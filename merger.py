import logging
import os
import subprocess
from functools import partial
from multiprocessing.pool import Pool

from domain import Echo360Lecture, FileInfo
from config_wrapper import EchoDownloaderConfig
from urllib.parse import quote

logger = logging.getLogger(__name__)
SAFE_CHARS = ' #[]'


def merge_files_concurrently(
        config: EchoDownloaderConfig,
        output_dir: str,
        lectures: list[Echo360Lecture],
        delete_originals: bool = True
) -> list[str]:
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

    return [os.path.abspath(info['output_path']) for info in file_infos]


def merge_files_wrapper(file_infos: dict[str, str]) -> None:
    merge_files(**file_infos)


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
    qualities = ['q1', 'q0']
    sources = {'screen': 's1', 'camera': 's2'}

    for lecture in lectures:
        course_folder = os.path.join(output_dir, quote(lecture.course_uuid, SAFE_CHARS))
        folder_join = partial(os.path.join, course_folder)
        info: FileInfo
        file_names = {info.file_name for info in lecture.file_infos}

        for q_audio in qualities:
            audio = f's0{q_audio}.m4s'
            if audio not in file_names:
                continue

            for source_type, source in sources.items():
                title_suffix = config.title_suffixes[source_type]
                output_path = folder_join(quote(repr(lecture), SAFE_CHARS) + title_suffix + '.mp4')
                if os.path.exists(output_path):
                    logger.info(f'File already exists: {output_path}, skipping...')
                    continue

                for q_video in qualities:
                    video = f'{source}{q_video}.m4s'

                    if video in file_names:
                        file_infos.append({
                            'audio_path': folder_join(quote(repr(lecture), SAFE_CHARS), audio),
                            'video_path': folder_join(quote(repr(lecture), SAFE_CHARS), video),
                            'output_path': output_path
                        })
                        break

    return file_infos
