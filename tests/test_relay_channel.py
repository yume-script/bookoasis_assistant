# -*- coding: utf-8 -*-
"""임시 채널: 한 채널에 계정 A가 올리는 동안 놀고 있는 B는 임시 채널로 올리고 -> 원래 채널로 옮기고(전달) -> 임시 채널에서 지운다"""
import asyncio
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="relay-test-")
os.environ.setdefault("GDW_ENV_FILE", os.path.join(TMP, ".env"))
os.environ.setdefault("DATA_DIR", os.path.join(TMP, "data"))

try:
    import aiohttp  # noqa: F401
    HAVE_AIOHTTP = True
except ImportError:
    HAVE_AIOHTTP = False


class Msg:
    def __init__(self, i):
        self.id = i


class Client:
    def __init__(self, name, world, deny_post=()):
        self.name, self.world, self.deny_post = name, world, set(deny_post)

    async def forward_messages(self, dst, ids, from_peer=None, drop_author=None):
        if dst in self.deny_post:
            raise type("ChatWriteForbiddenError", (Exception,), {})("no")
        assert drop_author is True
        out = []
        for i in ids:
            self.world["n"] += 1
            self.world["posts"].setdefault(dst, []).append(("fwd", from_peer, i, self.name))
            out.append(Msg(self.world["n"]))
        return out

    async def delete_messages(self, peer, ids):
        self.world["deleted"].append((peer, list(ids)))


@unittest.skipUnless(HAVE_AIOHTTP, "aiohttp 없음")
class RelayTest(unittest.TestCase):
    def setUp(self):
        from tgup import compat, plex_to_tg as m
        self.m = m
        compat.DATA_DIR = tempfile.mkdtemp(prefix="relay-data-")
        m.UPLOAD_GAP_SEC, gap0 = 0, m.UPLOAD_GAP_SEC
        self.addCleanup(setattr, m, "UPLOAD_GAP_SEC", gap0)

    def make(self, relay="-9", deny=None, accounts=("A", "B"), keys=("k1", "k2"), slow=None):
        m = self.m
        world = {"n": 1000, "posts": {}, "deleted": [], "sent": []}
        mir = m.Mirror(None, None, lambda *a: None, None)
        mir._route = lambda tg: "direct"
        clients = {a: Client(a, world, (deny or {}).get(a, ())) for a in accounts}

        class Acc:
            def __init__(self, a):
                self.a = a

            async def authorized_client(self):
                return clients[self.a]

            async def peer(self, ch):
                return str(ch)
        mir.tg_for = lambda tg: Acc(tg)

        async def nothing(*a, **k):
            return 0
        mir._drop_partial = nothing
        mir._resumable = lambda *a: None

        async def send_now(client, peer, pieces, *rest):
            msgs = rest[-1]
            for p in pieces:   # 영상 + 자막 하나씩
                world["n"] += 1
                vid = world["n"]
                world["posts"].setdefault(peer, []).append(("up", None, vid, client.name))
                msgs.append(vid)
                mir._note_sent(vid)
                world["n"] += 1
                mir._note_sent(world["n"])
                world.setdefault("live", set()).add(client.name)
                world["most"] = max(world.get("most", 0), len(world["live"]))
                await asyncio.sleep((slow or {}).get(client.name, 0.05))
                world["live"].discard(client.name)
            return 1
        mir._send_pieces_now = send_now

        async def upload(rule, key, max_gb, test=False):
            msgs = []
            await mir._send_pieces(None, None, [key], key, "cap", 0, 0, None, [], key, "/tmp", msgs)
            world["sent"].append((key, list(msgs)))
            return "올림"
        mir.upload = upload
        rule = {"tg": accounts[0], "tg_alt": list(accounts[1:]), "kind": "folder", "enabled": True, "channel_title": "c", "id": "r1",
                "channel": "-1", "relay_channel": relay}
        mir.queue = [{"rule": "r1", "key": k, "title": k} for k in keys]
        st = {"rules": [rule], "hours": "", "encode_slots": len(keys), "max_gb": 2}
        return mir, st, world

    def test_idle_account_goes_through_relay(self):
        mir, st, world = self.make()
        asyncio.run(mir.run_queue(st))
        direct = [p for p in world["posts"].get("-1", []) if p[0] == "up"]
        fwd = [p for p in world["posts"].get("-1", []) if p[0] == "fwd"]
        relayed = world["posts"].get("-9", [])
        self.assertEqual(len(direct), 1)                    # 하나는 원래 채널로 바로
        self.assertEqual(len(relayed), 1)                   # 다른 하나는 임시 채널로 올린 뒤
        self.assertEqual(len(fwd), 2)                       # 영상 + 자막을 원래 채널로 옮김
        self.assertEqual({direct[0][3], relayed[0][3]}, {"A", "B"})   # 두 계정이 동시에 일함
        self.assertEqual(len(world["deleted"]), 1)          # 임시 채널에서 지움
        self.assertEqual(world["deleted"][0][0], "-9")
        # 기록된 메시지 id는 원래 채널의 새 id
        rkey = next(k for k, ids in world["sent"] if ids and ids[0] not in [p[2] for p in direct])
        new_ids = dict(world["sent"])[rkey]
        self.assertTrue(all(i > relayed[0][2] for i in new_ids))
        sending = (self.m.load_state()["rules"].get("r1") or {}).get("sending") or {}
        self.assertFalse(any(i == relayed[0][2] for ids in sending.values() for i in ids))   # 임시 채널 id는 이어 올리기 기록에 없음

    def test_no_relay_without_setting(self):
        mir, st, world = self.make(relay="")
        asyncio.run(mir.run_queue(st))
        self.assertEqual(world["posts"].get("-9"), None)
        self.assertEqual(len([p for p in world["posts"]["-1"] if p[0] == "up"]), 2)   # 차례로 원래 채널에

    def test_forward_falls_back_to_other_account(self):
        mir, st, world = self.make(deny={"B": ("-1",)})   # B는 임시 채널엔 올리지만 원래 채널엔 못 씀 -> A가 옮김
        asyncio.run(mir.run_queue(st))
        fwd = [p for p in world["posts"].get("-1", []) if p[0] == "fwd"]
        self.assertTrue(world["posts"].get("-9"))
        self.assertTrue(fwd and all(p[3] == "A" for p in fwd))


    def test_all_idle_accounts_use_relay_together(self):
        """계정 셋: 하나가 원래 채널로 (느리게) 올리는 동안 나머지 둘이 함께 임시 채널로 (예전엔 임시 채널도 한 계정씩)"""
        mir, st, world = self.make(accounts=("C", "A", "B"), keys=("k1", "k2", "k3"), slow={"C": 0.4, "A": 0.2, "B": 0.2})
        asyncio.run(mir.run_queue(st))
        self.assertEqual(world["most"], 3)                                   # 세 계정이 동시에
        self.assertEqual({p[3] for p in world["posts"]["-9"]}, {"A", "B"})   # 임시 채널은 둘이 함께

    def test_relay_set_while_running_is_used(self):
        """도는 중에 저장한 임시 채널도 바로 쓴다 (예전엔 한 차례를 시작할 때 읽은 규칙만 써서 몇 시간이고 안 쓰였다)"""
        m = self.m
        mir, st, world = self.make(relay="")
        saved = {"rules": [{**st["rules"][0], "relay_channel": "-9"}]}
        orig = m.load_settings
        m.load_settings = lambda: saved
        self.addCleanup(setattr, m, "load_settings", orig)
        asyncio.run(mir.run_queue(st))
        self.assertTrue(world["posts"].get("-9"))


class CleanTest(unittest.TestCase):
    def test_relay_setting_clean(self):
        from tgup import plex_to_tg as m
        base = {"tg": "A", "kind": "folder", "folder": "/x", "channel": "-1003"}
        self.assertEqual(m.clean_settings({"rules": [{**base, "relay_channel": "-1009", "relay_title": "임시"}]})["rules"][0]["relay_channel"], "-1009")
        self.assertEqual(m.clean_settings({"rules": [{**base, "relay_channel": "-1003"}]})["rules"][0]["relay_channel"], "")   # 같은 채널이면 끔
        self.assertEqual(m.clean_settings({"rules": [{**base, "relay_channel": "abc"}]})["rules"][0]["relay_channel"], "")
