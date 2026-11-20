// 텔레그램 자동 올리기 화면 (서버: tgup/service.py). YMPlayer 설정 > 자동 올리기 화면(views/settings.js renderMirror)을 옮긴 것.
(function () {
    'use strict';
    const root = document.getElementById('tgup-app');

    // ── 작은 도구 ──
    function h(tag, attrs, ...children) {
        const el = document.createElement(tag);
        for (const [k, v] of Object.entries(attrs || {})) {
            if (v === undefined || v === null || v === false) continue;
            if (k === 'class') el.className = v;
            else if (k === 'text') el.textContent = v;
            else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
            else if (k === 'dataset') Object.assign(el.dataset, v);
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
    function modal(title, body, actions = []) {
        const close = () => wrap.remove();
        const wrap = h('div', { class: 'modal', on: { click: (e) => { if (e.target === wrap) close(); } } },
            h('div', { class: 'modal-card' },
                h('div', { class: 'modal-head' }, h('h3', { text: title }),
                    h('button', { class: 'icon-btn', title: '닫기', on: { click: close } }, icon('xmark'))),
                h('div', { class: 'modal-body' }, body),
                actions.length ? h('div', { class: 'modal-foot' }, actions) : null));
        document.body.appendChild(wrap);
        return { el: wrap, close };
    }
    async function api(path, opts = {}) {
        const init = { credentials: 'same-origin', method: opts.method || 'GET', headers: { Accept: 'application/json' } };
        if (opts.json !== undefined) { init.method = 'POST'; init.body = JSON.stringify(opts.json); init.headers['Content-Type'] = 'application/json'; }
        const res = await fetch(path, init);
        let data = null;
        try { data = await res.json(); } catch (e) { data = null; }
        if (res.status === 401 && data && data.login) { location.href = 'login#tgup'; throw new Error('로그인이 필요합니다.'); }
        if (!res.ok || (data && data.success === false)) throw new Error((data && data.error) || `HTTP ${res.status}`);
        return data;
    }
    const post = (path, json = {}) => api(path, { json });
    function field(label, input, hint) {
        return h('label', { class: 'field' }, h('span', { class: 'field-label', text: label }), input,
            hint ? h('span', { class: 'field-hint', text: hint }) : null);
    }
    const loading = () => h('div', { class: 'loading' }, icon('circle-notch', 'fa-spin'), h('span', { text: '불러오는 중...' }));
    const folderParent = (p) => {
        const m = /^([^/:]+:)(.*)$/.exec(p);   // rclone 원격 "이름:경로"
        if (m && !p.startsWith('/')) { const rest = m[2].replace(/\/+$/, ''); return rest.includes('/') ? m[1] + rest.slice(0, rest.lastIndexOf('/')) : (rest ? m[1] : ''); }
        const t = p.replace(/\/+$/, ''); return t.lastIndexOf('/') > 0 ? t.slice(0, t.lastIndexOf('/')) : (t === '' || t === '/' ? '' : '/');
    };
    const folderJoin = (p, n) => (p.endsWith('/') || p.endsWith(':') ? p + n : `${p}/${n}`);

    // ── 탭 ──
    const panes = {};
    root.querySelectorAll('[data-pane]').forEach((p) => { panes[p.dataset.pane] = p; });
    const tabs = root.querySelector('.tgup-tabs');
    function showTab(name) {
        if (!panes[name]) name = 'status';
        tabs.querySelectorAll('[data-tab]').forEach((b) => { b.classList.toggle('is-on', b.dataset.tab === name); b.setAttribute('aria-selected', b.dataset.tab === name); });
        Object.entries(panes).forEach(([k, p]) => { p.hidden = k !== name; });
        if (name === 'status') renderStatus(panes.status);
        if (name === 'rules') renderRules(panes.rules);
        if (name === 'send') renderSend(panes.send);
        if (name === 'account') renderAccount(panes.account);
        try { history.replaceState(null, '', `#${name}`); } catch (e) { /* 무시 */ }
    }
    tabs.addEventListener('click', (e) => { const b = e.target.closest('[data-tab]'); if (b) showTab(b.dataset.tab); });

    // ── 텔레그램 계정 ──
    async function renderAccount(pane) {
        clear(pane).appendChild(loading());
        let d;
        try { d = await api('api/tgup'); } catch (e) { clear(pane).appendChild(h('p', { class: 'muted error', text: e.message })); return; }
        const a = d.account || {};
        const apiId = h('input', { class: 'input', inputmode: 'numeric', value: a.api_id || '', placeholder: '12345678', disabled: a.from_env });
        const apiHash = h('input', { class: 'input', type: 'password', placeholder: a.has_hash ? '저장됨 (바꿀 때만 입력)' : '0123456789abcdef…', disabled: a.from_env, autocomplete: 'off' });
        const saveApi = h('button', { class: 'btn', disabled: a.from_env, on: { click: async () => {
            try { await post('api/tgup/account', { action: 'save_api', api_id: apiId.value.trim(), api_hash: apiHash.value.trim() }); toast('저장했습니다.', 'success'); renderAccount(pane); }
            catch (e) { toast(e.message, 'error', 6000); }
        } } }, icon('check'), ' API 저장');
        const apiCard = h('div', { class: 'src-card' },
            h('h3', { class: 'pane-title' }, icon('key'), ' Telegram API'),
            h('p', { class: 'field-hint', text: 'my.telegram.org에 로그인 > API development tools에서 앱을 만들면 나오는 api_id와 api_hash입니다. '
                + (a.from_env ? '.env의 TGUP_API_ID / TGUP_API_HASH로 정해져 있어 여기서는 바꿀 수 없습니다.' : '화면에서 넣으면 data/tgup/settings.json에 저장됩니다.') }),
            h('div', { class: 'row-2' }, field('API ID', apiId), field('API Hash', apiHash)),
            h('div', { class: 'toolbar' }, saveApi));
        const accounts = d.accounts && d.accounts.length ? d.accounts : [{ ...a, id: 'tg' }];
        const cards = accounts.map((acc, n) => accountCard(acc, n, pane, accounts.length));
        const add = h('button', { class: 'btn', type: 'button', on: { click: async () => {
            const name = prompt('새 텔레그램 계정의 이름 (구분용, 비워도 됨)', '');
            if (name === null) return;
            try { await post('api/tgup/account', { action: 'add', name }); toast('계정을 더했습니다. 그 카드에서 로그인하세요.', 'success'); renderAccount(pane); }
            catch (e) { toast(e.message, 'error'); }
        } } }, icon('plus'), ' 텔레그램 계정 더하기');
        const intro = h('p', { class: 'field-hint', text: '텔레그램 계정을 여러 개 넣을 수 있습니다. 규칙마다 올릴 계정을 고르고, 계정마다 따로 동시에 올립니다 '
            + '(같은 계정은 차례로, 한 계정이 요청 제한에 걸려도 다른 계정은 계속). 위의 API ID/Hash는 모든 계정이 같이 씁니다.' });
        clear(pane).append(apiCard, intro, ...cards, h('div', { class: 'toolbar' }, add));
    }

    // 계정 하나의 카드 (로그인 / 로그인된 계정 / 이름 바꾸기 / 빼기)
    function accountCard(a, n, pane, count) {
        const say = (body) => post('api/tgup/account', { ...body, account: a.id });
        const title = a.title || a.label || a.name || (n === 0 ? '첫 계정' : a.id);
        const rename = h('button', { class: 'btn btn-sm', type: 'button', title: '구분용 이름', on: { click: async () => {
            const name = prompt('이 계정의 이름 (구분용)', a.label || '');
            if (name === null) return;
            try { await say({ action: 'rename', name }); renderAccount(pane); } catch (e) { toast(e.message, 'error'); }
        } } }, icon('pen'));
        const remove = n === 0 ? null : h('button', { class: 'btn btn-sm danger', type: 'button', title: '이 계정 빼기', on: { click: async () => {
            if (!confirm(`"${title}" 계정을 뺄까요? (로그인돼 있으면 로그아웃하고 세션을 지웁니다. 이 계정으로 올리는 규칙이 있으면 못 뺍니다)`)) return;
            try { await say({ action: 'remove' }); toast('계정을 뺐습니다.', 'success'); renderAccount(pane); } catch (e) { toast(e.message, 'error', 6000); }
        } } }, icon('trash'));
        const box = h('div', { class: 'src-card tg-account' },
            h('div', { class: 'toolbar' }, h('h3', { class: 'pane-title', style: 'flex:1' }, h('i', { class: 'fa-brands fa-telegram' }),
                ` ${count > 1 ? `계정 ${n + 1}: ` : ''}${title}`), rename, remove));
        if (!a.telethon) box.appendChild(h('p', { class: 'muted error', text: '서버에 telethon이 없습니다: pip install -r requirements.txt 후 다시 시작하세요.' }));
        else if (a.authorized) {
            box.append(h('p', {}, h('span', { class: 'ok', text: `✓ ${a.name || '로그인됨'}` }), h('span', { class: 'muted', text: ` ${a.phone || ''}${a.premium ? ' · 프리미엄 (4GB까지)' : ' · 일반 계정 (2GB까지)'}` })),
                a.fast_crypto ? null : h('p', { class: 'field-hint', text: 'cryptg가 없어 올리기가 느릴 수 있습니다: pip install cryptg' }),
                h('div', { class: 'toolbar' }, h('button', { class: 'btn danger', on: { click: async () => {
                    if (!confirm('이 계정을 텔레그램에서 로그아웃할까요? (이 계정으로 올리는 규칙이 멈춥니다)')) return;
                    try { await say({ action: 'logout' }); renderAccount(pane); } catch (e) { toast(e.message, 'error'); }
                } } }, icon('right-from-bracket'), ' 로그아웃')));
        } else {
            const phone = h('input', { class: 'input', type: 'tel', value: a.phone || '', placeholder: '+821012345678' });
            const code = h('input', { class: 'input', inputmode: 'numeric', placeholder: '텔레그램 앱으로 온 숫자', autocomplete: 'one-time-code' });
            const pw = h('input', { class: 'input', type: 'password', placeholder: '2단계 인증 비밀번호', autocomplete: 'current-password' });
            const pwField = field('2단계 인증 비밀번호', pw);
            pwField.classList.add('hidden');
            const send = h('button', { class: 'btn', on: { click: async () => {
                send.disabled = true;
                try { await say({ action: 'send_code', phone: phone.value.trim() }); toast('인증 코드를 보냈습니다. 텔레그램 앱을 보세요.', 'success'); code.focus(); }
                catch (e) { toast(e.message, 'error', 6000); } finally { send.disabled = false; }
            } } }, icon('paper-plane'), ' 인증 코드 받기');
            const login = h('button', { class: 'btn btn-accent', on: { click: async () => {
                login.disabled = true;
                try {
                    const r = await say({ action: 'sign_in', code: code.value.trim(), password: pw.value });
                    if (r.password_required) { pwField.classList.remove('hidden'); pw.focus(); toast('2단계 인증 비밀번호를 넣어 주세요.'); }
                    else if (r.authorized) { toast('로그인했습니다.', 'success'); renderAccount(pane); }
                } catch (e) { toast(e.message, 'error', 6000); } finally { login.disabled = false; }
            } } }, icon('right-to-bracket'), ' 로그인');
            box.append(a.error ? h('p', { class: 'muted error', text: a.error }) : null,
                h('p', { class: 'field-hint', text: '봇이 아니라 내 계정으로 올립니다 (한 파일 2GB, 프리미엄은 4GB). 올릴 채널에 글을 쓸 수 있어야 합니다.' }),
                h('div', { class: 'tg-login' }, field('전화번호 (국가번호 포함)', phone), send),
                h('div', { class: 'tg-login' }, field('인증 코드', code), pwField, login));
        }
        return box;
    }

    // ── 파일 골라 보내기 ──
    // 폴더(rclone 드라이브) 규칙을 고르고 그 폴더 안을 돌아다니며 파일을 골라 진행 목록에 넣는다.
    // 고른 파일은 제외 정규식·자막 기다리기를 건너뛴다. 이미 올린 파일은 [다시 올리기]를 켜야 다시 올린다
    const fmtBytes = (n) => (n >= 1e9 ? `${(n / 1e9).toFixed(2)}GB` : n >= 1e6 ? `${(n / 1e6).toFixed(1)}MB` : `${Math.max(1, Math.round(n / 1e3))}KB`);
    const sendState = { rule: '', sub: '' };
    async function renderSend(pane) {
        clear(pane).appendChild(loading());
        let st;
        try { st = await api('api/tgup'); } catch (e) { clear(pane).append(h('p', { class: 'muted error', text: e.message })); return; }
        const rules = (st.settings.rules || []).filter((r) => r.kind === 'folder');
        clear(pane);
        if (!rules.length) {
            pane.append(h('p', { class: 'muted', text: '폴더(rclone 드라이브) 규칙이 없습니다. [규칙] 탭에서 rclone 드라이브 · 폴더(또는 음악) 규칙을 먼저 만들어 주세요.' }));
            return;
        }
        if (!rules.some((r) => r.id === sendState.rule)) { sendState.rule = rules[0].id; sendState.sub = ''; }
        const ruleSel = h('select', { class: 'select' }, rules.map((r) => h('option', {
            value: r.id, selected: r.id === sendState.rule,
            text: `${r.media === 'music' ? '🎵 ' : ''}${r.section_title || r.folder} → ${r.channel_title || r.channel}${r.enabled ? '' : ' (꺼짐)'}`,
        })));
        const againIn = h('input', { type: 'checkbox' });
        const sendBtn = h('button', { class: 'btn btn-accent', disabled: true }, icon('paper-plane'), ' 보내기');
        const allIn = h('input', { type: 'checkbox', title: '이 폴더의 파일 모두' });
        const listBox = h('div', { class: 'send-list' });
        const crumb = h('div', { class: 'toolbar send-crumb' });
        const picked = new Map();   // key -> 파일 이름 (폴더를 옮겨 다녀도 고른 것은 남는다)
        const syncBtn = () => {
            sendBtn.disabled = !picked.size;
            sendBtn.lastChild.textContent = picked.size ? ` 보내기 (${picked.size}개)` : ' 보내기';
        };
        async function show(sub) {
            sendState.sub = sub;
            clear(listBox).appendChild(loading());
            let d;
            try { d = await api(`api/tgup/files?${new URLSearchParams({ rule: sendState.rule, sub })}`); } catch (e) {
                clear(listBox).append(h('p', { class: 'muted error', text: e.message }));
                if (sub) listBox.append(h('button', { class: 'btn btn-sm', on: { click: () => show('') } }, icon('arrow-up'), ' 규칙 폴더로'));
                return;
            }
            // 위치: 규칙 폴더 / 하위 / 폴더
            const parts = sub ? sub.split('/') : [];
            clear(crumb).append(h('button', { class: 'btn btn-sm', on: { click: () => show('') } }, icon('folder'), ` ${d.folder}`),
                ...parts.map((p, i) => [h('span', { class: 'muted', text: '/' }),
                    h('button', { class: 'btn btn-sm', on: { click: () => show(parts.slice(0, i + 1).join('/')) } }, p)]).flat());
            clear(listBox);
            if (sub) listBox.append(h('button', { class: 'send-row send-dir', type: 'button', on: { click: () => show(parts.slice(0, -1).join('/')) } },
                icon('arrow-up'), h('span', { text: '위로' })));
            d.dirs.forEach((n) => listBox.append(h('button', { class: 'send-row send-dir', type: 'button', on: { click: () => show(sub ? `${sub}/${n}` : n) } },
                icon('folder'), h('span', { text: n }))));
            const boxes = [];
            d.files.forEach((f) => {
                const c = h('input', { type: 'checkbox', checked: picked.has(f.key) });
                c.addEventListener('change', () => { if (c.checked) picked.set(f.key, f.name); else picked.delete(f.key); syncBtn(); });
                boxes.push([c, f]);
                listBox.append(h('label', { class: 'send-row send-file' }, c, icon(d.music ? 'music' : 'film'), h('span', { class: 'send-name', text: f.name }),
                    f.queued ? h('span', { class: 'chip', text: '진행 목록에 있음' }) : f.sent ? h('span', { class: 'chip chip-ok', text: '올림' }) : null,
                    h('span', { class: 'muted', text: fmtBytes(f.size) })));
            });
            allIn.checked = !!boxes.length && boxes.every(([c]) => c.checked);
            allIn.disabled = !boxes.length;
            allIn.onchange = () => {
                boxes.forEach(([c, f]) => { c.checked = allIn.checked; if (allIn.checked) picked.set(f.key, f.name); else picked.delete(f.key); });
                syncBtn();
            };
            if (!d.dirs.length && !d.files.length) listBox.append(h('p', { class: 'muted', text: d.music ? '음악 파일이 없습니다.' : '동영상 파일이 없습니다.' }));
        }
        ruleSel.addEventListener('change', () => { sendState.rule = ruleSel.value; picked.clear(); syncBtn(); show(''); });
        sendBtn.addEventListener('click', async () => {
            sendBtn.disabled = true;
            try {
                const r = await post('api/tgup/send', { rule: sendState.rule, keys: [...picked.keys()], again: againIn.checked });
                toast(r.count ? `${r.count}개를 진행 목록에 넣었습니다.` : '이미 진행 목록에 있습니다.', 'success');
                picked.clear();
                showTab('status');
            } catch (e) { toast(e.message, 'error', 6000); syncBtn(); }
        });
        pane.append(h('div', { class: 'mirror-rule' },
            field('규칙 (올릴 폴더 → 텔레그램 채널)', ruleSel),
            crumb,
            h('div', { class: 'toolbar' }, h('label', { class: 'check' }, allIn, ' 이 폴더의 파일 모두'),
                h('label', { class: 'check', title: '같은 파일·파일 이름·회차를 이미 올렸어도 다시 올립니다' }, againIn, ' 이미 올린 파일도 다시 올리기'),
                sendBtn),
            listBox,
            h('p', { class: 'field-hint', text: '폴더를 옮겨 다니며 여러 폴더의 파일을 함께 고를 수 있습니다. 고른 파일은 진행 목록 끝에 들어가고, 제외 정규식·자막 기다리기는 건너뜁니다 (나머지 처리 - 인코딩·자막 입히기·나누기, 음악은 태그 캡션 - 는 규칙대로).' })));
        show(sendState.rule === ruleSel.value ? sendState.sub : '');
    }

    // ── 폴더 고르기 ──
    function pickFolder(input) {
        const body = h('div', { class: 'folder-pick' });
        const useBtn = h('button', { class: 'btn btn-accent' }, icon('check'), ' 이 폴더로');
        const m = modal('폴더 고르기', body, [useBtn]);
        let current = '';
        useBtn.addEventListener('click', () => { if (current) { input.value = current; m.close(); } });
        const entry = (ic, text, sub, go) => h('button', { class: 'folder-pick-item', type: 'button', on: { click: go } },
            icon(ic), h('span', { text }), sub ? h('span', { class: 'muted', text: ` ${sub}` }) : null);
        async function show(path) {
            current = path;
            useBtn.disabled = !path;
            clear(body).appendChild(loading());
            let d;
            try { d = await api(`api/tgup/folders?path=${encodeURIComponent(path)}`); } catch (e) {
                clear(body).append(h('p', { class: 'muted error', text: e.message }), entry('arrow-up', '위로', '', () => show(folderParent(path))));
                return;
            }
            clear(body);
            if (!path) {
                body.append(h('p', { class: 'field-hint', text: d.mounts.length || d.remotes.length
                    ? 'rclone 드라이브를 고른 뒤 올릴 하위 폴더로 들어가 [이 폴더로]를 누르세요.' : (d.note || 'rclone 드라이브를 찾지 못했습니다.') }),
                ...d.mounts.map((x) => entry('hard-drive', x.path, `rclone ${x.remote}`, () => show(x.path))),
                ...d.remotes.map((x) => entry('cloud', x, 'rclone 원격', () => show(x))),
                entry('folder', '/mnt', '이 컴퓨터', () => show('/mnt')), entry('folder', '/', '이 컴퓨터', () => show('/')));
                return;
            }
            body.append(h('p', { class: 'folder-pick-path', text: path }), entry('arrow-up', '위로', '', () => show(folderParent(path))),
                ...d.dirs.map((n) => entry('folder', n, '', () => show(folderJoin(path, n)))));
            if (!d.dirs.length) body.append(h('p', { class: 'muted', text: '하위 폴더가 없습니다.' }));
        }
        show(input.value.trim());
    }

    // ── 규칙 ──
    async function renderRules(pane) {
        clear(pane).appendChild(loading());
        let data, opts;
        try { [data, opts] = await Promise.all([api('api/tgup'), api('api/tgup/options')]); }
        catch (e) { clear(pane).appendChild(h('p', { class: 'muted error', text: e.message })); return; }
        const st = data.settings;
        const channelsP = {};   // 계정 id -> 채널 목록 (한 번 받은 것은 기억)
        const loadChannels = (acc) => (channelsP[acc] = channelsP[acc]
            || api(`api/tgup/channels?account=${encodeURIComponent(acc)}`).then((r) => r.channels).catch((e) => { delete channelsP[acc]; throw e; }));
        const intervalIn = h('input', { class: 'input', type: 'number', min: '2', max: '1440', value: String(st.interval) });
        const hw = opts.encoders || {};
        const encSel = h('select', { class: 'select' }, [['auto', `자동 (${['nvenc', 'qsv', 'vaapi'].filter((n) => hw[n]).map((n) => ({ nvenc: 'NVIDIA', qsv: 'Intel Quick Sync', vaapi: 'VAAPI' })[n])[0] || '그래픽 인코더 없음 - CPU'})`],
            ['cpu', 'CPU (libx264)'], ['nvenc', `NVIDIA NVENC${hw.nvenc ? '' : ' (안 됨)'}`], ['qsv', `Intel Quick Sync${hw.qsv ? '' : ' (안 됨)'}`],
            ['vaapi', `VAAPI (Intel·AMD)${hw.vaapi ? '' : ' (안 됨)'}`]].map(([v, t]) => h('option', { value: v, text: t, selected: (st.encoder || 'auto') === v })));
        const hoursSel = h('select', { class: 'select' }, [['', '언제나'], ['1-7', '새벽 1시~7시'], ['0-8', '밤 12시~아침 8시'], ['22-7', '밤 10시~아침 7시'], ['9-18', '낮 9시~6시']].map(([v, t]) =>
            h('option', { value: v, text: t, selected: (st.hours || '') === v })));
        const presetSel = h('select', { class: 'select' }, [['veryfast', '보통 (veryfast)'], ['superfast', '빠르게 (superfast)'], ['ultrafast', '가장 빠르게 (ultrafast, 파일이 큼)']].map(([v, t]) =>
            h('option', { value: v, text: t, selected: (st.cpu_preset || 'superfast') === v })));
        const slotsSel = h('select', { class: 'select' }, [1, 2, 3, 4].map((v) => h('option', { value: String(v), text: `${v}개${v === 1 ? ' (기본)' : ''}`, selected: (st.encode_slots || 1) === v })));
        const excludeIn = h('textarea', { class: 'input', rows: '3', placeholder: 'S101\nS201', spellcheck: false });
        excludeIn.value = (st.exclude || []).join('\n');
        const maxSel = h('select', { class: 'select' }, [[0, '자동 (프리미엄 계정이면 4GB, 아니면 2GB)'], [2, '2GB로 고정 (일반 계정)'], [4, '4GB로 고정 (텔레그램 프리미엄)']].map(([v, t]) =>
            h('option', { value: String(v), text: t, selected: st.max_gb === v })));
        const rulesBox = h('div', { class: 'mirror-rules' });
        const rows = [];
        const opt = (v, t, sel, name) => h('option', { value: v, text: t, selected: sel, dataset: { name: name || t } });

        const addRule = (r = {}) => {
            const enabledIn = h('input', { type: 'checkbox', checked: r.enabled !== false });
            const isMusic = r.media === 'music';
            const kindSel = h('select', { class: 'select' }, opt('plex', 'Plex 라이브러리', r.kind !== 'folder' && !!opts.plex.length),
                opt('folder', 'rclone 드라이브 · 폴더', (r.kind === 'folder' && !isMusic) || (!opts.plex.length && !isMusic)),
                opt('music', '음악 (rclone 드라이브 · 폴더)', isMusic));
            // 음악 규칙: 처음 켤 때 폴더에 이미 있는 곡도 올릴지
            const existIn = h('input', { type: 'checkbox', checked: !!r.upload_existing });
            const folderIn = h('input', { class: 'input', placeholder: '/mnt/gdrive/영화 또는 gdrive:영화', value: r.folder || '' });
            const pickBtn = h('button', { class: 'btn', type: 'button', on: { click: () => pickFolder(folderIn) } }, icon('folder-open'), ' 고르기');
            const heightSel = h('select', { class: 'select' }, [[720, '720p'], [480, '480p'], [1080, '1080p'], [0, '원본 그대로']].map(([v, t]) =>
                h('option', { value: String(v), text: t, selected: (r.height ?? 720) === v })));
            const plexSel = h('select', { class: 'select' }, opt('', 'Plex 라이브러리 고르기', !r.section),
                ...opts.plex.flatMap((p) => p.sections.map((sec) => opt(`${p.id}|${sec.key}`, `${sec.title} (${sec.type === 'show' ? 'TV' : '영화'})`,
                    r.plex === p.id && r.section === sec.key, sec.title))));
            const chSel = h('select', { class: 'select' }, r.channel ? opt(r.channel, r.channel_title || r.channel, true) : opt('', '채널 고르기', true));
            // 올릴 텔레그램 계정 (로그인한 계정들 - 규칙의 계정이 지금 로그인 안 돼 있어도 그대로 보여 준다)
            const accIds = opts.telegram.map((t) => t.id);
            const accSel = h('select', { class: 'select' }, ...opts.telegram.map((t) => opt(t.id, t.name, (r.tg || 'tg') === t.id)),
                ...(r.tg && !accIds.includes(r.tg) ? [opt(r.tg, `${r.tg} (로그인 안 됨)`, true)] : []));
            const waitIn = h('input', { type: 'checkbox', checked: r.wait_subs !== false });
            const burnIn = h('input', { type: 'checkbox', checked: r.burn_subs !== false });
            const minIn = h('input', { class: 'input mirror-days', type: 'number', min: '0', max: '525600', step: '10',
                value: String(r.wait_min ?? (r.wait_hours !== undefined ? r.wait_hours * 60 : 720)) });
            // 같이 올릴 다른 계정 (놀고 있는 계정이 가져가고, 한 계정에 문제가 생기면 다른 계정이 이어 올림)
            const altBox = h('div', { class: 'toolbar mirror-alt' });
            const altChecks = {};
            const fillAlt = () => {
                const main = accSel.value || r.tg || 'tg';
                const keep = new Set(Object.entries(altChecks).filter(([, c]) => c.checked).map(([k]) => k));
                if (!Object.keys(altChecks).length) (r.tg_alt || []).forEach((a) => keep.add(a));
                clear(altBox);
                Object.keys(altChecks).forEach((k) => delete altChecks[k]);
                const ids = [...new Set([...opts.telegram.map((t) => t.id), ...(r.tg_alt || [])])].filter((id) => id !== main);
                if (!ids.length) { altBox.append(h('span', { class: 'muted', text: '다른 텔레그램 계정이 없습니다 (텔레그램 계정 탭에서 더할 수 있음).' })); return; }
                for (const id of ids) {
                    const t = opts.telegram.find((x) => x.id === id);
                    const c = h('input', { type: 'checkbox', checked: keep.has(id) });
                    altChecks[id] = c;
                    altBox.append(h('label', { class: 'check' }, c, ` ${t ? t.name : `${id} (로그인 안 됨)`}`));
                }
            };
            const capIn = h('textarea', { class: 'input', rows: '3', placeholder: '{name}\n\n{summary}' });
            capIn.value = r.caption || '{name}\n\n{summary}';
            const fillChannels = async () => {
                const keep = chSel.value;
                try {
                    const list = await loadChannels(accSel.value || 'tg');
                    clear(chSel).append(opt('', '채널 고르기', !keep),
                        ...list.map((c) => opt(String(c.id), `${c.title}${c.kind === 'group' ? ' (그룹)' : ''}`, String(c.id) === keep, c.title)));
                } catch (e) { toast(`텔레그램 채널 목록을 못 받았습니다: ${e.message}`, 'error'); }
            };
            chSel.addEventListener('focus', fillChannels, { once: true });
            accSel.addEventListener('change', () => { clear(chSel).append(opt('', '채널 고르기', true)); fillChannels(); fillAlt(); });
            fillAlt();
            const test = h('button', { class: 'btn btn-sm', title: '저장한 뒤에 쓰세요', on: { click: async () => {
                try { const t = await post('api/tgup/test', { rule: row.id }); toast(`"${t.title}"을(를) 올리기 시작합니다. 진행 상태에서 보세요.`); }
                catch (e) { toast(e.message, 'error', 6000); }
            } } }, icon('paper-plane'), ' 가장 최근 것 하나 올려 보기');
            const del = h('button', { class: 'btn btn-sm', on: { click: () => { rows.splice(rows.indexOf(row), 1); card.remove(); } } }, icon('trash'), ' 지우기');
            const plexField = field('Plex 라이브러리', plexSel);
            const folderField = field('폴더', h('div', { class: 'toolbar mirror-folder-row' }, folderIn, pickBtn),
                '[고르기]에서 rclone 드라이브를 고르거나, rclone mount로 붙인 폴더(/로 시작) 또는 rclone 원격 "이름:경로"를 적으세요. 하위 폴더까지 봅니다.'
                + (opts.rclone_note ? ` (${opts.rclone_note})` : ''));
            const encText = h('span', { class: 'muted' });
            const burnText = h('span', {});
            const musicNote = h('p', { class: 'muted', text: '음악 파일(mp3·flac·m4a·ogg·opus 등)을 그대로 올립니다 (인코딩 없음). 캡션은 파일 안의 태그'
                + '(없으면 "아티스트/앨범 (연도)/01 곡" 폴더 이름)로 곡 제목·아티스트·앨범·트랙·디스크·장르·작곡·작사·편곡·앨범ID를 "이름: 값" 줄로 적고 '
                + '(YMPlayer 텔레그램 음악 채널이 읽음), 텔레그램 오디오 정보와 앨범 아트(파일 안 그림 또는 cover.jpg)도 붙입니다. '
                + '같은 이름의 가사(.lrc)가 있으면 곡 뒤에 파일로 올리고, 앨범 폴더별·파일 이름 순서(트랙 순)로 올립니다.' });
            const existRow = h('label', { class: 'check' }, existIn, ' 처음 켤 때 폴더에 이미 있는 곡도 올리기 (끄면 켠 뒤 새로 생긴 곡만)');
            const videoOnly = [];
            const syncKind = () => {
                const music = kindSel.value === 'music';
                const folder = kindSel.value === 'folder' || music;
                videoOnly.forEach((el) => el.classList.toggle('hidden', music));
                musicNote.classList.toggle('hidden', !music);
                existRow.classList.toggle('hidden', !music);
                plexField.classList.toggle('hidden', folder);
                folderField.classList.toggle('hidden', !folder);
                encText.textContent = folder ? '보다 높은 영상은 용량과 상관없이 줄여서, 텔레그램에서 바로 재생되는 H.264/AAC mp4로 올림 (이미 그 모양이면 그대로)'
                    : '보다 높은 영상은 용량과 상관없이 줄여서 H.264 mp4로 다시 인코딩해 올림';
                burnText.textContent = folder ? ' 자막 파일(SRT 등)이나 파일 안의 자막을 화면에 입혀 인코딩 (텔레그램 앱에서도 자막이 보임)'
                    : ' 영상 안에 자막이 없으면 외부 자막을 화면에 입혀 다시 인코딩 (텔레그램 앱에서도 자막이 보임)';
            };
            kindSel.addEventListener('change', syncKind);
            const heightRow = h('div', { class: 'mirror-wait' }, h('span', { class: 'muted', text: '화질:' }), heightSel, encText);
            const waitRow = h('div', { class: 'mirror-wait' }, h('label', { class: 'check' }, waitIn, ' 자막이 생길 때까지 기다렸다가 올리기'),
                h('span', { class: 'muted', text: ' 최대' }), minIn, h('span', { class: 'muted', text: '분 (0이면 계속 기다림. 파일 안에 자막(소프트 자막)이 있으면 기다리지 않고 바로. 하드섭은 진행 상태에서 [지금 올리기])' }));
            const burnRow = h('label', { class: 'check', title: '다시 인코딩하느라 시간이 걸립니다.' }, burnIn, burnText);
            const capRow = field('캡션', capIn, '{name} 제목(영화 "제목 (연도)", 에피소드 "작품 S01E02 - 제목") · {summary} 줄거리 · {title} {year} {show} {season} {episode} {code} {genres} {tags}(#장르) {library} {filename}');
            videoOnly.push(heightRow, waitRow, burnRow, capRow);
            const card = h('div', { class: 'mirror-rule' },
                h('div', { class: 'toolbar' }, h('label', { class: 'check' }, enabledIn, ' 켜기'), kindSel),
                h('div', { class: 'row-2 mirror-pick' }, plexField, folderField, field('올릴 텔레그램 계정 · 채널', h('div', { class: 'toolbar' }, opts.telegram.length > 1 || (r.tg && r.tg !== 'tg') ? accSel : null, chSel))),
                musicNote, existRow, heightRow,
                field('같이 올릴 다른 계정', altBox, '고른 계정도 이 채널에 글을 쓸 수 있어야 합니다. 놀고 있는 계정이 진행 목록 앞에서부터 가져가고, '
                    + '한 계정에 문제(로그아웃·세션 만료·채널 권한·요청 제한·연결 끊김)가 생기면 다른 계정이 이어 올립니다.'),
                waitRow, burnRow, capRow,
                h('div', { class: 'toolbar' }, test, del));
            syncKind();
            const row = { id: r.id, get: () => {
                const [plex, section] = plexSel.value.split('|');
                return { id: row.id, enabled: enabledIn.checked, kind: kindSel.value, folder: folderIn.value.trim(),
                    height: Number(heightSel.value), plex, section, section_title: ((plexSel.selectedOptions[0] || {}).dataset || {}).name || '',
                    tg: accSel.value || r.tg || 'tg', channel: chSel.value, channel_title: ((chSel.selectedOptions[0] || {}).dataset || {}).name || '', caption: capIn.value,
                    wait_subs: waitIn.checked, wait_min: Math.max(0, Math.round(Number(minIn.value) || 0)), burn_subs: burnIn.checked,
                    tg_alt: Object.entries(altChecks).filter(([, c]) => c.checked).map(([k]) => k), upload_existing: existIn.checked };
            } };
            rows.push(row);
            rulesBox.appendChild(card);
            if (r.channel && opts.telegram.length) fillChannels();
        };
        st.rules.forEach(addRule);

        const save = h('button', { class: 'btn btn-accent' }, icon('check'), ' 저장');
        save.addEventListener('click', async () => {
            save.disabled = true;
            try {
                const r = await post('api/tgup/settings', { interval: Number(intervalIn.value), max_gb: Number(maxSel.value), max_gb_v: 1, encoder: encSel.value,
                    cpu_preset: presetSel.value, hours: hoursSel.value, encode_slots: Number(slotsSel.value),
                    exclude: excludeIn.value.split('\n').map((x) => x.trim()).filter(Boolean), rules: rows.map((x) => x.get()) });
                r.settings.rules.forEach((x, i) => { if (rows[i]) rows[i].id = x.id; });
                toast('저장했습니다. 새 규칙은 지금 있는 것 다음부터 올립니다.', 'success', 5000);
            } catch (e) { toast(e.message, 'error', 6000); } finally { save.disabled = false; }
        });
        const warn = [];
        if (!opts.telegram.length) warn.push(h('p', { class: 'muted error' }, '텔레그램 계정에 로그인해야 올릴 수 있습니다 → ',
            h('a', { href: '#account', on: { click: (e) => { e.preventDefault(); showTab('account'); } } }, '텔레그램 계정')));
        if (!opts.plex.length) warn.push(h('p', { class: 'field-hint', text: 'Plex 규칙을 쓰려면 .env에 PLEX_URL과 PLEX_TOKEN을 넣고 다시 시작하세요 (드라이브 감시의 Plex 설정과 같은 값). rclone 드라이브 · 폴더 규칙은 그대로 쓸 수 있습니다.' }));
        opts.plex.filter((p) => p.error).forEach((p) => warn.push(h('p', { class: 'muted error', text: p.error })));
        if (!data.ffmpeg) warn.push(h('p', { class: 'muted error', text: '서버에 ffmpeg/ffprobe가 없습니다 - 인코딩·나눠 올리기를 못 합니다 (sudo apt install ffmpeg).' }));
        // 디스코드 알림 (올림·실패·건너뜀) - 서버: tgup/notify.py
        const nt = data.notify || {};
        const hookIn = h('input', { class: 'input', value: nt.webhook || '', placeholder: 'https://discord.com/api/webhooks/…', autocomplete: 'off' });
        const botIn = h('input', { class: 'input', type: 'password', placeholder: nt.has_bot_token ? '저장됨 (바꿀 때만 입력)' : '봇 토큰 (웹훅 대신 쓸 때)', autocomplete: 'off' });
        const chIn = h('input', { class: 'input', inputmode: 'numeric', value: nt.channel_id || '', placeholder: '채널 ID' });
        const okIn = h('input', { type: 'checkbox', checked: nt.ok !== false });
        const failIn = h('input', { type: 'checkbox', checked: nt.fail !== false });
        const skipIn = h('input', { type: 'checkbox', checked: !!nt.skip });
        const notifyBody = (action) => ({ action, webhook: hookIn.value.trim(), bot_token: botIn.value.trim(), channel_id: chIn.value.trim(),
            ok: okIn.checked, fail: failIn.checked, skip: skipIn.checked });
        const notifyBtn = (action, label, ic, cls) => h('button', { class: `btn ${cls || ''}`, on: { click: async (e) => {
            const btn = e.currentTarget; btn.disabled = true;
            try { await post('api/tgup/notify', notifyBody(action)); toast(action === 'test' ? '시험 알림을 보냈습니다. 디스코드를 보세요.' : '알림 설정을 저장했습니다.', 'success'); }
            catch (err) { toast(err.message, 'error', 6000); } finally { btn.disabled = false; }
        } } }, icon(ic), label);
        const notifyCard = h('div', { class: 'src-card' },
            h('h3', { class: 'pane-title' }, h('i', { class: 'fa-brands fa-discord' }), ' 디스코드 알림'),
            h('p', { class: 'field-hint', text: '올리기가 끝나거나 실패하면 디스코드로 알립니다. 디스코드 채널 설정 > 연동 > 웹후크에서 만든 주소를 넣거나, 봇 토큰과 채널 ID를 넣으세요 (둘 다 있으면 웹훅).' }),
            field('웹훅 주소', hookIn),
            h('div', { class: 'row-2' }, field('봇 토큰', botIn), field('채널 ID', chIn)),
            h('div', { class: 'toolbar' }, h('span', { class: 'muted', text: '알릴 것:' }), h('label', { class: 'check' }, okIn, ' 올림'),
                h('label', { class: 'check' }, failIn, ' 실패'), h('label', { class: 'check' }, skipIn, ' 건너뜀 (이미 올린 파일·너무 큰 파일 등)')),
            h('div', { class: 'toolbar' }, notifyBtn('save', ' 알림 저장', 'check', 'btn-accent'), notifyBtn('test', ' 시험 알림 보내기', 'paper-plane')));
        clear(pane).append(h('div', { class: 'src-card' },
            h('p', { text: '고른 Plex 라이브러리에 새 동영상(영화·에피소드)이 들어오거나, 고른 rclone 드라이브 폴더에 새 동영상이 올라오면 '
                + '로그인해 둔 텔레그램 계정으로 고른 채널에 올립니다. 규칙을 처음 저장할 때 이미 있던 것은 올리지 않고 그 뒤에 들어온 것부터 올립니다. '
                + '텔레그램 앱에서 바로 재생되는 mp4(H.264/AAC)로 올리고, 한도를 넘는 파일은 "이름_0000.mp4", "이름_0001.mp4"…로 나눠 올립니다. '
                + '네트워크 드라이브의 원본은 이 서버로 먼저 복사(자막 파일도 같이)한 뒤 인코딩합니다.' }),
            ...warn,
            h('div', { class: 'row-2' }, field('확인 간격 (분)', intervalIn, '2~1440'), field('파일 크기 한도', maxSel, '넘는 파일은 같은 길이로 나눠 올립니다 (ffmpeg 필요).')),
            h('div', { class: 'row-2' }, field('인코더', encSel, '그래픽 카드로 인코딩하면 CPU보다 몇 배 빠릅니다. 자동은 이 서버에서 실제로 되는 것을 골라 쓰고, 실패하면 CPU로 다시 합니다.'),
                field('CPU 인코딩 빠르기', presetSel, 'CPU로 할 때만. 빠를수록 같은 화질에 파일이 조금 커집니다.')),
            h('div', { class: 'row-2' }, field('올리기 시간대', hoursSel, '받기·인코딩·올리기를 이 시간에만 합니다. 새 항목 찾기는 늘 하고, 쌓아 두었다가 이 시간에 올립니다.'),
                field('동시 인코딩 개수', slotsSel, '계정이 여럿이면 올리기는 계정마다 동시에 하지만, 인코딩은 CPU·그래픽 카드를 많이 써서 이만큼만 동시에 합니다. 나머지는 "인코딩 차례 기다리는 중".')),
            field('제외할 파일 (정규식, 한 줄에 하나)', excludeIn, '파일 이름·제목·경로에 맞으면 올리지 않고 최근 기록에 "제외"로 남깁니다. 예: S101, S201, Featurettes 폴더 아래는 (?i)(^|[\\\\/])featurettes[\\\\/] (대소문자 무시는 (?i)를 앞에).'),
            rulesBox,
            h('div', { class: 'toolbar' }, h('button', { class: 'btn', on: { click: () => addRule() } }, icon('plus'), ' 규칙 추가'), save),
            h('p', { class: 'field-hint', text: '올리려면 그 채널에 글을 쓸 수 있어야 합니다(채널 관리자). Plex 서버의 파일 경로가 이 컴퓨터에서 보이면(PLEX_PATH_MAP으로 바꿈) 그대로 쓰고, '
                + '아니면 Plex에서 data/tgup의 임시 폴더로 받은 뒤 올리고 지웁니다(파일 크기만큼 빈 공간 필요).' })), notifyCard);
    }

    // ── 진행 상태 ──
    const fmtB = (n) => (n >= 1024 ** 3 ? `${(n / 1024 ** 3).toFixed(2)}GB` : `${Math.round(n / 1024 ** 2)}MB`);
    let statusTimer = 0;
    let statusFilter = 'all';   // 진행 상태: 전체 / 계정 id
    try { statusFilter = localStorage.getItem('tgup_status_filter') || 'all'; } catch (e) { /* 저장소를 못 쓰는 브라우저 */ }
    // 걸린 시간 "1시간 2분" / "3분 5초" / "40초"
    const fmtDur = (sec) => {
        sec = Math.max(0, Math.round(sec || 0));
        const hh = Math.floor(sec / 3600), mm = Math.floor((sec % 3600) / 60), ss = sec % 60;
        return hh ? `${hh}시간 ${mm}분` : mm ? `${mm}분 ${ss}초` : `${ss}초`;
    };
    // 단계별 시간 {받기, 인코딩, 나누기, 올리기, 대기} -> "받기 2분 · 인코딩 10분 · 올리기 3분"
    const fmtTimes = (t) => ['준비', '받기', '인코딩', '나누기', '올리기', '대기'].filter((k) => t && t[k] >= 1).map((k) => `${k} ${fmtDur(t[k])}`).join(' · ');
    // 취소·건너뛴 항목 다시 올리기 (최근 7일 / 30일 / 전체) - 이미 올린 같은 파일·같은 회차는 빼고 까닭을 보여 줌
    function againBox(s, pane) {
        if (!s.skipped) return null;
        const daysSel = h('select', { class: 'select' }, [['7', '최근 7일'], ['30', '최근 30일'], ['0', '전체']].map(([v, t]) => h('option', { value: v, text: t })));
        const go = h('button', { class: 'btn btn-sm', type: 'button' }, icon('rotate-left'), ' 다시 올리기');
        go.addEventListener('click', async () => {
            go.disabled = true;
            try {
                const r = await post('api/tgup/requeue', { days: Number(daysSel.value) });
                toast(`${r.queued.length}개를 다시 올릴 차례에 넣었습니다${r.excluded.length ? ` (${r.excluded.length}개는 이미 올라가 있어 뺌)` : ''}.`, 'success', 6000);
                if (r.excluded.length) {
                    modal('다시 올리지 않은 것', h('div', {}, r.excluded.slice(0, 200).map((x) => h('div', {}, h('b', { text: x.title }), h('span', { class: 'muted', text: ` - ${x.reason}` })))));
                }
            } catch (e) { toast(e.message, 'error'); } finally { go.disabled = false; }
            renderStatus(pane);
        });
        return h('div', { class: 'mirror-wait' }, h('span', { class: 'muted', text: `취소·건너뛴 항목 ${s.skipped}개:` }), daysSel, go,
            h('span', { class: 'muted', text: '이미 올린 같은 회차는 빼고 바로 올릴 차례에 넣습니다.' }));
    }

    async function renderStatus(pane) {
        clearTimeout(statusTimer);
        if (!pane.firstChild) pane.appendChild(loading());
        let s, d;
        try { d = await api('api/tgup'); s = d.status; } catch (e) { clear(pane).appendChild(h('p', { class: 'muted error', text: e.message })); return; }
        const cur = s.current;
        const now = Date.now() / 1000;
        const when = (t) => (t ? new Date(t * 1000).toLocaleString([], { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '');
        const chip = (cls, text) => h('span', { class: `mirror-chip ${cls}`, text });
        const row = (title, status, subs, note, extra = null) => h('div', { class: 'mirror-row', role: 'row' },
            h('span', { class: 'mirror-title', title, text: title }), h('span', {}, status, extra), h('span', { class: 'mirror-subs' }, subs),
            h('span', { class: 'mirror-note muted', title: note, text: note }));
        const head = () => h('div', { class: 'mirror-row mirror-head', role: 'row' },
            h('span', { text: '제목' }), h('span', { text: '상태' }), h('span', { text: '자막' }), h('span', { text: '비고' }));
        const waitKeys = new Map((s.waiting || []).map((w) => [`${w.rule}/${w.key}`, w]));
        // 자막 칸: 자막 파일 없음 / 소프트 자막(영상 안) / 자막 파일 있음 / 화면에 입힘 (서버 값 "없음"·"파일 N개"·"소프트 자막"·"화면에 입힘"·"옮기지 못함")
        const subsTag = (raw) => {
            const v = String(raw || '');
            if (!v || v === '-') return v;
            const m = v.match(/^파일 (\d+)개$/);
            const [cls, text, tip] = m ? ['file', `자막 파일 ${m[1]}개`, '자막 파일 있음 - 영상과 함께 올림']
                : v === '없음' ? ['none', '자막 파일 없음', '자막 파일도, 영상 안의 자막(소프트 자막)도 없음']
                    : v === '소프트 자막' ? ['soft', '소프트 자막', '영상 파일 안에 자막 트랙이 들어 있음']
                        : v === '화면에 입힘' ? ['burn', '화면에 입힘', '자막을 영상에 입혀 인코딩함']
                            : v === '옮기지 못함' ? ['lost', '자막 옮기지 못함', '영상 안의 자막(소프트 자막)을 텔레그램용으로 옮기지 못함']
                                : ['other', v, ''];
            return h('span', { class: `subs-tag subs-${cls}`, title: tip, text });
        };
        const act = (w, action, label, ask, extra = {}) => h('button', { class: `btn btn-sm${action === 'cancel' ? ' danger' : ''}`, title: extra.title, on: { click: async (e) => {
            if (ask && !confirm(ask)) return;
            e.currentTarget.disabled = true;
            try {
                await post('api/tgup/item', { rule: w.rule, key: w.key, action, ...extra.body });
                if (action !== 'move') toast(action === 'upload' ? `"${w.title}"을(를) 지금 올립니다.` : action === 'cancel' ? `"${w.title}"을(를) 취소했습니다.` : `"${w.title}"을(를) 뺐습니다.`);
            } catch (err) { toast(err.message, 'error'); }
            renderStatus(pane);
        } } }, label);
        const cancelBtn = (w, running) => act(w, 'cancel', '취소', running ? `지금 올리는 "${w.title}"을(를) 멈추고 취소할까요? (다시 올리지 않음)` : null);
        const accList = d.accounts || [];
        const accName = (id) => (accList.find((x) => x.id === id) || {}).title || id;
        const many = accList.length > 1 || Object.keys(s.accounts || {}).length > 1;
        // 계정 탭 (전체 / 계정마다) - 실제 처리는 계정마다 따로 도는 줄이라 계정별로 볼 수 있게
        const accIds = [...new Set([...accList.map((a) => a.id), ...Object.keys(s.accounts || {}).filter(Boolean)])];
        if (statusFilter !== 'all' && !accIds.includes(statusFilter)) statusFilter = 'all';
        const show = (tgs) => statusFilter === 'all' || (tgs || []).includes(statusFilter);
        // 계정 고르기 (그 항목을 올릴 계정을 직접) - 규칙대로면 놀고 있는 계정이 가져간다
        const assignSel = (q) => {
            if (accIds.length < 2) return null;
            const sel = h('select', { class: 'select select-sm', title: '올릴 계정 고르기 (계정에 문제가 있을 때 다른 계정으로)' },
                h('option', { value: '', text: '계정: 자동', selected: !q.pin }),
                ...accIds.map((id) => h('option', { value: id, text: `계정: ${accName(id)}`, selected: q.pin === id })));
            sel.addEventListener('change', async () => {
                try { await post('api/tgup/item', { rule: q.rule, key: q.key, action: 'assign', account: sel.value }); toast(sel.value ? `"${q.title}"을(를) ${accName(sel.value)} 계정으로 올립니다.` : '규칙대로(놀고 있는 계정) 올립니다.'); }
                catch (err) { toast(err.message, 'error'); }
                renderStatus(pane);
            });
            return sel;
        };
        const live = [];
        const shown = new Set();
        const lanes = s.lanes || (cur ? [{ tg: 'tg', current: cur }] : []);
        for (const l of lanes) {
            const c = l.current;
            if (!c) continue;
            shown.add(`${c.rule}/${c.key}`);
            if (!show([l.tg])) continue;
            const pct = c.total ? Math.min(100, (c.done / c.total) * 100) : 0;
            const flood = l.flood_until && /요청 제한/.test(c.phase || '');
            const r = row(c.title, chip(flood ? 'wait' : 'run', flood ? '계정 대기' : '올리는 중'), c.subs ? subsTag(c.subs) : '확인 중',
                [many ? `[${accName(l.tg)}]` : '', `${c.phase}${c.speed && /인코딩/.test(c.phase) ? ` · ${c.speed}` : ''}${c.total && /올리는|받는|복사/.test(c.phase) ? ` · ${fmtB(c.done)} / ${fmtB(c.total)}` : ''}`,
                    c.elapsed ? `시작 ${when(c.started)} · ${fmtDur(c.elapsed)} 지남` : '', fmtTimes(c.times)].filter(Boolean).join(' · '),
                h('div', { class: 'cache-bar mirror-bar' }, h('div', { style: { width: `${pct}%` } })));
            if (c.rule) r.lastChild.append(h('span', { class: 'mirror-actions' }, cancelBtn({ rule: c.rule, key: c.key, title: c.title }, true)));
            live.push(r);
        }
        let n = 0;
        for (const q of s.queue) {
            const k = `${q.rule}/${q.key}`;
            if (shown.has(k) || waitKeys.has(k)) continue;
            shown.add(k);
            n += 1;
            if (!show(q.tgs || [q.tg])) continue;
            const who = q.pin ? `${accName(q.pin)} (직접 고름)` : (q.tgs || [q.tg]).map(accName).join(' / ');
            const r = row(`${n}. ${q.title}`, chip('queue', '올릴 차례'), '확인 전',
                [many ? who : '', q.avoid && q.avoid.length ? `${q.avoid.map(accName).join(', ')}에서 문제 - 다른 계정이 이어 올림` : '',
                    q.added ? `${fmtDur(now - q.added)} 기다림` : ''].filter(Boolean).join(' · '));
            r.lastChild.append(h('span', { class: 'mirror-actions' },
                act(q, 'move', '⤒', null, { title: '맨 앞으로', body: { where: 'top' } }),
                act(q, 'move', '↑', null, { title: '위로', body: { where: 'up' } }),
                act(q, 'move', '↓', null, { title: '아래로', body: { where: 'down' } }),
                assignSel(q), cancelBtn(q)));
            live.push(r);
        }
        for (const [k, w] of waitKeys) {
            if (shown.has(k)) continue;
            const ruleTg = ((d.settings.rules || []).find((x) => x.id === w.rule) || {});
            if (!show([ruleTg.tg, ...(ruleTg.tg_alt || [])])) continue;
            // 자막 칸: 왜 기다리는지 ("영어 자막만", "그림 자막(PGS)만" - 파일 안의 자막이 한국어가 아니면 자막 파일을 기다린다)
            const r = row(w.title, chip('wait', '자막 기다림'), w.why ? h('span', { class: 'subs-tag subs-none', title: '파일 안에 한국어(또는 언어 표시 없는) 글자 자막이 없어 자막 파일을 기다림', text: w.why }) : subsTag('없음'), `${when(w.since)}부터 · ${fmtDur(now - w.since)} 기다림${ruleTg.wait_min ? ` (최대 ${fmtDur(ruleTg.wait_min * 60)})` : ''}`);
            const shotUrl = `api/tgup/shot?${new URLSearchParams({ rule: w.rule, key: w.key, v: w.shot || 0 })}`;
            const shot = w.shot ? h('img', { class: 'mirror-shot', src: shotUrl, alt: '', loading: 'lazy', title: '10분 지점 장면 (누르면 크게)',
                on: { error: (e) => e.target.classList.add('failed'),
                    click: () => modal(`${w.title} - 10분 지점`, h('img', { class: 'mirror-shot-big', src: shotUrl, alt: '' })) } })
                : h('span', { class: `mirror-shot mirror-shot-wait${w.shot_error ? ' failed' : ''}`,
                    title: w.shot_error ? `장면을 뽑지 못했습니다 (6시간 뒤 다시): ${w.shot_error}` : '장면을 만드는 중 (잠시 뒤 나타남)' },
                icon(w.shot_error ? 'image' : 'hourglass-half'));
            r.firstChild.replaceWith(h('span', { class: 'mirror-title-shot' }, shot, h('span', { class: 'mirror-title', title: w.title, text: w.title })));
            r.lastChild.append(h('span', { class: 'mirror-actions' }, act(w, 'upload', '지금 올리기'), act(w, 'drop', '빼기', `"${w.title}"을(를) 올리지 않고 뺄까요?`)));
            live.push(r);
        }
        for (const x of s.retry || []) {
            if (shown.has(`${x.rule}/${x.key}`)) continue;
            const ruleTg = ((d.settings.rules || []).find((y) => y.id === x.rule) || {});
            if (!show([ruleTg.tg, ...(ruleTg.tg_alt || [])])) continue;
            const r = row(x.title, chip('queue', '다시 시도 대기'), '', `${x.at > now ? `${when(x.at)}에` : '곧'} 다시 (${Math.max(1, x.tries)}/3)`);
            r.lastChild.append(h('span', { class: 'mirror-actions' }, assignSel(x), cancelBtn(x)));
            live.push(r);
        }
        const skipKind = (note) => (/^건너뜀: 중복/.test(note) ? ['skip', '중복 건너뜀'] : /^건너뜀: 제외/.test(note) ? ['skip', '제외'] : /^건너뜀/.test(note) ? ['skip', '건너뜀'] : null);
        const hist = s.history.filter((x) => show([x.tg])).map((x) => {
            const sk = skipKind(String(x.note || ''));
            const st = x.ok ? chip('ok', '완료') : x.handed ? chip('wait', '계정 넘김') : sk ? chip(sk[0], sk[1]) : chip('fail', '실패');
            return row(x.title, st, x.subs ? subsTag(x.subs) : (x.ok ? '' : '-'),
                [when(x.at), x.elapsed ? `걸린 시간 ${fmtDur(x.elapsed)}` : '', many && x.tg ? accName(x.tg) : '', x.channel ? `→ ${x.channel}` : '',
                    x.again ? '다시 올림' : '', x.handover && x.handover.length ? `${x.handover.map(accName).join(', ')}에서 넘겨받음` : '', fmtTimes(x.times),
                    x.queued_at && x.started && x.started - x.queued_at >= 60 ? `줄에서 ${fmtDur(x.started - x.queued_at)} 기다림` : '',
                    ...String(x.note || '').split(', ').filter((m) => m && !(x.subs && /^(자막 파일 \d+개 첨부|내장 자막|자막 없음|자막 입혀 인코딩)$/.test(m)))]
                    .filter(Boolean).join(' · '));
        });
        // 계정마다 지금 하는 것 · 기다리는 수 · 성공/실패 · 쉬는 중
        const accCards = many ? h('div', { class: 'tgup-accs' }, accIds.filter((id) => statusFilter === 'all' || id === statusFilter).map((id) => {
            const a = (s.accounts || {})[id] || {};
            const info = accList.find((x) => x.id === id) || {};
            return h('div', { class: `tgup-acc${a.down ? ' is-down' : ''}` },
                h('div', { class: 'tgup-acc-head' }, h('i', { class: 'fa-brands fa-telegram' }), h('b', { text: ` ${accName(id)}` }),
                    info.authorized === false ? h('span', { class: 'mirror-chip fail', text: '로그인 안 됨' }) : null,
                    a.down ? h('span', { class: 'mirror-chip wait', text: '쉬는 중' }) : a.current ? h('span', { class: 'mirror-chip run', text: '올리는 중' }) : h('span', { class: 'mirror-chip ok', text: '놀고 있음' })),
                h('div', { class: 'muted', text: a.current ? `지금: ${a.current.title} - ${a.current.phase} (${fmtDur(a.current.elapsed)})` : '지금 하는 것 없음' }),
                a.down ? h('div', { class: 'muted error', text: `${a.down} - ${when(a.down_until)}까지 다른 계정이 올림` }) : null,
                h('div', { class: 'muted', text: `기다리는 것 ${a.queued || 0}개 · 완료 ${a.ok || 0} · 실패 ${a.fail || 0}${a.last ? ` · 마지막: ${a.last.title} (${a.last.ok ? '완료' : '실패/건너뜀'}, ${fmtDur(a.last.elapsed)})` : ''}` }));
        })) : null;
        const tabBar = many ? h('div', { class: 'tgup-subtabs', role: 'tablist' }, [['all', '전체'], ...accIds.map((id) => [id, accName(id)])].map(([id, t]) => {
            const a = (s.accounts || {})[id] || {};
            const count = id === 'all' ? '' : ` (${(a.queued || 0) + (a.current ? 1 : 0)})`;
            return h('button', { type: 'button', role: 'tab', class: statusFilter === id ? 'is-on' : '', on: { click: () => {
                statusFilter = id;
                try { localStorage.setItem('tgup_status_filter', id); } catch (e) { /* 무시 */ }
                renderStatus(pane);
            } } }, `${t}${count}`);
        })) : null;
        const nRules = (d.settings.rules || []).filter((r) => r.enabled).length;
        clear(pane).append(h('div', { class: 'src-card' },
            h('div', { class: 'toolbar' },
                h('span', { class: 'muted', text: `${accList.length > 1 ? `텔레그램 계정 ${accList.filter((x) => x.authorized).length}/${accList.length}개 로그인` : d.account && d.account.authorized ? `텔레그램 ${d.account.name || '로그인됨'}` : '텔레그램 로그인 안 됨'} · 켜진 규칙 ${nRules}개 · `
                    + `인코딩 ${s.encoding || 0}/${s.encode_slots || 1} · `
                    + (s.last_check ? `마지막 확인 ${new Date(s.last_check * 1000).toLocaleString()}` : '아직 확인 전') }),
                h('button', { class: 'btn btn-sm', on: { click: async () => { await post('api/tgup/check'); toast('지금 확인합니다.'); setTimeout(() => renderStatus(pane), 2000); } } }, icon('rotate-right'), ' 지금 확인')),
            s.error ? h('p', { class: 'muted error', text: s.error }) : null,
            ...(s.offline || []).map((o) => h('p', { class: 'muted error', text: `원본 드라이브 ${o.drive}에 닿지 못합니다 (${new Date(o.since * 1000).toLocaleTimeString()}부터, ${o.count}번) - `
                + 'rclone 마운트·네트워크 드라이브가 연결됐는지 확인하세요. 5분마다 다시 시도하며 실패로 세지 않습니다.'
                + (/^[A-Z]:$/.test(o.drive) ? ' (Windows: 드라이브를 다른 사용자·관리자 권한으로 붙였으면 이 프로그램에서 안 보일 수 있습니다)' : '') })),
            s.off_hours ? h('p', { class: 'muted', text: `지금은 올리기 시간대(${s.off_hours.replace('-', '시~')}시)가 아니라 쉬는 중 - 쌓아 두었다가 그 시간에 올립니다.` }) : null,
            tabBar, accCards,
            h('div', { class: 'mirror-live-head' }, h('h4', { text: `진행 (${live.length})${statusFilter !== 'all' ? ` - ${accName(statusFilter)}` : ''}` }),
                live.length > 1 && statusFilter === 'all' ? h('button', { class: 'btn btn-sm danger', on: { click: async (e) => {
                    if (!confirm(`진행 목록 ${live.length}개를 모두 취소할까요? (지금 올리는 것도 멈추고, 취소한 것은 다시 올리지 않음)`)) return;
                    e.currentTarget.disabled = true;
                    try { const r = await post('api/tgup/item', { action: 'cancel_all' }); toast(`${r.count}개를 취소했습니다.`); } catch (err) { toast(err.message, 'error'); }
                    renderStatus(pane);
                } } }, icon('ban'), ' 전체 취소') : null),
            live.length ? h('div', { class: 'mirror-table', role: 'table' }, head(), ...live) : h('p', { class: 'muted', text: '올릴 것이 없습니다.' }),
            h('p', { class: 'field-hint', text: '처리 순서: 새 영상 → 채널 중복 확인(작품·파일 이름·시즌·회차) → 제외 정규식 → 소프트 자막이면 바로 / 자막 파일은 정한 분만큼 기다림 → 놀고 있는 계정이 진행 목록 앞에서부터 올림. ↑↓로 순서를 바꾸고, 계정에 문제가 있으면 다른 계정을 고를 수 있습니다.' }),
            againBox(s, pane),
            h('h4', { text: '최근 기록' }),
            hist.length ? h('div', { class: 'mirror-table', role: 'table' }, head(), ...hist) : h('p', { class: 'muted', text: '아직 올린 것이 없습니다.' })));
        // 이 탭을 보는 동안만 새로 고친다 (올리는 중이면 2초, 아니면 15초마다 / 브라우저 탭이 가려져 있으면 쉼)
        const tick = () => { if (pane.hidden) return; if (document.hidden) { statusTimer = setTimeout(tick, 5000); return; } renderStatus(pane); };
        if (!pane.hidden) statusTimer = setTimeout(tick, cur || s.queue.length ? 2000 : 15000);
    }

    showTab((location.hash || '').slice(1) || 'status');
}());
