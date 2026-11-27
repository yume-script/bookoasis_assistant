# -*- coding: utf-8 -*-
"""kavita.yaml: 끝이 잘린(UTF-8이 깨진) 기존 파일은 버리고 새로 만들고, 쓰기는 따로 된 임시 파일로"""
import os
import shutil
import sys
import tempfile
import threading
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="ky-test-")
os.environ.setdefault("GDW_ENV_FILE", os.path.join(TMP, ".env"))
os.environ.setdefault("DATA_DIR", os.path.join(TMP, "data"))

from wtm import kavita_yaml as ky  # noqa: E402


class BrokenYamlTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="series-")
        self.addCleanup(shutil.rmtree, self.d, True)
        self.series = os.path.join(self.d, "천사지인 (59152017)")
        os.makedirs(self.series)
        for n in (1, 2):
            open(os.path.join(self.series, "천사지인 %04d화#10.zip" % n), "wb").close()
        self.path = os.path.join(self.series, ky.YAML_NAME)
        self.logs = []

    def write(self, **kw):
        return ky.write_kavita_yaml(self.d, "59152017", series_dir=self.series, folder_title="천사지인",
                                    refresh_info=False, embed_cover=False, log=self.logs.append, **kw)

    def test_truncated_file_is_rebuilt(self):
        # 보고서와 같은 모양: 한글 한 글자의 앞 2바이트만 남고 잘림
        with open(self.path, "wb") as f:
            f.write('title: "천사지인"\npublisher: "카'.encode("utf-8")[:-1])
        with self.assertRaises(ky._Broken):
            ky._read_existing(self.path)
        self.assertEqual(self.write(), "written")                       # 예전엔 "error" (UnicodeDecodeError)
        with open(self.path, encoding="utf-8") as f:
            self.assertIn("천사지인", f.read())
        self.assertTrue(any("깨져 있어 새로 만듭니다" in x for x in self.logs), self.logs)
        self.assertEqual([n for n in os.listdir(self.series) if n.endswith(".tmp")], [])   # 임시 파일이 남지 않음

    def test_size_change_after_write_triggers_rewrite(self):
        self.assertEqual(self.write(), "written")
        self.assertEqual(self.write(), "unchanged")
        with open(self.path, "rb+") as f:                               # 쓴 뒤 누가 잘라 놓음
            f.truncate(os.path.getsize(self.path) - 3)
        self.assertEqual(self.write(), "written")                       # 기록상 최신이어도 크기가 다르면 다시
        with open(self.path, encoding="utf-8") as f:
            f.read()

    def test_existing_cover_reader_tolerates_broken_file(self):
        with open(self.path, "wb") as f:
            f.write(b'files:\n  a:\n    cover: "abc\xec\xb9')
        self.assertIsNone(ky._existing_first_cover(self.path))

    def test_concurrent_writes_never_truncate(self):
        texts = ["x" * 50000 + "끝%d\n" % i for i in range(8)]
        errs = []

        def run(t):
            try:
                ky._write_atomic(self.path, t)
            except Exception as e:  # noqa: BLE001
                errs.append(e)
        th = [threading.Thread(target=run, args=(t,)) for t in texts]
        [t.start() for t in th]
        [t.join() for t in th]
        self.assertEqual(errs, [])
        with open(self.path, encoding="utf-8") as f:
            self.assertIn(f.read(), texts)                              # 어느 하나가 온전히
        self.assertEqual([n for n in os.listdir(self.series) if n.endswith(".tmp")], [])


if __name__ == "__main__":
    unittest.main()
