# -*- coding: utf-8 -*-
"""
쿠키 자동 갱신(keep-alive)
--------------------------
다운로드 작업이 돌든 안 돌든, 정해진 간격(기본 6시간)마다 로그인 쿠키를 살려 둔다.

- 카카오페이지: /api/refresh_token 으로 로그인 토큰을 연장하고, 새로 받은 쿠키를
  kakao_cookie_state.json에 저장한다(다음 요청부터 그 쿠키를 씀). 이어서 프로필 API로
  실제로 로그인돼 있는지 확인한다.
- 네이버: 토큰 연장 API가 없어서, 로그인된 쿠키로 네이버 계정 페이지를 열어 세션을
  살려 두고 네이버가 새로 내려준 쿠키를 naver_cookie_state.json에 저장한다.

로그인이 풀린 게 확인되면(쿠키 만료) 디스코드로 한 번만 알린다. 같은 쿠키로는 다시
알리지 않고, 설정에 새 쿠키를 넣으면 알림 기록도 초기화된다.

아이디/비밀번호 자동 로그인은 하지 않는다(캡차·2단계 인증·새 기기 로그인 알림 때문에
불안정하고 계정 보안 문제가 생길 수 있음).
"""
import time

from . import state_store as ss

import os

STATE_PATH = os.path.join(ss.DATA_DIR, "cookie_keeper.json")
DEFAULT_INTERVAL_HOURS = 6


def _hours(cfg):
    try:
        h = float(cfg.get("COOKIE_KEEPALIVE_HOURS", DEFAULT_INTERVAL_HOURS))
    except (TypeError, ValueError):
        h = DEFAULT_INTERVAL_HOURS
    return h


def load_state():
    return ss.read_json(STATE_PATH, {})


def _save(platform, patch):
    with ss._lock:
        st = load_state()
        cur = st.get(platform) or {}
        cur.update(patch)
        st[platform] = cur
        ss.write_json(STATE_PATH, st)


NAVER_KEEP_LOGIN_MINUTES = 30


def _truthy(v, default=True):
    if v is None or v == "":
        return default
    return v if isinstance(v, bool) else str(v).strip().lower() in ("1", "true", "on", "yes")


def interval_seconds(cfg, platform):
    """플랫폼별 갱신 간격(초). 0이면 끔.
    네이버 '로그인 유지'(NAVER_KEEP_LOGIN, 기본 켬)면 30분마다 계정 페이지를 열어 세션을 살려 둔다
    (네이버는 연장 API가 없어 오래 손대지 않으면 NID_SES가 만료돼 로그인이 풀린다)."""
    if platform == "naver" and _truthy(cfg.get("NAVER_KEEP_LOGIN"), True):
        return NAVER_KEEP_LOGIN_MINUTES * 60
    h = _hours(cfg)
    return h * 3600 if h > 0 else 0


def _due_platforms(cfg):
    st, now, out = load_state(), time.time(), []
    for platform in ("naver", "kakao"):
        sec = interval_seconds(cfg, platform)
        if sec <= 0:
            continue
        last = (st.get(platform) or {}).get("last_at") or st.get("last_run_at") or 0
        if now - float(last) >= sec:
            out.append(platform)
    return out


def is_due(cfg):
    return bool(_due_platforms(cfg))


def _alert_once(cfg, platform, src_hash, title, desc, log):
    st = (load_state().get(platform) or {})
    if st.get("alerted_hash") == src_hash:
        return
    try:
        from . import discord_notify
        discord_notify.notify(cfg, title, desc, color=discord_notify.COLOR_WARN)
    except Exception:  # noqa: BLE001
        pass
    _save(platform, {"alerted_hash": src_hash})
    log("%s %s" % (title, desc))


def keep_kakao(cfg, log=print):
    """카카오 계정마다 토큰 연장·로그인 확인. 반환: 계정 1의 로그인 여부 (계정 1 쿠키가 없으면 None)."""
    from . import kakao_pipeline
    if not cfg.get("KAKAO_ENABLE"):
        return None
    result = None
    for n, raw in kakao_pipeline.accounts(cfg):
        ok = _keep_kakao_one(cfg, raw, "kakao" if n == 1 else "kakao_%d" % n,
                             "카카오페이지" if n == 1 else "카카오페이지 계정%d" % n, log)
        if n == 1:
            result = ok
    if result is None:  # 계정 1 쿠키 없이 추가 계정만 있을 때도 갱신 주기는 계정 1 기록으로 센다
        _save("kakao", {"last_at": time.time()})
    return result


def _keep_kakao_one(cfg, raw, state_key, name, log):
    from . import kakao_api, kakao_pipeline
    src = kakao_api._cookie_hash(raw)
    session = kakao_pipeline.build_session_from_cfg(kakao_pipeline.account_cfg(cfg, raw))
    refreshed, logged_in, detail = False, None, ""
    try:
        kakao_api.refresh_token(session, log=log)
        refreshed = bool(getattr(session, "kakao_renewed", False))
    except kakao_api.KakaoAuthExpired as e:
        logged_in, detail = False, str(e)
    if logged_in is None:
        try:
            r = session.post(kakao_api.PROFILE_API, timeout=session.request_timeout)
            body = r.json()
            logged_in = body.get("result_code") in (0, "0")
            if not logged_in:
                detail = "%s (%s)" % (body.get("message") or "", body.get("message_key") or "")
        except Exception as e:  # noqa: BLE001
            detail = "로그인 확인 실패(네트워크?): %s" % e
    if logged_in:
        kakao_api.save_session_cookies(session)
    _save(state_key, {"last_at": time.time(), "ok": logged_in, "refreshed": refreshed,
                      "detail": detail, "source_hash": src})
    if logged_in is False:
        _alert_once(cfg, state_key, src, "🍪 %s 쿠키 만료" % name,
                    "로그인이 풀렸습니다(%s). [설정] > 카카오웹툰에서 이 계정의 쿠키를 새로 넣어주세요. "
                    "그 전까지는 이 계정으로 유료 회차를 받지 않습니다." % (detail or "자동 연장 실패"), log)
    elif logged_in:
        log("%s 쿠키 자동 갱신 완료%s" % (name, ("" if refreshed else "(연장 응답 없음, 로그인은 유지 중)")))
    return logged_in


def keep_naver(cfg, log=print):
    from . import naver_api, pipeline
    raw = (cfg.get("NAVER_COOKIE_JSON") or "").strip()
    if not raw:
        return None
    src = naver_api.cookie_hash(raw)
    session = pipeline.build_session_from_cfg(cfg)
    logged_in = naver_api.check_login(session)
    if logged_in:
        naver_api.save_session_cookies(session)
    _save("naver", {"last_at": time.time(), "ok": logged_in, "source_hash": src})
    if logged_in is False:
        _alert_once(cfg, "naver", src, "🍪 네이버 쿠키 만료",
                    "로그인이 풀렸습니다. [설정] > 네이버에서 쿠키(JSON)를 새로 넣어주세요. "
                    "그 전까지는 성인 작품/소장 유료 회차를 받지 못합니다.", log)
    elif logged_in:
        log("네이버 쿠키 자동 갱신 완료(로그인 유지 중)")
    return logged_in


def run(cfg, log=print, platforms=None):
    """platforms를 주지 않으면 지금 갱신할 차례인 플랫폼만."""
    due = list(platforms) if platforms else _due_platforms(cfg)
    with ss._lock:
        st = load_state()
        st["last_run_at"] = time.time()
        for name in due:  # 쿠키가 없어 건너뛰어도 다음 차례까지는 다시 보지 않게
            cur = st.get(name) or {}
            cur["last_at"] = time.time()
            st[name] = cur
        ss.write_json(STATE_PATH, st)
    out = {}
    for name, fn in (("naver", keep_naver), ("kakao", keep_kakao)):
        if name not in due:
            continue
        try:
            out[name] = fn(cfg, log=log)
        except Exception as e:  # noqa: BLE001
            log("쿠키 자동 갱신(%s) 오류(무시): %s" % (name, e))
            out[name] = None
    return out
