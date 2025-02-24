import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path

import aiohttp
import platformdirs
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from prompt_toolkit.eventloop import run_in_executor_with_context
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import HSplit
from prompt_toolkit.widgets import Dialog, Label

from config import load_config
from debug_tools import lecture_cache
from domain import Echo360Lecture, FileInfo
from downloader import download_lecture_files
from merger import merge_files_concurrently
from ui import create_app, create_download_dialog, create_lectures_dialog, create_path_dialog, create_url_dialog


async def animate_loading(done_event: asyncio.Event, label: Label):
    original_text = label.text
    dots = ['   ', '.  ', '.. ', '...']
    i = 0
    while not done_event.is_set():
        label.text = f'{original_text}{dots[i % 4]}'
        app.invalidate()
        i += 1
        await asyncio.sleep(0.5)


@lecture_cache.read
async def get_lecture_selection(course_uuid: str):
    lectures = []

    async with aiohttp.ClientSession() as sess:
        await sess.get(arbitrary_url)

        async with (sess.get(f'https://echo360.org.uk/section/{course_uuid}/syllabus') as syllabus,
                    sess.get(f'https://echo360.org.uk/section/{course_uuid}/home') as homepage):
            html = await homepage.text()
            soup = BeautifulSoup(html, features='html.parser')
            section_header = soup.select_one('body > div.main-content > div.course-section-header > h1')
            course_name = list(section_header.children)[2].text.strip()

            json_data = await syllabus.json()
            for lesson in json_data['data']:
                if not lesson['lesson']['medias']:
                    continue

                institution_id = lesson['lesson']['lesson']['institutionId']
                media_id = lesson['lesson']['medias'][0]['id']

                lecture = Echo360Lecture()
                lecture.title = lesson['lesson']['lesson']['name']
                lecture.course_uuid = lesson['lesson']['lesson']['sectionId']
                lecture.course_name = course_name

                if lesson['lesson']['isScheduled']:
                    start_dt_str = lesson['lesson']['captureStartedAt']
                    end_dt_str = lesson['lesson']['captureEndedAt']
                else:
                    start_dt_str = lesson['lesson']['lesson']['timing']['start']
                    end_dt_str = lesson['lesson']['lesson']['timing']['end']

                start_dt = datetime.fromisoformat(start_dt_str)
                end_dt = datetime.fromisoformat(end_dt_str)

                lecture.date = start_dt.date()
                lecture.start_time = start_dt.time()
                lecture.end_time = end_dt.time()

                for source in ['s0', 's1', 's2']:
                    for quality in ['q1', 'q0']:
                        file_name = f'{source}{quality}.m4s'
                        url = f'https://content.echo360.org.uk/0000.{institution_id}/{media_id}/1/{file_name}'
                        async with sess.head(url) as head_response:
                            if head_response.status == 200:
                                file_size = int(head_response.headers['Content-Length'])
                                lecture.file_infos.append(FileInfo(file_name, file_size, url=url))
                                break

                date_str = lecture.date.strftime('%B %d, %Y')
                time_range_str = f'{lecture.start_time:%H:%M}-{lecture.end_time:%H:%M}'

                lectures.append((lecture, f'{lecture.title}   {date_str} {time_range_str}'))

    return lectures


async def continue_to_lecture_selection(course_uuid: str):
    loading_label = Label(text='Fetching lectures')
    loading_dialog = Dialog(title='Please wait', body=HSplit([loading_label]), with_background=True)

    app.layout = Layout(loading_dialog)
    app.invalidate()

    done_event = asyncio.Event()
    loading_task = asyncio.create_task(animate_loading(done_event, loading_label))
    lectures = await get_lecture_selection(course_uuid)
    done_event.set()
    await loading_task  # Ensure the loading animation is stopped before continuing

    lectures_dialog, element_to_focus = create_lectures_dialog(lectures, continue_to_path_selection)
    app.layout = Layout(lectures_dialog)
    app.layout.focus(element_to_focus)
    app.invalidate()


def continue_to_path_selection(lectures: list[Echo360Lecture]):
    path_dialog, element_to_focus = create_path_dialog(config, lambda path: continue_to_download(lectures, path))
    app.layout = Layout(path_dialog)
    app.layout.focus(element_to_focus)
    app.invalidate()


def continue_to_download(lectures: list[Echo360Lecture], path: Path):
    files = [info for lecture in lectures for info in lecture.file_infos]
    download_dialog, set_progress = create_download_dialog(files)
    app.layout = Layout(download_dialog)
    app.invalidate()

    def download_and_merge():
        asyncio.run(download_lecture_files(path, lectures, set_progress))
        download_dialog.title = 'Muxing files...'
        app.invalidate()
        output_files = merge_files_concurrently(config, path, lectures)
        result = f'Lectures downloaded and muxed to\n{'\n'.join(map(str, output_files))}' if output_files else 'Muxed files already exist'
        app.exit(result=result)

    run_in_executor_with_context(download_and_merge)


if __name__ == '__main__':
    config = load_config()

    log_dir = platformdirs.user_log_path('echo_downloader', appauthor=False)
    log_dir.mkdir(parents=True, exist_ok=True)

    log_files: list[Path] = sorted(log_dir.glob('echo_downloader_*.log'), key=lambda f: f.stat().st_mtime, reverse=True)
    for old_log in log_files[config.max_logs:]:
        old_log.unlink()

    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    log_file = log_dir / f'echo_downloader_{timestamp}.log'

    logging.basicConfig(
        filename=log_file,
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)-8s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    logger = logging.getLogger(__name__)

    load_dotenv()
    arbitrary_url = os.getenv('ECHO_O')

    url_dialog = create_url_dialog(lambda course_uuid: asyncio.get_running_loop().create_task(continue_to_lecture_selection(course_uuid)))
    app = create_app(url_dialog, None)
    run_result = app.run()
    logger.info(f'Application exited with result: {run_result}')
    print(run_result)
