# -*- coding: utf-8 -*-
"""시간대별 다운로드 (화면 [웹툰 다운로더 > 시간대별 다운로드])

플랫폼(네이버웹툰 / 카카오웹툰 / 카카오웹소설)과 기다무 주기(1시간·3시간·1일 기다무 …)별로 0~23시에
- 예약: 지금 기록된 기다무 충전 일정으로 앞으로 7일 동안 대여권을 쓸 시각을 시간대별로 모아 하루 평균으로 나눈 것
  (작품·계정마다 '마지막으로 쓴 시각 + 충전 주기 + 최근 평균 지연', 새벽 사용 설정·남은 잠긴 회차 반영).
  기다무가 아닌 것(새 회차·무료 등)은 예약이 없다.
- 실제: 다운로드 이력(history.jsonl)에서 고른 기간(최근 24시간 / 오늘 / 어제 / 최근 7일 평균)에 받은 회차 수
를 나란히 놓고, 하루에 고르게 펼쳐져 있는지(고른 정도: 24시간에 똑같이 나뉘면 100%)를 본다.
1일 기다무는 0~24시에 고르게, 3시간 기다무는 3시간마다 같은 수씩 쓰이는 게 이상적이다.

    python3 -m wtm.hourly_stats            최근 24시간 실제 + 예약
    python3 -m wtm.hourly_stats 7d         최근 7일 평균
"""
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

PLATFORMS = (("naver", "네이버웹툰"), ("kakao", "카카오웹툰"), ("kakao_novel", "카카오웹소설"))
RANGES = (("24h", "최근 24시간"), ("today", "오늘"), ("yesterday", "어제"), ("7d", "최근 7일 평균"))
NON_WAITFREE = "새 회차·무료·대여권"
SCHEDULE_DAYS = 7
_WF_RE = re.compile(r"(\d+)(분|시간|일) 기다무")
_hist = {"sig": None, "events": [], "at": 0.0}


def _period_min(label):
    """'3시간 기다무' → 180 (정렬용). 주기를 모르는 예전 기록('기다무')은 맨 뒤"""
    m = _WF_RE.search(label or "")
    if not m:
        return 10 ** 6
    return int(m.group(1)) * {"분": 1, "시간": 60, "일": 1440}[m.group(2)]


def _group_of(e):
    """이력 한 줄 → (플랫폼, 종류 라벨)"""
    from . import state_store as ss
    p = e.get("platform")
    if p not in ("kakao", "kakao_novel"):
        p = "kakao" if ss.history_bucket(e) == "kakao" else "naver"
    via = str(e.get("via") or "")
    if "기다무" in via:
        m = _WF_RE.search(via)
        return p, (m.group(0) if m else "기다무")
    return p, NON_WAITFREE


def _events():
    """[(ts, 플랫폼, 종류)] 받은 회차 (이력 파일이 바뀌었을 때만 다시 읽음, 최대 30초에 한 번)"""
    from . import state_store as ss
    sig = ss._file_sig(ss.HISTORY_PATH)
    if _hist["sig"] == sig or (_hist["sig"] is not None and time.time() - _hist["at"] < 30):
        return _hist["events"]
    out = []
    try:
        with open(ss.HISTORY_PATH, encoding="utf-8", errors="replace") as f:
            for line in f:
                if '"download"' not in line and '"manual_download"' not in line:
                    continue
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if e.get("type") not in ("download", "manual_download") or not e.get("ts"):
                    continue
                p, kind = _group_of(e)
                out.append((float(e["ts"]), p, kind))
    except OSError:
        pass
    _hist.update(sig=sig, events=out, at=time.time())
    return out


def _range_bounds(rng, now):
    lt = time.localtime(now)
    midnight = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
    if rng == "today":
        return midnight, now, 1
    if rng == "yesterday":
        return midnight - 86400, midnight, 1
    if rng == "7d":
        return now - 7 * 86400, now, 7
    return now - 86400, now, 1


def actual(rng, now):
    """{(플랫폼, 종류): [24]} 고른 기간에 받은 회차 수 (7일이면 하루 평균)"""
    start, end, div = _range_bounds(rng, now)
    out = {}
    for ts, p, kind in _events():
        if start <= ts < end:
            out.setdefault((p, kind), [0.0] * 24)[time.localtime(ts).tm_hour] += 1
    if div > 1:
        out = {k: [round(v / div, 1) for v in arr] for k, arr in out.items()}
    return out


def _cfg():
    from . import host
    from .webtoon_manager import DEFAULTS
    cfg = dict(DEFAULTS)
    cfg.update({k: v for k, v in host.load_settings().items() if v not in (None, "")})
    return cfg


def schedule(cfg, now, days=SCHEDULE_DAYS):
    """{(플랫폼, 'N시간 기다무'): [24]} 지금 충전 일정대로라면 하루에 시간대별로 쓸 대여권 수 (앞으로 days일 평균).
    작품·계정마다 다음 사용 시각부터 (주기 + 평균 지연)마다 한 장, 남은 잠긴 회차(최신 10화 제외)까지만."""
    from . import download_stats as ds, kakao_pipeline as kp
    nums, cands = kp._waitfree_candidates(cfg)
    out, titles = {}, {}
    if not cands:
        return out, titles
    end = now + days * 86400
    extra = max(0.0, ds.avg_waitfree_delay() - kp.WAITFREE_READY_GRACE)   # ready_at에 1분이 이미 들어 있다
    night = kp.night_info(cfg, now)
    for sid, t in cands.items():
        key = ("kakao_novel" if kp._is_novel(t) else "kakao", kp.waitfree_label(t))
        titles[key] = titles.get(key, 0) + 1
        period = kp.waitfree_period(t)
        left = None
        if t.get("episode_count"):
            left = max(0, int(t["episode_count"]) - kp.WAITFREE_LATEST_EXCLUDED - int(t.get("last_downloaded_no") or 0))
            if t.get("status") != "완결":
                left += days   # 그사이 새 회차가 잠긴 채 올라오는 것 (연재작, 넉넉히 하루 1화)
        evs = []
        for n in nums:
            r = max(now, kp.ready_at(cfg, t, n, now=now, night=night, nums=nums) + extra)
            while r < end:
                evs.append(r)
                r += period + extra
        evs.sort()
        arr = out.setdefault(key, [0.0] * 24)
        for r in (evs if left is None else evs[:left]):
            arr[time.localtime(r).tm_hour] += 1.0 / days
    return {k: [round(v, 1) for v in arr] for k, arr in out.items()}, titles


def evenness(arr):
    """24시간에 똑같이 나뉘면 100, 한 시간에 몰리면 0에 가깝다: 100 × (1 - 균등 분포와의 거리)"""
    tot = sum(arr or [])
    if tot <= 0:
        return None
    avg = tot / 24.0
    dist = sum(abs(v - avg) for v in arr) / (2.0 * tot)      # 0(균등) ~ 23/24(한 칸)
    return int(round(100 * (1 - dist * 24 / 23.0)))


def report(rng="24h", now=None):
    """화면용: {"range", "ranges", "rows": [{"platform", "platform_label", "kind", "titles", "schedule": [24]|None,
    "actual": [24], "sched_total", "actual_total", "sched_even", "actual_even", "ideal"}], "now_hour", "accounts", "delay"}"""
    from . import download_stats as ds, kakao_pipeline as kp
    now = now or time.time()
    rng = rng if rng in dict(RANGES) else "24h"
    cfg = _cfg()
    sched, titles = schedule(cfg, now)
    act = actual(rng, now)
    keys = set(sched) | set(act)
    for p, _l in PLATFORMS:   # 기다무 아닌 줄은 플랫폼마다 늘 보이게
        if p != "kakao_novel" or kp.novel_enabled(cfg) or any(k[0] == p for k in keys):
            keys.add((p, NON_WAITFREE))
    order = {p: i for i, (p, _l) in enumerate(PLATFORMS)}
    rows = []
    for key in sorted(keys, key=lambda k: (order.get(k[0], 9), k[1] == NON_WAITFREE, _period_min(k[1]))):
        p, kind = key
        s = sched.get(key) if kind != NON_WAITFREE else None
        a = act.get(key) or [0] * 24
        st = round(sum(s), 1) if s else 0
        rows.append({"platform": p, "platform_label": dict(PLATFORMS)[p], "kind": kind, "titles": titles.get(key),
                     "period_min": _period_min(kind) if kind != NON_WAITFREE else None,
                     "schedule": s, "actual": a, "sched_total": st, "actual_total": round(sum(a), 1),
                     "sched_even": evenness(s) if s else None, "actual_even": evenness(a),
                     "ideal": round(st / 24.0, 1) if s else None})
    nums, _c = kp._waitfree_candidates(cfg)
    return {"range": rng, "ranges": [list(r) for r in RANGES], "rows": rows, "now_hour": time.localtime(now).tm_hour,
            "accounts": len(nums), "delay": int(ds.avg_waitfree_delay()), "schedule_days": SCHEDULE_DAYS}


def main(argv):
    from gdw import config
    config.load_env()
    config.utf8_console()
    os.environ.setdefault("WTM_HOST", "1")
    rng = next((a for a in argv if a in dict(RANGES)), "24h")
    r = report(rng)
    print("■ 시간대별 다운로드 - 실제: %s · 예약: 지금 충전 일정 (계정 %d개, 평균 지연 %d초)" % (
        dict(RANGES)[r["range"]], r["accounts"], r["delay"]))
    print("  %-26s %s" % ("", " ".join("%3d" % h for h in range(24))))
    for x in r["rows"]:
        name = "%s %s" % (x["platform_label"], x["kind"])
        if x["schedule"]:
            print("  %-24s 예약 %s  하루 %g · 고른 정도 %s%%" % (name, " ".join("%3.0f" % v for v in x["schedule"]),
                                                       x["sched_total"], x["sched_even"]))
            name = ""
        print("  %-24s 실제 %s  하루 %g · 고른 정도 %s" % (name, " ".join("%3.0f" % v for v in x["actual"]), x["actual_total"],
                                                   "-" if x["actual_even"] is None else "%d%%" % x["actual_even"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
