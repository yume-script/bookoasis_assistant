# -*- coding: utf-8 -*-
"""텔레그램이 Telethon이 모르는 형식을 섞어 답할 때(TypeNotFoundError): 이미 올라갔으니 보낸 것으로 (다시 올려 두 번 올라가지 않게)"""
import asyncio
import os
import sys
import tempfile
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="tnf-test-")
os.environ.setdefault("GDW_ENV_FILE", os.path.join(TMP, ".env"))
os.environ.setdefault("DATA_DIR", os.path.join(TMP, "data"))

try:
    import aiohttp  # noqa: F401
    HAVE = True
except ImportError:
    HAVE = False


class TypeNotFoundError(Exception):
    pass


class Client:
    def __init__(self):
        self.calls = 0

    async def send_file(self, *a, **k):
        self.calls += 1
        raise TypeNotFoundError("Could not find a matching Constructor ID for the TLObject ... d49f34c6")

    async def forward_messages(self, *a, **k):
        self.calls += 1
        raise TypeNotFoundError("Could not find a matching Constructor ID")


class Tests(unittest.TestCase):
    @unittest.skipUnless(HAVE, "aiohttp 없음")
    def test_upload_counts_as_sent(self):
        from tgup import plex_to_tg as m
        mir = m.Mirror(None, None, lambda *a: None, None)
        c = Client()
        self.assertIsNone(asyncio.run(mir._send(c, "peer", "/tmp/a.mp4")))   # 오류 없이 (메시지 번호만 모름)
        self.assertEqual(c.calls, 1)

        async def other():
            raise ValueError("x")
        with self.assertRaises(ValueError):                                     # 다른 오류는 그대로
            asyncio.run(m.Mirror._sent_anyway(other(), "a"))

    def test_channel_copy_counts_as_forwarded(self):
        from tgup import chcopy
        cp = chcopy.Copier.__new__(chcopy.Copier)
        cp._save = lambda: None
        c = Client()
        got = asyncio.run(cp._forward(c, {"drop_author": True, "drop_captions": False, "src_title": "s"}, "src", "dst", [1, 2]))
        self.assertEqual((got, c.calls), ([1, 2], 1))


if __name__ == "__main__":
    unittest.main()
