# -*- coding: utf-8 -*-
"""다른 텔레그램 채널 영상 복사 (tgup/chcopy.py) - 가짜 텔레그램 클라이언트로"""
import asyncio
import os
import sys
import tempfile
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="chcopy-test-")
os.environ.setdefault("GDW_ENV_FILE", os.path.join(TMP, ".env"))
os.environ.setdefault("DATA_DIR", os.path.join(TMP, "data"))

from tgup import chcopy, compat, tgaccount  # noqa: E402


def msg(i, kind="video", gid=None):
    m = types.SimpleNamespace(id=i, action=None, video=None, photo=None, document=None, grouped_id=gid, message=f"m{i}")
    if kind == "video":
        m.video = m.document = types.SimpleNamespace(mime_type="video/mp4", attributes=[])
    elif kind == "mkv":
        m.document = types.SimpleNamespace(mime_type="application/x-matroska", attributes=[types.SimpleNamespace(file_name=f"{i}.mkv")])
    elif kind == "photo":
        m.photo = object()
    elif kind == "service":
        m.action = object()
    return m


class Channel:
    def __init__(self, cid, title, noforwards=False):
        self.id, self.title, self.username, self.noforwards = cid, title, "src", noforwards


Channel.__name__ = "Channel"


class FloodWaitError(Exception):
    seconds = 0


class Client:
    def __init__(self, msgs, src):
        self.msgs, self.src, self.sent, self.flood = msgs, src, [], 0

    async def get_entity(self, x):
        return self.src

    async def get_messages(self, ent, limit=0, filter=None):
        if limit == 0:
            return types.SimpleNamespace(total=len(self.msgs))
        return sorted(self.msgs, key=lambda m: -m.id)[:limit]

    async def iter_messages(self, ent, reverse=False, min_id=0, max_id=0):
        for m in sorted(self.msgs, key=lambda m: m.id, reverse=not reverse):
            if m.id > min_id and (not max_id or m.id < max_id):
                yield m

    async def forward_messages(self, dst, ids, from_peer=None, drop_author=None, drop_media_captions=None):
        if self.flood:
            self.flood -= 1
            raise FloodWaitError("wait")
        self.sent.append((list(ids), drop_author, drop_media_captions))
        return ids


class Acc:
    def __init__(self, client):
        self.client = client

    async def authorized_client(self):
        return self.client

    async def peer(self, ch):
        return ch


class ParseTest(unittest.TestCase):
    def test_parse_source(self):
        self.assertEqual(chcopy.parse_source("@my_chan"), ("name", "my_chan"))
        self.assertEqual(chcopy.parse_source("https://t.me/my_chan/123"), ("name", "my_chan"))
        self.assertEqual(chcopy.parse_source("t.me/s/my_chan"), ("name", "my_chan"))
        self.assertEqual(chcopy.parse_source("https://t.me/c/1234567890/55"), ("id", 1234567890))
        self.assertEqual(chcopy.parse_source("-1001234567890"), ("id", 1234567890))
        for bad in ("", "https://t.me/+abcdEF", "-12345", "x"):
            with self.assertRaises(ValueError):
                chcopy.parse_source(bad)

    def test_matches(self):
        self.assertTrue(chcopy.matches(msg(1, "video"), "video"))
        self.assertTrue(chcopy.matches(msg(1, "mkv"), "video"))
        self.assertFalse(chcopy.matches(msg(1, "photo"), "video"))
        self.assertTrue(chcopy.matches(msg(1, "photo"), "media"))
        self.assertFalse(chcopy.matches(msg(1, "text"), "media"))
        self.assertTrue(chcopy.matches(msg(1, "text"), "all"))
        self.assertFalse(chcopy.matches(msg(1, "service"), "all"))


class CopyTest(unittest.TestCase):
    def setUp(self):
        compat.DATA_DIR = tempfile.mkdtemp(prefix="chcopy-data-")
        self._accs = tgaccount.accounts
        tgaccount.accounts = lambda: [{"id": "tg"}]
        self.addCleanup(setattr, tgaccount, "accounts", self._accs)
        chcopy.GAP_SEC = 0
        self.msgs = [msg(1, "text"), msg(2, "video"), msg(3, "photo"), msg(4, "mkv"), msg(5, "service")] + \
                    [msg(i, "video") for i in range(6, 60)] + [msg(60, "video", gid=7), msg(61, "photo", gid=7)]
        self.client = Client(self.msgs, Channel(99, "원본"))

    def run_job(self, body, client=None):
        cp = chcopy.Copier(lambda a: Acc(client or self.client))
        job = cp.add({"account": "tg", "src": "@srcchan", "dst": "-100777", **body})

        async def go():
            await cp.run(job)
        asyncio.run(go())
        return cp, job

    def test_all_videos_batched(self):
        cp, job = self.run_job({"kind": "video", "drop_author": True})
        ids = [i for b, _a, _c in self.client.sent for i in b]
        self.assertEqual(ids, [2, 4] + list(range(6, 61)))          # 영상만, 오래된 것부터
        self.assertTrue(all(len(b) <= chcopy.BATCH for b, _a, _c in self.client.sent))
        self.assertEqual(self.client.sent[0][1:], (True, None))
        self.assertEqual((job["status"], job["copied"], job["last_id"], job["to_id"]), ("done", 57, 61, 61))
        self.assertEqual(chcopy.public(job)["percent"], 100)
        self.assertEqual(chcopy.load_jobs()[0]["copied"], 57)       # 저장됨

    def test_recent_and_ids(self):
        _cp, job = self.run_job({"kind": "media", "range": "recent", "limit": 3, "drop_captions": True})
        self.assertEqual([i for b, *_ in self.client.sent for i in b], [59, 60, 61])
        self.assertEqual(self.client.sent[0][2], True)
        self.client.sent.clear()
        _cp, job = self.run_job({"kind": "all", "range": "ids", "from_id": 1, "to_id": 5})
        self.assertEqual([i for b, *_ in self.client.sent for i in b], [1, 2, 3, 4])   # 알림 메시지(5)는 뺌

    def test_album_kept_together(self):
        chcopy.BATCH, b0 = 2, chcopy.BATCH
        self.addCleanup(setattr, chcopy, "BATCH", b0)
        self.client.msgs = [msg(1), msg(2), msg(3, gid=9), msg(4, "photo", gid=9), msg(5)]
        self.run_job({"kind": "media"})
        self.assertEqual([b for b, *_ in self.client.sent], [[1, 2], [3, 4], [5]])

    def test_flood_wait_then_continue(self):
        self.client.flood = 1
        sys.modules[__name__].FloodWaitError.seconds = 0
        _cp, job = self.run_job({"kind": "video", "range": "ids", "from_id": 2, "to_id": 4})
        self.assertEqual([b for b, *_ in self.client.sent], [[2, 4]])
        self.assertEqual(job["status"], "done")

    def test_protected_and_resume(self):
        client = Client(self.msgs, Channel(99, "원본", noforwards=True))
        with self.assertRaises(RuntimeError) as cm:
            self.run_job({}, client)
        self.assertIn("보호된 콘텐츠", str(cm.exception))
        # 재시작: 하던 작업은 이어서 (옮긴 곳 다음부터)
        cp = chcopy.Copier(lambda a: Acc(self.client))
        job = cp.add({"account": "tg", "src": "@srcchan", "dst": "-100777", "kind": "video"})
        job.update(status="running", prepared=True, to_id=61, last_id=50)
        cp._save()
        cp2 = chcopy.Copier(lambda a: Acc(self.client))
        j2 = cp2.find(job["id"])
        self.assertEqual(j2["status"], "waiting")
        asyncio.run(cp2.run(j2))
        self.assertEqual([i for b, *_ in self.client.sent for i in b], list(range(51, 61)))

    def test_loop_errors_and_cancel(self):
        cp = chcopy.Copier(lambda a: Acc(Client(self.msgs, Channel(99, "원본", noforwards=True))))
        job = cp.add({"account": "tg", "src": "@srcchan", "dst": "-100777"})

        async def go():
            t = asyncio.ensure_future(cp.loop())
            for _ in range(50):
                await asyncio.sleep(0.01)
                if job["status"] == "error":
                    break
            t.cancel()
            await asyncio.gather(t, return_exceptions=True)
        asyncio.run(go())
        self.assertEqual(job["status"], "error")
        self.assertIn("보호된 콘텐츠", job["error"])
        cp.retry(job["id"])
        self.assertEqual(job["status"], "waiting")
        cp.cancel(job["id"])
        self.assertEqual(job["status"], "cancelled")
        cp.remove(job["id"])
        self.assertEqual(cp.jobs, [])
        with self.assertRaises(ValueError):
            cp.add({"account": "nope", "src": "@srcchan", "dst": "-1"})
        with self.assertRaises(ValueError):
            cp.add({"account": "tg", "src": "@srcchan", "dst": "-1", "range": "recent", "limit": 0})


if __name__ == "__main__":
    unittest.main()
