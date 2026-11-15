// 브런치 EPUB 받기 화면 (서버: brunch/service.py)
(function () {
    'use strict';
    const root = document.getElementById('brunch-app');

    // ── 작은 도구 (텔레그램 자동 올리기 화면과 같음) ──
    function h(tag, attrs, ...children) {
        const el = document.createElement(tag);
        for (const [k, v] of Object.entries(attrs || {})) {
            if (v === undefined || v === null || v === false) continue;
            if (k === 'class') el.className = v;
            else if (k === 'text') el.textContent = v;
            else if (k === 'on') for (const [ev, fn] of Object.entries(v)) el.addEventListener(ev, fn);
            else if (k in el && typeof v !== 'string') el[k] = v;
            else el.setAttribute(k, v === true ? '' : v);
        }
        for (const c of children.flat(Infinity)) {
            if (c === null || c === undefined || c === false) continue;
            el.appendChild(c instanceof Node ? c : document.createTextNode(String(c)));
        }
        return el;
    }
    const icon = (name, extra = '') => h('i', { class: `fa-solid fa-${name} ${extra}`.trim() });
    const clear = (el) => { while (el.firstChild) el.removeChild(el.firstChild); return el; };
    let toastBox = null;
    function toast(message, type = 'info', ms = 3500) {
        if (!toastBox) { toastBox = h('div', { class: 'toast-box' }); document.body.appendChild(toastBox); }
        const t = h('div', { class: `toast toast-${type}`, text: message });
        toastBox.appendChild(t);
        ms = Math.max(ms, Math.min(15000, String(message).length * 70));
        setTimeout(() => { t.classList.add('out'); setTimeout(() => t.remove(), 300); }, ms);
    }
    async function api(path, opts = {}) {
        const init = { credentials: 'same-origin', method: opts.method || 'GET', headers: { Accept: 'application/json' } };
        if (opts.json !== undefined) { init.method = 'POST'; init.body = JSON.stringify(opts.json); init.headers['Content-Type'] = 'application/json'; }
        const res = await fetch(path, init);
        let data = null;
        try { data = await res.json(); } catch (e) { data = null; }
        if (res.status === 401 && data && data.login) { location.href = 'login#brunch'; throw new Error('로그인이 필요합니다.'); }
        if (!res.ok || (data && data.success === false)) throw new Error((data && data.error) || `HTTP ${res.status}`);
        return data;
    }
    const post = (path, json = {}) => api(path, { json });
    const loading = (text = '불러오는 중...') => h('div', { class: 'loading' }, icon('circle-notch', 'fa-spin'), h('span', { text }));
    const fmtSize = (n) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)}MB` : `${Math.max(1, Math.round((n || 0) / 1024))}KB`);
    const fmtDate = (ms) => { if (!ms) return ''; const d = new Date(ms); return `${d.getFullYear()}.${d.getMonth() + 1}.${d.getDate()}`; };
    async function busy(btn, fn) {
        btn.disabled = true;
        try { await fn(); } catch (e) { toast(e.message, 'error', 6000); } finally { btn.disabled = false; }
    }

    // ── 탭 ──
    const panes = {};
    root.querySelectorAll('[data-pane]').forEach((p) => { panes[p.dataset.pane] = p; });
    const tabs = root.querySelector('.brunch-tabs');
    let current = '';
    function showTab(name) {
        if (!panes[name]) name = 'browse';
        current = name;
        tabs.querySelectorAll('[data-tab]').forEach((b) => { b.classList.toggle('is-on', b.dataset.tab === name); b.setAttribute('aria-selected', b.dataset.tab === name); });
        Object.entries(panes).forEach(([k, p]) => { p.hidden = k !== name; });
        ({ browse: renderBrowse, url: renderUrl, history: renderHistory, settings: renderSettings })[name](panes[name]);
        try { history.replaceState(null, '', `#${name}`); } catch (e) { /* 무시 */ }
    }
    tabs.addEventListener('click', (e) => { const b = e.target.closest('[data-tab]'); if (b) showTab(b.dataset.tab); });

    // ── 받기 진행 (맨 위 줄) ──
    const jobsBox = root.querySelector('.br-jobs');
    let state = null;
    let pollTimer = null;
    const seen = {};   // 작업 id -> 마지막으로 본 상태 (끝났을 때 한 번만 알리려고)
    const STATE_TEXT = { queued: '대기', running: '받는 중', done: '끝', error: '실패' };
    async function refresh() {
        try { state = await api('api/brunch'); } catch (e) { return; }
        paintJobs();
        const active = state.jobs.some((j) => j.state === 'queued' || j.state === 'running');
        clearTimeout(pollTimer);
        if (active) pollTimer = setTimeout(refresh, 2000);
    }
    function paintJobs() {
        const jobs = (state && state.jobs) || [];
        let finishedNow = false;
        jobs.forEach((j) => {
            const before = seen[j.id];
            if (before && before !== j.state && (j.state === 'done' || j.state === 'error')) {
                finishedNow = true;
                if (j.state === 'done') toast(`EPUB을 만들었습니다: ${j.title} (${j.note})`, 'success', 6000);
                else toast(`받지 못했습니다: ${j.title || ''} - ${j.error}`, 'error', 8000);
            }
            seen[j.id] = j.state;
        });
        if (finishedNow && current === 'history') renderHistory(panes.history);
        clear(jobsBox);
        jobsBox.hidden = !jobs.length;
        if (!jobs.length) return;
        const list = h('div', { class: 'br-list' });
        jobs.slice(0, 8).forEach((j) => {
            const pct = j.total ? Math.round((j.done / j.total) * 100) : 0;
            list.appendChild(h('div', { class: 'br-row' },
                h('span', { class: `br-state ${j.state}`, text: STATE_TEXT[j.state] || j.state }),
                h('div', { class: 'br-row-main' },
                    h('span', { class: 'br-row-title', text: j.title || j.key }),
                    h('span', { class: 'br-row-sub' + (j.state === 'error' ? ' error-text' : ''), text: j.error || j.note || (j.kind === 'book' ? '브런치북' : '글 하나') })),
                j.state === 'running' ? h('div', { class: 'br-bar' }, h('div', { style: `width:${pct}%` })) : null));
        });
        const doneCount = jobs.filter((j) => j.state === 'done' || j.state === 'error').length;
        jobsBox.append(h('div', { class: 'toolbar' }, h('b', { text: '받기 진행' }),
            doneCount ? h('button', { class: 'btn btn-sm', type: 'button', on: { click: async () => { state = await post('api/brunch/clear-jobs'); paintJobs(); } } },
                icon('broom'), ' 끝난 줄 지우기') : null), list);
    }
    async function download(payload, label) {
        await post('api/brunch/download', payload);
        toast(`받기 대기열에 넣었습니다: ${label}`, 'success');
        refresh();
    }

    // ── 연재 목록 ──
    const DAYS = [['MONDAY', '월'], ['TUESDAY', '화'], ['WEDNESDAY', '수'], ['THURSDAY', '목'], ['FRIDAY', '금'], ['SATURDAY', '토'], ['SUNDAY', '일'], ['COMPLETE', '완결']];
    const SORTS = [['PUBLISH_TIME', '최신순'], ['LIKE_COUNT', '라이킷순'], ['DONATION_TOTAL_AMOUNT', '응원순']];
    const browse = { day: DAYS[(new Date().getDay() + 6) % 7][0], sort: 'PUBLISH_TIME' };
    function renderBrowse(pane) {
        if (pane.dataset.ready) return;
        pane.dataset.ready = '1';
        const chips = h('div', { class: 'chips' });
        const sortSel = h('select', { class: 'select', title: '정렬' }, SORTS.map(([v, t]) => h('option', { value: v, text: t })));
        const grid = h('div', { class: 'br-grid' });
        const moreBtn = h('button', { class: 'btn', type: 'button', hidden: true }, icon('chevron-down'), ' 더 보기');
        let next = '';
        const card = (it) => {
            const dl = h('button', { class: 'btn btn-sm btn-accent', type: 'button', title: '이 글이 든 브런치북 전체를 EPUB 한 권으로' }, icon('download'), ' EPUB 받기');
            dl.addEventListener('click', () => busy(dl, () => download({ url: it.url, scope: 'book', title: it.book_title }, it.book_title)));
            const thumb = it.image ? h('img', { class: 'br-thumb', src: it.image, alt: '', loading: 'lazy', referrerpolicy: 'no-referrer' })
                : h('div', { class: 'br-thumb br-thumb-empty' }, icon('book-open'));
            if (it.image) thumb.addEventListener('error', () => thumb.replaceWith(h('div', { class: 'br-thumb br-thumb-empty' }, icon('book-open'))));
            return h('div', { class: 'br-card' }, thumb,
                h('div', { class: 'br-body' },
                    h('div', { class: 'br-book' }, it.book_title, it.is_new ? h('span', { class: 'br-new', text: 'NEW' }) : null),
                    h('div', { class: 'br-meta', text: [it.author, fmtDate(it.publish_time)].filter(Boolean).join(' · ') }),
                    h('div', { class: 'br-ep', title: it.title, text: `최근: ${it.title}` }),
                    h('div', { class: 'toolbar' }, dl,
                        h('a', { class: 'btn btn-sm', href: it.url, target: '_blank', rel: 'noopener noreferrer' }, icon('arrow-up-right-from-square'), ' 브런치'))));
        };
        const load = async (more) => {
            if (!more) { clear(grid).appendChild(loading()); next = ''; }
            moreBtn.hidden = true;
            const q = new URLSearchParams({ day: browse.day, sort: browse.sort });
            if (more && next) q.set('next', next);
            try {
                const data = await api(`api/brunch/list?${q}`);
                if (!more) clear(grid);
                data.items.filter((it) => it.url).forEach((it) => grid.appendChild(card(it)));
                if (!grid.children.length) grid.appendChild(h('p', { class: 'muted', text: '연재가 없습니다.' }));
                next = data.next_url || '';
                moreBtn.hidden = !(data.more && next);
            } catch (e) {
                clear(grid).appendChild(h('p', { class: 'error-text', text: `목록을 불러오지 못했습니다: ${e.message}` }));
            }
        };
        const paintChips = () => {
            clear(chips);
            DAYS.forEach(([v, t]) => chips.appendChild(h('button', { type: 'button', class: 'chip' + (browse.day === v ? ' is-on' : ''), text: t,
                on: { click: () => { browse.day = v; paintChips(); load(false); } } })));
            sortSel.disabled = browse.day === 'COMPLETE';
        };
        sortSel.value = browse.sort;
        sortSel.addEventListener('change', () => { browse.sort = sortSel.value; load(false); });
        moreBtn.addEventListener('click', () => busy(moreBtn, () => load(true)));
        paintChips();
        pane.append(h('div', { class: 'toolbar' }, chips, sortSel),
            h('p', { class: 'field-hint', text: '브런치북 오리지널 연재 목록입니다. [EPUB 받기]는 그 글이 든 브런치북의 발행된 회차 전부를 한 권으로 받습니다 (멤버십 글은 공개된 앞부분만).' }),
            grid, moreBtn);
        load(false);
    }

    // ── 주소로 받기 ──
    function renderUrl(pane) {
        if (pane.dataset.ready) return;
        pane.dataset.ready = '1';
        const input = h('input', { class: 'input', placeholder: 'https://brunch.co.kr/brunchbook/… 또는 https://brunch.co.kr/@…/12', style: 'flex:1;min-width:0' });
        const go = h('button', { class: 'btn btn-accent', type: 'button' }, icon('magnifying-glass'), ' 확인');
        const out = h('div', {});
        const bookCard = (b, extra) => {
            const dl = h('button', { class: 'btn btn-accent', type: 'button', disabled: !b.count },
                icon('download'), ` 브런치북 전체 받기 (${b.count}화)`);
            dl.addEventListener('click', () => busy(dl, () => download({ address: b.address, title: b.title }, b.title)));
            return h('div', { class: 'card' }, h('div', { class: 'br-preview' },
                b.cover ? h('img', { src: b.cover, alt: '', referrerpolicy: 'no-referrer' }) : null,
                h('div', {},
                    h('div', { class: 'br-book', text: b.title }),
                    h('div', { class: 'br-meta', text: [b.author, b.status === 'COMPLETE' ? '완결' : (b.status ? '연재 중' : ''),
                        `발행 ${b.count}화` + (b.planned ? ` · 발행 예정 ${b.planned}화` : '')].filter(Boolean).join(' · ') }),
                    b.description ? h('p', { class: 'desc', text: b.description }) : null,
                    h('div', { class: 'toolbar', style: 'margin-top:0.7rem' }, dl, extra || null,
                        h('a', { class: 'btn', href: b.url, target: '_blank', rel: 'noopener noreferrer' }, icon('arrow-up-right-from-square'), ' 브런치')))));
        };
        const check = async () => {
            const url = input.value.trim();
            if (!url) { input.focus(); return; }
            clear(out).appendChild(loading('브런치에서 확인하는 중...'));
            try {
                const r = await api(`api/brunch/resolve?${new URLSearchParams({ url })}`);
                clear(out);
                if (r.kind === 'book') { out.appendChild(bookCard(r.book)); return; }
                const a = r.article;
                const one = h('button', { class: 'btn', type: 'button' }, icon('file-arrow-down'), ' 이 글만 받기');
                one.addEventListener('click', () => busy(one, () => download({ user_id: a.user_id, article_no: a.article_no, title: a.title }, a.title)));
                out.appendChild(h('div', { class: 'card' },
                    h('div', { class: 'br-book', text: a.title }),
                    h('div', { class: 'br-meta', text: [a.author, a.book_title ? `브런치북: ${a.book_title}` : '브런치북에 묶이지 않은 글',
                        a.restricted ? '멤버십 글 (공개된 앞부분만 담김)' : ''].filter(Boolean).join(' · ') }),
                    a.subtitle ? h('p', { class: 'desc muted', text: a.subtitle }) : null,
                    r.book ? null : h('div', { class: 'toolbar' }, one)));
                if (r.book) out.appendChild(bookCard(r.book, one));
            } catch (e) {
                clear(out).appendChild(h('p', { class: 'error-text', text: e.message }));
            }
        };
        go.addEventListener('click', () => busy(go, check));
        input.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); busy(go, check); } });
        pane.append(h('div', { class: 'card' },
            h('div', { class: 'field' }, h('span', { class: 'field-label', text: '브런치 주소' }),
                h('div', { class: 'toolbar', style: 'flex-wrap:nowrap' }, input, go),
                h('span', { class: 'field-hint', text: '브런치북 주소를 넣으면 그 책 전체를, 글 주소를 넣으면 그 글이 든 브런치북 전체 또는 그 글 하나를 받을 수 있습니다.' }))),
        out);
    }

    // ── 받은 목록 ──
    async function renderHistory(pane) {
        clear(pane).appendChild(loading());
        try { state = await api('api/brunch'); } catch (e) { clear(pane).appendChild(h('p', { class: 'error-text', text: e.message })); return; }
        paintJobs();
        clear(pane);
        const hist = state.history || [];
        if (!hist.length) { pane.appendChild(h('p', { class: 'muted', text: '아직 받은 책이 없습니다. [연재 목록]이나 [주소로 받기]에서 받으세요.' })); return; }
        const list = h('div', { class: 'br-list' });
        hist.forEach((x) => {
            const again = h('button', { class: 'btn btn-sm', type: 'button', title: '새 회차까지 담아 다시 만들어 덮어씁니다' }, icon('rotate'), ' 다시 받기');
            again.addEventListener('click', () => busy(again, async () => { await post('api/brunch/redownload', { id: x.id }); toast(`다시 받습니다: ${x.title}`, 'success'); refresh(); }));
            const forget = h('button', { class: 'btn btn-sm danger', type: 'button', title: '받은 목록에서 빼기' }, icon('trash'));
            forget.addEventListener('click', () => busy(forget, async () => {
                if (!confirm(`"${x.title}"을(를) 받은 목록에서 뺄까요?`)) return;
                const removeFile = x.exists && confirm('저장된 EPUB 파일도 지울까요? ([취소]를 누르면 파일은 그대로 둡니다)');
                state = await post('api/brunch/forget', { id: x.id, remove_file: removeFile });
                renderHistory(pane);
            }));
            const sub = [x.author, `${x.chapters}화`, x.images ? `그림 ${x.images}장` : '', fmtSize(x.size), x.at,
                x.restricted ? `멤버십 글 ${x.restricted}개는 앞부분만` : '', (x.skipped || []).length ? `빠진 글 ${x.skipped.length}개` : '',
                x.scan ? 'BookOasis 스캔 요청함' : ''].filter(Boolean).join(' · ');
            list.appendChild(h('div', { class: 'br-row' },
                h('div', { class: 'br-row-main' },
                    h('span', { class: 'br-row-title', text: x.title }),
                    h('span', { class: 'br-row-sub', text: sub }),
                    h('span', { class: 'br-row-sub', text: x.exists ? x.path : `파일 없음 (옮겼거나 지움): ${x.path}` }),
                    (x.skipped || []).length ? h('span', { class: 'br-row-sub error-text', text: `빠진 글: ${x.skipped.join(', ')}` }) : null),
                h('div', { class: 'toolbar' },
                    x.exists ? h('a', { class: 'btn btn-sm btn-accent', href: `api/brunch/file?id=${encodeURIComponent(x.id)}` }, icon('download'), ' 내려받기') : null,
                    again, x.url ? h('a', { class: 'btn btn-sm', href: x.url, target: '_blank', rel: 'noopener noreferrer', title: '브런치에서 보기' }, icon('arrow-up-right-from-square')) : null,
                    forget)));
        });
        pane.appendChild(list);
    }

    // ── 설정 ──
    async function renderSettings(pane) {
        clear(pane).appendChild(loading());
        try { state = await api('api/brunch'); } catch (e) { clear(pane).appendChild(h('p', { class: 'error-text', text: e.message })); return; }
        clear(pane);
        const s = state.settings;
        const dirIn = h('input', { class: 'input', value: s.save_dir, placeholder: state.env_root || '비우면 기본 위치' });
        const byAuthor = h('input', { type: 'checkbox', checked: s.by_author });
        const save = h('button', { class: 'btn btn-accent', type: 'button' }, icon('floppy-disk'), ' 저장');
        save.addEventListener('click', () => busy(save, async () => {
            state = await post('api/brunch/settings', { save_dir: dirIn.value.trim(), by_author: byAuthor.checked });
            toast('저장했습니다.', 'success');
            renderSettings(pane);
        }));
        pane.append(h('div', { class: 'card' },
            h('label', { class: 'field' }, h('span', { class: 'field-label', text: '저장 폴더 (서버 경로)' }), dirIn,
                h('span', { class: 'field-hint', text: `지금 저장하는 곳: ${state.root}` }),
                h('span', { class: 'field-hint', text: 'BookOasis 보관함 안의 폴더(예: /mnt/books/브런치)로 두면 받은 뒤 드라이브 변경 감시가 바로 BookOasis 스캔을 요청합니다. '
                    + '비우면 .env의 BRUNCH_DOWNLOAD_ROOT, 그것도 없으면 데이터 폴더(DATA_DIR/brunch/files)에 둡니다.' })),
            h('label', { class: 'check' }, byAuthor, ' 작가 이름으로 폴더 나누기 (<저장 폴더>/<작가>/<브런치북 제목>.epub)'),
            h('div', { class: 'toolbar' }, save)),
        h('div', { class: 'card' }, h('b', { text: '알아 두기' }),
            h('p', { class: 'field-hint', text: '브런치북 하나 = EPUB 한 권입니다. 발행된 회차가 차례대로 장이 되고, 목차·표지·책 정보(소개·원문 주소)와 본문 그림이 함께 들어갑니다. '
                + '연재 중인 책은 [받은 목록 > 다시 받기]로 새 회차까지 담아 덮어쓸 수 있습니다.' }),
            h('p', { class: 'field-hint', text: '멤버십(유료) 글은 브런치 페이지에 공개된 앞부분만 담기고 원문 링크가 붙습니다. 받은 EPUB은 개인 소장용으로만 쓰세요 (글의 저작권은 작가에게 있습니다).' })));
    }

    showTab((location.hash || '').slice(1) || 'browse');
    refresh();
})();
