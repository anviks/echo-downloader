import asyncio
import logging
import os
import re
import time
from datetime import datetime
from typing import Any, Callable

import aiohttp
import jsonpickle
import platformdirs
import requests
import wx
import yaml
from prompt_toolkit.application import Application
from prompt_toolkit.completion import PathCompleter
from prompt_toolkit.eventloop import run_in_executor_with_context
from prompt_toolkit.filters import to_filter
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import Layout, VSplit
from prompt_toolkit.layout.containers import AnyContainer, HSplit
from prompt_toolkit.styles import BaseStyle
from prompt_toolkit.validation import Validator
from prompt_toolkit.widgets import Button, CheckboxList, Dialog, Label, ProgressBar, TextArea
from utils_anviks import dict_to_object
from dotenv import load_dotenv

from config_wrapper import EchoDownloaderConfig

from config import load_config
from domain import Echo360Lecture, FileInfo
from downloader import download_lecture_files
from merger import merge_files_concurrently


def get_file_size_string(size: int) -> str:
    if size >= 1 << 30:
        return f'{size / (1 << 30):.2f} GiB'
    else:
        return f'{size / (1 << 20):.2f} MiB'


async def animate_loading(done_event: asyncio.Event, label: Label):
    original_text = label.text
    dots = ["   ", ".  ", ".. ", "..."]
    i = 0
    while not done_event.is_set():
        label.text = f"{original_text}{dots[i % 4]}"
        app.invalidate()
        i += 1
        await asyncio.sleep(0.5)


def create_app(dialog: AnyContainer, style: BaseStyle | None) -> Application[Any]:
    bindings = KeyBindings()
    bindings.add(Keys.ControlQ)(lambda event: app.exit(result=None))

    return Application(
        layout=Layout(dialog),
        key_bindings=bindings,
        mouse_support=True,
        style=style,
        full_screen=True,
    )


def create_url_dialog(continue_callback: Callable[[], Any]) -> Dialog:
    hex_ = '[0-9a-f]'
    uuid_regex = fr'{hex_}{{8}}-{hex_}{{4}}-{hex_}{{4}}-{hex_}{{4}}-{hex_}{{12}}'
    echo_url_regex = re.compile(fr'^https?://echo360\.org\.uk/section/({uuid_regex})/(public|home)$')

    def on_input(_):
        if error_label.text:
            error_label.text = ''
            app.invalidate()

    def on_submit():
        if not url_input.buffer.validate():
            error_label.text = 'Invalid Echo360 URL'
            app.invalidate()
            return

        match = echo_url_regex.search(url_input.text)
        if match.group(2) == 'home':
            dialog_choices['course_uuid'] = match.group(1)
        else:  # 'public'
            response = requests.get(url_input.text, allow_redirects=False)
            redirect_match = echo_url_regex.search('https://echo360.org.uk' + response.headers['Location'])
            dialog_choices['course_uuid'] = redirect_match.group(1)
        continue_callback()

    def on_cancel():
        app.exit()

    def validate_url(url: str) -> bool:
        return bool(echo_url_regex.search(url))

    url_input = TextArea(
        multiline=False,
        height=1,
        width=80,
        validator=Validator.from_callable(validate_url),
    )
    url_input.buffer.on_text_changed += on_input

    url_label = Label(text='URL:', dont_extend_width=True)
    error_label = Label(text='', style='class:red')

    dialog = Dialog(
        title='Enter Echo360 URL',
        body=HSplit([
            VSplit([url_label, url_input], padding=1),
            error_label
        ]),
        buttons=[
            Button(text="Continue", handler=on_submit),
            Button(text="Cancel", handler=on_cancel),
        ],
        with_background=True,
    )

    return dialog


def create_lectures_dialog(selection: list[tuple[Echo360Lecture, str]], continue_callback: Callable[[], None]) -> tuple[Dialog, AnyContainer]:
    def ok_handler() -> None:
        if not cb_list.current_values:
            app.exit(result='No lectures selected')
        dialog_choices['lectures'] = cb_list.current_values
        logger.debug(dialog_choices['lectures'])
        continue_callback()

    def _return_none() -> None:
        app.exit(result=None)

    cb_list = CheckboxList(values=selection)

    dialog = Dialog(
        title='Select lectures to download',
        body=cb_list,
        buttons=[
            Button(text='Continue', handler=ok_handler),
            Button(text='Cancel', handler=_return_none),
        ],
        with_background=True,
    )

    return dialog, cb_list


def create_path_dialog(continue_callback: Callable[[], None]) -> tuple[Dialog, AnyContainer]:
    def on_submit():
        dialog_choices['path'] = path_input.text
        continue_callback()

    def on_cancel():
        app.exit()

    def ask_for_directory():
        _ = wx.App(False)
        dir_dialog = wx.DirDialog(
            None,
            'Select directory',
            style=(wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)
        )
        if dir_dialog.ShowModal() == wx.ID_OK:
            chosen_dir = dir_dialog.GetPath()
        else:
            chosen_dir = None
        dir_dialog.Destroy()

        return chosen_dir

    def open_selector():
        selected_path = ask_for_directory()
        if selected_path:
            path_input.text = selected_path

    path_completer = PathCompleter(only_directories=True, expanduser=True)
    path_input = TextArea(
        completer=path_completer,
        multiline=False,
        height=1,
    )

    dialog = Dialog(
        title='Enter output path',
        body=VSplit([Button(text='Select directory', width=20, handler=open_selector), path_input], padding=2),
        buttons=[
            Button(text="Begin download", width=18, handler=on_submit),
            Button(text="Cancel", handler=on_cancel),
        ],
        with_background=True,
    )

    return dialog, path_input


def create_download_dialog(
        files: list[FileInfo],
        run_callback: Callable[[Callable[[int, int], None]], None] = (
                lambda *a: None
        ),
):
    file_count = len(files)
    progress_bars = [ProgressBar() for _ in range(file_count)]
    labels = [Label('0 / 0 MiB', width=25) for _ in range(file_count)]
    total_sizes = [file.size for file in files]
    total_size_strings = [get_file_size_string(size) for size in total_sizes]

    for bar in progress_bars:
        bar.percentage = 0

    dialog = Dialog(
        title='Downloading files...',
        body=VSplit([
            HSplit(labels, padding=1),
            HSplit(progress_bars, padding=1),
        ], padding=1),
        with_background=True,
    )

    def set_progress(i: int, downloaded: int) -> None:
        progress_bars[i].percentage = (downloaded / total_sizes[i]) * 100
        downloaded_str = get_file_size_string(downloaded)
        labels[i].text = f'{downloaded_str} / {total_size_strings[i]}'
        app.invalidate()

    def start() -> None:
        run_callback(set_progress)
        dialog.title = 'Muxing files...'
        app.invalidate()
        output_files = merge_files_concurrently(config, dialog_choices['path'], dialog_choices['lectures'], False)
        result = f'Lectures downloaded and muxed to\n{'\n'.join(output_files)}' if output_files else 'Muxed files already exist'
        app.exit(result=result)

    return dialog, start


async def continue_to_lecture_selection():
    loading_label = Label(text="Fetching lectures")
    loading_dialog = Dialog(title="Please wait", body=HSplit([loading_label]), with_background=True)

    app.layout = Layout(loading_dialog)
    app.invalidate()

    done_event = asyncio.Event()
    asyncio.create_task(animate_loading(done_event, loading_label))

    lectures = []

    async with aiohttp.ClientSession() as sess:
        await sess.get(arbitrary_url)

        async with sess.get(f'https://echo360.org.uk/section/{dialog_choices['course_uuid']}/syllabus') as response:
            json_data = await response.json()
            for lesson in json_data['data']:
                if not lesson['lesson']['medias']:
                    continue

                institution_id = lesson['lesson']['lesson']['institutionId']
                media_id = lesson['lesson']['medias'][0]['id']

                lecture = Echo360Lecture()
                lecture.title = lesson['lesson']['lesson']['name']
                lecture.course_uuid = lesson['lesson']['lesson']['sectionId']

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

                for source in [0, 1, 2]:
                    for quality in [1, 0]:
                        file_name = f's{source}q{quality}.m4s'
                        url = f'https://content.echo360.org.uk/0000.{institution_id}/{media_id}/1/{file_name}'
                        async with sess.head(url) as head_response:
                            logger.debug(f's{source}q{quality}.m4s - {head_response.status}')
                            if head_response.status == 200:
                                file_size = int(head_response.headers['Content-Length'])
                                lecture.file_infos.append(FileInfo(file_name, file_size, url=url))
                                break

                lectures.append((lecture, lecture.title))

    # with open('tarkvaratehnika.json', 'w') as f:
    #     f.write(jsonpickle.encode(lectures, indent=2))

    # await asyncio.sleep(2)

    done_event.set()

    # with open('tarkvaratehnika.json', 'r') as f:
    #     lectures = jsonpickle.decode(f.read())

    lectures_dialog, element_to_focus = create_lectures_dialog(lectures, continue_to_path_selection)
    app.layout = Layout(lectures_dialog)
    app.layout.focus(element_to_focus)
    app.invalidate()


def continue_to_path_selection():
    path_dialog, element_to_focus = create_path_dialog(continue_to_download)
    app.layout = Layout(path_dialog)
    app.layout.focus(element_to_focus)
    app.invalidate()


def continue_to_download():
    files = [info for lecture in dialog_choices['lectures'] for info in lecture.file_infos]
    download_dialog, start = create_download_dialog(files, lambda set_progress: asyncio.run(download_lecture_files(dialog_choices['path'], dialog_choices['lectures'], set_progress)))
    app.layout = Layout(download_dialog)
    app.invalidate()
    run_in_executor_with_context(start)


if __name__ == '__main__':
    logging.basicConfig(
        filename='echo_downloader.log',
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)-8s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    logger = logging.getLogger(__name__)

    load_dotenv()
    arbitrary_url = os.getenv('ECHO_O')

    config = load_config()

    dialog_choices: dict[str, Any] = {
        'lectures': None,
        'path': None,
        'download': None,
        'course_uuid': None,
    }

    url_dialog = create_url_dialog(lambda: asyncio.get_running_loop().create_task(continue_to_lecture_selection()))
    app = create_app(url_dialog, None)
    print(app.run())
