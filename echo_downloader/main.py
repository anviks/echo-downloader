import asyncio
import logging
from datetime import datetime
from pathlib import Path

import aiohttp
import platformdirs
from bs4 import BeautifulSoup
from prompt_toolkit.eventloop import run_in_executor_with_context
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import HSplit
from prompt_toolkit.widgets import Dialog, Label

from .config import load_config
from .domain import Echo360Lecture, FileInfo
from .downloader import download_lecture_files
from .merger import merge_files_concurrently
from .types.payload import Datum, Model
from .ui import (
    create_app,
    create_download_dialog,
    create_lectures_dialog,
    create_path_dialog,
    create_url_dialog,
)


async def get_file_size(sess: aiohttp.ClientSession, url: str) -> int | None:
    async with sess.head(url) as res:
        if res.status == 200:
            return int(res.headers.get("Content-Length", 0))


class EchoDownloaderApp:
    app_name = "echo-downloader"

    def __init__(self):
        # Arbitrary '/public' URL to get the cookies
        self.arbitrary_url = (
            "https://echo360.org.uk/section/6432fa3a-61e1-4cfe-b7c3-94c72e1b6386/public"
        )
        self.config = load_config()
        self.logger = self.get_logger()
        self.app = None

    def get_logger(self):
        log_dir = platformdirs.user_log_path(self.app_name, appauthor=False)
        log_dir.mkdir(parents=True, exist_ok=True)

        log_files: list[Path] = sorted(
            log_dir.glob(f"{self.app_name}_*.log"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        for old_log in log_files[self.config.max_logs :]:
            old_log.unlink()

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_file = log_dir / f"{self.app_name}_{timestamp}.log"

        logging.basicConfig(
            filename=log_file,
            level=logging.DEBUG,
            format="%(asctime)s - %(name)s - %(levelname)-8s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        return logging.getLogger(__name__)

    def run(self):
        url_dialog = create_url_dialog(
            lambda course_uuid: asyncio.get_running_loop().create_task(
                self.continue_to_lecture_selection(course_uuid)
            )
        )
        self.app = create_app(url_dialog, None)

        return self.app.run()

    async def collect_lecture(
        self, sess: aiohttp.ClientSession, lesson: Datum, course_name: str
    ) -> tuple[Echo360Lecture, str] | None:
        if not lesson["lesson"]["medias"]:
            return

        institution_id = lesson["lesson"]["lesson"]["institutionId"]
        media_id = lesson["lesson"]["medias"][0]["id"]

        lecture = Echo360Lecture()
        lecture.title = lesson["lesson"]["lesson"]["name"]
        lecture.course_uuid = lesson["lesson"]["lesson"]["sectionId"]
        lecture.course_name = course_name

        if lesson["lesson"]["isScheduled"]:
            start_dt_str = lesson["lesson"]["captureStartedAt"]
            end_dt_str = lesson["lesson"]["captureEndedAt"]
        else:
            start_dt_str = lesson["lesson"]["lesson"]["timing"]["start"]
            end_dt_str = lesson["lesson"]["lesson"]["timing"]["end"]

        start_dt = datetime.fromisoformat(start_dt_str)
        end_dt = datetime.fromisoformat(end_dt_str)

        lecture.date = start_dt.date()
        lecture.start_time = start_dt.time()
        lecture.end_time = end_dt.time()

        candidates = [
            (ext, src, q)
            for ext in ["mp4", "m4s"]
            for src in ["s0", "s1", "s2"]
            for q in ["q1", "q0"]
        ]

        urls = [
            f"https://content.echo360.org.uk/0000.{institution_id}/{media_id}/1/{src}{q}.{ext}"
            for (ext, src, q) in candidates
        ]

        sizes = await asyncio.gather(*[get_file_size(sess, url) for url in urls])

        found = {}
        for (ext, src, q), url, size in zip(candidates, urls, sizes):
            if size is None:
                continue

            key = (ext, src)
            if (
                key not in found
            ):  # keep q1 (higher quality) if it exists, otherwise q0 (lower quality)
                found[key] = FileInfo(file_name=f"{src}{q}.{ext}", size=size, url=url)

        lecture.file_infos = list(found.values())

        if not lecture.file_infos:
            self.logger.warning(f"No files found for lecture: {lecture}")
            return

        # Keep only mp4 or only m4s, whichever has more files
        if len(lecture.file_infos) > 1:
            mp4_files = [
                info for info in lecture.file_infos if info.file_name.endswith(".mp4")
            ]
            m4s_files = [
                info for info in lecture.file_infos if info.file_name.endswith(".m4s")
            ]
            if len(mp4_files) >= len(m4s_files):
                lecture.file_infos = mp4_files
            else:
                lecture.file_infos = m4s_files

        date_str = lecture.date.strftime("%B %d, %Y")
        time_range_str = f"{lecture.start_time:%H:%M}-{lecture.end_time:%H:%M}"

        return (lecture, f"{lecture.title}   {date_str} {time_range_str}")

    async def get_lecture_selection(self, course_uuid: str):
        lectures = []

        async with (
            aiohttp.ClientSession() as sess,
            sess.get(self.arbitrary_url),
            sess.get(
                f"https://echo360.org.uk/section/{course_uuid}/syllabus"
            ) as syllabus,
            sess.get(f"https://echo360.org.uk/section/{course_uuid}/home") as homepage,
        ):
            html = await homepage.text()
            soup = BeautifulSoup(html, features="html.parser")
            section_header = soup.select_one(
                "body > div.main-content > div.course-section-header > h1"
            )
            course_name = list(section_header.children)[2].text.strip()

            json_data: Model = await syllabus.json()
            tasks = [
                self.collect_lecture(sess, lesson, course_name)
                for lesson in json_data["data"]
            ]
            lectures = [
                lecture
                for lecture in await asyncio.gather(*tasks)
                if lecture is not None
            ]

        return lectures

    async def animate_loading(self, done_event: asyncio.Event, label: Label):
        original_text = label.text
        dots = ["   ", ".  ", ".. ", "..."]
        i = 0
        while not done_event.is_set():
            label.text = f"{original_text}{dots[i % 4]}"
            self.app.invalidate()
            i += 1
            await asyncio.sleep(0.5)

    async def continue_to_lecture_selection(self, course_uuid: str):
        loading_label = Label(text="Fetching lectures")
        loading_dialog = Dialog(
            title="Please wait", body=HSplit([loading_label]), with_background=True
        )

        self.app.layout = Layout(loading_dialog)
        self.app.invalidate()

        done_event = asyncio.Event()
        loading_task = asyncio.create_task(
            self.animate_loading(done_event, loading_label)
        )
        lectures = await self.get_lecture_selection(course_uuid)
        done_event.set()
        await loading_task  # Ensure the loading animation is stopped before continuing

        lectures_dialog, element_to_focus = create_lectures_dialog(
            lectures, self.continue_to_path_selection
        )
        self.app.layout = Layout(lectures_dialog)
        self.app.layout.focus(element_to_focus)
        self.app.invalidate()

    def continue_to_path_selection(self, lectures: list[Echo360Lecture]):
        path_dialog, element_to_focus = create_path_dialog(
            self.config, lambda path: self.continue_to_download(lectures, path)
        )
        self.app.layout = Layout(path_dialog)
        self.app.layout.focus(element_to_focus)
        self.app.invalidate()

    def continue_to_download(self, lectures: list[Echo360Lecture], path: Path):
        files = [info for lecture in lectures for info in lecture.file_infos]
        download_dialog, set_progress = create_download_dialog(files)
        self.app.layout = Layout(download_dialog)
        self.app.invalidate()

        def download_and_merge():
            asyncio.run(
                download_lecture_files(path, self.arbitrary_url, lectures, set_progress)
            )
            download_dialog.title = "Muxing files..."
            self.app.invalidate()
            output_files = merge_files_concurrently(self.config, path, lectures)
            if output_files:
                result = f"Lectures downloaded and muxed to\n{chr(10).join(map(str, output_files))}"
            else:
                result = "No lectures were muxed"
            self.app.exit(result=result)

        run_in_executor_with_context(download_and_merge)


def main():
    echo_app = EchoDownloaderApp()
    run_result = echo_app.run()
    echo_app.logger.info(f"Application exited with result: {run_result}")
    print(run_result or "", end="\n" if run_result else "")


if __name__ == "__main__":
    main()
