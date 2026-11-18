# -*- coding: utf-8 -*-
"""브런치 EPUB 받기 (brunch) - python3 -m unittest discover -s tests

브런치에는 붙지 않는다 (예시 HTML로 목차·본문 읽기, EPUB 만들기, 받기 흐름을 확인).
"""
import os
import time
import shutil
import sys
import tempfile
import threading
import unittest
import zipfile
from xml.dom import minidom

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="brunch-test-")
os.environ.setdefault("GDW_ENV_FILE", os.path.join(TMP, ".env"))
os.environ.setdefault("DATA_DIR", os.path.join(TMP, "data"))

try:
    import requests  # noqa: F401
    HAVE_REQUESTS = True
except ImportError:
    HAVE_REQUESTS = False

BOOK_PAGE = """<html><head>
<meta property="og:title" content="[연재 브런치북] 예시 &amp; 책">
<meta property="og:description" content="예시 소개입니다.">
<meta property="og:image" content="http://t1.kakaocdn.net/brunch/service/user/abc/image/cover">
</head><body><strong class="bb-book-title">예시 &amp; 책</strong><strong class="bb-tit-bloger">예시 작가</strong>
<span data-testid="article-total-count">3<!-- -->화</span>
<div class="post_article"><a class="cont_post" href="/@@abc/10" aria-disabled="false" data-testid="brunchbook-article-10">
<em class="num_txt" aria-label="1화">01<!-- --> </em><strong class="tit_post">첫 글</strong></a></div>
<div class="post_article"><a class="cont_post" href="/@@abc/12" aria-disabled="false" data-testid="brunchbook-article-12">
<em class="num_txt" aria-label="2화">02<!-- --> </em><strong class="tit_post">둘째 <b>글</b></strong></a></div>
<div class="post_article"><a class="cont_post" href="/@@abc/0" aria-disabled="true">
<em class="num_txt" aria-label="3화">03</em><strong class="tit_post">곧 발행</strong></a></div>
</body></html>"""

ARTICLE_PAGE = """<html><body>
<script type="application/json" id="ARTICLE_DATA">{"title": "첫 글", "subTitle": "부제", "authorName": "예시 작가", "publishTime": 1793750400000,
 "articleImageUrl": "http://t1.kakaocdn.net/x.jpg", "isMembershipContent": %s}</script>
<a class="link_magazinetit #brunchbook_title" href="/brunchbook/example1">예시 책</a>
<div id="ArticleView" class="text_align_left">
<p class="item_type_text">첫 줄 &amp; &lt;괄호&gt;<br>둘째 줄</p>
<script>alert(1)</script><input type="hidden" value="x"><p>input 뒤도 남아야 함</p>
<div class="item_type_img"><img src="http://t1.kakaocdn.net/a.jpg" alt="그림"></div>
<img src="https://evil.example.com/b.png"><p><strike>지운 글</strike> <a href="/@abc/3">링크</a> <a href="javascript:x()">나쁜 링크</a></p>
</div><div class="info_keyword">키워드</div></body></html>"""


class ParseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from brunch import fetch
        cls.f = fetch

    def test_parse_input(self):
        f = self.f
        self.assertEqual(f.parse_input("https://brunch.co.kr/brunchbook/abc_1"), ("book", "abc_1"))
        self.assertEqual(f.parse_input("brunch.co.kr/@@4r3L/12?x=1"), ("article", ("4r3L", 12)))
        self.assertEqual(f.parse_input("http://m.brunch.co.kr/@napurta/7"), ("article", ("@napurta", 7)))
        for bad in ("", "https://example.com/brunchbook/a", "https://brunch.co.kr/@@a/b", "https://brunch.co.kr/"):
            with self.assertRaises(ValueError):
                f.parse_input(bad)
        self.assertEqual(f.article_url("@napurta", 7), f.WEB_URL + "/@napurta/7")
        with self.assertRaises(ValueError):
            f.article_url("../x", 1)
        with self.assertRaises(ValueError):
            f.book_url("a/b")

    def test_parse_book(self):
        b = self.f.parse_book(BOOK_PAGE, "example1")
        self.assertEqual(b["title"], "예시 & 책")
        self.assertEqual(b["author"], "예시 작가")
        self.assertEqual(b["status"], "ONGOING")
        self.assertTrue(b["cover"].startswith("https://"))
        self.assertEqual([(e["num"], e["title"], e["article_no"]) for e in b["episodes"]], [("01", "첫 글", 10), ("02", "둘째 글", 12)])
        self.assertEqual(b["planned"], 1)
        self.assertEqual(b["total"], 3)
        done = self.f.parse_book(BOOK_PAGE.replace("[연재 브런치북]", "[브런치북]"), "example1")
        self.assertEqual(done["status"], "COMPLETE")

    def test_article_and_sanitize(self):
        a = self.f.parse_article(ARTICLE_PAGE % "false", "https://brunch.co.kr/@@abc/10")
        self.assertEqual(a["book_address"], "example1")
        self.assertFalse(a["restricted"])
        self.assertTrue(self.f.parse_article(ARTICLE_PAGE % "true", "u")["restricted"])
        asked = []

        def on_img(src):
            asked.append(src)
            return "images/img0001.jpg" if self.f.image_allowed(src) else None
        body = self.f.sanitize(a["html"], on_img)
        self.assertNotIn("alert", body)
        self.assertIn("input 뒤도 남아야 함", body)          # 닫는 태그 없는 <input> 뒤가 사라지지 않음
        self.assertIn("<br/>", body)
        self.assertIn("&amp; &lt;괄호&gt;", body)
        self.assertIn('<img src="images/img0001.jpg" alt="그림"/>', body)
        self.assertNotIn("evil.example.com", body)            # 허용하지 않은 곳의 그림은 뺀다
        self.assertIn("<s>지운 글</s>", body)
        self.assertIn('href="https://brunch.co.kr/@abc/3"', body)
        self.assertNotIn("javascript", body)
        self.assertEqual(asked, ["https://t1.kakaocdn.net/a.jpg", "https://evil.example.com/b.png"])
        minidom.parseString("<div>%s</div>" % body)           # XHTML로 읽힘

    def test_image_allowed(self):
        ok = self.f.image_allowed
        self.assertTrue(ok("https://img1.kakaocdn.net/thumb/x.jpg"))
        self.assertTrue(ok("https://t1.daumcdn.net/brunch/x"))
        self.assertFalse(ok("http://t1.kakaocdn.net/x"))
        self.assertFalse(ok("https://kakaocdn.net.evil.com/x"))
        self.assertFalse(ok("https://127.0.0.1/x"))


class EpubTest(unittest.TestCase):
    def test_build(self):
        from brunch import epub
        path = os.path.join(TMP, "book.epub")
        chapters = [{"num": "01", "title": "첫 글 & 시작", "subtitle": "부제", "body": '<p>본문</p><img src="images/img0001.png" alt=""/>',
                     "url": "https://brunch.co.kr/@@abc/10", "restricted": False},
                    {"num": "02", "title": "둘째", "subtitle": "", "body": "<p>유료 앞부분</p>", "url": "https://brunch.co.kr/@@abc/12", "restricted": True}]
        epub.build(path, {"title": "예시 & 책", "author": "작가", "description": "소개", "url": "https://brunch.co.kr/brunchbook/x"},
                   chapters, {"img0001.png": (b"\x89PNG....", "image/png")}, cover=(b"jpg", "image/jpeg"), identifier="brunch:book:x")
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            self.assertEqual(names[0], "mimetype")
            self.assertEqual(z.getinfo("mimetype").compress_type, zipfile.ZIP_STORED)
            for n in names:
                if n.endswith((".xhtml", ".opf", ".ncx", ".xml")):
                    minidom.parseString(z.read(n))
            opf = z.read("OEBPS/content.opf").decode()
            nav = z.read("OEBPS/nav.xhtml").decode()
            self.assertIn("text/images/cover.jpg", opf)
            self.assertIn('properties="cover-image"', opf)
            self.assertIn("<dc:title>예시 &amp; 책</dc:title>", opf)
            self.assertIn("01. 첫 글 &amp; 시작", nav)
            self.assertIn("멤버십 글", z.read("OEBPS/text/ch002.xhtml").decode())
            self.assertIn("OEBPS/text/images/img0001.png", names)
        self.assertFalse(os.path.exists(path + ".tmp"))
        with self.assertRaises(ValueError):
            epub.build(path, {"title": "x"}, [], {})


@unittest.skipUnless(HAVE_REQUESTS, "requests 없음")
class ServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from brunch import fetch, service
        cls.f, cls.s = fetch, service

    def test_settings_and_names(self):
        s = self.s
        with self.assertRaises(ValueError):
            s.clean_settings({"save_dir": "relative/dir"})
        self.assertEqual(s.clean_settings({"save_dir": "/a/b/../c", "by_author": False}), {"save_dir": "/a/c", "by_author": False, "auto_check": True, "check_minutes": 360, "kavita_yaml": True})
        self.assertEqual(s.safe_name('a/b:c*?"d.'), "a b c d")
        self.assertEqual(s.safe_name("..."), "브런치")
        p = s.target_path({"save_dir": "/books", "by_author": True}, "작가/이름", "책 제목")
        self.assertEqual(p, "/books/작가 이름/책 제목/책 제목.epub")          # 책마다 폴더 하나 (kavita.yaml)
        self.assertEqual(s.target_path({"save_dir": "/books", "by_author": False}, "작가", "책"), "/books/책/책.epub")

    def test_run_book(self):
        """받기 흐름 (브런치 대신 예시 페이지를 돌려주는 가짜 Client)"""
        f, s = self.f, self.s

        class FakeClient:
            def book(self, address):
                return f.parse_book(BOOK_PAGE, address)

            def article(self, uid, no):
                if no == 12:
                    raise f.BrunchError("삭제된 글")
                return f.parse_article(ARTICLE_PAGE % "false", f.article_url(uid, no))

            def get_image(self, url):
                return (b"img", "image/jpeg") if f.image_allowed(url) else None

        save = os.path.join(TMP, "books")
        s._write_json(s._settings_path(), {"save_dir": save, "by_author": True})
        s._STATE["client"] = FakeClient()
        try:
            job = {"id": "t1", "key": "book:example1", "kind": "book", "target": "example1", "title": "", "state": "running",
                   "done": 0, "total": 0, "error": "", "note": ""}
            s._run(job)
            out = os.path.join(save, "예시 작가", "예시 & 책", "예시 & 책.epub")
            self.assertTrue(os.path.isfile(out))
            # 책 폴더의 kavita.yaml (웹툰 다운로더와 같은 형식)
            yml = open(os.path.join(save, "예시 작가", "예시 & 책", "kavita.yaml"), encoding="utf-8").read()
            for want in ('code: "BRBexample1"', 'Name: "예시 & 책"', 'Person Writers: "예시 작가"', 'Person Publisher: "브런치"',
                         'Summary: "예시 소개입니다."', 'Publication Status: "0"', 'Web Links: "https://brunch.co.kr/brunchbook/example1"',
                         '"예시 & 책.epub":', "page: 1"):
                self.assertIn(want, yml)
            self.assertNotIn('cover: "FIRST"', yml)      # 표지가 들어감
            self.assertTrue(s.load_history()[0]["yaml"])
            mtime = os.path.getmtime(os.path.join(save, "예시 작가", "예시 & 책", "kavita.yaml"))
            h = s.load_history()[0]
            self.assertEqual((h["chapters"], h["images"], h["key"]), (1, 1, "book:example1"))
            self.assertEqual(len(h["skipped"]), 1)          # 삭제된 글은 빠지고 나머지로 만든다
            # 회차 발행일은 받은 날이 아니라 브런치에 발행된 날 (글의 publishTime)
            from datetime import datetime as _dt
            day = _dt.fromtimestamp(1793750400).strftime("%Y-%m-%d")
            self.assertEqual((h["first_published"], h["last_published"]), (day, day))
            self.assertEqual(set(h["episode_dates"].values()), {day})
            with zipfile.ZipFile(out) as z:
                opf = z.read("OEBPS/content.opf").decode("utf-8") if "OEBPS/content.opf" in z.namelist() else \
                    next(z.read(n).decode("utf-8") for n in z.namelist() if n.endswith(".opf"))
                ch = next(z.read(n).decode("utf-8") for n in z.namelist() if n.endswith("ch001.xhtml"))
            self.assertIn("<dc:date>%s</dc:date>" % day, opf)
            self.assertIn("%s 발행" % day.replace("-", "."), ch)
            self.assertEqual(s._public_history()[0]["first_published"], day)
            self.assertIn(f'Year: "{day[:4]}"', yml)
            self.assertEqual(job["done"], 2)
            # 같은 책을 다시 받으면 받은 목록에 한 줄만 남는다
            s._run(dict(job, id="t2"))
            self.assertEqual(len([x for x in s.load_history() if x["key"] == "book:example1"]), 1)
            self.assertEqual(os.path.getmtime(os.path.join(save, "예시 작가", "예시 & 책", "kavita.yaml")), mtime)   # 같으면 다시 안 씀
            got = s.api_get("/api/brunch/file", {"id": s.load_history()[0]["id"]})
            self.assertEqual(got[1], "application/epub+zip")
            with self.assertRaises(s.ApiError):
                s.api_get("/api/brunch/file", {"id": "nope"})
            with self.assertRaises(s.ApiError):
                s.api_post("/api/brunch/settings", {"save_dir": "rel"})
        finally:
            s._STATE["client"] = None


@unittest.skipUnless(HAVE_REQUESTS, "requests 없음")
class SearchTest(unittest.TestCase):
    def test_search_all_days(self):
        """제목으로 찾기: 모든 요일·완결 목록을 넘겨 모은 뒤 책 제목·회차 제목·작가로 (같은 책은 하나로, 요일 표시)"""
        from brunch import service as s

        def it(book, title, author, no, t):
            return {"book_title": book, "title": title, "author": author, "url": f"https://brunch.co.kr/@@a/{no}",
                    "user_id": "a", "article_no": no, "publish_time": t}
        pages = {("MONDAY", None): {"items": [it("말들에서 되올리는 것들", "1화", "갑", 1, 10)], "more": True,
                                    "next_url": "n2"},
                 ("MONDAY", "n2"): {"items": [it("기억의 편집", "역사는 진보", "을", 2, 5)], "more": False, "next_url": ""},
                 ("THURSDAY", None): {"items": [it("말들에서 되올리는 것들", "2화", "갑", 3, 20)], "more": False, "next_url": ""},
                 ("COMPLETE", None): {"items": [it("신학의 기초", "본회퍼", "KEN", 4, 1)], "more": False, "next_url": ""}}

        class FakeClient:
            def list(self, day, sort="", next_url=None):
                return pages.get((day, next_url), {"items": [], "more": False, "next_url": ""})
        orig = s._client
        s._client = lambda: FakeClient()
        s._SEARCH.update(items=[], at=0.0, building=False, pages=0, error="")
        try:
            first = s.search("말들")
            for _ in range(100):
                if not s._SEARCH["building"]:
                    break
                time.sleep(0.01)
            res = s.search("말 들")       # 띄어쓰기 상관없이
            self.assertEqual(res["total"], 3)
            self.assertEqual(len(res["items"]), 1)
            hit = res["items"][0]
            self.assertEqual((hit["title"], hit["days"]), ("2화", ["월", "목"]))   # 가장 최근 회차, 연재 요일 둘
            self.assertEqual([x["book_title"] for x in s.search("ken")["items"]], ["신학의 기초"])   # 작가로도
            self.assertEqual(s.search("진보")["items"][0]["book_title"], "기억의 편집")               # 회차 제목으로도
            self.assertEqual(s.search("")["items"], [])
            self.assertIn("building", first)
        finally:
            s._client = orig


class AutoCheckTest(unittest.TestCase):
    """새 글 자동 받기: 받은 브런치북에 새 회차가 오르면 다시 받기 대기열에"""

    @classmethod
    def setUpClass(cls):
        from brunch import fetch, service
        cls.f, cls.s = fetch, service

    def setUp(self):
        s = self.s
        with s._LOCK:
            s._JOBS.clear()
        s._write_json(s._history_path(), [])
        s._write_json(s._settings_path(), {"save_dir": os.path.join(TMP, "books2")})
        self.page = BOOK_PAGE
        f, test = self.f, self

        class FakeClient:
            def book(self, address):
                return f.parse_book(test.page, address)

            def article(self, uid, no):
                return f.parse_article(ARTICLE_PAGE % "false", f.article_url(uid, no))

            def get_image(self, url):
                return None
        s._STATE["client"] = FakeClient()
        s._STATE["thread"] = threading.Thread()   # 대기열 스레드를 띄우지 않게 (직접 _run) - 돌고 있는 것처럼 보이게
        s._STATE["thread"].is_alive = lambda: True

    def tearDown(self):
        self.s._STATE["client"] = None
        self.s._STATE["thread"] = None

    def _download(self):
        job = {"id": "a1", "key": "book:example1", "kind": "book", "target": "example1", "title": "", "state": "running",
               "done": 0, "total": 0, "error": "", "note": "", "auto": False}
        self.s._run(job)
        return self.s.load_history()[0]

    def test_history_epub_state(self):
        """받은 목록의 EPUB 상태: 최신 / 새 회차 미반영(발행 수 > 담은 수) / 만드는 중 / 파일 없음"""
        s = self.s
        h = self._download()
        st = lambda: next(x for x in s._public_history() if x["id"] == s.load_history()[0]["id"])  # noqa: E731
        self.assertEqual((st()["epub_state"], st()["published"], st()["new_count"]), ("latest", 2, 0))
        self.page = BOOK_PAGE.replace('href="/@@abc/0" aria-disabled="true"', 'href="/@@abc/15" aria-disabled="false"')
        s._JOBS.clear()
        s.check_now()                                   # 새 회차 발견 -> 다시 받기 대기열
        self.assertEqual(st()["epub_state"], "queued")
        s._JOBS.clear()
        self.assertEqual((st()["epub_state"], st()["new_count"], st()["published"]), ("behind", 1, 3))
        os.remove(h["file"])
        self.assertEqual(st()["epub_state"], "missing")

    def test_epub_state_and_bulk_complete(self):
        """연재 목록의 회차가 받아 둔 EPUB에 들어 있는지 표시하고, [완결작 모두 EPUB으로]는 아직 안 받은 책만 대기열에"""
        s = self.s
        h = self._download()
        self.assertEqual(h["episode_keys"], ["abc/10", "abc/12"])
        items = [{"book_title": "예시 & 책", "user_id": "abc", "article_no": 12},
                 {"book_title": "예시 & 책", "user_id": "abc", "article_no": 15},
                 {"book_title": "다른 책", "user_id": "xyz", "article_no": 3}]
        self.assertEqual([x["epub"] for x in s.epub_state(items)], ["done", "old", ""])
        # 예전 기록(episode_keys 없음)도 책 제목 + 글 번호로
        hist = s.load_history()
        hist[0].pop("episode_keys")
        s._write_json(s._history_path(), hist)
        self.assertEqual(s.epub_state([{"book_title": "예시 & 책", "user_id": "abc", "article_no": 10}])[0]["epub"], "done")
        # 완결작 모두 받기: 받은 책(done)은 건너뛰고 나머지를 bookof로 (받을 때 브런치북을 찾는다)
        pages = [{"items": [dict(items[0], url="u1"), dict(items[2], url="u3")], "more": True, "next_url": "n2"},
                 {"items": [dict(items[2], url="u3"), {"book_title": "셋째 책", "user_id": "qq", "article_no": 7, "url": "u4"}],
                  "more": False, "next_url": ""}]
        s._STATE["client"].list = lambda day, sort="", nxt=None: pages[0 if nxt is None else 1]
        s._JOBS.clear()
        s.bulk_complete()
        for _ in range(100):
            if not s._BULK.get("running"):
                break
            time.sleep(0.02)
        self.assertEqual((s._BULK["pages"], s._BULK["seen"], s._BULK["queued"], s._BULK["skipped"]), (2, 3, 2, 1))
        self.assertEqual(sorted(j["key"] for j in s._JOBS), ["bookof:qq/7", "bookof:xyz/3"])
        # bookof 작업: 글이 든 브런치북을 찾아 책으로 받는다
        job = next(j for j in s._JOBS if j["key"] == "bookof:xyz/3")
        s._run(job)
        self.assertEqual((job["kind"], job["key"]), ("book", "book:example1"))
        s._JOBS.clear()

    def test_settings(self):
        s = self.s
        self.assertEqual(s.load_settings()["check_minutes"], 360)
        self.assertTrue(s.load_settings()["auto_check"])
        self.assertEqual(s.clean_settings({"check_hours": "12", "auto_check": False})["check_minutes"], 720)   # 예전 설정(시간)
        self.assertEqual(s.clean_settings({"check_minutes": "10"})["check_minutes"], 10)
        self.assertEqual(s.clean_settings({"check_minutes": 30})["check_minutes"], 30)
        with self.assertRaises(ValueError):
            s.clean_settings({"check_minutes": 15})
        with self.assertRaises(ValueError):
            s.clean_settings({"check_hours": 5})

    def test_new_episode_queues_redownload(self):
        s = self.s
        h = self._download()
        self.assertEqual(h["episode_ids"], [10, 12])
        self.assertTrue(h["auto"] and s.watched(h))
        self.assertEqual(s.check_now(), 0)              # 그대로면 아무것도 안 함
        self.assertEqual(len(s._JOBS), 0)
        self.page = BOOK_PAGE.replace('href="/@@abc/0" aria-disabled="true"', 'href="/@@abc/15" aria-disabled="false"')
        self.assertEqual(s.check_now(), 1)              # 발행 예정이던 3화가 올라옴
        self.assertEqual([(j["key"], j["auto"]) for j in s._JOBS], [("book:example1", True)])
        self.assertEqual(s.check_now(), 1)
        self.assertEqual(len(s._JOBS), 1)               # 이미 대기 중이면 또 넣지 않음
        self.assertTrue(s.load_history()[0]["checked_at"])

    def test_redownload_hands_off_as_edit(self):
        """이미 받은(올린) 책을 새 회차까지 담아 다시 받으면 '수정'으로 넘긴다 - '추가'면 이미 등록된 파일로 건너뛰었다"""
        s = self.s
        calls = []
        orig = s._handoff
        s._handoff = lambda path, action="create": calls.append(action) or True
        try:
            os.remove(self._download()["file"])         # 처음 받는 것처럼 (앞 시험이 받아 둔 파일 치움)
            del calls[:]
            self._download()
            self._download()
        finally:
            s._handoff = orig
        self.assertEqual(calls, ["create", "edit"])

    def test_auto_off_and_complete(self):
        s = self.s
        h = self._download()
        s.api_post("/api/brunch/auto", {"id": h["id"], "auto": False})
        self.assertFalse(s.load_history()[0]["auto"])
        h = self._download()                            # 다시 받아도 끈 선택은 그대로
        self.assertFalse(h["auto"])
        self.page = BOOK_PAGE.replace('href="/@@abc/0" aria-disabled="true"', 'href="/@@abc/15" aria-disabled="false"')
        self.assertEqual(s.check_now(), 0)              # 자동 받기를 끈 책은 확인하지 않음
        s.api_post("/api/brunch/auto", {"id": h["id"], "auto": True})
        self.page = BOOK_PAGE.replace("[연재 브런치북]", "[브런치북]")
        self.assertEqual(s.check_now(), 0)
        self.assertEqual(s.load_history()[0]["status"], "COMPLETE")   # 완결 + 다 받음 -> 더 확인하지 않음
        self.assertFalse(s.watched(s.load_history()[0]))
        with self.assertRaises(s.ApiError):
            s.api_post("/api/brunch/auto", {"id": "nope", "auto": True})

    def test_old_history_without_ids(self):
        """예전 기록(회차 번호 없음)은 회차 수로 비교"""
        s = self.s
        h = {"chapters": 2, "skipped": []}
        book = self.f.parse_book(BOOK_PAGE, "example1")
        self.assertFalse(s._has_new(h, book))
        self.assertTrue(s._has_new({"chapters": 1, "skipped": []}, book))
        self.assertTrue(s._has_new({"episode_ids": [10]}, book))


@unittest.skipUnless(HAVE_REQUESTS, "requests 없음")
class KavitaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from brunch import kavita, service
        cls.k, cls.s = kavita, service

    def test_build_data(self):
        k = self.k
        d = k.build_data("article:abc/7", {"title": "글", "author": "작가", "description": "부제", "url": "u", "status": "COMPLETE"},
                         "글.epub", 120, "", 1794700000000)
        self.assertEqual(d["action"]["code"], "BRAabc_7")
        self.assertEqual(d["meta"]["Publication Status"], "2")
        self.assertEqual(d["files"]["글.epub"], {"cover": "FIRST", "page": 1, "wordcount": 120})
        self.assertEqual(len(d["meta"]["Release Date"]), 8)
        self.assertEqual(k.word_count([{"body": "<p>하나 둘</p><p>셋</p>"}, {"body": ""}]), 3)
        text = k.dump_yaml(d)
        self.assertTrue(text.startswith("action:\n    all_file_is_special: false\n"))

    def test_migrate_old_layout(self):
        """2.55.0까지 작가 폴더에 바로 받은 책은 다시 받아 책 폴더로 옮기고 예전 파일을 지운다"""
        s = self.s
        save = os.path.join(TMP, "books3")
        old = os.path.join(save, "예시 작가", "예시 & 책.epub")
        os.makedirs(os.path.dirname(old), exist_ok=True)
        open(old, "wb").close()
        s._write_json(s._settings_path(), {"save_dir": save})
        s._write_json(s._history_path(), [{"id": "o1", "key": "book:example1", "kind": "book", "title": "예시 & 책", "file": old}])
        with s._LOCK:
            s._JOBS.clear()
        s._STATE["thread"] = threading.Thread()
        s._STATE["thread"].is_alive = lambda: True   # 대기열 스레드를 띄우지 않게
        from brunch import fetch as f

        class FakeClient:
            def book(self, address):
                return f.parse_book(BOOK_PAGE, address)

            def article(self, uid, no):
                return f.parse_article(ARTICLE_PAGE % "false", f.article_url(uid, no))

            def get_image(self, url):
                return None
        s._STATE["client"] = FakeClient()
        try:
            self.assertEqual(s.migrate_layout(), 1)
            job = s._JOBS[0]
            s._run(job)
            self.assertFalse(os.path.exists(old))
            new = os.path.join(save, "예시 작가", "예시 & 책", "예시 & 책.epub")
            self.assertTrue(os.path.isfile(new) and os.path.isfile(os.path.join(os.path.dirname(new), "kavita.yaml")))
            self.assertEqual(s.load_history()[0]["layout"], s.LAYOUT)
            with s._LOCK:
                s._JOBS.clear()
            self.assertEqual(s.migrate_layout(), 0)       # 한 번만
            # 목록에서 빼며 파일도 지우면 kavita.yaml과 빈 책 폴더도 치운다
            s.api_post("/api/brunch/forget", {"id": s.load_history()[0]["id"], "remove_file": True})
            self.assertFalse(os.path.exists(os.path.dirname(new)))
        finally:
            s._STATE["client"] = None
            s._STATE["thread"] = None


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
