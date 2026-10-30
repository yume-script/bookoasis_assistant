# -*- coding: utf-8 -*-
"""작품 분류와 수량 - 어떤 작품을 얼마나 자주 확인해야 하는지 (네이버 / 카카오웹툰 / 카카오웹소설)

    venv/bin/python -m wtm.classify            분류별 작품 수와 하루 확인 횟수
    venv/bin/python -m wtm.classify --list     분류마다 작품 이름도 (앞 20개)

분류 (구독 중이거나 구매한 작품만, 제외·구독 해제는 뺌):
- 네이버: 하루 1번
- 카카오웹툰·카카오웹소설 기다무:
  - 남은 회차(전체 회차 - 받은 마지막 회차)가 10개 넘음: 기다무 주기마다 (1시간 기다무면 1시간마다, 12시간이면 12시간마다)
  - 남은 회차가 10개 이하: 하루 1번 (최신 10화는 기다무 대여권으로 열 수 없어 새 회차만 받으면 됨)
  - 1일 이상 기다무(1·2·3·7일): 남은 회차와 상관없이 하루 1번
- 카카오 기다무가 아닌 작품: 하루 1번
'하루 확인 횟수'는 작품 수 × (24시간 / 주기) - 계정이 여럿이면 계정마다 대여권이 따로라 실제 대여권 사용은 그 배수다.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

LATEST_EXCLUDED = 10
DAY_MIN = 1440


def _active(t):
    return (t.get("subscribed") or t.get("purchased")) and not t.get("excluded") and not t.get("unsubscribed")


def _period_label(pm):
    if pm % DAY_MIN == 0:
        return "%d일 기다무" % (pm // DAY_MIN)
    if pm % 60 == 0:
        return "%d시간 기다무" % (pm // 60)
    return "%d분 기다무" % pm


def remaining(t):
    """남은 회차 (전체 회차 - 받은 마지막 회차). 전체 회차를 모르면 None"""
    if not t.get("episode_count"):
        return None
    return max(0, int(t["episode_count"]) - int(t.get("last_downloaded_no") or 0))


def classify(cfg=None):
    """[(플랫폼, 분류 이름, 확인 주기(분), 작품 [(id, 제목, 남은 회차)])] - 표시 순서대로"""
    from wtm import kakao_pipeline as kp, state_store as ss
    groups = {}

    def add(platform, name, every_min, order, tid, t):
        g = groups.setdefault((platform, name), {"every": every_min, "order": order, "items": []})
        g["items"].append((tid, t.get("title") or tid, remaining(t)))

    for tid, t in ss.load_titles().items():
        if _active(t):
            add("네이버웹툰", "하루 1번 확인", DAY_MIN, (0, 0, 0), tid, t)
    for sid, t in ss.load_kakao_titles().items():
        if not _active(t):
            continue
        platform = "카카오웹소설" if kp._is_novel(t) else "카카오웹툰"
        pidx = 2 if platform == "카카오웹소설" else 1
        if not t.get("waitfree"):
            add(platform, "기다무 아님 · 하루 1번", DAY_MIN, (pidx, 9, 0, 0), sid, t)
            continue
        pm = max(1, int(t.get("waitfree_period_min") or DAY_MIN))
        left = remaining(t)
        label = _period_label(pm)
        if pm >= DAY_MIN:
            add(platform, "%s · 하루 1번" % label, DAY_MIN, (pidx, 1, pm, 0), sid, t)
        elif left is None:
            add(platform, "%s · 회차 수 모름 → %s마다" % (label, label.split()[0]), pm, (pidx, 0, pm, 2), sid, t)
        elif left > LATEST_EXCLUDED:
            add(platform, "%s · 남은 회차 %d개 넘음 → %s마다" % (label, LATEST_EXCLUDED, label.split()[0]), pm,
                (pidx, 0, pm, 0), sid, t)
        else:
            add(platform, "%s · 남은 회차 %d개 이하 → 하루 1번" % (label, LATEST_EXCLUDED), DAY_MIN, (pidx, 0, pm, 1), sid, t)
    out = []
    for (platform, name), g in sorted(groups.items(), key=lambda kv: kv[1]["order"]):
        out.append((platform, name, g["every"], sorted(g["items"], key=lambda x: str(x[1]))))
    return out


def main(argv):
    from gdw import config
    config.load_env()
    config.utf8_console()
    os.environ.setdefault("WTM_HOST", "1")
    from wtm import kakao_pipeline as kp, host
    show = "--list" in argv
    rows = classify()
    n_acc = max(1, len(kp.accounts(host.load_settings())))
    print("■ 작품 분류와 수량 (구독·구매 중인 작품, 카카오 계정 %d개)" % n_acc)
    cur = None
    tot_titles = tot_checks = 0
    sub = {}
    for platform, name, every, items in rows:
        if platform != cur:
            if cur is not None:
                print("    %-44s %6d개   하루 %7.0f번" % ("(소계)", sub[cur][0], sub[cur][1]))
            cur = platform
            sub[cur] = [0, 0.0]
            print("\n  [%s]" % platform)
        per_day = len(items) * (DAY_MIN / float(every))
        sub[cur][0] += len(items)
        sub[cur][1] += per_day
        tot_titles += len(items)
        tot_checks += per_day
        print("    %-44s %6d개   하루 %7.0f번" % (name, len(items), per_day))
        if show:
            for tid, title, left in items[:20]:
                print("        - %s (남은 회차 %s)" % (title, "?" if left is None else left))
            if len(items) > 20:
                print("        … 외 %d개" % (len(items) - 20))
    if cur is not None:
        print("    %-44s %6d개   하루 %7.0f번" % ("(소계)", sub[cur][0], sub[cur][1]))
    print("\n  합계 %d개 · 하루 확인 %.0f번 (카카오 기다무 대여권은 계정마다 따로라 최대 계정 수 배)" % (tot_titles, tot_checks))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
