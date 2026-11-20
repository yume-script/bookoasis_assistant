# -*- coding: utf-8 -*-
"""자동 올리기에 쓰는 텔레그램 계정들 (telethon 사용자 로그인 - 봇이 아니라 내 계정이라 2GB/4GB 파일을 올린다).

계정은 여러 개 넣을 수 있다 (규칙마다 올릴 계정을 고른다 - 계정마다 따로 동시에 올리고, 요청 제한은 그 계정만 기다린다).
API ID / API Hash는 계정들이 같이 쓴다 (my.telegram.org의 앱 하나로 여러 계정이 로그인할 수 있다).
  계정 목록: data/tgup/settings.json의 "accounts" [{id, name, phone}] - 첫 계정 id는 "tg" (예전 하나뿐이던 계정 그대로)
  세션 파일: 첫 계정 data/tgup/telegram.session, 그 밖 data/tgup/telegram_<id>.session (계정 열쇠 - 권한 600)

YMPlayer의 텔레그램 소스(TelegramSource)에서 자동 올리기가 쓰는 부분만 옮겼다: 로그인(전화번호 → 인증 코드 → 2단계 비밀번호),
채널 목록, 채널 주소(peer), 로그인된 클라이언트.
  API ID / API Hash: my.telegram.org > API development tools 에서 발급 (화면에서 넣으면 data/tgup/settings.json, 또는 .env의
  TGUP_API_ID / TGUP_API_HASH)
  세션 파일: data/tgup/telegram.session (계정 열쇠 - 권한 600)
"""
import asyncio
import json
import logging
import os
import re
import time

from . import compat, throttle

log = logging.getLogger("tgup.telegram")
KEEP_PLEX_META = False   # plex_to_tg._save_meta: 작품 정보는 YMPlayer 텔레그램 색인에만 쓰여 여기선 남기지 않는다
ACCOUNT_ID = "tg"        # 첫 계정의 id (규칙의 tg 칸 - 예전에 계정이 하나뿐일 때의 값 그대로)
MAX_ACCOUNTS = 10
_ID_RE = re.compile(r"^tg[0-9]{0,3}$")


class TgError(Exception):
    pass


class ChannelLost(TgError):
    """그 계정이 채널을 못 찾음 (나갔거나 지워짐) - 계정 전체 문제가 아니라 그 채널만 (다른 계정에 넘긴다)"""


def plex_meta_put(*_args, **_kwargs):   # plex_to_tg가 부른다 (KEEP_PLEX_META가 False라 실제로는 안 불림)
    return None


def fast_crypto():
    try:
        import cryptg  # noqa: F401
        return True
    except ImportError:
        return False


def available():
    try:
        import telethon  # noqa: F401
        return True
    except ImportError:
        return False


def api_conf():
    tg = compat.load().get("telegram") or {}
    return {"api_id": str(compat.config.env("TGUP_API_ID") or tg.get("api_id") or "").strip(),
            "api_hash": str(compat.config.env("TGUP_API_HASH") or tg.get("api_hash") or "").strip(),
            "phone": str(tg.get("phone") or "").strip(),
            "from_env": bool(compat.config.env("TGUP_API_ID") and compat.config.env("TGUP_API_HASH"))}


def accounts():
    """[{id, name, phone}] - 비어 있으면 첫 계정 하나 (예전 설정)"""
    data = compat.load()
    out, seen = [], set()
    for a in data.get("accounts") or []:
        if isinstance(a, dict) and _ID_RE.match(str(a.get("id") or "")) and a["id"] not in seen:
            seen.add(a["id"])
            out.append({"id": a["id"], "name": str(a.get("name") or "")[:40], "phone": str(a.get("phone") or ""),
                        "proxy": str(a.get("proxy") or "")})
    if ACCOUNT_ID not in seen:
        out.insert(0, {"id": ACCOUNT_ID, "name": "", "phone": str((data.get("telegram") or {}).get("phone") or ""), "proxy": ""})
    return out


def save_accounts(items):
    data = compat.load()
    data["accounts"] = [{"id": a["id"], "name": a.get("name", ""), "phone": a.get("phone", ""),
                         **({"proxy": a["proxy"]} if a.get("proxy") else {})} for a in items]
    compat.save(data)


# ---------------------------------------------------------------------------
# 계정별 프록시 (같은 채널로 두 계정이 같이 올릴 때 두 번째 계정은 다른 연결 경로로 - plex_to_tg 채널별 동시 올리기 규칙)
#   socks5://[아이디:비밀번호@]호스트:포트 · socks4://호스트:포트 · http://[아이디:비밀번호@]호스트:포트
#   mtproxy://시크릿@호스트:포트 (텔레그램 MTProto 프록시)
# ---------------------------------------------------------------------------
_PROXY_RE = re.compile(r"^(socks5|socks4|http|mtproxy)://(?:([^:@/\s]*)(?::([^@/\s]*))?@)?([A-Za-z0-9.\-\[\]:]+?):(\d{1,5})/?$")


def clean_proxy(url):
    """프록시 주소 확인 -> 정리한 주소 ("" = 프록시 안 씀). 잘못 쓰면 ValueError"""
    url = str(url or "").strip()
    if not url:
        return ""
    m = _PROXY_RE.match(url)
    if not m or not (0 < int(m.group(5)) < 65536):
        raise ValueError("프록시 주소는 socks5://호스트:포트 · socks5://아이디:비밀번호@호스트:포트 · http://호스트:포트 · "
                         "mtproxy://시크릿@호스트:포트 모양으로 넣어 주세요.")
    if m.group(1) == "mtproxy" and not m.group(2):
        raise ValueError("MTProto 프록시는 mtproxy://시크릿@호스트:포트 모양입니다.")
    return url


def proxy_of(acc_id):
    return next((a.get("proxy") or "" for a in accounts() if a["id"] == acc_id), "")


def route_of(acc_id):
    """이 계정이 텔레그램에 닿는 경로: "direct" 또는 프록시 주소 (같은 경로의 계정끼리는 한 채널에 동시에 올리지 않는다)"""
    return proxy_of(acc_id) or "direct"


def proxy_public(url):
    """화면에 보일 프록시 (비밀번호·시크릿은 가림)"""
    m = _PROXY_RE.match(str(url or ""))
    if not m:
        return ""
    who = ("***" if m.group(1) == "mtproxy" else m.group(2) + (":***" if m.group(3) else "")) if m.group(2) else ""
    return f"{m.group(1)}://{who + '@' if who else ''}{m.group(4)}:{m.group(5)}"


def client_proxy_args(url):
    """TelegramClient에 줄 인자 {proxy=..., connection=...} (프록시 없으면 {})"""
    m = _PROXY_RE.match(str(url or ""))
    if not m:
        return {}
    kind, user, pw, host, port = m.group(1), m.group(2), m.group(3), m.group(4).strip("[]"), int(m.group(5))
    if kind == "mtproxy":
        from telethon import connection
        return {"connection": connection.ConnectionTcpMTProxyRandomizedIntermediate, "proxy": (host, port, user)}
    try:
        import python_socks  # noqa: F401 - Telethon이 SOCKS/HTTP 프록시에 쓴다
    except ImportError as e:
        raise TgError("프록시를 쓰려면 python-socks가 필요합니다: pip install -r requirements.txt") from e
    return {"proxy": {"proxy_type": kind, "addr": host, "port": port, "username": user or None, "password": pw or None, "rdns": True}}


def new_account_id():
    used = {a["id"] for a in accounts()}
    n = 2
    while f"tg{n}" in used:
        n += 1
    return f"tg{n}"


class TelegramAccount:
    def __init__(self, acc_id=ACCOUNT_ID):
        self.id = acc_id
        self.client = None
        self._key = None
        self._lock = asyncio.Lock()
        self._code_hash = None
        self.phone = ""

    @property
    def _suffix(self):
        return "" if self.id == ACCOUNT_ID else f"_{self.id}"

    @property
    def session_path(self):
        return os.path.join(compat.DATA_DIR, f"telegram{self._suffix}.session")

    @property
    def peers_path(self):
        return os.path.join(compat.DATA_DIR, f"peers{self._suffix}.json")

    def _saved_phone(self):
        return next((a["phone"] for a in accounts() if a["id"] == self.id), "")

    def _save_phone(self, phone):
        items = accounts()
        for a in items:
            if a["id"] == self.id:
                a["phone"] = phone
        save_accounts(items)
        if self.id == ACCOUNT_ID:   # 예전 설정 자리에도 (되돌려도 그대로)
            data = compat.load()
            data.setdefault("telegram", {})["phone"] = phone
            compat.save(data)

    async def get_client(self):
        conf = api_conf()
        if not conf["api_id"] or not conf["api_hash"]:
            raise TgError("Telegram API ID와 API Hash를 넣고 저장해 주세요 (my.telegram.org에서 발급).")
        if not conf["api_id"].isdigit():
            raise TgError("API ID는 숫자여야 합니다.")
        try:
            from telethon import TelegramClient
        except ImportError as e:
            raise TgError("telethon이 설치되어 있지 않습니다: pip install -r requirements.txt") from e
        async with self._lock:
            proxy = proxy_of(self.id)
            key = (conf["api_id"], conf["api_hash"], proxy)
            if self.client is not None and self._key != key:   # API 값을 바꿨으면 새로 연결
                await self.client.disconnect()
                self.client = None
            if self.client is None:
                os.makedirs(compat.DATA_DIR, exist_ok=True)
                # 텔레그램에 닿지 않을 때 화면이 오래 멈추지 않게 (기본은 5번 x 10초)
                # base_logger: 계정별 로거 - Telethon이 혼자 기다린 업로드 제한(flood wait)을 계정마다 센다 (tgup/throttle.py)
                self.client = TelegramClient(self.session_path, int(conf["api_id"]), conf["api_hash"], receive_updates=False,
                                             connection_retries=2, timeout=10, base_logger=throttle.logger_name(self.id),
                                             **client_proxy_args(proxy))
                self._key = key
            if not self.client.is_connected():
                await self.client.connect()
                try:
                    os.chmod(self.session_path, 0o600)
                except OSError:
                    pass
        return self.client

    async def authorized_client(self):
        client = await self.get_client()
        if not await client.is_user_authorized():
            raise TgError("Telegram 로그인이 필요합니다. 자동 올리기 > 텔레그램 계정에서 로그인해 주세요.")
        return client

    async def close(self):
        if self.client is not None and self.client.is_connected():
            await self.client.disconnect()

    async def status(self):
        conf = api_conf()
        base = {"id": self.id, "authorized": False, "phone": self.phone or self._saved_phone() or (conf["phone"] if self.id == ACCOUNT_ID else ""),
                "api_id": conf["api_id"],
                "has_hash": bool(conf["api_hash"]), "from_env": conf["from_env"], "telethon": available(),
                "fast_crypto": fast_crypto()}
        try:
            client = await self.get_client()
            if not await client.is_user_authorized():
                return base
            me = await client.get_me()
            name = " ".join(x for x in (getattr(me, "first_name", ""), getattr(me, "last_name", "")) if x)
            return {**base, "authorized": True, "name": name or getattr(me, "username", "") or "",
                    "premium": bool(getattr(me, "premium", False))}
        except TgError as e:
            return {**base, "error": str(e)}
        except Exception as e:  # noqa: BLE001 - 연결 실패 등은 화면에 그대로
            return {**base, "error": f"텔레그램에 연결하지 못했습니다: {e}"}

    async def send_code(self, phone=""):
        phone = re.sub(r"[\s-]", "", phone or self.phone or self._saved_phone())
        if not phone:
            raise TgError("전화번호를 넣어 주세요 (국가번호 포함, 예: +821012345678).")
        client = await self.get_client()
        sent = await client.send_code_request(phone)
        self.phone, self._code_hash = phone, sent.phone_code_hash
        self._save_phone(phone)
        return {"code_sent": True, "phone": phone}

    async def sign_in(self, code="", password=""):
        from telethon.errors import (PasswordHashInvalidError, PhoneCodeExpiredError, PhoneCodeInvalidError,
                                     SessionPasswordNeededError)
        client = await self.get_client()
        try:
            if password:
                await client.sign_in(password=password)
            else:
                if not self._code_hash:
                    raise TgError("먼저 [인증 코드 받기]를 눌러 주세요.")
                await client.sign_in(phone=self.phone, code=re.sub(r"\s", "", code), phone_code_hash=self._code_hash)
        except SessionPasswordNeededError:
            return {"password_required": True}
        except PhoneCodeInvalidError:
            raise TgError("인증 코드가 틀렸습니다.")
        except PhoneCodeExpiredError:
            raise TgError("인증 코드가 만료됐습니다. 다시 받아 주세요.")
        except PasswordHashInvalidError:
            raise TgError("2단계 인증 비밀번호가 틀렸습니다.")
        self._code_hash = None
        return await self.status()

    async def logout(self):
        try:
            client = await self.get_client()
            if await client.is_user_authorized():
                await client.log_out()
        finally:
            await self.close()
            self.client = None
            for path in (self.session_path, self.session_path + "-journal", self.peers_path):
                try:
                    os.remove(path)
                except OSError:
                    pass

    def _peers(self):
        try:
            with open(self.peers_path, encoding="utf-8") as f:
                return json.load(f) or {}
        except (OSError, ValueError):
            return {}

    async def list_channels(self):
        """들어가 있는 채널·그룹 [{id, title, username, kind}] (올리려면 그 채널에 글을 쓸 수 있어야 한다)"""
        client = await self.authorized_client()
        items, peers = [], {}
        async for dialog in client.iter_dialogs():
            ent = dialog.entity
            if type(ent).__name__ != "Channel":
                continue
            items.append({"id": int(ent.id), "title": str(getattr(ent, "title", "") or dialog.name or ""),
                          "username": str(getattr(ent, "username", "") or ""),
                          "kind": "channel" if getattr(ent, "broadcast", False) else "group",
                          "can_post": bool(getattr(ent, "creator", False) or getattr(ent, "admin_rights", None)
                                           or not getattr(ent, "broadcast", False))})
            peers[str(int(ent.id))] = str(getattr(ent, "access_hash", 0) or 0)
        os.makedirs(compat.DATA_DIR, exist_ok=True)
        with open(self.peers_path, "w", encoding="utf-8") as f:
            json.dump(peers, f)
        items.sort(key=lambda c: c["title"].lower())
        return items

    async def peer(self, channel):
        from telethon.tl.types import InputPeerChannel
        h = self._peers().get(str(int(channel)))
        if not h or not int(h):
            await self.list_channels()
            h = self._peers().get(str(int(channel)))
        if not h:
            raise ChannelLost(f"채널 {channel}을(를) 대화 목록에서 찾지 못했습니다 (나갔거나 지워졌을 수 있음).")
        return InputPeerChannel(int(channel), int(h))


# ---------------------------------------------------------------------------
# 채널 목록 (중복 막기) - 자동 올리기가 올리기 전에 "이 채널에 이미 있나"를 본다 (작품 이름·파일 이름·시즌·회차).
# YMPlayer는 텔레그램 색인(DB)이 있지만 여기는 없어서, 채널의 영상 메시지(파일 이름·캡션 첫 줄)를 읽어 data/tgup/channel_index/에 둔다.
# 처음에는 최근 INDEX_FIRST개까지, 그 뒤로는 마지막으로 읽은 메시지 다음 것만. 계정이 여럿이어도 채널마다 하나.
# ---------------------------------------------------------------------------
INDEX_TTL = 300          # 이만큼(초) 안에 다시 읽었으면 그대로 쓴다
INDEX_FIRST = 20000      # 처음 읽을 때 최근 메시지 몇 개까지
INDEX_KEEP = 50000
_VIDEO_EXT = {".mp4", ".mkv", ".avi", ".mov", ".m4v", ".wmv", ".ts", ".webm", ".flv", ".mpg", ".mpeg"}
_INDEX = {}              # 채널 -> {"last", "at", "items": {msg: [캡션 첫 줄, 파일 이름]}}
_INDEX_LOCKS = {}
_EP_CACHE = {}           # 채널 -> (항목 수, 마지막 메시지, {(작품 키, 시즌, 회차): 제목})
_NAME_CACHE = {}         # 채널 -> (항목 수, 마지막 메시지, {파일 이름 키: 제목})


def _index_path(channel):
    return os.path.join(compat.DATA_DIR, "channel_index", f"{abs(int(channel))}.json")


def _index(channel):
    channel = abs(int(channel))
    if channel not in _INDEX:
        try:
            with open(_index_path(channel), encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
        data = data if isinstance(data, dict) else {}
        _INDEX[channel] = {"last": int(data.get("last") or 0), "at": 0, "items": dict(data.get("items") or {})}
    return _INDEX[channel]


def _save_index(channel, idx):
    path = _index_path(channel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    items = idx["items"]
    if len(items) > INDEX_KEEP:   # 오래된 메시지부터 버린다
        for k in sorted(items, key=int)[:len(items) - INDEX_KEEP]:
            items.pop(k, None)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump({"last": idx["last"], "items": items}, f, ensure_ascii=False)
    os.replace(path + ".tmp", path)


def _doc_name(msg):
    """메시지의 영상 파일 이름 (영상이 아니면 "")"""
    doc = getattr(msg, "document", None)
    if not doc:
        return ""
    name = next((getattr(a, "file_name", "") for a in getattr(doc, "attributes", None) or [] if getattr(a, "file_name", "")), "")
    mime = str(getattr(doc, "mime_type", "") or "")
    if mime.startswith("video/") or os.path.splitext(name)[1].lower() in _VIDEO_EXT:
        return name or f"{msg.id}.mp4"
    return ""


async def refresh_channel(acc, channel):
    """채널의 새 영상 메시지를 읽어 목록에 더한다 (plex_to_tg가 중복을 보기 전에 부른다)"""
    key = abs(int(channel))
    lock = _INDEX_LOCKS.setdefault(key, asyncio.Lock())
    async with lock:
        idx = _index(key)
        if time.time() - idx["at"] < INDEX_TTL:
            return
        client = await acc.authorized_client()
        peer = await acc.peer(channel)
        last, n = idx["last"], 0
        async for msg in client.iter_messages(peer, min_id=last, limit=None if last else INDEX_FIRST):
            idx["last"] = max(idx["last"], int(msg.id))
            name = _doc_name(msg)
            if name:
                idx["items"][str(msg.id)] = [str(getattr(msg, "message", "") or "").split("\n", 1)[0][:200], name]
                n += 1
        idx["at"] = time.time()
        if n or idx["last"] != last:
            _save_index(key, idx)
            log.info("텔레그램 채널 %s 목록: 영상 %d개 더 읽음 (모두 %d개)", key, n, len(idx["items"]))


_PART_TAIL = re.compile(r"(?:_\d{3,4}"                                   # 자동 올리기 조각 _0000 (3자리도)
                        r"|[ ._-]+(?:part|pt|cd|disc|disk)[ ._-]?\d{1,2}"   # 다른 사람이 나눈 것 .part1 / CD2 / disc 1
                        r"|\s*[(\[]\s*\d{1,2}\s*(?:/|of)\s*\d{1,2}\s*[)\]])$", re.I)   # (1/2) [2 of 3]


def file_stem_key(file_name):
    """같은 파일 이름 비교용 (확장자, 나눈 조각 꼬리 _0000·.part1·CD2·(1/2) 무시, 대소문자 무시).
    꼬리만 지운다 - "…Part.1.2010.1080p"처럼 이름 가운데의 Part 1(작품 이름)은 그대로라 1편·2편이 섞이지 않는다"""
    stem = os.path.splitext(os.path.basename(str(file_name or "")))[0]
    return _PART_TAIL.sub("", stem).casefold()


def _cached(cache, channel, build):
    idx = _index(channel)
    sig = (len(idx["items"]), idx["last"])
    hit = cache.get(abs(int(channel)))
    if not hit or hit[0] != sig:
        hit = cache[abs(int(channel))] = (sig, build(idx["items"]))
    return hit[1]


def channel_file(_sid, channel, file_name):
    """이 채널에 같은 이름의 영상이 이미 있으면 그 제목 (없으면 "")"""
    want = file_stem_key(file_name)
    if not want:
        return ""

    def build(items):
        out = {}
        for msg in sorted(items, key=int):
            title, name = items[msg]
            out.setdefault(file_stem_key(name), title or name)
        return out
    return _cached(_NAME_CACHE, channel, build).get(want, "")


_MOVIE_CACHE = {}        # 채널 -> (항목 수, 마지막 메시지, {(작품 키, 연도): 제목})


def channel_movie(_sid, channel, name_key, year):
    """이 채널에 같은 영화(작품 이름 + 연도)가 이미 있으면 그 제목 (없으면 "") - 파일 이름, 안 되면 캡션 첫 줄에서 읽는다.
    회차 표시가 있는 것(드라마)은 빼고, 연도가 없으면 비교하지 않는다 (같은 이름의 다른 영화와 섞이지 않게)"""
    if not name_key or not year:
        return ""
    from . import folder_watch, plex_to_tg   # (순환 import를 피해 여기서)

    def build(items):
        out = {}
        for msg in sorted(items, key=int):
            title, name = items[msg]
            cap = re.sub(r"\s*[(\[]\s*\d{1,2}\s*(?:/|of)\s*\d{1,2}\s*[)\]]\s*$", "", title or "")   # 캡션 꼬리 (1/2)
            for text in (name, f"{cap}.mp4" if cap else ""):
                f = folder_watch.file_fields(text) if text else None
                if f and f.get("year") and not plex_to_tg.episode_key(f):
                    out.setdefault((plex_to_tg._name_key(f.get("title")), str(f["year"])), title or name)
                    break
        return out
    return _cached(_MOVIE_CACHE, channel, build).get((name_key, str(year)), "")


def channel_episode(_sid, channel, name_key, season, ep):
    """이 채널에 같은 작품·시즌·회차 영상이 이미 있으면 그 제목 (없으면 "") - 파일 이름, 안 되면 캡션 첫 줄에서 읽는다"""
    if not name_key or ep is None:
        return ""
    from . import folder_watch, plex_to_tg   # (순환 import를 피해 여기서)

    def build(items):
        out = {}
        for msg in sorted(items, key=int):
            title, name = items[msg]
            for text in (name, f"{title}.mp4" if title else ""):
                info = plex_to_tg.episode_key(folder_watch.file_fields(text)) if text else None
                if info:
                    out.setdefault(info, title or name)
                    break
        return out
    return _cached(_EP_CACHE, channel, build).get((name_key, int(season or 1), int(ep)), "")
