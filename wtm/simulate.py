# -*- coding: utf-8 -*-
"""기다무 확인 순서와 지연을 지금 데이터로 미리 계산해 본다 (카카오에 요청하지 않음).

    python3 -m wtm.simulate                 앞으로 24시간
    python3 -m wtm.simulate 48 "곤륜객잔"    48시간 + 이 작품이 언제 받는지
    python3 -m wtm.simulate 24 --csv /tmp/wf.csv   대여권 사용 예정을 한 줄씩 CSV로
    python3 -m wtm.simulate 24 --fixed                       예전 동작: 충전 시각과 상관없이 5분 간격
    python3 -m wtm.simulate 24 --pause-full --full-min 120   예전 동작: 2시간 전체 실행 동안 기다무 확인이 멈춤

서버에 저장된 작품 기록(계정별 마지막 대여권 사용 시각, 충전 주기, 남은 회차 수)과 실제 동작 규칙
(다음 충전 시각에 맞춰 확인 - 1분 이상·최대 간격 이하, 한 번에 30개, 충전 시각이 오래된 순서, 밀리면 1분 뒤 이어서, 전체 실행 중에도 돎)으로
앞으로 대여권을 언제 쓰게 되는지 따라가 본다. 한 번 확인에 걸리는 시간은 job.log의 최근 기록으로 잰다.

가정 (실제와 다를 수 있는 부분)
  - 충전된 계정은 차례가 오면 모두 대여권을 쓴다 (기다무로 열 회차가 없거나 카카오가 거절하는 경우는 모름)
  - 남은 회차 = 전체 회차 - 받은 마지막 회차. 다 받으면 대상에서 빠진다
  - 전체 실행이 쓰는 대여권은 따로 세지 않는다 (전체 실행과 같이 돌 때 느려지는 것도 반영하지 않음)
"""
import csv
import os
import re
import sys
import time
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from gdw import config  # noqa: E402

config.load_env()
os.environ.setdefault("WTM_HOST", "1")

TICK = 300          # scheduler.WAITFREE_TICK_SECONDS
BACKLOG_GAP = 60    # 밀린 작품이 남았을 때 다음 확인까지 (스케줄러 루프 간격)
LOG_TS = re.compile(r"^\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\] (.*)$")


def _ts(text):
    return time.mktime(time.strptime(text, "%Y-%m-%d %H:%M:%S"))


def _hm(ts):
    lt = time.localtime(ts)
    return time.strftime("%m-%d", lt) + "(" + "월화수목금토일"[lt.tm_wday] + ") " + time.strftime("%H:%M", lt)


def _dur(sec):
    m = int(sec) // 60
    return "%d분" % m if m < 60 else "%d시간 %02d분" % (m // 60, m % 60)


def _period_label(m):
    return "%d일" % (m // 1440) if m % 1440 == 0 else ("%d시간" % (m // 60) if m % 60 == 0 else "%d분" % m)


def measure(log_path):
    """job.log에서 (작품 하나당 걸린 초, 표본 수, 최근 전체 실행 소요 초 또는 None)"""
    try:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        lines = []
    per, start, n = [], None, 0
    full_start, full_end, fulls = None, None, []
    for ln in lines:
        m = LOG_TS.match(ln.rstrip())
        if not m:
            continue
        ts, msg = _ts(m.group(1)), m.group(2)
        hit = re.match(r"카카오 기다무: 대여권이 충전된 작품 (\d+)개 확인$", msg)
        if hit:
            start, n = ts, int(hit.group(1))
        elif msg.startswith("카카오 기다무: 대여권 ") and start and n:
            per.append((ts - start) / n)
            start = None
        if msg.startswith("요일별 연재 목록 수집 시작"):
            if full_start and full_end:
                fulls.append(full_end - full_start)
            full_start, full_end = ts, None
        elif full_start and (msg.startswith("다운로드 사이클 완료") or msg.startswith("카카오페이지 완료")):
            full_end = ts
    if full_start and full_end:
        fulls.append(full_end - full_start)
    per = per[-30:]
    return (sum(per) / len(per) if per else 10.0), len(per), (fulls[-1] if fulls else None)


def simulate(cfg, hours=24, per_title=10.0, full_dur=None, now=None, pause_full=False, fixed=False):
    """fixed=True: 예전 동작(5분 간격 고정)으로 계산 - 비교용"""
    from wtm.scheduler import waitfree_wait
    from wtm import kakao_pipeline as kp, state_store as ss
    now = now or time.time()
    job = ss.load_job_state()
    nums = [n for n, _c in kp.accounts(cfg) if n == 1 or not job.get("kakao_cookie_expired_notified_%d" % n)]
    if not nums:
        return None
    # 대상 작품: 실제 기다무 확인과 같은 조건 (충전 여부만 빼고 - 아주 먼 미래 시각으로 물어 본다)
    cands = kp.waitfree_due_titles(cfg, now=now + 10 * 365 * 86400)
    st = {}
    for sid, t in cands.items():
        left = max(0, int(t.get("episode_count") or 0) - int(t.get("last_downloaded_no") or 0))
        st[sid] = {"title": t.get("title") or sid, "period": kp.waitfree_period(t),
                   "tick": {n: kp._ticket_at(t, n) for n in nums}, "left": left or 1}
    # 전체 실행 구간 (그동안 기다무 확인은 작업 잠금을 못 잡아 쉰다)
    interval = max(10.0, float(cfg.get("INTERVAL_MINUTES") or 240)) * 60
    blocks = []
    # v2.10.4부터 기다무 확인은 전체 실행 중에도 따로 돈다 - --pause-full로 예전 동작(멈춤)을 비교해 볼 수 있다
    if full_dur and pause_full and str(cfg.get("ENABLE_SCHEDULER", "")).lower() in ("1", "true", "on", "y", "yes"):
        s = (job.get("last_scan_at") or now)
        while s < now + hours * 3600:
            if s + full_dur > now:
                blocks.append((s, s + full_dur))
            s += interval

    win = kp._night_window(cfg)

    def ready(x, n, at):  # kakao_pipeline.ready_at과 같은 규칙 (긴 주기 기다무는 새벽 시간대로)
        base = x["tick"][n] + x["period"] if x["tick"][n] else at
        return kp._window_start(win, base) if win and x["period"] >= kp.NIGHT_MIN_PERIOD else base

    def charged(x, at):
        return [n for n in nums if ready(x, n, at) <= at]

    def key(item):
        x = item[1]
        known = [ready(x, n, t) for n in nums if x["tick"][n]]
        night = 1 if win and x["period"] >= kp.NIGHT_MIN_PERIOD else 0   # waitfree_order와 같게: 새벽으로 미룬 작품은 뒤에
        return (night, 0 if known else 1, min(known) if known else 0)

    def next_charge(at):
        best = None
        for x in st.values():
            for n in nums:
                c = ready(x, n, at)
                if c > at and (best is None or c < best):
                    best = c
        return best

    end = now + hours * 3600
    t = now
    visits, rounds = [], []
    while t < end and st:
        blk = next((b for b in blocks if b[0] <= t < b[1]), None)
        if blk:
            t = blk[1] + 60
            continue
        due = sorted(((sid, x) for sid, x in st.items() if charged(x, t)), key=key)
        if not due:
            t += max(60, TICK) if fixed else waitfree_wait(cfg, t, next_charge(t), now=t)
            continue
        batch = due[:kp.WAITFREE_TICK_MAX]
        dur = per_title * len(batch)
        rounds.append((t, len(due), len(batch), dur))
        for i, (sid, x) in enumerate(batch):
            at = t + dur * (i + 1) / len(batch)
            for n in charged(x, t):
                if x["left"] <= 0:
                    break
                late = max(0, at - ready(x, n, at)) if x["tick"][n] else None
                visits.append({"at": at, "sid": sid, "title": x["title"], "account": n,
                               "night": bool(win and x["period"] >= kp.NIGHT_MIN_PERIOD),
                               "outside": bool(win and x["period"] >= kp.NIGHT_MIN_PERIOD and not kp._in_window(win, at)),
                               "period_min": x["period"] // 60, "late_sec": late, "queue": len(due), "pos": i + 1})
                x["tick"][n] = at
                x["left"] -= 1
            if x["left"] <= 0:
                del st[sid]
        done = t + dur
        if len(due) > len(batch):
            t = done + BACKLOG_GAP
        else:
            t = done + (max(60, t + TICK - done) if fixed else waitfree_wait(cfg, t, next_charge(done), now=done))
    return {"now": now, "hours": hours, "nums": nums, "titles": cands, "visits": visits, "rounds": rounds,
            "blocks": blocks, "per_title": per_title}


def report(r, out=print, query=None):
    if r is None:
        out("카카오 계정(쿠키)이 없어 계산할 수 없습니다.")
        return
    now, visits, rounds = r["now"], r["visits"], r["rounds"]
    by_p = defaultdict(int)
    for t in r["titles"].values():
        by_p[int(t.get("waitfree_period_min") or 1440)] += 1
    out("■ 기다무 확인 예상 (%s부터 %d시간, 계정 %s)" % (_hm(now), r["hours"], ", ".join(map(str, r["nums"]))))
    out("  대상 작품 %d개: %s" % (len(r["titles"]), " · ".join("%s %d" % (_period_label(m), c) for m, c in sorted(by_p.items()))))
    out("  한 번 확인: 작품당 %.1f초 (30개면 약 %s) · 전체 실행 중: %s" % (
        r["per_title"], _dur(r["per_title"] * 30 + BACKLOG_GAP),
        ("멈춤 " + ", ".join("%s~%s" % (_hm(a), time.strftime("%H:%M", time.localtime(b))) for a, b in r["blocks"]))
        if r["blocks"] else "따로 계속 돎"))
    if not rounds:
        out("  이 기간에 확인할 작품이 없습니다.")
        return

    # 대기열이 다 빠지는 시각: 처음으로 한 번에 다 처리된 확인
    clear = next((t for t, q, b, _d in rounds if q <= b), None)
    out("  지금 대기열: %d개 → %s" % (rounds[0][1], ("%s에 다 빠짐 (%s 뒤)" % (_hm(clear), _dur(clear - now))) if clear
                                     else "이 기간 안에 다 빠지지 않음 - 처리 속도보다 충전이 많음"))

    out("\n[시간대별] 대기열(그 시간 최대) · 확인 횟수 · 대여권 · 지연(평균/최대, 충전 시각을 아는 것만)")
    hours = defaultdict(lambda: {"q": 0, "r": 0, "v": 0, "late": []})
    for t, q, _b, _d in rounds:
        h = hours[int((t - now) // 3600)]
        h["q"], h["r"] = max(h["q"], q), h["r"] + 1
    for v in visits:
        h = hours[int((v["at"] - now) // 3600)]
        h["v"] += 1
        if v["late_sec"] is not None:
            h["late"].append(v["late_sec"])
    for k in sorted(hours):
        h = hours[k]
        lt = h["late"]
        out("  %s  대기 %4d · 확인 %2d번 · 대여권 %3d장 · 지연 %s" % (
            _hm(now + k * 3600), h["q"], h["r"], h["v"],
            ("%s / %s" % (_dur(sum(lt) / len(lt)), _dur(max(lt)))) if lt else "-"))

    out("\n[주기별 지연] 대기열이 빠진 뒤(평소 상태) 기준" if clear else "\n[주기별 지연]")
    per = defaultdict(list)
    for v in visits:
        if v["late_sec"] is not None and (not clear or v["at"] >= clear):
            per[v["period_min"]].append(v["late_sec"])
    for m in sorted(per):
        lt = sorted(per[m])
        out("  %-6s 대여권 %4d장 · 평균 %s · 90%% %s · 최대 %s" % (
            _period_label(m), len(lt), _dur(sum(lt) / len(lt)), _dur(lt[int(len(lt) * 0.9) - 1 if len(lt) > 1 else 0]),
            _dur(lt[-1])))
    if not per:
        out("  (계산할 대여권 사용 없음)")
    nv = [v for v in visits if v.get("night") and (not clear or v["at"] >= clear)]
    if nv:
        out_n = sum(1 for v in nv if v["outside"])
        out("  * 1일 이상 기다무는 새벽 시간대로 미루므로 위 지연에 그 대기가 포함됩니다. 시간대 안에서 쓰면 손해 없음 - "
            "시간대 밖으로 넘친 대여권 %d장 / %d장%s" % (out_n, len(nv), "" if not out_n else " (시간대를 늘리거나 동시 처리 수를 올리세요)"))

    if query:
        q = query.strip().lower()
        mine = [v for v in visits if q == str(v["sid"]) or q in str(v["title"]).lower()]
        out("\n[%s] 예상 대여권 사용" % query)
        for v in mine[:20]:
            out("  %s 계정%d %s  %s · 대기열 %d개 중 %d번째" % (
                _hm(v["at"]), v["account"], v["title"],
                ("충전 후 " + _dur(v["late_sec"])) if v["late_sec"] is not None else "첫 사용",
                v["queue"], v["pos"]))
        if not mine:
            out("  이 기간에 사용 예정 없음 (기다무 대상이 아니거나 충전 전)")


def main(argv):
    from wtm import host, state_store as ss
    from wtm.webtoon_manager import DEFAULTS
    args = list(argv)
    csv_path, full_min = None, None
    fixed = "--fixed" in args  # 예전 동작(5분 간격 고정)으로 계산
    if fixed:
        args.remove("--fixed")
    pause_full = "--pause-full" in args  # 예전 동작(전체 실행 동안 기다무 확인 멈춤)으로 계산
    if pause_full:
        args.remove("--pause-full")
    if "--full-min" in args:  # 전체 실행 소요(분)를 직접 지정 (job.log에 기록이 없을 때)
        i = args.index("--full-min")
        full_min = float(args[i + 1]) if i + 1 < len(args) else None
        del args[i:i + 2]
    if "--csv" in args:
        i = args.index("--csv")
        csv_path = args[i + 1] if i + 1 < len(args) else None
        del args[i:i + 2]
    hours = int(args[0]) if args and args[0].isdigit() else 24
    query = args[1] if len(args) > 1 else (args[0] if args and not args[0].isdigit() else None)
    cfg = dict(DEFAULTS)
    cfg.update({k: v for k, v in host.load_settings().items() if v not in (None, "")})
    if not (cfg.get("KAKAO_ENABLE") and cfg.get("KAKAO_USE_WAITFREE")):
        print("카카오페이지 사용 또는 기다무 대여권 자동 사용이 꺼져 있습니다.")
        return 1
    per_title, samples, full_dur = measure(os.path.join(ss.DATA_DIR, "job.log"))
    if not samples:
        print("(job.log에 기다무 확인 기록이 없어 작품당 %.0f초로 가정)" % per_title)
    if full_min is not None:
        full_dur = full_min * 60
    elif not full_dur and pause_full:
        print("(job.log에 전체 실행 시작~끝 기록이 없어 전체 실행 동안 멈추는 것은 빼고 계산 - "
              "--full-min 분 으로 지정할 수 있음)")
    r = simulate(cfg, hours=hours, per_title=per_title, full_dur=full_dur, pause_full=pause_full, fixed=fixed)
    report(r, query=query)
    if csv_path and r:
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["시각", "작품", "작품번호", "계정", "주기(분)", "지연(분)", "대기열", "순번"])
            for v in r["visits"]:
                w.writerow([time.strftime("%Y-%m-%d %H:%M", time.localtime(v["at"])), v["title"], v["sid"], v["account"],
                            v["period_min"], "" if v["late_sec"] is None else int(v["late_sec"] // 60), v["queue"], v["pos"]])
        print("\nCSV 저장: %s (%d줄)" % (csv_path, len(r["visits"])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
