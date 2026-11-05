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
                            "moving": bool(body.get("moving")), "reading": str(reading)[:80] if reading else "",
                            "sit": bool(body.get("sit")), "t": now}
        _clean(now)
        others = [dict(v, user=k) for k, v in _STATE.items() if k != username and v["floor"] == floor]
        online = [{"user": k, "floor": v["floor"], "reading": v["reading"]} for k, v in sorted(_STATE.items())]
        try:
            since = int(body.get("since") or 0)
        except (TypeError, ValueError):
            since = 0
        mine = [c for c in _CHAT if not c.get("to") or c["to"] == username]   # 귓속말(안내 데스크 문답)은 당사자에게만
        chat = [c for c in mine if c["id"] > since] if since >= 0 else []
        if since == 0:          # 처음 들어오면 최근 몇 개만
            chat = mine[-10:]
    for o in others:
        o.pop("t", None)
    return {"others": others, "online": online, "chat": chat, "chat_id": _SEQ["chat"]}


def post(user, text, floor="", to=None, books=None):
    """서버가 남기는 메시지 (to가 있으면 그 사람에게만)"""
    with _LOCK:
        _SEQ["chat"] += 1
        msg = {"id": _SEQ["chat"], "user": user, "floor": str(floor or "")[:40], "text": str(text)[:4000], "t": time.time()}
        if to:
            msg["to"] = to
        if books:
            msg["books"] = books
        _CHAT.append(msg)
        del _CHAT[:-CHAT_KEEP]
    return msg


ASK_PREFIXES = ("@안내", "@ai", "@AI", "@봇")
_ASK_HIST = {}   # 사용자 → 최근 문답 [{"q", "a"}]
_ASKING = set()


def ask_in_chat(username, question, floor, ask_fn):
    """관리자가 채팅에서 안내 데스크를 부르면: 질문을 귓속말로 남기고, 답은 다른 스레드에서 구해 귓속말로"""
    import threading as _t
    if not question:
        raise ValueError("'@안내 질문'처럼 물어볼 것을 적어 주세요.")
    with _LOCK:
        if username in _ASKING:
            raise ValueError("앞 질문에 답하는 중입니다. 잠시 기다려 주세요.")
        _ASKING.add(username)
    post(username, "@안내 " + question, floor, to=username)
    post("안내 데스크", "찾아보는 중...", floor, to=username)

    def run():
        try:
            out = ask_fn(question, _ASK_HIST.get(username, []))
            answer = out.get("answer") or "(답이 비어 있습니다)"
            books = out.get("books") or None
            if out.get("tools"):
                answer += "\n(찾아본 도구: " + ", ".join(dict.fromkeys(out["tools"])) + ")"
            if out.get("warnings"):
                answer += "\n(연결 못 한 MCP: " + " / ".join(out["warnings"]) + ")"
            _ASK_HIST[username] = (_ASK_HIST.get(username, []) + [{"q": question, "a": out.get("answer") or ""}])[-6:]
        except Exception as error:  # noqa: BLE001 - 실패 이유를 채팅으로
            answer, books = "답하지 못했습니다: %s" % error, None
        finally:
            with _LOCK:
                _ASKING.discard(username)
        post("안내 데스크", answer, floor, to=username, books=books)
    _t.Thread(target=run, daemon=True).start()


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
