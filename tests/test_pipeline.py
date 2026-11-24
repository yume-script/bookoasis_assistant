# -*- coding: utf-8 -*-
"""1단계(준비 - 계정과 상관없이) → 2단계(보낼 때 놀고 있는 계정 + 빈 채널) 흐름을 가짜 업로드로 끝까지 (Mirror.run_queue)"""
import asyncio
import os
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="pipeline-test-")
os.environ.setdefault("GDW_ENV_FILE", os.path.join(TMP, ".env"))
os.environ.setdefault("DATA_DIR", os.path.join(TMP, "data"))

try:
    import aiohttp  # noqa: F401
    HAVE_AIOHTTP = True
except ImportError:
    HAVE_AIOHTTP = False


@unittest.skipUnless(HAVE_AIOHTTP, "aiohttp 없음")
class PipelineTest(unittest.TestCase):
    def test_prepare_then_upload_with_idle_account_and_free_channel(self):
        from tgup import compat, plex_to_tg as m
        compat.DATA_DIR = tempfile.mkdtemp(prefix="pipeline-data-")
        m.UPLOAD_GAP_SEC, gap0 = 0, m.UPLOAD_GAP_SEC
        self.addCleanup(setattr, m, "UPLOAD_GAP_SEC", gap0)
        mir = m.Mirror(None, None, lambda *a: None, None)
        mir._route = lambda tg: "direct"

        class Acc:
            async def authorized_client(self):
                return object()

            async def peer(self, ch):
                return ch
        mir.tg_for = lambda tg: Acc()

        async def nothing(*a, **k):
            return 0
        mir._drop_partial = nothing
        mir._resumable = lambda *a: None
        log, prep, sending = [], [0, 0], {}

        async def upload(rule, key, max_gb, test=False):
            # 1단계: 준비 (계정을 잡지 않음 - 여러 줄이 동시에)
            mir.current = {"title": key, "phase": "인코딩 중", "done": 0, "total": 0}
            prep[0] += 1
            prep[1] = max(prep[1], prep[0])
            await asyncio.sleep(0.05)
            prep[0] -= 1
            # 2단계: 놀고 있는 계정 + 그 채널로 보내는 중이 아님
            async with mir._upload_slot() as (tg, client, peer):
                ch = rule["channel"]
                self.assertNotIn(ch, sending)                   # 같은 채널로 동시에 보내지 않음
                self.assertNotIn(tg, sending.values())          # 한 계정은 한 번에 하나
                sending[ch] = tg
                log.append((key, tg, ch))
                await asyncio.sleep(0.05)
                sending.pop(ch)
            return "올림"
        mir.upload = upload
        base = {"tg": "A", "tg_alt": ["B"], "kind": "folder", "enabled": True, "channel_title": "c"}
        rules = [{**base, "id": "r1", "channel": "-1"}, {**base, "id": "r2", "channel": "-2"}]
        st = {"rules": rules, "hours": "", "encode_slots": 1, "max_gb": 2}
        mir.queue = [{"rule": r, "key": k, "title": k} for r, k in (("r1", "k1"), ("r1", "k2"), ("r2", "k3"), ("r2", "k4"))]
        t0 = time.time()
        asyncio.run(mir.run_queue(st))
        self.assertEqual(sorted(k for k, _, _ in log), ["k1", "k2", "k3", "k4"])
        self.assertEqual({tg for _, tg, _ in log}, {"A", "B"})     # 두 계정이 나눠 보냄
        self.assertGreaterEqual(prep[1], 2)                        # 준비는 계정과 상관없이 동시에
        self.assertEqual(mir.queue, [])
        self.assertLess(time.time() - t0, 5)
        hist = m.load_state()["history"]
        self.assertEqual(sorted(h["key"] for h in hist[:4]), ["k1", "k2", "k3", "k4"])
        self.assertTrue(all(h["tg"] in ("A", "B") for h in hist[:4]))

    def test_encode_wait_does_not_block_next_items(self):
        """인코딩 차례를 기다리는 줄은 작업 줄 수에서 빠져 - 그동안 다음 항목(인코딩이 필요 없는 것)을 다른 줄이 처리"""
        from tgup import compat, plex_to_tg as m
        compat.DATA_DIR = tempfile.mkdtemp(prefix="pipeline-enc-")
        m.UPLOAD_GAP_SEC, gap0 = 0, m.UPLOAD_GAP_SEC
        self.addCleanup(setattr, m, "UPLOAD_GAP_SEC", gap0)
        mir = m.Mirror(None, None, lambda *a: None, None)
        mir._route = lambda tg: "direct"

        class Acc:
            async def authorized_client(self):
                return object()

            async def peer(self, ch):
                return ch
        mir.tg_for = lambda tg: Acc()

        async def nothing(*a, **k):
            return 0
        mir._drop_partial = nothing
        mir._resumable = lambda *a: None
        events = []
        data = compat.load()
        data["plex_to_tg"] = m.clean_settings({"encode_slots": 1})
        compat.save(data)

        async def upload(rule, key, max_gb, test=False):
            if key.startswith("e"):   # 인코딩이 필요한 항목
                await mir._encode_slot()
                try:
                    events.append(("enc", key))
                    await asyncio.sleep(0.3)
                finally:
                    mir._encode_done()
            async with mir._upload_slot() as (tg, client, peer):
                events.append(("sent", key))
            return "올림"
        mir.upload = upload
        rules = [{"id": "r1", "tg": "A", "tg_alt": [], "kind": "folder", "enabled": True, "channel_title": "c", "channel": "-1"}]
        st = {"rules": rules, "hours": "", "encode_slots": 1, "max_gb": 2}   # 작업 줄 = 인코딩 1 + 계정 1 = 2
        mir.queue = [{"rule": "r1", "key": k, "title": k} for k in ("e1", "e2", "e3", "n1")]
        asyncio.run(mir.run_queue(st))
        sent = [k for e, k in events if e == "sent"]
        self.assertEqual(sorted(sent), ["e1", "e2", "e3", "n1"])
        # n1(인코딩 없음)은 e2·e3가 인코딩 차례를 기다리는 동안 먼저 올라간다
        self.assertLess(events.index(("sent", "n1")), events.index(("enc", "e2")))
        self.assertLessEqual(len(mir._lane_tasks), 2 + m.ENCODE_BACKLOG)


if __name__ == "__main__":
    unittest.main()
