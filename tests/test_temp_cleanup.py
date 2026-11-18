# -*- coding: utf-8 -*-
"""작업 파일 정리: 웹툰 회차 임시 폴더(오래된 것만), 브런치 tmp, 텔레그램 자동 올리기 임시 폴더"""
import os
import sys
import time
import unittest
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class WebtoonTempTest(unittest.TestCase):
    def test_sweep_stale_temp_only_old_episode_dirs(self):
        from wtm import downloader
        root = tempfile.mkdtemp()
        old_ep = os.path.join(root, "123", "0005")
        new_ep = os.path.join(root, "123", "0006")
        box = os.path.join(root, "_outbox", "123")
        kakao = os.path.join(root, "kakao", "77", "0001")
        for d in (old_ep, new_ep, box, kakao):
            os.makedirs(d)
            open(os.path.join(d, "1.jpg"), "wb").close()
        past = time.time() - 20 * 86400
        for p in (old_ep, os.path.join(old_ep, "1.jpg"), kakao, os.path.join(kakao, "1.jpg")):
            os.utime(p, (past, past))
        self.assertEqual(downloader.sweep_stale_temp(root), 1)
        self.assertFalse(os.path.exists(old_ep))
        self.assertTrue(os.path.exists(new_ep))      # 최근에 받던 것은 이어 받게 그대로
        self.assertTrue(os.path.exists(box))         # 옮길 zip은 그대로
        self.assertTrue(os.path.exists(kakao))       # 카카오 경로는 따로 (kakao_temp_root로 부름)
        self.assertEqual(downloader.sweep_stale_temp(os.path.join(root, "kakao")), 1)


class BrunchTmpTest(unittest.TestCase):
    def test_sweep_tmp_old_files(self):
        from brunch import service
        d = tempfile.mkdtemp()
        orig = service.data_dir
        service.data_dir = lambda: d
        try:
            os.makedirs(os.path.join(d, "tmp"))
            old, new = os.path.join(d, "tmp", "a.epub"), os.path.join(d, "tmp", "b.epub")
            for p in (old, new):
                open(p, "wb").close()
            past = time.time() - 7200
            os.utime(old, (past, past))
            self.assertEqual(service.sweep_tmp(), 1)
            self.assertEqual(os.listdir(os.path.join(d, "tmp")), ["b.epub"])
        finally:
            service.data_dir = orig


class TgupTmpTest(unittest.TestCase):
    def test_sweep_tmp(self):
        from tgup import compat, service
        d = tempfile.mkdtemp()
        orig = compat.DATA_DIR
        compat.DATA_DIR = d
        try:
            os.makedirs(os.path.join(d, "plex_to_tg_tmp", "abc"))
            self.assertEqual(service._sweep_tmp(), 1)
            self.assertFalse(os.path.exists(os.path.join(d, "plex_to_tg_tmp")))
        finally:
            compat.DATA_DIR = orig


if __name__ == "__main__":
    unittest.main()


class MemtrimTest(unittest.TestCase):
    def test_release_and_loop(self):
        import threading
        from gdw import memtrim
        self.assertIn(memtrim.release(), (True, False))
        ev = threading.Event()
        t = memtrim.start_loop(ev, every=0.01)
        time.sleep(0.05)
        ev.set()
        t.join(1)
        self.assertFalse(t.is_alive())
