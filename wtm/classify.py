# -*- coding: utf-8 -*-
"""작품 분류와 수량 - 실제로 무엇을 얼마나 자주 확인·받는지 (네이버 / 카카오웹툰 / 카카오웹소설)

    venv/bin/python -m wtm.classify            분류별 작품 수 · 확인 주기 · 하루 확인 횟수 · 하루 대여권
    venv/bin/python -m wtm.classify --list     분류마다 작품 이름도 (앞 20개)

기다무 확인(kakao_pipeline._waitfree_candidates)과 같은 기준으로 센다 - 화면 [시간대별 다운로드]의 숫자와 맞는다.
- 네이버: 연재 요일에 하루 1번 (매일+는 매일, 완결·요일 없음은 새 회차가 없어 확인 안 함, BL/GL 숨김은 받지 않음)
- 카카오 기다무, 대여권을 쓰는 작품: 남은 잠긴 회차가 최신 10화 말고도 있음
  - 1·2·3·6·12시간 기다무: 그 주기마다 / 1일 이상 기다무: 하루 1번 (2일 기다무는 대여권이 이틀에 1장)
- 카카오 기다무, 대여권을 안 쓰는 작품: 남은 회차가 10개 이하(최신 10화는 대여권으로 못 엶)·잠긴 회차 없음·
  성인 인증/BL 차단·구독 안 함 등 - 연재 요일에 새 회차만 하루 1번
- 카카오 기다무 아님: 연재 요일에 하루 1번
'하루 대여권'은 계정마다 따로 충전되므로 작품 수 × (하루 / 주기) × 계정 수.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DAY_MIN = 1440


def period_label(pm):
    if pm % DAY_MIN == 0:
        return "%d일 기다무" % (pm // DAY_MIN)
    if pm % 60 == 0:
        return "%d시간 기다무" % (pm // 60)
    return "%d분 기다무" % pm


def serial_per_day(t):
    """연재 요일 기준 하루 평균 새 회차 확인 수 (매일+ 1, 주 2회 연재 2/7, 완결·요일 없음 0)"""
    if t.get("status") == "완결":
        return 0.0
    wds = t.get("weekdays") or []
    if "dailyPlus" in wds:
        return 1.0
    return len([w for w in wds if w != "dailyPlus"]) / 7.0


def open_left(t):
    """기다무 대여권으로 열 수 있는 남은 회차 (전체 - 받은 마지막 - 최신 10화). 전체 회차를 모르면 None"""
    from wtm import kakao_pipeline as kp
    if not t.get("episode_count"):
        return None
    return int(t["episode_count"]) - int(t.get("last_downloaded_no") or 0) - kp.WAITFREE_LATEST_EXCLUDED


def _kakao_reason(cfg, t, sid, cands, now):
    from wtm import kakao_pipeline as kp, pipeline as pl
    if sid in cands:
        return "남은 회차 10개 이하"          # 대상이지만 기록상 최신 10화뿐 (첫 확인 때 하루 쉬게 됨)
    if not (t.get("subscribed") or t.get("purchased")):
        return "구독 안 함"
    if kp._is_novel(t) and not kp.novel_enabled(cfg):
        return "웹소설 꺼짐"
    if kp.adult_block_reason_any(cfg, t) or pl.bl_blocked(cfg, t):
        return "성인/BL 차단"
    if not t.get("has_locked"):
        return "잠긴 회차 없음"
    if float(t.get("waitfree_idle_until") or 0) > now:
        return "남은 회차 10개 이하"
    if not (cfg.get("KAKAO_ENABLE") and cfg.get("KAKAO_USE_WAITFREE")):
        return "기다무 사용 꺼짐"
    return "기타"


def classify(cfg=None, now=None):
    """[{"platform", "name", "every", "titles": [...], "checks", "tickets"}] 표시 순서대로.
    every: 확인 주기(분, None=연재 요일), checks: 하루 확인 수, tickets: 하루 대여권(계정 합)"""
    import time
    from wtm import kakao_pipeline as kp, pipeline as pl, state_store as ss
    from wtm.hourly_stats import _cfg
    cfg = cfg or _cfg()
    now = now or time.time()
    nums, cands = kp._waitfree_candidates(cfg)
    n_acc = max(1, len(nums))
    groups = {}

    def add(platform, order, name, every, checks, tickets, tid, t):
        g = groups.setdefault((platform, name), {"platform": platform, "name": name, "every": every, "order": order,
                                                 "titles": [], "checks": 0.0, "tickets": 0.0})
        g["titles"].append((tid, t.get("title") or tid, open_left(t) if platform != "네이버웹툰" else None))
        g["checks"] += checks
        g["tickets"] += tickets

    for tid, t in ss.load_titles().items():
        if t.get("excluded") or t.get("unsubscribed") or not t.get("subscribed"):
            continue
        if pl.bl_blocked(cfg, t):
            add("네이버웹툰", (0, 2), "BL/GL 숨김 → 받지 않음", None, 0, 0, tid, t)
            continue
        per = serial_per_day(t)
        if per:
            add("네이버웹툰", (0, 0), "연재 중 → 연재일 하루 1번", None, per, 0, tid, t)
        else:
            add("네이버웹툰", (0, 1), "완결·요일 없음 → 새 회차 없어 확인 안 함", None, 0, 0, tid, t)
    for sid, t in ss.load_kakao_titles().items():
        if t.get("excluded") or t.get("unsubscribed") or not (t.get("subscribed") or t.get("purchased")):
            continue
        platform = "카카오웹소설" if kp._is_novel(t) else "카카오웹툰"
        pidx = 2 if platform == "카카오웹소설" else 1
        if not t.get("waitfree"):
            add(platform, (pidx, 9, 0), "기다무 아님 → 연재일 하루 1번", None, serial_per_day(t), 0, sid, t)
            continue
        pm = max(1, int(t.get("waitfree_period_min") or DAY_MIN))
        label = period_label(pm)
        left = open_left(t)
        if sid in cands and (left is None or left > 0):
            if pm < DAY_MIN:
                name, every, checks = "%s → %s마다 대여권" % (label, label.split()[0]), pm, DAY_MIN / float(pm)
            else:
                name, every, checks = "%s → 하루 1번 대여권" % label, DAY_MIN, 1.0
            add(platform, (pidx, 0, pm), name, every, checks, n_acc * DAY_MIN / float(pm), sid, t)
        else:
            why = _kakao_reason(cfg, t, sid, cands, now)
            add(platform, (pidx, 1, pm), "%s · %s → 연재일 하루 1번" % (label, why), None, serial_per_day(t), 0, sid, t)
    out = sorted(groups.values(), key=lambda g: (g["order"], g["name"]))
    for g in out:
        g["titles"].sort(key=lambda x: str(x[1]))
    return out, n_acc


def main(argv):
    from gdw import config
    config.load_env()
    config.utf8_console()
    os.environ.setdefault("WTM_HOST", "1")
    show = "--list" in argv
    rows, n_acc = classify()
    print("■ 작품 분류와 수량 (구독·구매 중, 카카오 계정 %d개) - 화면 [시간대별 다운로드]와 같은 기준" % n_acc)
    print("    %-46s %6s  %10s  %12s" % ("", "작품", "하루 확인", "하루 대여권"))
    cur, sub = None, None
    tot = [0, 0.0, 0.0]

    def subtotal():
        print("    %-46s %6d  %10.0f  %12.0f" % ("(소계)", sub[0], sub[1], sub[2]))
    for g in rows:
        if g["platform"] != cur:
            if cur is not None:
                subtotal()
            cur, sub = g["platform"], [0, 0.0, 0.0]
            print("\n  [%s]" % cur)
        n = len(g["titles"])
        for acc, v in ((sub, None), (tot, None)):
            acc[0] += n
            acc[1] += g["checks"]
            acc[2] += g["tickets"]
        print("    %-46s %6d  %10.0f  %12s" % (g["name"], n, g["checks"], ("%.0f" % g["tickets"]) if g["tickets"] else "-"))
        if show:
            for _tid, title, left in g["titles"][:20]:
                print("        - %s%s" % (title, "" if left is None else " (대여권으로 열 회차 %d)" % max(0, left)))
            if n > 20:
                print("        … 외 %d개" % (n - 20))
    if cur is not None:
        subtotal()
    print("\n  합계 %d개 · 하루 확인 %.0f번 · 하루 기다무 대여권 %.0f장" % (tot[0], tot[1], tot[2]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
