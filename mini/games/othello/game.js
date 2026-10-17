// plugins/metadata/ym_mini_game/games/othello/game.js

window.YmMiniGameHub.register('othello', {
    name: '⚫⚪ 오델로 (Othello)',
    icon: 'fa-solid fa-circle',
    order: 10
}, function (container, hub) {
    const HTML = `
    <div class="othello-game-root">
        <div class="game-sub-bar">
            <span class="game-view-name"><i class="fa-solid fa-circle"></i> OTHELLO</span>
            <div class="sub-actions">
                <button id="othello-btn-start" class="btn-banner primary"><i class="fa-solid fa-play"></i> 새 게임</button>
                <button id="othello-btn-surrender" class="btn-banner danger" disabled><i class="fa-solid fa-flag"></i> 기권</button>
            </div>
        </div>

        <div class="othello-stage-grid">
            <div class="stage-col left-col" id="othello-left-col">
            <button class="panel-toggle-btn" id="othello-toggle-left" title="패널 접기/펼치기"><i class="fa-solid fa-chevron-left"></i></button>
            <div class="panel-content">
                <div class="mini-panel-card">
                    <div class="panel-header"><i class="fa-solid fa-chart-simple"></i> STATISTICS</div>
                    <div class="stat-grid">
                        <div class="stat-box"><span class="stat-lbl">현재 차례</span><span id="othello-turn" class="stat-val highlight">-</span></div>
                        <div class="stat-box"><span class="stat-lbl">흑돌(나)</span><span id="othello-black-count" class="stat-val">2</span></div>
                        <div class="stat-box"><span class="stat-lbl">백돌(AI)</span><span id="othello-white-count" class="stat-val">2</span></div>
                        <div class="stat-box"><span class="stat-lbl">승</span><span id="othello-wins" class="stat-val">0</span></div>
                        <div class="stat-box"><span class="stat-lbl">패</span><span id="othello-losses" class="stat-val">0</span></div>
                        <div class="stat-box"><span class="stat-lbl">무</span><span id="othello-draws" class="stat-val">0</span></div>
                    </div>
                </div>
                <div class="mini-panel-card">
                    <div class="panel-header"><i class="fa-regular fa-lightbulb"></i> 게임 방법</div>
                    <p class="tip-text">
                        • 당신은 흑돌, AI는 백돌입니다. 흑돌이 먼저 둡니다.<br>
                        • 상대 돌을 자신의 돌 두 개 사이에 가두면 전부 뒤집힙니다.<br>
                        • 둘 수 있는 곳이 없으면 자동으로 차례가 넘어갑니다(패스).<br>
                        • 둘 다 둘 곳이 없으면 게임이 끝나고, 돌이 더 많은 쪽이 승리합니다.
                    </p>
                </div>
            
            </div></div>

            <div class="stage-col center-col">
                <div class="othello-board-frame">
                    <canvas id="othello-board" width="400" height="400"></canvas>
                    <div id="othello-overlay" class="game-overlay hidden">
                        <h2 id="othello-overlay-title">GAME OVER</h2>
                        <p id="othello-overlay-msg"></p>
                        <button id="othello-btn-overlay-action" class="btn-banner primary">다시 시작</button>
                    </div>
                </div>
            </div>

            <div class="stage-col right-col" id="othello-right-col">
            <button class="panel-toggle-btn" id="othello-toggle-right" title="패널 접기/펼치기"><i class="fa-solid fa-chevron-right"></i></button>
            <div class="panel-content">
                <div class="mini-panel-card">
                    <div class="panel-header"><i class="fa-regular fa-keyboard"></i> 조작 가이드</div>
                    <ul class="key-guide-list">
                        <li><span>착수</span> <kbd>보드 클릭/탭</kbd></li>
                    </ul>
                </div>
                <div class="mini-panel-card">
                    <div class="panel-header"><i class="fa-solid fa-circle-half-stroke"></i> 돌 색상</div>
                    <ul class="key-guide-list">
                        <li><span><i class="fa-solid fa-circle" style="color:#111827;"></i> 나 (흑돌)</span></li>
                        <li><span><i class="fa-regular fa-circle" style="color:#f8fafc;"></i> AI (백돌)</span></li>
                    </ul>
                </div>
            
            </div></div>
        </div>
    </div>`;

    container.innerHTML = HTML;

    // ---------- 오델로 핵심 로직 (독립 검증 완료) ----------
    const SIZE = 8;
    const EMPTY = 0, BLACK = 1, WHITE = 2;
    const DIRS = [[-1,-1],[-1,0],[-1,1],[0,-1],[0,1],[1,-1],[1,0],[1,1]];
    const AI_DEPTH = 4;

    function makeInitialGrid() {
        const g = Array.from({ length: SIZE }, () => new Array(SIZE).fill(EMPTY));
        g[3][3] = WHITE; g[3][4] = BLACK;
        g[4][3] = BLACK; g[4][4] = WHITE;
        return g;
    }

    function inBounds(r, c) { return r >= 0 && r < SIZE && c >= 0 && c < SIZE; }
    function opponent(p) { return p === BLACK ? WHITE : BLACK; }
    function cloneGrid(g) { return g.map(row => row.slice()); }

    function getFlipsInDirection(grid, r, c, dr, dc, player) {
        const opp = opponent(player);
        let rr = r + dr, cc = c + dc;
        const line = [];
        while (inBounds(rr, cc) && grid[rr][cc] === opp) {
            line.push([rr, cc]);
            rr += dr; cc += dc;
        }
        if (line.length > 0 && inBounds(rr, cc) && grid[rr][cc] === player) return line;
        return [];
    }

    function getAllFlips(grid, r, c, player) {
        if (grid[r][c] !== EMPTY) return [];
        let all = [];
        for (const [dr, dc] of DIRS) all = all.concat(getFlipsInDirection(grid, r, c, dr, dc, player));
        return all;
    }

    function getValidMoves(grid, player) {
        const moves = [];
        for (let r = 0; r < SIZE; r++) {
            for (let c = 0; c < SIZE; c++) {
                if (grid[r][c] !== EMPTY) continue;
                if (getAllFlips(grid, r, c, player).length > 0) moves.push({ r, c });
            }
        }
        return moves;
    }

    function applyMove(grid, r, c, player) {
        const flips = getAllFlips(grid, r, c, player);
        grid[r][c] = player;
        flips.forEach(([fr, fc]) => { grid[fr][fc] = player; });
        return flips.length;
    }

    function countDiscs(grid) {
        let black = 0, white = 0;
        for (let r = 0; r < SIZE; r++) for (let c = 0; c < SIZE; c++) {
            if (grid[r][c] === BLACK) black++;
            else if (grid[r][c] === WHITE) white++;
        }
        return { black, white };
    }

    const WEIGHTS = [
        [120, -20, 20, 5, 5, 20, -20, 120],
        [-20, -40, -5, -5, -5, -5, -40, -20],
        [20, -5, 15, 3, 3, 15, -5, 20],
        [5, -5, 3, 3, 3, 3, -5, 5],
        [5, -5, 3, 3, 3, 3, -5, 5],
        [20, -5, 15, 3, 3, 15, -5, 20],
        [-20, -40, -5, -5, -5, -5, -40, -20],
        [120, -20, 20, 5, 5, 20, -20, 120],
    ];

    function evaluate(grid, aiPlayer) {
        const opp = opponent(aiPlayer);
        let score = 0;
        for (let r = 0; r < SIZE; r++) {
            for (let c = 0; c < SIZE; c++) {
                if (grid[r][c] === aiPlayer) score += WEIGHTS[r][c];
                else if (grid[r][c] === opp) score -= WEIGHTS[r][c];
            }
        }
        const myMoves = getValidMoves(grid, aiPlayer).length;
        const oppMoves = getValidMoves(grid, opp).length;
        score += (myMoves - oppMoves) * 8;
        return score;
    }

    function minimax(grid, depth, player, aiPlayer, alpha, beta) {
        const moves = getValidMoves(grid, player);
        if (depth === 0) return evaluate(grid, aiPlayer);

        if (moves.length === 0) {
            const oppMoves = getValidMoves(grid, opponent(player));
            if (oppMoves.length === 0) return evaluate(grid, aiPlayer);
            return minimax(grid, depth - 1, opponent(player), aiPlayer, alpha, beta);
        }

        const maximizing = player === aiPlayer;
        let best = maximizing ? -Infinity : Infinity;
        for (const { r, c } of moves) {
            const newGrid = cloneGrid(grid);
            applyMove(newGrid, r, c, player);
            const val = minimax(newGrid, depth - 1, opponent(player), aiPlayer, alpha, beta);
            if (maximizing) { best = Math.max(best, val); alpha = Math.max(alpha, val); }
            else { best = Math.min(best, val); beta = Math.min(beta, val); }
            if (beta <= alpha) break;
        }
        return best;
    }

    function findBestMove(grid, aiPlayer, depth) {
        const moves = getValidMoves(grid, aiPlayer);
        if (moves.length === 0) return null;
        let bestMove = moves[0], bestScore = -Infinity;
        for (const { r, c } of moves) {
            const newGrid = cloneGrid(grid);
            applyMove(newGrid, r, c, aiPlayer);
            const score = minimax(newGrid, depth - 1, opponent(aiPlayer), aiPlayer, -Infinity, Infinity);
            if (score > bestScore) { bestScore = score; bestMove = { r, c }; }
        }
        return bestMove;
    }

    // ---------- 게임 상태 ----------
    const CELL = 50;
    const canvas = container.querySelector('#othello-board');
    const ctx = canvas.getContext('2d');

    const turnEl = container.querySelector('#othello-turn');
    const blackCountEl = container.querySelector('#othello-black-count');
    const whiteCountEl = container.querySelector('#othello-white-count');
    const winsEl = container.querySelector('#othello-wins');
    const lossesEl = container.querySelector('#othello-losses');
    const drawsEl = container.querySelector('#othello-draws');

    const overlay = container.querySelector('#othello-overlay');
    const overlayTitle = container.querySelector('#othello-overlay-title');
    const overlayMsg = container.querySelector('#othello-overlay-msg');
    const btnOverlay = container.querySelector('#othello-btn-overlay-action');

    const btnStart = container.querySelector('#othello-btn-start');
    const btnSurrender = container.querySelector('#othello-btn-surrender');

    let grid = makeInitialGrid();
    let currentTurn = BLACK;
    let isGameOver = true;
    let isAiThinking = false;
    let validMovesForCurrent = [];
    let aiTimeoutId = null;
    let wins = 0, losses = 0, draws = 0;

    function loadStats() {
        wins = parseInt(localStorage.getItem('ym_othello_wins') || '0', 10);
        losses = parseInt(localStorage.getItem('ym_othello_losses') || '0', 10);
        draws = parseInt(localStorage.getItem('ym_othello_draws') || '0', 10);
    }
    function saveStats() {
        localStorage.setItem('ym_othello_wins', String(wins));
        localStorage.setItem('ym_othello_losses', String(losses));
        localStorage.setItem('ym_othello_draws', String(draws));
    }

    function updateStats() {
        const counts = countDiscs(grid);
        blackCountEl.textContent = String(counts.black);
        whiteCountEl.textContent = String(counts.white);
        winsEl.textContent = String(wins);
        lossesEl.textContent = String(losses);
        drawsEl.textContent = String(draws);

        if (isGameOver) turnEl.textContent = '-';
        else if (isAiThinking) turnEl.textContent = 'AI 생각 중...';
        else turnEl.textContent = currentTurn === BLACK ? '나 (흑돌)' : 'AI (백돌)';
    }

    // ---------- 렌더링 ----------
    function draw() {
        ctx.fillStyle = '#0f5c34';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        ctx.strokeStyle = '#0b3f24';
        ctx.lineWidth = 1;
        for (let i = 0; i <= SIZE; i++) {
            ctx.beginPath(); ctx.moveTo(i * CELL, 0); ctx.lineTo(i * CELL, canvas.height); ctx.stroke();
            ctx.beginPath(); ctx.moveTo(0, i * CELL); ctx.lineTo(canvas.width, i * CELL); ctx.stroke();
        }

        for (let r = 0; r < SIZE; r++) {
            for (let c = 0; c < SIZE; c++) {
                if (grid[r][c] === EMPTY) continue;
                drawDisc(r, c, grid[r][c]);
            }
        }

        if (!isGameOver && !isAiThinking && currentTurn === BLACK) {
            ctx.fillStyle = 'rgba(255,255,255,0.35)';
            validMovesForCurrent.forEach(({ r, c }) => {
                ctx.beginPath();
                ctx.arc(c * CELL + CELL / 2, r * CELL + CELL / 2, 5, 0, Math.PI * 2);
                ctx.fill();
            });
        }
    }

    function drawDisc(r, c, stone) {
        const cx = c * CELL + CELL / 2, cy = r * CELL + CELL / 2;
        const rad = CELL * 0.4;
        ctx.beginPath();
        ctx.arc(cx, cy, rad, 0, Math.PI * 2);
        ctx.fillStyle = stone === BLACK ? '#111827' : '#f8fafc';
        ctx.fill();
        ctx.strokeStyle = 'rgba(0,0,0,0.3)';
        ctx.lineWidth = 1;
        ctx.stroke();
    }

    // ---------- 게임 흐름 ----------
    function refreshValidMoves() {
        validMovesForCurrent = isGameOver ? [] : getValidMoves(grid, currentTurn);
    }

    function checkGameEnd() {
        const blackMoves = getValidMoves(grid, BLACK);
        const whiteMoves = getValidMoves(grid, WHITE);
        if (blackMoves.length === 0 && whiteMoves.length === 0) {
            endGame();
            return true;
        }
        return false;
    }

    function endGame() {
        isGameOver = true;
        isAiThinking = false;
        clearTimeout(aiTimeoutId);
        btnStart.innerHTML = '<i class="fa-solid fa-play"></i> 새 게임';
        btnSurrender.disabled = true;

        const counts = countDiscs(grid);
        let result;
        if (counts.black > counts.white) result = 'win';
        else if (counts.black < counts.white) result = 'lose';
        else result = 'draw';

        if (result === 'win') {
            wins++;
            hub.setStatusBadge('WIN', 'won');
            overlayTitle.textContent = '🎉 승리했습니다!';
            overlayTitle.style.color = '#10b981';
        } else if (result === 'lose') {
            losses++;
            hub.setStatusBadge('LOSE', 'lost');
            overlayTitle.textContent = '💥 패배했습니다';
            overlayTitle.style.color = '#ef4444';
        } else {
            draws++;
            hub.setStatusBadge('DRAW', '');
            overlayTitle.textContent = '🤝 무승부';
            overlayTitle.style.color = '#f59e0b';
        }
        overlayMsg.textContent = `흑돌 ${counts.black} : 백돌 ${counts.white}`;
        saveStats();
        updateStats();
        draw();
        btnOverlay.textContent = '다시 시작';
        overlay.dataset.nextAction = 'restart';
        overlay.classList.remove('hidden');
    }

    function proceedTurn() {
        if (checkGameEnd()) return;
        refreshValidMoves();

        if (currentTurn === BLACK && validMovesForCurrent.length === 0) {
            // 플레이어 패스
            hub.setStatusBadge('PASS', '');
            currentTurn = WHITE;
            updateStats();
            draw();
            proceedTurn();
            return;
        }

        if (currentTurn === WHITE) {
            if (validMovesForCurrent.length === 0) {
                hub.setStatusBadge('PASS', '');
                currentTurn = BLACK;
                updateStats();
                draw();
                proceedTurn();
                return;
            }
            isAiThinking = true;
            updateStats();
            draw();
            aiTimeoutId = setTimeout(aiMove, 200);
            return;
        }

        updateStats();
        draw();
    }

    function aiMove() {
        if (isGameOver) return;
        const move = findBestMove(grid, WHITE, AI_DEPTH);
        isAiThinking = false;
        if (!move) { currentTurn = BLACK; proceedTurn(); return; }

        applyMove(grid, move.r, move.c, WHITE);
        currentTurn = BLACK;
        proceedTurn();
    }

    function playerMove(r, c) {
        if (isGameOver || isAiThinking || currentTurn !== BLACK) return;
        if (!inBounds(r, c)) return;
        if (getAllFlips(grid, r, c, BLACK).length === 0) return;

        applyMove(grid, r, c, BLACK);
        currentTurn = WHITE;
        proceedTurn();
    }

    function onCanvasClick(evt) {
        if (isGameOver || isAiThinking || currentTurn !== BLACK) return;
        const rect = canvas.getBoundingClientRect();
        const scaleX = canvas.width / rect.width;
        const scaleY = canvas.height / rect.height;
        const px = (evt.clientX - rect.left) * scaleX;
        const py = (evt.clientY - rect.top) * scaleY;
        const c = Math.floor(px / CELL), r = Math.floor(py / CELL);
        playerMove(r, c);
    }

    function start() {
        grid = makeInitialGrid();
        currentTurn = BLACK;
        isGameOver = false;
        isAiThinking = false;
        clearTimeout(aiTimeoutId);

        btnStart.innerHTML = '<i class="fa-solid fa-rotate-right"></i> 다시 시작';
        btnSurrender.disabled = false;
        overlay.classList.add('hidden');
        hub.setStatusBadge('PLAYING (OTHELLO)', 'playing');

        refreshValidMoves();
        updateStats();
        draw();
    }

    function surrender() {
        if (isGameOver) return;
        isGameOver = true;
        isAiThinking = false;
        clearTimeout(aiTimeoutId);
        losses++;
        saveStats();

        btnStart.innerHTML = '<i class="fa-solid fa-play"></i> 새 게임';
        btnSurrender.disabled = true;
        hub.setStatusBadge('LOSE', 'lost');
        overlayTitle.textContent = '🏳️ 기권했습니다';
        overlayTitle.style.color = '#ef4444';
        const counts = countDiscs(grid);
        overlayMsg.textContent = `흑돌 ${counts.black} : 백돌 ${counts.white} (기권)`;
        btnOverlay.textContent = '다시 시작';
        overlay.dataset.nextAction = 'restart';
        overlay.classList.remove('hidden');
        updateStats();
    }

    function reset() {
        isGameOver = true;
        isAiThinking = false;
        clearTimeout(aiTimeoutId);
        grid = makeInitialGrid();
        currentTurn = BLACK;
        validMovesForCurrent = [];

        btnStart.innerHTML = '<i class="fa-solid fa-play"></i> 새 게임';
        btnSurrender.disabled = true;
        overlay.classList.add('hidden');

        hub.setStatusBadge('READY (OTHELLO)', '');
        loadStats();
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
            btnStart.onclick = start;
            btnSurrender.onclick = surrender;
            btnOverlay.onclick = () => start();
            canvas.addEventListener('click', onCanvasClick);

            reset();
        

            setupPanelToggle('othello-left-col', 'othello-toggle-left', 'fa-solid fa-chevron-left', 'fa-solid fa-chevron-right');
            setupPanelToggle('othello-right-col', 'othello-toggle-right', 'fa-solid fa-chevron-right', 'fa-solid fa-chevron-left');
},
        destroy() {
            clearTimeout(aiTimeoutId);
            canvas.removeEventListener('click', onCanvasClick);
        }
    };
});
