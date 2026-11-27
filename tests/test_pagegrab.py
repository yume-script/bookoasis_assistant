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

    def test_fetch_prefers_browser_and_falls_back(self):
        calls = []

        def cffi(url):
            calls.append(("cffi", url))
            raise pagegrab.GrabError("페이지를 열지 못했습니다: Connection reset by peer")

        def req(url):
            calls.append(("req", url))
            return 200, "", HTML.encode(), "utf-8"
        old = (pagegrab._cffi_get, pagegrab._requests_get, pagegrab._check_host)
        self.addCleanup(lambda: (setattr(pagegrab, "_cffi_get", old[0]), setattr(pagegrab, "_requests_get", old[1]),
                                 setattr(pagegrab, "_check_host", old[2])))
        pagegrab._check_host = lambda u: None
        pagegrab._cffi_get, pagegrab._requests_get = (lambda: cffi), (lambda session=None: req)
        text, _ = pagegrab.fetch("https://example.org/a")
        self.assertEqual([c[0] for c in calls], ["cffi", "req"])          # 브라우저 흉내가 끊기면 requests로
        self.assertIn("video.twimg.com", text)
        calls.clear()
        pagegrab._cffi_get = lambda: (lambda url: calls.append(("cffi", url)) or (200, "", b"<p>ok</p>", None))
        self.assertEqual(pagegrab.fetch("https://example.org/a")[0], "<p>ok</p>")
        self.assertEqual([c[0] for c in calls], ["cffi"])                  # 되면 그것만
        pagegrab._cffi_get = lambda: None                                   # curl_cffi가 없으면 requests
        calls.clear()
        pagegrab.fetch("https://example.org/a")
        self.assertEqual([c[0] for c in calls], ["req"])

    def test_cffi_real_request(self):
        """curl_cffi가 설치돼 있으면 실제로 (이 컴퓨터 안의 작은 서버에서) 받아 본다"""
        try:
            import curl_cffi  # noqa: F401
        except ImportError:
            self.skipTest("curl_cffi 없음")
        import http.server
        import threading

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/go":
                    self.send_response(302)
                    self.send_header("Location", "/page")
                    self.end_headers()
                    return
                body = HTML.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass
        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        old = pagegrab._check_host
        pagegrab._check_host = lambda u: None
        self.addCleanup(setattr, pagegrab, "_check_host", old)
        os.environ["NO_PROXY"] = "127.0.0.1"
        text, final = pagegrab._follow(pagegrab._cffi_get(), f"http://127.0.0.1:{srv.server_port}/go")
        self.assertTrue(final.endswith("/page"))
        self.assertEqual(len(pagegrab.extract(text)), 2)


class FakeMirror:
    def __init__(self):
        self.added = []

    async def add_youtube(self, rule, urls, again=False):
        if rule != "yt1":
            raise ValueError("유튜브 규칙을 골라 주세요.")
        self.added.append((rule, list(urls)))
        return len(urls), 0


V3 = "https://video.twimg.com/ext_tw_video/1790000000000000003/pu/vid/avc1/720x1280/n.mp4"


class WatchTest(unittest.TestCase):
    def setUp(self):
        compat.DATA_DIR = tempfile.mkdtemp(prefix="pw-data-")

    def run_(self, coro):
        import asyncio
        return asyncio.run(coro)

    def test_save_validates(self):
        w = pagegrab.save_watch({"url": "https://example.org/p", "rule": "yt1", "every": 2})
        self.assertEqual((w["every"], w["enabled"], w["existing"], w["seen_count"]), (pagegrab.WATCH_MIN, True, True, 0))
        with self.assertRaises(pagegrab.GrabError):
            pagegrab.save_watch({"url": "https://example.org/p", "rule": "yt1"})     # 같은 페이지·규칙
        with self.assertRaises(pagegrab.GrabError):
            pagegrab.save_watch({"url": "ftp://x", "rule": "yt1"})
        with self.assertRaises(pagegrab.GrabError):
            pagegrab.save_watch({"url": "https://example.org/q", "rule": ""})
        w2 = pagegrab.save_watch({"id": w["id"], "url": "https://example.org/p", "rule": "yt1", "every": 30, "enabled": False})
        self.assertEqual((w2["id"], w2["every"], w2["enabled"]), (w["id"], 30, False))
        self.assertNotIn("seen", w2)
        pagegrab.delete_watch(w["id"])
        self.assertEqual(pagegrab.watches(), [])

    def test_sends_only_new_videos(self):
        mir, html_now = FakeMirror(), [HTML]
        fetch = lambda u: (html_now[0], u)   # noqa: E731
        w = pagegrab.save_watch({"url": "https://example.org/p", "rule": "yt1"})
        got = self.run_(pagegrab.check_watch(mir, w["id"], fetch))
        self.assertEqual((got["last_new"], got["last_error"], got["seen_count"], got["title"]), (2, "", 2, "고양이 & 강아지 모음"))
        self.assertFalse(pagegrab.due(pagegrab.watches()[0], got["last_at"] + 60))           # 10분 안엔 다시 안 함
        self.assertTrue(pagegrab.due(pagegrab.watches()[0], got["last_at"] + 600))
        got = self.run_(pagegrab.check_watch(mir, w["id"], fetch))
        self.assertEqual((got["last_new"], len(mir.added)), (0, 1))                          # 같은 페이지면 아무것도
        html_now[0] = HTML + f' <video src="{V3}"></video>'
        got = self.run_(pagegrab.check_watch(mir, w["id"], fetch))
        self.assertEqual((got["last_new"], mir.added[-1][1]), (1, [V3]))                     # 새로 올라온 것만
        self.assertIn(V3, pagegrab.load()[0]["sent"])                                          # 찾은 기록에도 보냄 표시
        html_now[0] = "<p>지금은 없음</p>"
        got = self.run_(pagegrab.check_watch(mir, w["id"], fetch))
        self.assertEqual((got["last_error"], got.get("note")), ("", "영상 없음"))

    def test_first_check_can_skip_existing_and_errors_retry(self):
        mir = FakeMirror()
        fetch = lambda u: (HTML, u)   # noqa: E731
        w = pagegrab.save_watch({"url": "https://example.org/p", "rule": "yt1", "existing": False})
        got = self.run_(pagegrab.check_watch(mir, w["id"], fetch))
        self.assertEqual((got["last_new"], got["seen_count"], mir.added), (0, 2, []))        # 처음 있던 것은 본 것으로만
        bad = pagegrab.save_watch({"url": "https://example.org/z", "rule": "nope"})
        got = self.run_(pagegrab.check_watch(mir, bad["id"], fetch))
        self.assertIn("유튜브 규칙", got["last_error"])
        self.assertEqual(got["seen_count"], 0)                                                 # 못 넣었으면 다음에 다시


if __name__ == "__main__":
    unittest.main()
