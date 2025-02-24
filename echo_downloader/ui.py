import logging
import re
from pathlib import Path
from typing import Any, Callable

import requests
import wx
from prompt_toolkit.application import Application, get_app
from prompt_toolkit.completion import PathCompleter
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import Dimension, Layout, VSplit
from prompt_toolkit.layout.containers import AnyContainer, HSplit
from prompt_toolkit.styles import BaseStyle
from prompt_toolkit.validation import Validator
from prompt_toolkit.widgets import Button, CheckboxList, Dialog, Label, ProgressBar, TextArea

from .config import EchoDownloaderConfig
from .domain import Echo360Lecture, FileInfo
from .helpers import get_file_size_string, get_long_path

logger = logging.getLogger(__name__)


def create_app(dialog: AnyContainer, style: BaseStyle | None) -> Application[Any]:
    bindings = KeyBindings()
    bindings.add(Keys.ControlQ)(lambda event: get_app().exit(result=None))

    return Application(
        layout=Layout(dialog),
        key_bindings=bindings,
        mouse_support=True,
        style=style,
        full_screen=True,
    )


def create_url_dialog(continue_callback: Callable[[str], Any]) -> Dialog:
    app = get_app()

    hex_ = '[0-9a-f]'
    uuid_regex = fr'{hex_}{{8}}-{hex_}{{4}}-{hex_}{{4}}-{hex_}{{4}}-{hex_}{{12}}'
    echo_url_regex = re.compile(fr'^https?://echo360\.org\.uk/section/({uuid_regex})/(public|home)$')

    def on_input(_):
        if error_label.text:
            error_label.text = ''
            app.invalidate()

    def on_submit():
        if not url_input.buffer.validate():
            logger.debug(f'Invalid Echo360 URL entered: {url_input.text}')
            error_label.text = 'Invalid Echo360 URL'
            app.invalidate()
            return

        logger.debug(f'Echo360 URL entered: {url_input.text}')

        match = echo_url_regex.search(url_input.text)
        if match.group(2) == 'home':
            course_uuid = match.group(1)
        else:  # 'public'
            response = requests.get(url_input.text, allow_redirects=False)
            redirect_match = echo_url_regex.search('https://echo360.org.uk' + response.headers['Location'])
            course_uuid = redirect_match.group(1)

        continue_callback(course_uuid)

    def on_cancel():
        get_app().exit()

    def validate_url(url: str) -> bool:
        return bool(echo_url_regex.search(url))

    url_input = TextArea(
        multiline=False,
        height=1,
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
        width=Dimension(min=85),
        buttons=[
            Button(text="Continue", handler=on_submit),
            Button(text="Cancel", handler=on_cancel),
        ],
        with_background=True,
    )

    return dialog


def create_lectures_dialog(
        selection: list[tuple[Echo360Lecture, str]],
        continue_callback: Callable[[list[Echo360Lecture]], None]
) -> tuple[Dialog, AnyContainer]:
    def on_submit() -> None:
        if not cb_list.current_values:
            get_app().exit(result='No lectures selected')
        lectures = cb_list.current_values
        continue_callback(lectures)

    def on_cancel() -> None:
        get_app().exit()

    cb_list = CheckboxList(values=selection)

    dialog = Dialog(
        title='Select lectures to download',
        body=cb_list,
        width=Dimension(min=85),
        buttons=[
            Button(text='Continue', handler=on_submit),
            Button(text='Cancel', handler=on_cancel),
        ],
        with_background=True,
    )

    return dialog, cb_list


def create_path_dialog(
        config: EchoDownloaderConfig,
        continue_callback: Callable[[Path], None]
) -> tuple[Dialog, AnyContainer]:
    def on_submit():
        selected_path = path_input.text
        logger.debug(f'Output path selected: {selected_path}')
        continue_callback(get_long_path(Path(selected_path)))

    def on_cancel():
        get_app().exit()

    def ask_for_directory():
        logger.debug('Opening directory selection dialog...')
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

    if config.path_completion:
        path_completer = PathCompleter(only_directories=True, expanduser=True)
    else:
        path_completer = None

    path_input = TextArea(
        completer=path_completer,
        multiline=False,
        height=1,
    )

    dialog = Dialog(
        title='Enter output path',
        body=VSplit([Button(text='Select directory', width=20, handler=open_selector), path_input], padding=2),
        width=Dimension(min=85),
        buttons=[
            Button(text="Begin download", width=18, handler=on_submit),
            Button(text="Cancel", handler=on_cancel),
        ],
        with_background=True,
    )

    return dialog, path_input


def create_download_dialog(files: list[FileInfo]):
    app = get_app()

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
        width=Dimension(min=85),
        with_background=True,
    )

    def set_progress(i: int, downloaded: int) -> None:
        progress_bars[i].percentage = (downloaded / total_sizes[i]) * 100
        downloaded_str = get_file_size_string(downloaded)
        labels[i].text = f'{downloaded_str} / {total_size_strings[i]}'
        app.invalidate()

    return dialog, set_progress
