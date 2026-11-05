# -*- coding: utf-8 -*-
"""BookOasis 3D 서재 1층 '브런치 연재 낭독 코너' - 브런치(brunch.co.kr) 요일별 연재 목록·글 본문·Edge 음성

yume-script/ym_brunch 플러그인(BookOasis용)의 서버 코드를 그대로 옮겨 왔다:
  목록  GET https://api.brunch.co.kr/v2/serial-brunchbook/all?dayOfWeek=..&orderKeyword=..&serialStatus=ONGOING
  본문  GET https://brunch.co.kr/@@{userId}/{articleNo} 에서 ARTICLE_DATA + #ArticleView (허용한 태그만 남김)
  음성  edge-tts 패키지가 있으면 마이크로소프트 Edge 무료 음성(비공식 경로) mp3, 없으면 화면이 브라우저 음성만 쓴다.
여기에 더한 것: 목록마다 '새 글' 표시(브런치의 new 표시 또는 NEW_HOURS 안에 올라온 회차)와 오늘 요일 요약(fetch_today).
브런치의 화면용 비공식 API라 브런치가 바뀌면 깨질 수 있다.
"""
import asyncio
import collections
import json
import re
import threading
import time
from html import escape, unescape
from html.parser import HTMLParser
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_URL = "https://api.brunch.co.kr/v2/serial-brunchbook/all"
WEB_URL = "https://brunch.co.kr"
DAYS = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY")
SORTS = ("PUBLISH_TIME", "DONATION_TOTAL_AMOUNT", "LIKE_COUNT")
USER_AGENT = "Mozilla/5.0 (BookOasisAssistant 3D library brunch corner)"
TIMEOUT_SEC = 10
CACHE_SEC = 300  # 같은 목록을 탭 전환마다 다시 받지 않게 5분 보관
ARTICLE_CACHE_SEC = 600

_cache = {}
_cache_lock = threading.Lock()


def _https(url):
    # 브런치 이미지 주소가 http://로 와서 https 페이지에선 혼합 콘텐츠로 막힌다 (CDN은 https도 받음)
    if isinstance(url, str) and url.startswith("http://"):
        return "https://" + url[len("http://"):]
    if isinstance(url, str) and url.startswith("//"):
        return "https:" + url
    return url or ""


def _cached(key, ttl):
    with _cache_lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
    return None


def _store(key, value):
    with _cache_lock:
        if len(_cache) > 200:
            _cache.clear()
        _cache[key] = (time.time(), value)


def _get(url, accept):
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept, "Referer": WEB_URL + "/"})
    resp = urlopen(req, timeout=TIMEOUT_SEC)
    try:
        return resp.read().decode("utf-8", "replace")
    finally:
        resp.close()


def _fetch_json(url):
    hit = _cached(url, CACHE_SEC)
    if hit is not None:
        return hit
    body = json.loads(_get(url, "application/json"))
    if body.get("code") != 200 or not isinstance(body.get("data"), dict):
        raise RuntimeError(body.get("title") or body.get("desc") or "브런치 응답 오류")
    _store(url, body["data"])
    return body["data"]


def _item(raw):
    user_id = raw.get("userId") or ""
    article_no = raw.get("articleNo")
    return {
        "book_title": raw.get("magazineTitle") or "",
        "author": raw.get("userName") or "",
        "author_image": _https(raw.get("userImage")),
        "author_url": "%s/@@%s" % (WEB_URL, user_id) if user_id else "",
        "title": raw.get("articleTitle") or "",
        "subtitle": raw.get("articleSubTitle") or "",
        "summary": (raw.get("articleContentSummary") or "").strip(),
        "image": _https(raw.get("articleImage")),
        "url": "%s/@@%s/%s" % (WEB_URL, user_id, article_no) if user_id and article_no else "",
        "user_id": user_id,
        "article_no": article_no or 0,
        "publish_time": raw.get("publishTime") or 0,
        "like_count": raw.get("likeCount") or 0,
        "donation_amount": raw.get("donationTotalAmount") or 0,
        "donation_count": raw.get("donationCommentCount") or 0,
        "status": raw.get("serialStatus") or "",
        "is_new": bool(raw.get("new")),
    }


def fetch_list(day, sort, next_url=None):
    """day: MONDAY..SUNDAY 또는 COMPLETE(완결). next_url은 직전 응답의 nextUrl."""
    if next_url:
        # 화면이 넘겨준 값이라 아무 주소나 부르지 않도록 브런치 API로만 제한
        if not str(next_url).startswith(API_URL + "?"):
            raise ValueError("잘못된 다음 페이지 주소입니다.")
        url = next_url
    elif day == "COMPLETE":
        url = API_URL + "?" + urlencode({"serialStatus": "COMPLETE"})
    else:
        if day not in DAYS:
            raise ValueError("알 수 없는 요일: %s" % day)
        if sort not in SORTS:
            sort = SORTS[0]
        url = API_URL + "?" + urlencode({"dayOfWeek": day, "orderKeyword": sort,
                                         "serialStatus": "ONGOING"})
    data = _fetch_json(url)
    return {
        "items": [_item(x) for x in (data.get("list") or []) if isinstance(x, dict)],
        "more": bool(data.get("moreList")),
        "next_url": data.get("nextUrl") or "",
    }


# ── 글 본문 ──
_ALLOWED = {"p", "br", "b", "strong", "i", "em", "u", "s", "strike", "del", "sub", "sup",
            "h1", "h2", "h3", "h4", "blockquote", "ul", "ol", "li", "hr", "a", "img", "div",
            "figure", "figcaption", "table", "thead", "tbody", "tr", "td", "th", "small"}
_VOID = {"br", "hr", "img"}
_DROP = {"script", "style", "noscript", "button", "svg", "iframe", "object", "embed", "form",
         "input", "select", "textarea", "video", "audio", "template"}
# 브런치 본문 블록(wrap_item item_type_X ...)에서 화면 모양에 필요한 것만 class로 옮긴다
_KEEP_CLASS = re.compile(r"^(item_type_\w+|blockquote_type\d|hr_type_\d|img_align_\w+)$")


class _Sanitizer(HTMLParser):
    """허용한 태그만 남기고 속성은 href/src/class(브런치 블록 종류)만. 결과는 화면이 innerHTML로 넣는다."""

    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.out = []
        self.drop_depth = 0
        self.stack = []

    def handle_starttag(self, tag, attrs):
        if self.drop_depth:
            if tag in _DROP:
                self.drop_depth += 1
            return
        if tag in _DROP:
            self.drop_depth = 1
            return
        if tag not in _ALLOWED:
            return
        a = dict(attrs)
        parts = [tag]
        classes = [c for c in (a.get("class") or "").split() if _KEEP_CLASS.match(c)]
        if classes:
            parts.append('class="%s"' % escape(" ".join("bb-" + c for c in classes)))
        if tag == "a":
            href = _https(a.get("href") or "")
            if href.startswith("/"):
                href = WEB_URL + href
            if href.startswith("https://"):
                parts.append('href="%s" target="_blank" rel="noopener noreferrer"' % escape(href))
        elif tag == "img":
            src = _https(a.get("src") or a.get("data-src") or "")
            if not src.startswith("https://"):
                return
            parts.append('src="%s" loading="lazy" referrerpolicy="no-referrer" alt="%s"'
                         % (escape(src), escape(a.get("alt") or "")))
        self.out.append("<%s>" % " ".join(parts))
        if tag not in _VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID and self.stack and self.stack[-1] == tag:
            self.stack.pop()
            self.out.append("</%s>" % tag)

    def handle_endtag(self, tag):
        if self.drop_depth:
            if tag in _DROP:
                self.drop_depth -= 1
            return
        if tag in _VOID or tag not in self.stack:
            return
        while self.stack:  # 브런치 HTML이 짝이 안 맞아도 열린 태그를 정리하며 닫는다
            t = self.stack.pop()
            self.out.append("</%s>" % t)
            if t == tag:
                break

    def handle_data(self, data):
        if not self.drop_depth:
            self.out.append(escape(data, quote=False))

    def result(self):
        self.close()
        while self.stack:
            self.out.append("</%s>" % self.stack.pop())
        return "".join(self.out)


def sanitize(html_text):
    p = _Sanitizer()
    p.feed(html_text)
    return p.result()


def _between(text, start_marker, end_markers):
    i = text.find(start_marker)
    if i < 0:
        return ""
    i = text.find(">", i) + 1
    ends = [j for j in (text.find(m, i) for m in end_markers) if j >= 0]
    return text[i:min(ends)] if ends else text[i:]


_EP_RE = re.compile(r'<li class="item_magazine">(.*?)</li>', re.S)


def _episodes(page):
    block = _between(page, 'class="list_magazine"', ["</ul>"])
    eps = []
    for li in _EP_RE.findall(block):
        num = re.search(r'class="txt_num">(?:\s*<span[^>]*>.*?</span>)?\s*([^<]*?)\s*<', li, re.S)
        title = re.search(r'class="txt_magazine">([^<]*)<', li)
        link = re.search(r'href="/@@([A-Za-z0-9]+)/(\d+)"', li)
        info = re.search(r'class="info_tobe">\s*([^<]*?)\s*<', li, re.S)
        eps.append({
            "num": num.group(1).strip() if num else "",
            "title": unescape(title.group(1).strip()) if title else "",
            "user_id": link.group(1) if link else "",
            "article_no": int(link.group(2)) if link else 0,
            "current": "magazine_current" in li,
            "upcoming": unescape(info.group(1)) if info else "",
        })
    return eps


_ID_RE = re.compile(r"^[A-Za-z0-9]{1,40}$")


def fetch_article(user_id, article_no):
    user_id = str(user_id or "")
    if not _ID_RE.match(user_id) or not str(article_no or "").isdigit():
        raise ValueError("잘못된 글 주소입니다.")
    url = "%s/@@%s/%s" % (WEB_URL, user_id, int(article_no))
    hit = _cached(url, ARTICLE_CACHE_SEC)
    if hit is not None:
        return hit
    page = _get(url, "text/html")
    m = re.search(r'<script type="application/json" id="ARTICLE_DATA">(.*?)</script>', page, re.S)
    meta = json.loads(m.group(1)) if m else {}
    if not meta:
        raise RuntimeError("글을 찾을 수 없습니다(삭제됐거나 비공개일 수 있음).")
    view = re.search(r'<div id="ArticleView" class="([^"]*)"', page)
    align = ""
    if view:
        for a in ("center", "right", "left"):
            if "text_align_" + a in view.group(1):
                align = a
    body = _between(page, 'id="ArticleView"', ['<div class="info_keyword"', 'class="info_article magazine_article"'])
    book = re.search(r'class="link_magazinetit[^"]*">\s*(?:<span class="tag_state">[^<]*</span>)?\s*([^<]*?)\s*</a>', page)
    result = {
        "title": meta.get("title") or "",
        "subtitle": meta.get("subTitle") or "",
        "author": meta.get("authorName") or "",
        "publish_time": meta.get("publishTime") or 0,
        "like_count": meta.get("likeCount") or 0,
        "comment_count": meta.get("commentCount") or 0,
        "book_title": unescape(book.group(1)) if book else "",
        "book_url": WEB_URL + meta["magazineAddressUri"] if meta.get("magazineAddressUri") else "",
        "cover": _https(meta.get("articleImageUrl")),
        "url": url,
        "align": align,
        # 멤버십(유료) 글은 페이지에 앞부분만 있어서 원문 링크를 같이 안내한다
        "restricted": bool(meta.get("isMembershipContent") or meta.get("isRestrict")),
        "body": sanitize(body),
        "episodes": _episodes(page),
    }
    _store(url, result)
    return result


# ── 서버 음성 (Edge) ──
try:
    import edge_tts
except Exception:  # noqa: BLE001 - 없거나 깨져 있어도 플러그인 전체가 안 뜨면 안 된다. 브라우저 음성만 쓴다
    edge_tts = None

# (ShortName, 화면 이름) - edge-tts --list-voices 에서 한국어와, 한국어도 읽는 Multilingual만 추렸다
EDGE_VOICES = [
    ("ko-KR-SunHiNeural", "선히 (여성)"),
    ("ko-KR-InJoonNeural", "인준 (남성)"),
    ("ko-KR-HyunsuMultilingualNeural", "현수 (남성)"),
    ("en-US-AvaMultilingualNeural", "Ava (여성, 다국어)"),
    ("en-US-EmmaMultilingualNeural", "Emma (여성, 다국어)"),
    ("en-US-AndrewMultilingualNeural", "Andrew (남성, 다국어)"),
    ("en-US-BrianMultilingualNeural", "Brian (남성, 다국어)"),
    ("en-AU-WilliamMultilingualNeural", "William (남성, 다국어)"),
    ("de-DE-SeraphinaMultilingualNeural", "Seraphina (여성, 다국어)"),
    ("de-DE-FlorianMultilingualNeural", "Florian (남성, 다국어)"),
    ("fr-FR-VivienneMultilingualNeural", "Vivienne (여성, 다국어)"),
    ("fr-FR-RemyMultilingualNeural", "Remy (남성, 다국어)"),
    ("it-IT-GiuseppeMultilingualNeural", "Giuseppe (남성, 다국어)"),
    ("pt-BR-ThalitaMultilingualNeural", "Thalita (여성, 다국어)"),
]
_EDGE_IDS = set(v[0] for v in EDGE_VOICES)
TTS_MAX_CHARS = 600
TTS_TIMEOUT_SEC = 30
TTS_CACHE_BYTES = 30 * 1024 * 1024  # 같은 문장을 다시 들을 때(되감기·이어 듣기) 다시 받지 않게

_audio_cache = collections.OrderedDict()
_audio_cache_size = [0]
_audio_lock = threading.Lock()


def tts_voices():
    if edge_tts is None:
        return {"available": False, "voices": [],
                "reason": "서버에 edge-tts가 없습니다 - 서비스가 쓰는 파이썬(venv)에 설치 후 재시작 (3D 서재 가이드 7장)"}
    return {"available": True, "voices": [{"id": i, "name": n} for i, n in EDGE_VOICES]}


def _edge_synth(voice, text):
    async def run():
        buf = bytearray()
        async for part in edge_tts.Communicate(text, voice, receive_timeout=TTS_TIMEOUT_SEC).stream():
            if part.get("type") == "audio":
                buf.extend(part["data"])
        return bytes(buf)

    # 코어가 이벤트 루프 안에서 부르더라도 충돌하지 않게 별도 스레드에서 새 루프로 돌린다
    box = {}

    def worker():
        try:
            box["data"] = asyncio.run(run())
        except Exception as e:  # noqa: BLE001
            box["error"] = e

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join(TTS_TIMEOUT_SEC + 5)
    if t.is_alive():
        raise RuntimeError("음성 서버 응답이 너무 늦습니다.")
    if "error" in box:
        raise box["error"]
    if not box.get("data"):
        raise RuntimeError("음성을 받지 못했습니다.")
    return box["data"]


def tts_audio(voice, text):
    if edge_tts is None:
        raise RuntimeError(tts_voices()["reason"])
    if voice not in _EDGE_IDS:
        raise ValueError("알 수 없는 목소리입니다.")
    text = re.sub(r"\s+", " ", str(text or "")).strip()[:TTS_MAX_CHARS]
    if not text:
        raise ValueError("읽을 글이 없습니다.")
    key = voice + "\n" + text
    with _audio_lock:
        hit = _audio_cache.get(key)
        if hit is not None:
            _audio_cache.move_to_end(key)
            return hit
    data = _edge_synth(voice, text)
    with _audio_lock:
        _audio_cache[key] = data
        _audio_cache_size[0] += len(data)
        while _audio_cache_size[0] > TTS_CACHE_BYTES and _audio_cache:
            _, old = _audio_cache.popitem(last=False)
            _audio_cache_size[0] -= len(old)
    return data


# ── 3D 서재에서 더한 것 ──
NEW_HOURS = 36   # 이 시간 안에 올라온 회차는 '새 글'


def _mark_new(items):
    now_ms = time.time() * 1000
    for it in items:
        pt = it.get("publish_time") or 0
        it["fresh"] = bool(it.get("is_new")) or (pt and now_ms - pt < NEW_HOURS * 3600 * 1000)
    return items


def list_day(day, sort, next_url=None):
    out = fetch_list(day, sort, next_url)
    _mark_new(out["items"])
    return out


def today_key():
    return DAYS[time.localtime().tm_wday]


def fetch_today():
    """1층 낭독 코너 안내판용: 오늘 요일 연재 중 새 글 (최신순 앞 20개 기준)"""
    day = today_key()
    out = list_day(day, "PUBLISH_TIME")
    fresh = [x for x in out["items"] if x["fresh"]]
    return {"day": day, "fresh": len(fresh), "total": len(out["items"]),
            "items": [{"title": x["title"], "book_title": x["book_title"], "author": x["author"], "fresh": x["fresh"]}
                      for x in (fresh or out["items"])[:6]]}


def enabled():
    """LIB3D_BRUNCH (기본 켜짐) - 끄면 1층 낭독 코너를 짓지 않는다"""
    from . import config
    return str(config.env("LIB3D_BRUNCH", "true") or "true").strip().lower() not in ("false", "0", "no", "off")
