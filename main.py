import asyncio
import logging
import os
import time
from typing import Any, Callable

import jsonpickle
import platformdirs
import wx
import yaml
from prompt_toolkit.application import Application
from prompt_toolkit.completion import PathCompleter
from prompt_toolkit.eventloop import run_in_executor_with_context
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import Layout, VSplit
from prompt_toolkit.layout.containers import AnyContainer, HSplit
from prompt_toolkit.styles import BaseStyle
from prompt_toolkit.widgets import Button, CheckboxList, Dialog, Label, ProgressBar, TextArea
from utils_anviks import dict_to_object
from dotenv import load_dotenv

from config_wrapper import EchoDownloaderConfig
from domain import FileInfo
from downloader import download_lecture_files
from merger import merge_files_concurrently


def get_file_size_string(size: int) -> str:
    if size >= 1 << 30:
        return f'{size / (1 << 30):.2f} GiB'
    else:
        return f'{size / (1 << 20):.2f} MiB'


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


def create_lectures_dialog(continue_callback: Callable[[], None]) -> Dialog:
    def ok_handler() -> None:
        dialog_choices['lectures'] = cb_list.current_values
        logger.debug(dialog_choices['lectures'])
        continue_callback()

    def _return_none() -> None:
        app.exit(result=None)

    cb_list = CheckboxList(values=sel)

    dialog = Dialog(
        title='Select some items',
        body=HSplit(
            [Label(text='yo', dont_extend_height=True), cb_list],
            padding=1,
        ),
        buttons=[
            Button(text='Continue', handler=ok_handler),
            Button(text='Cancel', handler=_return_none),
        ],
        with_background=True,
    )

    return dialog


def create_path_dialog(continue_callback: Callable[[], None]) -> tuple[Dialog, AnyContainer]:
    def on_submit():
        dialog_choices['path'] = path_input.text
        continue_callback()

    def on_cancel():
        app.exit()

    def ask_for_directory():
        wx_app = wx.App(False)
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
        ]
    )

    return dialog, path_input


def create_download_dialog(
        files: list[FileInfo],
        run_callback: Callable[[Callable[[int, int, int], None]], None] = (
                lambda *a: None
        ),
):
    file_count = len(files)
    progress_bars = [ProgressBar() for _ in range(file_count)]
    labels = [Label('0 / 0 MiB', width=25) for _ in range(file_count)]
    total_size_strings = [get_file_size_string(file.size) for file in files]

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

    def set_progress(i: int, downloaded: int, total: int) -> None:
        progress_bars[i].percentage = (downloaded / total) * 100
        downloaded_str = get_file_size_string(downloaded)
        labels[i].text = f'{downloaded_str} / {total_size_strings[i]}'
        app.invalidate()

    def start() -> None:
        run_callback(set_progress)
        dialog.title = 'Muxing files...'
        app.invalidate()
        output_files = merge_files_concurrently(config, dialog_choices['path'], dialog_choices['lectures'], False)
        app.exit(result=f'Lectures downloaded and muxed to\n{'\n'.join(output_files)}')

    return dialog, start


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
    url = os.getenv('ECHO_O')

    config_dir = platformdirs.user_config_dir('echo-downloader', 'anviks', roaming=True)
    default_config_path = os.path.join(os.path.dirname(__file__), 'config.yaml')
    custom_config_path = os.path.join(config_dir, 'config.yaml')

    with open(default_config_path) as f:
        file_contents = f.read()

    config_dict = yaml.safe_load(file_contents)

    if not os.path.exists(custom_config_path):
        os.makedirs(os.path.dirname(custom_config_path), exist_ok=True)
        with open(custom_config_path, 'w') as f:
            f.write(file_contents)
    else:
        with open(custom_config_path) as f:
            config_dict.update(yaml.safe_load(f))

    config = dict_to_object(config_dict, EchoDownloaderConfig)

    # with EchoScraper(config, url, headless=False) as scraper:
    #     sel = scraper.get_lecture_selection()
    #     # exit(0)
    #
    # with open('test_lectures.json', 'w') as f:
    #     f.write(jsonpickle.encode(sel, indent=2))
    #     exit(0)

    with open('test_lectures.json', 'r') as f:
        sel = jsonpickle.decode(f.read())

    dialog_choices: dict[str, Any] = {
        'lectures': None,
        'path': None,
        'download': None,
    }
    lectures_dialog = create_lectures_dialog(continue_to_path_selection)
    app = create_app(lectures_dialog, None)
    print(app.run())
