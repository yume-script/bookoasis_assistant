# -*- coding: utf-8 -*-
"""페이지에서 X 영상 찾기 (tgup/pagegrab.py) - 실제 페이지에는 붙지 않는다"""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="pg-test-")
os.environ.setdefault("GDW_ENV_FILE", os.path.join(TMP, ".env"))
os.environ.setdefault("DATA_DIR", os.path.join(TMP, "data"))

from tgup import compat, pagegrab  # noqa: E402

V1 = "https://video.twimg.com/ext_tw_video/1790000000000000001/pu/vid/avc1/{}/AbC.mp4?tag=12"
HTML = ("<html><head><title> 고양이 &amp; 강아지 모음 </title></head><body>"
        f'<video src="{V1.format("320x568")}"></video>'
        f'<script>var a = {{"u":"{V1.format("720x1280").replace("/", chr(92) + "/")}"}};</script>'
        '<a href="https://video.twimg.com/amplify_video/1790000000000000002/vid/avc1/1080x1920/x.mp4?tag=14&amp;b=1">b</a>'
        '<img src="https://pbs.twimg.com/media/abc.jpg"> https://video.twimg.com/ext_tw_video/1/pu/pl/x.m3u8'
        f' {V1.format("480x852")} </body></html>')


class PageGrabTest(unittest.TestCase):
    def setUp(self):
        compat.DATA_DIR = tempfile.mkdtemp(prefix="pg-data-")

    def test_extract_picks_largest_per_video(self):
        got = pagegrab.extract(HTML)
        self.assertEqual(got, [V1.format("720x1280"),   # \\/ 정리, 같은 영상은 가장 큰 화질
                               "https://video.twimg.com/amplify_video/1790000000000000002/vid/avc1/1080x1920/x.mp4?tag=14&b=1"])
        self.assertEqual(pagegrab.page_title(HTML), "고양이 & 강아지 모음")
        self.assertEqual(pagegrab.extract("<p>없음</p>"), [])

    def test_grab_saves_and_marks(self):
        page = pagegrab.grab("https://example.org/p/1", fetcher=lambda u: (HTML, u))
        self.assertEqual((page["title"], len(page["urls"]), page["sent"]), ("고양이 & 강아지 모음", 2, []))
        pagegrab.mark_sent("https://example.org/p/1", [page["urls"][0], "https://video.twimg.com/other.mp4"])
        self.assertEqual(pagegrab.load()[0]["sent"], [page["urls"][0]])   # 그 페이지에 있던 것만
        again = pagegrab.grab("https://example.org/p/1", fetcher=lambda u: (HTML, u))
        self.assertEqual(again["sent"], [page["urls"][0]])                   # 다시 찾아도 보낸 표시는 남음
        pagegrab.grab("https://example.org/p/2", fetcher=lambda u: (HTML, u + "?r"))
        self.assertEqual([p["url"] for p in pagegrab.load()], ["https://example.org/p/2", "https://example.org/p/1"])
        self.assertEqual(pagegrab.load()[0]["final"], "https://example.org/p/2?r")
        pagegrab.delete("https://example.org/p/1")
        self.assertEqual(len(pagegrab.load()), 1)
        with self.assertRaises(pagegrab.GrabError):
            pagegrab.grab("https://example.org/none", fetcher=lambda u: ("<p>x</p>", u))
        self.assertEqual(len(pagegrab.load()), 1)                            # 못 찾으면 저장 안 함

    def test_blocks_internal_hosts(self):
        for u in ("http://127.0.0.1/x", "http://localhost:5999/", "http://192.168.0.31/", "http://10.0.0.1/", "http://[::1]/",
                  "ftp://example.org/", "file:///etc/passwd", "nope"):
            with self.assertRaises(pagegrab.GrabError, msg=u):
                pagegrab._check_host(u)

    def test_fetch_checks_each_redirect(self):
        class R:
            def __init__(self, status, loc=None, body=b""):
                self.status_code, self.headers, self._b, self.encoding = status, ({"location": loc} if loc else {}), body, "utf-8"
                self.is_redirect = loc is not None

            def iter_content(self, n):
                yield self._b

            def close(self):
                pass

        class S:
            def __init__(self, seq):
                self.seq, self.seen = list(seq), []

            def get(self, url, **kw):
                self.seen.append(url)
                return self.seq.pop(0)
        old = pagegrab._check_host
        checked = []
        pagegrab._check_host = lambda u: checked.append(u) or (old(u) if "127.0.0.1" in u else None)
        self.addCleanup(setattr, pagegrab, "_check_host", old)
        s = S([R(302, "/next"), R(200, body=HTML.encode())])
        text, final = pagegrab.fetch("https://example.org/a", session=s)
        self.assertEqual((final, checked), ("https://example.org/next", ["https://example.org/a", "https://example.org/next"]))
        self.assertIn("video.twimg.com", text)
        with self.assertRaises(pagegrab.GrabError):     # 공인 주소에서 내부 주소로 리다이렉트하면 막음
            pagegrab.fetch("https://example.org/a", session=S([R(302, "http://127.0.0.1:5999/api")]))


if __name__ == "__main__":
    unittest.main()
