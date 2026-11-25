# -*- coding: utf-8 -*-
"""다른 텔레그램 채널의 영상(메시지)을 내 채널로 복사 - 한 번만 (새 글을 따라 옮기지는 않는다).

텔레그램 안에서 전달(forward)하므로 받았다가 다시 올리지 않는다 - 크기와 상관없이 빠르고, 인코딩·나누기도 없다.
- 출처 숨기기(drop_author): "Forwarded from …" 없이 내가 올린 것처럼
- 캡션 빼기(drop_media_captions)
- 원본 채널이 '저장·전달 제한(보호된 콘텐츠)'을 켜 두었으면 텔레그램이 막는다 - 받아서 다시 올리는 우회는 하지 않는다
- 시작할 때 원본의 마지막 메시지까지로 범위를 정한다 (복사하는 동안 새로 올라온 글은 넣지 않음)
- 어디까지 옮겼는지(last_id)를 data/tgup/chcopy.json에 남겨 재시작해도 이어서 (같은 것을 두 번 옮기지 않게)
- 요청 제한(FLOOD_WAIT)에 걸리면 그 시간만큼 쉬고 이어서
작업은 한 번에 하나씩 차례로.
"""
import asyncio
import json
import logging
import os
import re
import time
import uuid

from . import compat, tgaccount

log = logging.getLogger("tgup")
BATCH = 50            # 한 번에 전달할 메시지 수 (텔레그램 최대 100)
GAP_SEC = 3           # 묶음 사이 쉬는 시간
FLOOD_MAX = 6 * 3600  # 이보다 길게 기다리라고 하면 멈춤 (나중에 [다시 시작])
KINDS = {"video": "영상만", "media": "사진·영상·파일", "all": "모든 글"}
KEEP_JOBS = 50
FILES_PAGE = 300      # 파일 고르기 목록 한 쪽
PICK_MAX = 5000       # 한 작업에 고를 수 있는 수
ACTIVE = ("waiting", "running", "flood")


def _path():
    return os.path.join(compat.DATA_DIR, "chcopy.json")


def load_jobs():
    try:
        with open(_path(), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    jobs = data.get("jobs") if isinstance(data, dict) else None
    return [j for j in jobs or [] if isinstance(j, dict) and j.get("id")]


def save_jobs(jobs):
    os.makedirs(compat.DATA_DIR, exist_ok=True)
    with open(_path() + ".tmp", "w", encoding="utf-8") as f:
        json.dump({"jobs": jobs[:KEEP_JOBS]}, f, ensure_ascii=False)
    os.replace(_path() + ".tmp", _path())


def parse_source(text):
    """원본 채널 -> ("id", 채널 id) / ("name", 사용자 이름). 링크의 메시지 번호는 무시"""
    s = str(text or "").strip()
    if not s:
        raise ValueError("원본 채널을 넣어 주세요 (@이름, t.me 링크, 또는 채널 번호).")
    m = re.match(r"^(?:https?://)?(?:www\.)?(?:t|telegram)\.me/c/(\d+)", s, re.I)   # 비공개 채널 메시지 링크
    if m:
        return "id", int(m.group(1))
    m = re.match(r"^(?:https?://)?(?:www\.)?(?:t|telegram)\.me/(?:s/)?([A-Za-z][A-Za-z0-9_]{3,31})(?:[/?#].*)?$", s, re.I)
    if m:
        return "name", m.group(1)
    if re.match(r"^(?:https?://)?(?:www\.)?(?:t|telegram)\.me/(?:\+|joinchat/)", s, re.I):
        raise ValueError("초대 링크로는 찾을 수 없습니다 - 그 계정으로 채널에 먼저 들어간 뒤 채널 이름이나 목록에서 골라 주세요.")
    m = re.match(r"^-?(?:100)?(\d{5,})$", s)
    if m and (s.startswith("-100") or not s.startswith("-")):
        return "id", int(s[4:] if s.startswith("-100") else s)
    m = re.match(r"^@?([A-Za-z][A-Za-z0-9_]{3,31})$", s)
    if m:
        return "name", m.group(1)
    raise ValueError("원본 채널 형식을 알 수 없습니다 (@이름, https://t.me/이름, 또는 -100으로 시작하는 채널 번호).")


def matches(msg, kind):
    """이 메시지를 옮기나"""
    if getattr(msg, "action", None) is not None:   # 입장·고정 같은 알림 메시지
        return False
    if kind == "all":
        return True
    if kind == "media":
        return bool(getattr(msg, "photo", None) or getattr(msg, "document", None))
    return bool(getattr(msg, "video", None) or tgaccount._doc_name(msg))


def public(job):
    out = {k: v for k, v in job.items() if not k.startswith("_") and k != "ids"}
    if job.get("range") == "pick":
        n = len(job.get("ids") or [])
        out["count"] = n
        out["percent"] = 100 if job.get("status") == "done" else (min(99, int(int(job.get("done_n") or 0) * 100 / n)) if n else 0)
        out["kind_label"] = KINDS.get(job.get("kind"), "")
        return out
    span = max(0, int(job.get("to_id") or 0) - int(job.get("from_id") or 0))
    done = max(0, int(job.get("last_id") or 0) - int(job.get("from_id") or 0))
    out["percent"] = 100 if job.get("status") == "done" else (min(99, int(done * 100 / span)) if span else 0)
    out["kind_label"] = KINDS.get(job.get("kind"), "")
    return out


def item_name(msg):
    """목록에 보일 이름: 파일 이름 > 캡션 첫 줄 > 종류 #번호"""
    doc = getattr(msg, "document", None)
    name = next((getattr(a, "file_name", "") for a in getattr(doc, "attributes", None) or [] if getattr(a, "file_name", "")), "") if doc else ""
    if name:
        return name
    cap = str(getattr(msg, "message", "") or "").strip().split("\n", 1)[0][:120]
    if cap:
        return cap
    kind = "영상" if getattr(msg, "video", None) else "사진" if getattr(msg, "photo", None) else "파일" if doc else "글"
    return f"{kind} #{msg.id}"


def _error_text(e):
    name = type(e).__name__
    if isinstance(e, tgaccount.TgError):
        return str(e)
    if name == "ChatForwardsRestrictedError":
        return "원본 채널이 저장·전달을 막아 두었습니다 (보호된 콘텐츠) - 복사할 수 없습니다."
    if name in ("ChatWriteForbiddenError", "ChatAdminRequiredError", "ChatSendMediaForbiddenError"):
        return "대상 채널에 글을 올릴 권한이 없습니다 (관리자 권한을 확인해 주세요)."
    if name in ("ChannelPrivateError", "ChannelInvalidError"):
        return "원본 채널을 볼 수 없습니다 - 이 계정으로 그 채널에 들어가 있는지 확인해 주세요."
    if name in ("UsernameNotOccupiedError", "UsernameInvalidError"):
        return "그런 이름의 채널이 없습니다."
    return f"{name}: {e}" if str(e) else name


class Copier:
    def __init__(self, tg_for):
        self.tg_for = tg_for            # 계정 id -> TelegramAccount
        self.jobs = load_jobs()
        for j in self.jobs:            # 재시작: 하던 것은 이어서
            if j.get("status") in ("running", "flood"):
                j["status"] = "waiting"
        self._wake = asyncio.Event()
        self._task = None               # 지금 도는 작업의 태스크
        self._cur = None

    def _save(self):
        save_jobs(self.jobs)

    def find(self, job_id):
        j = next((x for x in self.jobs if x["id"] == job_id), None)
        if j is None:
            raise ValueError("없는 복사 작업입니다.")
        return j

    async def _source(self, acc, client, src):
        how, val = parse_source(src)
        if how == "id":
            try:
                return await client.get_entity(await acc.peer(val))
            except tgaccount.ChannelLost:
                raise ValueError("이 계정의 대화 목록에 그 채널이 없습니다 - 이 계정으로 채널에 먼저 들어가 주세요.") from None
        return await client.get_entity(val)

    async def preview(self, account, src):
        """원본 채널 확인: {id, title, username, protected, messages, videos, files}"""
        from telethon.tl.types import InputMessagesFilterDocument, InputMessagesFilterPhotoVideo, InputMessagesFilterVideo
        acc = self.tg_for(account)
        client = await acc.authorized_client()
        try:
            ent = await self._source(acc, client, src)
        except ValueError:
            raise
        except Exception as e:  # noqa: BLE001
            raise ValueError(_error_text(e)) from None
        if type(ent).__name__ != "Channel":
            raise ValueError("채널·그룹이 아닙니다.")

        async def total(flt=None):
            try:
                return int((await client.get_messages(ent, limit=0, filter=flt)).total or 0)
            except Exception:  # noqa: BLE001
                return None
        return {"id": int(ent.id), "title": str(getattr(ent, "title", "") or ""), "username": str(getattr(ent, "username", "") or ""),
                "protected": bool(getattr(ent, "noforwards", False)), "messages": await total(),
                "videos": await total(InputMessagesFilterVideo), "photos_videos": await total(InputMessagesFilterPhotoVideo),
                "files": await total(InputMessagesFilterDocument)}

    async def files(self, account, src, kind="video", offset_id=0, limit=FILES_PAGE):
        """원본 채널의 고를 수 있는 항목 (새 것부터) -> {"items": [{id, name, size, date, album}], "next": 다음 offset_id 또는 0}"""
        acc = self.tg_for(account)
        client = await acc.authorized_client()
        try:
            ent = await self._source(acc, client, src)
        except ValueError:
            raise
        except Exception as e:  # noqa: BLE001
            raise ValueError(_error_text(e)) from None
        kind = kind if kind in KINDS else "video"
        items, last, scanned = [], 0, 0
        async for msg in client.iter_messages(ent, offset_id=int(offset_id or 0)):
            last, scanned = int(msg.id), scanned + 1
            if matches(msg, kind):
                doc = getattr(msg, "document", None)
                date = getattr(msg, "date", None)
                items.append({"id": int(msg.id), "name": item_name(msg), "size": int(getattr(doc, "size", 0) or 0) if doc else 0,
                              "date": int(date.timestamp()) if date else 0, "album": int(getattr(msg, "grouped_id", 0) or 0)})
                if len(items) >= limit:
                    break
            if scanned >= limit * 20:   # 고를 것이 드문 채널: 너무 오래 훑지 않게 (다음 쪽에서 이어서)
                break
        more = bool(last) and (len(items) >= limit or scanned >= limit * 20) and last > 1
        return {"items": items, "next": last if more else 0}

    def add(self, body):
        """복사 작업 더하기 -> job"""
        account = str(body.get("account") or tgaccount.ACCOUNT_ID)
        if account not in {a["id"] for a in tgaccount.accounts()}:
            raise ValueError("없는 텔레그램 계정입니다.")
        src = str(body.get("src") or "").strip()
        parse_source(src)
        try:
            dst = int(str(body.get("dst") or "").strip())
        except ValueError:
            raise ValueError("올릴 채널을 골라 주세요.") from None
        kind = body.get("kind") if body.get("kind") in KINDS else "video"
        rng = body.get("range") if body.get("range") in ("all", "recent", "ids", "pick") else "all"
        ids = []
        if rng == "pick":
            try:
                ids = sorted({int(x) for x in body.get("ids") or [] if int(x) > 0})
            except (TypeError, ValueError):
                raise ValueError("고른 파일 목록이 잘못됐습니다.") from None
            if not ids:
                raise ValueError("옮길 파일을 골라 주세요.")
            if len(ids) > PICK_MAX:
                raise ValueError(f"한 번에 {PICK_MAX}개까지 고를 수 있습니다.")

        def num(k):
            try:
                return max(0, int(body.get(k) or 0))
            except (TypeError, ValueError):
                raise ValueError("숫자를 넣어 주세요.") from None
        limit, from_id, to_id = num("limit"), num("from_id"), num("to_id")
        if rng == "recent" and not limit:
            raise ValueError("최근 몇 개를 옮길지 넣어 주세요.")
        if rng == "ids" and to_id and from_id > to_id:
            raise ValueError("시작 번호가 끝 번호보다 큽니다.")
        job = {"id": uuid.uuid4().hex[:10], "account": account, "src": src, "src_id": int(body.get("src_id") or 0),
               "src_title": str(body.get("src_title") or src)[:120], "dst": dst, "dst_title": str(body.get("dst_title") or dst)[:120],
               "kind": kind, "range": rng, "limit": limit if rng == "recent" else 0,
               "from_id": from_id if rng == "ids" else 0, "to_id": to_id if rng == "ids" else 0,
               "ids": ids, "done_n": 0, "first_name": str(body.get("first_name") or "")[:120], "last_name": str(body.get("last_name") or "")[:120],
               "drop_author": bool(body.get("drop_author", True)), "drop_captions": bool(body.get("drop_captions")),
               "status": "waiting", "last_id": 0, "copied": 0, "error": "", "created": int(time.time()),
               "started": 0, "finished": 0, "flood_until": 0, "prepared": False}
        self.jobs.insert(0, job)
        self._save()
        self._wake.set()
        return job

    def cancel(self, job_id):
        j = self.find(job_id)
        if j["status"] in ACTIVE:
            j["status"], j["finished"] = "cancelled", int(time.time())
            self._save()
            if self._cur is j and self._task:
                self._task.cancel()
        return j

    def retry(self, job_id):
        j = self.find(job_id)
        if j["status"] in ("error", "cancelled"):
            j["status"], j["error"] = "waiting", ""
            self._save()
            self._wake.set()
        return j

    def remove(self, job_id):
        j = self.find(job_id)
        if j["status"] in ACTIVE:
            raise ValueError("진행 중인 작업은 먼저 멈춰 주세요.")
        self.jobs.remove(j)
        self._save()

    def status(self):
        return [public(j) for j in self.jobs]

    async def loop(self):
        while True:
            job = next((j for j in reversed(self.jobs) if j.get("status") == "waiting"), None)   # 먼저 넣은 것부터
            if job is None:
                self._wake.clear()
                await self._wake.wait()
                continue
            self._cur = job
            self._task = asyncio.ensure_future(self.run(job))
            try:
                await self._task
            except asyncio.CancelledError:
                if job.get("status") != "cancelled":   # 끝내는 중
                    raise
            except Exception as e:  # noqa: BLE001
                job["status"], job["error"], job["finished"] = "error", _error_text(e)[:300], int(time.time())
                log.warning("채널 복사 %s 실패: %s", job.get("src_title"), job["error"])
            finally:
                self._cur = self._task = None
                self._save()

    async def _prepare(self, client, src, job):
        """범위 정하기: 끝은 지금 원본의 마지막 메시지, 최근 N개면 그 N번째의 번호부터"""
        if not job.get("to_id"):
            last = await client.get_messages(src, limit=1)
            job["to_id"] = int(last[0].id) if last else 0
        if job["range"] == "recent":
            n, first = 0, 0
            async for msg in client.iter_messages(src, max_id=job["to_id"] + 1):
                if matches(msg, job["kind"]):
                    n, first = n + 1, int(msg.id)
                    if n >= job["limit"]:
                        break
            job["from_id"] = first
            job["total"] = n
        job["last_id"] = max(int(job.get("last_id") or 0), max(0, int(job.get("from_id") or 0) - 1))
        job["prepared"] = True
        self._save()

    async def _forward(self, client, job, src, dst, ids):
        while True:
            try:
                return await client.forward_messages(dst, ids, from_peer=src, drop_author=job["drop_author"] or None,
                                                     drop_media_captions=job["drop_captions"] or None)
            except Exception as e:  # noqa: BLE001
                if type(e).__name__ == "TypeNotFoundError":   # 옮겨졌지만 답을 Telethon이 못 읽음 - 다시 보내면 두 번 올라감
                    log.warning("채널 복사 %s: 텔레그램 답을 읽지 못했지만 옮겨진 것으로 봅니다: %s", job.get("src_title"), str(e)[:160])
                    return ids
                if type(e).__name__ not in ("FloodWaitError", "FloodPremiumWaitError", "SlowModeWaitError"):
                    raise
                sec = getattr(e, "seconds", None)
                wait = (60 if sec is None else int(sec)) + 1
                if wait > FLOOD_MAX:
                    raise RuntimeError(f"텔레그램이 {wait // 60}분 기다리라고 합니다 (FLOOD_WAIT) - 나중에 [다시 시작]을 눌러 주세요.") from None
                job["status"], job["flood_until"] = "flood", int(time.time()) + wait
                self._save()
                log.info("채널 복사 %s: FLOOD_WAIT %d초 쉼", job.get("src_title"), wait)
                await asyncio.sleep(wait)
                job["status"], job["flood_until"] = "running", 0

    async def run(self, job):
        acc = self.tg_for(job["account"])
        client = await acc.authorized_client()
        try:
            src = await self._source(acc, client, job["src"])
        except ValueError:
            raise
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(_error_text(e)) from None
        if getattr(src, "noforwards", False):
            raise RuntimeError("원본 채널이 저장·전달을 막아 두었습니다 (보호된 콘텐츠) - 복사할 수 없습니다.")
        dst = await acc.peer(job["dst"])
        job["src_id"], job["src_title"] = int(src.id), str(getattr(src, "title", "") or job["src_title"])
        job["status"], job["started"] = "running", job.get("started") or int(time.time())
        if job["range"] == "pick":
            await self._run_pick(client, job, src, dst)
            return
        if not job.get("prepared"):
            await self._prepare(client, src, job)
        batch, group, scanned = [], None, job["last_id"]

        async def flush():
            nonlocal batch
            if batch:
                await self._forward(client, job, src, dst, batch)
                job["copied"] += len(batch)
                batch = []
                await asyncio.sleep(GAP_SEC)
            job["last_id"] = scanned
            self._save()

        async for msg in client.iter_messages(src, reverse=True, min_id=job["last_id"], max_id=job["to_id"] + 1):
            gid = getattr(msg, "grouped_id", None)
            if len(batch) >= BATCH and not (gid and gid == group):   # 앨범(묶음)은 한 번에
                await flush()
            if matches(msg, job["kind"]):
                batch.append(int(msg.id))
                group = gid
            scanned = int(msg.id)
        scanned = job["to_id"]
        await flush()
        job["status"], job["finished"] = "done", int(time.time())
        log.info("채널 복사 %s -> %s: %d개 옮김", job.get("src_title"), job.get("dst_title"), job["copied"])

    async def _run_pick(self, client, job, src, dst):
        """고른 파일만 (오래된 것부터). 지워진 메시지는 건너뜀"""
        ids = job.get("ids") or []
        while job["done_n"] < len(ids):
            chunk = ids[job["done_n"]:job["done_n"] + BATCH]
            msgs = await client.get_messages(src, ids=chunk)
            alive = [int(m.id) for m in msgs or [] if m is not None and getattr(m, "action", None) is None]
            if alive:
                await self._forward(client, job, src, dst, alive)
                job["copied"] += len(alive)
            job["skipped"] = int(job.get("skipped") or 0) + len(chunk) - len(alive)
            job["done_n"] += len(chunk)
            self._save()
            if alive and job["done_n"] < len(ids):
                await asyncio.sleep(GAP_SEC)
        job["status"], job["finished"] = "done", int(time.time())
        log.info("채널 복사 %s -> %s: 고른 %d개 중 %d개 옮김", job.get("src_title"), job.get("dst_title"), len(ids), job["copied"])
