# -*- coding: utf-8 -*-
"""텔레그램 업로드 속도 제한 감지 (tgup/throttle.py)"""
import logging
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tgup import throttle  # noqa: E402


class ThrottleTest(unittest.TestCase):
    def setUp(self):
        throttle.reset()

    def test_flood_log_per_account(self):
        """Telethon이 혼자 기다린 로그(계정별 로거)를 잡아 '텔레그램 제한'으로 - 프리미엄 아닌 계정의 조각 올리기면 FLOOD_PREMIUM_WAIT"""
        throttle.install()
        throttle.set_premium("a2", False)
        lg = logging.getLogger(throttle.logger_name("a2")).getChild("client.users")
        for _ in range(3):
            lg.info("Sleeping%s for %ds (%s) on %s flood wait", "", 15, "0:00:15", "SaveBigFilePartRequest")
        st = throttle.status("a2")
        self.assertEqual((st["state"], st["waits_1h"], st["wait_sec_1h"], st["upload_waits_1h"]), ("limited", 3, 45, 3))
        self.assertTrue(st["premium_limit"] and "FLOOD_PREMIUM_WAIT" in st["note"])
        self.assertEqual(throttle.status("tg")["state"], "ok")   # 다른 계정은 그대로
        self.assertTrue(throttle.throttled("a2") and not throttle.throttled("tg"))

    def test_slow_without_signal(self):
        """신호 없이 평소의 40% 밑이 3분 넘게면 '느림 의심', 평소 속도는 큰 파일 3개부터"""
        for _ in range(3):
            throttle.done("tg", 100 * 1024 * 1024, 10)          # 평소 ~10.5MB/s
        throttle.done("tg", 1024, 1)                              # 작은 파일은 안 셈
        t0 = 1000.0
        for i in range(0, 241, 10):                               # 4분 동안 1MB/s
            throttle.progress("tg", i * 1_000_000, now=t0 + i)
        st = throttle.status("tg", now=t0 + 240)
        self.assertEqual(st["state"], "slow")
        self.assertAlmostEqual(st["speed"], 1.0, places=1)
        self.assertGreater(st["baseline"], 10)
        throttle.done("tg", 240_000_000, 240)
        self.assertEqual(throttle.status("tg", now=t0 + 250)["state"], "ok")

    def test_fast_is_ok(self):
        for _ in range(3):
            throttle.done("tg", 100 * 1024 * 1024, 10)
        for i in range(0, 61, 10):
            throttle.progress("tg", i * 10_000_000, now=2000.0 + i)
        self.assertEqual(throttle.status("tg", now=2060.0)["state"], "ok")

    def test_mirror_prefers_unthrottled_account(self):
        """제한 걸린 계정은 같이 올릴 수 있는 다른 계정(놀고 있고 제한 없음)에게 다음 항목을 양보"""
        try:
            from tgup import plex_to_tg as m
        except ImportError:
            self.skipTest("aiohttp 없음")
        mir = m.Mirror(None, None, lambda *a: None, None)
        rules = {"r": {"id": "r", "tg": "tg", "tg_alt": ["a2"]}}
        mir.queue = [{"rule": "r", "key": "k1", "title": "t"}]
        throttle.flood("tg", 60, "SaveBigFilePartRequest")
        self.assertIsNone(mir._next_job("tg", rules))             # tg는 제한 - a2가 가져가게
        self.assertEqual(mir._next_job("a2", rules)["key"], "k1")
        throttle.flood("a2", 60, "SaveBigFilePartRequest")
        self.assertEqual(mir._next_job("tg", rules)["key"], "k1")  # 둘 다 제한이면 그냥 가져감


if __name__ == "__main__":
    unittest.main()
