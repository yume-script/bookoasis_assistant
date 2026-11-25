# -*- coding: utf-8 -*-
"""웹툰 다운로더: 받은 회차 기록 (wtm/state_store received) - 파일을 지우거나 옮겨도 다시 받지 않음"""
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from wtm import downloader, state_store as ss  # noqa: E402


class ReceivedTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="wtm-recv-")
        self.addCleanup(shutil.rmtree, self.d, True)
        saved = (ss.RECEIVED_DIR, ss.HISTORY_PATH)
        ss.RECEIVED_DIR = os.path.join(self.d, "received")
        ss.HISTORY_PATH = os.path.join(self.d, "history.jsonl")
        ss._recv_cache.clear()
        ss._recv_seeded[0] = False

        def restore():
            ss.RECEIVED_DIR, ss.HISTORY_PATH = saved
            ss._recv_cache.clear()
            ss._recv_seeded[0] = False
        self.addCleanup(restore)

    def reload(self):
        ss._recv_cache.clear()
        ss._recv_seeded[0] = False

    def test_seed_from_history_and_record(self):
        with open(ss.HISTORY_PATH, "w", encoding="utf-8") as f:
            for e in ({"type": "download", "title_id": "11", "episode_no": 1},
                      {"type": "download", "platform": "kakao", "title_id": "11", "episode_no": 7},
                      {"type": "manual_download", "title_id": "11", "episode_no": 2},
                      {"type": "download_fail", "title_id": "11", "episode_no": 3}):
                f.write(json.dumps(e) + "\n")
        self.assertEqual(ss.received_nos("naver", "11"), {1, 2})      # 이력에서 한 번 채움 (실패는 뺌)
        self.assertEqual(ss.received_nos("kakao", 11), {7})            # 플랫폼마다 따로
        ss.append_history({"type": "download", "title_id": "11", "episode_no": 5})
        os.remove(ss.HISTORY_PATH)                                     # 이력이 잘려 나가도
        self.reload()
        self.assertEqual(ss.received_nos("naver", "11"), {1, 2, 5})    # 기록 파일에 남음
        ss.forget_received("naver", "11", [2])
        self.reload()
        self.assertEqual(ss.received_nos("naver", "11"), {1, 5})

    def test_download_episode_skips_moved(self):
        root, tmp = os.path.join(self.d, "lib"), os.path.join(self.d, "tmp")
        sd = downloader.title_dir(root, "작품", "99")
        os.makedirs(sd)
        z = os.path.join(sd, downloader._archive_prefix("작품", 3, 4) + "#2.zip")
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("a.jpg", b"x")
            zf.writestr("b.jpg", b"x")
        ok, skipped, cnt, err = downloader.download_episode(None, root, tmp, "작품", "99", 3)
        self.assertEqual((ok, skipped, cnt), (True, True, 2))
        self.assertIn(3, ss.received_nos("naver", "99"))               # 폴더에 있던 회차도 기록
        os.remove(z)                                                   # 사용자가 지움/옮김
        downloader._dir_cache_remove(sd, os.path.basename(z))
        ok, skipped, cnt, err = downloader.download_episode(None, root, tmp, "작품", "99", 3)
        self.assertEqual((ok, skipped), (True, True))                  # 네트워크 없이 건너뜀
        self.assertTrue(downloader.is_received_skip(err))
        try:                                                           # 강제 다시 받기는 기록을 무시 (여기서는 세션이 없어 받기에서 실패)
            r = downloader.download_episode(None, root, tmp, "작품", "99", 3, force=True, timeout=1)
            self.assertFalse(downloader.is_received_skip(r[3]))
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    unittest.main()
