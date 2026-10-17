// plugins/metadata/ym_mini_game/games/omok/game.js

window.YmMiniGameHub.register('omok', {
    name: '⚫ 오목 (Omok)',
    icon: 'fa-solid fa-circle-dot',
    order: 4
}, function (container, hub) {
    const HTML = `
    <div class="omok-game-root">
        <div class="game-sub-bar">
            <span class="game-view-name"><i class="fa-solid fa-circle-dot"></i> OMOK</span>
            <div class="sub-actions">
                <button id="omok-btn-start" class="btn-banner primary"><i class="fa-solid fa-play"></i> 새 게임</button>
                <button id="omok-btn-undo" class="btn-banner secondary" disabled><i class="fa-solid fa-rotate-left"></i> 무르기</button>
                <button id="omok-btn-surrender" class="btn-banner danger" disabled><i class="fa-solid fa-flag"></i> 기권</button>
            </div>
        </div>

        <div class="omok-stage-grid">
            <div class="stage-col left-col" id="omok-left-col">
            <button class="panel-toggle-btn" id="omok-toggle-left" title="패널 접기/펼치기"><i class="fa-solid fa-chevron-left"></i></button>
            <div class="panel-content">
                <div class="mini-panel-card">
                    <div class="panel-header"><i class="fa-solid fa-chart-simple"></i> STATISTICS</div>
                    <div class="stat-grid">
                        <div class="stat-box"><span class="stat-lbl">현재 차례</span><span id="omok-turn" class="stat-val highlight">-</span></div>
                        <div class="stat-box"><span class="stat-lbl">수(手)</span><span id="omok-move-count" class="stat-val">0</span></div>
                        <div class="stat-box"><span class="stat-lbl">승</span><span id="omok-wins" class="stat-val">0</span></div>
                        <div class="stat-box"><span class="stat-lbl">패</span><span id="omok-losses" class="stat-val">0</span></div>
                        <div class="stat-box"><span class="stat-lbl">무</span><span id="omok-draws" class="stat-val">0</span></div>
                    </div>
                </div>
                <div class="mini-panel-card">
                    <div class="panel-header"><i class="fa-regular fa-lightbulb"></i> 게임 방법</div>
                    <p class="tip-text">
                        • 당신은 흑돌, AI는 백돌입니다. 흑돌이 먼저 둡니다.<br>
                        • 가로·세로·대각선 중 한 방향으로 5개를 먼저 연결하면 승리합니다.<br>
                        • 실수했다면 "무르기"로 직전 한 수(내 돌+AI 돌)를 되돌릴 수 있습니다.
                    </p>
                </div>
            
            </div></div>

            <div class="stage-col center-col">
                <div class="omok-board-frame">
                    <canvas id="omok-board" width="440" height="440"></canvas>
                    <div id="omok-overlay" class="game-overlay hidden">
                        <h2 id="omok-overlay-title">GAME OVER</h2>
                        <p id="omok-overlay-msg">다시 도전해보세요!</p>
                        <button id="omok-btn-overlay-action" class="btn-banner primary">다시 시작</button>
                    </div>
                </div>
            </div>

            <div class="stage-col right-col" id="omok-right-col">
            <button class="panel-toggle-btn" id="omok-toggle-right" title="패널 접기/펼치기"><i class="fa-solid fa-chevron-right"></i></button>
            <div class="panel-content">
                <div class="mini-panel-card">
                    <div class="panel-header"><i class="fa-regular fa-keyboard"></i> 조작 가이드</div>
                    <ul class="key-guide-list">
                        <li><span>착수</span> <kbd>보드 클릭/탭</kbd></li>
                        <li><span>무르기</span> <kbd>버튼 클릭</kbd></li>
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

    const SIZE = 15, CELL = 28, MARGIN = 24;
    const EMPTY = 0, BLACK = 1, WHITE = 2; // BLACK = 플레이어(선공), WHITE = AI
    const BOARD_PX = MARGIN * 2 + CELL * (SIZE - 1);

    let grid = [];
    let moveHistory = []; // [{x,y,stone}, ...]
    let currentTurn = BLACK;
    let isGameOver = true;
    let isAiThinking = false;
    let winningLine = null;
    let aiTimeoutId = null;

    let wins = 0, losses = 0, draws = 0;

    const canvas = container.querySelector('#omok-board');
    const ctx = canvas.getContext('2d');

    const turnEl = container.querySelector('#omok-turn');
    const moveCountEl = container.querySelector('#omok-move-count');
    const winsEl = container.querySelector('#omok-wins');
    const lossesEl = container.querySelector('#omok-losses');
    const drawsEl = container.querySelector('#omok-draws');

    const overlay = container.querySelector('#omok-overlay');
    const overlayTitle = container.querySelector('#omok-overlay-title');
    const overlayMsg = container.querySelector('#omok-overlay-msg');
    const btnOverlay = container.querySelector('#omok-btn-overlay-action');

    const btnStart = container.querySelector('#omok-btn-start');
    const btnUndo = container.querySelector('#omok-btn-undo');
    const btnSurrender = container.querySelector('#omok-btn-surrender');

    function inBounds(x, y) { return x >= 0 && x < SIZE && y >= 0 && y < SIZE; }

    function createGrid() {
        const g = [];
        for (let y = 0; y < SIZE; y++) g.push(new Array(SIZE).fill(EMPTY));
        return g;
    }

    function loadStats() {
        wins = parseInt(localStorage.getItem('ym_omok_wins') || '0', 10);
        losses = parseInt(localStorage.getItem('ym_omok_losses') || '0', 10);
        draws = parseInt(localStorage.getItem('ym_omok_draws') || '0', 10);
    }

    function saveStats() {
        localStorage.setItem('ym_omok_wins', String(wins));
        localStorage.setItem('ym_omok_losses', String(losses));
        localStorage.setItem('ym_omok_draws', String(draws));
    }

    function updateStats() {
        moveCountEl.textContent = String(moveHistory.length);
        winsEl.textContent = String(wins);
        lossesEl.textContent = String(losses);
        drawsEl.textContent = String(draws);
        if (isGameOver) {
            turnEl.textContent = '-';
        } else if (isAiThinking) {
            turnEl.textContent = 'AI 생각 중...';
        } else {
            turnEl.textContent = currentTurn === BLACK ? '나 (흑돌)' : 'AI (백돌)';
        }
    }

    // ---------- 승리 판정 ----------
    function checkWin(g, x, y, stone) {
        const dirs = [[1, 0], [0, 1], [1, 1], [1, -1]];
        for (const [dx, dy] of dirs) {
            let cells = [[x, y]];
            let cx = x + dx, cy = y + dy;
            while (inBounds(cx, cy) && g[cy][cx] === stone) { cells.push([cx, cy]); cx += dx; cy += dy; }
            cx = x - dx; cy = y - dy;
            while (inBounds(cx, cy) && g[cy][cx] === stone) { cells.unshift([cx, cy]); cx -= dx; cy -= dy; }
            if (cells.length >= 5) return cells;
        }
        return null;
    }

    function isBoardFull(g) {
        for (let y = 0; y < SIZE; y++) for (let x = 0; x < SIZE; x++) if (g[y][x] === EMPTY) return false;
        return true;
    }

    // ---------- AI 평가 함수 ----------
    function lineScore(length, openEnds) {
        if (length >= 5) return 100000;
        if (length === 4) return openEnds === 2 ? 100000 : (openEnds === 1 ? 10000 : 0);
        if (length === 3) return openEnds === 2 ? 5000 : (openEnds === 1 ? 200 : 0);
        if (length === 2) return openEnds === 2 ? 100 : (openEnds === 1 ? 10 : 0);
        if (length === 1) return openEnds === 2 ? 5 : 1;
        return 0;
    }

    function evaluateDirection(g, x, y, dx, dy, stone) {
        let posCount = 0;
        let cx = x + dx, cy = y + dy;
        while (inBounds(cx, cy) && g[cy][cx] === stone) { posCount++; cx += dx; cy += dy; }
        const posOpen = inBounds(cx, cy) && g[cy][cx] === EMPTY;

        let negCount = 0;
        let nx = x - dx, ny = y - dy;
        while (inBounds(nx, ny) && g[ny][nx] === stone) { negCount++; nx -= dx; ny -= dy; }
        const negOpen = inBounds(nx, ny) && g[ny][nx] === EMPTY;

        const length = 1 + posCount + negCount;
        const openEnds = (posOpen ? 1 : 0) + (negOpen ? 1 : 0);
        return lineScore(length, openEnds);
    }

    function evaluatePoint(g, x, y, stone) {
        const dirs = [[1, 0], [0, 1], [1, 1], [1, -1]];
        let total = 0;
        for (const [dx, dy] of dirs) total += evaluateDirection(g, x, y, dx, dy, stone);
        return total;
    }

    function hasNeighbor(g, x, y, radius) {
        for (let dy = -radius; dy <= radius; dy++) {
            for (let dx = -radius; dx <= radius; dx++) {
                if (dx === 0 && dy === 0) continue;
                const nx = x + dx, ny = y + dy;
                if (inBounds(nx, ny) && g[ny][nx] !== EMPTY) return true;
            }
        }
        return false;
    }

    function findBestAiMove() {
        const center = Math.floor(SIZE / 2);
        if (moveHistory.length === 0) return { x: center, y: center };

        let best = null, bestScore = -Infinity;
        for (let y = 0; y < SIZE; y++) {
            for (let x = 0; x < SIZE; x++) {
                if (grid[y][x] !== EMPTY) continue;
                if (!hasNeighbor(grid, x, y, 2)) continue;

                grid[y][x] = WHITE;
                const aiScore = evaluatePoint(grid, x, y, WHITE);
                grid[y][x] = BLACK;
                const humanScore = evaluatePoint(grid, x, y, BLACK);
                grid[y][x] = EMPTY;

                // 공격 점수 + 방어 가중치(상대 위협을 살짝 더 크게 평가해 방어를 우선)
                const score = aiScore + humanScore * 1.05;
                if (score > bestScore) { bestScore = score; best = { x, y }; }
            }
        }
        return best || { x: center, y: center };
    }

    // ---------- 렌더링 ----------
    function draw() {
        ctx.fillStyle = '#dcb35c';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        ctx.strokeStyle = '#5c3a17';
        ctx.lineWidth = 1;
        for (let i = 0; i < SIZE; i++) {
            const pos = MARGIN + i * CELL;
            ctx.beginPath(); ctx.moveTo(MARGIN, pos); ctx.lineTo(BOARD_PX - MARGIN, pos); ctx.stroke();
            ctx.beginPath(); ctx.moveTo(pos, MARGIN); ctx.lineTo(pos, BOARD_PX - MARGIN); ctx.stroke();
        }

        // 화점(전통 오목판 표식점)
        const starPoints = [3, 7, 11];
        ctx.fillStyle = '#5c3a17';
        starPoints.forEach(sx => {
            starPoints.forEach(sy => {
                ctx.beginPath();
                ctx.arc(MARGIN + sx * CELL, MARGIN + sy * CELL, 3, 0, Math.PI * 2);
                ctx.fill();
            });
        });

        for (let y = 0; y < SIZE; y++) {
            for (let x = 0; x < SIZE; x++) {
                if (grid[y][x] === EMPTY) continue;
                drawStone(x, y, grid[y][x]);
            }
        }

        if (winningLine) {
            ctx.strokeStyle = '#ef4444';
            ctx.lineWidth = 4;
            ctx.beginPath();
            const [sx, sy] = winningLine[0];
            const [ex, ey] = winningLine[winningLine.length - 1];
            ctx.moveTo(MARGIN + sx * CELL, MARGIN + sy * CELL);
            ctx.lineTo(MARGIN + ex * CELL, MARGIN + ey * CELL);
            ctx.stroke();
        }

        // 마지막 착수 표시
        if (moveHistory.length > 0) {
            const last = moveHistory[moveHistory.length - 1];
            ctx.strokeStyle = '#ef4444';
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.arc(MARGIN + last.x * CELL, MARGIN + last.y * CELL, CELL * 0.22, 0, Math.PI * 2);
            ctx.stroke();
        }
    }

    function drawStone(x, y, stone) {
        const cx = MARGIN + x * CELL, cy = MARGIN + y * CELL;
        const r = CELL * 0.42;
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        if (stone === BLACK) {
            ctx.fillStyle = '#111827';
        } else {
            ctx.fillStyle = '#f8fafc';
        }
        ctx.fill();
        ctx.strokeStyle = 'rgba(0,0,0,0.35)';
        ctx.lineWidth = 1;
        ctx.stroke();
    }

    // ---------- 게임 흐름 ----------
    function placeStone(x, y, stone) {
        grid[y][x] = stone;
        moveHistory.push({ x, y, stone });
    }

    function endGame(result) {
        // result: 'win' | 'lose' | 'draw'
        isGameOver = true;
        isAiThinking = false;
        clearTimeout(aiTimeoutId);

        btnStart.innerHTML = '<i class="fa-solid fa-play"></i> 새 게임';
        btnUndo.disabled = true;
        btnSurrender.disabled = true;

        if (result === 'win') {
            wins++;
            hub.setStatusBadge('WIN', 'won');
            overlayTitle.textContent = '🎉 승리했습니다!';
            overlayTitle.style.color = '#10b981';
            overlayMsg.textContent = `${moveHistory.length}수 만에 오목을 완성했습니다.`;
        } else if (result === 'lose') {
            losses++;
            hub.setStatusBadge('LOSE', 'lost');
            overlayTitle.textContent = '💥 패배했습니다';
            overlayTitle.style.color = '#ef4444';
            overlayMsg.textContent = 'AI가 먼저 5개를 연결했습니다. 다시 도전해보세요!';
        } else {
            draws++;
            hub.setStatusBadge('DRAW', '');
            overlayTitle.textContent = '🤝 무승부';
            overlayTitle.style.color = '#f59e0b';
            overlayMsg.textContent = '보드가 가득 찼습니다.';
        }

        saveStats();
        updateStats();
        draw();
        btnOverlay.textContent = '다시 시작';
        overlay.dataset.nextAction = 'restart';
        overlay.classList.remove('hidden');
    }

    function afterMove(x, y, stone) {
        const win = checkWin(grid, x, y, stone);
        if (win) {
            winningLine = win;
            draw();
            endGame(stone === BLACK ? 'win' : 'lose');
            return true;
        }
        if (isBoardFull(grid)) {
            draw();
            endGame('draw');
            return true;
        }
        return false;
    }

    function playerMove(x, y) {
        if (isGameOver || isAiThinking || currentTurn !== BLACK) return;
        if (!inBounds(x, y) || grid[y][x] !== EMPTY) return;

        placeStone(x, y, BLACK);
        updateStats();
        draw();

        if (afterMove(x, y, BLACK)) return;

        currentTurn = WHITE;
        isAiThinking = true;
        updateStats();
        aiTimeoutId = setTimeout(aiMove, 380);
    }

    function aiMove() {
        if (isGameOver) return;
        const move = findBestAiMove();
        isAiThinking = false;
        if (!move) { currentTurn = BLACK; updateStats(); return; }

        placeStone(move.x, move.y, WHITE);
        currentTurn = BLACK;
        updateStats();
        draw();

        afterMove(move.x, move.y, WHITE);
    }

    function onCanvasClick(evt) {
        if (isGameOver || isAiThinking || currentTurn !== BLACK) return;
        const rect = canvas.getBoundingClientRect();
        const scaleX = canvas.width / rect.width;
        const scaleY = canvas.height / rect.height;
        const px = (evt.clientX - rect.left) * scaleX;
        const py = (evt.clientY - rect.top) * scaleY;
        const x = Math.round((px - MARGIN) / CELL);
        const y = Math.round((py - MARGIN) / CELL);
        playerMove(x, y);
    }

    function start() {
        grid = createGrid();
        moveHistory = [];
        currentTurn = BLACK;
        isGameOver = false;
        isAiThinking = false;
        winningLine = null;
        clearTimeout(aiTimeoutId);

        btnStart.innerHTML = '<i class="fa-solid fa-rotate-right"></i> 다시 시작';
        btnUndo.disabled = false;
        btnSurrender.disabled = false;

        overlay.classList.add('hidden');
        hub.setStatusBadge('PLAYING (OMOK)', 'playing');
        updateStats();
        draw();
    }

    function undo() {
        if (isGameOver || isAiThinking) return;
        // 플레이어 턴일 때 무르기 = 마지막 AI 수 + 마지막 내 수까지 함께 되돌림
        if (moveHistory.length < 2) return;
        const last1 = moveHistory.pop(); // AI 마지막 수
        const last2 = moveHistory.pop(); // 내 마지막 수
        grid[last1.y][last1.x] = EMPTY;
        grid[last2.y][last2.x] = EMPTY;
        currentTurn = BLACK;
        winningLine = null;
        updateStats();
        draw();
    }

    function surrender() {
        if (isGameOver) return;
        endGame('lose');
    }

    function reset() {
        isGameOver = true;
        isAiThinking = false;
        clearTimeout(aiTimeoutId);
        grid = createGrid();
        moveHistory = [];
        currentTurn = BLACK;
        winningLine = null;

        btnStart.innerHTML = '<i class="fa-solid fa-play"></i> 새 게임';
        btnUndo.disabled = true;
        btnSurrender.disabled = true;
        overlay.classList.add('hidden');

        hub.setStatusBadge('READY (OMOK)', '');
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
            btnUndo.onclick = undo;
            btnSurrender.onclick = surrender;
            btnOverlay.onclick = () => start();
            canvas.addEventListener('click', onCanvasClick);

            reset();
        

            setupPanelToggle('omok-left-col', 'omok-toggle-left', 'fa-solid fa-chevron-left', 'fa-solid fa-chevron-right');
            setupPanelToggle('omok-right-col', 'omok-toggle-right', 'fa-solid fa-chevron-right', 'fa-solid fa-chevron-left');
},
        destroy() {
            clearTimeout(aiTimeoutId);
            canvas.removeEventListener('click', onCanvasClick);
        }
    };
});
