// plugins/metadata/ym_mini_game/games/territory/game.js

window.YmMiniGameHub.register('territory', {
    name: '🗺️ 땅따먹기 (Territory)',
    icon: 'fa-solid fa-flag',
    order: 3
}, function (container, hub) {
    const HTML = `
    <div class="territory-game-root">
        <div class="game-sub-bar">
            <span class="game-view-name"><i class="fa-solid fa-flag"></i> TERRITORY</span>
            <div class="sub-actions">
                <button id="terr-btn-start" class="btn-banner primary"><i class="fa-solid fa-play"></i> 게임 시작</button>
                <button id="terr-btn-pause" class="btn-banner secondary" disabled><i class="fa-solid fa-pause"></i> 일시 정지</button>
                <button id="terr-btn-reset" class="btn-banner danger"><i class="fa-solid fa-rotate-left"></i> 초기화</button>
            </div>
        </div>

        <div class="territory-stage-grid">
            <div class="stage-col left-col" id="terr-left-col">
                <button class="panel-toggle-btn" id="terr-toggle-left" title="패널 접기/펼치기"><i class="fa-solid fa-chevron-left"></i></button>
                <div class="panel-content">
                <div class="mini-panel-card">
                    <div class="panel-header"><i class="fa-solid fa-chart-simple"></i> STATISTICS</div>
                    <div class="stat-grid">
                        <div class="stat-box"><span class="stat-lbl">점령률</span><span id="terr-percent" class="stat-val highlight">0%</span></div>
                        <div class="stat-box"><span class="stat-lbl">목표</span><span id="terr-target" class="stat-val">75%</span></div>
                        <div class="stat-box"><span class="stat-lbl">레벨</span><span id="terr-level" class="stat-val">1</span></div>
                        <div class="stat-box"><span class="stat-lbl">생명</span><span id="terr-lives" class="stat-val">❤️❤️❤️</span></div>
                        <div class="stat-box"><span class="stat-lbl">점수</span><span id="terr-score" class="stat-val">0</span></div>
                    </div>
                </div>
                <div class="mini-panel-card">
                    <div class="panel-header"><i class="fa-regular fa-lightbulb"></i> 게임 방법</div>
                    <p class="tip-text">
                        • 테두리(안전지대)에서 나가 선을 그은 뒤 다시 안전지대로 돌아오면, 그 선이 감싼 영역이 내 땅이 됩니다.<br>
                        • 선을 긋는 도중 쥐가 그 선에 닿으면 목숨을 하나 잃고 처음 위치로 돌아갑니다.<br>
                        • 내가 그리던 선을 스스로 다시 밟아도 목숨을 잃습니다.<br>
                        • 목표 점령률에 도달하면 다음 레벨(적 증가·속도 상승)로 넘어갑니다.
                    </p>
                </div>
                </div>
            </div>

            <div class="stage-col center-col">
                <div class="territory-board-frame">
                    <canvas id="terr-board" width="528" height="336"></canvas>
                    <div id="terr-overlay" class="game-overlay hidden">
                        <h2 id="terr-overlay-title">GAME OVER</h2>
                        <p id="terr-overlay-msg">다시 도전해보세요!</p>
                        <button id="terr-btn-overlay-action" class="btn-banner primary">다시 시작</button>
                    </div>
                </div>
            </div>

            <div class="stage-col right-col" id="terr-right-col">
                <button class="panel-toggle-btn" id="terr-toggle-right" title="패널 접기/펼치기"><i class="fa-solid fa-chevron-right"></i></button>
                <div class="panel-content">
                <div class="mini-panel-card">
                    <div class="panel-header"><i class="fa-regular fa-keyboard"></i> 조작 가이드</div>
                    <ul class="key-guide-list">
                        <li><span>이동</span> <div class="key-group"><kbd>↑</kbd><kbd>↓</kbd><kbd>←</kbd><kbd>→</kbd></div></li>
                        <li><span>일시 정지</span> <kbd>P</kbd></li>
                        <li><span>모바일</span> <kbd>방향 버튼</kbd></li>
                    </ul>
                </div>
                <div class="territory-touch-controls">
                    <div class="touch-row">
                        <button class="touch-btn" data-dir="up"><i class="fa-solid fa-arrow-up"></i></button>
                    </div>
                    <div class="touch-row middle">
                        <button class="touch-btn" data-dir="left"><i class="fa-solid fa-arrow-left"></i></button>
                        <button class="touch-btn" data-dir="down"><i class="fa-solid fa-arrow-down"></i></button>
                        <button class="touch-btn" data-dir="right"><i class="fa-solid fa-arrow-right"></i></button>
                    </div>
                </div>
                </div>
            </div>
        </div>
    </div>`;

    container.innerHTML = HTML;

    const COLS = 22, ROWS = 14, CELL = 24;
    const EMPTY = 0, CLAIMED = 1, TRAIL = 2;
    const TARGET_PERCENT = 75;

    let grid = [];
    let player = { x: 0, y: 0, dx: 0, dy: 0 };
    let enemies = [];
    let trailCells = [];
    let lives = 3, score = 0, level = 1, percent = 0;
    let isPlaying = false, isPaused = false, animId = null;
    let lastPlayerMove = 0, lastEnemyMove = 0;
    let playerInterval = 130, enemyInterval = 200;

    const canvas = container.querySelector('#terr-board');
    const ctx = canvas.getContext('2d');

    const percentEl = container.querySelector('#terr-percent');
    const targetEl = container.querySelector('#terr-target');
    const levelEl = container.querySelector('#terr-level');
    const livesEl = container.querySelector('#terr-lives');
    const scoreEl = container.querySelector('#terr-score');

    const overlay = container.querySelector('#terr-overlay');
    const overlayTitle = container.querySelector('#terr-overlay-title');
    const overlayMsg = container.querySelector('#terr-overlay-msg');
    const btnOverlay = container.querySelector('#terr-btn-overlay-action');

    const btnStart = container.querySelector('#terr-btn-start');
    const btnPause = container.querySelector('#terr-btn-pause');
    const btnReset = container.querySelector('#terr-btn-reset');

    function createGrid() {
        const g = [];
        for (let y = 0; y < ROWS; y++) {
            g.push(new Array(COLS).fill(EMPTY));
        }
        for (let x = 0; x < COLS; x++) { g[0][x] = CLAIMED; g[ROWS - 1][x] = CLAIMED; }
        for (let y = 0; y < ROWS; y++) { g[y][0] = CLAIMED; g[y][COLS - 1] = CLAIMED; }
        return g;
    }

    function spawnEnemies(count) {
        const list = [];
        let guard = 0;
        for (let i = 0; i < count; i++) {
            let x, y;
            do {
                x = 2 + Math.floor(Math.random() * (COLS - 4));
                y = 2 + Math.floor(Math.random() * (ROWS - 4));
                guard++;
            } while (grid[y][x] !== EMPTY && guard < 500);
            const dirs = [[1, 1], [1, -1], [-1, 1], [-1, -1]];
            const d = dirs[Math.floor(Math.random() * dirs.length)];
            list.push({ x, y, dx: d[0], dy: d[1] });
        }
        return list;
    }

    function updateStats() {
        percentEl.textContent = percent + '%';
        targetEl.textContent = TARGET_PERCENT + '%';
        levelEl.textContent = level;
        scoreEl.textContent = score;
        livesEl.textContent = '❤️'.repeat(Math.max(0, lives));
    }

    function calcPercent() {
        let claimed = 0, total = 0;
        for (let y = 0; y < ROWS; y++) {
            for (let x = 0; x < COLS; x++) {
                total++;
                if (grid[y][x] === CLAIMED) claimed++;
            }
        }
        return Math.floor((claimed / total) * 100);
    }

    function clearTrail(toValue) {
        trailCells.forEach(([tx, ty]) => { if (grid[ty][tx] === TRAIL) grid[ty][tx] = toValue; });
        trailCells = [];
    }

    function commitTerritory() {
        // 1. 그려진 선을 영토로 확정
        trailCells.forEach(([tx, ty]) => { grid[ty][tx] = CLAIMED; });
        trailCells = [];

        // 2. 적이 서 있는 빈 칸에서 BFS로 "적이 도달 가능한" 빈 칸을 모두 찾는다
        const visited = [];
        for (let y = 0; y < ROWS; y++) visited.push(new Array(COLS).fill(false));

        const queue = [];
        enemies.forEach(e => {
            if (grid[e.y][e.x] === EMPTY && !visited[e.y][e.x]) {
                visited[e.y][e.x] = true;
                queue.push([e.x, e.y]);
            }
        });

        while (queue.length) {
            const [cx, cy] = queue.shift();
            const neighbors = [[cx + 1, cy], [cx - 1, cy], [cx, cy + 1], [cx, cy - 1]];
            for (const [nx, ny] of neighbors) {
                if (nx >= 0 && nx < COLS && ny >= 0 && ny < ROWS && !visited[ny][nx] && grid[ny][nx] === EMPTY) {
                    visited[ny][nx] = true;
                    queue.push([nx, ny]);
                }
            }
        }

        // 3. 적이 도달하지 못한 빈 칸 = 선으로 감싸인 영역 -> 점령 처리
        let gained = 0;
        for (let y = 0; y < ROWS; y++) {
            for (let x = 0; x < COLS; x++) {
                if (grid[y][x] === EMPTY && !visited[y][x]) {
                    grid[y][x] = CLAIMED;
                    gained++;
                }
            }
        }

        score += 10 + gained * 2;
        percent = calcPercent();
        updateStats();

        if (percent >= TARGET_PERCENT) {
            levelUp();
        }
    }

    function levelUp() {
        isPlaying = false;
        cancelAnimationFrame(animId);
        hub.setStatusBadge('LEVEL CLEAR', 'won');
        overlayTitle.textContent = `🎉 레벨 ${level} 클리어!`;
        overlayTitle.style.color = '#10b981';
        overlayMsg.textContent = `점령률 ${percent}% 달성! 다음 레벨로 진행합니다.`;
        btnOverlay.textContent = '다음 레벨';
        overlay.dataset.nextAction = 'nextLevel';
        overlay.classList.remove('hidden');
    }

    function nextLevel() {
        level++;
        grid = createGrid();
        enemies = spawnEnemies(1 + level);
        enemyInterval = Math.max(90, 200 - (level - 1) * 12);
        player = { x: Math.floor(COLS / 2), y: 0, dx: 0, dy: 0 };
        trailCells = [];
        percent = calcPercent();
        updateStats();
        overlay.classList.add('hidden');
        isPlaying = true; isPaused = false;
        hub.setStatusBadge('PLAYING (TERRITORY)', 'playing');
        lastPlayerMove = 0; lastEnemyMove = 0;
        cancelAnimationFrame(animId);
        loop(performance.now());
    }

    function loseLife() {
        lives--;
        clearTrail(EMPTY);
        player = { x: Math.floor(COLS / 2), y: 0, dx: 0, dy: 0 };
        updateStats();
        if (lives <= 0) { gameOver(); return; }
        hub.setStatusBadge('LIFE LOST', 'lost');
    }

    function movePlayer() {
        if (player.dx === 0 && player.dy === 0) return;
        const nx = player.x + player.dx, ny = player.y + player.dy;
        if (nx < 0 || nx >= COLS || ny < 0 || ny >= ROWS) return;

        // 쥐가 있는 칸으로 이동하면 즉시 충돌 처리 (쥐의 이동 타이밍을 기다리지 않음)
        if (enemies.some(e => e.x === nx && e.y === ny)) { loseLife(); return; }

        const target = grid[ny][nx];

        if (target === TRAIL) { loseLife(); return; }

        player.x = nx; player.y = ny;

        if (target === EMPTY) {
            grid[ny][nx] = TRAIL;
            trailCells.push([nx, ny]);
        } else if (target === CLAIMED && trailCells.length > 0) {
            commitTerritory();
        }
    }

    function moveEnemies() {
        enemies.forEach(e => {
            let nx = e.x + e.dx, ny = e.y + e.dy;
            if (nx < 0 || nx >= COLS || grid[e.y][nx] !== EMPTY) e.dx *= -1;
            if (ny < 0 || ny >= ROWS || grid[ny][e.x] !== EMPTY) e.dy *= -1;
            nx = e.x + e.dx; ny = e.y + e.dy;
            if (nx >= 0 && nx < COLS && ny >= 0 && ny < ROWS && grid[ny][nx] === EMPTY) {
                e.x = nx; e.y = ny;
            }
            if (grid[e.y][e.x] === TRAIL || (e.x === player.x && e.y === player.y)) {
                loseLife();
            }
        });
    }

    function draw() {
        ctx.fillStyle = '#0b1220';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        for (let y = 0; y < ROWS; y++) {
            for (let x = 0; x < COLS; x++) {
                const v = grid[y][x];
                if (v === CLAIMED) ctx.fillStyle = 'rgba(16,185,129,0.35)';
                else continue;
                ctx.fillRect(x * CELL, y * CELL, CELL, CELL);
            }
        }

        ctx.strokeStyle = 'rgba(255,255,255,0.05)';
        for (let x = 0; x <= COLS; x++) {
            ctx.beginPath(); ctx.moveTo(x * CELL, 0); ctx.lineTo(x * CELL, canvas.height); ctx.stroke();
        }
        for (let y = 0; y <= ROWS; y++) {
            ctx.beginPath(); ctx.moveTo(0, y * CELL); ctx.lineTo(canvas.width, y * CELL); ctx.stroke();
        }

        // 그리는 중인 선(트레일)은 두꺼운 칸 채우기 대신 얇은 실선으로 표시
        if (trailCells.length > 0) {
            ctx.strokeStyle = 'rgba(250,204,21,0.9)';
            ctx.lineWidth = 3;
            ctx.lineJoin = 'round';
            ctx.lineCap = 'round';
            ctx.beginPath();
            const [px0, py0] = trailCells[0];
            ctx.moveTo(px0 * CELL + CELL / 2, py0 * CELL + CELL / 2);
            for (let i = 1; i < trailCells.length; i++) {
                const [tx, ty] = trailCells[i];
                ctx.lineTo(tx * CELL + CELL / 2, ty * CELL + CELL / 2);
            }
            ctx.lineTo(player.x * CELL + CELL / 2, player.y * CELL + CELL / 2);
            ctx.stroke();
        }

        ctx.fillStyle = '#38bdf8';
        ctx.beginPath();
        ctx.arc(player.x * CELL + CELL / 2, player.y * CELL + CELL / 2, CELL / 2.4, 0, Math.PI * 2);
        ctx.fill();

        enemies.forEach(e => {
            drawMouse(e.x * CELL + CELL / 2, e.y * CELL + CELL / 2, e.dx, e.dy);
        });
    }

    function drawMouse(cx, cy, dx, dy) {
        // 이동 방향으로 자연스럽게 향하도록 회전 (대각선 이동이라도 부드럽게 보이게 각도 계산)
        const angle = Math.atan2(dy || 0.0001, dx || 0.0001);
        const r = CELL / 2.3;

        ctx.save();
        ctx.translate(cx, cy);
        ctx.rotate(angle);

        // 꼬리 (진행 방향 반대쪽으로 살짝 흔들리는 곡선)
        ctx.strokeStyle = '#94a3b8';
        ctx.lineWidth = Math.max(1, CELL * 0.05);
        ctx.beginPath();
        ctx.moveTo(-r * 0.85, 0);
        ctx.quadraticCurveTo(-r * 1.6, r * 0.55, -r * 2.1, r * 0.05);
        ctx.stroke();

        // 몸통
        ctx.fillStyle = '#cbd5e1';
        ctx.beginPath();
        ctx.ellipse(0, 0, r * 0.95, r * 0.68, 0, 0, Math.PI * 2);
        ctx.fill();

        // 귀 (양쪽)
        ctx.fillStyle = '#f9a8d4';
        ctx.beginPath();
        ctx.arc(r * 0.35, -r * 0.55, r * 0.34, 0, Math.PI * 2);
        ctx.fill();
        ctx.beginPath();
        ctx.arc(r * 0.35, r * 0.55, r * 0.34, 0, Math.PI * 2);
        ctx.fill();

        // 코
        ctx.fillStyle = '#f472b6';
        ctx.beginPath();
        ctx.arc(r * 0.95, 0, r * 0.16, 0, Math.PI * 2);
        ctx.fill();

        // 눈
        ctx.fillStyle = '#1f2937';
        ctx.beginPath();
        ctx.arc(r * 0.4, -r * 0.18, r * 0.09, 0, Math.PI * 2);
        ctx.fill();
        ctx.beginPath();
        ctx.arc(r * 0.4, r * 0.18, r * 0.09, 0, Math.PI * 2);
        ctx.fill();

        ctx.restore();
    }

    function loop(time = 0) {
        if (!isPlaying || isPaused) return;
        if (time - lastPlayerMove > playerInterval) { movePlayer(); lastPlayerMove = time; }
        if (isPlaying && time - lastEnemyMove > enemyInterval) { moveEnemies(); lastEnemyMove = time; }
        draw();
        if (isPlaying && !isPaused) animId = requestAnimationFrame(loop);
    }

    function start() {
        grid = createGrid();
        level = 1; lives = 3; score = 0;
        enemies = spawnEnemies(2);
        enemyInterval = 200;
        player = { x: Math.floor(COLS / 2), y: 0, dx: 0, dy: 0 };
        trailCells = [];
        percent = calcPercent();
        updateStats();
        isPlaying = true; isPaused = false;
        btnStart.innerHTML = '<i class="fa-solid fa-gamepad"></i> 진행 중';
        btnStart.disabled = true;
        btnPause.disabled = false;
        btnPause.innerHTML = '<i class="fa-solid fa-pause"></i> 일시 정지';
        hub.setStatusBadge('PLAYING (TERRITORY)', 'playing');
        overlay.classList.add('hidden');
        lastPlayerMove = 0; lastEnemyMove = 0;
        cancelAnimationFrame(animId);
        loop(performance.now());
    }

    function togglePause() {
        if (!isPlaying) return;
        isPaused = !isPaused;
        if (isPaused) {
            btnPause.innerHTML = '<i class="fa-solid fa-play"></i> 계속 하기';
            hub.setStatusBadge('PAUSED', 'paused');
            overlayTitle.textContent = 'PAUSED';
            overlayTitle.style.color = '#f59e0b';
            overlayMsg.textContent = '땅따먹기가 일시정지되었습니다.';
            btnOverlay.textContent = '계속 진행';
            overlay.dataset.nextAction = 'resume';
            overlay.classList.remove('hidden');
        } else {
            btnPause.innerHTML = '<i class="fa-solid fa-pause"></i> 일시 정지';
            hub.setStatusBadge('PLAYING (TERRITORY)', 'playing');
            overlay.classList.add('hidden');
            lastPlayerMove = 0; lastEnemyMove = 0;
            loop(performance.now());
        }
    }

    function gameOver() {
        isPlaying = false;
        cancelAnimationFrame(animId);
        btnStart.innerHTML = '<i class="fa-solid fa-play"></i> 새 게임';
        btnStart.disabled = false;
        btnPause.disabled = true;
        hub.setStatusBadge('GAME OVER', 'lost');
        overlayTitle.textContent = '💥 GAME OVER';
        overlayTitle.style.color = '#ef4444';
        overlayMsg.textContent = `최종 점령률 ${percent}% · 점수 ${score}점 (레벨 ${level})`;
        btnOverlay.textContent = '다시 시작';
        overlay.dataset.nextAction = 'restart';
        overlay.classList.remove('hidden');
    }

    function reset() {
        isPlaying = false; isPaused = false;
        cancelAnimationFrame(animId);
        grid = createGrid();
        enemies = [];
        trailCells = [];
        level = 1; lives = 3; score = 0; percent = 0;
        player = { x: Math.floor(COLS / 2), y: 0, dx: 0, dy: 0 };
        updateStats();
        btnStart.innerHTML = '<i class="fa-solid fa-play"></i> 게임 시작';
        btnStart.disabled = false;
        btnPause.disabled = true;
        overlay.classList.add('hidden');
        hub.setStatusBadge('READY (TERRITORY)', '');
        draw();
    }

    function setDirection(dx, dy) {
        if (!isPlaying || isPaused) return;
        player.dx = dx; player.dy = dy;
    }

    function onKeyDown(e) {
        if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.code)) {
            if (isPlaying && !isPaused) e.preventDefault();
        }
        switch (e.code) {
            case 'ArrowLeft': setDirection(-1, 0); break;
            case 'ArrowRight': setDirection(1, 0); break;
            case 'ArrowUp': setDirection(0, -1); break;
            case 'ArrowDown': setDirection(0, 1); break;
            case 'KeyP': togglePause(); break;
        }
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
            btnPause.onclick = togglePause;
            btnReset.onclick = reset;
            btnOverlay.onclick = () => {
                const action = overlay.dataset.nextAction;
                if (action === 'nextLevel') nextLevel();
                else if (action === 'resume') togglePause();
                else start();
            };

            container.querySelectorAll('.territory-touch-controls .touch-btn').forEach(btn => {
                btn.onclick = (e) => {
                    e.preventDefault();
                    const dir = btn.dataset.dir;
                    if (dir === 'up') setDirection(0, -1);
                    if (dir === 'down') setDirection(0, 1);
                    if (dir === 'left') setDirection(-1, 0);
                    if (dir === 'right') setDirection(1, 0);
                };
            });

            setupPanelToggle('terr-left-col', 'terr-toggle-left', 'fa-solid fa-chevron-left', 'fa-solid fa-chevron-right');
            setupPanelToggle('terr-right-col', 'terr-toggle-right', 'fa-solid fa-chevron-right', 'fa-solid fa-chevron-left');

            window.addEventListener('keydown', onKeyDown);
            reset();
        },
        destroy() {
            isPlaying = false;
            cancelAnimationFrame(animId);
            window.removeEventListener('keydown', onKeyDown);
        }
    };
});
