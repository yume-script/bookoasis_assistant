// plugins/metadata/ym_mini_game/games/picture-territory/game.js

window.YmMiniGameHub.register('picture-territory', {
    name: '🖼️ 그림 땅따먹기 (Picture Reveal)',
    icon: 'fa-solid fa-image',
    order: 12
}, function (container, hub) {
    const HTML = `
    <div class="picture-game-root">
        <div class="game-sub-bar">
            <span class="game-view-name"><i class="fa-solid fa-image"></i> 그림 땅따먹기</span>
            <div class="sub-actions">
                <button id="pic-btn-start" class="btn-banner primary"><i class="fa-solid fa-play"></i> 게임 시작</button>
                <button id="pic-btn-pause" class="btn-banner secondary" disabled><i class="fa-solid fa-pause"></i> 일시 정지</button>
                <button id="pic-btn-reset" class="btn-banner danger"><i class="fa-solid fa-rotate-left"></i> 초기화</button>
            </div>
        </div>

        <div class="picture-stage-grid">
            <div class="stage-col left-col" id="pic-left-col">
            <button class="panel-toggle-btn" id="pic-toggle-left" title="패널 접기/펼치기"><i class="fa-solid fa-chevron-left"></i></button>
            <div class="panel-content">
                <div class="mini-panel-card">
                    <div class="panel-header"><i class="fa-solid fa-chart-simple"></i> STATISTICS</div>
                    <div class="stat-grid">
                        <div class="stat-box"><span class="stat-lbl">공개율</span><span id="pic-percent" class="stat-val highlight">0%</span></div>
                        <div class="stat-box"><span class="stat-lbl">목표</span><span id="pic-target" class="stat-val">75%</span></div>
                        <div class="stat-box"><span class="stat-lbl">레벨</span><span id="pic-level" class="stat-val">1</span></div>
                        <div class="stat-box"><span class="stat-lbl">생명</span><span id="pic-lives" class="stat-val">❤️❤️❤️</span></div>
                        <div class="stat-box"><span class="stat-lbl">점수</span><span id="pic-score" class="stat-val">0</span></div>
                    </div>
                </div>
                <div class="mini-panel-card">
                    <div class="panel-header"><i class="fa-solid fa-book"></i> 표지 이미지</div>
                    <input id="pic-cover-url" type="text" class="cover-url-input" placeholder="책 표지 이미지 URL 입력 (예: /covers/123.jpg)">
                    <div class="cover-btn-row">
                        <button id="pic-btn-apply-cover" class="btn-banner primary">적용</button>
                        <button id="pic-btn-default-cover" class="btn-banner secondary">기본 이미지</button>
                    </div>
                    <p class="tip-text">URL을 직접 넣거나, 이 폴더의 covers/ 안에 이미지와 list.json(파일명 목록)을 넣어두면 게임마다 무작위로 표지가 바뀝니다.</p>
                </div>
                <div class="mini-panel-card">
                    <div class="panel-header"><i class="fa-regular fa-lightbulb"></i> 게임 방법</div>
                    <p class="tip-text">
                        • 테두리(안전지대)에서 나가 선을 그은 뒤 다시 돌아오면, 감싼 영역의 표지 그림이 드러납니다.<br>
                        • 선을 긋는 도중 쥐가 닿으면 목숨을 하나 잃고 처음 위치로 돌아갑니다.<br>
                        • 그리던 선을 스스로 다시 밟아도 목숨을 잃습니다.<br>
                        • 목표 공개율에 도달하면 다음 레벨로 넘어갑니다.
                    </p>
                </div>
            
            </div></div>

            <div class="stage-col center-col">
                <div class="picture-board-frame">
                    <canvas id="pic-board" width="360" height="540"></canvas>
                    <div id="pic-overlay" class="game-overlay hidden">
                        <h2 id="pic-overlay-title">GAME OVER</h2>
                        <p id="pic-overlay-msg">다시 도전해보세요!</p>
                        <button id="pic-btn-overlay-action" class="btn-banner primary">다시 시작</button>
                    </div>
                </div>
            </div>

            <div class="stage-col right-col" id="pic-right-col">
            <button class="panel-toggle-btn" id="pic-toggle-right" title="패널 접기/펼치기"><i class="fa-solid fa-chevron-right"></i></button>
            <div class="panel-content">
                <div class="mini-panel-card">
                    <div class="panel-header"><i class="fa-regular fa-keyboard"></i> 조작 가이드</div>
                    <ul class="key-guide-list">
                        <li><span>이동</span> <div class="key-group"><kbd>↑</kbd><kbd>↓</kbd><kbd>←</kbd><kbd>→</kbd></div></li>
                        <li><span>일시 정지</span> <kbd>P</kbd></li>
                        <li><span>모바일</span> <kbd>방향 버튼</kbd></li>
                    </ul>
                </div>
                <div class="picture-touch-controls">
                    <div class="touch-row">
                        <button class="touch-btn" data-dir="up"><i class="fa-solid fa-arrow-up"></i></button>
                    </div>
                    <div class="touch-row middle">
                        <button class="touch-btn" data-dir="left"><i class="fa-solid fa-arrow-left"></i></button>
                        <button class="touch-btn" data-dir="down"><i class="fa-solid fa-arrow-down"></i></button>
                        <button class="touch-btn" data-dir="right"><i class="fa-solid fa-arrow-right"></i></button>
                    </div>
                </div>
            
            </div></div>
        </div>
    </div>`;

    container.innerHTML = HTML;

    const COLS = 60, ROWS = 90, CELL = 6;
    const EMPTY = 0, CLAIMED = 1, TRAIL = 2;
    const TARGET_PERCENT = 75;

    const DEFAULT_COVER_SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="360" height="540">
        <rect width="360" height="540" fill="#334155"/>
        <rect x="20" y="20" width="320" height="500" fill="none" stroke="#64748b" stroke-width="3"/>
        <text x="180" y="245" font-size="22" fill="#e2e8f0" text-anchor="middle" font-family="sans-serif">표지 이미지 URL을</text>
        <text x="180" y="280" font-size="22" fill="#e2e8f0" text-anchor="middle" font-family="sans-serif">입력해 주세요</text>
        <text x="180" y="340" font-size="46" text-anchor="middle">📖</text>
    </svg>`;
    const DEFAULT_COVER_URL = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(DEFAULT_COVER_SVG);
    const COVER_STORAGE_KEY = 'ym_picture_territory_cover_url';

    let grid = [];
    let player = { x: 0, y: 0, dx: 0, dy: 0 };
    let enemies = [];
    let trailCells = [];
    let lives = 3, score = 0, level = 1, percent = 0;
    let isPlaying = false, isPaused = false, animId = null;
    let lastPlayerMove = 0, lastEnemyMove = 0;
    let playerInterval = 40, enemyInterval = 60;

    let coverImage = null;
    let coverImageReady = false;

    const canvas = container.querySelector('#pic-board');
    const ctx = canvas.getContext('2d');

    const percentEl = container.querySelector('#pic-percent');
    const targetEl = container.querySelector('#pic-target');
    const levelEl = container.querySelector('#pic-level');
    const livesEl = container.querySelector('#pic-lives');
    const scoreEl = container.querySelector('#pic-score');

    const overlay = container.querySelector('#pic-overlay');
    const overlayTitle = container.querySelector('#pic-overlay-title');
    const overlayMsg = container.querySelector('#pic-overlay-msg');
    const btnOverlay = container.querySelector('#pic-btn-overlay-action');

    const btnStart = container.querySelector('#pic-btn-start');
    const btnPause = container.querySelector('#pic-btn-pause');
    const btnReset = container.querySelector('#pic-btn-reset');

    const coverUrlInput = container.querySelector('#pic-cover-url');
    const btnApplyCover = container.querySelector('#pic-btn-apply-cover');
    const btnDefaultCover = container.querySelector('#pic-btn-default-cover');

    // covers/ 폴더에 이미지와 함께 list.json(파일명 배열)을 넣어두면
    // "적용" 버튼으로 수동 URL을 지정하지 않은 한, 게임 시작마다 그중 하나를 무작위로 사용합니다.
    // 예) games/picture-territory/covers/list.json 내용: ["book1.jpg", "book2.png"]
    const COVERS_BASE_PATH = '/plugins/metadata/ym_mini_game/games/picture-territory/covers/';
    let coversList = null; // null=아직 조회 전, []=목록 없음/비어있음

    function loadCoversList() {
        return fetch(COVERS_BASE_PATH + 'list.json')
            .then(res => { if (!res.ok) throw new Error('list.json 없음'); return res.json(); })
            .then(list => { coversList = Array.isArray(list) ? list.filter(Boolean) : []; })
            .catch(() => { coversList = []; });
    }

    function pickRandomFolderCoverUrl() {
        if (coversList && coversList.length > 0) {
            const name = coversList[Math.floor(Math.random() * coversList.length)];
            return COVERS_BASE_PATH + name;
        }
        return null;
    }

    function resolveCoverForNewGame() {
        const manualUrl = localStorage.getItem(COVER_STORAGE_KEY);
        if (manualUrl) { loadCoverImage(manualUrl); return; }
        loadCoverImage(pickRandomFolderCoverUrl() || DEFAULT_COVER_URL);
    }

    function loadCoverImage(url) {
        coverImageReady = false;
        const img = new Image();
        img.onload = () => { coverImage = img; coverImageReady = true; draw(); };
        img.onerror = () => {
            if (url !== DEFAULT_COVER_URL) {
                hub.setStatusBadge('표지 로드 실패', 'lost');
                loadCoverImage(DEFAULT_COVER_URL);
            }
        };
        img.src = url;
    }

    function applyCoverUrl(url) {
        const trimmed = (url || '').trim();
        localStorage.setItem(COVER_STORAGE_KEY, trimmed);
        if (trimmed) loadCoverImage(trimmed);
        else loadCoverImage(pickRandomFolderCoverUrl() || DEFAULT_COVER_URL);
    }

    function createGrid() {
        const g = [];
        for (let y = 0; y < ROWS; y++) g.push(new Array(COLS).fill(EMPTY));
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
        trailCells.forEach(([tx, ty]) => { grid[ty][tx] = CLAIMED; });
        trailCells = [];

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

        let gained = 0;
        for (let y = 0; y < ROWS; y++) {
            for (let x = 0; x < COLS; x++) {
                if (grid[y][x] === EMPTY && !visited[y][x]) { grid[y][x] = CLAIMED; gained++; }
            }
        }

        score += 10 + gained * 2;
        percent = calcPercent();
        updateStats();

        if (percent >= TARGET_PERCENT) levelUp();
    }

    function levelUp() {
        isPlaying = false;
        cancelAnimationFrame(animId);
        hub.setStatusBadge('LEVEL CLEAR', 'won');
        overlayTitle.textContent = `🎉 레벨 ${level} 클리어!`;
        overlayTitle.style.color = '#10b981';
        overlayMsg.textContent = `공개율 ${percent}% 달성! 다음 레벨로 진행합니다.`;
        btnOverlay.textContent = '다음 레벨';
        overlay.dataset.nextAction = 'nextLevel';
        overlay.classList.remove('hidden');
    }

    function nextLevel() {
        level++;
        grid = createGrid();
        enemies = spawnEnemies(1 + level);
        enemyInterval = Math.max(27, 60 - (level - 1) * 4);
        player = { x: Math.floor(COLS / 2), y: 0, dx: 0, dy: 0 };
        trailCells = [];
        percent = calcPercent();
        updateStats();
        overlay.classList.add('hidden');
        isPlaying = true; isPaused = false;
        hub.setStatusBadge('PLAYING (PICTURE)', 'playing');
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

    const DIAG_DIRS = [[1, 1], [1, -1], [-1, 1], [-1, -1]];

    function moveEnemies() {
        enemies.forEach(e => {
            let nx = e.x + e.dx, ny = e.y + e.dy;

            // 진행 방향에 놓인 선(TRAIL)에 닿으면 벽처럼 튕기기 전에 먼저 접촉으로 처리
            const willTouchTrailX = nx >= 0 && nx < COLS && grid[e.y][nx] === TRAIL;
            const willTouchTrailY = ny >= 0 && ny < ROWS && grid[ny][e.x] === TRAIL;
            const willTouchTrailDiag = nx >= 0 && nx < COLS && ny >= 0 && ny < ROWS && grid[ny][nx] === TRAIL;
            if (willTouchTrailX || willTouchTrailY || willTouchTrailDiag) {
                loseLife();
                return;
            }

            if (nx < 0 || nx >= COLS || grid[e.y][nx] !== EMPTY) e.dx *= -1;
            if (ny < 0 || ny >= ROWS || grid[ny][e.x] !== EMPTY) e.dy *= -1;
            nx = e.x + e.dx; ny = e.y + e.dy;

            if (nx >= 0 && nx < COLS && ny >= 0 && ny < ROWS && grid[ny][nx] === EMPTY) {
                e.x = nx; e.y = ny;
            } else {
                // 양쪽 반사 후에도 여전히 막혀있으면(구석에 몰림) - 멈추는 대신
                // 이동 가능한 다른 대각선 방향을 찾아 즉시 방향을 틀어 계속 움직이게 함
                const options = DIAG_DIRS.filter(([ddx, ddy]) => {
                    const tx = e.x + ddx, ty = e.y + ddy;
                    return tx >= 0 && tx < COLS && ty >= 0 && ty < ROWS && grid[ty][tx] === EMPTY;
                });
                if (options.length > 0) {
                    const [ddx, ddy] = options[Math.floor(Math.random() * options.length)];
                    e.dx = ddx; e.dy = ddy;
                    e.x += ddx; e.y += ddy;
                }
                // options가 비어있으면(사방이 완전히 막힘) 이번 틱은 어쩔 수 없이 정지 - 매우 드문 경우
            }

            if (grid[e.y][e.x] === TRAIL || (e.x === player.x && e.y === player.y)) {
                loseLife();
            }
        });
    }

    // ---------- 렌더링 (핵심: 점령된 칸만 표지 이미지가 보이도록) ----------
    function draw() {
        if (coverImageReady && coverImage) {
            ctx.drawImage(coverImage, 0, 0, canvas.width, canvas.height);
        } else {
            ctx.fillStyle = '#0b1220';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
        }

        for (let y = 0; y < ROWS; y++) {
            for (let x = 0; x < COLS; x++) {
                const v = grid[y][x];
                const px = x * CELL, py = y * CELL;
                if (v === CLAIMED) continue; // 이미지가 그대로 드러나도록 덮지 않음
                ctx.fillStyle = '#05080f'; // 미점령/트레일 모두 완전히 가림(트레일은 아래 얇은 선으로 별도 표시)
                ctx.fillRect(px, py, CELL, CELL);
            }
        }

        // 칸이 촘촘해져서(6px) 개별 격자선은 그리지 않음 (그리면 오히려 지저분해 보임)

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
        ctx.arc(player.x * CELL + CELL / 2, player.y * CELL + CELL / 2, Math.max(6, CELL / 2.4), 0, Math.PI * 2);
        ctx.fill();

        enemies.forEach(e => drawMouse(e.x * CELL + CELL / 2, e.y * CELL + CELL / 2, e.dx, e.dy));
    }

    function drawMouse(cx, cy, dx, dy) {
        const angle = Math.atan2(dy || 0.0001, dx || 0.0001);
        const r = Math.max(7, CELL / 2.3);

        ctx.save();
        ctx.translate(cx, cy);
        ctx.rotate(angle);

        ctx.strokeStyle = '#94a3b8';
        ctx.lineWidth = Math.max(1, CELL * 0.05);
        ctx.beginPath();
        ctx.moveTo(-r * 0.85, 0);
        ctx.quadraticCurveTo(-r * 1.6, r * 0.55, -r * 2.1, r * 0.05);
        ctx.stroke();

        ctx.fillStyle = '#cbd5e1';
        ctx.beginPath();
        ctx.ellipse(0, 0, r * 0.95, r * 0.68, 0, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = '#f9a8d4';
        ctx.beginPath(); ctx.arc(r * 0.35, -r * 0.55, r * 0.34, 0, Math.PI * 2); ctx.fill();
        ctx.beginPath(); ctx.arc(r * 0.35, r * 0.55, r * 0.34, 0, Math.PI * 2); ctx.fill();

        ctx.fillStyle = '#f472b6';
        ctx.beginPath(); ctx.arc(r * 0.95, 0, r * 0.16, 0, Math.PI * 2); ctx.fill();

        ctx.fillStyle = '#1f2937';
        ctx.beginPath(); ctx.arc(r * 0.4, -r * 0.18, r * 0.09, 0, Math.PI * 2); ctx.fill();
        ctx.beginPath(); ctx.arc(r * 0.4, r * 0.18, r * 0.09, 0, Math.PI * 2); ctx.fill();

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
        resolveCoverForNewGame();
        grid = createGrid();
        level = 1; lives = 3; score = 0;
        enemies = spawnEnemies(2);
        enemyInterval = 60;
        player = { x: Math.floor(COLS / 2), y: 0, dx: 0, dy: 0 };
        trailCells = [];
        percent = calcPercent();
        updateStats();
        isPlaying = true; isPaused = false;
        btnStart.innerHTML = '<i class="fa-solid fa-gamepad"></i> 진행 중';
        btnStart.disabled = true;
        btnPause.disabled = false;
        btnPause.innerHTML = '<i class="fa-solid fa-pause"></i> 일시 정지';
        hub.setStatusBadge('PLAYING (PICTURE)', 'playing');
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
            overlayMsg.textContent = '그림 땅따먹기가 일시정지되었습니다.';
            btnOverlay.textContent = '계속 진행';
            overlay.dataset.nextAction = 'resume';
            overlay.classList.remove('hidden');
        } else {
            btnPause.innerHTML = '<i class="fa-solid fa-pause"></i> 일시 정지';
            hub.setStatusBadge('PLAYING (PICTURE)', 'playing');
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
        overlayMsg.textContent = `최종 공개율 ${percent}% · 점수 ${score}점 (레벨 ${level})`;
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
        hub.setStatusBadge('READY (PICTURE)', '');
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

            btnApplyCover.onclick = () => applyCoverUrl(coverUrlInput.value);
            btnDefaultCover.onclick = () => {
                coverUrlInput.value = '';
                applyCoverUrl('');
            };

            container.querySelectorAll('.picture-touch-controls .touch-btn').forEach(btn => {
                btn.onclick = (e) => {
                    e.preventDefault();
                    const dir = btn.dataset.dir;
                    if (dir === 'up') setDirection(0, -1);
                    if (dir === 'down') setDirection(0, 1);
                    if (dir === 'left') setDirection(-1, 0);
                    if (dir === 'right') setDirection(1, 0);
                };
            });

            window.addEventListener('keydown', onKeyDown);

            const savedUrl = localStorage.getItem(COVER_STORAGE_KEY) || '';
            coverUrlInput.value = savedUrl;
            loadCoverImage(savedUrl || DEFAULT_COVER_URL); // 목록 조회 전까지 우선 표시
            loadCoversList().then(() => {
                if (!localStorage.getItem(COVER_STORAGE_KEY)) resolveCoverForNewGame();
            });

            reset();
        

            setupPanelToggle('pic-left-col', 'pic-toggle-left', 'fa-solid fa-chevron-left', 'fa-solid fa-chevron-right');
            setupPanelToggle('pic-right-col', 'pic-toggle-right', 'fa-solid fa-chevron-right', 'fa-solid fa-chevron-left');
},
        destroy() {
            isPlaying = false;
            cancelAnimationFrame(animId);
            window.removeEventListener('keydown', onKeyDown);
        }
    };
});
