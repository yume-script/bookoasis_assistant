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

    def busy(self, tg, rule):
        """그 계정 줄이 그 규칙의 항목을 처리 중 (받기·인코딩·보내기 어느 단계든)"""
        ln = self.mir.lanes.setdefault(tg, self.m.Lane(tg))
        ln.channel, ln.current_job = self.rules[rule]["channel"], {"rule": rule, "key": "?"}

    def test_other_channel_first(self):
        x1, x2, y1 = self.job("x", "x1"), self.job("x", "x2"), self.job("y", "y1")
        self.mir._taken.add(id(x1))
        self.busy("A", "x")
        self.assertIs(self.mir._next_job("B", self.rules), y1)   # -100은 A가 처리 중 -> 다른 채널(-200)을 먼저
        self.mir._taken.add(id(y1))
        self.assertIs(self.mir._next_job("B", self.rules), x2)   # 다른 채널이 없으면 같은 채널도 가져가 받기·인코딩은 한다
        self.assertEqual(self.mir._waiting_accounts(self.rules), ["A", "B", "P"])   # 줄은 막지 않는다 (보내기에서 차례)

    def test_send_gate_same_route_waits_other_route_shares(self):
        m, mir = self.m, self.mir
        order = []

        async def send(tg, name, hold):
            lane = mir.lanes.setdefault(tg, m.Lane(tg))
            lane.channel = "-100"
            m._LANE.set(lane)
            async with mir._channel_gate():
                order.append(("start", name))
                await asyncio.sleep(hold)
                order.append(("end", name))

        async def run():
            a = asyncio.ensure_future(send("A", "A", 0.2))
            await asyncio.sleep(0.02)
            b = asyncio.ensure_future(send("B", "B", 0.01))   # A와 같은 경로(직접) -> A가 끝날 때까지 기다림
            p = asyncio.ensure_future(send("P", "P", 0.01))   # 프록시 경로 -> 바로 같이
            await asyncio.gather(a, b, p)
        asyncio.run(run())
        self.assertLess(order.index(("start", "P")), order.index(("end", "A")))
        self.assertGreater(order.index(("start", "B")), order.index(("end", "A")))
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
