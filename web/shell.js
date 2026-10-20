/* web/shell.js - 두 화면 공용 화면 틀 (YMPlayer와 같은 구성)
 *
 *  ┌ 위쪽 바: 메뉴 버튼(좁은 화면) · 로고+이름+버전 배지 · 지금 위치(모듈 › 메뉴)
 *  ├ 사이드바: 모듈마다 접고 펴는 그룹(아코디언), 그 안에 각 화면의 탭이 서브 메뉴로 · 맨 아래 [테마]와 계정
 *  └ 본문: 남은 화면 전체
 * 화면 스크립트(script.js, webtoon/script.js)는 그대로 두고, 원래 탭 막대는 숨긴 채 메뉴가 그 탭 버튼을 눌러 준다.
 * 다른 모듈의 서브 메뉴는 그 화면으로 이동하며 주소의 #탭 이름으로 해당 탭을 연다.
 * 테마/강조색은 YMPlayer와 같은 값(<html data-theme data-accent>)이고 이 브라우저에 기억한다.
 */
(function () {
  'use strict';
  var ICONS = {
    'cloud-arrow-down': '<path d="M12 13v8"/><path d="m8 17 4 4 4-4"/><path d="M20.9 18.1A5 5 0 0 0 18 9h-1.3A8 8 0 1 0 3 16.3"/>',
    'list-check': '<path d="m3 17 2 2 4-4"/><path d="m3 7 2 2 4-4"/><path d="M13 6h8"/><path d="M13 12h8"/><path d="M13 18h8"/>',
    'sliders': '<path d="M21 4h-7"/><path d="M10 4H3"/><path d="M21 12h-9"/><path d="M8 12H3"/><path d="M21 20h-5"/><path d="M12 20H3"/><path d="M14 2v4"/><path d="M8 10v4"/><path d="M16 18v4"/>',
    'calendar-days': '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4"/><path d="M8 2v4"/><path d="M3 10h18"/>',
    'terminal': '<path d="m4 17 6-6-6-6"/><path d="M12 19h8"/>',
    'book-open-reader': '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>',
    'table-cells': '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/>',
    'bookmark': '<path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" fill="currentColor"/>',
    'bookmark-o': '<path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>',
    'ban': '<circle cx="12" cy="12" r="10"/><path d="m4.9 4.9 14.2 14.2"/>',
    'clone': '<rect x="8" y="8" width="14" height="14" rx="2"/><path d="M4 16a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2"/>',
    'download': '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
    'user-pen': '<circle cx="10" cy="7" r="4"/><path d="M4 21v-2a4 4 0 0 1 4-4h4"/><path d="M18.4 12.6a2 2 0 1 1 2.8 2.8L16 20.6l-3.6.9.9-3.6z"/>',
    'clock-rotate-left': '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/>',
    'gear': '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
    'circle-question': '<circle cx="12" cy="12" r="10"/><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3"/><path d="M12 17h.01"/>',
    'angles-left': '<path d="m11 17-5-5 5-5"/><path d="m18 17-5-5 5-5"/>',
    'bars': '<path d="M4 6h16"/><path d="M4 12h16"/><path d="M4 18h16"/>',
    'gamepad': '<path d="M6 11h4"/><path d="M8 9v4"/><path d="M15 12h.01"/><path d="M18 10h.01"/><path d="M17.3 5H6.7a4 4 0 0 0-3.98 3.59l-.6 5.98A3 3 0 0 0 5.1 18c1 0 1.96-.5 2.5-1.34L8.7 15h6.6l1.1 1.66A3 3 0 0 0 18.9 18a3 3 0 0 0 2.98-3.43l-.6-5.98A4 4 0 0 0 17.3 5z"/>',
    'xmark': '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    'check': '<path d="M20 6 9 17l-5-5"/>',
    'key': '<circle cx="7.5" cy="15.5" r="4.5"/><path d="m10.7 12.3 9.8-9.8"/><path d="m16 7 3 3"/><path d="m18 5 2 2"/>',
    'right-from-bracket': '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/>',
    'trash': '<path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>',
    'chevron-down': '<path d="m6 9 6 6 6-6"/>',
    'palette': '<circle cx="13.5" cy="6.5" r="1.2" fill="currentColor"/><circle cx="17.5" cy="10.5" r="1.2" fill="currentColor"/><circle cx="8.5" cy="7.5" r="1.2" fill="currentColor"/><circle cx="6.5" cy="12.5" r="1.2" fill="currentColor"/><path d="M12 2a10 10 0 0 0 0 20 2 2 0 0 0 2-2c0-.5-.2-1-.5-1.3-.3-.4-.5-.8-.5-1.3a2 2 0 0 1 2-2h2.4A5.6 5.6 0 0 0 22 9.8C22 5.5 17.5 2 12 2z"/>'
  };
  var MENU = [
    { id: 'gdw', title: '드라이브 변경 감시', icon: 'cloud-arrow-down', href: './', tabsSel: '.gdw-tabs',
      items: [
        { tab: 'events', label: '변경 기록', icon: 'list-check' },
        { tab: 'setup', label: '감시 설정', icon: 'sliders' },
        { tab: 'schedule', label: '스캔 일정', icon: 'calendar-days' },
        { tab: 'log', label: '로그', icon: 'terminal' }
      ] },
    { id: 'wtm', title: '웹툰 다운로더', icon: 'book-open-reader', href: 'webtoon', tabsSel: '.wtm-tabs',
      items: [
        { tab: 'all', label: '전체목록', icon: 'table-cells' },
        { tab: 'subscribed', label: '구독중', icon: 'bookmark' },
        { tab: 'unsubscribed', label: '구독해제', icon: 'bookmark-o' },
        { tab: 'excluded', label: '제외됨', icon: 'ban' },
        { tab: 'duplicate', label: '중복', icon: 'clone' },
        { tab: 'manual', label: '선택 회차 다운로드', icon: 'download' },
        { tab: 'authors', label: '작가·태그 관리', icon: 'user-pen' },
        { tab: 'history', label: '다운로드 이력', icon: 'clock-rotate-left' },
        { tab: 'settings', label: '설정', icon: 'gear' },
        { tab: 'help', label: '도움말', icon: 'circle-question' }
      ] },
    // 미니게임: 게임 목록은 서버(/api/modules의 games)에서 받아 채운다. 탭 막대 대신 주소의 #게임id로 고른다
    { id: 'mini', title: '미니게임', icon: 'gamepad', href: 'games', hashNav: true, items: [] }
  ];
  var THEMES = [
    { id: 'dark', label: '다크', colors: ['#141517', '#1d1f22', '#ececec'] },
    { id: 'light', label: '라이트', colors: ['#f3f4f6', '#ffffff', '#1c1e22'] },
    { id: 'black', label: '블랙 (OLED)', colors: ['#000000', '#0d0e10', '#ececec'] },
    { id: 'navy', label: '네이비', colors: ['#0f1623', '#172030', '#e6ebf3'] },
    { id: 'auto', label: '시스템 따라', colors: ['#141517', '#f3f4f6', '#888888'] }
  ];
  var ACCENTS = [
    { id: 'amber', label: '주황 (기본)', color: '#e5a00d' }, { id: 'blue', label: '파랑', color: '#3b82f6' },
    { id: 'green', label: '초록', color: '#22c55e' }, { id: 'purple', label: '보라', color: '#a855f7' },
    { id: 'red', label: '빨강', color: '#ef4444' }, { id: 'pink', label: '분홍', color: '#ec4899' },
    { id: 'teal', label: '청록', color: '#14b8a6' }
  ];
  var THEME_KEY = 'bo_theme', OPEN_KEY = 'bo_nav_open';
  var root = document.documentElement;
  var current = document.body.getAttribute('data-module');
  var mod = MENU.filter(function (m) { return m.id === current; })[0];

  function storeGet(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }
  function storeSet(key, value) { try { localStorage.setItem(key, value); } catch (e) { /* 저장소를 못 쓰는 브라우저 */ } }
  function h(tag, attrs, children) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === 'text') n.textContent = attrs[k];
      else if (k === 'class') n.className = attrs[k];
      else if (k.slice(0, 2) === 'on') n.addEventListener(k.slice(2), attrs[k]);
      else n.setAttribute(k, attrs[k]);
    });
    (children || []).forEach(function (c) { if (c) n.appendChild(c); });
    return n;
  }
  function icon(name, cls) {
    var span = document.createElement('span');
    span.className = cls || 'app-icon';
    span.setAttribute('aria-hidden', 'true');
    span.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" ' +
      'stroke-linejoin="round">' + (ICONS[name] || '') + '</svg>';  // ICONS는 위의 고정 문자열
    return span;
  }

  // ── 테마 (YMPlayer theme.js와 같은 구조) ──
  // 기본 테마는 서버(설정 > 화면, ui_prefs.json)에 두고 모든 브라우저가 따른다. 이 브라우저에서 따로 고른 테마(bo_theme)가 있으면 그게 우선.
  // 다음에 열 때 깜빡이지 않게 서버 기본값도 브라우저(bo_theme_default)에 적어 두고, 각 화면 머리의 짧은 스크립트가 먼저 읽는다.
  var DEFAULT_KEY = 'bo_theme_default';
  function readJSON(key) { try { return JSON.parse(storeGet(key) || 'null') || {}; } catch (e) { return {}; } }
  var defaults = { theme: readJSON(DEFAULT_KEY).theme || 'dark', accent: readJSON(DEFAULT_KEY).accent || 'amber' };
  var mine = { theme: readJSON(THEME_KEY).theme || '', accent: readJSON(THEME_KEY).accent || '' };
  function applyTheme() {
    root.setAttribute('data-theme', mine.theme || defaults.theme);
    root.setAttribute('data-accent', mine.accent || defaults.accent);
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = getComputedStyle(root).getPropertyValue('--bg').trim() || '#141517';
    setFavicon();
  }
  function saveMine() {
    storeSet(THEME_KEY, JSON.stringify(mine.theme || mine.accent ? mine : {}));
    applyTheme();
  }
  function setDefaults(d) {
    if (d && d.theme) defaults.theme = d.theme;
    if (d && d.accent) defaults.accent = d.accent;
    storeSet(DEFAULT_KEY, JSON.stringify(defaults));
    applyTheme();
  }

  // ── 로고 / 파비콘: YMPlayer 아이콘에서 재생(▷) 대신 'P' ──
  var LOGO_INNER = '<rect class="logo-bg" width="64" height="64" rx="15"/>' +
    '<circle class="logo-ink" cx="27" cy="33" r="19"/><circle class="logo-bg" cx="37" cy="26" r="15.5"/>' +
    '<text class="logo-ink logo-p" x="37.6" y="27" text-anchor="middle" dominant-baseline="central">P</text>';
  var ACCENT_HEX = { amber: ['#e5a00d', '#141517'], blue: ['#3b82f6', '#ffffff'], green: ['#22c55e', '#06200f'],
    purple: ['#a855f7', '#ffffff'], red: ['#ef4444', '#ffffff'], pink: ['#ec4899', '#ffffff'], teal: ['#14b8a6', '#032420'] };
  function setFavicon() {  // 브라우저 탭 아이콘도 지금 강조색으로
    var c = ACCENT_HEX[mine.accent || defaults.accent] || ACCENT_HEX.amber;
    var svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="15" fill="' + c[0] + '"/>' +
      '<circle cx="27" cy="33" r="19" fill="' + c[1] + '"/><circle cx="37" cy="26" r="15.5" fill="' + c[0] + '"/>' +
      '<text x="37.6" y="27" text-anchor="middle" dominant-baseline="central" font-family="Arial,Helvetica,sans-serif" ' +
      'font-weight="900" font-size="22" fill="' + c[1] + '">P</text></svg>';
    var link = document.querySelector('link[rel="icon"]');
    if (!link) { link = document.createElement('link'); link.rel = 'icon'; document.head.appendChild(link); }
    link.type = 'image/svg+xml';
    link.href = 'data:image/svg+xml,' + encodeURIComponent(svg);
  }
  applyTheme();

  // 로그인 화면: 테마·파비콘·로고만 쓰고 화면 틀(메뉴)은 만들지 않는다
  if (document.body.classList.contains('login-body')) {
    var loginMark = document.querySelector('.login-brand .brand-mark');
    if (loginMark) loginMark.innerHTML = '<svg class="logo" viewBox="0 0 64 64" aria-hidden="true">' + LOGO_INNER + '</svg>';
    window.GdwShell = { setDefaults: setDefaults };
    return;
  }

  // 로그인이 풀리면(만료, 비밀번호 변경, 계정 삭제) API가 401을 주므로 로그인 화면으로. 로그인 뒤 지금 화면으로 돌아온다
  if (window.fetch) {
    var rawFetch = window.fetch.bind(window);
    window.fetch = function () {
      return rawFetch.apply(null, arguments).then(function (res) {
        if (res.status === 401) {
          var page = location.pathname.split('/').filter(Boolean)[0] || '';
          location.href = 'login#' + encodeURIComponent(page + location.hash);
        }
        return res;
      });
    };
  }
  function api(path, body) {  // 설정 창의 계정 요청: 실패면 서버의 오류 문구로 reject
    return fetch(path, body === undefined ? { credentials: 'same-origin' } : { method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (d) {
          if (!r.ok || d.success === false) throw new Error(d.error || 'HTTP ' + r.status);
          return d;
        });
      });
  }
  function toast(msg, kind) {
    var t = h('div', { class: 'shell-toast' + (kind ? ' ' + kind : ''), role: 'status', text: msg });
    document.body.appendChild(t);
    setTimeout(function () { t.remove(); }, 3000);
  }

  // ── 창 (YMPlayer util.js modal과 같은 모양) ──
  function modal(title, body, actions) {
    var wrap;
    function close() { if (wrap) wrap.remove(); document.removeEventListener('keydown', onKey); }
    function onKey(ev) { if (ev.key === 'Escape') close(); }
    wrap = h('div', { class: 'modal', onclick: function (e) { if (e.target === wrap) close(); } }, [
      h('div', { class: 'modal-card', role: 'dialog', 'aria-label': title }, [
        h('div', { class: 'modal-head' }, [h('h3', { text: title }),
          h('button', { type: 'button', class: 'icon-btn', title: '닫기', 'aria-label': '닫기', onclick: function () { close(); } }, [icon('xmark')])]),
        h('div', { class: 'modal-body' }, [body]),
        actions && actions.length ? h('div', { class: 'modal-foot' }, actions) : null])]);
    document.body.appendChild(wrap);
    document.addEventListener('keydown', onKey);
    return { el: wrap, close: close };
  }
  function swatch(t) {
    var sw = h('div', { class: 'sw' });
    t.colors.forEach(function (c) { var i = document.createElement('i'); i.style.background = c; sw.appendChild(i); });
    return sw;
  }
  /** 테마 고르기 (YMPlayer themePicker). admin이면 서버 기본값을 고른다. */
  function themePicker(admin) {
    var cur = admin ? { theme: defaults.theme, accent: defaults.accent } : { theme: mine.theme, accent: mine.accent };
    var box = h('div', { class: 'theme-pick' });
    function pick(key, id) {
      cur[key] = id;
      if (admin) {
        fetch('api/ui-prefs', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(cur) }).then(function (r) { return r.json(); }).then(function (d) { if (d.ui) setDefaults(d.ui); draw(); });
      } else { mine = { theme: cur.theme, accent: cur.accent }; saveMine(); }
      draw();
    }
    function draw() {
      var shownTheme = cur.theme || defaults.theme, shownAccent = cur.accent || defaults.accent;
      while (box.firstChild) box.removeChild(box.firstChild);
      var grid = h('div', { class: 'theme-grid' });
      THEMES.forEach(function (t) {
        grid.appendChild(h('button', { type: 'button', class: 'theme-opt' + (shownTheme === t.id ? ' on' : ''),
          onclick: function () { pick('theme', t.id); } }, [swatch(t), h('span', { text: t.label })]));
      });
      var row = h('div', { class: 'accent-row' });
      ACCENTS.forEach(function (a) {
        var b = h('button', { type: 'button', class: 'accent-opt' + (shownAccent === a.id ? ' on' : ''), title: a.label, 'aria-label': a.label,
          onclick: function () { pick('accent', a.id); } }, [shownAccent === a.id ? icon('check') : null]);
        b.style.background = a.color;
        row.appendChild(b);
      });
      box.appendChild(h('div', {}, [h('h4', { text: admin ? '기본 테마 (모든 브라우저)' : '테마' }), grid]));
      box.appendChild(h('div', {}, [h('h4', { text: '강조색' }), row]));
      if (!admin) {
        var cb = h('input', { type: 'checkbox' });
        cb.checked = !cur.theme && !cur.accent;
        cb.addEventListener('change', function () {
          if (cb.checked) { cur.theme = ''; cur.accent = ''; mine = { theme: '', accent: '' }; saveMine(); draw(); }
        });
        box.appendChild(h('label', { class: 'theme-default' }, [cb, document.createTextNode('설정의 기본 테마 쓰기')]));
      }
    }
    draw();
    return box;
  }
  function openThemeDialog() {
    var m = modal('테마', themePicker(false), [h('button', { type: 'button', class: 'btn btn-accent', text: '닫기', onclick: function () { m.close(); } })]);
  }
  /** 설정 (YMPlayer 설정의 탭 구성 중 이 프로그램에 맞는 것: 화면 / 정보) */
  function openSettings() {
    var body = h('div', { class: 'settings-dialog' });
    var tabs = h('div', { class: 'tabs' });
    var pane = h('div', { class: 'settings-pane' });
    var pages = {
      '화면': function () {
        return h('div', {}, [h('p', { class: 'muted', text: '모든 브라우저의 기본 테마입니다. 브라우저마다 따로 고르려면 왼쪽 아래 계정 옆의 팔레트 버튼을 쓰세요.' }),
          themePicker(true)]);
      },
      '사용자': usersPane,
      '정보': function () {
        var list = h('div', { class: 'about-list' });
        var names = { gdw: '드라이브 변경 감시', wtm: '웹툰 다운로더', mini: '미니게임' };
        Object.keys(names).forEach(function (k) {
          list.appendChild(h('div', { class: 'about-row' }, [h('span', { text: names[k] }),
            h('b', { text: (info.versions && info.versions[k] ? 'v' + info.versions[k] : '-') + (info[k] === false ? ' (꺼짐)' : '') })]));
        });
        list.appendChild(h('div', { class: 'about-row' }, [h('span', { text: '프로그램' }), h('b', { text: info.version ? 'v' + info.version : '-' })]));
        return h('div', {}, [list, h('p', { class: 'muted', text: '모듈 켜기/끄기와 경로·토큰 같은 실행 환경은 .env에서 바꿉니다 (GDW_ENABLED / WTM_ENABLED / MINI_ENABLED).' })]);
      }
    };
    function show(name) {
      tabs.querySelectorAll('.tab').forEach(function (t) { t.classList.toggle('active', t.textContent === name); });
      while (pane.firstChild) pane.removeChild(pane.firstChild);
      pane.appendChild(pages[name]());
    }
    Object.keys(pages).forEach(function (name) {
      tabs.appendChild(h('button', { type: 'button', class: 'tab', text: name, onclick: function () { show(name); } }));
    });
    body.appendChild(tabs);
    body.appendChild(pane);
    var m = modal('설정', body, [h('button', { type: 'button', class: 'btn btn-accent', text: '닫기', onclick: function () { m.close(); } })]);
    show('화면');
  }
  var info = {};

  /** 설정 > 사용자 (YMPlayer 사용자 관리). 이 화면은 관리용이라 모든 사용자가 관리자다. */
  function usersPane() {
    var box = h('div', { class: 'users-box' });
    function load() {
      while (box.firstChild) box.removeChild(box.firstChild);
      box.appendChild(h('p', { class: 'muted', text: '로그인할 수 있는 사람 (모두 관리자). 비밀번호를 바꾸면 그 사람의 다른 기기 로그인은 끊깁니다.' }));
      var list = h('div', { class: 'about-list' });
      box.appendChild(list);
      api('api/users').then(function (d) {
        d.users.forEach(function (u) {
          var me = u.username === info.user;
          var pw = h('button', { type: 'button', class: 'icon-btn', title: '비밀번호 바꾸기', 'aria-label': '비밀번호 바꾸기', onclick: function () {
            if (me) { changePassword(); return; }
            var v = window.prompt(u.username + '의 새 비밀번호 (6자 이상)');
            if (!v) return;
            api('api/users/password', { username: u.username, password: v })
              .then(function () { toast('비밀번호를 바꿨습니다.', 'success'); }, function (e) { toast(e.message, 'error'); });
          } }, [icon('key')]);
          var del = me ? null : h('button', { type: 'button', class: 'icon-btn', title: '지우기', 'aria-label': '지우기', onclick: function () {
            if (!window.confirm(u.username + ' 사용자를 지울까요?')) return;
            api('api/users/delete', { username: u.username }).then(load, function (e) { toast(e.message, 'error'); });
          } }, [icon('trash')]);
          list.appendChild(h('div', { class: 'about-row' }, [h('span', { text: u.username + (me ? ' (나)' : '') }),
            h('span', { class: 'row-actions' }, [pw, del])]));
        });
      }, function (e) { box.appendChild(h('p', { class: 'muted', text: e.message })); });
      var name = h('input', { class: 'input', type: 'text', placeholder: '아이디', autocomplete: 'off' });
      var pass = h('input', { class: 'input', type: 'password', placeholder: '비밀번호 (6자 이상)', autocomplete: 'new-password' });
      var add = h('button', { type: 'button', class: 'btn btn-accent', text: '추가', onclick: function () {
        api('api/users', { username: name.value.trim(), password: pass.value })
          .then(function () { toast('추가했습니다.', 'success'); load(); }, function (e) { toast(e.message, 'error'); });
      } });
      box.appendChild(h('h4', { text: '사용자 추가' }));
      box.appendChild(h('div', { class: 'user-add' }, [name, pass, add]));
    }
    load();
    return box;
  }
  /** 내 비밀번호 바꾸기 (YMPlayer와 같음): 바꾸면 다른 기기의 로그인은 끊기고 이 기기는 새 쿠키 */
  function changePassword() {
    var cur = h('input', { class: 'input', type: 'password', placeholder: '지금 비밀번호', autocomplete: 'current-password' });
    var next = h('input', { class: 'input', type: 'password', placeholder: '새 비밀번호 (6자 이상)', autocomplete: 'new-password' });
    var again = h('input', { class: 'input', type: 'password', placeholder: '새 비밀번호 확인', autocomplete: 'new-password' });
    var save = h('button', { type: 'button', class: 'btn btn-accent', text: '바꾸기' });
    var m = modal('비밀번호 변경', h('div', { class: 'pw-fields' }, [cur, next, again,
      h('span', { class: 'muted', text: '바꾸면 다른 기기의 로그인은 끊깁니다.' })]), [save]);
    save.addEventListener('click', function () {
      if (next.value !== again.value) { toast('새 비밀번호 확인이 다릅니다.', 'error'); return; }
      save.disabled = true;
      api('api/auth/password', { current: cur.value, 'new': next.value })
        .then(function () { m.close(); toast('비밀번호를 바꿨습니다.', 'success'); }, function (e) { toast(e.message, 'error'); })
        .then(function () { save.disabled = false; });
    });
    cur.focus();
  }
  function logout() {
    api('api/auth/logout', {}).catch(function () { /* 이미 풀렸어도 로그인 화면으로 */ })
      .then(function () { location.href = 'login'; });
  }

  // ── 원래 탭 막대와 연결 ──
  function tabBar() { return mod && mod.tabsSel ? document.querySelector(mod.tabsSel) : null; }
  function tabButton(tab) { var bar = tabBar(); return bar ? bar.querySelector('[data-tab="' + tab + '"]') : null; }
  function activeTab() {
    if (mod && mod.hashNav) {  // 미니게임: 화면이 지금 띄운 게임
      var hub = window.YmMiniGameHub;
      return (hub && hub.current) || decodeURIComponent((location.hash || '').slice(1));
    }
    var bar = tabBar(), on = bar && bar.querySelector('.is-on, .active');
    return on ? on.getAttribute('data-tab') : '';
  }
  function openTab(tab, push) {
    if (mod && mod.hashNav) {  // 화면이 #게임id 변화를 보고 게임을 바꾼다
      if (location.hash !== '#' + tab) location.hash = tab;
      document.body.classList.remove('nav-open');
      return true;
    }
    var btn = tabButton(tab);
    if (!btn) return false;
    btn.click();
    if (push !== false) { try { history.replaceState(null, '', '#' + tab); } catch (e) { /* 무시 */ } }
    document.body.classList.remove('nav-open');
    window.scrollTo(0, 0);
    return true;
  }

  // ── 위쪽 바 ──
  var verEl = h('span', { class: 'brand-ver' });
  var mark = h('span', { class: 'brand-mark' });
  mark.innerHTML = '<svg class="logo" viewBox="0 0 64 64" aria-hidden="true">' + LOGO_INNER + '</svg>';
  mark.appendChild(verEl);
  var crumbTab = h('b', { text: '' });
  var top = h('header', { class: 'topbar' }, [
    h('button', { type: 'button', class: 'icon-btn menu-btn', title: '메뉴', 'aria-label': '메뉴',
      onclick: function () { document.body.classList.toggle('nav-open'); } }, [icon('bars')]),
    h('a', { class: 'brand', href: './' }, [mark, h('span', { class: 'brand-name', text: 'BookOasis 보조' })]),
    h('div', { class: 'crumbs' }, [h('span', { text: mod ? mod.title : '' }), h('span', { class: 'sep', text: '›' }), crumbTab])
  ]);

  // ── 사이드바 ──
  var nav = h('nav', { id: 'nav', class: 'sidebar', 'aria-label': '메뉴' });
  var groups = [];
  function openGroup(id) {
    groups.forEach(function (g) {
      var open = g.getAttribute('data-module') === id;
      g.classList.toggle('collapsed', !open);
      g.querySelector('.nav-head').setAttribute('aria-expanded', String(open));
    });
    storeSet(OPEN_KEY, id || '');
  }
  function faIcon(cls) {  // 게임 manifest의 Font Awesome 아이콘
    var span = h('span', { class: 'app-icon', 'aria-hidden': 'true' });
    span.appendChild(h('i', { class: cls }));
    return span;
  }
  function addItem(m, it) {
    var link = h('a', { class: 'nav-link', href: m.href + '#' + it.tab, 'data-tab': it.tab, 'data-module': m.id },
      [it.fa ? faIcon(it.fa) : icon(it.icon), h('span', { text: it.label })]);
    if (m.id === current) {
      link.addEventListener('click', function (ev) {
        if (ev.button !== 0 || ev.metaKey || ev.ctrlKey || ev.shiftKey) return;  // 새 탭으로 열기는 그대로
        if (openTab(it.tab)) ev.preventDefault();
      });
    }
    m.itemsEl.appendChild(link);
  }
  MENU.forEach(function (m) {
    var group = h('div', { class: 'nav-group', 'data-module': m.id });
    var head = h('button', { type: 'button', class: 'nav-head nav-toggle', title: m.title + ' 메뉴 펼치기/접기',
      onclick: function () { openGroup(group.classList.contains('collapsed') ? m.id : null); } },
      [h('span', { text: m.title }), icon('chevron-down', 'nav-chevron')]);
    var items = h('div', { class: 'nav-items' });
    m.itemsEl = items;
    m.items.forEach(function (it) { addItem(m, it); });
    group.appendChild(head);
    group.appendChild(items);
    groups.push(group);
    nav.appendChild(group);
  });
  // 처음에는 지금 화면의 모듈을 펼친다
  openGroup(current || storeGet(OPEN_KEY));

  // 아래 (YMPlayer와 같은 구성): 설정, 그리고 계정 줄 (테마 버튼)
  var who = h('div', { class: 'who' }, [h('b', { text: '' }), h('span', { text: '' })]);
  var avatar = h('span', { class: 'avatar', text: 'A' });
  nav.appendChild(h('div', { class: 'nav-footer' }, [
    h('a', { class: 'nav-link', href: '#', onclick: function (ev) { ev.preventDefault(); openSettings(); } },
      [icon('gear'), h('span', { text: '설정' })]),
    h('div', { class: 'nav-account' }, [avatar, who,
      h('button', { type: 'button', class: 'icon-btn', title: '테마', 'aria-label': '테마', onclick: openThemeDialog }, [icon('palette')]),
      h('button', { type: 'button', class: 'icon-btn', title: '비밀번호 변경', 'aria-label': '비밀번호 변경', onclick: changePassword }, [icon('key')]),
      h('button', { type: 'button', class: 'icon-btn', title: '로그아웃', 'aria-label': '로그아웃', onclick: logout }, [icon('right-from-bracket')])])
  ]));

  var scrim = h('div', { class: 'nav-scrim', onclick: function () { document.body.classList.remove('nav-open'); } });

  // 본문을 .main으로 감싼다
  var main = h('main', { id: 'main', class: 'main' });
  while (document.body.firstChild) main.appendChild(document.body.firstChild);
  document.body.appendChild(top);
  document.body.appendChild(nav);
  document.body.appendChild(scrim);
  document.body.appendChild(main);

  // ── 선택 표시: 탭이 바뀌면(화면 안의 다른 버튼으로 바뀐 경우 포함) 메뉴와 위쪽 위치도 따라간다 ──
  function syncActive() {
    var tab = activeTab();
    nav.querySelectorAll('.nav-link[data-module="' + current + '"]').forEach(function (a) {
      var on = a.getAttribute('data-tab') === tab;
      a.classList.toggle('active', on);
      if (on) { a.setAttribute('aria-current', 'page'); crumbTab.textContent = a.textContent; } else a.removeAttribute('aria-current');
    });
  }
  var bar = tabBar();
  if (bar && window.MutationObserver) {
    new MutationObserver(syncActive).observe(bar, { subtree: true, attributes: true, attributeFilter: ['class'] });
  }
  function fromHash() {
    var tab = decodeURIComponent((location.hash || '').slice(1));
    if (tab && tabButton(tab)) openTab(tab, false);
    syncActive();
  }
  window.addEventListener('hashchange', fromHash);
  document.addEventListener('mini:mounted', syncActive);  // 미니게임 화면이 게임을 바꿨을 때
  fromHash();

  // 켜진 모듈·버전·로그인 이름 (서버의 /api/modules)
  fetch('api/modules', { credentials: 'same-origin' }).then(function (r) { return r.json(); }).then(function (m) {
    groups.forEach(function (g) { g.hidden = !m[g.getAttribute('data-module')]; });
    var miniMenu = MENU.filter(function (x) { return x.id === 'mini'; })[0];
    (m.games || []).forEach(function (g) {
      var it = { tab: g.id, label: g.name, fa: g.icon };
      miniMenu.items.push(it);
      addItem(miniMenu, it);
    });
    syncActive();
    info = m;
    if (m.ui) setDefaults(m.ui);
    // 아이콘 배지: 지금 보는 화면의 모듈 버전 (드라이브 변경 감시 / 웹툰 다운로더 / 미니게임마다 다름)
    var ver = (m.versions && current && m.versions[current]) || m.version;
    if (ver) { verEl.textContent = ver; document.title = document.title + ' · v' + ver; }
    var name = m.user || '?';
    who.firstChild.textContent = name;
    who.lastChild.textContent = '관리자';
    avatar.textContent = name.slice(0, 1).toUpperCase();
  }).catch(function () {});
})();
