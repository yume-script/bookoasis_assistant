# -*- coding: utf-8 -*-
"""자동 올리기에 쓰는 텔레그램 계정 하나 (telethon 사용자 로그인 - 봇이 아니라 내 계정이라 2GB/4GB 파일을 올린다).

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

from . import compat

log = logging.getLogger("tgup.telegram")
KEEP_PLEX_META = False   # plex_to_tg._save_meta: 작품 정보는 YMPlayer 텔레그램 색인에만 쓰여 여기선 남기지 않는다
ACCOUNT_ID = "tg"        # 규칙의 tg 칸 (계정이 하나뿐)


class TgError(Exception):
    pass


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


class TelegramAccount:
    def __init__(self):
        self.client = None
        self._key = None
        self._lock = asyncio.Lock()
        self._code_hash = None
        self.phone = ""

    @property
    def session_path(self):
        return os.path.join(compat.DATA_DIR, "telegram.session")

    @property
    def peers_path(self):
        return os.path.join(compat.DATA_DIR, "peers.json")

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
            key = (conf["api_id"], conf["api_hash"])
            if self.client is not None and self._key != key:   # API 값을 바꿨으면 새로 연결
                await self.client.disconnect()
                self.client = None
            if self.client is None:
                os.makedirs(compat.DATA_DIR, exist_ok=True)
                # 텔레그램에 닿지 않을 때 화면이 오래 멈추지 않게 (기본은 5번 x 10초)
                self.client = TelegramClient(self.session_path, int(conf["api_id"]), conf["api_hash"], receive_updates=False,
                                             connection_retries=2, timeout=10)
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
        base = {"authorized": False, "phone": self.phone or conf["phone"], "api_id": conf["api_id"],
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
        phone = re.sub(r"[\s-]", "", phone or self.phone or api_conf()["phone"])
        if not phone:
            raise TgError("전화번호를 넣어 주세요 (국가번호 포함, 예: +821012345678).")
        client = await self.get_client()
        sent = await client.send_code_request(phone)
        self.phone, self._code_hash = phone, sent.phone_code_hash
        data = compat.load()
        data.setdefault("telegram", {})["phone"] = phone
        compat.save(data)
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
            raise TgError(f"채널 {channel}을(를) 대화 목록에서 찾지 못했습니다 (나갔거나 지워졌을 수 있음).")
        return InputPeerChannel(int(channel), int(h))
