# -*- coding: utf-8 -*-
"""텔레그램 업로드 규칙: 같은 채널 동시 올리기 금지 · 다른 채널 먼저 · FLOOD_WAIT면 그 계정만 쉬고 항목은 제자리 ·
그래도 같은 채널이면 경로가 다른 계정(직접 + 프록시)만 같이 (tgup/plex_to_tg.py Mirror._next_job, tgup/tgaccount.py 프록시)"""
import asyncio
import os
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="chanrule-test-")
os.environ.setdefault("GDW_ENV_FILE", os.path.join(TMP, ".env"))
os.environ.setdefault("DATA_DIR", os.path.join(TMP, "data"))

try:
    import aiohttp  # noqa: F401
    HAVE_AIOHTTP = True
except ImportError:
    HAVE_AIOHTTP = False

from tgup import tgaccount  # noqa: E402


class ProxyTest(unittest.TestCase):
    def test_clean_and_public(self):
        self.assertEqual(tgaccount.clean_proxy(""), "")
        for ok in ("socks5://1.2.3.4:1080", "socks5://u:p@host.example:1080", "http://h:8080", "socks4://h:1", "mtproxy://ee11@h:443"):
            self.assertEqual(tgaccount.clean_proxy(ok), ok)
        for bad in ("1.2.3.4:1080", "ftp://h:1", "socks5://h", "socks5://h:99999", "mtproxy://h:443"):
            with self.assertRaises(ValueError):
                tgaccount.clean_proxy(bad)
        self.assertEqual(tgaccount.proxy_public("socks5://u:secret@h:1080"), "socks5://u:***@h:1080")
        self.assertEqual(tgaccount.proxy_public("mtproxy://ee11@h:443"), "mtproxy://***@h:443")
        self.assertEqual(tgaccount.proxy_public("http://h:8080"), "http://h:8080")

    def test_client_args(self):
        self.assertEqual(tgaccount.client_proxy_args(""), {})
        try:
            import python_socks  # noqa: F401
        except ImportError:
            with self.assertRaises(tgaccount.TgError):
                tgaccount.client_proxy_args("socks5://h:1")
            return
        a = tgaccount.client_proxy_args("socks5://u:p@h:1080")["proxy"]
        self.assertEqual((a["proxy_type"], a["addr"], a["port"], a["username"], a["password"]), ("socks5", "h", 1080, "u", "p"))


class OfflineStatusTest(unittest.TestCase):
    """텔레그램에 잠깐 못 닿을 때 "로그인 안 됨"으로 보이지 않게 - 마지막으로 확인한 로그인 상태 + offline"""

    def test_offline_keeps_last_auth(self):
        acc = tgaccount.TelegramAccount("tg")
        st = acc.offline_status({"id": "tg", "authorized": False}, "연결 실패")
        self.assertEqual((st["authorized"], st["offline"]), (None, True))      # 처음: 모름 (로그인 화면 안 띄움)
        acc.last_auth = {"name": "포링", "premium": True}
        st = acc.offline_status({"id": "tg", "authorized": False}, "연결 실패")
        self.assertEqual((st["authorized"], st["name"], st["offline"]), (True, "포링", True))
        acc.last_auth = False
        self.assertFalse(acc.offline_status({"id": "tg", "authorized": False}, "x")["authorized"])

        async def fail():
            raise ConnectionError("Connection to Telegram failed 2 time(s)")
        acc.last_auth = {"name": "포링", "premium": False}
        acc.get_client = fail
        st = asyncio.run(acc.status())
        self.assertTrue(st["authorized"] and st["offline"])
        self.assertIn("Connection to Telegram failed", st["error"])


@unittest.skipUnless(HAVE_AIOHTTP, "aiohttp 없음")
class ChannelRuleTest(unittest.TestCase):
    def setUp(self):
        from tgup import plex_to_tg as m
        self.m = m
        self.mir = m.Mirror(None, None, lambda *a: None, None)
        self.routes = {"A": "direct", "B": "direct", "P": "socks5://h:1"}
        self.mir._route = lambda tg: self.routes[tg]
        self.rules = {"x": {"id": "x", "tg": "A", "tg_alt": ["B", "P"], "channel": "-100"},
                      "y": {"id": "y", "tg": "A", "tg_alt": ["B", "P"], "channel": "-200"}}

    def job(self, rule, key):
        j = {"rule": rule, "key": key, "title": key}
        self.mir.queue.append(j)
        return j

    def busy(self, wid, rule):
        """작업 줄 wid가 그 규칙의 항목을 처리 중 (받기·인코딩·보내기 어느 단계든)"""
        ln = self.mir.lanes.setdefault(wid, self.m.Lane(""))
        ln.channel, ln.current_job = self.rules[rule]["channel"], {"rule": rule, "key": "?"}

    def test_other_channel_first(self):
        x1, x2, y1 = self.job("x", "x1"), self.job("x", "x2"), self.job("y", "y1")
        self.mir._taken.add(id(x1))
        self.busy("w1", "x")
        me = self.m.Lane("")
        self.assertIs(self.mir._next_job(self.rules, me), y1)   # -100은 w1이 처리 중 -> 다른 채널(-200)을 먼저
        self.mir._taken.add(id(y1))
        self.assertIs(self.mir._next_job(self.rules, me), x2)   # 다른 채널이 없으면 같은 채널도 가져가 준비(받기·인코딩)는 한다
        self.mir._down["A"] = (time.time() + 60, "x")
        self.mir._down["B"] = (time.time() + 60, "x")
        self.mir._down["P"] = (time.time() + 60, "x")
        self.assertIsNone(self.mir._next_job(self.rules, me))   # 올릴 계정이 모두 쉬면 준비도 하지 않음 (줄을 잡고 기다리지 않게)

    def test_upload_slot_picks_idle_account_and_free_channel(self):
        """2단계: 놀고 있는 계정 + 그 채널로 보내는 중이 아님 - 같은 경로면 기다리고, 경로가 다르면(프록시) 같이"""
        m, mir = self.m, self.mir
        m.UPLOAD_GAP_SEC, gap0 = 0, m.UPLOAD_GAP_SEC
        self.addCleanup(setattr, m, "UPLOAD_GAP_SEC", gap0)

        class Acc:
            async def authorized_client(self):
                return object()

            async def peer(self, ch):
                return ch
        mir.tg_for = lambda tg: Acc()
        order = []

        async def send(wid, rule_tgs, hold):
            lane = mir.lanes.setdefault(wid, m.Lane(""))
            lane.rule = {"id": wid, "tg": rule_tgs[0], "tg_alt": rule_tgs[1:], "channel": "-100"}
            lane.job, lane.channel = {"rule": wid, "key": wid}, "-100"
            m._LANE.set(lane)
            async with mir._upload_slot() as (tg, client, peer):
                order.append(("start", wid, tg))
                await asyncio.sleep(hold)
                order.append(("end", wid, tg))

        async def run():
            a = asyncio.ensure_future(send("w1", ["A"], 0.2))
            await asyncio.sleep(0.02)
            b = asyncio.ensure_future(send("w2", ["A", "B"], 0.01))   # A는 보내는 중, B는 직접 경로 -> 그 채널에 직접이 있어 기다림
            p = asyncio.ensure_future(send("w3", ["A", "P"], 0.01))   # P는 프록시 경로 -> 바로 같이
            await asyncio.gather(a, b, p)
        asyncio.run(run())
        starts = {w: (i, tg) for i, (k, w, tg) in enumerate(order) if k == "start"}
        end_a = order.index(("end", "w1", "A"))
        self.assertEqual(starts["w3"][1], "P")
        self.assertLess(starts["w3"][0], end_a)
        self.assertGreater(starts["w2"][0], end_a)
        self.assertEqual(mir._uploading, {})
        self.assertEqual(mir._chan_routes, {})

    def test_flood_wait_rests_account_and_keeps_job(self):
        m = self.m
        rule = {"id": "x", "tg": "A", "tg_alt": [], "channel": "-100", "channel_title": "c", "kind": "folder"}
        job = self.job("x", "x1")

        class FloodWaitError(Exception):
            seconds = 120

        async def boom(*a, **k):
            raise FloodWaitError("wait")
        self.mir.upload = boom

        async def nothing(*a, **k):
            return None
        self.mir._drop_partial = nothing
        self.mir._resumable = lambda *a: None

        async def run():
            lane = m.Lane("A")
            m._LANE.set(lane)
            await self.mir._run_job(lane, job, rule, {"max_gb": 2})
            return lane
        before = len(m.load_state().get("history") or [])
        lane = asyncio.run(run())
        self.assertIn(job, self.mir.queue)                               # 항목은 진행 목록 제자리
        self.assertIn("FLOOD_WAIT", self.mir._is_down("A"))              # 이 계정만 쉼
        self.assertGreater(lane.flood_until, time.time() + 100)
        self.assertEqual(len(m.load_state().get("history") or []), before)   # 실패로 남기지 않음


if __name__ == "__main__":
    unittest.main()
