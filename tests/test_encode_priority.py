# -*- coding: utf-8 -*-
"""텔레그램 올리기 인코딩 우선순위 설정 (low / normal / high)"""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="prio-test-")
os.environ.setdefault("GDW_ENV_FILE", os.path.join(TMP, ".env"))
os.environ.setdefault("DATA_DIR", os.path.join(TMP, "data"))

try:
    import aiohttp  # noqa: F401
    HAVE = True
except ImportError:
    HAVE = False


@unittest.skipUnless(HAVE, "aiohttp 없음")
class PriorityTest(unittest.TestCase):
    def test_settings_and_levels(self):
        from tgup import plex_to_tg as m
        self.assertEqual(m.clean_settings({"encode_priority": "high"})["encode_priority"], "high")
        self.assertEqual(m.clean_settings({"encode_priority": "x"})["encode_priority"], "low")
        self.assertEqual((m.ENCODE_NICE["high"], m.ENCODE_IONICE["high"]), (0, 4))
        old = m._encode_priority
        self.addCleanup(setattr, m, "_encode_priority", old)
        m._encode_priority = lambda: "high"
        before = os.nice(0)
        pid = os.fork()
        if pid == 0:   # 자식에서 우선순위 그대로인지
            m._lowest_priority()
            os._exit(0 if os.nice(0) == before else 1)
        _, status = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 0)


if __name__ == "__main__":
    unittest.main()
