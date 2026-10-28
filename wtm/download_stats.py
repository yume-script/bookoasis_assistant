# -*- coding: utf-8 -*-
"""날짜별로 받은 회차 수와 용량 (네이버웹툰 / 카카오웹툰 / 카카오웹소설)

회차 파일이 라이브러리에 들어갈 때마다(host.file_ready) 그 파일 크기를 그날 기록에 더한다 → download_stats.json
(최근 120일). 화면의 진행 줄('오늘 N화 · X.XGB')과 다운로드 이력 탭 위의 날짜별 표가 이 기록을 쓴다.

    python3 -m wtm.download_stats            최근 14일 기록
    python3 -m wtm.download_stats 30         최근 30일 기록
    python3 -m wtm.download_stats --scan 7   기록을 쓰기 전(업데이트 전)의 날짜도 보려면: 저장 경로의 회차 파일을
                                             수정 시각으로 세어 본다 (원격 마운트면 몇 분 걸릴 수 있음, 기록은 안 바꿈)
    python3 -m wtm.download_stats --forecast 30   앞으로 30일 동안 하루에 받을 회차 수·용량 예측
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

EXTS = (".zip", ".cbz", ".epub")
PLATFORMS = (("naver", "네이버웹툰"), ("kakao", "카카오웹툰"), ("kakao_novel", "카카오웹소설"))
KEEP_DAYS = 120
_roots = {"at": 0.0, "v": None}


def _path():
    from . import state_store as ss
    return os.path.join(ss.DATA_DIR, "download_stats.json")


def roots():
    """[(플랫폼, 저장 경로)] - 설정은 1분에 한 번만 다시 읽는다"""
    if _roots["v"] is None or time.time() - _roots["at"] > 60:
        from . import host, kakao_pipeline as kp, state_store as ss
        cfg = host.load_settings()
        _roots["v"] = [("kakao_novel", os.path.normpath(kp.kakao_novel_root(cfg))),
                       ("kakao", os.path.normpath(kp.kakao_root(cfg))),
                       ("naver", os.path.normpath(cfg.get("DOWNLOAD_ROOT") or ss.DOWNLOAD_DEFAULT_DIR))]
        _roots["at"] = time.time()
    return _roots["v"]


def platform_of(path):
    """회차 파일 경로 → naver / kakao / kakao_novel (저장 경로로 판단, 모르면 None)"""
    series = os.path.dirname(os.path.dirname(os.path.abspath(path)))
    for p, r in roots():
        if os.path.normpath(series) == r:
            return p
    if path.lower().endswith(".epub"):
        return "kakao_novel"
    return None


def record(path, size=None):
    """회차 파일 하나가 라이브러리에 들어감 → 그날 기록에 더한다"""
    from . import state_store as ss
    path = str(path or "")
    if not path.lower().endswith(EXTS):
        return
    if size is None:
        try:
            size = os.path.getsize(path)
        except OSError:
            return
    p = platform_of(path) or "naver"
    day = time.strftime("%Y-%m-%d")
    with ss._lock:
        data = ss.read_json(_path(), {})
        d = data.setdefault(day, {})
        rec = d.setdefault(p, {"count": 0, "bytes": 0})
        rec["count"] += 1
        rec["bytes"] += int(size)
        for old in sorted(data)[:-KEEP_DAYS]:
            data.pop(old, None)
        ss.write_json(_path(), data)


def load(days=14):
    """최근 days일 [(날짜, {플랫폼: {"count", "bytes"}})] - 오늘이 먼저"""
    from . import state_store as ss
    data = ss.read_json(_path(), {})
    out = []
    for i in range(days):
        day = time.strftime("%Y-%m-%d", time.localtime(time.time() - i * 86400))
        out.append((day, data.get(day) or {}))
    return out


def summary(days=7):
    """화면용: [{"day", "count", "bytes", "naver": {...}, ...}] 오늘이 먼저"""
    out = []
    for day, d in load(days):
        row = {"day": day, "count": sum(v.get("count", 0) for v in d.values()),
               "bytes": sum(v.get("bytes", 0) for v in d.values())}
        for p, _label in PLATFORMS:
            row[p] = d.get(p) or {"count": 0, "bytes": 0}
        out.append(row)
    return out


def gb(n):
    return "%.2fGB" % (n / 1073741824.0) if n >= 107374182 else "%.0fMB" % (n / 1048576.0)


def scan(days):
    """저장 경로의 회차 파일을 수정 시각으로 날짜별로 센다 (기록과 별개, 기록이 없던 날 확인용)"""
    cut = time.time() - days * 86400
    out = {}
    for p, root in roots():
        if not os.path.isdir(root):
            continue
        try:
            series = os.listdir(root)
        except OSError:
            continue
        for i, name in enumerate(series):
            d = os.path.join(root, name)
            try:
                entries = list(os.scandir(d))
            except OSError:
                continue
            for e in entries:
                if not e.name.lower().endswith(EXTS):
                    continue
                try:
                    st = e.stat()
                except OSError:
                    continue
                if st.st_mtime < cut:
                    continue
                day = time.strftime("%Y-%m-%d", time.localtime(st.st_mtime))
                rec = out.setdefault(day, {}).setdefault(p, {"count": 0, "bytes": 0})
                rec["count"] += 1
                rec["bytes"] += st.st_size
            if (i + 1) % 500 == 0:
                print("  … %s %d/%d 폴더" % (p, i + 1, len(series)), flush=True)
    return out


# 회차 크기를 모를 때 쓰는 기본값 (기록이 쌓이면 최근 기록의 평균을 쓴다)
DEFAULT_EP_BYTES = {"naver": 25 * 1048576, "kakao": 15 * 1048576, "kakao_novel": 200 * 1024}


def avg_bytes(days=14):
    """플랫폼별 회차 하나 평균 크기 {플랫폼: (바이트, 근거 회차 수)} - 최근 기록, 없으면 기본값"""
    tot = {}
    for _day, d in load(days):
        for p, v in d.items():
            c, b = tot.get(p, (0, 0))
            tot[p] = (c + v.get("count", 0), b + v.get("bytes", 0))
    return {p: ((tot[p][1] / tot[p][0], tot[p][0]) if tot.get(p, (0, 0))[0] else (DEFAULT_EP_BYTES[p], 0))
            for p, _l in PLATFORMS}


def avg_waitfree_delay(days=7):
    """최근 기다무 사용의 평균 지연(초) - 충전 뒤 1분 기다림 포함. 이력에 기록이 없으면 5분으로 본다"""
    from . import state_store as ss
    cut = time.time() - days * 86400
    lates = [float(h["late_sec"]) for h in ss.load_history(limit=3000, per_platform=True)
             if h.get("late_sec") is not None and float(h.get("ts") or 0) >= cut]
    try:
        from .kakao_pipeline import WAITFREE_READY_GRACE as grace
    except ImportError:
        grace = 60
    return (sum(lates) / len(lates) if lates else 240) + grace


def tickets_per_day(period_min, delay_sec):
    """계정 하나가 하루에 실제로 쓰는 기다무 대여권 수. 대여권은 '쓴 시각 + 주기'에 다시 충전되므로, 쓸 때마다 생기는
    지연(충전 뒤 1분 + 대기열)만큼 한 바퀴가 길어진다.
    - 하루보다 짧은 주기(1·2·3·12시간): 하루 횟수에서 한 번을 뺀다 (3시간 → 8번이 아니라 7번). 지연이 쌓여 하루에
      한 바퀴쯤은 다음 날로 밀린다고 보는 보수적 계산
    - 1일 이상: 한 바퀴가 (주기 + 지연)이 되는 만큼 줄인다 (1일 기다무에 지연 5분 → 하루 0.997장)"""
    period = max(1, int(period_min)) * 60.0
    if period < 86400:
        return max(0.0, 86400.0 // period - 1)
    return 86400.0 / (period + max(0.0, delay_sec))


def forecast(days=30, now=None):
    """앞으로 days일 동안 하루에 받을 회차 수 예측 [(날짜, {플랫폼: 회차 수})], 근거 설명 dict.
    - 기다무: 대여권을 쓰는 작품(구독·구매 + 잠긴 회차 남음)마다 계정 수 × (하루 / 충전 주기)장. 작품마다 남은 잠긴 회차
      (전체 회차 - 받은 마지막 회차)를 다 받으면 그 작품은 빠진다 → 날이 갈수록 줄어든다
    - 새 회차: 구독 중인 연재작마다 연재 요일 수만큼 일주일에 받는다(매일+는 7번). 완결작은 0
    실제로는 처리 속도·대여권 거절·새 기다무 작품 등으로 달라질 수 있다."""
    from . import host, kakao_pipeline as kp, pipeline as pl, state_store as ss
    from .webtoon_manager import DEFAULTS
    cfg = dict(DEFAULTS)
    cfg.update({k: v for k, v in host.load_settings().items() if v not in (None, "")})
    now = now or time.time()
    nums, cands = kp._waitfree_candidates(cfg)
    n_acc = max(1, len(nums))
    def weekly_of(t):
        if t.get("status") == "완결":
            return 0
        wd = t.get("weekdays") or []
        return 7 if "dailyPlus" in wd else len([w for w in wd if w != "dailyPlus"])

    delay = avg_waitfree_delay()
    wf = []   # (플랫폼, 하루 장수, 남은 회차, 따라잡은 뒤 하루 새 회차)
    for sid, t in cands.items():
        per_day = n_acc * tickets_per_day(int(t.get("waitfree_period_min") or 1440), delay)
        left = max(0, int(t.get("episode_count") or 0) - int(t.get("last_downloaded_no") or 0))
        wf.append(("kakao_novel" if kp._is_novel(t) else "kakao", per_day, left or 1, weekly_of(t) / 7.0))
    weekly = {"naver": 0.0, "kakao": 0.0, "kakao_novel": 0.0}
    for platform, titles in (("naver", ss.load_titles()), ("kakao", ss.load_kakao_titles())):
        for tid, t in titles.items():
            if not t.get("subscribed") or t.get("excluded") or t.get("unsubscribed"):
                continue
            if platform == "naver" and pl.bl_blocked(cfg, t):
                continue
            if platform == "kakao" and str(tid) in cands:
                continue   # 기다무로 밀린 회차를 받는 중인 작품 - 새 회차도 그 흐름으로 들어온다(아래)
            n = weekly_of(t)
            if not n:
                continue
            p = "kakao_novel" if platform == "kakao" and kp._is_novel(t) else platform
            weekly[p] += n
    rows = []
    left = [x[2] for x in wf]
    for i in range(days):
        day = time.strftime("%Y-%m-%d", time.localtime(now + i * 86400))
        cnt = {p: weekly[p] / 7.0 for p, _l in PLATFORMS}
        for j, (p, per_day, _l0, new_per_day) in enumerate(wf):
            left[j] += new_per_day          # 새 회차가 잠긴 채 올라오면 받을 회차가 늘어난다
            use = min(per_day, left[j])
            left[j] -= use
            cnt[p] += use
        rows.append((day, cnt))
    info = {"waitfree_titles": len(wf), "accounts": n_acc, "weekly_new": weekly, "delay": delay,
            "waitfree_left": sum(x[2] for x in wf)}
    return rows, info


def _print_forecast(days):
    rows, info = forecast(days)
    sizes = avg_bytes()
    print("■ 앞으로 %d일 예측 (기다무 작품 %d개 · 계정 %d개 · 남은 잠긴 회차 합계 %d화)" % (
        days, info["waitfree_titles"], info["accounts"], info["waitfree_left"]))
    print("  기다무 한 계정이 하루에 쓰는 대여권: 3시간 %g장 · 12시간 %g장 · 1일 %.3f장 (평균 지연 %d분 반영)" % (
        tickets_per_day(180, info["delay"]), tickets_per_day(720, info["delay"]), tickets_per_day(1440, info["delay"]),
        round(info["delay"] / 60)))
    print("  회차 평균 크기: " + " · ".join("%s %s%s" % (label, gb(sizes[p][0]), "" if sizes[p][1] else "(기본값)")
                                      for p, label in PLATFORMS))
    print("  새 회차(연재): 일주일에 " + " · ".join("%s %d화" % (label, info["weekly_new"][p]) for p, label in PLATFORMS))
    print("\n  날짜          합계              " + "  ".join("%-16s" % label for _p, label in PLATFORMS))
    tot_c = tot_b = 0
    for day, cnt in rows:
        c = sum(cnt.values())
        b = sum(cnt[p] * sizes[p][0] for p in cnt)
        tot_c += c
        tot_b += b
        print("  %s  %-16s  %s" % (day, "%d화 %s" % (round(c), gb(b)), "  ".join(
            "%-16s" % ("%d화 %s" % (round(cnt[p]), gb(cnt[p] * sizes[p][0]))) for p, _l in PLATFORMS)))
    print("\n  %d일 합계: %d화 · %s (하루 평균 %d화 · %s)" % (days, round(tot_c), gb(tot_b), round(tot_c / days),
                                                         gb(tot_b / days)))
    print("  * 기다무는 남은 잠긴 회차를 다 받으면 빠지므로 날이 갈수록 줄어듭니다. 대여권 거절·처리 속도·새로 생기는")
    print("    기다무 작품은 반영하지 않은 추정치입니다. 크기는 최근 14일 기록 평균(없으면 기본값)입니다.")


def _print(rows):
    print("  날짜          합계              " + "  ".join("%-16s" % label for _p, label in PLATFORMS))
    for day, d in rows:
        cnt = sum(v.get("count", 0) for v in d.values())
        size = sum(v.get("bytes", 0) for v in d.values())
        cols = "  ".join("%-16s" % ("%d화 %s" % (d[p]["count"], gb(d[p]["bytes"])) if d.get(p) else "-")
                         for p, _label in PLATFORMS)
        print("  %s  %-16s  %s" % (day, ("%d화 %s" % (cnt, gb(size))) if cnt else "-", cols))


def main(argv):
    from gdw import config
    config.load_env()
    config.utf8_console()
    os.environ.setdefault("WTM_HOST", "1")
    if "--forecast" in argv:
        i = argv.index("--forecast")
        _print_forecast(int(argv[i + 1]) if i + 1 < len(argv) and argv[i + 1].isdigit() else 30)
        return 0
    if "--scan" in argv:
        i = argv.index("--scan")
        days = int(argv[i + 1]) if i + 1 < len(argv) and argv[i + 1].isdigit() else 7
        print("■ 저장 경로의 회차 파일을 수정 시각으로 세기 (최근 %d일, 경로: %s)" % (
            days, ", ".join(r for _p, r in roots())))
        found = scan(days)
        _print([(day, found[day]) for day in sorted(found, reverse=True)])
        return 0
    days = int(argv[0]) if argv and argv[0].isdigit() else 14
    print("■ 날짜별로 받은 회차·용량 (최근 %d일, 업데이트 뒤부터 기록됨 - 그 전은 --scan 으로)" % days)
    _print(load(days))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
