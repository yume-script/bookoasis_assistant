# -*- coding: utf-8 -*-
"""요일별 스캔 + 새 회차 다운로드의 실행 시각 (crontab 식, 이 컴퓨터의 시간대)

  "분 시 일 월 요일" 다섯 칸. 칸마다 *, 숫자, 범위(1-5), 간격(*/15, 9-18/3), 목록(0,30) - 요일은 0·7=일요일, 1=월요일 … 또는 mon..sun
  예) "0 */4 * * *"  4시간마다 정각     "30 5,11,17,23 * * *"  하루 4번
      "*/30 9-23 * * *"  아침 9시~밤 11시 30분마다     "0 6 * * 1-5"  평일 아침 6시
  일과 요일을 둘 다 정하면 crontab처럼 둘 중 하나만 맞아도 된다.

예전 설정의 실행 주기(INTERVAL_MINUTES, 분)는 from_interval()로 가장 가까운 crontab 식으로 바꾼다.
"""
import time

_NAMES = {"sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6,
          "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
_RANGES = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))
_LABELS = ("분", "시", "일", "월", "요일")
DEFAULT = "0 */4 * * *"
MAX_SEARCH_DAYS = 400


class CronError(ValueError):
    pass


def _num(text, lo, hi, label):
    t = text.strip().lower()
    v = _NAMES.get(t[:3]) if t[:3] in _NAMES and not t.isdigit() else None
    if v is None:
        try:
            v = int(t)
        except ValueError:
            raise CronError(f"{label} 칸의 '{text}'을(를) 읽을 수 없습니다.")
    if not lo <= v <= hi:
        raise CronError(f"{label} 칸의 {v}은(는) {lo}~{hi} 사이여야 합니다.")
    return v


def _field(text, lo, hi, label):
    out = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            raise CronError(f"{label} 칸이 비어 있습니다.")
        rng, _, step = part.partition("/")
        step = _num(step, 1, hi - lo + 1 if hi > lo else 1, label) if step else 1
        if rng == "*":
            a, b = lo, hi
        elif "-" in rng:
            x, _, y = rng.partition("-")
            a, b = _num(x, lo, hi, label), _num(y, lo, hi, label)
            if a > b:
                raise CronError(f"{label} 칸의 범위 {rng}가 거꾸로입니다.")
        else:
            a = _num(rng, lo, hi, label)
            b = hi if _ else a   # "5/15" = 5부터 15마다
        out.update(range(a, b + 1, step))
    return out


def parse(expr):
    """crontab 식 -> (분, 시, 일, 월, 요일 집합, 일 칸 *, 요일 칸 *). 틀리면 CronError"""
    parts = str(expr or "").split()
    if len(parts) != 5:
        raise CronError("crontab 식은 '분 시 일 월 요일' 다섯 칸입니다 (예: 0 */4 * * *).")
    sets = [_field(p, lo, hi, lab) for p, (lo, hi), lab in zip(parts, _RANGES, _LABELS)]
    if 7 in sets[4]:
        sets[4] = (sets[4] - {7}) | {0}
    return (*sets, parts[2] == "*", parts[4] == "*")


def validate(expr):
    """틀렸으면 CronError (한 번도 돌지 않는 식도 - 2월 30일 등)"""
    if next_after(expr, time.time()) is None:
        raise CronError("이 crontab 식으로는 실행할 날이 없습니다.")
    return " ".join(str(expr).split())


def _day_ok(spec, tm):
    _mi, _h, dom, mon, dow, dom_any, dow_any = spec
    if tm.tm_mon not in mon:
        return False
    d_ok, w_ok = tm.tm_mday in dom, (tm.tm_wday + 1) % 7 in dow   # tm_wday: 월=0 -> cron: 일=0
    if dom_any or dow_any:
        return d_ok and w_ok
    return d_ok or w_ok


def next_after(expr, after):
    """after(유닉스 초) 다음(초과)의 실행 시각 (유닉스 초, 분 단위). 없으면 None"""
    spec = parse(expr) if isinstance(expr, str) else expr
    mins, hours = spec[0], spec[1]
    t = (int(after) // 60 + 1) * 60
    end = after + MAX_SEARCH_DAYS * 86400
    while t <= end:
        tm = time.localtime(t)
        if not _day_ok(spec, tm):   # 다음 날 0시로
            t = int(time.mktime((tm.tm_year, tm.tm_mon, tm.tm_mday + 1, 0, 0, 0, 0, 0, -1)))
            continue
        if tm.tm_hour not in hours:   # 다음 시 0분으로
            t = int(time.mktime((tm.tm_year, tm.tm_mon, tm.tm_mday, tm.tm_hour + 1, 0, 0, 0, 0, -1)))
            continue
        if tm.tm_min in mins:
            return t
        t += 60
    return None


def due(expr, last, now=None):
    """last(지난번에 처리한 실행 시각) 뒤로 now까지 실행 시각이 있었으면 그 시각 (여럿 지났어도 한 번), 아니면 None"""
    now = time.time() if now is None else now
    nxt = next_after(expr, last)
    return nxt if nxt is not None and nxt <= now else None


def from_interval(minutes):
    """예전 실행 주기(분) -> 가장 가까운 crontab 식 (60을 나누면 '*/N * * * *', 시간 단위로 24를 나누면 '0 */H * * *')"""
    try:
        m = max(10, int(float(minutes)))
    except (TypeError, ValueError):
        return DEFAULT
    if m < 60:
        n = min((d for d in (10, 12, 15, 20, 30) if d >= m), default=30)
        return f"*/{n} * * * *"
    hours = max(1, round(m / 60))
    if hours >= 24:
        return "0 0 * * *"
    h = min((d for d in (1, 2, 3, 4, 6, 8, 12) if d >= hours), default=12)
    return "0 * * * *" if h == 1 else f"0 */{h} * * *"


def describe(expr, now=None, count=3):
    """다음 실행 시각 몇 개 ["11/17 16:00", …] (화면 안내용)"""
    out, t = [], time.time() if now is None else now
    try:
        spec = parse(expr)
    except CronError:
        return out
    for _ in range(count):
        t = next_after(spec, t)
        if t is None:
            break
        out.append(time.strftime("%m/%d %H:%M", time.localtime(t)))
    return out
