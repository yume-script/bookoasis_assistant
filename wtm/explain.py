# -*- coding: utf-8 -*-
"""작품 하나가 언제 자동으로 확인·다운로드되는지 계산해 보여 준다 (카카오·네이버에 요청하지 않음).

    python3 -m wtm.explain "천하제일 곤륜객잔"

서버에 저장된 작품 정보(titles.json / kakao_titles.json), 작업 상태(job_state.json), 설정으로
  - 전체 실행(실행 주기마다)에서 이 작품을 확인하는 다음 시각들
  - 기다무 대여권(5분마다 도는 기다무 확인)으로 계정마다 다음에 받을 시각
  - 최근 다운로드 이력과 로그
를 계산한다. 실제 동작과 같은 판정 함수(in_new_episode_scope, _needs_check, waitfree_due_titles)를 쓴다.
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from gdw import config  # noqa: E402

config.load_env()
os.environ.setdefault("WTM_HOST", "1")

WD_NAMES = {"mon": "월", "tue": "화", "wed": "수", "thu": "목", "fri": "금", "sat": "토", "sun": "일",
            "dailyPlus": "매일+"}


def _t(ts):
    if not ts:
        return "-"
    lt = time.localtime(ts)
    return time.strftime("%m-%d", lt) + "(" + "월화수목금토일"[lt.tm_wday] + ") " + time.strftime("%H:%M", lt)


def _period_label(minutes):
    m = int(minutes or 1440)
    return "%d일" % (m // 1440) if m % 1440 == 0 else ("%d시간" % (m // 60) if m % 60 == 0 else "%d분" % m)


def _find(query):
    from wtm import state_store as ss
    q = query.strip().lower()
    hits = []
    for platform, titles in (("kakao", ss.load_kakao_titles()), ("naver", ss.load_titles())):
        for tid, t in titles.items():
            name = str(t.get("title") or "")
            if q == str(tid) or q in name.lower():
                hits.append((platform, str(tid), t))
    hits.sort(key=lambda h: (h[2].get("title", "").lower() != q, not h[2].get("subscribed")))
    return hits


def explain(query, days=3, out=print):
    from wtm import host, kakao_pipeline as kp, pipeline as pl, state_store as ss
    from wtm.webtoon_manager import DEFAULTS
    cfg = dict(DEFAULTS)
    cfg.update({k: v for k, v in host.load_settings().items() if v not in (None, "")})

    hits = _find(query)
    if not hits:
        out("'%s' 작품을 찾지 못했습니다 (작품 목록에 없음 - 전체 목록/구독 화면에서 먼저 추가돼 있어야 합니다)" % query)
        return 1
    if len(hits) > 1:
        out("이름이 겹치는 작품 %d개 - 첫 번째를 봅니다:" % len(hits))
        for p, tid, t in hits[:8]:
            out("  - [%s] %s (%s)%s" % (p, t.get("title"), tid, " · 구독" if t.get("subscribed") else ""))
        out("")
    platform, tid, t = hits[0]
    now = time.time()
    novel = platform == "kakao" and kp._is_novel(t)
    label = "네이버웹툰" if platform == "naver" else ("카카오웹소설" if novel else "카카오웹툰")
    wds = [WD_NAMES.get(w, w) for w in (t.get("weekdays") or [])]
    out("■ %s [%s] %s (%s)" % (t.get("title"), label, t.get("status") or "", tid))
    out("  연재 요일: %s / 구독: %s%s%s" % (
        ",".join(wds) or "없음", "예" if t.get("subscribed") else "아니오",
        " / 제외됨" if t.get("excluded") else "", " / 구독해제" if t.get("unsubscribed") else ""))
    if platform == "kakao":
        out("  기다무: %s / 잠긴 회차 남음: %s" % (
            (_period_label(t.get("waitfree_period_min")) + " 기다무") if t.get("waitfree") else "아님",
            "예" if t.get("has_locked") else "아니오"))
    out("  마지막으로 받은 회차: %s화 / 마지막 결과: %s (%s)" % (
        t.get("last_downloaded_no"), t.get("last_result") or "-", _t(t.get("last_result_at"))))

    if not t.get("subscribed") or t.get("excluded") or t.get("unsubscribed"):
        out("\n→ 구독 중이 아니라 자동 다운로드 대상이 아닙니다%s." % (
            " (구매 작품이라 하루 1번 '구매 작품 동기화' 때는 받음)" if t.get("purchased") else ""))

    # ── 전체 실행 ──
    job = ss.load_job_state()
    interval = max(10.0, float(cfg.get("INTERVAL_MINUTES") or 240)) * 60
    sched_on = str(cfg.get("ENABLE_SCHEDULER", "")).lower() in ("1", "true", "on", "y", "yes")
    last = job.get("last_scan_at")
    nxt = (last + interval) if last else now
    if nxt < now:
        nxt = now
    out("\n[전체 실행] 실행 주기 %d분 · 예약 실행 %s · 마지막 시작 %s · 다음 %s%s" % (
        interval // 60, "켬" if sched_on else "꺼짐(자동 실행 안 됨)", _t(last), _t(nxt),
        " (지금 실행 중)" if job.get("running") and job.get("stage") != "waitfree" else ""))
    if platform == "kakao" and not cfg.get("KAKAO_ENABLE"):
        out("  카카오페이지 사용이 꺼져 있습니다.")
    runs, n = [], 0
    probe = dict(t)
    while n < days * 24 * 3600 / interval + 1 and len(runs) < 12:
        at = nxt + n * interval
        n += 1
        if pl.in_new_episode_scope(cfg, probe, platform, now=at):
            # 카카오: 연재 요일이어도 요일 목록 스캔에서 새 회차가 보여야(또는 보유 대여권 확인 차례여야) 회차 목록을 연다
            sure = platform == "naver" or kp._needs_check(cfg, probe, at)
            runs.append((at, sure))
            if platform == "naver":
                probe["last_auto_check_at"] = at   # 네이버: 확인한 뒤 20시간은 다시 안 봄
    if runs:
        out("  이 작품을 보는 전체 실행: " + ", ".join(_t(a) + ("" if sure else "*") for a, sure in runs))
        if any(not sure for _a, sure in runs):
            out("    * 그 실행의 요일 목록 스캔에서 새 회차가 올라온 게 보이면 받음 (새 회차가 없으면 회차 목록을 열지 않음)")
    else:
        out("  앞으로 %d일 동안 전체 실행에서는 보지 않음 - 연재 요일이 아니고%s" % (days, (
            " 새 회차가 올라왔다는 표시도 없음" if platform == "kakao" else " 오늘 이미 확인함")))
    blocked = (kp.adult_block_reason_any(cfg, t) if platform == "kakao" else None) or (
        pl.genre_block_msg(cfg, t) if pl.bl_blocked(cfg, t) else None)
    if blocked:
        out("  ⚠️ 건너뜀: %s" % blocked)

    # ── 기다무 ──
    if platform == "kakao" and t.get("waitfree"):
        out("\n[기다무 확인] 5분마다 · 기다무 대여권 자동 사용 %s" % ("켬" if cfg.get("KAKAO_USE_WAITFREE") else "꺼짐 → 기다무로는 받지 않음"))
        accs = kp.accounts(cfg)
        if not accs:
            out("  카카오 로그인 쿠키가 없어 기다무 대여권을 쓸 수 없습니다.")
        dead = {n for n, _c in accs if n > 1 and job.get("kakao_cookie_expired_notified_%d" % n)}
        for n, _c in accs:
            used = kp._ticket_at(t, n)
            ready = used + kp.waitfree_period(t)
            state = "만료·로그인 안 됨으로 제외 중" if n in dead else ("지금 충전됨" if ready <= now else "충전 " + _t(ready))
            out("  계정%d: 마지막 사용(또는 확인) %s → %s" % (n, _t(used), state))
        if not t.get("has_locked"):
            out("  잠긴 회차가 없다고 기록돼 있어 기다무 확인 대상이 아닙니다 (새 회차가 잠긴 채 올라오면 다시 대상이 됨).")
        elif cfg.get("KAKAO_USE_WAITFREE"):
            due = kp.waitfree_due_titles(cfg, now)
            if tid in due:
                pos = [sid for sid, _t in kp.waitfree_order(cfg, due)].index(tid)
                rounds = pos // kp.WAITFREE_TICK_MAX
                out("  지금 기다무 확인 대상: 예 - 충전된 작품 %d개 중 %d번째%s" % (
                    len(due), pos + 1, " (앞에 %d번 확인이 더 돌아야 차례, 한 번에 %d개씩)" % (rounds, kp.WAITFREE_TICK_MAX)
                    if rounds else " (다음 확인 때 받음)"))
            else:
                out("  지금 기다무 확인 대상: 아니오(충전 전)")

    # ── 최근 이력·로그 ──
    hist = [h for h in ss.load_history(limit=3000) if str(h.get("title_id")) == tid][:5]
    out("\n[최근 다운로드 이력]")
    for h in hist:
        out("  %s %s %s화 %s%s" % (_t(h.get("ts")), h.get("type"), h.get("episode_no"),
                                  ("계정%s " % h["account"]) if h.get("account") else "", h.get("via") or h.get("error") or ""))
    if not hist:
        out("  (없음)")
    log_path = os.path.join(ss.DATA_DIR, "job.log")
    try:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()[-20000:]
        mine = [ln.rstrip() for ln in lines if str(t.get("title") or "\0") in ln][-8:]
    except OSError:
        mine = []
    out("\n[최근 로그]")
    for ln in mine:
        out("  " + ln)
    if not mine:
        out("  (최근 로그에 없음)")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('사용법: python3 -m wtm.explain "작품 이름 또는 번호" [며칠 앞까지, 기본 3]')
        sys.exit(2)
    sys.exit(explain(sys.argv[1], days=int(sys.argv[2]) if len(sys.argv) > 2 else 3))
