// 브런치 EPUB 받기 화면 (서버: brunch/service.py)
(function () {
    'use strict';
    // 분 -> '10분' / '1시간 30분' / '6시간'
    const fmtMin = (m) => (m % 60 ? (m > 60 ? `${Math.floor(m / 60)}시간 ${m % 60}분` : `${m}분`) : `${m / 60}시간`);
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
        const active = state.jobs.some((j) => j.state === 'queued' || j.state === 'running') || !!(state.bulk && state.bulk.running);
        clearTimeout(pollTimer);
        if (active) pollTimer = setTimeout(refresh, 2000);
    }
    function paintJobs() {
        const jobs = (state && state.jobs) || [];
        let finishedNow = false;
        const ended = [];
        jobs.forEach((j) => {
            const before = seen[j.id];
            if (before && before !== j.state && (j.state === 'done' || j.state === 'error')) {
                finishedNow = true;
                ended.push(j);
            }
            seen[j.id] = j.state;
        });
        // 한꺼번에 많이 끝나면(완결작 모두 받기) 한 번에 묶어서 알린다
        const made = ended.filter((j) => j.state === 'done' && !/^이미/.test(j.note || ''));
        const failed = ended.filter((j) => j.state === 'error');
        if (ended.length > 2) {
            if (made.length || failed.length) toast(`EPUB ${made.length}권을 만들었습니다${failed.length ? ` · 실패 ${failed.length}권` : ''}.`, failed.length ? 'error' : 'success', 6000);
        } else {
            made.forEach((j) => toast(`EPUB을 만들었습니다: ${j.title} (${j.note})`, 'success', 6000));
            failed.forEach((j) => toast(`받지 못했습니다: ${j.title || ''} - ${j.error}`, 'error', 8000));
        }
        if (finishedNow && current === 'history') renderHistory(panes.history);
        clear(jobsBox);
        jobsBox.hidden = !jobs.length;
        if (!jobs.length && !((state && state.bulk) || {}).running) return;
        jobsBox.hidden = false;
        const list = h('div', { class: 'br-list' });
        jobs.slice(0, 8).forEach((j) => {
            const pct = j.total ? Math.round((j.done / j.total) * 100) : 0;
            list.appendChild(h('div', { class: 'br-row' },
                h('span', { class: `br-state ${j.state}`, text: STATE_TEXT[j.state] || j.state }),
                h('div', { class: 'br-row-main' },
                    h('span', { class: 'br-row-title', text: (j.auto ? '[새 글] ' : '') + (j.title || j.key) }),
                    h('span', { class: 'br-row-sub' + (j.state === 'error' ? ' error-text' : ''), text: j.error || j.note || (j.kind === 'book' ? '브런치북' : j.kind === 'bookof' ? '브런치북 (완결작 모두 받기)' : '글 하나') })),
                j.state === 'running' ? h('div', { class: 'br-bar' }, h('div', { style: `width:${pct}%` })) : null));
        });
        const doneCount = jobs.filter((j) => j.state === 'done' || j.state === 'error').length;
        const waiting = jobs.filter((j) => j.state === 'queued').length;
        const bulk = (state && state.bulk) || {};
        jobsBox.append(h('div', { class: 'toolbar' }, h('b', { text: '받기 진행' }),
            waiting ? h('span', { class: 'muted', text: `대기 ${waiting}개` }) : null,
            bulk.running ? h('span', { class: 'muted', text: `완결작 목록 모으는 중: ${bulk.pages}쪽 · 책 ${bulk.seen}권 중 ${bulk.queued}권 대기열에` }) : null,
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
        // 완결 탭: 완결된 책 전부를 EPUB으로 (이미 다 받은 책은 빼고)
        const bulkBtn = h('button', { class: 'btn btn-accent', type: 'button', hidden: true,
            title: '완결 목록을 끝까지 넘겨 보며 아직 받지 않은 완결 브런치북을 모두 받기 대기열에 넣습니다' }, icon('layer-group'), ' 완결작 모두 EPUB으로');
        bulkBtn.addEventListener('click', () => busy(bulkBtn, async () => {
            if (!confirm('완결된 브런치북을 모두 EPUB으로 만들까요?\n이미 받은 책은 건너뛰고, 한 권씩 차례로 받습니다 (책이 많으면 오래 걸립니다).')) return;
            await post('api/brunch/bulk-complete');
            toast('완결작 목록을 모아 받기 대기열에 넣는 중입니다. 맨 위 [받기 진행]에서 보세요.', 'success', 6000);
            refresh();
        }));
        let next = '';
        // 이 글(최근 회차)이 받아 둔 EPUB에 들어 있는지
        const EPUB_BADGE = {
            done: ['br-epub done', 'circle-check', 'EPUB 반영됨', '이 회차까지 EPUB에 들어 있습니다'],
            old: ['br-epub old', 'triangle-exclamation', '새 회차 미반영', '받아 둔 EPUB에 이 회차가 아직 없습니다 - [다시 받기]로 합쳐 다시 만듭니다'],
            queued: ['br-epub queued', 'hourglass-half', '받는 중', 'EPUB으로 만드는 중이거나 대기 중입니다'],
        };
        const card = (it) => {
            const old = it.epub === 'old';
            const dl = h('button', { class: `btn btn-sm${it.epub === 'done' ? '' : ' btn-accent'}`, type: 'button', title: '이 글이 든 브런치북 전체를 EPUB 한 권으로' },
                icon(old ? 'rotate' : 'download'), old ? ' 다시 받기' : it.epub === 'done' ? ' 다시 받기' : ' EPUB 받기');
            const b = EPUB_BADGE[it.epub];
            const badge = b ? h('div', { class: b[0], title: b[3] + (it.epub_at ? ` (마지막으로 받은 때 ${it.epub_at})` : '') }, icon(b[1]), ` ${b[2]}`) : null;
            dl.addEventListener('click', () => busy(dl, () => download({ url: it.url, scope: 'book', title: it.book_title }, it.book_title)));
            const thumb = it.image ? h('img', { class: 'br-thumb', src: it.image, alt: '', loading: 'lazy', referrerpolicy: 'no-referrer' })
                : h('div', { class: 'br-thumb br-thumb-empty' }, icon('book-open'));
            if (it.image) thumb.addEventListener('error', () => thumb.replaceWith(h('div', { class: 'br-thumb br-thumb-empty' }, icon('book-open'))));
            return h('div', { class: 'br-card' }, thumb,
                h('div', { class: 'br-body' },
                    h('div', { class: 'br-book' }, it.book_title, it.is_new ? h('span', { class: 'br-new', text: 'NEW' }) : null),
                    h('div', { class: 'br-meta', text: [it.author, fmtDate(it.publish_time),
                        it.days && it.days.length ? (it.days.includes('완결') ? '완결' : `${it.days.join('·')}요일 연재`) : ''].filter(Boolean).join(' · ') }),
                    h('div', { class: 'br-ep', title: it.title, text: `최근: ${it.title}` }),
                    badge,
                    h('div', { class: 'toolbar' }, dl,
                        h('a', { class: 'btn btn-sm', href: it.url, target: '_blank', rel: 'noopener noreferrer' }, icon('arrow-up-right-from-square'), ' 브런치'))));
        };
        // 제목으로 찾기: 모든 요일·완결 목록에서 (서버가 처음 한 번 모아 두는 동안은 조금 기다렸다 다시 묻는다)
        const searchBox = h('input', { class: 'input br-search', type: 'search', placeholder: '제목·작가로 찾기',
            title: '모든 요일과 완결 목록에서 브런치북 제목·회차 제목·작가로 찾습니다' });
        const searchNote = h('p', { class: 'field-hint', hidden: true });
        let searchSeq = 0, searchTimer = null;
        const runSearch = async () => {
            const q = searchBox.value.trim();
            const seq = ++searchSeq;
            clearTimeout(searchTimer);
            if (!q) { searchNote.hidden = true; chips.hidden = false; sortSel.hidden = false; paintChips(); load(false); return; }
            chips.hidden = true; sortSel.hidden = true; bulkBtn.hidden = true; moreBtn.hidden = true;
            if (!grid.querySelector('.br-card')) clear(grid).appendChild(loading());
            try {
                const data = await api(`api/brunch/search?${new URLSearchParams({ q })}`);
                if (seq !== searchSeq) return;
                clear(grid);
                data.items.forEach((it) => grid.appendChild(card(it)));
                searchNote.hidden = false;
                searchNote.textContent = data.building
                    ? `연재 목록을 모으는 중입니다 (${data.pages}쪽째) - 찾은 것 ${data.items.length}개, 다 모으면 다시 찾습니다.`
                    : `'${q}' - ${data.items.length}개 찾음 (모든 요일·완결 브런치북 ${data.total}권 중)` + (data.error ? ` · 오류: ${data.error}` : '');
                if (!data.items.length && !data.building) grid.appendChild(h('p', { class: 'muted', text: '찾은 브런치북이 없습니다.' }));
                if (data.building) searchTimer = setTimeout(() => { if (seq === searchSeq) runSearch(); }, 2500);
            } catch (e) {
                if (seq === searchSeq) clear(grid).appendChild(h('p', { class: 'error-text', text: `찾지 못했습니다: ${e.message}` }));
            }
        };
        let typing = null;
        searchBox.addEventListener('input', () => { clearTimeout(typing); typing = setTimeout(runSearch, 400); });
        searchBox.addEventListener('keydown', (e) => { if (e.key === 'Enter') { clearTimeout(typing); runSearch(); } });
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
                on: { click: () => { browse.day = v; searchBox.value = ''; searchNote.hidden = true; paintChips(); load(false); } } })));
            sortSel.disabled = browse.day === 'COMPLETE';
            bulkBtn.hidden = browse.day !== 'COMPLETE';
        };
        sortSel.value = browse.sort;
        sortSel.addEventListener('change', () => { browse.sort = sortSel.value; load(false); });
        moreBtn.addEventListener('click', () => busy(moreBtn, () => load(true)));
        paintChips();
        pane.append(h('div', { class: 'toolbar' }, chips, sortSel, bulkBtn, searchBox), searchNote,
            h('p', { class: 'field-hint', text: '브런치북 오리지널 연재 목록입니다. [EPUB 받기]는 그 글이 든 브런치북의 발행된 회차 전부를 한 권으로 받습니다 (멤버십 글은 공개된 앞부분만). '
                + '카드 아래 표시: "EPUB 반영됨"은 이 회차까지 EPUB에 들어 있음, "새 회차 미반영"은 받아 둔 EPUB에 이 회차가 아직 없음([다시 받기]). 완결 탭의 [완결작 모두 EPUB으로]는 아직 받지 않은 완결작을 모두 받습니다.' }),
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
        pane.appendChild(checkBar(() => renderHistory(pane)));
        const list = h('div', { class: 'br-list' });
        hist.forEach((x) => {
            // 새 글 자동 받기 (브런치북만, 완결된 책은 확인하지 않음)
            let autoBox = null;
            if (x.kind === 'book') {
                const chk = h('input', { type: 'checkbox', checked: !!x.auto, disabled: x.status === 'COMPLETE' });
                chk.addEventListener('change', async () => {
                    chk.disabled = true;
                    try { state = await post('api/brunch/auto', { id: x.id, auto: chk.checked }); toast(chk.checked ? `새 글이 오르면 자동으로 받습니다: ${x.title}` : `자동 받기를 껐습니다: ${x.title}`, 'success'); }
                    catch (e) { chk.checked = !chk.checked; toast(e.message, 'error'); }
                    finally { chk.disabled = false; }
                });
                autoBox = h('label', { class: 'check', title: x.status === 'COMPLETE' ? '완결된 책은 새 글을 확인하지 않습니다' : '새 회차가 발행되면 자동으로 다시 받아 덮어씁니다' },
                    chk, x.status === 'COMPLETE' ? ' 완결' : ' 자동 받기');
            }
            const checked = x.kind === 'book' && x.status !== 'COMPLETE' && x.auto
                ? (x.check_error ? `새 글 확인 실패: ${x.check_error}` : (x.checked_at ? `새 글 확인: ${x.checked_at}` : '')) : '';
            const again = h('button', { class: `btn btn-sm${x.epub_state === 'behind' || x.epub_state === 'missing' ? ' btn-accent' : ''}`, type: 'button',
                title: '새 회차까지 담아 다시 만들어 덮어씁니다' }, icon('rotate'), ' 다시 받기');
            again.addEventListener('click', () => busy(again, async () => { await post('api/brunch/redownload', { id: x.id }); toast(`다시 받습니다: ${x.title}`, 'success'); refresh(); }));
            const forget = h('button', { class: 'btn btn-sm danger', type: 'button', title: '받은 목록에서 빼기' }, icon('trash'));
            forget.addEventListener('click', () => busy(forget, async () => {
                if (!confirm(`"${x.title}"을(를) 받은 목록에서 뺄까요?`)) return;
                const removeFile = x.exists && confirm('저장된 EPUB 파일도 지울까요? ([취소]를 누르면 파일은 그대로 둡니다)');
                state = await post('api/brunch/forget', { id: x.id, remove_file: removeFile });
                renderHistory(pane);
            }));
            const sub = [x.author, `${x.chapters}화`, x.images ? `그림 ${x.images}장` : '', fmtSize(x.size),
                x.first_published ? `발행 ${x.first_published.replace(/-/g, '.')}${x.last_published && x.last_published !== x.first_published ? `~${x.last_published.replace(/-/g, '.')}` : ''}` : '',
                x.at ? `받은 때 ${x.at}` : '',
                x.restricted ? `멤버십 글 ${x.restricted}개는 앞부분만` : '', (x.skipped || []).length ? `빠진 글 ${x.skipped.length}개` : '',
                x.yaml ? 'kavita.yaml' : '', x.scan ? 'BookOasis 스캔 요청함' : ''].filter(Boolean).join(' · ');
            // EPUB 상태: 최신 회차까지 담겼는지
            const ST = {
                latest: ['br-epub done', 'circle-check', `EPUB 최신 (${x.chapters}화${x.latest_title ? ` · ${x.latest_title}` : ''})`],
                behind: ['br-epub old', 'triangle-exclamation', `새 회차 ${x.new_count}개 미반영 (EPUB ${x.chapters}화 / 발행 ${x.published}화) - [다시 받기]`],
                queued: ['br-epub queued', 'hourglass-half', 'EPUB 만드는 중'],
                missing: ['br-epub old', 'file-circle-xmark', 'EPUB 파일 없음 (옮겼거나 지움) - [다시 받기]로 다시 만들기'],
            }[x.epub_state];
            const stBadge = ST ? h('span', { class: ST[0], title: x.checked_at ? `마지막 새 글 확인: ${x.checked_at}` : '' }, icon(ST[1]), ` ${ST[2]}`) : null;
            list.appendChild(h('div', { class: 'br-row' },
                h('div', { class: 'br-row-main' },
                    h('span', { class: 'br-row-title', text: x.title }),
                    stBadge,
                    h('span', { class: 'br-row-sub', text: sub }),
                    h('span', { class: 'br-row-sub', text: x.exists ? x.path : `파일 없음 (옮겼거나 지움): ${x.path}` }),
                    (x.skipped || []).length ? h('span', { class: 'br-row-sub error-text', text: `빠진 글: ${x.skipped.join(', ')}` }) : null,
                    checked ? h('span', { class: 'br-row-sub' + (x.check_error ? ' error-text' : ''), text: checked }) : null),
                h('div', { class: 'toolbar' }, autoBox,
                    x.exists ? h('a', { class: 'btn btn-sm btn-accent', href: `api/brunch/file?id=${encodeURIComponent(x.id)}` }, icon('download'), ' 내려받기') : null,
                    again, x.url ? h('a', { class: 'btn btn-sm', href: x.url, target: '_blank', rel: 'noopener noreferrer', title: '브런치에서 보기' }, icon('arrow-up-right-from-square')) : null,
                    forget)));
        });
        pane.appendChild(list);
    }

    // 새 글 확인 상태 줄 + [지금 새 글 확인]
    const fmtTime = (sec) => { if (!sec) return ''; const d = new Date(sec * 1000); return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`; };
    function checkBar(again) {
        const c = state.check || {};
        const s = state.settings || {};
        const btn = h('button', { class: 'btn btn-sm', type: 'button', disabled: !!c.running }, icon('magnifying-glass'), c.running ? ' 확인하는 중...' : ' 지금 새 글 확인');
        btn.addEventListener('click', () => busy(btn, async () => {
            state = await post('api/brunch/check');
            toast('연재 중인 브런치북의 새 글을 확인합니다. 새 글이 있으면 받기 진행에 나옵니다.', 'success');
            setTimeout(() => { refresh(); again(); }, 4000);
        }));
        const text = !s.auto_check ? '새 글 자동 받기가 꺼져 있습니다 (설정 탭).'
            : `새 글 자동 받기: ${fmtMin(s.check_minutes || s.check_hours * 60)}마다` + (c.last ? ` · 마지막 확인 ${fmtTime(c.last)}` + (c.found ? ` (새 글 ${c.found}권)` : '') : '')
              + (c.next ? ` · 다음 확인 ${fmtTime(c.next)}` : '') + (c.error ? ` · 실패: ${c.error}` : '');
        return h('div', { class: 'toolbar' }, h('span', { class: 'field-hint', text }), btn);
    }

    // ── 설정 ──
    async function renderSettings(pane) {
        clear(pane).appendChild(loading());
        try { state = await api('api/brunch'); } catch (e) { clear(pane).appendChild(h('p', { class: 'error-text', text: e.message })); return; }
        clear(pane);
        const s = state.settings;
        const dirIn = h('input', { class: 'input', value: s.save_dir, placeholder: state.env_root || '비우면 기본 위치' });
        const byAuthor = h('input', { type: 'checkbox', checked: s.by_author });
        const autoIn = h('input', { type: 'checkbox', checked: s.auto_check });
        const yamlIn = h('input', { type: 'checkbox', checked: s.kavita_yaml !== false });
        const hoursSel = h('select', { class: 'select', style: 'width:auto' },
            (state.check_minutes || [10, 20, 30, 60, 120, 180, 360, 720, 1440]).map((n) => h('option', { value: String(n), text: `${fmtMin(n)}마다`,
                selected: n === (s.check_minutes || s.check_hours * 60) })));
        const save = h('button', { class: 'btn btn-accent', type: 'button' }, icon('floppy-disk'), ' 저장');
        save.addEventListener('click', () => busy(save, async () => {
            state = await post('api/brunch/settings', { save_dir: dirIn.value.trim(), by_author: byAuthor.checked,
                auto_check: autoIn.checked, check_minutes: Number(hoursSel.value), kavita_yaml: yamlIn.checked });
            toast('저장했습니다.', 'success');
            renderSettings(pane);
        }));
        pane.append(h('div', { class: 'card' },
            h('label', { class: 'field' }, h('span', { class: 'field-label', text: '저장 폴더 (서버 경로)' }), dirIn,
                h('span', { class: 'field-hint', text: `지금 저장하는 곳: ${state.root}` }),
                h('span', { class: 'field-hint', text: 'BookOasis 보관함 안의 폴더(예: /mnt/books/브런치)로 두면 받은 뒤 드라이브 변경 감시가 바로 BookOasis 스캔을 요청합니다. '
                    + '비우면 .env의 BRUNCH_DOWNLOAD_ROOT, 그것도 없으면 데이터 폴더(DATA_DIR/brunch/files)에 둡니다.' })),
            h('label', { class: 'check' }, byAuthor, ' 작가 이름으로 폴더 나누기 (<저장 폴더>/<작가>/<브런치북 제목>/<브런치북 제목>.epub)'),
            h('div', { class: 'field' }, h('label', { class: 'check' }, yamlIn, ' kavita.yaml 만들기 (BookOasis 메타데이터)'),
                h('span', { class: 'field-hint', text: '웹툰 다운로더처럼 책 폴더에 kavita.yaml을 같이 둡니다: 제목·작가·소개·연재 상태·첫 회 발행일·원문 주소·표지(출판사 "브런치"). '
                    + '책마다 폴더 하나에 받습니다. 예전에 작가 폴더에 바로 받은 책은 프로그램을 다시 켤 때 한 번 다시 받아 책 폴더로 옮깁니다.' })),
            h('div', { class: 'field' }, h('span', { class: 'field-label', text: '새 글 자동 받기' }),
                h('div', { class: 'toolbar' }, h('label', { class: 'check' }, autoIn, ' 받은 연재 중 브런치북에 새 글이 오르면 자동으로 받기'), hoursSel),
                h('span', { class: 'field-hint', text: '정한 간격마다 받은 목록의 연재 중인 브런치북을 확인해, 발행된 회차가 늘었으면 새 회차까지 담아 다시 받아 덮어씁니다 '
                    + '(저장 폴더가 보관함 안이면 BookOasis 스캔도 다시). 책마다 [받은 목록 > 자동 받기]로 끌 수 있고, 완결된 책은 확인하지 않습니다.' })),
            h('div', { class: 'toolbar' }, save)),
        h('div', { class: 'card' }, h('b', { text: '알아 두기' }),
            h('p', { class: 'field-hint', text: '브런치북 하나 = EPUB 한 권입니다. 발행된 회차가 차례대로 장이 되고, 목차·표지·책 정보(소개·원문 주소)와 본문 그림이 함께 들어갑니다. '
                + '연재 중인 책은 새 글이 오르면 자동으로 다시 받고(위 설정), [받은 목록 > 다시 받기]로 바로 받을 수도 있습니다.' }),
            h('p', { class: 'field-hint', text: '멤버십(유료) 글은 브런치 페이지에 공개된 앞부분만 담기고 원문 링크가 붙습니다. 받은 EPUB은 개인 소장용으로만 쓰세요 (글의 저작권은 작가에게 있습니다).' })));
    }

    showTab((location.hash || '').slice(1) || 'browse');
    refresh();
})();
