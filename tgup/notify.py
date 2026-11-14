# -*- coding: utf-8 -*-
"""텔레그램 자동 올리기 디스코드 알림.

올리기 기록(plex_to_tg.json의 history)에 새 줄이 생기면 디스코드로 보낸다 - 올린 코드(plex_to_tg.py)는 YMPlayer와
같게 두고, 여기서 기록만 지켜본다 (10초마다).
  설정: data/tgup/settings.json의 "notify" = {"webhook", "bot_token", "channel_id", "ok", "fail", "skip"}
        (화면: 텔레그램 자동 올리기 > 규칙 > 디스코드 알림. 웹훅이 비면 .env의 TGUP_DISCORD_WEBHOOK_URL)
  보내는 곳: 웹훅 주소, 또는 봇 토큰 + 채널 ID (둘 다 있으면 웹훅)
"""
import asyncio
import logging
import re

from . import compat

log = logging.getLogger("tgup.notify")
CHECK_SEC = 10
COLOR = {"ok": 0x2ECC71, "fail": 0xE74C3C, "skip": 0xE67E22}
LABEL = {"ok": "올림", "fail": "실패", "skip": "건너뜀"}
WEBHOOK_RE = re.compile(r"^https://(?:\w+\.)?discord(?:app)?\.com/api/webhooks/\d+/[\w-]+$")


def settings(data=None):
    raw = ((data if data is not None else compat.load()).get("notify")) or {}
    return {"webhook": str(raw.get("webhook") or compat.config.env("TGUP_DISCORD_WEBHOOK_URL") or "").strip(),
            "bot_token": str(raw.get("bot_token") or compat.config.env("TGUP_DISCORD_BOT_TOKEN") or "").strip(),
            "channel_id": str(raw.get("channel_id") or compat.config.env("TGUP_DISCORD_CHANNEL_ID") or "").strip(),
            "ok": bool(raw.get("ok", True)), "fail": bool(raw.get("fail", True)), "skip": bool(raw.get("skip", False))}


def clean(body, old):
    """화면에서 온 값 -> 저장할 값. 토큰 칸이 비면 저장된 토큰 그대로"""
    webhook = str(body.get("webhook") or "").strip()
    if webhook and not WEBHOOK_RE.match(webhook):
        raise ValueError("디스코드 웹훅 주소 모양이 아닙니다 (https://discord.com/api/webhooks/…).")
    channel = str(body.get("channel_id") or "").strip()
    if channel and not channel.isdigit():
        raise ValueError("디스코드 채널 ID는 숫자입니다.")
    return {"webhook": webhook, "bot_token": str(body.get("bot_token") or "").strip() or (old or {}).get("bot_token", ""),
            "channel_id": channel, "ok": bool(body.get("ok", True)), "fail": bool(body.get("fail", True)),
            "skip": bool(body.get("skip", False))}


def public(s):
    """화면에 보낼 것 (봇 토큰은 있는지만)"""
    return {**{k: v for k, v in s.items() if k != "bot_token"}, "has_bot_token": bool(s["bot_token"])}


def kind_of(h):
    if h.get("ok"):
        return "ok"
    return "skip" if str(h.get("note") or "").startswith("건너뜀") else "fail"


def embed_for(h):
    kind = kind_of(h)
    fields = []
    if h.get("channel"):
        fields.append({"name": "채널", "value": str(h["channel"])[:200], "inline": True})
    if h.get("subs"):
        fields.append({"name": "자막", "value": str(h["subs"])[:200], "inline": True})
    if h.get("note"):
        fields.append({"name": "비고", "value": str(h["note"])[:1000], "inline": False})
    return {"title": f"텔레그램 자동 올리기 · {LABEL[kind]}", "description": str(h.get("title") or "")[:1000],
            "color": COLOR[kind], "fields": fields, "footer": {"text": "bookoasis_assistant"}}


async def send(http, s, embed):
    """(성공, 메시지)"""
    from aiohttp import ClientTimeout
    try:
        if s["webhook"]:
            async with http.post(s["webhook"], json={"embeds": [embed]}, timeout=ClientTimeout(total=15)) as r:
                return (r.status < 300), f"웹훅 응답 {r.status}"
        if s["bot_token"] and s["channel_id"]:
            async with http.post(f"https://discord.com/api/v10/channels/{s['channel_id']}/messages",
                                 headers={"Authorization": f"Bot {s['bot_token']}"}, json={"embeds": [embed]},
                                 timeout=ClientTimeout(total=15)) as r:
                return (r.status < 300), f"봇 응답 {r.status}"
    except Exception as e:  # noqa: BLE001
        return False, str(e)
    return False, "디스코드 웹훅 주소나 봇 토큰·채널 ID가 없습니다."


def _sig(h):
    return (h.get("at"), h.get("key"), h.get("note"))


async def watch(http, load_state):
    """기록에 새로 생긴 줄을 보낸다 (처음 볼 때 이미 있던 줄은 보내지 않음)"""
    seen = {_sig(h) for h in load_state().get("history") or []}
    while True:
        await asyncio.sleep(CHECK_SEC)
        try:
            hist = load_state().get("history") or []
            new = [h for h in hist if _sig(h) not in seen]
            seen = {_sig(h) for h in hist}
            if not new:
                continue
            s = settings()
            if not (s["webhook"] or (s["bot_token"] and s["channel_id"])):
                continue
            for h in reversed(new):   # 오래된 것부터
                if not s.get(kind_of(h)):
                    continue
                ok, msg = await send(http, s, embed_for(h))
                if not ok:
                    log.warning("자동 올리기 디스코드 알림 실패: %s", msg)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - 알림이 죽어도 올리기는 계속
            log.exception("자동 올리기 디스코드 알림 확인 실패")
