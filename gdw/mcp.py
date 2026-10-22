# -*- coding: utf-8 -*-
"""MCP 서버 (Model Context Protocol, Streamable HTTP)

Claude Code·Claude Desktop 같은 MCP 클라이언트가 이 프로그램의 상태를 묻고 몇 가지 동작을 시킬 수 있게 한다.
  POST /mcp   JSON-RPC 2.0 (요청 하나 또는 묶음) → JSON 응답. 세션·SSE 없이 요청마다 답한다(상태 없는 서버).
  인증: Authorization: Bearer <MCP_TOKEN>. .env의 MCP_TOKEN이 비어 있으면 MCP는 꺼져 있다(404).
  토큰은 관리 화면 설정 > MCP에서 만들고 지운다.

도구는 화면의 버튼과 같은 동작(service.dispatch, wtm.service.action)을 그대로 부른다.
켜진 모듈의 도구만 보인다 (드라이브 변경 감시: gdw_…, 웹툰 다운로더: wtm_…).
"""
import hmac
import json
import logging
import secrets

from . import config, service

log = logging.getLogger("gdw.mcp")
PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
MAX_TEXT = 60000  # 도구 결과 글자 수 상한 (모델 문맥을 너무 쓰지 않게)

READ = {"readOnlyHint": True, "openWorldHint": False}
WRITE = {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False}


def token():
    return (config.env("MCP_TOKEN") or "").strip()


def enabled():
    return bool(token())


def authorized(header):
    expect = token()
    given = str(header or "")
    if not expect or not given.lower().startswith("bearer "):
        return False
    return hmac.compare_digest(given[7:].strip().encode(), expect.encode())


def new_token():
    value = "gdw_" + secrets.token_urlsafe(32)
    config.save_env({"MCP_TOKEN": value})
    return value


def disable():
    config.save_env({"MCP_TOKEN": ""})


# ── 도구 ──
def _schema(props=None, required=None):
    return {"type": "object", "properties": props or {}, "required": required or [], "additionalProperties": False}


def _tools(mods, svc):
    tools = []
    if mods.get("gdw") and svc is not None:
        tools += [
            ("gdw_status", "드라이브 변경 감시 현황: 워커 실행 여부, 대기·반영·실패 건수, 대기 내역(어디서 기다리는지), "
                           "최근 1시간 부하(스캔 평균·최대 시간), 감시 폴더별 상태와 경고.", _schema(), READ),
            ("gdw_events", "변경 기록 목록 (최신순). status로 거르고 q로 경로·메시지를 찾는다.",
             _schema({"status": {"type": "string", "enum": ["pending", "done", "skipped", "failed", "db_missing"],
                                 "description": "pending=대기(파일·BookOasis 대기 포함), failed=실패·시간 초과, db_missing=반영됐지만 DB에 없음"},
                      "q": {"type": "string", "description": "경로·메시지에 들어간 글자"},
                      "root": {"type": "string", "description": "감시 폴더 이름"},
                      "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 30}}), READ),
            ("gdw_log", "워커 로그의 마지막 줄들.", _schema({"lines": {"type": "integer", "minimum": 20, "maximum": 1000, "default": 150}}), READ),
            ("gdw_schedules", "보관함별 전체 스캔(cron) 일정과 감시 폴더 연결.", _schema(), READ),
            ("gdw_request_path", "경로 직접 반영: 그 경로를 감시가 감지한 것처럼 VFS 새로고침 → 파일 확인 → BookOasis 부분 스캔한다.",
             _schema({"path": {"type": "string", "description": "이 프로그램 기준 절대 경로 (BookOasis 보관함 경로와 같음)"},
                      "action": {"type": "string", "enum": ["create", "delete"], "default": "create"}}, ["path"]), WRITE),
            ("gdw_retry", "실패한 기록을 다시 처리한다. ids를 주거나 all_failed=true로 실패 전체.",
             _schema({"ids": {"type": "array", "items": {"type": "integer"}}, "all_failed": {"type": "boolean"}}), WRITE),
            ("gdw_poll_now", "Drive 변경을 지금 바로 확인한다 (다음 확인 주기를 기다리지 않음).", _schema(), WRITE),
            ("gdw_worker", "감시 워커 시작/중지/다시 시작.",
             _schema({"action": {"type": "string", "enum": ["start", "stop", "restart"]}}, ["action"]), WRITE),
        ]
    if mods.get("wtm"):
        platform = {"type": "string", "enum": ["naver", "kakao"], "default": "naver"}
        tools += [
            ("wtm_status", "웹툰 다운로더 현황: 진행 중인 작업, 작품 다운로드 작업, 카카오 대기열, 속도, 최근 로그.", _schema(), READ),
            ("wtm_titles", "작품 목록 (네이버웹툰·카카오웹툰·카카오페이지 웹소설). 이름·작가로 찾고 구독 상태로 거른다.",
             _schema({"query": {"type": "string", "description": "제목·작가에 들어간 글자"},
                      "state": {"type": "string", "enum": ["all", "subscribed", "unsubscribed", "excluded"], "default": "all"},
                      "platform": {"type": "string", "enum": ["all", "naver", "kakao"], "default": "all"},
                      "limit": {"type": "integer", "minimum": 1, "maximum": 300, "default": 50}}), READ),
            ("wtm_history", "다운로드 이력 (최신순).",
             _schema({"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 50}}), READ),
            ("wtm_set_subscription", "작품 구독 상태 바꾸기.",
             _schema({"titleId": {"type": "string"}, "platform": platform,
                      "state": {"type": "string", "enum": ["subscribe", "unsubscribe", "exclude", "restore"]}},
                     ["titleId", "state"]), WRITE),
            ("wtm_download_title", "구독 중인 작품 하나의 새 회차를 지금 받는다.",
             _schema({"titleId": {"type": "string"}, "platform": platform}, ["titleId"]), WRITE),
            ("wtm_run", "웹툰 다운로더 작업 실행·취소: scan_now(요일별 스캔), run_full_cycle_now(전체 실행), "
                        "scan_finished_now(완결 목록 수집), cancel_job(진행 중인 작업 취소).",
             _schema({"job": {"type": "string", "enum": ["scan_now", "run_full_cycle_now", "scan_finished_now", "cancel_job"]}},
                     ["job"]), WRITE),
        ]
    return tools


def _text(data):
    text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, default=str, indent=1)
    if len(text) > MAX_TEXT:
        text = text[:MAX_TEXT] + f"\n… (잘림: 전체 {len(text)}자)"
    return text


def _check(result):
    """화면 동작의 {"success": False, "error"}를 도구 오류로"""
    if isinstance(result, dict) and result.get("success") is False:
        raise ToolError(result.get("error") or "실패")
    return result


class ToolError(Exception):
    pass


_EVENT_KEYS = ("id", "status", "action", "item_type", "root", "path", "removed_path", "created", "finished", "attempts", "message")


def _call(name, args, mods, svc):
    if name.startswith("gdw_"):
        if svc is None:
            raise ToolError("드라이브 변경 감시가 꺼져 있습니다 (GDW_ENABLED).")
        if name == "gdw_status":
            data = _check(svc.dispatch("status", {}))
            data.pop("success", None)
            return data
        if name == "gdw_events":
            limit = min(200, max(1, int(args.get("limit") or 30)))
            ctx = {k: args[k] for k in ("status", "q", "root") if args.get(k)}
            data = _check(svc.dispatch("events", dict(ctx, size=max(10, limit))))
            items = []
            for item in (data.get("items") or [])[:limit]:
                row = {k: item.get(k) for k in _EVENT_KEYS if item.get(k) not in (None, "")}
                result = item.get("result") or {}
                if result.get("db_msg"):
                    row["db"] = result["db_msg"]
                scans = [f"{s.get('dir')} → {'OK' if s.get('ok') else s.get('msg')}" for s in result.get("scans") or []]
                if scans:
                    row["scans"] = scans
                items.append(row)
            return {"total": data.get("total"), "items": items}
        if name == "gdw_log":
            return _check(svc.dispatch("log", {"lines": int(args.get("lines") or 150)})).get("text", "")
        if name == "gdw_schedules":
            data = _check(svc.dispatch("schedules", {}))
            data.pop("success", None)
            return data
        if name == "gdw_request_path":
            return _check(svc.dispatch("manual", {"path": args.get("path"), "action": args.get("action") or "create"})).get("message")
        if name == "gdw_retry":
            if not args.get("ids") and not args.get("all_failed"):
                raise ToolError("ids 또는 all_failed=true가 필요합니다.")
            return _check(svc.dispatch("retry", {"ids": args.get("ids") or [], "all_failed": bool(args.get("all_failed"))})).get("message")
        if name == "gdw_poll_now":
            return _check(svc.dispatch("poll_now", {})).get("message") or "확인을 요청했습니다."
        if name == "gdw_worker":
            action = args.get("action")
            if action not in ("start", "stop", "restart"):
                raise ToolError("action은 start/stop/restart 중 하나입니다.")
            return _check(svc.dispatch(action, {})).get("message") or "요청했습니다."
    if name.startswith("wtm_"):
        if not mods.get("wtm"):
            raise ToolError("웹툰 다운로더가 꺼져 있습니다 (WTM_ENABLED).")
        from wtm import service as wtm_service
        from wtm import state_store as ss
        if name == "wtm_status":
            message = _check(wtm_service.action("poll_status", {})).get("message")
            try:
                return json.loads(message) if isinstance(message, str) else message
            except ValueError:
                return message
        if name == "wtm_titles":
            items = wtm_service.dashboard().get("titles") or []
            query = str(args.get("query") or "").strip().lower()
            state, platform = args.get("state") or "all", args.get("platform") or "all"
            out = []
            for t in items:
                if platform != "all" and t.get("platform") != platform:
                    continue
                if state == "subscribed" and not t.get("subscribed"):
                    continue
                if state in ("unsubscribed", "excluded") and not t.get(state):
                    continue
                if query and query not in f"{t.get('title', '')} {t.get('author', '')}".lower():
                    continue
                out.append({k: t[k] for k in ("titleId", "platform", "title", "author", "status", "weekdays", "subscribed",
                                              "unsubscribed", "excluded", "novel", "last_downloaded_no", "episode_count",
                                              "in_library", "telegram_upload", "last_result") if t.get(k) not in (None, "", [])})
            limit = min(300, max(1, int(args.get("limit") or 50)))
            return {"total": len(out), "items": out[:limit]}
        if name == "wtm_history":
            limit = min(500, max(1, int(args.get("limit") or 50)))
            return ss.load_history(limit=limit, query=(args.get("query") or None))
        payload = {"titleId": str(args.get("titleId") or ""), "platform": args.get("platform") or "naver"}
        known = ss.get_kakao_title(payload["titleId"]) if payload["platform"] == "kakao" else ss.get_title(payload["titleId"])
        if not known:  # 화면 버튼과 달리 아무 ID나 올 수 있으니, 없는 작품이 새로 생기지 않게 먼저 확인
            raise ToolError(f"목록에 없는 작품입니다 ({payload['platform']} {payload['titleId']}). wtm_titles로 titleId를 확인하세요.")
        if name == "wtm_set_subscription":
            if args.get("state") not in ("subscribe", "unsubscribe", "exclude", "restore"):
                raise ToolError("state는 subscribe/unsubscribe/exclude/restore 중 하나입니다.")
            return _check(wtm_service.action(args["state"], payload)).get("message")
        if name == "wtm_download_title":
            return _check(wtm_service.action("download_title", payload)).get("message")
        if name == "wtm_run":
            if args.get("job") not in ("scan_now", "run_full_cycle_now", "scan_finished_now", "cancel_job"):
                raise ToolError("알 수 없는 작업입니다.")
            return _check(wtm_service.action(args["job"], {})).get("message")
    raise ToolError(f"알 수 없는 도구: {name}")


# ── JSON-RPC ──
def _error(rid, code, message):
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def _handle_one(msg, mods, svc, version):
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
        return _error(msg.get("id") if isinstance(msg, dict) else None, -32600, "Invalid Request")
    rid, method, params = msg.get("id"), msg["method"], msg.get("params") or {}
    if "id" not in msg:  # 알림(notifications/initialized 등): 답하지 않는다
        return None
    if method == "initialize":
        asked = str(params.get("protocolVersion") or "")
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "bookoasis_assistant", "title": "BookOasis 보조", "version": version},
            "instructions": ("BookOasis 보조 프로그램: Google Drive 변경 감시(BookOasis 부분 스캔)와 웹툰 다운로더. "
                             "gdw_status로 감시 현황을, wtm_status로 다운로더 현황을 먼저 보세요. 경로는 이 프로그램 기준 절대 경로입니다.")}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": [
            {"name": n, "description": d, "inputSchema": s, "annotations": a} for n, d, s, a in _tools(mods, svc)]}}
    if method == "tools/call":
        name = str(params.get("name") or "")
        args = params.get("arguments") or {}
        if name not in {t[0] for t in _tools(mods, svc)}:
            return _error(rid, -32602, f"알 수 없는 도구: {name}")
        if not isinstance(args, dict):
            return _error(rid, -32602, "arguments는 객체여야 합니다.")
        try:
            result, is_error = _call(name, args, mods, svc), False
        except ToolError as error:
            result, is_error = str(error), True
        except Exception as error:  # 도구 하나의 오류가 서버를 멈추지 않게
            log.exception("MCP 도구 실패: %s", name)
            result, is_error = f"{type(error).__name__}: {error}", True
        if not is_error and name not in ("gdw_status", "gdw_events", "gdw_log", "gdw_schedules", "wtm_status", "wtm_titles", "wtm_history"):
            log.info("MCP 도구 실행: %s %s", name, json.dumps(args, ensure_ascii=False)[:200])
        return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"type": "text", "text": _text(result)}], "isError": is_error}}
    return _error(rid, -32601, f"Method not found: {method}")


def handle(body, mods, svc):
    """반환 (HTTP 코드, 응답 객체 또는 None). 알림만 왔으면 202에 본문 없음."""
    version = service._plugin_version()
    if isinstance(body, list):
        if not body:
            return 400, _error(None, -32600, "Invalid Request")
        replies = [r for r in (_handle_one(m, mods, svc, version) for m in body) if r is not None]
        return (200, replies) if replies else (202, None)
    reply = _handle_one(body, mods, svc, version)
    return (200, reply) if reply is not None else (202, None)
