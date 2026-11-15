# -*- coding: utf-8 -*-
"""브런치(brunch.co.kr) 목록·브런치북·글 받기 (YMPlayer ym_player/brunch.py를 requests로 옮기고 브런치북 목차를 더함)

- 연재 목록: 브런치 화면이 쓰는 공개 API (로그인 없음)
    GET https://api.brunch.co.kr/v2/serial-brunchbook/all?dayOfWeek=MONDAY&orderKeyword=PUBLISH_TIME&serialStatus=ONGOING
    (완결: ?serialStatus=COMPLETE) -> data.list(20개씩), data.moreList, data.nextUrl
- 브런치북 목차: https://brunch.co.kr/brunchbook/<주소> 페이지의 연재 목차(발행된 회차 전부, 발행 예정은 링크가 막혀 있음)
- 글: https://brunch.co.kr/@@{userId}/{articleNo} (또는 /@필명/번호) 페이지에서
    <script id="ARTICLE_DATA"> JSON(제목·작가) + <div id="ArticleView"> 본문(허용한 태그만 남김)
  멤버십(유료) 글은 페이지에 있는 앞부분만 담고 원문 링크를 남긴다 (유료 부분을 우회하지 않는다).
- 정해진 브런치 주소만 부른다 (넘겨받은 다음 페이지 주소, 리다이렉트도 검사). 그림은 카카오 CDN에서만 받는다.
비공식(화면용) 페이지라 브런치가 바뀌면 깨질 수 있다 - 그때는 parse_list / parse_book / parse_article만 고치면 된다.
"""
import json
import os
import re
import threading
import time
from html import escape, unescape
from html.parser import HTMLParser
from urllib.parse import urlencode, urljoin, urlparse

# (BRUNCH_TEST_URL: 자동 테스트가 이 컴퓨터의 가짜 브런치를 쓰게 할 때만)
_TEST = os.environ.get("BRUNCH_TEST_URL", "").rstrip("/")
API_URL = f"{_TEST}/api" if _TEST else "https://api.brunch.co.kr/v2/serial-brunchbook/all"
WEB_URL = _TEST or "https://brunch.co.kr"
DAYS = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY")
SORTS = ("PUBLISH_TIME", "DONATION_TOTAL_AMOUNT", "LIKE_COUNT")
# 브라우저와 같은 모양으로 (봇처럼 보이는 이름이면 다른 곳으로 넘기는 경우가 있어서)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
_HOSTS = ("brunch.co.kr", "api.brunch.co.kr", "www.brunch.co.kr")   # 넘겨줘도(리다이렉트) 따라가는 곳은 브런치 주소만
# 그림을 받는 곳: 카카오·다음 CDN (글쓴이가 넣은 다른 주소는 받지 않는다 - 서버가 아무 주소나 부르지 않게)
_IMG_HOST_RE = re.compile(r"(^|\.)(kakaocdn\.net|daumcdn\.net|kakao\.com|brunch\.co\.kr)$")
TIMEOUT = 20
MAX_IMAGE = 15 * 1024 * 1024
LIST_CACHE_SEC = 300
_ID_RE = re.compile(r"^[A-Za-z0-9]{1,40}$")
_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,60}$")
_BOOK_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


class BrunchError(Exception):
    pass


def https(url):
    """브런치 이미지 주소가 http://로 오는 경우가 많다 (CDN은 https도 받음)"""
    if isinstance(url, str) and url.startswith("http://"):
        return "https://" + url[len("http://"):]
    if isinstance(url, str) and url.startswith("//"):
        return "https:" + url
    return url if isinstance(url, str) else ""


def image_allowed(url):
    p = urlparse(url or "")
    if _TEST and str(url).startswith(_TEST):
        return True
    return p.scheme == "https" and bool(_IMG_HOST_RE.search(p.hostname or ""))


_THUMB_RE = re.compile(r"^https://img1\.(kakaocdn|daumcdn)\.net/thumb/([A-Za-z0-9]+)(\.f[a-z]+)?/\?fname=")
_RAW_RE = re.compile(r"^https?://t1\.(kakaocdn|daumcdn)\.net/brunch/service/")


def epub_image_url(url):
    """EPUB에 넣을 그림 주소: 카카오 CDN의 가로 1280px JPEG로 받는다.
    - 본문 그림은 이미 줄인 WebP(thumb/R1280x0.fwebp)라 JPEG로만 바꾼다 (WebP를 못 그리는 전자책 리더가 있어서)
    - 표지·원본 주소(t1.kakaocdn.net/brunch/service/…)는 10MB가 넘는 원본이 오기도 해서 줄인 것으로"""
    m = _THUMB_RE.match(url or "")
    if m:
        size = m.group(2) if m.group(2).startswith("R") else "R1280x0"
        return "https://img1.%s.net/thumb/%s.fjpg/?fname=%s" % (m.group(1), size, url[m.end():])
    if _RAW_RE.match(url or ""):
        return "https://img1.kakaocdn.net/thumb/R1280x0.fjpg/?fname=" + url
    return url


# ── 연재 목록 ──
def item(raw):
    user_id = str(raw.get("userId") or "")
    no = raw.get("articleNo")
    ok = bool(_ID_RE.match(user_id)) and str(no or "").isdigit()
    return {
        "book_title": raw.get("magazineTitle") or "",
        "author": raw.get("userName") or "",
        "title": raw.get("articleTitle") or "",
        "subtitle": raw.get("articleSubTitle") or "",
        "summary": (raw.get("articleContentSummary") or "").strip()[:300],
        "image": https(raw.get("articleImage")),
        "url": f"{WEB_URL}/@@{user_id}/{no}" if ok else "",
        "user_id": user_id if ok else "",
        "article_no": int(no) if ok else 0,
        "publish_time": raw.get("publishTime") or 0,
        "like_count": raw.get("likeCount") or 0,
        "status": raw.get("serialStatus") or "",
        "is_new": bool(raw.get("new")),
    }


def list_url(day, sort, next_url=None):
    """요일(MONDAY..SUNDAY) 또는 COMPLETE(완결) -> 부를 주소. next_url은 직전 응답의 nextUrl (브런치 API 주소만)"""
    if next_url:
        if not str(next_url).startswith(API_URL + "?"):
            raise ValueError("잘못된 다음 페이지 주소입니다.")
        return str(next_url)
    if day == "COMPLETE":
        return API_URL + "?" + urlencode({"serialStatus": "COMPLETE"})
    if day not in DAYS:
        raise ValueError(f"알 수 없는 요일: {day}")
    return API_URL + "?" + urlencode({"dayOfWeek": day, "orderKeyword": sort if sort in SORTS else SORTS[0],
                                      "serialStatus": "ONGOING"})


def parse_list(body):
    if not isinstance(body, dict) or body.get("code") != 200 or not isinstance(body.get("data"), dict):
        raise BrunchError((body or {}).get("title") or (body or {}).get("desc") or "브런치 응답 오류")
    data = body["data"]
    return {"items": [item(x) for x in (data.get("list") or []) if isinstance(x, dict)],
            "more": bool(data.get("moreList")), "next_url": data.get("nextUrl") or ""}


# ── 글 본문 정리 ──
_ALLOWED = {"p", "br", "b", "strong", "i", "em", "u", "s", "strike", "del", "sub", "sup",
            "h1", "h2", "h3", "h4", "blockquote", "ul", "ol", "li", "hr", "a", "img", "div",
            "figure", "figcaption", "table", "thead", "tbody", "tr", "td", "th", "small"}
_RENAME = {"strike": "s"}
_VOID = {"br", "hr", "img"}
_DROP = {"script", "style", "noscript", "button", "svg", "iframe", "object", "form",
         "select", "textarea", "video", "audio", "template"}
_DROP_VOID = {"input", "embed", "source", "track", "link", "meta"}   # 닫는 태그가 없는 것 - 그 태그만 버린다
_KEEP_CLASS = re.compile(r"^(item_type_\w+|blockquote_type\d|hr_type_\d|img_align_\w+)$")


class _Sanitizer(HTMLParser):
    """허용한 태그만, 속성은 href/src/class(브런치 블록 종류)만 남긴 XHTML 조각을 만든다.
    on_img(주소) -> EPUB 안의 그림 경로 (None이면 그 그림은 뺀다)"""

    def __init__(self, on_img=None):
        super().__init__(convert_charrefs=True)
        self.out, self.stack, self.drop = [], [], 0
        self.on_img = on_img

    def handle_starttag(self, tag, attrs):
        if tag in _DROP_VOID:
            return
        if self.drop:
            self.drop += tag in _DROP
            return
        if tag in _DROP:
            self.drop = 1
            return
        if tag not in _ALLOWED:
            return
        a = dict(attrs)
        name = _RENAME.get(tag, tag)
        parts = [name]
        classes = [c for c in (a.get("class") or "").split() if _KEEP_CLASS.match(c)]
        if classes:
            parts.append('class="%s"' % escape(" ".join("bb-" + c for c in classes)))
        if tag == "a":
            href = https(a.get("href") or "")
            if href.startswith("/"):
                href = WEB_URL + href
            if href.startswith("https://"):
                parts.append('href="%s"' % escape(href))
        elif tag == "img":
            src = https(a.get("src") or a.get("data-src") or "")
            local = self.on_img(src) if (self.on_img and src.startswith("https://")) else None
            if not local:
                return
            parts.append('src="%s" alt="%s"' % (escape(local), escape(a.get("alt") or "")))
        if tag in _VOID:
            self.out.append("<%s/>" % " ".join(parts))
            return
        self.out.append("<%s>" % " ".join(parts))
        self.stack.append(name)

    def handle_startendtag(self, tag, attrs):
        """<br/> <img .../> <p/> 처럼 스스로 닫는 태그"""
        if self.drop or tag in _DROP or tag not in _ALLOWED:
            return   # 버리는 태그는 안에 든 것이 없으니 무시만 하면 된다
        self.handle_starttag(tag, attrs)
        if tag in _VOID:
            return
        name = _RENAME.get(tag, tag)
        if self.stack and self.stack[-1] == name:
            self.stack.pop()
            self.out.append("</%s>" % name)

    def handle_endtag(self, tag):
        if self.drop:
            self.drop -= tag in _DROP
            return
        name = _RENAME.get(tag, tag)
        if tag in _VOID or name not in self.stack:
            return
        while self.stack:
            t = self.stack.pop()
            self.out.append("</%s>" % t)
            if t == name:
                break

    def handle_data(self, data):
        if not self.drop:
            self.out.append(escape(data, quote=False))

    def result(self):
        self.close()
        while self.stack:
            self.out.append("</%s>" % self.stack.pop())
        return "".join(self.out)


def sanitize(html_text, on_img=None):
    p = _Sanitizer(on_img)
    p.feed(html_text or "")
    return p.result()


def _between(text, start_marker, end_markers):
    i = text.find(start_marker)
    if i < 0:
        return ""
    i = text.find(">", i) + 1
    ends = [j for j in (text.find(m, i) for m in end_markers) if j >= 0]
    return text[i:min(ends)] if ends else text[i:]


def _strip_tags(s):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


# ── 주소 ──
def article_url(user_id, article_no):
    user_id = str(user_id or "")
    if not str(article_no or "").isdigit():
        raise ValueError("잘못된 글 주소입니다.")
    if _ID_RE.match(user_id):
        return f"{WEB_URL}/@@{user_id}/{int(article_no)}"
    if user_id.startswith("@") and _NAME_RE.match(user_id[1:]):   # 필명 주소 (/@필명/번호)
        return f"{WEB_URL}/{user_id}/{int(article_no)}"
    raise ValueError("잘못된 글 주소입니다.")


def book_url(address):
    if not _BOOK_RE.match(str(address or "")):
        raise ValueError("잘못된 브런치북 주소입니다.")
    return f"{WEB_URL}/brunchbook/{address}"


def parse_input(text):
    """사용자가 붙여 넣은 주소 -> ("book", 주소) / ("article", (user_id, 번호))
    https://brunch.co.kr/brunchbook/abc · https://brunch.co.kr/@@4r3L/12 · https://brunch.co.kr/@필명/12 (http·www·모바일 주소도)"""
    s = str(text or "").strip()
    if not s:
        raise ValueError("브런치 주소를 넣으세요.")
    if not re.match(r"^[a-z]+://", s):
        s = "https://" + s.lstrip("/")
    p = urlparse(s)
    host = (p.hostname or "").lower()
    if not (host in _HOSTS or host == "m.brunch.co.kr" or (_TEST and s.startswith(_TEST))):
        raise ValueError("브런치(brunch.co.kr) 주소가 아닙니다.")
    parts = [x for x in p.path.split("/") if x]
    if len(parts) >= 2 and parts[0] == "brunchbook" and _BOOK_RE.match(parts[1]):
        return "book", parts[1]
    if len(parts) >= 2 and parts[1].isdigit():
        if parts[0].startswith("@@") and _ID_RE.match(parts[0][2:]):
            return "article", (parts[0][2:], int(parts[1]))
        if parts[0].startswith("@") and _NAME_RE.match(parts[0][1:]):
            return "article", (parts[0], int(parts[1]))
    raise ValueError("브런치북 주소(brunch.co.kr/brunchbook/…)나 글 주소(brunch.co.kr/@@…/번호)를 넣으세요.")


# ── 브런치북 목차 ──
_POST_RE = re.compile(r'<a class="cont_post" href="/@@([A-Za-z0-9]+)/(\d+)" aria-disabled="(true|false)"(.*?)</a>', re.S)


def parse_book(page, address):
    title = re.search(r'class="bb-book-title">([^<]*)<', page)
    og_title = re.search(r'<meta property="og:title" content="([^"]*)"', page)
    raw_title = unescape(title.group(1)).strip() if title else ""
    status = ""
    if og_title:
        t = unescape(og_title.group(1)).strip()
        m = re.match(r"^\[([^\]]*)\]\s*(.*)$", t)
        if m:
            # [연재 브런치북] = 연재 중, [브런치북] = 발행을 마친 책
            status = "ONGOING" if "연재" in m.group(1) else "COMPLETE"
            t = m.group(2)
        raw_title = raw_title or t
    if not raw_title:
        raise BrunchError("브런치북을 찾을 수 없습니다 (주소가 틀렸거나 비공개일 수 있음).")
    author = re.search(r'class="bb-tit-bloger">([^<]*)<', page)
    cover = re.search(r'<meta property="og:image" content="([^"]*)"', page)
    desc = re.search(r'<meta property="og:description" content="([^"]*)"', page)
    total = re.search(r'article-total-count">(\d+)', page)
    eps, planned = [], 0
    for uid, no, disabled, inner in _POST_RE.findall(page):
        if disabled == "true":   # 발행 예정 (아직 글이 없음)
            planned += 1
            continue
        num = re.search(r'class="num_txt"[^>]*>\s*([^<]*)', inner)
        tit = re.search(r'class="tit_post">(.*?)</strong>', inner, re.S)
        if any(e["article_no"] == int(no) and e["user_id"] == uid for e in eps):
            continue
        eps.append({"num": (num.group(1).strip() if num else "") or str(len(eps) + 1),
                    "title": _strip_tags(tit.group(1)) if tit else "", "user_id": uid, "article_no": int(no)})
    return {"address": address, "url": book_url(address), "title": raw_title,
            "author": unescape(author.group(1)).strip() if author else "",
            "cover": https(unescape(cover.group(1))) if cover else "",
            "description": unescape(desc.group(1)).strip() if desc else "",
            "status": status, "total": int(total.group(1)) if total else len(eps) + planned,
            "planned": planned, "episodes": eps}


# ── 글 ──
def parse_article(page, url):
    m = re.search(r'<script type="application/json" id="ARTICLE_DATA">(.*?)</script>', page, re.S)
    try:
        meta = json.loads(m.group(1)) if m else {}
    except ValueError:
        meta = {}
    if not meta:
        raise BrunchError("글을 찾을 수 없습니다 (삭제됐거나 비공개일 수 있음).")
    body = _between(page, 'id="ArticleView"', ['<div class="info_keyword"', 'class="info_article magazine_article"'])
    book = re.search(r'class="link_magazinetit[^"]*"[^>]*>\s*(?:<span class="tag_state">[^<]*</span>)?\s*([^<]*?)\s*</a>', page)
    book_addr = re.search(r'href="/brunchbook/([A-Za-z0-9_-]+)"', page)
    return {
        "title": meta.get("title") or "",
        "subtitle": meta.get("subTitle") or "",
        "author": meta.get("authorName") or "",
        "publish_time": meta.get("publishTime") or 0,
        "book_title": unescape(book.group(1)) if book else "",
        "book_address": book_addr.group(1) if book_addr else "",
        "cover": https(meta.get("articleImageUrl")),
        "url": url,
        "restricted": bool(meta.get("isMembershipContent") or meta.get("isRestrict")),
        "html": body,   # 아직 정리하지 않은 본문 - sanitize()로 (그림 처리와 함께)
    }


class Client:
    """브런치를 부르는 곳 하나 (쿠키를 기억 - 처음 부를 때 카카오 로그인 확인으로 넘기는 경우가 있어서).
    여러 작업이 함께 써도 되게 잠근다. 너무 빨리 연달아 부르지 않게 요청 사이를 띄운다."""

    def __init__(self, gap=0.6):
        import requests
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9", "Referer": WEB_URL + "/"})
        self.gap = gap
        self._lock = threading.Lock()
        self._last = 0.0
        self._cache = {}

    def _wait(self):
        with self._lock:
            d = self.gap - (time.time() - self._last)
            if d > 0:
                time.sleep(d)
            self._last = time.time()

    def get_text(self, url, accept="text/html"):
        start, bounced = url, 0
        try:
            for _hop in range(8):   # 리다이렉트는 브런치 주소 안에서만 직접 따라간다
                self._wait()
                r = self.s.get(url, headers={"Accept": accept}, timeout=TIMEOUT, allow_redirects=False)
                if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("Location"):
                    nxt = urljoin(url, r.headers["Location"])
                    host = urlparse(nxt).hostname or ""
                    if not (host in _HOSTS or (_TEST and nxt.startswith(_TEST))):
                        # 가끔 카카오 로그인 확인(kauth.kakao.com)으로 넘긴다 - 그 응답이 남긴 쿠키로 같은 주소를 다시 부르면 된다
                        if bounced < 2:
                            bounced += 1
                            url = start
                            time.sleep(0.3 * bounced)
                            continue
                        raise BrunchError(f"브런치가 다른 곳으로 넘겼습니다 ({host or nxt[:80]})")
                    url = nxt
                    continue
                if r.status_code == 404:
                    raise BrunchError("브런치에 없는 주소입니다 (삭제됐거나 비공개일 수 있음).")
                if r.status_code != 200:
                    raise BrunchError(f"브런치 응답 HTTP {r.status_code}")
                r.encoding = "utf-8"
                return r.text
            raise BrunchError("브런치가 너무 여러 번 다른 주소로 넘겼습니다.")
        except BrunchError:
            raise
        except Exception as e:  # noqa: BLE001
            raise BrunchError(f"브런치에 연결하지 못했습니다: {e}") from None

    def get_image(self, url):
        """그림 받기 -> (bytes, media type) 또는 None (허용한 CDN만, 15MB까지). 줄인 JPEG를 먼저, 안 되면 원래 주소로"""
        if not image_allowed(url):
            return None
        small = epub_image_url(url)
        if small != url:
            got = self._image(small)
            if got:
                return got
        return self._image(url)

    def _image(self, url):
        try:
            r = self.s.get(url, headers={"Accept": "image/*"}, timeout=TIMEOUT, stream=True, allow_redirects=False)
            if r.status_code != 200:
                return None
            mt = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if mt not in ("image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml"):
                return None
            data = b""
            for chunk in r.iter_content(65536):
                data += chunk
                if len(data) > MAX_IMAGE:
                    return None
            return data, mt
        except Exception:  # noqa: BLE001
            return None

    def list(self, day, sort="", next_url=None):
        url = list_url(day, sort, next_url)
        hit = self._cache.get(url)
        if hit and time.time() - hit[0] < LIST_CACHE_SEC:
            return hit[1]
        try:
            body = json.loads(self.get_text(url, "application/json"))
        except ValueError:
            raise BrunchError("브런치 응답을 읽지 못했습니다.") from None
        res = parse_list(body)
        if len(self._cache) > 100:
            self._cache.clear()
        self._cache[url] = (time.time(), res)
        return res

    def book(self, address):
        url = book_url(address)
        return parse_book(self.get_text(url), address)

    def article(self, user_id, article_no):
        url = article_url(user_id, article_no)
        return parse_article(self.get_text(url), url)
