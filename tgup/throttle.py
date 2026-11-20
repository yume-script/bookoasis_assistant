# -*- coding: utf-8 -*-
"""텔레그램 업로드 속도 제한 감지 (계정마다).

1) 텔레그램이 '기다려라'라고 알려 준 것 (FLOOD_WAIT / FLOOD_PREMIUM_WAIT): Telethon은 60초 이하면 알리지 않고 혼자 기다린 뒤
   이어 올린다 - 그 로그("Sleeping for Ns ... on SaveBigFilePartRequest flood wait")를 계정별 로거(tgup.tg.<계정>)에서 잡아 센다.
   파일 조각 올리기(Save*FilePartRequest)에서 기다린 것은 업로드 속도 제한이다 (프리미엄이 아닌 계정이면 FLOOD_PREMIUM_WAIT로 본다).
2) 신호 없이 느려진 것: 올리는 동안 최근 30초 속도를 재고, 그 계정의 평소 속도(최근 업로드 중앙값)와 비교한다 -
   평소의 SLOW_RATIO 아래가 SLOW_MIN분 넘게 이어지면 '느림 의심' (다른 계정도 같이 느리면 우리 회선 쪽일 수 있음).
상태(state): ok / slow(느림 의심) / limited(텔레그램이 제한 - 최근 10분 대기 LIMIT_SEC초 이상)
"""
import logging
import re
import statistics
import threading
import time

LOGGER = "tgup.tg"            # TelegramClient(base_logger="tgup.tg.<계정>")
WINDOW_SEC = 30               # 지금 속도를 재는 구간
SLOW_RATIO = 0.4
SLOW_MIN = 3
LIMIT_WINDOW = 600            # 최근 10분 안의 대기
LIMIT_SEC = 30                # 그 안에 이만큼 넘게 기다렸으면 '제한'
KEEP_EVENTS = 200
KEEP_SPEEDS = 20
MIN_BYTES = 20 * 1024 * 1024  # 이보다 작은 파일은 평소 속도 계산에 안 넣는다 (시작·마무리 시간이 커서)

_FLOOD_RE = re.compile(r"Sleeping(?: early)? for (\d+)s .* on (\w+) flood wait")
_lock = threading.Lock()
_acc = {}          # 계정 -> {"events": [(시각, 초, 요청)], "speeds": [MB/s], "samples": [(시각, 바이트)], "slow_since": 0, "premium": None}


def _a(tg):
    return _acc.setdefault(tg, {"events": [], "speeds": [], "samples": [], "slow_since": 0, "premium": None, "uploading": False})


class _FloodHandler(logging.Handler):
    def emit(self, record):
        try:
            m = _FLOOD_RE.search(record.getMessage())
            if not m:
                return
            # 로거 이름 tgup.tg.<계정>.client.users
            parts = record.name.split(".")
            tg = parts[2] if len(parts) > 2 and parts[0] == "tgup" and parts[1] == "tg" else "?"
            flood(tg, int(m.group(1)), m.group(2))
        except Exception:  # noqa: BLE001 - 로그 처리가 업로드를 막지 않게
            pass


_installed = False


def install():
    """계정별 Telethon 로거(tgup.tg.*)의 대기 로그를 잡는다 (한 번)"""
    global _installed
    if _installed:
        return
    lg = logging.getLogger(LOGGER)
    lg.setLevel(logging.INFO)   # (Telethon 대기 로그는 INFO)
    lg.addHandler(_FloodHandler())
    # Telethon의 다른 INFO(연결 등)가 로그를 채우지 않게 위로는 경고부터만 넘긴다
    lg.propagate = False
    lg.addHandler(_Forward())
    _installed = True


class _Forward(logging.Handler):
    def __init__(self):
        super().__init__(logging.WARNING)

    def emit(self, record):
        logging.getLogger("tgup").handle(record)


def logger_name(tg):
    return f"{LOGGER}.{tg}"


def flood(tg, seconds, request="", now=None):
    now = now or time.time()
    with _lock:
        ev = _a(tg)["events"]
        ev.append((now, int(seconds), str(request)))
        del ev[:-KEEP_EVENTS]


def set_premium(tg, premium):
    with _lock:
        _a(tg)["premium"] = premium


def progress(tg, done, now=None):
    """올리는 중 진행 바이트 (같은 파일 안에서 늘어나는 값). 0으로 돌아오면 새 파일"""
    now = now or time.time()
    with _lock:
        a = _a(tg)
        s = a["samples"]
        if s and done < s[-1][1]:
            s.clear()
        s.append((now, int(done)))
        while s and now - s[0][0] > WINDOW_SEC * 2:
            s.pop(0)
        a["uploading"] = True
        cur, base = _current(a, now), _baseline(a)
        if cur is not None and base and cur < base * SLOW_RATIO:
            a["slow_since"] = a["slow_since"] or now
        else:
            a["slow_since"] = 0


def done(tg, nbytes, seconds):
    """파일 하나를 다 올림 - 평소 속도에 넣는다"""
    with _lock:
        a = _a(tg)
        a["samples"].clear()
        a["uploading"] = False
        a["slow_since"] = 0
        if nbytes >= MIN_BYTES and seconds > 0:
            a["speeds"].append(nbytes / seconds / 1e6)
            del a["speeds"][:-KEEP_SPEEDS]


def stopped(tg):
    with _lock:
        a = _a(tg)
        a["samples"].clear()
        a["uploading"] = False
        a["slow_since"] = 0


def _current(a, now):
    s = [x for x in a["samples"] if now - x[0] <= WINDOW_SEC]
    if len(s) < 2 or s[-1][0] - s[0][0] < 5:
        return None
    return (s[-1][1] - s[0][1]) / (s[-1][0] - s[0][0]) / 1e6


def _baseline(a):
    return statistics.median(a["speeds"]) if len(a["speeds"]) >= 3 else None


def _is_upload(req):
    return "FilePart" in req


def status(tg, now=None):
    """계정 하나: {state, speed(MB/s, 올리는 중이면), baseline, waits_1h, wait_sec_1h, upload_waits_1h, premium_limit, slow_min, note}"""
    now = now or time.time()
    with _lock:
        a = _a(tg)
        hour = [e for e in a["events"] if now - e[0] <= 3600]
        recent = sum(e[1] for e in a["events"] if now - e[0] <= LIMIT_WINDOW)
        cur = _current(a, now) if a["uploading"] else None
        base = _baseline(a)
        up = [e for e in hour if _is_upload(e[2])]
        premium_limit = bool(up) and a["premium"] is False
        slow_min = int((now - a["slow_since"]) // 60) if a["slow_since"] else 0
        if recent >= LIMIT_SEC:
            state = "limited"
        elif slow_min >= SLOW_MIN:
            state = "slow"
        else:
            state = "ok"
        note = ""
        if state == "limited":
            note = (f"텔레그램이 업로드를 늦춤 - 최근 10분 {recent}초 대기"
                    + (" (프리미엄이 아닌 계정의 업로드 속도 제한 FLOOD_PREMIUM_WAIT)" if premium_limit else ""))
        elif state == "slow":
            note = f"평소({base:.1f}MB/s)보다 느림 - {cur:.2f}MB/s가 {slow_min}분째 (신호 없는 속도 저하 의심)" if base and cur is not None else "느림 의심"
        return {"state": state, "speed": round(cur, 2) if cur is not None else None, "baseline": round(base, 2) if base else None,
                "waits_1h": len(hour), "wait_sec_1h": sum(e[1] for e in hour), "upload_waits_1h": len(up),
                "premium_limit": premium_limit, "slow_min": slow_min, "note": note}


def throttled(tg, now=None):
    return status(tg, now)["state"] != "ok"


def all_status(tgs, now=None):
    out = {tg: status(tg, now) for tg in tgs}
    # 올리는 중인 계정이 모두 느리면 우리 회선 쪽일 수 있다
    slow = [t for t, s in out.items() if s["state"] == "slow"]
    if len(slow) >= 2 and len(slow) == len([t for t, s in out.items() if s["speed"] is not None]):
        for t in slow:
            out[t]["note"] += " · 올리는 계정이 모두 느림 - 이 서버의 회선·디스크 쪽일 수 있음"
    return out


def reset():
    """(시험용)"""
    with _lock:
        _acc.clear()
