"""Telegram channel synchronizer (GitHub Actions runner).

Copies new posts from source channels to target channels as fresh messages,
keeping their original order. Progress checkpoints live behind a private HTTP
endpoint, so the runner itself is stateless.

PUBLIC REPO: this script must never print channel IDs, message text, captions,
usernames or file names. All output goes through ``report()`` and is anonymous.
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import shutil
import sys
import tempfile
import uuid
import warnings
from dataclasses import dataclass, field

import httpx
import uvloop
from telethon import TelegramClient, utils
from telethon.sessions import StringSession
from telethon.tl import types
from telethon.tl.functions.messages import SendMediaRequest, SendMultiMediaRequest, UploadMediaRequest

from fast_telethon import FastTelethon, flood_retry, pick_connections

# Third-party loggers/warnings may include identifiers — silence them all.
logging.disable(logging.CRITICAL)
warnings.simplefilter("ignore")

QUEUE_SIZE = 2
INITIAL_POSTS = 5
HTTP_TIMEOUT = 30.0


def report(line: str) -> None:
    print(line, flush=True)


class ConfigError(Exception):
    pass


# --------------------------------------------------------------------------- config


@dataclass(frozen=True)
class Config:
    api_id: int
    api_hash: str
    session: str
    pairs: list[tuple[int, int]]
    worker_url: str
    secret: str


def load_config() -> Config:
    missing = [k for k in ("TG_API_ID", "TG_API_HASH", "TG_SESSION", "SYNC_MAP", "WORKER_URL", "INTERNAL_API_SECRET") if not os.environ.get(k)]
    if missing:
        raise ConfigError(f"missing env: {', '.join(missing)}")
    try:
        raw = json.loads(os.environ["SYNC_MAP"])
        pairs = [(int(item["source"]), int(item["target"])) for item in raw]
    except (ValueError, TypeError, KeyError) as e:
        raise ConfigError("SYNC_MAP must be a JSON list of {source, target}") from e
    if not pairs:
        raise ConfigError("SYNC_MAP is empty")
    try:
        api_id = int(os.environ["TG_API_ID"])
    except ValueError as e:
        raise ConfigError("TG_API_ID must be an integer") from e
    return Config(
        api_id=api_id,
        api_hash=os.environ["TG_API_HASH"],
        session=os.environ["TG_SESSION"],
        pairs=pairs,
        worker_url=os.environ["WORKER_URL"].rstrip("/"),
        secret=os.environ["INTERNAL_API_SECRET"],
    )


# --------------------------------------------------------------------------- state API


class StateApi:
    def __init__(self, http: httpx.AsyncClient, base: str, secret: str) -> None:
        self.http = http
        self.url = f"{base}/internal/sync/state"
        self.headers = {"Authorization": f"Bearer {secret}"}

    async def load(self) -> dict[str, int]:
        res = await self.http.get(self.url, headers=self.headers)
        res.raise_for_status()
        data = res.json()
        ids = data.get("last_message_id") if isinstance(data, dict) else None
        if not isinstance(ids, dict):
            return {}
        return {str(k): int(v) for k, v in ids.items() if isinstance(v, int)}

    async def save(self, source: int, last_id: int) -> None:
        for attempt in range(3):
            try:
                res = await self.http.post(self.url, headers=self.headers, json={"last_message_id": {str(source): last_id}})
                res.raise_for_status()
                return
            except httpx.HTTPError:
                if attempt == 2:
                    raise
                await asyncio.sleep(2 * (attempt + 1))


# --------------------------------------------------------------------------- units


@dataclass
class Unit:
    """One post (single message) or one album; ``checkpoint`` also covers skipped messages before it."""

    messages: list[types.Message]
    checkpoint: int
    files: list[str | None] = field(default_factory=list)
    thumbs: list[str | None] = field(default_factory=list)


def is_supported(msg: types.Message) -> bool:
    if isinstance(msg, types.MessageService):
        return False
    media = msg.media
    if media is None or isinstance(media, types.MessageMediaWebPage):
        return bool(msg.message)
    if isinstance(media, types.MessageMediaPhoto):
        return isinstance(media.photo, types.Photo) and not media.ttl_seconds
    if isinstance(media, types.MessageMediaDocument):
        return isinstance(media.document, types.Document) and not media.ttl_seconds
    return False  # polls, geo, contacts, dice, stories, ...


def group_units(messages: list[types.Message]) -> tuple[list[Unit], int]:
    """Group ascending messages into posts/albums. Returns (units, skipped_count)."""
    units: list[Unit] = []
    skipped = 0
    pending_skip = 0
    for msg in messages:
        if not is_supported(msg):
            skipped += 1
            pending_skip = msg.id
            continue
        last = units[-1] if units else None
        if (
            msg.grouped_id
            and last is not None
            and last.messages[-1].grouped_id == msg.grouped_id
            and len(last.messages) < 10
            and pending_skip < last.checkpoint
        ):
            last.messages.append(msg)
            last.checkpoint = msg.id
        else:
            units.append(Unit(messages=[msg], checkpoint=msg.id))
    if pending_skip and (not units or pending_skip > units[-1].checkpoint):
        units.append(Unit(messages=[], checkpoint=pending_skip))  # checkpoint-only
    return units, skipped


async def fetch_new(client: TelegramClient, source: types.TypeInputPeer, last_id: int | None) -> list[types.Message]:
    if last_id is not None:
        return [m async for m in client.iter_messages(source, min_id=last_id, reverse=True)]
    # First run: start with the latest INITIAL_POSTS posts (albums count as one).
    recent = list(reversed(await client.get_messages(source, limit=INITIAL_POSTS * 10)))
    units, _ = group_units(recent)
    posts = [u for u in units if u.messages][-INITIAL_POSTS:]
    if not posts:
        return []
    start = posts[0].messages[0].id
    return [m for m in recent if m.id >= start]


# --------------------------------------------------------------------------- media


def document_size(doc: types.Document) -> int:
    return int(doc.size or 0)


def streaming_attributes(attrs: list[types.TypeDocumentAttribute]) -> list[types.TypeDocumentAttribute]:
    out: list[types.TypeDocumentAttribute] = []
    for attr in attrs:
        if isinstance(attr, types.DocumentAttributeVideo):
            attr = copy.copy(attr)  # keeps duration, w, h, round_message, ...
            attr.supports_streaming = True
        out.append(attr)
    return out


def is_plain_file(attrs: list[types.TypeDocumentAttribute]) -> bool:
    special = (
        types.DocumentAttributeVideo,
        types.DocumentAttributeAudio,
        types.DocumentAttributeAnimated,
        types.DocumentAttributeSticker,
    )
    return not any(isinstance(a, special) for a in attrs)


class Downloader:
    def __init__(self, client: TelegramClient, fast: FastTelethon, workdir: str) -> None:
        self.client = client
        self.fast = fast
        self.workdir = workdir

    def _path(self) -> str:
        return os.path.join(self.workdir, uuid.uuid4().hex)

    async def prepare(self, unit: Unit) -> None:
        for msg in unit.messages:
            media = msg.media
            if isinstance(media, types.MessageMediaPhoto):
                path = await flood_retry(lambda: self.client.download_media(msg, file=self._path()))
                unit.files.append(path)
                unit.thumbs.append(None)
            elif isinstance(media, types.MessageMediaDocument):
                doc = media.document
                unit.files.append(await self.fast.download(doc, self._path(), document_size(doc)))
                thumb = None
                if doc.thumbs and not is_plain_file(doc.attributes):
                    thumb = await flood_retry(lambda: self.client.download_media(msg, file=self._path(), thumb=-1))
                unit.thumbs.append(thumb)
            else:
                unit.files.append(None)
                unit.thumbs.append(None)


def cleanup(unit: Unit) -> None:
    for path in (*unit.files, *unit.thumbs):
        if path:
            try:
                os.remove(path)
            except OSError:
                pass


# --------------------------------------------------------------------------- sending


class Sender:
    def __init__(self, client: TelegramClient, fast: FastTelethon) -> None:
        self.client = client
        self.fast = fast

    async def _input_media(self, msg: types.Message, path: str, thumb: str | None) -> types.TypeInputMedia:
        media = msg.media
        is_photo = isinstance(media, types.MessageMediaPhoto)
        uploaded = await self.fast.upload(path, name="photo.jpg" if is_photo else "file")
        if is_photo:
            return types.InputMediaUploadedPhoto(file=uploaded, spoiler=bool(media.spoiler))
        doc = media.document
        thumb_file = await flood_retry(lambda: self.client.upload_file(thumb)) if thumb else None
        attrs = list(doc.attributes)
        return types.InputMediaUploadedDocument(
            file=uploaded,
            mime_type=doc.mime_type or "application/octet-stream",
            attributes=streaming_attributes(attrs),
            thumb=thumb_file,
            force_file=is_plain_file(attrs) or None,
            spoiler=bool(media.spoiler),
            nosound_video=bool(getattr(media, "nosound", False)) or None,
        )

    async def send(self, target: types.TypeInputPeer, unit: Unit) -> None:
        msgs = unit.messages
        if len(msgs) == 1 and unit.files[0] is None:
            msg = msgs[0]
            await flood_retry(
                lambda: self.client.send_message(
                    target,
                    msg.message,
                    formatting_entities=msg.entities,
                    link_preview=isinstance(msg.media, types.MessageMediaWebPage),
                )
            )
            return

        if len(msgs) == 1:
            msg = msgs[0]
            media = await self._input_media(msg, unit.files[0], unit.thumbs[0])
            await flood_retry(
                lambda: self.client(SendMediaRequest(peer=target, media=media, message=msg.message or "", entities=msg.entities))
            )
            return

        # Album: upload each item, convert to a reusable InputMedia, then send in one request.
        items: list[types.InputSingleMedia] = []
        for msg, path, thumb in zip(msgs, unit.files, unit.thumbs):
            uploaded = await self._input_media(msg, path, thumb)
            stored = await flood_retry(lambda: self.client(UploadMediaRequest(peer=target, media=uploaded)))
            input_media = utils.get_input_media(stored)
            if isinstance(input_media, types.InputMediaDocument) and isinstance(uploaded, types.InputMediaUploadedDocument):
                input_media.spoiler = uploaded.spoiler
            items.append(
                types.InputSingleMedia(media=input_media, message=msg.message or "", entities=msg.entities)
            )
        await flood_retry(lambda: self.client(SendMultiMediaRequest(peer=target, multi_media=items)))


# --------------------------------------------------------------------------- pipeline


@dataclass
class ChannelResult:
    synced: int = 0
    skipped: int = 0
    error: str | None = None


async def sync_channel(
    client: TelegramClient,
    fast: FastTelethon,
    state: StateApi,
    workdir: str,
    source_id: int,
    target_id: int,
    last_id: int | None,
) -> ChannelResult:
    result = ChannelResult()
    source = await client.get_input_entity(source_id)
    target = await client.get_input_entity(target_id)
    messages = await fetch_new(client, source, last_id)
    units, result.skipped = group_units(messages)
    if not units:
        return result

    downloader = Downloader(client, fast, workdir)
    sender = Sender(client, fast)
    queue: asyncio.Queue[Unit | None] = asyncio.Queue(maxsize=QUEUE_SIZE)

    async def producer() -> None:
        for unit in units:
            try:
                await downloader.prepare(unit)
            except BaseException:
                cleanup(unit)
                raise
            await queue.put(unit)
        await queue.put(None)

    async def consumer() -> None:
        while (unit := await queue.get()) is not None:
            try:
                if unit.messages:
                    await sender.send(target, unit)
                    result.synced += len(unit.messages)
            finally:
                cleanup(unit)  # temp files leave the disk right after sending
            await state.save(source_id, unit.checkpoint)

    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(producer())
            tg.create_task(consumer())
    except* Exception as group:
        result.error = type(group.exceptions[0]).__name__
    finally:
        while not queue.empty():
            leftover = queue.get_nowait()
            if leftover is not None:
                cleanup(leftover)
    return result


async def run(cfg: Config) -> int:
    workdir = tempfile.mkdtemp(prefix="sync-")
    failed = 0
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as http:
            state = StateApi(http, cfg.worker_url, cfg.secret)
            checkpoints = await state.load()

            client = TelegramClient(StringSession(cfg.session), cfg.api_id, cfg.api_hash)
            await client.connect()
            try:
                if not await client.is_user_authorized():
                    raise ConfigError("TG_SESSION is not authorized")
                # Fill the entity cache so bare -100... IDs resolve.
                await client.get_dialogs()
                fast = FastTelethon(client)

                for n, (source_id, target_id) in enumerate(cfg.pairs, start=1):
                    try:
                        res = await sync_channel(
                            client, fast, state, workdir, source_id, target_id, checkpoints.get(str(source_id))
                        )
                    except Exception as e:  # noqa: BLE001 — report class name only
                        res = ChannelResult(error=type(e).__name__)
                    line = f"Channel #{n}: synced {res.synced} items"
                    if res.skipped:
                        line += f", skipped {res.skipped}"
                    if res.error:
                        failed += 1
                        line += f" — stopped ({res.error})"
                    report(line)
            finally:
                await client.disconnect()
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return 1 if failed else 0


def main() -> int:
    try:
        cfg = load_config()
    except ConfigError as e:
        report(f"Config error: {e}")
        return 2
    report(f"Sync started: {len(cfg.pairs)} channel(s), up to {pick_connections(1 << 40)} parallel parts")
    try:
        return uvloop.run(run(cfg))
    except BaseException as e:  # noqa: BLE001 — never print tracebacks (they may contain identifiers)
        if isinstance(e, ConfigError):
            report(f"Config error: {e}")
        else:
            report(f"Sync failed: {type(e).__name__}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
