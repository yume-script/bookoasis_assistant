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
  LIB3D_MCP_COMMAND     BookOasis MCP 실행 명령 (예: docker exec -i bookoasis python3 tools/mcp_server.py) - 읽기 전용 도구만
  LIB3D_MCP_SERVERS     추가 MCP, 한 줄에 '이름 = 실행 명령 또는 http(s) 주소' (도구 이름은 '이름__도구')
  LIB3D_AI_BUILTIN      기본 도구(지금 시각·날씨·웹 페이지 읽기) 켜기 (기본 true)
"""
import ipaddress
import json
import logging
import queue
import random
import re
import shlex
import socket
import subprocess
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
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

KEYS = ("LIB3D_AI_PROVIDER", "LIB3D_AI_BASE_URL", "LIB3D_AI_API_KEY", "LIB3D_AI_MODEL", "LIB3D_AI_CHAT", "LIB3D_AI_CHAT_SEC", "LIB3D_AI_ASK",
        "LIB3D_MCP_COMMAND", "LIB3D_MCP_SERVERS", "LIB3D_AI_BUILTIN")


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
                mcp_command=config.env("LIB3D_MCP_COMMAND"), mcp_servers=config.env("LIB3D_MCP_SERVERS"),
                builtin=builtin_on(), sdk=sdk_ok(), fixed=config.overridden(list(KEYS)))


def builtin_on():
    return config.env_bool("LIB3D_AI_BUILTIN", True)


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
    if "mcp_servers" in values:
        text = str(values["mcp_servers"] or "").replace("\r", "").strip()
        for ln in text.split("\n"):
            if ln.strip() and not ln.strip().startswith("#") and "=" not in ln:
                raise ValueError("추가 MCP는 한 줄에 '이름 = 실행 명령 또는 http(s) 주소' 형식으로 적어 주세요: " + ln.strip())
        out["LIB3D_MCP_SERVERS"] = text
    if "builtin" in values:
        out["LIB3D_AI_BUILTIN"] = "true" if values["builtin"] else "false"
    if values.get("api_key"):
        out["LIB3D_AI_API_KEY"] = str(values["api_key"]).strip()
    if values.get("clear_key"):
        out["LIB3D_AI_API_KEY"] = ""
    fixed = config.overridden(list(out))
    if fixed:
        raise ValueError("실제 환경변수로 지정돼 있어 화면에서 바꿀 수 없습니다: " + ", ".join(fixed))
    if out:
        config.save_env(out)
    if "LIB3D_MCP_COMMAND" in out or "LIB3D_MCP_SERVERS" in out:
        stop_all()
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
RETRY_CODES = (429, 500, 502, 503, 504, 529)


def _oa_post(payload, timeout=180):
    """서버가 붐비거나(503) 한도에 걸리면(429) 잠깐 쉬었다가 두 번 더 시도한다"""
    for attempt, wait in enumerate((2, 6, None)):
        try:
            return _oa_post_once(payload, timeout)
        except _OaError as error:
            if error.code not in RETRY_CODES:
                raise
            if wait is None:
                kind = "사용 한도에 걸려" if error.code == 429 else "지금 붐벼서"
                raise RuntimeError("LLM 서버가 %s 답하지 못했습니다 (%s, %d번 시도). 잠시 뒤 다시 물어보세요. 자세히: %s"
                                   % (kind, error.code, attempt + 1, error.detail[:200])) from error
            log.info("3D 서재 AI: LLM %s - %d초 뒤 다시 시도", error.code, wait)
            time.sleep(wait)


def _oa_post_once(payload, timeout=180):
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
        raise _OaError(error.code, "LLM API 오류 (%s): %s" % (error.code, str(msg)[:300]), str(msg)) from error
    except (URLError, OSError) as error:
        raise RuntimeError("LLM API(%s)에 연결하지 못했습니다: %s" % (base, getattr(error, "reason", error))) from error
    except ValueError as error:
        raise RuntimeError("LLM API 응답이 JSON이 아닙니다.") from error


class _OaError(RuntimeError):
    def __init__(self, code, msg, detail=""):
        super().__init__(msg)
        self.code = code
        self.detail = re.sub(r"\s+", " ", detail or msg)


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


# ── MCP 연결 (stdio 자식 프로세스 또는 HTTP) ──
def _clip(text):
    if len(text) > TOOL_RESULT_MAX:
        text = text[:TOOL_RESULT_MAX] + "\n...(결과가 길어 %d자 중 앞부분만 보냄)" % len(text)
    return text


def _result_text(res):
    parts = [c.get("text", "") for c in res.get("content", []) if c.get("type") == "text"]
    text = "\n".join(parts) if parts else json.dumps(res.get("structuredContent", res), ensure_ascii=False)
    return _clip(text), bool(res.get("isError"))


class McpClient:
    """MCP 서버를 자식 프로세스로 띄워 한 줄짜리 JSON-RPC로 주고받는다. 한 번에 한 요청.
    allow가 있으면 그 도구만 쓴다 (BookOasis는 읽기 전용 도구만)."""

    def __init__(self, name, cmd, allow=None):
        self.name, self.cmd, self.allow = name, cmd, allow
        self.proc = None
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
            log.debug("MCP %s: %s", self.name, raw.decode("utf-8", "replace").rstrip())

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
                raise RuntimeError("MCP '%s'가 %d초 안에 답하지 않았습니다." % (self.name, timeout))
            if raw is None:
                self._kill()
                raise RuntimeError("MCP '%s'가 끝났습니다. 실행 명령을 확인하세요." % self.name)
            try:
                msg = json.loads(raw)
            except ValueError:
                continue   # 프로토콜이 아닌 출력은 건너뛴다
            if msg.get("id") != rid:
                continue
            if msg.get("error"):
                raise RuntimeError("MCP '%s' 오류: %s" % (self.name, msg["error"].get("message")))
            return msg.get("result") or {}

    def _ensure(self):
        if self.proc and self.proc.poll() is None and self.tools:
            return
        self._kill()
        self.lines = queue.Queue()
        try:
            self.proc = subprocess.Popen(shlex.split(self.cmd), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE)
        except OSError as error:
            self.proc = None
            raise RuntimeError("MCP '%s'를 실행하지 못했습니다: %s" % (self.name, error)) from error
        threading.Thread(target=self._reader, args=(self.proc,), daemon=True).start()
        threading.Thread(target=self._errlog, args=(self.proc,), daemon=True).start()
        self._rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                 "clientInfo": {"name": "bookoasis-assistant-lib3d", "version": lib3d.VERSION}}, timeout=90)
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        tools = self._rpc("tools/list", {}).get("tools", [])
        self.tools = [t for t in tools if self.allow is None or t.get("name") in self.allow]

    def list_tools(self):
        with self.lock:
            self._ensure()
            return list(self.tools)

    def call(self, name, args):
        if self.allow is not None and name not in self.allow:
            return "이 도구는 쓸 수 없습니다: " + name, True
        with self.lock:
            self._ensure()
            res = self._rpc("tools/call", {"name": name, "arguments": args or {}}, timeout=120)
        return _result_text(res)


class HttpMcpClient:
    """원격 MCP 서버 (Streamable HTTP): JSON-RPC를 POST로 보내고 JSON 또는 SSE(data:) 응답을 읽는다"""

    def __init__(self, name, url, headers=None):
        self.name, self.url, self.headers = name, url, headers or {}
        self.session = None
        self.seq = 0
        self.tools = []
        self.lock = threading.Lock()

    def stop(self):
        self.session, self.tools = None, []

    def _post(self, obj, timeout=90):
        h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-06-18"}
        h.update(self.headers)
        if self.session:
            h["Mcp-Session-Id"] = self.session
        req = Request(self.url, data=json.dumps(obj, ensure_ascii=False).encode("utf-8"), headers=h)
        try:
            with urlopen(req, timeout=timeout) as r:
                self.session = r.headers.get("Mcp-Session-Id") or self.session
                body = r.read().decode("utf-8", "replace")
                ctype = r.headers.get("Content-Type") or ""
        except HTTPError as error:
            raise RuntimeError("MCP '%s' HTTP %s: %s" % (self.name, error.code, error.read().decode("utf-8", "replace")[:200])) from error
        except (URLError, OSError) as error:
            raise RuntimeError("MCP '%s'(%s)에 연결하지 못했습니다: %s" % (self.name, self.url, getattr(error, "reason", error))) from error
        if "id" not in obj:
            return {}
        msgs = []
        if "event-stream" in ctype:
            for ln in body.splitlines():
                if ln.startswith("data:"):
                    try:
                        msgs.append(json.loads(ln[5:].strip()))
                    except ValueError:
                        pass
        elif body.strip():
            try:
                parsed = json.loads(body)
                msgs = parsed if isinstance(parsed, list) else [parsed]
            except ValueError as error:
                raise RuntimeError("MCP '%s' 응답을 읽지 못했습니다." % self.name) from error
        for m in msgs:
            if isinstance(m, dict) and m.get("id") == obj["id"]:
                if m.get("error"):
                    raise RuntimeError("MCP '%s' 오류: %s" % (self.name, m["error"].get("message")))
                return m.get("result") or {}
        raise RuntimeError("MCP '%s'가 답을 주지 않았습니다." % self.name)

    def _rpc(self, method, params, timeout=90):
        self.seq += 1
        return self._post({"jsonrpc": "2.0", "id": self.seq, "method": method, "params": params}, timeout)

    def list_tools(self):
        with self.lock:
            if not self.tools:
                self._rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                         "clientInfo": {"name": "bookoasis-assistant-lib3d", "version": lib3d.VERSION}})
                self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
                self.tools = self._rpc("tools/list", {}).get("tools", [])
            return list(self.tools)

    def call(self, name, args):
        with self.lock:
            return _result_text(self._rpc("tools/call", {"name": name, "arguments": args or {}}, timeout=120))


# ── 기본 도구 (MCP 없이도 쓰는 것): 지금 시각, 날씨(Open-Meteo, 키 없음), 웹 페이지 읽기 ──
_WMO = {0: "맑음", 1: "대체로 맑음", 2: "구름 조금", 3: "흐림", 45: "안개", 48: "서리 안개", 51: "약한 이슬비", 53: "이슬비", 55: "강한 이슬비",
        61: "약한 비", 63: "비", 65: "강한 비", 66: "어는 비", 67: "강한 어는 비", 71: "약한 눈", 73: "눈", 75: "강한 눈", 77: "싸락눈",
        80: "소나기", 81: "강한 소나기", 82: "매우 강한 소나기", 85: "눈 소나기", 86: "강한 눈 소나기", 95: "뇌우", 96: "우박 뇌우", 99: "강한 우박 뇌우"}
BUILTIN_TOOLS = [
    {"name": "now", "description": "지금 날짜·시각·요일 (서버 시간대). 오늘·내일·요일이 필요한 질문에 쓴다.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "weather", "description": "지역의 지금 날씨와 오늘·내일 예보 (기온·강수·날씨). 지역을 말하지 않았으면 서울.",
     "inputSchema": {"type": "object", "properties": {"location": {"type": "string", "description": "도시 이름, 영어로 (예: Seoul, Busan, Jeju, Tokyo)"}}}},
    {"name": "fetch_url", "description": "공개 웹 페이지(http/https)를 읽어 본문 글자를 돌려준다. 사용자가 준 주소나 확인이 필요한 페이지에.",
     "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}},
]


def _get_json(url, timeout=15):
    req = Request(url, headers={"User-Agent": "BookOasisAssistant/3D-library"})
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _tool_now(args):
    t = time.localtime()
    days = "월화수목금토일"
    return time.strftime("%Y-%m-%d %H:%M", t) + " (%s요일, %s)" % (days[t.tm_wday], time.strftime("%Z", t) or "서버 시간")


_KO_CITY = {"서울": "Seoul", "부산": "Busan", "인천": "Incheon", "대구": "Daegu", "대전": "Daejeon", "광주": "Gwangju", "울산": "Ulsan",
            "세종": "Sejong", "수원": "Suwon", "성남": "Seongnam", "고양": "Goyang", "용인": "Yongin", "부천": "Bucheon", "안산": "Ansan",
            "안양": "Anyang", "남양주": "Namyangju", "화성": "Hwaseong", "평택": "Pyeongtaek", "의정부": "Uijeongbu", "파주": "Paju",
            "김포": "Gimpo", "청주": "Cheongju", "천안": "Cheonan", "전주": "Jeonju", "포항": "Pohang", "창원": "Changwon", "김해": "Gimhae",
            "제주": "Jeju", "서귀포": "Seogwipo", "춘천": "Chuncheon", "원주": "Wonju", "강릉": "Gangneung", "속초": "Sokcho", "여수": "Yeosu",
            "순천": "Suncheon", "목포": "Mokpo", "경주": "Gyeongju", "구미": "Gumi", "진주": "Jinju", "거제": "Geoje", "안동": "Andong",
            "도쿄": "Tokyo", "오사카": "Osaka", "뉴욕": "New York", "런던": "London", "파리": "Paris", "베이징": "Beijing", "상하이": "Shanghai"}


def _tool_weather(args):
    loc = str(args.get("location") or "Seoul").strip()[:60]
    name = re.sub(r"(특별자치시|특별자치도|특별시|광역시|시|군|구)$", "", loc) if re.search(r"[가-힣]", loc) else loc
    tries = [_KO_CITY.get(name), loc, name]
    geo = {}
    for q in [t for t in tries if t]:   # 지명 검색은 한글을 잘 못 찾아 영어 이름을 먼저
        geo = _get_json("https://geocoding-api.open-meteo.com/v1/search?count=1&language=ko&name=" + quote(q))
        if geo.get("results"):
            break
    if not geo.get("results"):
        return "'%s' 위치를 찾지 못했습니다. 영어 도시 이름으로 다시 찾아보세요." % loc
    g = geo["results"][0]
    w = _get_json("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s&timezone=auto&forecast_days=2"
                  "&current=temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weather_code,wind_speed_10m"
                  "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max" % (g["latitude"], g["longitude"]))
    c, d = w.get("current", {}), w.get("daily", {})
    lines = ["%s (%s) 지금: %s, %s°C (체감 %s°C), 습도 %s%%, 바람 %skm/h, 강수 %smm" % (
        g.get("name"), g.get("country", ""), _WMO.get(c.get("weather_code"), c.get("weather_code")), c.get("temperature_2m"),
        c.get("apparent_temperature"), c.get("relative_humidity_2m"), c.get("wind_speed_10m"), c.get("precipitation"))]
    for i, day in enumerate(d.get("time", [])[:2]):
        lines.append("%s %s: %s, 최저 %s°C / 최고 %s°C, 비 올 확률 %s%%" % (
            "오늘" if i == 0 else "내일", day, _WMO.get(d["weather_code"][i], d["weather_code"][i]),
            d["temperature_2m_min"][i], d["temperature_2m_max"][i], d["precipitation_probability_max"][i]))
    return "\n".join(lines) + "\n(출처: Open-Meteo)"


def _public_host(host):
    """사설·내부 주소로는 가지 않는다"""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return True   # 여기서 이름을 못 풀면(프록시 환경 등) 요청에 맡긴다 - 사설 주소로 풀리는 것만 막는다
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    return True


def _tool_fetch(args):
    url = str(args.get("url") or "").strip()
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        return "http(s) 주소만 읽을 수 있습니다."
    if not _public_host(u.hostname):
        return "내부·사설 주소는 읽지 않습니다."
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (BookOasisAssistant)", "Accept-Language": "ko,en;q=0.8"})
    with urlopen(req, timeout=20) as r:
        raw = r.read(2_000_000).decode(r.headers.get_content_charset() or "utf-8", "replace")
    raw = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", raw)
    title = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw)
    text = re.sub(r"(?s)<[^>]+>", " ", raw)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    return _clip(("제목: " + re.sub(r"\s+", " ", title.group(1)).strip() + "\n" if title else "") + text[:20000])


class BuiltinTools:
    name = "기본 도구"

    def list_tools(self):
        return list(BUILTIN_TOOLS)

    def call(self, name, args):
        fn = {"now": _tool_now, "weather": _tool_weather, "fetch_url": _tool_fetch}.get(name)
        if not fn:
            return "없는 도구: " + name, True
        try:
            return fn(args or {}), False
        except (URLError, OSError, ValueError, KeyError) as error:
            return "도구 실행 실패: %s" % error, True

    def stop(self):
        pass


# ── 연결 목록: BookOasis(읽기 전용) + 추가 MCP(LIB3D_MCP_SERVERS, 한 줄에 '이름 = 명령 또는 URL') + 기본 도구 ──
_CLIENTS = {"sig": None, "list": []}
_CLIENTS_LOCK = threading.Lock()


def _extra_servers():
    out = []
    for ln in (config.env("LIB3D_MCP_SERVERS") or "").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#") or "=" not in ln:
            continue
        name, target = ln.split("=", 1)
        name = re.sub(r"[^A-Za-z0-9_-]", "_", name.strip())[:20] or "mcp"
        out.append((name, target.strip()))
    return out


def _clients():
    sig = (config.env("LIB3D_MCP_COMMAND"), config.env("LIB3D_MCP_SERVERS"), builtin_on())
    with _CLIENTS_LOCK:
        if _CLIENTS["sig"] != sig:
            for c in _CLIENTS["list"]:
                c.stop()
            lst = []
            if sig[0]:
                lst.append(McpClient("bookoasis", sig[0], READ_ONLY_TOOLS))
            for name, target in _extra_servers():
                if target.startswith(("http://", "https://")):
                    lst.append(HttpMcpClient(name, target))
                else:
                    lst.append(McpClient(name, target))
            if sig[2]:
                lst.append(BuiltinTools())
            _CLIENTS.update(sig=sig, list=lst)
        return list(_CLIENTS["list"])


def stop_all():
    with _CLIENTS_LOCK:
        for c in _CLIENTS["list"]:
            c.stop()
        _CLIENTS.update(sig=None, list=[])


def _tool_table():
    """[(모델에 보이는 이름, 도구 정의, 연결, 원래 이름)], [연결 못 한 이유] - BookOasis·기본 도구는 이름 그대로, 추가 MCP는 '이름__도구'"""
    rows, warns, seen = [], [], set()
    for c in _clients():
        try:
            tools = c.list_tools()
        except Exception as error:  # noqa: BLE001 - 하나가 안 돼도 나머지로 답한다
            warns.append("%s: %s" % (c.name, error))
            continue
        for t in tools:
            real = t.get("name") or ""
            shown = real if c.name in ("bookoasis", "기본 도구") else re.sub(r"[^A-Za-z0-9_-]", "_", c.name + "__" + real)[:64]
            if shown in seen:
                continue
            seen.add(shown)
            rows.append((shown, t, c, real))
    return rows, warns


def test_mcp():
    rows, warns = _tool_table()
    by = {}
    for shown, t, c, real in rows:
        by.setdefault(c.name, []).append(real)
    return {"servers": [{"name": k, "tools": v} for k, v in by.items()], "errors": warns,
            "tools": [r[0] for r in rows]}


def _run_tool(table, name, args):
    for shown, t, c, real in table:
        if shown == name:
            try:
                return c.call(real, args if isinstance(args, dict) else {})
            except Exception as error:  # noqa: BLE001 - 도구 실패는 모델에게 알려 다른 길을 찾게 한다
                return "도구 실행 실패: %s" % error, True
    return "없는 도구: %s" % name, True


_ASK_SYSTEM = (
    "너는 BookOasis 개인 서재(만화·소설·오디오북·영상)의 안내 데스크 직원이다. 사용자는 이 서재의 관리자다. "
    "서재 이야기뿐 아니라 일상적인 질문(날씨·시각·일반 상식·웹 페이지 내용 등)에도 친절하게 답한다.\n"
    "- 서재 내용에 대한 질문은 BookOasis 도구로 실제 데이터를 확인한 뒤 답한다. db_type은 general(일반)·adult(성인)·audiobook(오디오북)이며 "
    "모호하면 general부터 본다.\n"
    "- 날씨는 weather, 날짜·요일·시각은 now, 주어진 주소의 내용은 fetch_url 도구로 확인한다. 다른 도구가 있으면 알맞게 쓴다.\n"
    "- 도구로 확인하지 못한 것은 추측이라고 밝힌다. 최신 정보가 필요한데 도구가 없으면 모른다고 말한다.\n"
    "- 답은 한국어로 짧고 분명하게. 목록은 많아야 10개까지 보여 주고 나머지는 개수만 알려 준다.")


def ask(question, history=None):
    """{"answer", "tools": [쓴 도구 이름…], "warnings": [연결 못 한 MCP]} - history는 [{"q", "a"}] (화면이 기억하는 지난 문답)"""
    if not flags()["ask"]:
        raise ValueError("질문하기가 꺼져 있습니다 (3D 서재 설정 > AI).")
    question = str(question or "").strip()[:2000]
    if not question:
        raise ValueError("질문을 적어 주세요.")
    table, warns = _tool_table()
    out = (_ask_anthropic if provider() == "anthropic" else _ask_openai)(question, history, table)
    if warns:
        out["warnings"] = warns
    return out


def _history(history):
    msgs = []
    for h in (history or [])[-6:]:
        if isinstance(h, dict) and h.get("q") and h.get("a"):
            msgs += [{"role": "user", "content": str(h["q"])[:2000]}, {"role": "assistant", "content": str(h["a"])[:4000]}]
    return msgs


def _ask_anthropic(question, history, table):
    tools = [{"name": shown, "description": (t.get("description") or "")[:1024],
              "input_schema": t.get("inputSchema") or {"type": "object", "properties": {}}} for shown, t, c, real in table]
    messages = _history(history) + [{"role": "user", "content": question}]
    used = []
    for _ in range(ASK_MAX_STEPS):
        kw = dict(max_tokens=16000, system=_ASK_SYSTEM, output_config={"effort": "medium"}, messages=messages)
        if tools:
            kw["tools"] = tools
        resp = _create(**kw)
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
            text, is_err = _run_tool(table, b.name, b.input)
            results.append({"type": "tool_result", "tool_use_id": b.id, "content": text, "is_error": is_err})
        messages.append({"role": "user", "content": results})
    return {"answer": "도구를 너무 여러 번 써서 멈췄습니다. 질문을 좁혀 다시 물어 주세요.", "tools": used}


def _ask_openai(question, history, table):
    """OpenAI 호환 도구 호출(tools/tool_calls)"""
    tools = [{"type": "function", "function": {
        "name": shown, "description": (t.get("description") or "")[:1024],
        "parameters": _oa_schema(t.get("inputSchema") or {"type": "object", "properties": {}})}} for shown, t, c, real in table]
    messages = [{"role": "system", "content": _ASK_SYSTEM}] + _history(history) + [{"role": "user", "content": question}]
    used = []
    for _ in range(ASK_MAX_STEPS):
        payload = {"model": model(), "messages": messages, "max_tokens": 4000}
        if tools:
            payload["tools"] = tools
        msg, finish = _oa_message(_oa_post(payload))
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
            except ValueError:
                args = {}
            text, is_err = _run_tool(table, name, args)
            messages.append({"role": "tool", "tool_call_id": c.get("id") or name, "content": ("[오류] " if is_err else "") + text})
    return {"answer": "도구를 너무 여러 번 써서 멈췄습니다. 질문을 좁혀 다시 물어 주세요.", "tools": used}
