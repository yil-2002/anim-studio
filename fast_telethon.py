"""Parallel download/upload helpers for Telethon.

* 512 KB chunks (Telegram's maximum part size).
* 4-8 concurrent part requests per file (scaled by file size).
* ``FloodWaitError`` is awaited and the request retried automatically.

Nothing in this module logs; callers decide what (anonymous) output to print.
"""

from __future__ import annotations

import asyncio
import math
import os
from typing import Awaitable, Callable, TypeVar

import aiofiles
from telethon import TelegramClient, errors, helpers
from telethon.tl import types
from telethon.tl.functions.upload import SaveBigFilePartRequest, SaveFilePartRequest

CHUNK_SIZE = 512 * 1024
MIN_CONNECTIONS = 4
MAX_CONNECTIONS = 8
BIG_FILE_THRESHOLD = 10 * 1024 * 1024
MAX_FLOOD_RETRIES = 5
# Longer waits than this are not worth blocking a CI job for.
MAX_FLOOD_WAIT = 15 * 60

T = TypeVar("T")


def pick_connections(size: int) -> int:
    """4 workers for small files, up to 8 for large ones."""
    if size <= 0:
        return MIN_CONNECTIONS
    by_size = MIN_CONNECTIONS + int(size // (100 * 1024 * 1024))
    return max(MIN_CONNECTIONS, min(MAX_CONNECTIONS, by_size))


async def flood_retry(call: Callable[[], Awaitable[T]], retries: int = MAX_FLOOD_RETRIES) -> T:
    """Run ``call()``; on ``FloodWaitError`` sleep the requested time and retry."""
    attempt = 0
    while True:
        try:
            return await call()
        except errors.FloodWaitError as e:
            attempt += 1
            if attempt > retries or e.seconds > MAX_FLOOD_WAIT:
                raise
            await asyncio.sleep(e.seconds + 1)


class FastTelethon:
    def __init__(self, client: TelegramClient, connections: int | None = None) -> None:
        self.client = client
        self._fixed = None if connections is None else max(MIN_CONNECTIONS, min(MAX_CONNECTIONS, connections))

    def _workers(self, size: int) -> int:
        return self._fixed or pick_connections(size)

    # ------------------------------------------------------------------ download

    async def download(self, location: object, path: str, size: int, dc_id: int | None = None) -> str:
        """Download ``location`` (Document / InputFileLocation) of ``size`` bytes to ``path``."""
        parts = max(1, math.ceil(size / CHUNK_SIZE))
        workers = min(self._workers(size), parts)
        async with aiofiles.open(path, "wb") as f:
            await f.truncate(size)

        per_worker = math.ceil(parts / workers)
        ranges = [(i * per_worker, min(parts, (i + 1) * per_worker)) for i in range(workers)]
        await asyncio.gather(*(self._download_range(location, path, a, b, size, dc_id) for a, b in ranges if a < b))
        return path

    async def _download_range(self, location: object, path: str, first: int, last: int, size: int, dc_id: int | None) -> None:
        part = first
        retries = 0
        async with aiofiles.open(path, "r+b") as f:
            while part < last:
                try:
                    async for chunk in self.client.iter_download(
                        location,
                        offset=part * CHUNK_SIZE,
                        limit=last - part,
                        request_size=CHUNK_SIZE,
                        chunk_size=CHUNK_SIZE,
                        file_size=size,
                        dc_id=dc_id,
                    ):
                        await f.seek(part * CHUNK_SIZE)
                        await f.write(chunk)
                        part += 1
                    break
                except errors.FloodWaitError as e:
                    retries += 1
                    if retries > MAX_FLOOD_RETRIES or e.seconds > MAX_FLOOD_WAIT:
                        raise
                    await asyncio.sleep(e.seconds + 1)  # resume from the current part

    # ------------------------------------------------------------------ upload

    async def upload(self, path: str, name: str = "file") -> types.TypeInputFile:
        """Upload a local file in parallel parts and return an ``InputFile``/``InputFileBig``."""
        size = os.path.getsize(path)
        if size == 0:
            raise ValueError("empty file")
        parts = math.ceil(size / CHUNK_SIZE)
        is_big = size > BIG_FILE_THRESHOLD
        file_id = helpers.generate_random_long()
        workers = min(self._workers(size), parts)
        queue: asyncio.Queue[int] = asyncio.Queue()
        for i in range(parts):
            queue.put_nowait(i)

        async def worker() -> None:
            async with aiofiles.open(path, "rb") as f:
                while True:
                    try:
                        idx = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        return
                    await f.seek(idx * CHUNK_SIZE)
                    data = await f.read(CHUNK_SIZE)
                    if is_big:
                        request = SaveBigFilePartRequest(file_id, idx, parts, data)
                    else:
                        request = SaveFilePartRequest(file_id, idx, data)
                    ok = await flood_retry(lambda: self.client(request))
                    if not ok:
                        raise RuntimeError("upload part rejected")

        await asyncio.gather(*(worker() for _ in range(workers)))
        if is_big:
            return types.InputFileBig(id=file_id, parts=parts, name=name)
        return types.InputFile(id=file_id, parts=parts, name=name, md5_checksum="")
