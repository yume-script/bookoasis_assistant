# -*- coding: utf-8 -*-
"""웹툰 다운로더: 실행 시각(crontab), 동영상만 있는 회차, 스캔본 웹소설 - python3 -m unittest discover -s tests"""
import os
import sys
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from wtm import cronspec  # noqa: E402


class CronTest(unittest.TestCase):
    def setUp(self):
        self.now = time.mktime((2026, 11, 17, 13, 5, 0, 0, 0, -1))   # 화요일 13:05

    def at(self, expr):
        return time.strftime("%a %H:%M", time.localtime(cronspec.next_after(expr, self.now)))

    def test_next_and_due(self):
        self.assertEqual(self.at("0 */4 * * *"), "Tue 16:00")
        self.assertEqual(self.at("*/30 9-23 * * *"), "Tue 13:30")
        self.assertEqual(self.at("0 6 * * 1-5"), "Wed 06:00")
        self.assertEqual(self.at("0 6 * * sat,sun"), "Sat 06:00")
        self.assertEqual(self.at("0 6 * * 7"), "Sun 06:00")
        slot = cronspec.due("0 */4 * * *", self.now - 3 * 3600, self.now)   # 12:00이 지나감 -> 한 번
        self.assertEqual(time.strftime("%H:%M", time.localtime(slot)), "12:00")
        self.assertIsNone(cronspec.due("0 */4 * * *", slot, self.now))

    def test_errors_and_migration(self):
        for bad in ("* * *", "61 * * * *", "x * * * *", "5-1 * * * *"):
            with self.assertRaises(cronspec.CronError):
                cronspec.parse(bad)
        with self.assertRaises(cronspec.CronError):
            cronspec.validate("0 0 31 2 *")
        self.assertEqual([cronspec.from_interval(m) for m in (10, 60, 240, 1440, "x")],
                         ["*/10 * * * *", "0 * * * *", "0 */4 * * *", "0 0 * * *", cronspec.DEFAULT])

    def test_scheduler_uses_cron(self):
        from wtm import scheduler
        cfg = {"SCHEDULE_CRON": "0 */4 * * *"}
        due, slot = scheduler._cycle_due(cfg, {"cron_slot": self.now - 3 * 3600}, 240, now=self.now)
        self.assertTrue(due and slot)
        self.assertEqual(scheduler._cycle_due(cfg, {"cron_slot": slot}, 240, now=self.now), (False, None))
        # 비우면 예전처럼 주기(분)
        self.assertEqual(scheduler._cycle_due({}, {"last_scan_at": self.now - 300}, 10, now=self.now), (False, None))


class VideoAndScanTest(unittest.TestCase):
    def test_kakao_video_only_and_scans(self):
        from wtm import kakao_api as k
        orig = k._fetch_viewer
        self.addCleanup(setattr, k, "_fetch_viewer", orig)
        self.assertTrue(k.video_only({"type": "Video", "videoData": {"url": "x"}}))
        self.assertFalse(k.video_only({"imageDownloadData": {"files": [{"no": 1, "secureUrl": "u"}]}}))
        self.assertFalse(k.video_only({"contents_list": [{}]}))
        self.assertTrue(issubclass(k.KakaoVideoOnly, k.KakaoSkip))

        class R:
            content, headers = b"img", {"Content-Type": "image/jpeg"}

            def raise_for_status(self):
                pass

        class S:
            request_timeout = 5

            def get(self, url, **kw):
                return R()
        k._fetch_viewer = lambda *a: {"imageDownloadData": {"files": [{"no": 2, "secureUrl": "b"}, {"no": 1, "secureUrl": "a"}]}}
        d = k.fetch_novel_episode(S(), "1", "2")
        self.assertTrue(d["scan"])
        self.assertEqual(list(d["images"]), ["page0001.jpg", "page0002.jpg"])
        k._fetch_viewer = lambda *a: {"type": "VIDEO", "video": {"id": 1}}
        with self.assertRaises(k.KakaoVideoOnly):
            k.fetch_novel_episode(S(), "1", "2")
        with self.assertRaises(k.KakaoVideoOnly):
            k.fetch_episode_images(S(), "1", "2")

    def test_naver_video_marker(self):
        from wtm import naver_api
        self.assertTrue(naver_api._VIDEO_RE.search('<div class="videoPlayer"></div>'))
        self.assertFalse(naver_api._VIDEO_RE.search('<img src="a.jpg">'))


class EmptyEpisodeTest(unittest.TestCase):
    def test_kakao_no_body(self):
        from wtm import kakao_api as k
        orig = k._fetch_viewer
        self.addCleanup(setattr, k, "_fetch_viewer", orig)
        self.assertTrue(issubclass(k.KakaoNoBody, k.KakaoNotPurchased))   # 유료 회차면 예전처럼 '볼 수 없는 회차'
        k._fetch_viewer = lambda *a: {"type": "Image"}
        with self.assertRaises(k.KakaoNoBody):
            k.fetch_episode_images(None, "1", "2")
        with self.assertRaises(k.KakaoNoBody):   # 예전엔 KakaoUnsupported로 작품 전체를 멈췄다
            k.fetch_novel_episode(None, "1", "2")

    def test_naver_empty_episode(self):
        from wtm import downloader, naver_api
        orig = naver_api._get
        self.addCleanup(setattr, naver_api, "_get", orig)

        class Resp:
            url = "https://comic.naver.com/webtoon/detail?titleId=1&no=2"

        def page(html):
            r = Resp()
            r.text = html
            return lambda *a, **kw: r
        naver_api._get = page('<div class="wt_viewer"><p>휴재 안내</p></div>')
        with self.assertRaises(naver_api.NaverEmptyEpisode):
            naver_api.fetch_episode_images(None, 1, 2)
        naver_api._get = page("<html><body>다른 모양</body></html>")   # 본문 자리도 없음 - 예전처럼 실패
        with self.assertRaises(ValueError):
            naver_api.fetch_episode_images(None, 1, 2)
        import tempfile
        d = tempfile.mkdtemp()
        naver_api._get = page('<div class="wt_viewer"></div>')
        ok, skipped, cnt, err = downloader.download_episode(None, d, d, "작품", 1, 2)
        self.assertEqual((ok, skipped, cnt), (True, True, 0))
        self.assertTrue(err.startswith(downloader.EMPTY_PREFIX) and "본문 없는" in err)

    def test_notify_text(self):
        from wtm import discord_notify
        sent = []
        orig = discord_notify.notify
        self.addCleanup(setattr, discord_notify, "notify", orig)
        discord_notify.notify = lambda cfg, title, desc, **kw: sent.append((title, desc)) or (True, "ok")
        discord_notify.notify_empty_episodes({}, "[카카오웹툰]", "작품", [(3, "공지", "본문 없는 회차"),
                                                                     ("특별 회차", "작가 후기", "본문 없는 회차")])
        title, desc = sent[0]
        self.assertIn("받을 본문이 없는 회차 2개", title)
        self.assertIn("· 3화 (공지) - 본문 없는 회차", desc)
        self.assertIn("· 특별 회차 (작가 후기)", desc)
        self.assertIn("받은 것으로 처리", desc)


class DailyPlanTest(unittest.TestCase):
    """기다무 하루 계획표: 1시간·3시간은 주기마다, 1일은 한 번, 2일·3일은 오늘 충전되는 날만"""

    def test_build(self):
        from wtm import daily_plan as dp, kakao_pipeline as kp
        now = time.mktime((2026, 11, 18, 0, 5, 0, 0, 0, -1))   # 0시 5분 (계획 시각 0시)
        start = time.mktime((2026, 11, 18, 0, 0, 0, 0, 0, -1))
        H = 3600
        titles = {   # sid: (주기 분, 다음 충전 = 하루 시작 + 몇 시간)
            "h1": (60, 0.5), "h3": (180, 2), "h6": (360, -5), "d1": (1440, 9),
            "d2_today": (2880, 20), "d2_tomorrow": (2880, 30), "d3_today": (4320, 1)}
        cands = {sid: {"title": sid, "waitfree_period_min": p} for sid, (p, _h) in titles.items()}
        saved = {}
        orig = (kp._waitfree_candidates, kp.ready_at, kp.night_info)
        kp._waitfree_candidates = lambda cfg: ([1], dict(cands))
        kp.ready_at = lambda cfg, t, n, now=None, night=None, nums=None: start + titles[t["title"]][1] * H
        kp.night_info = lambda cfg, now=None: None
        from wtm import pipeline as pl, state_store as ss
        orig_ss = (ss.load_job_state, ss.save_job_state, ss.load_titles)
        ss.load_job_state = lambda: dict(saved)
        ss.save_job_state = lambda patch: saved.update(patch)
        # 네이버: 수요일(2026-11-18) 연재작, 목요일 연재작, 매일+ - 확인 시각은 작품마다 (분)
        naver = {"101": {"title": "수요웹툰", "subscribed": True, "weekdays": ["wed"], "check_slot_min": 13 * 60},
                 "102": {"title": "목요웹툰", "subscribed": True, "weekdays": ["thu"], "check_slot_min": 15 * 60},
                 "103": {"title": "매일웹툰", "subscribed": True, "weekdays": ["dailyPlus"], "check_slot_min": 6 * 60},
                 "104": {"title": "구독해제", "subscribed": False, "weekdays": ["wed"]}}
        ss.load_titles = lambda: dict(naver)
        try:
            cfg = {"WAITFREE_DAILY_PLAN": True, "WAITFREE_PLAN_HOUR": 0}
            plan = dp.current(cfg, now)
            items, skipped = plan["items"], plan["skipped"]
            self.assertEqual(len(items["h1"]["slots"]), 24)                    # 1시간 기다무: 24번 (00:30부터)
            self.assertEqual([(x - start) / H for x in items["h3"]["slots"]], [2, 5, 8, 11, 14, 17, 20, 23])
            self.assertEqual((items["h6"]["slots"][0] - start) / H, 0)        # 지난 충전을 못 씀 -> 계획 시작에
            self.assertEqual(len(items["h6"]["slots"]), 4)
            self.assertEqual(len(items["d1"]["slots"]), 1)                     # 1일: 한 번
            self.assertIn("d2_today", items)
            self.assertIn("d3_today", items)
            self.assertIn("d2_tomorrow", skipped)                              # 오늘 충전 안 됨 -> 뺌
            self.assertNotIn("d2_tomorrow", items)
            self.assertEqual(set(dp.allowed(cfg, cands, now)), set(cands) - {"d2_tomorrow"})
            self.assertEqual(set(dp.allowed({}, cands, now)), set(cands))      # 끄면 그대로
            # 계획을 짠 뒤 새로 생긴 작품은 오늘 계획에 더한다
            titles["new3"] = (180, 4)
            cands["new3"] = {"title": "new3", "waitfree_period_min": 180}
            self.assertIn("new3", dp.current(cfg, now + 600)["items"])
            # 다음 날 0시가 지나면 새로 짠다
            self.assertNotEqual(dp.current(cfg, now + 86400)["start"], plan["start"])
            self.assertIn("오늘 쉼", dp.summary(plan))
            # 네이버: 오늘 연재일인 작품만 정한 시각에, 아니면 뺌
            self.assertEqual(set(plan["naver"]), {"101", "103"})
            self.assertEqual((plan["naver"]["101"]["slot"] - start) / H, 13)
            self.assertIn("102", plan["naver_skipped"])
            self.assertEqual(time.localtime(plan["naver_skipped"]["102"]["next"]).tm_mday, 19)   # 다음 목요일 = 11/19
            self.assertNotIn("104", plan["naver"])
            n101 = dict(naver["101"], last_downloaded_no=10)
            self.assertFalse(dp.naver_due(cfg, "101", n101, start + 12 * H))                 # 확인 시각 전
            self.assertTrue(dp.naver_due(cfg, "101", n101, start + 13.5 * H))                # 시각이 지났고 안 봄
            self.assertFalse(dp.naver_due(cfg, "101", dict(n101, last_auto_check_at=start + 13.2 * H), start + 14 * H))
            self.assertFalse(dp.naver_due(cfg, "102", dict(naver["102"], last_downloaded_no=3), start + 16 * H))   # 오늘 연재 아님
            self.assertTrue(pl.in_new_episode_scope(cfg, n101, "naver", start + 13.5 * H, tid="101"))
            self.assertIn("네이버 연재일 확인 2개", dp.summary(plan))
        finally:
            kp._waitfree_candidates, kp.ready_at, kp.night_info = orig
            ss.load_job_state, ss.save_job_state, ss.load_titles = orig_ss


if __name__ == "__main__":
    unittest.main()
