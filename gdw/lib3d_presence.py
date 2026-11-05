"""BookOasis 3D 서재 함께 보기 - 같은 서재에 들어온 사람들의 위치·채팅 (메모리에만, 다시 시작하면 비워짐)

화면이 0.4초마다 자기 위치를 보내면(POST /api/lib3d/presence) 같은 층의 다른 사람 위치와 새 채팅을 돌려준다.
몇 명~십여 명 규모를 생각한 짧은 주기 요청 방식이다.
"""
import threading
import time

STALE_SEC = 8          # 이만큼 소식이 없으면 나간 것으로 본다
CHAT_KEEP = 80         # 기억할 채팅 수
CHAT_MAX_LEN = 200
CHAT_MIN_GAP = 0.8     # 한 사람이 채팅을 보내는 최소 간격(초)

_LOCK = threading.Lock()
_STATE = {}            # 사용자 → {floor, x, z, yaw, moving, reading, t}
_CHAT = []             # [{id, user, floor, text, t}]
_SEQ = {"chat": 0}
_LAST_SAY = {}


def _num(v, lo=-1e4, hi=1e4):
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return 0.0


def _clean(now):
    for name in [k for k, v in _STATE.items() if now - v["t"] > STALE_SEC]:
        _STATE.pop(name, None)


def update(username, body):
    """내 위치를 남기고 {others, online, chat, chat_id}를 돌려준다"""
    now = time.time()
    floor = str(body.get("floor") or "")[:40]
    reading = body.get("reading")
    with _LOCK:
        _STATE[username] = {"floor": floor, "x": _num(body.get("x")), "z": _num(body.get("z")), "yaw": _num(body.get("yaw"), -100, 100),
                            "moving": bool(body.get("moving")), "reading": str(reading)[:80] if reading else "", "t": now}
        _clean(now)
        others = [dict(v, user=k) for k, v in _STATE.items() if k != username and v["floor"] == floor]
        online = [{"user": k, "floor": v["floor"], "reading": v["reading"]} for k, v in sorted(_STATE.items())]
        try:
            since = int(body.get("since") or 0)
        except (TypeError, ValueError):
            since = 0
        chat = [c for c in _CHAT if c["id"] > since] if since >= 0 else []
        if since == 0:          # 처음 들어오면 최근 몇 개만
            chat = _CHAT[-10:]
    for o in others:
        o.pop("t", None)
    return {"others": others, "online": online, "chat": chat, "chat_id": _SEQ["chat"]}


def say(username, text, floor):
    text = " ".join(str(text or "").split())[:CHAT_MAX_LEN]
    if not text:
        raise ValueError("할 말을 적어 주세요.")
    now = time.time()
    with _LOCK:
        if now - _LAST_SAY.get(username, 0) < CHAT_MIN_GAP:
            raise ValueError("너무 빨리 보냈습니다. 잠시 뒤에 다시 보내 주세요.")
        _LAST_SAY[username] = now
        _SEQ["chat"] += 1
        msg = {"id": _SEQ["chat"], "user": username, "floor": str(floor or "")[:40], "text": text, "t": now}
        _CHAT.append(msg)
        del _CHAT[:-CHAT_KEEP]
    return msg


def leave(username):
    with _LOCK:
        _STATE.pop(username, None)
