"""BookOasis 3D 서재 AI

- 손님 대화: 지금 층의 보관함에서 책 한 권을 무작위로 골라, 두 손님이 그 책 이야기를 나누는 짧은 대화를 LLM이 쓴다.
- 질문하기: BookOasis MCP 서버(tools/mcp_server.py, stdio)의 읽기 전용 도구를 LLM에 붙여 서재에 대한 질문에 답한다.

LLM은 두 가지로 부른다:
  openai     OpenAI 호환 /chat/completions (LiteLLM·Ollama·LM Studio·OpenAI 등) - 표준 라이브러리만 씀
  anthropic  Claude API (anthropic 패키지 필요: pip install anthropic)

설정은 .env에 저장한다 (save_env는 파일 권한 0600):
  LIB3D_AI_PROVIDER     openai(기본) | anthropic
  LIB3D_AI_BASE_URL     OpenAI 호환 API 주소 (예: http://192.168.0.26:4000/v1)
  LIB3D_AI_API_KEY      API 키 (anthropic에서 비우면 ANTHROPIC_API_KEY 등 SDK 기본 인증)
  LIB3D_AI_MODEL        모델 (openai는 필수, anthropic 기본 claude-opus-5-5)
  LIB3D_AI_CHAT         손님 대화 켜기 (기본 false)
  LIB3D_AI_CHAT_SEC     대화 사이 최소 간격(초, 기본 60) - 호출 비용을 묶는다
  LIB3D_AI_ASK          질문하기 켜기 (기본 false)
  LIB3D_MCP_COMMAND     BookOasis MCP 실행 명령 (예: docker exec -i bookoasis python3 tools/mcp_server.py)
"""
import json
import logging
import queue
import random
import shlex
import subprocess
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import bookoasis_db, config, lib3d

log = logging.getLogger("gdw.lib3d_ai")

DEFAULT_MODEL = "claude-opus-5-5"
# 거절(refusal) 시 서버가 다른 모델로 이어 받는 기능("default")을 받는 모델
_FALLBACK_MODELS = ("claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5")
_FALLBACK_BETA = "server-side-fallback-2026-07-01"
# BookOasis MCP 도구 중 읽기 전용만 쓴다 (쓰기·제안 도구는 붙이지 않는다)
READ_ONLY_TOOLS = ("search_books", "get_random_book", "get_library_stats", "find_missing_cover",
                   "find_missing_genre_and_tags", "find_missing_offsets", "find_duplicate_series", "list_problems",
                   "get_problem_card", "diagnose_book", "get_version", "run_readonly_query", "call_api")
TOOL_RESULT_MAX = 40000   # 도구 결과가 이보다 길면 잘랐다고 표시하고 자른다
ASK_MAX_STEPS = 10

KEYS = ("LIB3D_AI_PROVIDER", "LIB3D_AI_BASE_URL", "LIB3D_AI_API_KEY", "LIB3D_AI_MODEL", "LIB3D_AI_CHAT", "LIB3D_AI_CHAT_SEC", "LIB3D_AI_ASK", "LIB3D_MCP_COMMAND")


# ── 설정 ──
def provider():
    return "anthropic" if config.env("LIB3D_AI_PROVIDER", "openai").lower() == "anthropic" else "openai"


def model():
    m = config.env("LIB3D_AI_MODEL")
    return m or (DEFAULT_MODEL if provider() == "anthropic" else "")


def chat_sec():
    return max(15, min(3600, config.env_int("LIB3D_AI_CHAT_SEC", 60)))


def sdk_ok():
    try:
        import anthropic  # noqa: F401
        return True
    except ImportError:
        return False


def flags():
    """화면에 알려 줄 켜짐 상태 (키·명령은 보내지 않는다)"""
    return {"chat": config.env_bool("LIB3D_AI_CHAT", False), "ask": config.env_bool("LIB3D_AI_ASK", False),
            "chat_sec": chat_sec()}


def settings():
    return dict(flags(), provider=provider(), base_url=config.env("LIB3D_AI_BASE_URL"), model=model(),
                api_key_set=bool(config.env("LIB3D_AI_API_KEY") or (provider() == "anthropic" and config.env("ANTHROPIC_API_KEY"))),
                mcp_command=config.env("LIB3D_MCP_COMMAND"), sdk=sdk_ok(), fixed=config.overridden(list(KEYS)))


def save(values):
    """화면에서 보낸 항목만 .env에 쓴다. api_key가 빈 문자열이면 그대로 둔다(지우려면 clear_key)."""
    out = {}
    if "chat" in values:
        out["LIB3D_AI_CHAT"] = "true" if values["chat"] else "false"
    if "ask" in values:
        out["LIB3D_AI_ASK"] = "true" if values["ask"] else "false"
    if "chat_sec" in values:
        out["LIB3D_AI_CHAT_SEC"] = str(max(15, min(3600, int(values["chat_sec"] or 60))))
    if "provider" in values:
        out["LIB3D_AI_PROVIDER"] = "anthropic" if values["provider"] == "anthropic" else "openai"
    if "base_url" in values:
        url = str(values["base_url"] or "").strip().rstrip("/")
        if url and not url.startswith(("http://", "https://")):
            raise ValueError("API 주소는 http:// 또는 https://로 시작해야 합니다.")
        out["LIB3D_AI_BASE_URL"] = url
    if "model" in values:
        out["LIB3D_AI_MODEL"] = str(values["model"] or "").strip()
    if "mcp_command" in values:
        out["LIB3D_MCP_COMMAND"] = str(values["mcp_command"] or "").strip()
    if values.get("api_key"):
        out["LIB3D_AI_API_KEY"] = str(values["api_key"]).strip()
    if values.get("clear_key"):
        out["LIB3D_AI_API_KEY"] = ""
    fixed = config.overridden(list(out))
    if fixed:
        raise ValueError("실제 환경변수로 지정돼 있어 화면에서 바꿀 수 없습니다: " + ", ".join(fixed))
    if out:
        config.save_env(out)
    if "LIB3D_MCP_COMMAND" in out:
        MCP.stop()
    return settings()


# ── Claude 호출 ──
def _client():
    try:
        import anthropic
    except ImportError as error:
        raise RuntimeError("anthropic 패키지가 없습니다. 서버에서 pip install anthropic 후 다시 시작하세요.") from error
    key = config.env("LIB3D_AI_API_KEY")
    return anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()


def _create(**kw):
    """모델이 받으면 거절 시 다른 모델로 이어 받기(fallbacks="default")를 켠다"""
    client = _client()   # 패키지가 없으면 여기서 안내 문구로 멈춘다
    import anthropic
    m = model()
    try:
        if m in _FALLBACK_MODELS:
            return client.beta.messages.create(model=m, betas=[_FALLBACK_BETA], fallbacks="default", **kw)
        return client.beta.messages.create(model=m, **kw)
    except anthropic.AuthenticationError as error:
        raise RuntimeError("Claude API 키가 맞지 않습니다 (3D 서재 설정 > AI).") from error
    except anthropic.PermissionDeniedError as error:
        raise RuntimeError("이 API 키로는 %s 모델을 쓸 수 없습니다." % m) from error
    except anthropic.NotFoundError as error:
        raise RuntimeError("모델 이름을 확인하세요: %s" % m) from error
    except anthropic.RateLimitError as error:
        raise RuntimeError("Claude API 사용 한도에 걸렸습니다. 잠시 뒤 다시 하세요.") from error
    except anthropic.APIConnectionError as error:
        raise RuntimeError("Claude API에 연결하지 못했습니다.") from error
    except anthropic.APIStatusError as error:
        raise RuntimeError("Claude API 오류 (%s): %s" % (error.status_code, error.message)) from error


# ── OpenAI 호환 (/chat/completions) 호출 ──
def _oa_post(payload, timeout=180):
    base = config.env("LIB3D_AI_BASE_URL").rstrip("/")
    if not base:
        raise ValueError("OpenAI 호환 API 주소가 없습니다 (3D 서재 설정 > AI).")
    if not payload.get("model"):
        raise ValueError("모델 이름이 없습니다 (3D 서재 설정 > AI).")
    headers = {"Content-Type": "application/json"}
    key = config.env("LIB3D_AI_API_KEY")
    if key:
        headers["Authorization"] = "Bearer " + key
    req = Request(base + "/chat/completions", data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers=headers)
    try:
        with urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except HTTPError as error:
        body = error.read().decode("utf-8", "replace")
        try:
            msg = json.loads(body).get("error", body)
            msg = msg.get("message", msg) if isinstance(msg, dict) else msg
        except ValueError:
            msg = body
        if error.code in (401, 403):
            raise RuntimeError("API 키가 맞지 않습니다 (%s): %s" % (error.code, str(msg)[:300])) from error
        raise _OaError(error.code, "LLM API 오류 (%s): %s" % (error.code, str(msg)[:300])) from error
    except (URLError, OSError) as error:
        raise RuntimeError("LLM API(%s)에 연결하지 못했습니다: %s" % (base, getattr(error, "reason", error))) from error
    except ValueError as error:
        raise RuntimeError("LLM API 응답이 JSON이 아닙니다.") from error


class _OaError(RuntimeError):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code


def _oa_message(resp):
    try:
        return resp["choices"][0]["message"] or {}, resp["choices"][0].get("finish_reason")
    except (KeyError, IndexError, TypeError) as error:
        raise RuntimeError("LLM API 응답에 choices가 없습니다.") from error


def _json_from(text):
    """```json 울타리나 앞뒤 말이 붙어 와도 첫 JSON 객체를 꺼낸다"""
    text = (text or "").strip()
    try:
        return json.loads(text)
    except ValueError:
        a, b = text.find("{"), text.rfind("}")
        if a >= 0 and b > a:
            return json.loads(text[a:b + 1])
        raise


def _oa_schema(node):
    """MCP 입력 스키마를 OpenAI 호환 함수 스키마로 다듬는다 (Gemini 등이 싫어하는 title·default 제거, null 허용은 본래 타입으로)"""
    if isinstance(node, list):
        return [_oa_schema(x) for x in node]
    if not isinstance(node, dict):
        return node
    for key in ("anyOf", "oneOf"):
        if key in node:
            opts = [o for o in node[key] if not (isinstance(o, dict) and o.get("type") == "null")]
            if len(opts) == 1:
                merged = dict(opts[0])
                for k in ("description",):
                    if k in node and k not in merged:
                        merged[k] = node[k]
                return _oa_schema(merged)
    out = {}
    for k, v in node.items():
        if k in ("title", "default", "$schema", "additionalProperties"):
            continue
        out[k] = {pk: _oa_schema(pv) for pk, pv in v.items()} if k == "properties" and isinstance(v, dict) else _oa_schema(v)
    if out.get("type") == "object" and "properties" not in out:
        out["properties"] = {}
    return out


def _text(resp):
    return "".join(b.text for b in resp.content if b.type == "text").strip()


# ── 손님 대화 ──
_CHAT = {"last": 0.0, "cache": {}, "lock": threading.Lock()}
_CHAT_SCHEMA = {
    "type": "object",
    "properties": {"lines": {"type": "array", "items": {
        "type": "object",
        "properties": {"who": {"type": "integer", "enum": [0, 1]}, "text": {"type": "string"}},
        "required": ["who", "text"], "additionalProperties": False}}},
    "required": ["lines"], "additionalProperties": False,
}
_CHAT_SYSTEM = (
    "너는 서점 안 두 손님(0번, 1번)이 서가 앞에서 책 한 권을 두고 나누는 짧은 대화를 쓴다.\n"
    "- 한국어 구어체로 4~6줄, 한 줄은 40자 안팎. 0번과 1번이 번갈아 말한다.\n"
    "- 주어진 책 정보(제목·작가·장르·태그·줄거리)에 있는 내용만 근거로 말한다. 정보에 없는 줄거리·결말·등장인물을 지어내지 않는다. "
    "정보가 제목뿐이면 제목에서 받은 인상, 읽어 볼지 말지 같은 이야기를 한다.\n"
    "- 큰 스포일러는 피한다. 성인 서재의 책이라도 대화는 노골적이지 않게 쓴다.")
_CHAT_JSON_RULE = '답은 JSON 객체 하나만: {"lines": [{"who": 0, "text": "..."}, {"who": 1, "text": "..."}]} (who는 0 또는 1)'



def _book_detail(db_type, book_id):
    gw = bookoasis_db.gateway(db_type)
    for cols in ("title, series_name, author, genre, tags, summary, publisher", "title, series_name"):
        try:
            rows = gw.fetch_all("SELECT " + cols + " FROM books WHERE id = %s", (book_id,))
            return rows[0] if rows else {}
        except Exception:  # noqa: BLE001 - 칼럼이 없는 BookOasis 버전
            continue
    return {}


def _pick_book(lib_keys):
    libs = [l for l in lib3d.data().get("libraries", []) if not lib_keys or l["key"] in lib_keys]
    libs = [l for l in libs if l.get("series")]
    if not libs:
        raise ValueError("이 층에 책이 없습니다.")
    lib = random.choice(libs)
    s = random.choice(lib["series"])
    return lib, s


def _chat_text(user):
    if provider() == "anthropic":
        resp = _create(max_tokens=4000, system=_CHAT_SYSTEM,
                       output_config={"effort": "low", "format": {"type": "json_schema", "schema": _CHAT_SCHEMA}},
                       messages=[{"role": "user", "content": user}])
        if resp.stop_reason == "refusal":
            raise RuntimeError("이 책으로는 대화를 만들지 않았습니다.")
        return _text(resp)
    payload = {"model": model(), "max_tokens": 2000, "response_format": {"type": "json_object"},
               "messages": [{"role": "system", "content": _CHAT_SYSTEM + "\n" + _CHAT_JSON_RULE},
                            {"role": "user", "content": user}]}
    try:
        resp = _oa_post(payload)
    except _OaError as error:   # json_object를 모르는 모델·게이트웨이면 지시문만으로 다시
        if error.code != 400:
            raise
        payload.pop("response_format")
        resp = _oa_post(payload)
    return _oa_message(resp)[0].get("content") or ""


def chat(lib_keys):
    """{"book": {...}, "lines": [{"who", "text"}]} - 간격(LIB3D_AI_CHAT_SEC)보다 자주 부르면 지난 대화 중 하나를 다시 쓴다"""
    if not flags()["chat"]:
        raise ValueError("손님 대화가 꺼져 있습니다 (3D 서재 설정 > AI).")
    with _CHAT["lock"]:
        wait = chat_sec() - (time.time() - _CHAT["last"])
        cached = [v for v in _CHAT["cache"].values() if not lib_keys or v["book"]["lib"] in lib_keys]
        if wait > 0:
            if cached:
                return dict(random.choice(cached), reused=True)
            return {"book": None, "lines": [], "wait": int(wait) + 1}
        _CHAT["last"] = time.time()
    lib, s = _pick_book(lib_keys)
    ck = "%s|%s" % (lib["key"], s["title"])
    if ck in _CHAT["cache"]:
        return dict(_CHAT["cache"][ck], reused=True)
    d = _book_detail(lib["db_type"], s["last"]) if s.get("last") else {}
    info = {"제목": s["title"] or d.get("title"), "보관함": lib["name"], "권수": s.get("count")}
    for k, name in (("author", "작가"), ("genre", "장르"), ("tags", "태그"), ("publisher", "출판사"), ("summary", "줄거리")):
        v = (d.get(k) or "").strip() if isinstance(d.get(k), str) else d.get(k)
        if v:
            info[name] = v
    user = "책 정보:\n" + json.dumps(info, ensure_ascii=False, indent=1)
    try:
        text = _chat_text(user)
    except Exception:
        with _CHAT["lock"]:
            _CHAT["last"] = 0.0   # 실패하면 다음 호출을 막지 않는다
        raise
    try:
        lines = _json_from(text)["lines"]
    except (ValueError, KeyError, TypeError) as error:
        raise RuntimeError("대화를 읽지 못했습니다 (모델이 JSON으로 답하지 않음).") from error
    out = {"book": {"title": info["제목"], "lib": lib["key"], "lib_name": lib["name"]},
           "lines": [{"who": int(x.get("who", i % 2)) % 2, "text": str(x.get("text", ""))[:120]} for i, x in enumerate(lines) if x.get("text")][:8]}
    with _CHAT["lock"]:
        if len(_CHAT["cache"]) > 100:
            _CHAT["cache"].pop(next(iter(_CHAT["cache"])))
        _CHAT["cache"][ck] = out
    return out


# ── BookOasis MCP (stdio JSON-RPC) ──
class McpClient:
    """BookOasis tools/mcp_server.py를 자식 프로세스로 띄워 한 줄짜리 JSON-RPC로 주고받는다. 한 번에 한 요청."""

    def __init__(self):
        self.proc = None
        self.cmd = ""
        self.lines = queue.Queue()
        self.lock = threading.Lock()
        self.seq = 0
        self.tools = []

    def stop(self):
        with self.lock:
            self._kill()

    def _kill(self):
        if self.proc:
            try:
                self.proc.kill()
            except OSError:
                pass
        self.proc, self.tools = None, []

    def _reader(self, proc):
        for raw in proc.stdout:
            self.lines.put(raw)
        self.lines.put(None)

    def _errlog(self, proc):
        for raw in proc.stderr:
            log.debug("BookOasis MCP: %s", raw.decode("utf-8", "replace").rstrip())

    def _send(self, obj):
        self.proc.stdin.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
        self.proc.stdin.flush()

    def _rpc(self, method, params, timeout=90):
        self.seq += 1
        rid = self.seq
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        end = time.time() + timeout
        while True:
            try:
                raw = self.lines.get(timeout=max(0.1, end - time.time()))
            except queue.Empty:
                self._kill()
                raise RuntimeError("BookOasis MCP가 %d초 안에 답하지 않았습니다." % timeout)
            if raw is None:
                self._kill()
                raise RuntimeError("BookOasis MCP가 끝났습니다. 실행 명령을 확인하세요.")
            try:
                msg = json.loads(raw)
            except ValueError:
                continue   # 프로토콜이 아닌 출력은 건너뛴다
            if msg.get("id") != rid:
                continue
            if msg.get("error"):
                raise RuntimeError("BookOasis MCP 오류: %s" % msg["error"].get("message"))
            return msg.get("result") or {}

    def _ensure(self):
        cmd = config.env("LIB3D_MCP_COMMAND")
        if not cmd:
            raise ValueError("BookOasis MCP 실행 명령이 없습니다 (3D 서재 설정 > AI).")
        if self.proc and self.proc.poll() is None and self.cmd == cmd and self.tools:
            return
        self._kill()
        self.lines = queue.Queue()
        try:
            self.proc = subprocess.Popen(shlex.split(cmd), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE)
        except OSError as error:
            self.proc = None
            raise RuntimeError("BookOasis MCP를 실행하지 못했습니다: %s" % error) from error
        self.cmd = cmd
        threading.Thread(target=self._reader, args=(self.proc,), daemon=True).start()
        threading.Thread(target=self._errlog, args=(self.proc,), daemon=True).start()
        self._rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                 "clientInfo": {"name": "bookoasis-assistant-lib3d", "version": lib3d.VERSION}}, timeout=60)
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        tools = self._rpc("tools/list", {}).get("tools", [])
        self.tools = [t for t in tools if t.get("name") in READ_ONLY_TOOLS]

    def list_tools(self):
        with self.lock:
            self._ensure()
            return list(self.tools)

    def call(self, name, args):
        if name not in READ_ONLY_TOOLS:
            return "이 도구는 쓸 수 없습니다: " + name, True
        with self.lock:
            self._ensure()
            res = self._rpc("tools/call", {"name": name, "arguments": args or {}}, timeout=120)
        parts = [c.get("text", "") for c in res.get("content", []) if c.get("type") == "text"]
        text = "\n".join(parts) if parts else json.dumps(res.get("structuredContent", res), ensure_ascii=False)
        if len(text) > TOOL_RESULT_MAX:
            text = text[:TOOL_RESULT_MAX] + "\n...(결과가 길어 %d자 중 앞부분만 보냄)" % len(text)
        return text, bool(res.get("isError"))


MCP = McpClient()


def test_mcp():
    tools = MCP.list_tools()
    return {"tools": [t["name"] for t in tools]}


_ASK_SYSTEM = (
    "너는 BookOasis 개인 서재(만화·소설·오디오북·영상)의 안내 데스크 직원이다. 사용자는 이 서재의 관리자다.\n"
    "- 서재 내용에 대한 질문은 BookOasis 도구로 실제 데이터를 확인한 뒤 답한다. 확인하지 못한 것은 추측이라고 밝힌다.\n"
    "- db_type은 general(일반)·adult(성인)·audiobook(오디오북)이다. 어느 서재인지 모호하면 general부터 본다.\n"
    "- 답은 한국어로 짧고 분명하게. 목록은 많아야 10개까지 보여 주고 나머지는 개수만 알려 준다.")


def ask(question, history=None):
    """{"answer", "tools": [쓴 도구 이름…]} - history는 [{"q", "a"}] (화면이 기억하는 지난 문답)"""
    if not flags()["ask"]:
        raise ValueError("질문하기가 꺼져 있습니다 (3D 서재 설정 > AI).")
    question = str(question or "").strip()[:2000]
    if not question:
        raise ValueError("질문을 적어 주세요.")
    mcp_tools = MCP.list_tools()
    if provider() != "anthropic":
        return _ask_openai(question, history, mcp_tools)
    tools = [{"name": t["name"], "description": (t.get("description") or "")[:1024],
              "input_schema": t.get("inputSchema") or {"type": "object", "properties": {}}} for t in mcp_tools]
    messages = []
    for h in (history or [])[-6:]:
        if isinstance(h, dict) and h.get("q") and h.get("a"):
            messages += [{"role": "user", "content": str(h["q"])[:2000]}, {"role": "assistant", "content": str(h["a"])[:4000]}]
    messages.append({"role": "user", "content": question})
    used = []
    for _ in range(ASK_MAX_STEPS):
        resp = _create(max_tokens=16000, system=_ASK_SYSTEM, tools=tools, output_config={"effort": "medium"},
                       messages=messages)
        if resp.stop_reason == "refusal":
            return {"answer": "이 질문에는 답하지 않았습니다.", "tools": used}
        if resp.stop_reason != "tool_use":
            return {"answer": _text(resp) or "(답이 비어 있습니다)", "tools": used}
        messages.append({"role": "assistant", "content": resp.content})
        results = []
        for b in resp.content:
            if b.type != "tool_use":
                continue
            used.append(b.name)
            try:
                text, is_err = MCP.call(b.name, b.input if isinstance(b.input, dict) else {})
            except Exception as error:  # noqa: BLE001 - 도구 실패는 모델에게 알려 다른 길을 찾게 한다
                text, is_err = "도구 실행 실패: %s" % error, True
            results.append({"type": "tool_result", "tool_use_id": b.id, "content": text, "is_error": is_err})
        messages.append({"role": "user", "content": results})
    return {"answer": "도구를 너무 여러 번 써서 멈췄습니다. 질문을 좁혀 다시 물어 주세요.", "tools": used}


def _ask_openai(question, history, mcp_tools):
    """OpenAI 호환 도구 호출(tools/tool_calls)로 같은 일을 한다"""
    tools = [{"type": "function", "function": {
        "name": t["name"], "description": (t.get("description") or "")[:1024],
        "parameters": _oa_schema(t.get("inputSchema") or {"type": "object", "properties": {}})}} for t in mcp_tools]
    messages = [{"role": "system", "content": _ASK_SYSTEM}]
    for h in (history or [])[-6:]:
        if isinstance(h, dict) and h.get("q") and h.get("a"):
            messages += [{"role": "user", "content": str(h["q"])[:2000]}, {"role": "assistant", "content": str(h["a"])[:4000]}]
    messages.append({"role": "user", "content": question})
    used = []
    for _ in range(ASK_MAX_STEPS):
        msg, finish = _oa_message(_oa_post({"model": model(), "messages": messages, "tools": tools, "max_tokens": 4000}))
        calls = msg.get("tool_calls") or []
        if not calls:
            return {"answer": (msg.get("content") or "").strip() or "(답이 비어 있습니다)", "tools": used}
        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        for c in calls:
            fn = c.get("function") or {}
            name = fn.get("name") or ""
            used.append(name)
            try:
                args = json.loads(fn.get("arguments") or "{}") if isinstance(fn.get("arguments"), str) else (fn.get("arguments") or {})
                text, is_err = MCP.call(name, args if isinstance(args, dict) else {})
            except Exception as error:  # noqa: BLE001 - 도구 실패는 모델에게 알려 다른 길을 찾게 한다
                text, is_err = "도구 실행 실패: %s" % error, True
            messages.append({"role": "tool", "tool_call_id": c.get("id") or name, "content": ("[오류] " if is_err else "") + text})
    return {"answer": "도구를 너무 여러 번 써서 멈췄습니다. 질문을 좁혀 다시 물어 주세요.", "tools": used}
