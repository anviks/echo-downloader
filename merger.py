import logging
import os
import subprocess
from functools import partial
from multiprocessing import Pool

from domain import Echo360Lecture, FileInfo
from config_wrapper import EchoDownloaderConfig
from urllib.parse import quote

logger = logging.getLogger(__name__)
SAFE_CHARS = ' #[]'

def merge_files_concurrently(config: EchoDownloaderConfig, output_dir: str, lectures: list[Echo360Lecture],
                             delete_originals: bool = True) -> None:
    file_infos = get_file_infos(config, output_dir, lectures)

    with Pool() as pool:
        list(pool.imap_unordered(merge_files_wrapper, file_infos))

    if delete_originals:
        directories = set()

        for info in file_infos:
            for key, path in info.items():
                if key == 'output_path':
                    continue
                if os.path.exists(path):
                    os.remove(path)
                directories.add(os.path.dirname(path))

        for directory in directories:
            if not os.listdir(directory):
                os.rmdir(directory)


def merge_files_wrapper(file_info: dict[str, str]) -> None:
    merge_files(**file_info)


def merge_files(*, audio_path: str, video_path: str, output_path: str) -> None:
    ffmpeg_cmd = [
        'ffmpeg',
        '-i', audio_path,
        '-i', video_path,
        '-c:a', 'copy',
        '-c:v', 'copy',
        output_path
    ]

    try:
        process = subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logger.info(f'Muxing completed successfully! ({output_path})')
        logger.debug(f'Process: {process}')
    except subprocess.CalledProcessError as e:
        logger.exception(f'Error while muxing: {e}')


def get_file_infos(config: EchoDownloaderConfig, output_dir: str, lectures: list[Echo360Lecture]) -> list[dict[str, str]]:
    file_infos = []

    for lecture in lectures:
        course_folder = os.path.join(output_dir, quote(lecture.course_name, SAFE_CHARS))
        folder_join = partial(os.path.join, course_folder)
        info: FileInfo
        file_names = {info.file_name for info in lecture.file_infos}

        for title_suffix, av_pairs in config.file_pairs.items():
            output_path = folder_join(quote(repr(lecture), SAFE_CHARS) + title_suffix + '.mp4')
            if os.path.exists(output_path):
                logger.info(f'File already exists: {output_path}, skipping...')
                continue

            for audio, video in av_pairs:
                if audio in file_names and video in file_names:
                    kwargs = dict(audio_path=folder_join(quote(repr(lecture), SAFE_CHARS), audio),
                                  video_path=folder_join(quote(repr(lecture), SAFE_CHARS), video),
                                  output_path=output_path)

                    file_infos.append(kwargs)
                    break

    return file_infos
