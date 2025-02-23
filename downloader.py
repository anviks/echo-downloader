import asyncio
import logging
import os
from typing import Callable

import aiofiles
import aiohttp
import jsonpickle
from dotenv import load_dotenv

from domain import Echo360Lecture
from helpers import get_long_path, encode_path

logger = logging.getLogger(__name__)
load_dotenv()
initial_url = os.getenv('ECHO_O')


async def download_lecture_files(
        output_dir: str,
        lectures: list[Echo360Lecture],
        set_progress: Callable[[int, int], None]
) -> None:
    logger.info('Downloading files...')
    async with aiohttp.ClientSession() as session:
        # Initial request to get the cookies
        await session.get(initial_url)

        i = 0
        tasks = []
        progresses: list[tuple[int, int] | None] = []

        for lecture in lectures:
            logger.info(jsonpickle.encode(lecture, False, indent=2))

            if not lecture.file_infos:
                continue

            folder = os.path.join(output_dir, lecture.course_uuid, encode_path(repr(lecture)))
            folder = get_long_path(folder)
            os.makedirs(folder, exist_ok=True)

            for info in lecture.file_infos:
                progresses.append(None)

                if info.url is None:
                    continue

                destination_path = os.path.join(folder, info.file_name)
                info.local_path = destination_path
                task = asyncio.create_task(download_file(session, destination_path, info.url, (lambda bound_i: lambda downloaded: set_progress(bound_i, downloaded))(i)))
                tasks.append(task)
                logger.debug(f'Started downloading {info.url} to {destination_path}')
                i += 1

        results = await asyncio.gather(*tasks, return_exceptions=True)
        logger.debug(f'Results: {results}')
    logger.info('All files downloaded')


async def download_file(
        session: aiohttp.ClientSession,
        destination_path: str,
        url: str,
        progress_update_callback: Callable[[int], None]
) -> None:
    try:
        async with session.get(url, timeout=30 * 60) as response:
            downloaded_size = 0
            total_size = int(response.headers.get('Content-Length', 0))

            # Return if the file already exists
            if os.path.exists(destination_path) and os.path.getsize(destination_path) == total_size:
                progress_update_callback(total_size)
                return
            response.raise_for_status()

            async with aiofiles.open(destination_path, 'wb') as f:
                async for chunk in response.content.iter_any():  # type: bytes
                    await f.write(chunk)
                    downloaded_size += len(chunk)
                    progress_update_callback(downloaded_size)
    except aiohttp.ClientError as e:
        logger.error(f"Failed to download {url}: {e}")
        await asyncio.sleep(0)  # Yield to the event loop to prevent blocking
