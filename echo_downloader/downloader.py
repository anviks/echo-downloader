import asyncio
import logging
from pathlib import Path
from typing import Callable

import aiofiles
import aiohttp

from .domain import Echo360Lecture
from .helpers import encode_path

logger = logging.getLogger(__name__)


async def download_lecture_files(
        output_dir: Path,
        initial_url: str,
        lectures: list[Echo360Lecture],
        set_progress: Callable[[int, int], None]
) -> None:
    logger.info('Downloading files...')
    async with aiohttp.ClientSession() as session:
        await session.get(initial_url)

        i = 0
        tasks = []
        progresses: list[tuple[int, int] | None] = []

        for lecture in lectures:
            if not lecture.file_infos:
                continue

            folder = output_dir / encode_path(lecture.course_name) / encode_path(repr(lecture))
            folder.mkdir(parents=True, exist_ok=True)

            for info in lecture.file_infos:
                progresses.append(None)

                if info.url is None:
                    continue

                destination_path = folder / info.file_name
                info.local_path = destination_path
                # Inner lambda needs to be wrapped in another lambda to capture the current value of i
                progress_update_callback = (lambda bound_i: lambda downloaded: set_progress(bound_i, downloaded))(i)
                task = asyncio.create_task(download_file(session, destination_path, info.url, progress_update_callback))
                tasks.append(task)
                logger.debug(f'Started downloading {info.url} to {destination_path}')
                i += 1

        results = await asyncio.gather(*tasks, return_exceptions=True)
        logger.debug(f'Results: {results}')
    logger.info('All files downloaded')


async def download_file(
        session: aiohttp.ClientSession,
        destination_path: Path,
        url: str,
        progress_update_callback: Callable[[int], None]
) -> None:
    try:
        async with session.get(url, timeout=30 * 60) as response:
            downloaded_size = 0
            total_size = int(response.headers.get('Content-Length', 0))

            # Return if the file already exists
            if destination_path.exists() and destination_path.stat().st_size == total_size:
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
