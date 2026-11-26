# -*- coding: utf-8 -*-
"""카카오 기다무 처리량: 순서(주기 몇 번만큼 늦었나), 한 번에 처리할 수, 밀린 동안 kavita.yaml 미루기"""
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from wtm import kakao_pipeline as kp, state_store as ss  # noqa: E402

H = 3600


class OrderTest(unittest.TestCase):
    def test_order_key_prefers_short_period_when_equally_late(self):
        now = 1_000_000
        three_h = kp.order_key([now - 12 * H], 3 * H, now)       # 3시간 기다무 12시간 늦음 = 주기 4번
        one_day = kp.order_key([now - 30 * H], 24 * H, now)      # 1일 기다무 30시간 늦음 = 주기 1.25번
        never = kp.order_key([], 24 * H, now)                    # 처음 쓰는 작품 (충전 시각 모름)
        self.assertLess(three_h, one_day)
        self.assertLess(one_day, never)
        very_late_day = kp.order_key([now - 100 * H], 24 * H, now)   # 1일 기다무도 많이 밀리면 앞으로 (굶지 않게)
        self.assertLess(very_late_day, three_h)

    def test_waitfree_order_uses_period(self):
        now = 2_000_000
        cfg = {}
        old = (kp.accounts, kp.ready_at, kp._ticket_at, kp.waitfree_period)
        self.addCleanup(lambda: setattr(kp, "accounts", old[0]) or setattr(kp, "ready_at", old[1])
                        or setattr(kp, "_ticket_at", old[2]) or setattr(kp, "waitfree_period", old[3]))
        kp.accounts = lambda c: [(1, "c")]
        kp._ticket_at = lambda t, n: t.get("used")
        kp.ready_at = lambda c, t, n, now=None: t["ready"]
        kp.waitfree_period = lambda t: t["period"]
        due = {"day": {"used": 1, "ready": now - 30 * H, "period": 24 * H},
               "three": {"used": 1, "ready": now - 12 * H, "period": 3 * H},
               "new": {"used": 0, "ready": now, "period": 3 * H}}
        self.assertEqual([sid for sid, _ in kp.waitfree_order(cfg, due, now)], ["three", "day", "new"])

    def test_tick_max_scales_with_parallel(self):
        self.assertEqual(kp.tick_max({}), 30)
        self.assertEqual(kp.tick_max({"PARALLEL_TITLES": 6}), 60)
        self.assertEqual(kp.tick_max({"PARALLEL_TITLES": 99}), 100)


class DeferYamlTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="wtm-yaml-")
        self.addCleanup(shutil.rmtree, self.d, True)
        self._data = ss.DATA_DIR
        ss.DATA_DIR = self.d
        self.addCleanup(setattr, ss, "DATA_DIR", self._data)
        self.saved = {k: getattr(kp, k) for k in ("extra_accounts", "download_series", "update_yaml", "build_session_from_cfg")}
        self.addCleanup(lambda: [setattr(kp, k, v) for k, v in self.saved.items()])
        self.written = []
        kp.update_yaml = lambda cfg, sid, session, log=print: self.written.append(sid)
        kp.build_session_from_cfg = lambda cfg: object()

    def test_single_account_defers_then_flushes(self):
        kp.extra_accounts = lambda cfg: []
        seen = []

        def ds(cfg, session, sid, log=print, yaml=True, **kw):
            seen.append(yaml)
            return {"downloaded": 1, "yaml_due": not yaml, "locked": 0, "failures": []}
        kp.download_series = ds
        kp._download_series_all({}, None, "111", log=lambda *a: None, defer_yaml=True)
        self.assertEqual((seen, self.written, kp.yaml_pending()), ([False], [], ["111"]))
        kp._download_series_all({}, None, "222", log=lambda *a: None, defer_yaml=False)
        self.assertEqual(seen[-1], True)                       # 밀리지 않았으면 예전처럼 바로 (download_series 안에서)
        self.assertEqual(kp.flush_pending_yaml({}, log=lambda *a: None), 1)
        self.assertEqual((self.written, kp.yaml_pending()), (["111"], []))

    def test_two_accounts_defer(self):
        kp.extra_accounts = lambda cfg: [(2, "cookie2")]
        kp.download_series = lambda cfg, session, sid, log=print, yaml=True, **kw: {
            "downloaded": 1, "yaml_due": True, "locked": 0, "failures": []}
        kp._download_series_all({}, None, "333", log=lambda *a: None, defer_yaml=True)
        self.assertEqual((self.written, kp.yaml_pending()), ([], ["333"]))
        kp._download_series_all({}, None, "444", log=lambda *a: None)
        self.assertEqual(self.written, ["444"])                # 밀리지 않았으면 작품 끝에 바로


if __name__ == "__main__":
    unittest.main()
