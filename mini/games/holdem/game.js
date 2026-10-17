// plugins/metadata/ym_mini_game/games/holdem/game.js

window.YmMiniGameHub.register('holdem', {
    name: "🃏 홀덤 (Texas Hold'em)",
    icon: 'fa-solid fa-heart',
    order: 11
}, function (container, hub) {
    const HTML = `
    <div class="holdem-game-root">
        <div class="game-sub-bar">
            <span class="game-view-name"><i class="fa-solid fa-heart"></i> TEXAS HOLD'EM</span>
            <div class="sub-actions">
                <button id="holdem-btn-start" class="btn-banner primary"><i class="fa-solid fa-play"></i> 게임 시작</button>
                <button id="holdem-btn-reset" class="btn-banner danger"><i class="fa-solid fa-rotate-left"></i> 세션 초기화</button>
            </div>
        </div>

        <div class="holdem-stage-grid">
            <div class="stage-col left-col" id="holdem-left-col">
            <button class="panel-toggle-btn" id="holdem-toggle-left" title="패널 접기/펼치기"><i class="fa-solid fa-chevron-left"></i></button>
            <div class="panel-content">
                <div class="mini-panel-card">
                    <div class="panel-header"><i class="fa-solid fa-chart-simple"></i> STATISTICS</div>
                    <div class="stat-grid">
                        <div class="stat-box"><span class="stat-lbl">핸드 수</span><span id="holdem-hand-count" class="stat-val highlight">0</span></div>
                        <div class="stat-box"><span class="stat-lbl">내 스택</span><span id="holdem-my-stack" class="stat-val">1000</span></div>
                        <div class="stat-box"><span class="stat-lbl">AI 1 스택</span><span id="holdem-ai1-stack" class="stat-val">1000</span></div>
                        <div class="stat-box"><span class="stat-lbl">AI 2 스택</span><span id="holdem-ai2-stack" class="stat-val">1000</span></div>
                    </div>
                </div>
                <div class="mini-panel-card">
                    <div class="panel-header"><i class="fa-regular fa-lightbulb"></i> 게임 방법</div>
                    <p class="tip-text">
                        • 3인 홀덤(나 + AI 2명), 시작 스택 1000, 블라인드 10/20 고정입니다.<br>
                        • 홀카드 2장 + 커뮤니티 카드 5장 중 최고의 5장으로 승부합니다.<br>
                        • 상대가 전부 폴드하면 카드를 공개하지 않고 팟을 가져갑니다.<br>
                        • 스택이 0이 되면 탈락하며, 최후의 1인이 남으면 세션이 종료됩니다.
                    </p>
                </div>
                <div class="mini-panel-card">
                    <div class="panel-header"><i class="fa-solid fa-list"></i> 핸드 기록</div>
                    <div id="holdem-log" class="holdem-log"></div>
                </div>
            
            </div></div>

            <div class="stage-col center-col">
                <div class="holdem-board-frame">
                    <canvas id="holdem-board" width="480" height="380"></canvas>
                    <div id="holdem-overlay" class="game-overlay hidden">
                        <h2 id="holdem-overlay-title">핸드 종료</h2>
                        <p id="holdem-overlay-msg"></p>
                        <button id="holdem-btn-overlay-action" class="btn-banner primary">다음 핸드</button>
                    </div>
                </div>
                <div id="holdem-action-bar" class="holdem-action-bar">
                    <button id="holdem-btn-fold" class="btn-banner danger">폴드</button>
                    <button id="holdem-btn-checkcall" class="btn-banner secondary">체크</button>
                    <div class="raise-controls">
                        <input id="holdem-raise-slider" type="range" min="20" max="1000" step="10" value="20">
                        <span id="holdem-raise-amount" class="raise-amount-label">20</span>
                        <button id="holdem-btn-raise" class="btn-banner primary">베팅</button>
                    </div>
                    <div class="raise-presets">
                        <button class="btn-banner secondary preset-btn" data-preset="half">1/2 팟</button>
                        <button class="btn-banner secondary preset-btn" data-preset="pot">팟</button>
                        <button class="btn-banner secondary preset-btn" data-preset="allin">올인</button>
                    </div>
                </div>
            </div>

            <div class="stage-col right-col" id="holdem-right-col">
            <button class="panel-toggle-btn" id="holdem-toggle-right" title="패널 접기/펼치기"><i class="fa-solid fa-chevron-right"></i></button>
            <div class="panel-content">
                <div class="mini-panel-card">
                    <div class="panel-header"><i class="fa-solid fa-ranking-star"></i> 족보 순위 (낮음 → 높음)</div>
                    <ul class="key-guide-list">
                        <li><span>하이카드</span></li>
                        <li><span>원페어</span></li>
                        <li><span>투페어</span></li>
                        <li><span>트리플</span></li>
                        <li><span>스트레이트</span></li>
                        <li><span>플러시</span></li>
                        <li><span>풀하우스</span></li>
                        <li><span>포카드</span></li>
                        <li><span>스트레이트 플러시</span></li>
                    </ul>
                </div>
            
            </div></div>
        </div>
    </div>`;

    container.innerHTML = HTML;

    // ============================================================
    // 카드/족보 평가 로직 (독립 검증 완료)
    // ============================================================
    const SUITS = ['s', 'h', 'd', 'c'];
    const SUIT_SYMBOL = { s: '♠', h: '♥', d: '♦', c: '♣' };
    const RANK_NAMES = { 11: 'J', 12: 'Q', 13: 'K', 14: 'A' };
    function rankName(r) { return RANK_NAMES[r] || String(r); }

    function createDeck() {
        const deck = [];
        for (const s of SUITS) for (let r = 2; r <= 14; r++) deck.push({ r, s });
        return deck;
    }
    function shuffle(arr) {
        for (let i = arr.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [arr[i], arr[j]] = [arr[j], arr[i]];
        }
        return arr;
    }

    function evaluate5(cards) {
        const ranks = cards.map(c => c.r).sort((a, b) => b - a);
        const suits = cards.map(c => c.s);
        const isFlush = suits.every(s => s === suits[0]);
        const countMap = {};
        ranks.forEach(r => { countMap[r] = (countMap[r] || 0) + 1; });
        const groups = Object.entries(countMap).map(([r, cnt]) => ({ r: parseInt(r, 10), cnt }))
            .sort((a, b) => (b.cnt - a.cnt) || (b.r - a.r));

        const uniqueRanks = [...new Set(ranks)];
        let straightHigh = null;
        if (uniqueRanks.length >= 5) {
            for (let i = 0; i <= uniqueRanks.length - 5; i++) {
                if (uniqueRanks[i] - uniqueRanks[i + 4] === 4) { straightHigh = uniqueRanks[i]; break; }
            }
        }
        if (straightHigh === null && uniqueRanks.includes(14) && uniqueRanks.includes(2) &&
            uniqueRanks.includes(3) && uniqueRanks.includes(4) && uniqueRanks.includes(5)) {
            straightHigh = 5;
        }

        if (isFlush && straightHigh !== null) return { rank: 8, tiebreak: [straightHigh] };
        if (groups[0].cnt === 4) {
            const kicker = groups.find(g => g.cnt === 1).r;
            return { rank: 7, tiebreak: [groups[0].r, kicker] };
        }
        if (groups[0].cnt === 3 && groups[1] && groups[1].cnt >= 2) return { rank: 6, tiebreak: [groups[0].r, groups[1].r] };
        if (isFlush) return { rank: 5, tiebreak: ranks };
        if (straightHigh !== null) return { rank: 4, tiebreak: [straightHigh] };
        if (groups[0].cnt === 3) {
            const kickers = groups.filter(g => g.cnt === 1).map(g => g.r).sort((a, b) => b - a);
            return { rank: 3, tiebreak: [groups[0].r, ...kickers] };
        }
        if (groups[0].cnt === 2 && groups[1] && groups[1].cnt === 2) {
            const pairs = [groups[0].r, groups[1].r].sort((a, b) => b - a);
            const kicker = groups.find(g => g.cnt === 1).r;
            return { rank: 2, tiebreak: [...pairs, kicker] };
        }
        if (groups[0].cnt === 2) {
            const kickers = groups.filter(g => g.cnt === 1).map(g => g.r).sort((a, b) => b - a);
            return { rank: 1, tiebreak: [groups[0].r, ...kickers] };
        }
        return { rank: 0, tiebreak: ranks };
    }

    function compareEval(a, b) {
        if (a.rank !== b.rank) return a.rank - b.rank;
        for (let i = 0; i < Math.max(a.tiebreak.length, b.tiebreak.length); i++) {
            const av = a.tiebreak[i] || 0, bv = b.tiebreak[i] || 0;
            if (av !== bv) return av - bv;
        }
        return 0;
    }

    function combinations(arr, k) {
        const results = [];
        function helper(start, combo) {
            if (combo.length === k) { results.push(combo.slice()); return; }
            for (let i = start; i < arr.length; i++) { combo.push(arr[i]); helper(i + 1, combo); combo.pop(); }
        }
        helper(0, []);
        return results;
    }

    function evaluate7(cards) {
        if (cards.length === 5) return evaluate5(cards);
        const combos = combinations(cards, 5);
        let best = null;
        for (const combo of combos) {
            const ev = evaluate5(combo);
            if (!best || compareEval(ev, best) > 0) best = ev;
        }
        return best;
    }

    const HAND_NAMES_KO = ['하이 카드', '원 페어', '투 페어', '트리플', '스트레이트', '플러시', '풀하우스', '포카드', '스트레이트 플러시'];
    function handNameKo(ev) { return HAND_NAMES_KO[ev.rank]; }

    function calculatePots(players) {
        const contributors = players.filter(p => p.totalContributed > 0);
        if (contributors.length === 0) return [];
        const levels = [...new Set(contributors.map(p => p.totalContributed))].sort((a, b) => a - b);
        const pots = [];
        let prevLevel = 0;
        for (const level of levels) {
            const layerAmount = level - prevLevel;
            const layerContributors = contributors.filter(p => p.totalContributed >= level);
            const potSize = layerAmount * layerContributors.length;
            const eligiblePlayerIds = layerContributors.filter(p => !p.folded).map(p => p.id);
            if (potSize > 0) pots.push({ amount: potSize, eligiblePlayerIds });
            prevLevel = level;
        }
        return pots;
    }

    function estimateWinProbability(myHole, community, numOpponents, deadCards, simulations) {
        simulations = simulations || 120;
        const known = [...myHole, ...community, ...deadCards];
        const knownKeys = new Set(known.map(c => c.r + c.s));
        const baseDeck = createDeck().filter(c => !knownKeys.has(c.r + c.s));
        let wins = 0, ties = 0;
        for (let i = 0; i < simulations; i++) {
            const deck = shuffle(baseDeck.slice());
            let idx = 0;
            const neededCommunity = 5 - community.length;
            const simCommunity = community.concat(deck.slice(idx, idx + neededCommunity));
            idx += neededCommunity;
            const myBest = evaluate7(myHole.concat(simCommunity));
            let bestOppEval = null;
            for (let o = 0; o < numOpponents; o++) {
                const oppHole = deck.slice(idx, idx + 2);
                idx += 2;
                const oppEval = evaluate7(oppHole.concat(simCommunity));
                if (!bestOppEval || compareEval(oppEval, bestOppEval) > 0) bestOppEval = oppEval;
            }
            const cmp = compareEval(myBest, bestOppEval);
            if (cmp > 0) wins++; else if (cmp === 0) ties++;
        }
        return (wins + ties * 0.5) / simulations;
    }

    // ============================================================
    // 테이블 엔진 (독립 검증 완료)
    // ============================================================
    const SMALL_BLIND = 10, BIG_BLIND = 20, STARTING_STACK = 1000;

    function createTable() {
        return {
            players: [
                { id: 'player', name: '나', stack: STARTING_STACK, holeCards: [], folded: false, allIn: false, betThisStreet: 0, totalContributed: 0, isAI: false, eliminated: false },
                { id: 'ai1', name: 'AI 1', stack: STARTING_STACK, holeCards: [], folded: false, allIn: false, betThisStreet: 0, totalContributed: 0, isAI: true, eliminated: false },
                { id: 'ai2', name: 'AI 2', stack: STARTING_STACK, holeCards: [], folded: false, allIn: false, betThisStreet: 0, totalContributed: 0, isAI: true, eliminated: false },
            ],
            deck: [], community: [], buttonIndex: -1, street: 'waiting',
            currentBet: 0, minRaise: BIG_BLIND, toActQueue: [], handLog: [], pots: [], handOver: false,
            handCount: 0,
        };
    }

    function activePlayers(t) { return t.players.filter(p => !p.eliminated); }
    function notFolded(t) { return t.players.filter(p => !p.eliminated && !p.folded); }
    function getPlayer(t, id) { return t.players.find(p => p.id === id); }

    function nextActiveIndexFrom(t, fromIndex) {
        const n = t.players.length;
        for (let step = 1; step <= n; step++) {
            const idx = (fromIndex + step) % n;
            if (!t.players[idx].eliminated) return idx;
        }
        return fromIndex;
    }

    function postBlind(t, player, amount) {
        const actual = Math.min(amount, player.stack);
        player.stack -= actual; player.betThisStreet += actual; player.totalContributed += actual;
        if (player.stack === 0) player.allIn = true;
        return actual;
    }

    function startHand(t) {
        t.deck = shuffle(createDeck());
        t.community = []; t.handLog = []; t.pots = []; t.handOver = false;
        t.currentBet = 0; t.minRaise = BIG_BLIND;
        t.handCount++;

        t.players.forEach(p => {
            p.holeCards = []; p.folded = p.eliminated; p.allIn = false;
            p.betThisStreet = 0; p.totalContributed = 0;
        });

        const active = activePlayers(t);
        if (active.length < 2) { t.street = 'gameover'; return t; }

        t.buttonIndex = nextActiveIndexFrom(t, t.buttonIndex);

        let sbIndex, bbIndex;
        if (active.length === 2) {
            sbIndex = t.buttonIndex;
            bbIndex = nextActiveIndexFrom(t, sbIndex);
        } else {
            sbIndex = nextActiveIndexFrom(t, t.buttonIndex);
            bbIndex = nextActiveIndexFrom(t, sbIndex);
        }

        const sbAmt = postBlind(t, t.players[sbIndex], SMALL_BLIND);
        const bbAmt = postBlind(t, t.players[bbIndex], BIG_BLIND);
        t.handLog.push(`${t.players[sbIndex].name}가 스몰블라인드 ${sbAmt} 지불`);
        t.handLog.push(`${t.players[bbIndex].name}가 빅블라인드 ${bbAmt} 지불`);
        t.currentBet = BIG_BLIND;

        for (let i = 0; i < 2; i++) activePlayers(t).forEach(p => p.holeCards.push(t.deck.pop()));

        t.street = 'preflop';
        const order = [];
        let idx = bbIndex;
        for (let i = 0; i < active.length; i++) { idx = nextActiveIndexFrom(t, idx); order.push(t.players[idx].id); }
        t.toActQueue = order.filter(id => !getPlayer(t, id).allIn);
        t.lastAggressorId = t.players[bbIndex].id;
        return t;
    }

    function callAmount(t, playerId) {
        const p = getPlayer(t, playerId);
        return Math.max(0, t.currentBet - p.betThisStreet);
    }

    function applyAction(t, playerId, action, amount) {
        const p = getPlayer(t, playerId);
        const toCall = callAmount(t, playerId);

        if (action === 'fold') {
            p.folded = true;
            t.handLog.push(`${p.name} 폴드`);
        } else if (action === 'check') {
            t.handLog.push(`${p.name} 체크`);
        } else if (action === 'call') {
            const pay = Math.min(toCall, p.stack);
            p.stack -= pay; p.betThisStreet += pay; p.totalContributed += pay;
            if (p.stack === 0) p.allIn = true;
            t.handLog.push(`${p.name} 콜 (${pay})`);
        } else if (action === 'bet' || action === 'raise' || action === 'allin') {
            let target = amount;
            if (action === 'allin') target = p.betThisStreet + p.stack;
            const pay = Math.min(target - p.betThisStreet, p.stack);
            const newBetLevel = p.betThisStreet + pay;
            p.stack -= pay; p.betThisStreet = newBetLevel; p.totalContributed += pay;
            if (p.stack === 0) p.allIn = true;

            const isRaise = newBetLevel > t.currentBet;
            if (isRaise) {
                const raiseSize = newBetLevel - t.currentBet;
                t.minRaise = Math.max(t.minRaise, raiseSize);
                t.currentBet = newBetLevel;
                t.lastAggressorId = playerId;
                t.toActQueue = notFolded(t).filter(pl => pl.id !== playerId && !pl.allIn).map(pl => pl.id);
                t.handLog.push(`${p.name} ${action === 'allin' ? '올인' : (t.street === 'preflop' && action === 'bet' ? '레이즈' : action === 'bet' ? '베팅' : '레이즈')} (${newBetLevel})`);
                return t;
            } else {
                t.handLog.push(`${p.name} 올인 (${newBetLevel}, 콜 수준 이하)`);
            }
        }
        t.toActQueue = t.toActQueue.filter(id => id !== playerId);
        return t;
    }

    function isHandOverByFold(t) { return notFolded(t).length <= 1; }
    function isStreetOver(t) {
        if (isHandOverByFold(t)) return true;
        const contestants = notFolded(t).filter(p => !p.allIn);
        if (contestants.length === 0) return true;
        return t.toActQueue.length === 0;
    }

    function setupPostflopQueue(t) {
        const order = [];
        let idx = t.buttonIndex;
        const n = t.players.length;
        for (let i = 0; i < n; i++) { idx = nextActiveIndexFrom(t, idx); order.push(t.players[idx].id); }
        t.toActQueue = order.filter(id => { const p = getPlayer(t, id); return !p.folded && !p.allIn; });
    }

    function advanceStreet(t) {
        t.players.forEach(p => { p.betThisStreet = 0; });
        t.currentBet = 0; t.minRaise = BIG_BLIND;

        if (t.street === 'preflop') { t.deck.pop(); t.community.push(t.deck.pop(), t.deck.pop(), t.deck.pop()); t.street = 'flop'; }
        else if (t.street === 'flop') { t.deck.pop(); t.community.push(t.deck.pop()); t.street = 'turn'; }
        else if (t.street === 'turn') { t.deck.pop(); t.community.push(t.deck.pop()); t.street = 'river'; }
        else if (t.street === 'river') { t.street = 'showdown'; return t; }

        setupPostflopQueue(t);
        return t;
    }

    function markEliminated(t) { t.players.forEach(p => { if (!p.eliminated && p.stack <= 0) p.eliminated = true; }); }

    function finishHandByFold(t) {
        const winner = notFolded(t)[0];
        const pots = calculatePots(t.players.map(p => ({ id: p.id, folded: p.folded, totalContributed: p.totalContributed })));
        const totalPot = pots.reduce((s, pot) => s + pot.amount, 0);
        winner.stack += totalPot;
        t.handLog.push(`${winner.name}가 팟 ${totalPot} 획득 (다른 플레이어 전원 폴드)`);
        t.pots = pots; t.street = 'handover'; t.handOver = true;
        markEliminated(t);
        return { winners: [{ id: winner.id, amount: totalPot }], pots, byFold: true };
    }

    function resolveShowdown(t) {
        while (t.community.length < 5) { t.deck.pop(); t.community.push(t.deck.pop()); }
        const pots = calculatePots(t.players.map(p => ({ id: p.id, folded: p.folded, totalContributed: p.totalContributed })));
        const evalCache = {};
        notFolded(t).forEach(p => { evalCache[p.id] = evaluate7(p.holeCards.concat(t.community)); });

        const winners = [];
        pots.forEach(pot => {
            let best = null, bestIds = [];
            pot.eligiblePlayerIds.forEach(id => {
                const ev = evalCache[id];
                if (!best || compareEval(ev, best) > 0) { best = ev; bestIds = [id]; }
                else if (compareEval(ev, best) === 0) bestIds.push(id);
            });
            const share = Math.floor(pot.amount / bestIds.length);
            let remainder = pot.amount - share * bestIds.length;
            bestIds.forEach(id => {
                let amt = share;
                if (remainder > 0) { amt += 1; remainder -= 1; }
                getPlayer(t, id).stack += amt;
                winners.push({ id, amount: amt, hand: handNameKo(evalCache[id]) });
            });
        });

        t.pots = pots; t.street = 'handover'; t.handOver = true;
        markEliminated(t);
        return { winners, pots, evalCache, byFold: false };
    }

    // ============================================================
    // UI 및 게임 진행 제어
    // ============================================================
    const canvas = container.querySelector('#holdem-board');
    const ctx = canvas.getContext('2d');
    const W = canvas.width, H = canvas.height;

    const handCountEl = container.querySelector('#holdem-hand-count');
    const myStackEl = container.querySelector('#holdem-my-stack');
    const ai1StackEl = container.querySelector('#holdem-ai1-stack');
    const ai2StackEl = container.querySelector('#holdem-ai2-stack');
    const logEl = container.querySelector('#holdem-log');

    const overlay = container.querySelector('#holdem-overlay');
    const overlayTitle = container.querySelector('#holdem-overlay-title');
    const overlayMsg = container.querySelector('#holdem-overlay-msg');
    const btnOverlay = container.querySelector('#holdem-btn-overlay-action');

    const btnStart = container.querySelector('#holdem-btn-start');
    const btnReset = container.querySelector('#holdem-btn-reset');
    const actionBar = container.querySelector('#holdem-action-bar');
    const btnFold = container.querySelector('#holdem-btn-fold');
    const btnCheckCall = container.querySelector('#holdem-btn-checkcall');
    const btnRaise = container.querySelector('#holdem-btn-raise');
    const raiseSlider = container.querySelector('#holdem-raise-slider');
    const raiseAmountLabel = container.querySelector('#holdem-raise-amount');

    let table = createTable();
    let aiTimeoutId = null;
    let sessionOver = false;

    function loadLog() {
        logEl.innerHTML = '';
        table.handLog.slice().reverse().forEach(line => {
            const div = document.createElement('div');
            div.textContent = line;
            logEl.appendChild(div);
        });
    }

    function updateStats() {
        handCountEl.textContent = String(table.handCount);
        myStackEl.textContent = String(getPlayer(table, 'player').stack);
        ai1StackEl.textContent = String(getPlayer(table, 'ai1').stack);
        ai2StackEl.textContent = String(getPlayer(table, 'ai2').stack);
        loadLog();
    }

    // ---------- 렌더링 ----------
    function drawCard(x, y, card, faceDown) {
        const w = 34, h = 48;
        ctx.fillStyle = faceDown ? '#1d4ed8' : '#f8fafc';
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(x, y, w, h, 5); else ctx.rect(x, y, w, h);
        ctx.fill();
        ctx.strokeStyle = 'rgba(0,0,0,0.4)';
        ctx.lineWidth = 1;
        ctx.stroke();
        if (faceDown) {
            ctx.strokeStyle = 'rgba(255,255,255,0.4)';
            ctx.beginPath(); ctx.moveTo(x + 4, y + 4); ctx.lineTo(x + w - 4, y + h - 4); ctx.stroke();
            ctx.beginPath(); ctx.moveTo(x + w - 4, y + 4); ctx.lineTo(x + 4, y + h - 4); ctx.stroke();
            return;
        }
        const isRed = card.s === 'h' || card.s === 'd';
        ctx.fillStyle = isRed ? '#dc2626' : '#111827';
        ctx.font = 'bold 13px sans-serif';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'top';
        ctx.fillText(rankName(card.r), x + 3, y + 3);
        ctx.font = '14px sans-serif';
        ctx.fillText(SUIT_SYMBOL[card.s], x + 3, y + 18);
    }

    function drawSeat(cx, cy, player, isDealer) {
        ctx.fillStyle = 'rgba(0,0,0,0.35)';
        ctx.beginPath();
        ctx.ellipse(cx, cy, 58, 26, 0, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = player.folded ? '#6b7280' : '#f8fafc';
        ctx.font = 'bold 12px sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(`${player.name}${player.eliminated ? ' (탈락)' : ''}`, cx, cy - 12);
        ctx.font = '11px sans-serif';
        ctx.fillStyle = '#facc15';
        ctx.fillText(`${player.stack}`, cx, cy + 4);

        if (player.betThisStreet > 0) {
            ctx.fillStyle = '#38bdf8';
            ctx.font = '10px sans-serif';
            ctx.fillText(`베팅 ${player.betThisStreet}`, cx, cy + 18);
        }
        if (isDealer) {
            ctx.fillStyle = '#f8fafc';
            ctx.beginPath();
            ctx.arc(cx + 46, cy - 20, 8, 0, Math.PI * 2);
            ctx.fill();
            ctx.fillStyle = '#111827';
            ctx.font = 'bold 9px sans-serif';
            ctx.fillText('D', cx + 46, cy - 20);
        }
    }

    function draw() {
        ctx.fillStyle = '#14532d';
        ctx.fillRect(0, 0, W, H);
        ctx.strokeStyle = '#0b3a1f';
        ctx.lineWidth = 6;
        ctx.beginPath();
        ctx.ellipse(W / 2, H / 2, W / 2 - 10, H / 2 - 10, 0, 0, Math.PI * 2);
        ctx.stroke();

        const positions = {
            player: { x: W / 2, y: H - 40, cardY: H - 90 },
            ai1: { x: 90, y: 60, cardY: 70 },
            ai2: { x: W - 90, y: 60, cardY: 70 },
        };

        table.players.forEach(p => {
            const pos = positions[p.id];
            drawSeat(pos.x, pos.y, p, table.players.indexOf(p) === table.buttonIndex);
            if (p.holeCards.length === 2 && !p.eliminated) {
                const showFace = p.id === 'player' || table.street === 'handover';
                const isFold = p.folded;
                if (!isFold || showFace) {
                    drawCard(pos.x - 38, pos.cardY, p.holeCards[0], !showFace);
                    drawCard(pos.x - 2, pos.cardY, p.holeCards[1], !showFace);
                }
            }
        });

        // 커뮤니티 카드
        const comX = W / 2 - (5 * 38) / 2;
        table.community.forEach((c, i) => drawCard(comX + i * 38, H / 2 - 24, c, false));

        // 팟
        const potTotal = table.players.reduce((s, p) => s + p.totalContributed, 0);
        ctx.fillStyle = '#fde68a';
        ctx.font = 'bold 13px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(`팟: ${potTotal}`, W / 2, H / 2 + 40);
    }

    // ---------- AI 의사결정 ----------
    function aiDecide(playerId) {
        const p = getPlayer(table, playerId);
        const toCall = callAmount(table, playerId);
        const numOpponents = notFolded(table).filter(pl => pl.id !== playerId).length;
        const winProb = estimateWinProbability(p.holeCards, table.community, numOpponents, [], 120);
        const potSize = table.players.reduce((s, pl) => s + pl.totalContributed, 0);
        const potOdds = toCall / Math.max(1, (potSize + toCall));

        if (toCall === 0) {
            if (winProb > 0.68 && Math.random() < 0.55) {
                return { action: 'bet', amount: Math.min(table.currentBet + Math.max(BIG_BLIND, Math.floor(potSize * 0.6)), p.betThisStreet + p.stack) };
            }
            return { action: 'check' };
        }
        if (toCall >= p.stack) return { action: winProb > potOdds * 0.9 ? 'call' : 'fold' };
        if (winProb < potOdds * 0.85) return { action: 'fold' };
        if (winProb > 0.72 && Math.random() < 0.5) {
            return { action: 'raise', amount: Math.min(table.currentBet + Math.max(BIG_BLIND, Math.floor(potSize * 0.7)), p.betThisStreet + p.stack) };
        }
        return { action: 'call' };
    }

    // ---------- 게임 흐름 ----------
    function advanceGame() {
        if (table.street === 'handover' || table.street === 'gameover') { draw(); return; }

        if (isHandOverByFold(table)) {
            const result = finishHandByFold(table);
            onHandEnd(result);
            return;
        }
        if (isStreetOver(table)) {
            if (table.street === 'river') { const result = resolveShowdown(table); onHandEnd(result); return; }
            advanceStreet(table);
            updateStats(); draw();
            aiTimeoutId = setTimeout(advanceGame, 550);
            return;
        }

        const actingId = table.toActQueue[0];
        if (!actingId) {
            if (table.street === 'river') { const result = resolveShowdown(table); onHandEnd(result); return; }
            advanceStreet(table); updateStats(); draw();
            aiTimeoutId = setTimeout(advanceGame, 550);
            return;
        }

        const player = getPlayer(table, actingId);
        if (player.isAI) {
            setActionBarEnabled(false);
            draw();
            aiTimeoutId = setTimeout(() => {
                const decision = aiDecide(actingId);
                applyAction(table, actingId, decision.action, decision.amount);
                updateStats(); draw();
                advanceGame();
            }, 500 + Math.random() * 400);
        } else {
            setupPlayerControls(actingId);
            updateStats(); draw();
        }
    }

    function onHandEnd(result) {
        updateStats(); draw();
        setActionBarEnabled(false);

        const player = getPlayer(table, 'player');
        const winnerIsMe = result.winners.some(w => w.id === 'player');
        let msg = '';
        if (result.byFold) {
            const winnerName = getPlayer(table, result.winners[0].id).name;
            msg = `${winnerName}가 팟 ${result.winners[0].amount}을(를) 획득했습니다.\n(다른 플레이어가 모두 폴드)`;
        } else {
            const lines = result.winners.map(w => `${getPlayer(table, w.id).name}: ${w.hand} (+${w.amount})`);
            msg = lines.join('\n');
        }

        overlayTitle.textContent = winnerIsMe ? '🎉 핸드 승리' : (result.winners.length && !result.byFold ? '패배' : '핸드 종료');
        overlayTitle.style.color = winnerIsMe ? '#10b981' : '#f8fafc';
        overlayMsg.textContent = msg;

        const alive = activePlayers(table);
        if (player.eliminated) {
            overlayTitle.textContent = '💥 파산했습니다';
            overlayTitle.style.color = '#ef4444';
            overlayMsg.textContent = msg + '\n\n세션이 종료되었습니다.';
            btnOverlay.textContent = '새 세션 시작';
            overlay.dataset.nextAction = 'newsession';
            sessionOver = true;
            hub.setStatusBadge('GAME OVER', 'lost');
        } else if (alive.length < 2) {
            overlayTitle.textContent = '🏆 세션 승리!';
            overlayTitle.style.color = '#10b981';
            overlayMsg.textContent = msg + '\n\n모든 상대를 이겼습니다!';
            btnOverlay.textContent = '새 세션 시작';
            overlay.dataset.nextAction = 'newsession';
            sessionOver = true;
            hub.setStatusBadge('WIN', 'won');
        } else {
            btnOverlay.textContent = '다음 핸드';
            overlay.dataset.nextAction = 'nexthand';
            hub.setStatusBadge(winnerIsMe ? 'WIN HAND' : 'NEXT HAND', winnerIsMe ? 'won' : '');
        }
        overlay.classList.remove('hidden');
    }

    function setActionBarEnabled(enabled) {
        actionBar.classList.toggle('disabled', !enabled);
    }

    function setupPlayerControls(playerId) {
        const p = getPlayer(table, playerId);
        const toCall = callAmount(table, playerId);
        setActionBarEnabled(true);

        btnCheckCall.textContent = toCall === 0 ? '체크' : `콜 (${toCall})`;
        btnCheckCall.disabled = false;

        const minTotal = Math.min(table.currentBet + Math.max(table.minRaise, BIG_BLIND), p.betThisStreet + p.stack);
        const maxTotal = p.betThisStreet + p.stack;
        raiseSlider.min = String(Math.max(minTotal, BIG_BLIND));
        raiseSlider.max = String(Math.max(maxTotal, minTotal));
        raiseSlider.step = String(BIG_BLIND);
        raiseSlider.value = String(Math.min(Math.max(minTotal, BIG_BLIND), maxTotal));
        raiseAmountLabel.textContent = raiseSlider.value;
        btnRaise.textContent = toCall === 0 ? '베팅' : '레이즈';
        btnRaise.disabled = maxTotal <= table.currentBet; // 콜만 가능하고 더 못 올릴 때(스택 부족)
    }

    function submitPlayerAction(action, amount) {
        clearTimeout(aiTimeoutId);
        applyAction(table, 'player', action, amount);
        setActionBarEnabled(false);
        updateStats(); draw();
        advanceGame();
    }

    // ---------- 시작/리셋 ----------
    function startNextHand() {
        overlay.classList.add('hidden');
        startHand(table);
        if (table.street === 'gameover') { return; }
        updateStats(); draw();
        advanceGame();
    }

    function startSession() {
        table = createTable();
        sessionOver = false;
        btnStart.disabled = true;
        btnStart.innerHTML = '<i class="fa-solid fa-gamepad"></i> 진행 중';
        hub.setStatusBadge('PLAYING (HOLDEM)', 'playing');
        startNextHand();
    }

    function resetSession() {
        clearTimeout(aiTimeoutId);
        table = createTable();
        sessionOver = false;
        overlay.classList.add('hidden');
        setActionBarEnabled(false);
        btnStart.disabled = false;
        btnStart.innerHTML = '<i class="fa-solid fa-play"></i> 게임 시작';
        hub.setStatusBadge('READY (HOLDEM)', '');
        updateStats();
        draw();
    }

    function setupPanelToggle(colId, btnId, iconOpen, iconClosed) {
        const col = container.querySelector('#' + colId);
        const btn = container.querySelector('#' + btnId);
        if (!col || !btn) return;
        btn.onclick = () => {
            const collapsed = col.classList.toggle('collapsed');
            const icon = btn.querySelector('i');
            if (icon) icon.className = collapsed ? iconClosed : iconOpen;
        };
    }

    return {
        init() {
            btnStart.onclick = startSession;
            btnReset.onclick = resetSession;

            btnFold.onclick = () => submitPlayerAction('fold');
            btnCheckCall.onclick = () => {
                const toCall = callAmount(table, 'player');
                submitPlayerAction(toCall === 0 ? 'check' : 'call');
            };
            btnRaise.onclick = () => {
                const amount = parseInt(raiseSlider.value, 10);
                const toCall = callAmount(table, 'player');
                const p = getPlayer(table, 'player');
                const isAllIn = amount >= p.betThisStreet + p.stack;
                submitPlayerAction(isAllIn ? 'allin' : (toCall === 0 ? 'bet' : 'raise'), amount);
            };
            raiseSlider.oninput = () => { raiseAmountLabel.textContent = raiseSlider.value; };

            container.querySelectorAll('.preset-btn').forEach(btn => {
                btn.onclick = () => {
                    const p = getPlayer(table, 'player');
                    const potSize = table.players.reduce((s, pl) => s + pl.totalContributed, 0);
                    const maxTotal = p.betThisStreet + p.stack;
                    let target;
                    if (btn.dataset.preset === 'half') target = table.currentBet + Math.floor(potSize * 0.5);
                    else if (btn.dataset.preset === 'pot') target = table.currentBet + potSize;
                    else target = maxTotal;
                    target = Math.max(parseInt(raiseSlider.min, 10), Math.min(target, maxTotal));
                    raiseSlider.value = String(target);
                    raiseAmountLabel.textContent = raiseSlider.value;
                };
            });

            btnOverlay.onclick = () => {
                const action = overlay.dataset.nextAction;
                if (action === 'newsession') startSession();
                else startNextHand();
            };

            setActionBarEnabled(false);
            updateStats();
            draw();
        

            setupPanelToggle('holdem-left-col', 'holdem-toggle-left', 'fa-solid fa-chevron-left', 'fa-solid fa-chevron-right');
            setupPanelToggle('holdem-right-col', 'holdem-toggle-right', 'fa-solid fa-chevron-right', 'fa-solid fa-chevron-left');
},
        destroy() {
            clearTimeout(aiTimeoutId);
        }
    };
});
