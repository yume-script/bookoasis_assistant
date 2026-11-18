# -*- coding: utf-8 -*-
"""브런치북 -> EPUB 3 (표준 라이브러리만)

- 회차 하나 = 장(章) 하나 (text/ch001.xhtml …), 목차(nav.xhtml + 옛 리더용 toc.ncx)
- 표지(브런치북 표지 그림) / 책 정보 쪽(제목·작가·소개·원문 주소)
- 본문 그림은 images/ 아래에 넣는다 (fetch.Client.get_image)
- 멤버십 글은 페이지에 공개된 앞부분만 담기고 원문 링크를 남긴다
"""
import os
import uuid
import zipfile
from datetime import datetime, timezone
from xml.sax.saxutils import escape

CSS = """
body { margin: 0 4%; line-height: 1.85; word-break: keep-all; overflow-wrap: break-word; }
p { margin: 0 0 0.8em 0; }
h1 { font-size: 1.35em; margin: 1.4em 0 0.3em 0; line-height: 1.4; }
h2.sub { font-size: 0.95em; font-weight: normal; color: #666; margin: 0 0 1.6em 0; }
p.date { font-size: 0.8em; color: #888; margin: -1.2em 0 1.6em 0; }
.num { display: block; font-size: 0.8em; color: #888; letter-spacing: 0.1em; margin-top: 2em; }
img { max-width: 100%; height: auto; }
figure, div.bb-item_type_img { text-align: center; margin: 1em 0; }
figcaption { font-size: 0.85em; color: #777; }
blockquote { margin: 1em 0; padding: 0 0 0 1em; border-left: 3px solid #ccc; color: #555; }
hr { border: 0; border-top: 1px solid #ccc; margin: 2em 20%; }
.note { font-size: 0.85em; color: #777; border-top: 1px solid #ddd; margin-top: 2em; padding-top: 0.8em; }
.cover { text-align: center; margin: 0; padding: 0; }
.cover img { max-height: 95vh; }
.info h1 { text-align: center; margin-top: 3em; }
.info .author { text-align: center; color: #555; }
.info .desc { margin-top: 2em; font-size: 0.95em; }
.info .src { margin-top: 2em; font-size: 0.8em; color: #888; word-break: break-all; }
"""

_EXT = {"image/png": ".png", "image/gif": ".gif", "image/webp": ".webp", "image/svg+xml": ".svg"}


def ext_of(media_type):
    return _EXT.get(media_type, ".jpg")


def _xhtml(title, body, css="../style.css"):
    return ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" '
            'xml:lang="ko" lang="ko"><head><meta charset="utf-8"/><title>%s</title>'
            '<link rel="stylesheet" type="text/css" href="%s"/></head><body>%s</body></html>'
            % (escape(title), css, body))


def build(path, book, chapters, images, cover=None, identifier=None):
    """path에 EPUB을 만든다 (임시 파일에 쓰고 바꿔 넣음).
    book: {title, author, description, url, status}
    chapters: [{title, subtitle, num, body(XHTML 조각, 그림은 images/이름), url, restricted}]
    images: {이름: (bytes, media type)} - 본문 그림, cover: (bytes, media type) 또는 None"""
    if not chapters:
        raise ValueError("담을 글이 없습니다.")
    ident = identifier or "urn:uuid:%s" % uuid.uuid4()
    title = book.get("title") or chapters[0].get("title") or "브런치"
    docs = []   # (id, href, 제목, xhtml, 목차에 넣을지)
    if cover:
        cover_name = "cover" + ext_of(cover[1])
        docs.append(("cover", "text/cover.xhtml", "표지",
                     _xhtml(title, '<div class="cover"><img src="images/%s" alt="표지"/></div>' % cover_name), False))
    info = ['<div class="info"><h1>%s</h1>' % escape(title)]
    if book.get("author"):
        info.append('<p class="author">%s</p>' % escape(book["author"]))
    if book.get("description"):
        info.append('<p class="desc">%s</p>' % escape(book["description"]))
    if book.get("url"):
        info.append('<p class="src">원문: <a href="%s">%s</a><br/>받은 날: %s</p>' % (
            escape(book["url"]), escape(book["url"]), datetime.now().strftime("%Y-%m-%d")))
    info.append("</div>")
    docs.append(("info", "text/info.xhtml", "책 정보", _xhtml(title, "".join(info)), False))
    for i, ch in enumerate(chapters, 1):
        head = ""
        if ch.get("num"):
            head += '<span class="num">%s</span>' % escape(str(ch["num"]))
        head += "<h1>%s</h1>" % escape(ch.get("title") or "%d화" % i)
        if ch.get("subtitle"):
            head += '<h2 class="sub">%s</h2>' % escape(ch["subtitle"])
        if ch.get("published"):   # 브런치에 발행된 날
            head += '<p class="date">%s 발행</p>' % escape(ch["published"].replace("-", "."))
        tail = ""
        if ch.get("restricted"):
            tail = ('<p class="note">멤버십 글이라 공개된 앞부분만 담았습니다. 전체는 브런치에서 읽을 수 있습니다: '
                    '<a href="%s">%s</a></p>' % (escape(ch.get("url") or ""), escape(ch.get("url") or "")))
        label = ("%s. " % ch["num"] if ch.get("num") else "") + (ch.get("title") or "%d화" % i)
        docs.append(("ch%03d" % i, "text/ch%03d.xhtml" % i, label, _xhtml(label, head + (ch.get("body") or "") + tail), True))

    toc = [d for d in docs if d[4]]
    nav = _xhtml(title, '<nav epub:type="toc" id="toc"><h1>목차</h1><ol>%s</ol></nav>' % "".join(
        '<li><a href="%s">%s</a></li>' % (d[1], escape(d[2])) for d in toc), css="style.css")
    ncx = ('<?xml version="1.0" encoding="utf-8"?>\n<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
           '<head><meta name="dtb:uid" content="%s"/></head><docTitle><text>%s</text></docTitle><navMap>%s</navMap></ncx>') % (
        escape(ident), escape(title), "".join(
            '<navPoint id="np%d" playOrder="%d"><navLabel><text>%s</text></navLabel><content src="%s"/></navPoint>'
            % (n, n, escape(d[2]), d[1]) for n, d in enumerate(toc, 1)))

    all_images = dict(images or {})
    if cover:
        all_images["cover" + ext_of(cover[1])] = cover
    manifest = ['<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
                '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
                '<item id="css" href="style.css" media-type="text/css"/>']
    for d in docs:
        manifest.append('<item id="%s" href="%s" media-type="application/xhtml+xml"/>' % (d[0], d[1]))
    for n, (name, (_data, mt)) in enumerate(sorted(all_images.items())):
        props = ' properties="cover-image"' if cover and name.startswith("cover.") else ""
        manifest.append('<item id="img%04d" href="text/images/%s" media-type="%s"%s/>' % (n, escape(name), mt, props))
    cover_id = next((m.split('"')[1] for m in manifest if 'properties="cover-image"' in m), "")
    spine = "".join('<itemref idref="%s"/>' % d[0] for d in docs)
    modified = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    meta = ['<dc:identifier id="bookid">%s</dc:identifier>' % escape(ident),
            "<dc:title>%s</dc:title>" % escape(title),
            "<dc:language>ko</dc:language>",
            "<dc:publisher>브런치</dc:publisher>",
            *(["<dc:date>%s</dc:date>" % escape(book["published"])] if book.get("published") else []),
            '<meta property="dcterms:modified">%s</meta>' % modified]
    if book.get("author"):
        meta.append("<dc:creator>%s</dc:creator>" % escape(book["author"]))
    if book.get("description"):
        meta.append("<dc:description>%s</dc:description>" % escape(book["description"]))
    if book.get("url"):
        meta.append("<dc:source>%s</dc:source>" % escape(book["url"]))
    if cover_id:
        meta.append('<meta name="cover" content="%s"/>' % cover_id)
    opf = ('<?xml version="1.0" encoding="utf-8"?>\n'
           '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="ko">'
           '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">%s</metadata>'
           '<manifest>%s</manifest><spine toc="ncx">%s</spine></package>') % ("".join(meta), "".join(manifest), spine)
    container = ('<?xml version="1.0" encoding="utf-8"?>\n'
                 '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                 '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
                 '</rootfiles></container>')

    tmp = path + ".tmp"
    try:
        with zipfile.ZipFile(tmp, "w") as zf:
            zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            z = zipfile.ZIP_DEFLATED
            zf.writestr("META-INF/container.xml", container, compress_type=z)
            zf.writestr("OEBPS/content.opf", opf, compress_type=z)
            zf.writestr("OEBPS/nav.xhtml", nav, compress_type=z)
            zf.writestr("OEBPS/toc.ncx", ncx, compress_type=z)
            zf.writestr("OEBPS/style.css", CSS, compress_type=z)
            for d in docs:
                zf.writestr("OEBPS/" + d[1], d[3], compress_type=z)
            for name, (data, _mt) in all_images.items():
                zf.writestr("OEBPS/text/images/" + name, data, compress_type=zipfile.ZIP_STORED)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return path
