# -*- coding: utf-8 -*-
"""날짜별로 받은 회차 수와 용량 (네이버웹툰 / 카카오웹툰 / 카카오웹소설)

회차 파일이 라이브러리에 들어갈 때마다(host.file_ready) 그 파일 크기를 그날 기록에 더한다 → download_stats.json
(최근 120일). 화면의 진행 줄('오늘 N화 · X.XGB')과 다운로드 이력 탭 위의 날짜별 표가 이 기록을 쓴다.

    python3 -m wtm.download_stats            최근 14일 기록
    python3 -m wtm.download_stats 30         최근 30일 기록
    python3 -m wtm.download_stats --scan 7   기록을 쓰기 전(업데이트 전)의 날짜도 보려면: 저장 경로의 회차 파일을
                                             수정 시각으로 세어 본다 (원격 마운트면 몇 분 걸릴 수 있음, 기록은 안 바꿈)
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
