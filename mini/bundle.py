# -*- coding: utf-8 -*-
"""미니게임 화면(/games) 만들기 - 원래 플러그인의 build_mini_game_bundle()을 독립형 화면 틀(shell.js)에 맞춘 것.

  - 게임 선택: 플러그인의 드롭다운 대신 사이드바 서브 메뉴. 주소의 #게임id로 고르고, 바뀌면 게임을 다시 띄운다.
  - 그림 땅따먹기 표지: games/covers/list.json(서버가 covers 폴더를 보고 만들어 줌) + games/covers/<파일>
    폴더는 .env의 MINI_COVERS_DIR (기본: mini/games/picture-territory/covers)
"""
import html
import json
import logging
import os
import re
import threading

from gdw import config

log = logging.getLogger("mini")
HERE = os.path.dirname(os.path.abspath(__file__))
GAMES_DIR = os.path.join(HERE, "games")
COVER_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif"}
_CACHE = {"key": None, "games": None, "page": None}
_LOCK = threading.Lock()


def version():
    try:
        with open(os.path.join(HERE, "VERSION"), encoding="utf-8") as f:
            return str(json.load(f).get("plugin version") or "")
    except (OSError, ValueError):
        return ""


def covers_dir():
    path = config.env("MINI_COVERS_DIR")
    if not path:
        return os.path.join(GAMES_DIR, "picture-territory", "covers")
    return os.path.abspath(path if os.path.isabs(path) else os.path.join(config.ROOT, path))


def list_covers():
    try:
        names = sorted(os.listdir(covers_dir()))
    except OSError:
        return []
    return [n for n in names if os.path.splitext(n)[1].lower() in COVER_EXTS and not n.startswith(".")]


def cover_path(name):
    """요청한 표지 파일의 실제 경로. 목록에 있는 이름만 (경로 이동 차단)."""
    return os.path.join(covers_dir(), name) if name in set(list_covers()) else None


def _signature():
    sig = []
    try:
        for item in sorted(os.listdir(GAMES_DIR)):
            folder = os.path.join(GAMES_DIR, item)
            for name in ("manifest.json", "template.html", "style.css", "game.js"):
                try:
                    sig.append((item, name, os.path.getmtime(os.path.join(folder, name))))
                except OSError:
                    pass
    except OSError:
        pass
    return tuple(sig)


def _read(path, default=""):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return default


def _label(name):
    """사이드바용 이름: 앞의 그림 문자(🕹️ 등)를 뗀다 (아이콘은 따로 있음)."""
    return re.sub(r"^[^\w가-힣(]+", "", name).strip() or name


def load_games():
    """[{id, name, label, icon, order, html, css, js}] - 파일이 바뀌었을 때만 다시 읽는다."""
    key = _signature()
    with _LOCK:
        if _CACHE["key"] == key and _CACHE["games"] is not None:
            return _CACHE["games"]
        games = []
        for item in sorted(os.listdir(GAMES_DIR)) if os.path.isdir(GAMES_DIR) else []:
            folder = os.path.join(GAMES_DIR, item)
            m_file, t_file, g_file = (os.path.join(folder, n) for n in ("manifest.json", "template.html", "game.js"))
            if not (os.path.isfile(m_file) and os.path.isfile(t_file) and os.path.isfile(g_file)):
                continue
            try:
                meta = json.loads(_read(m_file, "{}"))
            except ValueError as error:
                log.error("미니게임 manifest 읽기 실패 (%s): %s", item, error)
                continue
            js = _read(g_file)
            if item == "picture-territory":  # 플러그인 경로 대신 이 서버의 표지 경로
                js = js.replace("'/plugins/metadata/ym_mini_game/games/picture-territory/covers/'", "'games/covers/'")
            name = str(meta.get("name") or item)
            games.append({"id": str(meta.get("id") or item), "name": name, "label": _label(name),
                          "icon": str(meta.get("icon") or "fa-solid fa-gamepad"), "order": meta.get("order", 99),
                          "html": _read(t_file), "css": _read(os.path.join(folder, "style.css")), "js": js})
        games.sort(key=lambda g: (g["order"], g["id"]))
        _CACHE.update(key=key, games=games, page=None)
        return games


def menu():
    return [{"id": g["id"], "name": g["label"], "icon": g["icon"]} for g in load_games()]


BASE_CSS = """/* 미니게임 공통 (플러그인 공통 CSS, 색은 화면 틀의 테마 변수) */
.mini-app-container { display: flex; flex-direction: column; width: 100%; gap: 1.5rem; }
.mini-top-banner { display: flex; justify-content: space-between; align-items: center; width: 100%; padding: 1.25rem 1.5rem; background: var(--app-bg-card); border: 1px solid var(--app-border); border-radius: 12px; box-shadow: 0 4px 14px rgba(0, 0, 0, 0.08); flex-wrap: wrap; gap: 1rem; }
.banner-left { display: flex; align-items: center; gap: 1.2rem; }
.banner-icon-box { width: 52px; height: 52px; background: var(--accent); color: var(--accent-ink); border-radius: 12px; display: flex; justify-content: center; align-items: center; font-size: 1.6rem; box-shadow: 0 4px 10px rgba(0, 0, 0, 0.15); }
.banner-info { display: flex; flex-direction: column; gap: 0.25rem; }
.banner-title-row { display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap; }
.banner-title { margin: 0; font-size: 1.35rem; font-weight: 800; color: var(--app-text-primary); }
.banner-version { font-size: 0.85rem; font-weight: 600; color: var(--app-text-muted); }
.mini-badge { background: var(--app-border); color: var(--app-text-muted); font-size: 0.72rem; padding: 0.2rem 0.6rem; border-radius: 999px; font-weight: 700; text-transform: uppercase; }
.mini-badge.playing { background: var(--accent); color: var(--accent-ink); }
.mini-badge.paused { background: #f59e0b; color: #1c1300; }
.mini-badge.won { background: #10b981; color: #ffffff; }
.mini-badge.lost { background: #ef4444; color: #ffffff; }
.banner-desc { margin: 0; font-size: 0.88rem; color: var(--app-text-muted); }
.game-viewport { width: 100%; }
.mini-select-narrow { display: none; }  /* 넓은 화면은 사이드바 서브 메뉴로 고른다 */
.game-dropdown { background: var(--bg); color: var(--text); border: 1px solid var(--border); border-radius: var(--radius); padding: 0.5rem 0.7rem; font-weight: 600; }
@media (max-width: 900px) { .mini-select-narrow { display: block; } }
.btn-banner { padding: 0.6rem 1.1rem; border-radius: 8px; border: 1px solid transparent; font-size: 0.88rem; font-weight: 600; cursor: pointer; display: inline-flex; align-items: center; gap: 0.45rem; transition: all 0.2s ease; }
.btn-banner:disabled { opacity: 0.45; cursor: not-allowed; }
.btn-banner.primary { background: var(--accent); color: var(--accent-ink); }
.btn-banner.secondary { background: var(--app-bg-card-hover); border-color: var(--app-border); color: var(--app-text-primary); }
.btn-banner.secondary.active-flag { background: #ef4444; color: #ffffff; }
.btn-banner.danger { background: #ef4444; color: #ffffff; }
"""

HUB_JS = """
    const selectorEl = document.getElementById('game-selector');
    const viewportEl = document.getElementById('game-viewport');
    const bannerIcon = document.getElementById('banner-main-icon');
    const bannerName = document.getElementById('banner-game-name');
    const statusBadge = document.getElementById('app-status-badge');
    let activeInstance = null;

    function setStatusBadge(text, className) {
        if (statusBadge) {
            statusBadge.textContent = text;
            statusBadge.className = 'mini-badge ' + (className || '');
        }
    }

    function mount(gameId) {
        const game = GameData.find(g => g.id === gameId) || GameData[0];
        if (!game || window.YmMiniGameHub.current === game.id) return;
        if (activeInstance && activeInstance.destroy) {
            try { activeInstance.destroy(); } catch (e) { console.error(e); }
        }
        activeInstance = null;
        window.YmMiniGameHub.current = game.id;
        if (bannerIcon) bannerIcon.className = game.icon;
        if (bannerName) bannerName.textContent = game.name;
        if (selectorEl) selectorEl.value = game.id;
        setStatusBadge('READY', '');
        viewportEl.innerHTML = game.html;
        const handler = GameRegistry[game.id];
        if (typeof handler === 'function') {
            activeInstance = handler(viewportEl, { setStatusBadge });
            if (activeInstance && activeInstance.init) activeInstance.init();
        }
        document.dispatchEvent(new CustomEvent('mini:mounted', { detail: { id: game.id } }));
    }

    // 게임 선택은 주소의 #게임id (사이드바 서브 메뉴가 바꿈). 드롭다운은 좁은 화면용으로 남겨 둔다
    function fromHash() { mount(decodeURIComponent((location.hash || '').slice(1))); }
    if (selectorEl) {
        GameData.forEach(g => {
            const opt = document.createElement('option');
            opt.value = g.id;
            opt.textContent = g.name;
            selectorEl.appendChild(opt);
        });
        selectorEl.addEventListener('change', (e) => { location.hash = e.target.value; });
    }
    window.addEventListener('hashchange', fromHash);
    fromHash();
"""


def _script_safe(text):
    """<script> 안에 넣는 JSON: </script>로 끝나 버리지 않게."""
    return text.replace("</", "<\\/")


def _js_safe(text):
    """게임 스크립트 안의 '</script'가 <script> 태그를 닫아 버리지 않게."""
    return re.sub(r"</(script)", r"<\/\1", text, flags=re.I)


def page():
    games = load_games()
    with _LOCK:
        if _CACHE["page"] is not None and _CACHE["games"] is games:
            return _CACHE["page"]
    css = BASE_CSS + "".join(f"\n/* === [Game: {g['id']}] === */\n{g['css']}" for g in games)
    data = [{k: g[k] for k in ("id", "name", "icon", "order", "html")} for g in games]
    js = ("(function () {\n    const GameData = " + _script_safe(json.dumps(data, ensure_ascii=False)) + ";\n"
          "    const GameRegistry = {};\n"
          "    window.YmMiniGameHub = { current: '', register(gameId, meta, handler) { GameRegistry[gameId] = handler; } };\n"
          + "".join("\n// --- Game Script: %s ---\n%s\n" % (g["id"], _js_safe(g["js"])) for g in games)
          + HUB_JS + "})();\n")
    ver = html.escape(version())
    doc = f"""<!doctype html>
<html lang="ko" data-theme="dark" data-accent="amber">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#141517">
<title>미니게임</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/css/all.min.css" crossorigin="anonymous" referrerpolicy="no-referrer">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&display=swap">
<script>
  (function () {{ try {{ var t = JSON.parse(localStorage.getItem('bo_theme') || '{{}}') || {{}};
    var d = JSON.parse(localStorage.getItem('bo_theme_default') || '{{}}') || {{}};
    document.documentElement.setAttribute('data-theme', t.theme || d.theme || 'dark');
    document.documentElement.setAttribute('data-accent', t.accent || d.accent || 'amber'); }} catch (e) {{ }} }})();
</script>
<link rel="stylesheet" href="theme.css">
<style>
{_script_safe(css)}
</style>
</head>
<body data-module="mini">
<main class="gdw-page">
<div class="mini-app-container">
    <div class="mini-top-banner">
        <div class="banner-left">
            <div class="banner-icon-box"><i id="banner-main-icon" class="fa-solid fa-gamepad"></i></div>
            <div class="banner-info">
                <div class="banner-title-row">
                    <h2 class="banner-title" id="banner-game-name">미니게임 아케이드</h2>
                    <span class="banner-version">v{ver}</span>
                    <span id="app-status-badge" class="mini-badge">READY</span>
                </div>
                <p class="banner-desc">미니게임 아케이드 · 왼쪽 메뉴에서 게임을 고르세요.</p>
            </div>
        </div>
        <div class="banner-actions mini-select-narrow">
            <select id="game-selector" class="game-dropdown" aria-label="게임 선택"></select>
        </div>
    </div>
    <div id="game-viewport" class="game-viewport"></div>
</div>
</main>
<script>
{js}
</script>
<script src="shell.js"></script>
</body>
</html>
"""
    with _LOCK:
        _CACHE["page"] = doc
    return doc
