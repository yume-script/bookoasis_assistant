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
import time

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
            ("wtm_title_report", "작품 하나의 다운로드 현황과 앞으로의 일정 보고서 (카카오·네이버에 요청하지 않음, 저장된 정보로 계산). "
                                 "연재 요일·완결 여부, 마지막으로 받은 회차와 결과, 다음 자동 확인(전체 실행) 시각들, "
                                 "기다무 주기와 계정별 다음 대여권 사용 시각·대기 순번, 최근 다운로드 이력과 로그. "
                                 "'○○ 몇 화까지 받았어?', '새 회차 언제 받아?', '왜 안 받아져?' 같은 질문에 쓴다. "
                                 "query는 작품 이름 일부 또는 작품 번호(titleId). 이름이 겹치면 구독 중인 것을 먼저 본다.",
             _schema({"query": {"type": "string"}, "days": {"type": "integer", "minimum": 1, "maximum": 14, "default": 3}},
                     ["query"]), READ),
            ("wtm_forecast", "앞으로 며칠 동안 날마다 받을 회차 수·용량 예측과 최근 날짜별 받은 양 (네이버웹툰/카카오웹툰/카카오웹소설).",
             _schema({"days": {"type": "integer", "minimum": 1, "maximum": 90, "default": 14}}), READ),
            ("wtm_set_subscription", "작품 구독 상태 바꾸기.",
             _schema({"titleId": {"type": "string"}, "platform": platform,
                      "state": {"type": "string", "enum": ["subscribe", "unsubscribe", "exclude", "restore"]}},
                     ["titleId", "state"]), WRITE),
            ("wtm_download_title", "구독 중인 작품 하나의 새 회차를 지금 받는다.",
             _schema({"titleId": {"type": "string"}, "platform": platform}, ["titleId"]), WRITE),
            ("wtm_settings", "웹툰 다운로더 설정 전체 (자동 실행 crontab, 동시 작품 수·이미지 동시 수·회차 간 대기, 고속 모드, 기다무·하루 계획표, "
                             "카카오·웹소설 켜기 등): 칸마다 key·이름·종류·현재 값·설명과 다음 자동 실행 시각. 비밀값(쿠키)은 값 없이, "
                             "locked=true인 칸(경로·쿠키·알림)은 wtm_set_settings로 바꿀 수 없다.", _schema(), READ),
            ("wtm_set_settings", "웹툰 다운로더 설정 바꾸기 (화면의 설정 저장과 같음, 작업 프로세스에 바로 반영). "
                                 "values는 {key: 값} - wtm_settings의 key, locked가 아닌 칸만. 바뀐 칸의 전·후 값을 돌려준다.",
             _schema({"values": {"type": "object", "description": "예: {\"SCHEDULE_CRON\": \"0 */2 * * *\", \"PARALLEL_TITLES\": 3}"}},
                     ["values"]), WRITE),
            ("wtm_run", "웹툰 다운로더 작업 실행·취소: scan_now(요일별 스캔), run_full_cycle_now(전체 실행), "
                        "scan_finished_now(완결 목록 수집), cancel_job(진행 중인 작업 취소).",
             _schema({"job": {"type": "string", "enum": ["scan_now", "run_full_cycle_now", "scan_finished_now", "cancel_job"]}},
                     ["job"]), WRITE),
        ]
    if mods.get("tgup"):
        tools += [
            ("tgup_settings", "텔레그램 자동 올리기 설정: 확인 주기(interval 분)·올리는 시간대(hours \"1-7\", 비우면 언제나)·동시 인코딩 수"
                              "(encode_slots)·한도(max_gb)·인코더·제외 정규식, 규칙들(id·켜짐·종류·폴더/Plex·채널·화질·자막 기다리기 분·"
                              "자막 입히기·같이 올릴 계정·음악 규칙의 이미 있는 곡 올리기).", _schema(), READ),
            ("tgup_set_settings", "텔레그램 자동 올리기 설정 바꾸기 (화면의 규칙 저장과 같음). settings: 바꿀 공통 칸 "
                                  "{interval, hours, encode_slots, max_gb, encoder, cpu_preset, exclude}, rules: [{id, 바꿀 칸…}] "
                                  "(enabled, height 0/480/720/1080, wait_subs, wait_min, burn_subs, caption, tg_alt, upload_existing), "
                                  "add_rules: [새 규칙 - kind folder/music/plex, folder 또는 plex+section, tg, channel …]. "
                                  "규칙을 지우지는 않는다 (끄려면 enabled=false).",
             _schema({"settings": {"type": "object"}, "rules": {"type": "array", "items": {"type": "object"}},
                      "add_rules": {"type": "array", "items": {"type": "object"}}}), WRITE),
            ("tgup_youtube", "유튜브 영상·재생목록 링크를 받아서 텔레그램 채널에 올리기 (유튜브 규칙의 진행 목록 끝에 넣는다 - 받기·올리기는 뒤에서, "
                             "진행은 tgup_status). rule: 유튜브 규칙 id 또는 채널 이름 (유튜브 규칙이 하나면 생략). again: 이미 올린 영상도 다시.",
             _schema({"urls": {"type": "string", "description": "유튜브 주소들 (줄·빈칸으로 여러 개, 재생목록이면 안의 영상 모두)"},
                      "rule": {"type": "string"}, "again": {"type": "boolean", "default": False}}, ["urls"]), WRITE),
            ("tgup_status", "텔레그램 자동 올리기 현황: 계정마다 지금 올리는 것(단계·진행률·걸린 시간), 진행 목록(대기열 - 순서·제목·채널·계정), "
                            "자막 기다림, 다시 시도 대기, 끊긴 드라이브, 최근 기록(올림·건너뜀·실패와 까닭). "
                            "'텔레그램 올리기 뭐 하고 있어?', '대기열 몇 개야?', '○○ 올라갔어?' 같은 질문에 쓴다.",
             _schema({"limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 30,
                                "description": "진행 목록·최근 기록을 몇 개까지"}}), READ),
        ]
    return tools


# 에이전트(MCP)로 바꾸지 않는 웹툰 다운로더 칸: 경로·쿠키·알림·업로드 대상 (사람이 화면에서)
_WTM_LOCKED_RE = __import__("re").compile(r"ROOT|COOKIE|COMPARE_|NOTIFY|DISCORD_|TELEGRAM_UPLOAD_|_LIBRARY_|WEBHOOK|TOKEN")


def _wtm_locked(key, ftype):
    return ftype in ("password", "library", "hidden") or bool(_WTM_LOCKED_RE.search(key))


def wtm_settings():
    from wtm import service as wtm_service
    res = _check(wtm_service.action("get_settings", {}))
    data = json.loads(res.get("message") or "{}")
    values = data.get("values") or {}
    fields = []
    for g in data.get("groups") or []:
        for f in g.get("fields") or []:
            if f.get("type") == "heading":
                continue
            locked = _wtm_locked(f["key"], f.get("type"))
            row = {"key": f["key"], "label": f.get("label") or "", "type": f.get("type") or "text", "section": g.get("title") or g.get("label") or ""}
            if f.get("type") == "password":
                row["set"] = bool((data.get("secret_set") or {}).get(f["key"]))
            else:
                row["value"] = values.get(f["key"])
            if f.get("options"):
                row["options"] = [o[0] if isinstance(o, (list, tuple)) else o for o in f["options"]]
            if f.get("hint"):
                row["hint"] = str(f["hint"])[:220]
            if f.get("requires"):
                row["requires"] = f["requires"]   # 이 체크 칸이 켜져 있어야 쓰이는 칸
            if locked:
                row["locked"] = True
            fields.append(row)
    return {"next_runs": data.get("next_runs"), "fields": fields}


def wtm_set_settings(values):
    from wtm import service as wtm_service
    if not isinstance(values, dict) or not values:
        raise ToolError("values({key: 값})가 필요합니다.")
    cur = {f["key"]: f for f in wtm_settings()["fields"]}
    bad = [k for k in values if k not in cur]
    if bad:
        raise ToolError("없는 설정: " + ", ".join(bad))
    locked = [k for k in values if cur[k].get("locked")]
    if locked:
        raise ToolError("이 칸은 화면에서 사람이 바꿉니다 (경로·쿠키·알림): " + ", ".join(locked))
    res = wtm_service.action("save_settings", {"values": values})
    if not res.get("success"):
        raise ToolError(res.get("error") or res.get("message") or "저장 실패")
    after = {f["key"]: f.get("value") for f in wtm_settings()["fields"]}
    return {"message": res.get("message") or "저장했습니다.",
            "changed": {k: {"before": cur[k].get("value"), "after": after.get(k)} for k in values if cur[k].get("value") != after.get(k)}}


_TGUP_GLOBAL = ("interval", "hours", "encode_slots", "max_gb", "encoder", "cpu_preset", "exclude")
_TGUP_RULE = ("enabled", "height", "wait_subs", "wait_min", "burn_subs", "caption", "tg_alt", "upload_existing")


def tgup_settings():
    from tgup import plex_to_tg
    return plex_to_tg.load_settings()


def tgup_youtube(urls, rule="", again=False):
    """tgup_youtube 도구: 유튜브 규칙 고르기 (id·채널 이름, 하나면 그것) -> Mirror.add_youtube"""
    from tgup import plex_to_tg
    from tgup import service as tgup_service
    rules = [r for r in plex_to_tg.load_settings()["rules"] if r.get("media") == "youtube"]
    if not rules:
        raise ToolError("유튜브 규칙이 없습니다 - BOA 텔레그램 자동 올리기 > 규칙에서 종류 '유튜브 링크'로 채널을 정해 주세요.")
    want = str(rule or "").strip()
    if want:
        pick = [r for r in rules if r["id"] == want] or [r for r in rules if want.casefold() in (r["channel_title"] or "").casefold()]
    else:
        pick = rules if len(rules) == 1 else []
    if len(pick) != 1:
        raise ToolError("유튜브 규칙을 골라 주세요 (rule): " + ", ".join(f"{r['id']}={r['channel_title'] or r['channel']}" for r in rules))
    r = pick[0]
    if not tgup_service.RUNNER.loop:
        raise ToolError("텔레그램 자동 올리기가 꺼져 있습니다.")
    try:
        n, dup = tgup_service.RUNNER.call(tgup_service.RUNNER.mirror.add_youtube(r["id"], str(urls or ""), bool(again)), 180)
    except (ValueError, RuntimeError) as e:
        raise ToolError(str(e))
    return {"queued": n, "already_queued": dup, "rule": r["id"], "channel": r["channel_title"] or r["channel"],
            "enabled": r["enabled"], "note": "진행 목록 끝에 넣었습니다 - 진행은 tgup_status" + ("" if r["enabled"] else " (이 규칙은 꺼져 있음)")}


def tgup_set_settings(settings=None, rules=None, add_rules=None):
    from tgup import compat, plex_to_tg
    from tgup import service as tgup_service
    st = plex_to_tg.load_settings()
    before = json.loads(json.dumps(st))
    for k, v in (settings or {}).items():
        if k not in _TGUP_GLOBAL:
            raise ToolError(f"바꿀 수 없는 공통 칸: {k} (가능: {', '.join(_TGUP_GLOBAL)})")
        st[k] = v
    if "max_gb" in (settings or {}):
        st["max_gb_v"] = 1
    by_id = {r["id"]: r for r in st["rules"]}
    for patch in rules or []:
        r = by_id.get(str((patch or {}).get("id") or ""))
        if not r:
            raise ToolError(f"없는 규칙: {(patch or {}).get('id')}")
        for k, v in patch.items():
            if k == "id":
                continue
            if k not in _TGUP_RULE:
                raise ToolError(f"규칙에서 바꿀 수 없는 칸: {k} (가능: {', '.join(_TGUP_RULE)})")
            r[k] = v
    for new in add_rules or []:
        if not isinstance(new, dict):
            raise ToolError("add_rules의 항목은 객체여야 합니다.")
        st["rules"].append({k: v for k, v in new.items() if k != "id"})
    for r in st["rules"]:   # (clean_settings는 화면 형식 - 음악 규칙은 kind music으로)
        if r.get("media") == "music":
            r["kind"] = "music"
    try:
        clean = plex_to_tg.clean_settings(st)
    except ValueError as e:
        raise ToolError(str(e))
    data = compat.load()
    data["plex_to_tg"] = clean
    compat.save(data)
    runner = tgup_service.RUNNER
    if runner.loop and runner.mirror:
        runner.run(runner.mirror.wake)
    changed = {k: {"before": before.get(k), "after": clean.get(k)} for k in _TGUP_GLOBAL if before.get(k) != clean.get(k)}
    old_rules = {r["id"]: r for r in before["rules"]}
    for r in clean["rules"]:
        o = old_rules.get(r["id"])
        if o is None:
            changed[f"rule {r['id']}"] = {"added": {k: r.get(k) for k in ("kind", "media", "folder", "section_title", "channel_title")}}
            continue
        diff = {k: {"before": o.get(k), "after": r.get(k)} for k in _TGUP_RULE if o.get(k) != r.get(k)}
        if diff:
            changed[f"rule {r['id']} ({r.get('section_title') or r.get('folder')})"] = diff
    return {"message": "저장했습니다.", "changed": changed}


def tgup_status(limit=30):
    """tgup_status 도구: 자동 올리기 상태(Mirror.status)를 사람이 읽기 좋게 줄인 것"""
    from tgup import service as tgup_service
    from tgup import plex_to_tg
    runner = tgup_service.RUNNER
    if not runner.loop or not runner.mirror:
        raise ToolError("텔레그램 자동 올리기가 돌고 있지 않습니다 (aiohttp·telethon 설치, TGUP_ENABLED).")
    st = runner.run(runner.mirror.status)
    rules = {r["id"]: r for r in plex_to_tg.load_settings()["rules"]}
    chan = lambda rid: (rules.get(rid) or {}).get("channel_title") or (rules.get(rid) or {}).get("channel") or ""  # noqa: E731
    names = {}
    try:
        from tgup import tgaccount
        # (전화번호는 내보내지 않는다 - 붙인 이름, 없으면 "첫 계정"/"계정 N")
        names = {a["id"]: a.get("name") or ("첫 계정" if a["id"] == tgaccount.ACCOUNT_ID else f"계정 {a['id'][2:]}")
                 for a in tgaccount.accounts()}
    except Exception:  # noqa: BLE001 - 계정 이름을 못 읽으면 id로
        pass
    now = time.time()
    ago = lambda t: int((now - t) // 60) if t else None  # noqa: E731
    running = []
    for ln in st.get("lanes") or []:
        cur = ln.get("current")
        if not cur:
            continue
        total, done = int(cur.get("total") or 0), int(cur.get("done") or 0)
        running.append({"account": names.get(ln["tg"], ln["tg"]), "title": cur.get("title", ""), "phase": cur.get("phase", ""),
                        "percent": round(done * 100 / total, 1) if total else None, "elapsed_min": round((cur.get("elapsed") or 0) / 60, 1),
                        "channel": chan(cur.get("rule")), "subs": cur.get("subs") or ""})
    queue = [q for q in st.get("queue") or [] if not q.get("running")]
    return {
        "running": running,
        "queue_total": len(queue),
        "queue": [{"pos": n + 1, "title": q["title"], "channel": chan(q["rule"]), "account": names.get(q["tg"], q["tg"]),
                   **({"pinned": True} if q.get("pin") else {})} for n, q in enumerate(queue[:limit])],
        "waiting_subs": [{"title": w["title"], "why": w.get("why") or "", "waiting_min": ago(w.get("since"))} for w in st.get("waiting") or []],
        "retry": [{"title": r["title"], "tries": r.get("tries", 0), "in_min": max(0, int((r.get("at", 0) - now) // 60))}
                  for r in st.get("retry") or []],
        "offline_drives": [{"drive": o["drive"], "since_min": ago(o.get("since"))} for o in st.get("offline") or []],
        "off_hours": bool(st.get("off_hours")), "skipped_total": st.get("skipped", 0), "error": st.get("error") or "",
        "accounts": {names.get(k, k): {"queued": a.get("queued", 0), "ok": a.get("ok", 0), "fail": a.get("fail", 0),
                                       **({"down": True} if a.get("down") else {}),
                                       # 텔레그램 업로드 속도: state ok/slow(느림 의심)/limited(텔레그램이 늦춤), MB/s, 최근 1시간 대기
                                       **({"upload": {x: (a.get("throttle") or {}).get(x) for x in
                                                      ("state", "speed", "baseline", "waits_1h", "wait_sec_1h", "premium_limit")}}
                                          if a.get("throttle") else {})}
                     for k, a in (st.get("accounts") or {}).items()},
        "throttle_warnings": [f"{names.get(k, k)}: {(a.get('throttle') or {}).get('note')}" for k, a in (st.get("accounts") or {}).items()
                              if (a.get("throttle") or {}).get("state") not in (None, "ok")],
        "recent": [{"title": h.get("title", ""), "result": "올림" if h.get("ok") else (h.get("note") or "실패").split(" - ")[0][:30],
                    "note": (h.get("note") or "")[:160], "ago_min": ago(h.get("at")), "subs": h.get("subs") or ""}
                   for h in (st.get("history") or [])[:min(limit, 20)]],
    }


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
    if name == "tgup_status":
        return tgup_status(min(200, max(1, int(args.get("limit") or 30))))
    if name == "tgup_settings":
        return tgup_settings()
    if name == "tgup_youtube":
        return tgup_youtube(args.get("urls"), args.get("rule") or "", bool(args.get("again")))
    if name == "tgup_set_settings":
        return tgup_set_settings(args.get("settings"), args.get("rules"), args.get("add_rules"))
    if name == "wtm_settings":
        return wtm_settings()
    if name == "wtm_set_settings":
        return wtm_set_settings(args.get("values"))
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
        if name == "wtm_title_report":   # python3 -m wtm.explain 과 같은 내용
            from wtm import explain
            query = str(args.get("query") or "").strip()
            if not query:
                raise ToolError("query(작품 이름 또는 번호)가 필요합니다.")
            lines = []
            explain.explain(query, days=min(14, max(1, int(args.get("days") or 3))), out=lines.append)
            return "\n".join(str(x) for x in lines)
        if name == "wtm_forecast":       # python3 -m wtm.download_stats --forecast 와 같은 내용 + 최근 기록
            import contextlib
            import io
            from wtm import download_stats
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                print("■ 최근 7일 받은 양")
                download_stats._print(download_stats.load(7))
                print()
                download_stats._print_forecast(min(90, max(1, int(args.get("days") or 14))))
            return buf.getvalue()
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
            "serverInfo": {"name": "bookoasis_assistant", "title": "BookOasisAssistant", "version": version},
            "instructions": ("BookOasisAssistant(BookOasis 보조 프로그램): Google Drive 변경 감시(BookOasis 부분 스캔)와 웹툰 다운로더. "
                             "gdw_status로 감시 현황을, wtm_status로 다운로더 현황을, tgup_status로 텔레그램 자동 올리기를 먼저 보세요. 경로는 이 프로그램 기준 절대 경로입니다.")}}
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
        if not is_error and name not in ("gdw_status", "gdw_events", "gdw_log", "gdw_schedules", "wtm_status", "wtm_titles", "tgup_status",
                                         "tgup_settings", "wtm_settings",
                                         "wtm_history", "wtm_title_report", "wtm_forecast"):
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
