import logging
import subprocess
from multiprocessing.pool import Pool
from pathlib import Path

from .config import EchoDownloaderConfig
from .domain import Echo360Lecture, FileInfo
from .helpers import encode_path

logger = logging.getLogger(__name__)


def merge_files_concurrently(
        config: EchoDownloaderConfig,
        output_dir: Path,
        lectures: list[Echo360Lecture]
) -> list[Path]:
    file_infos = get_file_infos(config, output_dir, lectures)

    with Pool() as pool:
        list(pool.imap_unordered(merge_files_wrapper, file_infos))

    if config.delete_source_files:
        directories = set()

        for info in file_infos:
            for key, path in info.items():
                if key == 'output_path':
                    continue
                path.unlink(missing_ok=True)
                directories.add(path.parent)

        for directory in directories:
            if not list(directory.iterdir()):
                directory.rmdir()

    return [info['output_path'] for info in file_infos]


def merge_files_wrapper(file_infos: dict[str, Path]) -> None:
    merge_files(**file_infos)


def merge_files(*, audio_path: Path, video_path: Path, output_path: Path) -> None:
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


def get_file_infos(
        config: EchoDownloaderConfig,
        output_dir: Path,
        lectures: list[Echo360Lecture]
) -> list[dict[str, Path]]:
    file_infos = []
    extensions = ['m4s', 'mp4']
    qualities = ['q1', 'q0']
    sources = {'screen': 's1', 'camera': 's2'}

    for lecture in lectures:
        encoded_title = encode_path(repr(lecture))
        course_folder = output_dir / encode_path(lecture.course_name)
        info: FileInfo
        file_names = {info.file_name for info in lecture.file_infos}

        for ext in extensions:
            for q_audio in qualities:
                audio = f's0{q_audio}.{ext}'
                if audio not in file_names:
                    continue

                for source_type, source in sources.items():
                    title_suffix = config.title_suffixes[source_type]
                    output_path = course_folder / (encoded_title + title_suffix + '.mp4')
                    if output_path.exists():
                        logger.info(f'File already exists: {output_path}, skipping...')
                        continue

                    for q_video in qualities:
                        video = f'{source}{q_video}.{ext}'
                        logger.debug(f'Checking for video: {video}')

                        if video in file_names:
                            logger.debug(f'Found video: {video}')
                            file_infos.append({
                                'audio_path': course_folder / encoded_title / audio,
                                'video_path': course_folder / encoded_title / video,
                                'output_path': output_path
                            })
                            break
                        else:
                            logger.debug(f'Video not found: {video}')

    return file_infos
