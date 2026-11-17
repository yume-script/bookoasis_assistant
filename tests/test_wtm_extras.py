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


if __name__ == "__main__":
    unittest.main()
