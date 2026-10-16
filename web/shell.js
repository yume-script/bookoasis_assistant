/* web/shell.js - 두 화면 공용 좌측 메뉴 (Plex 스타일)
 *
 * 모듈(드라이브 변경 감시 / 웹툰 다운로더)을 1단 메뉴로, 각 화면의 탭을 2단(서브) 메뉴로 보여 준다.
 * 화면 스크립트(script.js, webtoon/script.js)는 그대로 두고, 원래 탭 막대는 숨긴 채 메뉴가 그 탭 버튼을 눌러 준다.
 * 다른 모듈의 서브 메뉴를 누르면 그 화면으로 이동하고 주소의 #탭 이름으로 해당 탭을 연다.
 */
(function () {
  'use strict';
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
        { tab: 'unsubscribed', label: '구독해제', icon: 'bookmark' },
        { tab: 'excluded', label: '제외됨', icon: 'ban' },
        { tab: 'duplicate', label: '중복', icon: 'clone' },
        { tab: 'manual', label: '선택 회차 다운로드', icon: 'download' },
        { tab: 'authors', label: '작가·태그 관리', icon: 'user-pen' },
        { tab: 'history', label: '다운로드 이력', icon: 'clock-rotate-left' },
        { tab: 'settings', label: '설정', icon: 'gear' },
        { tab: 'help', label: '도움말', icon: 'circle-question' }
      ] }
  ];
  // 메뉴 아이콘: 인라인 SVG (외부 아이콘 CDN이 막혀도 메뉴가 보이도록)
  var ICONS = {
    'cloud-arrow-down': '<path d="M12 13v8"/><path d="m8 17 4 4 4-4"/><path d="M20.9 18.1A5 5 0 0 0 18 9h-1.3A8 8 0 1 0 3 16.3"/>',
    'list-check': '<path d="m3 17 2 2 4-4"/><path d="m3 7 2 2 4-4"/><path d="M13 6h8"/><path d="M13 12h8"/><path d="M13 18h8"/>',
    'sliders': '<path d="M21 4h-7"/><path d="M10 4H3"/><path d="M21 12h-9"/><path d="M8 12H3"/><path d="M21 20h-5"/><path d="M12 20H3"/><path d="M14 2v4"/><path d="M8 10v4"/><path d="M16 18v4"/>',
    'calendar-days': '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4"/><path d="M8 2v4"/><path d="M3 10h18"/>',
    'terminal': '<path d="m4 17 6-6-6-6"/><path d="M12 19h8"/>',
    'book-open-reader': '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>',
    'table-cells': '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/>',
    'bookmark': '<path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" fill="currentColor"/>',
    'bookmark': '<path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>',
    'ban': '<circle cx="12" cy="12" r="10"/><path d="m4.9 4.9 14.2 14.2"/>',
    'clone': '<rect x="8" y="8" width="14" height="14" rx="2"/><path d="M4 16a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2"/>',
    'download': '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
    'user-pen': '<circle cx="10" cy="7" r="4"/><path d="M4 21v-2a4 4 0 0 1 4-4h4"/><path d="M18.4 12.6a2 2 0 1 1 2.8 2.8L16 20.6l-3.6.9.9-3.6z"/>',
    'clock-rotate-left': '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/>',
    'gear': '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
    'circle-question': '<circle cx="12" cy="12" r="10"/><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3"/><path d="M12 17h.01"/>',
    'angles-left': '<path d="m11 17-5-5 5-5"/><path d="m18 17-5-5 5-5"/>',
    'bars': '<path d="M4 6h16"/><path d="M4 12h16"/><path d="M4 18h16"/>'
  };
  var current = document.body.getAttribute('data-module');
  var mod = MENU.filter(function (m) { return m.id === current; })[0];

  function store(key, value) {
    try { if (value === undefined) return localStorage.getItem(key); localStorage.setItem(key, value); } catch (e) { return null; }
    return null;
  }
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
  function icon(name) {
    var span = document.createElement('span');
    span.className = 'app-side-ico';
    span.setAttribute('aria-hidden', 'true');
    span.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" ' +
      'stroke-linejoin="round">' + (ICONS[name] || '') + '</svg>';  // ICONS는 위의 고정 문자열
    return span;
  }

  // ── 원래 탭 막대와 연결 ──
  function tabButton(tab) {
    var bar = mod && document.querySelector(mod.tabsSel);
    return bar ? bar.querySelector('[data-tab="' + tab + '"]') : null;
  }
  function activeTab() {
    var bar = mod && document.querySelector(mod.tabsSel);
    if (!bar) return '';
    var on = bar.querySelector('.is-on, .active');
    return on ? on.getAttribute('data-tab') : '';
  }
  function openTab(tab, push) {
    var btn = tabButton(tab);
    if (!btn) return false;
    btn.click();
    if (push !== false) {
      try { history.replaceState(null, '', '#' + tab); } catch (e) { /* 무시 */ }
    }
    closeDrawer();
    window.scrollTo(0, 0);
    return true;
  }

  // ── 메뉴 그리기 ──
  var side = h('aside', { class: 'app-side', 'aria-label': '메뉴' });
  var head = h('div', { class: 'app-side-head' }, [
    h('a', { class: 'app-side-brand', href: './', title: 'BookOasis 보조 프로그램' }, [
      h('span', { class: 'app-side-logo', 'aria-hidden': 'true', text: 'B' }),
      h('span', { class: 'app-side-brand-text', text: 'BookOasis 보조' })
    ]),
    h('button', { type: 'button', class: 'app-side-collapse', title: '메뉴 접기/펼치기', 'aria-label': '메뉴 접기/펼치기',
      onclick: function () { setCollapsed(!document.body.classList.contains('app-side-collapsed')); } },
      [icon('angles-left')])
  ]);
  side.appendChild(head);
  var nav = h('nav', { class: 'app-side-nav' });
  MENU.forEach(function (m) {
    var group = h('div', { class: 'app-side-group' + (m.id === current ? ' is-current' : ''), 'data-module': m.id });
    group.appendChild(h('a', { class: 'app-side-mod', href: m.href, title: m.title }, [
      icon(m.icon), h('span', { class: 'app-side-label', text: m.title })
    ]));
    var list = h('ul', { class: 'app-side-sub' });
    m.items.forEach(function (it) {
      var link = h('a', { class: 'app-side-item', href: m.href + '#' + it.tab, 'data-tab': it.tab, title: it.label }, [
        icon(it.icon), h('span', { class: 'app-side-label', text: it.label })
      ]);
      if (m.id === current) {
        link.addEventListener('click', function (ev) {
          if (ev.button !== 0 || ev.metaKey || ev.ctrlKey || ev.shiftKey) return;  // 새 탭으로 열기는 그대로
          if (openTab(it.tab)) ev.preventDefault();
        });
      }
      list.appendChild(h('li', {}, [link]));
    });
    group.appendChild(list);
    nav.appendChild(group);
  });
  side.appendChild(nav);
  side.appendChild(h('div', { class: 'app-side-foot' }, [
    h('span', { class: 'app-side-label', text: 'gdrive_watch_sa' })
  ]));

  var top = h('header', { class: 'app-topbar' }, [
    h('button', { type: 'button', class: 'app-topbar-menu', 'aria-label': '메뉴 열기',
      onclick: function () { document.body.classList.toggle('app-drawer-open'); } }, [icon('bars')]),
    h('span', { class: 'app-topbar-title', text: mod ? mod.title : '' })
  ]);
  var scrim = h('div', { class: 'app-scrim', onclick: closeDrawer });

  function closeDrawer() { document.body.classList.remove('app-drawer-open'); }
  function setCollapsed(on) {
    document.body.classList.toggle('app-side-collapsed', on);
    store('app-side-collapsed', on ? '1' : '0');
  }

  // 본문을 .app-main으로 감싼다
  var main = h('div', { class: 'app-main' });
  while (document.body.firstChild) {
    var node = document.body.firstChild;
    if (node.tagName === 'SCRIPT') { document.body.removeChild(node); main.appendChild(node); continue; }
    main.appendChild(node);
  }
  document.body.appendChild(side);
  document.body.appendChild(scrim);
  document.body.appendChild(top);
  document.body.appendChild(main);
  if (store('app-side-collapsed') === '1') document.body.classList.add('app-side-collapsed');

  // ── 선택 표시: 탭이 바뀌면(화면 안의 다른 버튼으로 바뀐 경우 포함) 메뉴도 따라간다 ──
  function syncActive() {
    var tab = activeTab();
    side.querySelectorAll('.app-side-group.is-current .app-side-item').forEach(function (a) {
      var on = a.getAttribute('data-tab') === tab;
      a.classList.toggle('is-active', on);
      if (on) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });
  }
  var bar = mod && document.querySelector(mod.tabsSel);
  if (bar && window.MutationObserver) {
    new MutationObserver(syncActive).observe(bar, { subtree: true, attributes: true, attributeFilter: ['class'] });
  }

  // 주소의 #탭 이름으로 시작 탭 열기 (다른 모듈 메뉴에서 넘어온 경우)
  function fromHash() {
    var tab = decodeURIComponent((location.hash || '').slice(1));
    if (tab && tabButton(tab)) openTab(tab, false);
    syncActive();
  }
  window.addEventListener('hashchange', fromHash);
  fromHash();

  // 꺼 둔 모듈(.env의 GDW_ENABLED / WTM_ENABLED)은 메뉴에서 숨긴다
  fetch('api/modules', { credentials: 'same-origin' }).then(function (r) { return r.json(); }).then(function (m) {
    side.querySelectorAll('.app-side-group').forEach(function (g) { g.hidden = !m[g.getAttribute('data-module')]; });
  }).catch(function () {});
})();
