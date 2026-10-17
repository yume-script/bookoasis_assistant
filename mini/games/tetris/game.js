// plugins/metadata/ym_mini_game/games/tetris/game.js

window.YmMiniGameHub.register('tetris', {
    name: '🕹️ 테트리스 (Tetris)',
    icon: 'fa-solid fa-shapes',
    order: 1
}, function (container, hub) {
    const HTML = `
    <div class="tetris-game-root">
        <div class="game-sub-bar">
            <span class="game-view-name"><i class="fa-solid fa-shapes"></i> TETRIS</span>
            <div class="sub-actions">
                <button id="tetris-btn-start" class="btn-banner primary"><i class="fa-solid fa-play"></i> 게임 시작</button>
                <button id="tetris-btn-pause" class="btn-banner secondary" disabled><i class="fa-solid fa-pause"></i> 일시 정지</button>
                <button id="tetris-btn-reset" class="btn-banner danger"><i class="fa-solid fa-rotate-left"></i> 초기화</button>
            </div>
        </div>
        <div class="tetris-stage-grid">
            <div class="stage-col left-col">
                <div class="mini-panel-card">
                    <div class="panel-header"><i class="fa-solid fa-chart-simple"></i> STATISTICS</div>
                    <div class="stat-grid">
                        <div class="stat-box"><span class="stat-lbl">SCORE</span><span id="tetris-score" class="stat-val highlight">0</span></div>
                        <div class="stat-box"><span class="stat-lbl">HIGH SCORE</span><span id="tetris-high-score" class="stat-val">0</span></div>
                        <div class="stat-box"><span class="stat-lbl">LEVEL</span><span id="tetris-level" class="stat-val">1</span></div>
                        <div class="stat-box"><span class="stat-lbl">LINES</span><span id="tetris-lines" class="stat-val">0</span></div>
                    </div>
                </div>
                <div class="mini-panel-card">
                    <div class="panel-header"><i class="fa-regular fa-keyboard"></i> 조작 가이드</div>
                    <ul class="key-guide-list">
                        <li><span>이동</span> <div class="key-group"><kbd>←</kbd> <kbd>→</kbd></div></li>
                        <li><span>회전</span> <kbd>↑</kbd></li>
                        <li><span>소프트 드롭</span> <kbd>↓</kbd></li>
                        <li><span>하드 드롭</span> <kbd>Space</kbd></li>
                        <li><span>일시 정지</span> <kbd>P</kbd></li>
                    </ul>
                </div>
            </div>
            <div class="stage-col center-col">
                <div class="tetris-board-frame">
                    <canvas id="tetris-board" width="360" height="720"></canvas>
                    <div id="tetris-overlay" class="game-overlay hidden">
                        <h2 id="tetris-overlay-title">GAME OVER</h2>
                        <p id="tetris-overlay-msg">다시 도전해보세요!</p>
                        <button id="tetris-btn-overlay-action" class="btn-banner primary">다시 시작</button>
                    </div>
                </div>
            </div>
            <div class="stage-col right-col">
                <div class="mini-panel-card next-panel">
                    <div class="panel-header"><i class="fa-solid fa-forward"></i> NEXT BLOCK</div>
                    <div class="next-canvas-wrapper">
                        <canvas id="tetris-next" width="140" height="140"></canvas>
                    </div>
                </div>
                <div class="tetris-touch-controls">
                    <div class="touch-row">
                        <button class="touch-btn" data-action="rotate"><i class="fa-solid fa-rotate-right"></i> 회전</button>
                    </div>
                    <div class="touch-row middle">
                        <button class="touch-btn" data-action="left"><i class="fa-solid fa-arrow-left"></i></button>
                        <button class="touch-btn" data-action="down"><i class="fa-solid fa-arrow-down"></i></button>
                        <button class="touch-btn" data-action="right"><i class="fa-solid fa-arrow-right"></i></button>
                    </div>
                    <div class="touch-row">
                        <button class="touch-btn hard-drop" data-action="drop"><i class="fa-solid fa-angles-down"></i> HARD DROP</button>
                    </div>
                </div>
            </div>
        </div>
    </div>`;

    container.innerHTML = HTML;

    const COLS = 10, ROWS = 20, BLOCK_SIZE = 36;
    const SHAPES = {
        I: [[0,0,0,0],[1,1,1,1],[0,0,0,0],[0,0,0,0]],
        J: [[1,0,0],[1,1,1],[0,0,0]],
        L: [[0,0,1],[1,1,1],[0,0,0]],
        O: [[1,1],[1,1]],
        S: [[0,1,1],[1,1,0],[0,0,0]],
        T: [[0,1,0],[1,1,1],[0,0,0]],
        Z: [[1,1,0],[0,1,1],[0,0,0]]
    };
    const COLORS = { I: '#06b6d4', J: '#3b82f6', L: '#f97316', O: '#eab308', S: '#22c55e', T: '#a855f7', Z: '#ef4444' };

    let grid = [], currentPiece = null, nextPiece = null;
    let score = 0, level = 1, lines = 0, highScore = 0;
    let dropInterval = 1000, lastDropTime = 0, isPlaying = false, isPaused = false, animId = null;

    const canvas = container.querySelector('#tetris-board');
    const ctx = canvas.getContext('2d');
    const nextCanvas = container.querySelector('#tetris-next');
    const nextCtx = nextCanvas.getContext('2d');

    const scoreEl = container.querySelector('#tetris-score');
    const levelEl = container.querySelector('#tetris-level');
    const linesEl = container.querySelector('#tetris-lines');
    const highScoreEl = container.querySelector('#tetris-high-score');

    const overlay = container.querySelector('#tetris-overlay');
    const overlayTitle = container.querySelector('#tetris-overlay-title');
    const overlayMsg = container.querySelector('#tetris-overlay-msg');
    const btnOverlay = container.querySelector('#tetris-btn-overlay-action');

    const btnStart = container.querySelector('#tetris-btn-start');
    const btnPause = container.querySelector('#tetris-btn-pause');
    const btnReset = container.querySelector('#tetris-btn-reset');

    function createGrid() { return Array.from({ length: ROWS }, () => Array(COLS).fill(0)); }

    function getRandomPiece() {
        const keys = Object.keys(SHAPES);
        const type = keys[Math.floor(Math.random() * keys.length)];
        const shape = SHAPES[type];
        return { type, shape, color: COLORS[type], x: Math.floor(COLS / 2) - Math.ceil(shape[0].length / 2), y: 0 };
    }

    function collide(offsetX = 0, offsetY = 0, newShape = null) {
        const shape = newShape || currentPiece.shape;
        for (let y = 0; y < shape.length; y++) {
            for (let x = 0; x < shape[y].length; x++) {
                if (shape[y][x]) {
                    const tx = currentPiece.x + x + offsetX;
                    const ty = currentPiece.y + y + offsetY;
                    if (tx < 0 || tx >= COLS || ty >= ROWS) return true;
                    if (ty >= 0 && grid[ty][tx]) return true;
                }
            }
        }
        return false;
    }

    function merge() {
        currentPiece.shape.forEach((row, y) => {
            row.forEach((val, x) => {
                if (val && currentPiece.y + y >= 0) grid[currentPiece.y + y][currentPiece.x + x] = currentPiece.color;
            });
        });
    }

    function clearLines() {
        let count = 0;
        for (let y = ROWS - 1; y >= 0; y--) {
            if (grid[y].every(cell => cell !== 0)) {
                grid.splice(y, 1);
                grid.unshift(Array(COLS).fill(0));
                count++;
                y++;
            }
        }
        if (count > 0) {
            lines += count;
            const lineScores = [0, 100, 300, 500, 800];
            score += (lineScores[count] || 100) * level;
            level = Math.floor(lines / 10) + 1;
            dropInterval = Math.max(120, 1000 - (level - 1) * 90);
            updateStats();
        }
    }

    function updateStats() {
        scoreEl.textContent = score;
        levelEl.textContent = level;
        linesEl.textContent = lines;
        if (score > highScore) {
            highScore = score;
            highScoreEl.textContent = highScore;
            localStorage.setItem('ym_tetris_high', highScore);
        }
    }

    function draw() {
        ctx.fillStyle = '#090d16';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        ctx.strokeStyle = 'rgba(255,255,255,0.04)';
        for (let x = 0; x < COLS; x++) { ctx.beginPath(); ctx.moveTo(x * BLOCK_SIZE, 0); ctx.lineTo(x * BLOCK_SIZE, canvas.height); ctx.stroke(); }
        for (let y = 0; y < ROWS; y++) { ctx.beginPath(); ctx.moveTo(0, y * BLOCK_SIZE); ctx.lineTo(canvas.width, y * BLOCK_SIZE); ctx.stroke(); }

        grid.forEach((row, y) => {
            row.forEach((color, x) => { if (color) drawBlock(ctx, x, y, color); });
        });

        if (currentPiece && isPlaying && !isPaused) {
            let ghostY = 0;
            while (!collide(0, ghostY + 1)) ghostY++;
            currentPiece.shape.forEach((row, y) => {
                row.forEach((val, x) => {
                    if (val) {
                        ctx.fillStyle = 'rgba(255,255,255,0.15)';
                        ctx.fillRect((currentPiece.x + x) * BLOCK_SIZE, (currentPiece.y + y + ghostY) * BLOCK_SIZE, BLOCK_SIZE, BLOCK_SIZE);
                    }
                });
            });
        }

        if (currentPiece) {
            currentPiece.shape.forEach((row, y) => {
                row.forEach((val, x) => { if (val) drawBlock(ctx, currentPiece.x + x, currentPiece.y + y, currentPiece.color); });
            });
        }
        drawNext();
    }

    function drawBlock(c, x, y, color) {
        c.fillStyle = color;
        c.fillRect(x * BLOCK_SIZE, y * BLOCK_SIZE, BLOCK_SIZE, BLOCK_SIZE);
        c.strokeStyle = 'rgba(255,255,255,0.3)';
        c.lineWidth = 2;
        c.strokeRect(x * BLOCK_SIZE + 1, y * BLOCK_SIZE + 1, BLOCK_SIZE - 2, BLOCK_SIZE - 2);
    }

    function drawNext() {
        nextCtx.fillStyle = '#090d16';
        nextCtx.fillRect(0, 0, nextCanvas.width, nextCanvas.height);
        if (!nextPiece) return;
        const shape = nextPiece.shape, size = 28;
        const ox = (nextCanvas.width - shape[0].length * size) / 2;
        const oy = (nextCanvas.height - shape.length * size) / 2;
        shape.forEach((row, y) => {
            row.forEach((val, x) => {
                if (val) {
                    nextCtx.fillStyle = nextPiece.color;
                    nextCtx.fillRect(ox + x * size, oy + y * size, size, size);
                    nextCtx.strokeStyle = 'rgba(255,255,255,0.3)';
                    nextCtx.strokeRect(ox + x * size + 1, oy + y * size + 1, size - 2, size - 2);
                }
            });
        });
    }

    function loop(time = 0) {
        if (!isPlaying || isPaused) return;
        if (time - lastDropTime > dropInterval) {
            moveDown();
            lastDropTime = time;
        }
        draw();
        animId = requestAnimationFrame(loop);
    }

    function move(dir) {
        if (!isPlaying || isPaused || !currentPiece) return;
        if (!collide(dir, 0)) currentPiece.x += dir;
        draw();
    }

    function moveDown() {
        if (!collide(0, 1)) {
            currentPiece.y++;
        } else {
            merge();
            clearLines();
            spawn();
        }
        draw();
    }

    function hardDrop() {
        if (!isPlaying || isPaused || !currentPiece) return;
        while (!collide(0, 1)) { currentPiece.y++; score += 2; }
        merge(); clearLines(); spawn(); updateStats(); draw();
    }

    function rotate() {
        if (!isPlaying || isPaused || !currentPiece) return;
        const N = currentPiece.shape.length;
        const rotated = currentPiece.shape.map((row, i) => row.map((val, j) => currentPiece.shape[N - 1 - j][i]));
        if (!collide(0, 0, rotated)) currentPiece.shape = rotated;
        else if (!collide(-1, 0, rotated)) { currentPiece.x--; currentPiece.shape = rotated; }
        else if (!collide(1, 0, rotated)) { currentPiece.x++; currentPiece.shape = rotated; }
        draw();
    }

    function spawn() {
        currentPiece = nextPiece || getRandomPiece();
        nextPiece = getRandomPiece();
        if (collide(0, 0)) gameOver();
    }

    function start() {
        grid = createGrid();
        score = 0; level = 1; lines = 0; dropInterval = 1000;
        isPlaying = true; isPaused = false;
        updateStats();
        nextPiece = getRandomPiece();
        spawn();
        btnStart.innerHTML = '<i class="fa-solid fa-gamepad"></i> 진행 중';
        btnStart.disabled = true;
        btnPause.disabled = false;
        btnPause.innerHTML = '<i class="fa-solid fa-pause"></i> 일시 정지';
        hub.setStatusBadge('PLAYING (TETRIS)', 'playing');
        overlay.classList.add('hidden');
        lastDropTime = performance.now();
        cancelAnimationFrame(animId);
        loop();
    }

    function togglePause() {
        if (!isPlaying) return;
        isPaused = !isPaused;
        if (isPaused) {
            btnPause.innerHTML = '<i class="fa-solid fa-play"></i> 계속 하기';
            hub.setStatusBadge('PAUSED', 'paused');
            overlayTitle.textContent = 'PAUSED';
            overlayTitle.style.color = '#f59e0b';
            overlayMsg.textContent = '테트리스가 일시정지되었습니다.';
            btnOverlay.textContent = '계속 진행';
            overlay.classList.remove('hidden');
        } else {
            btnPause.innerHTML = '<i class="fa-solid fa-pause"></i> 일시 정지';
            hub.setStatusBadge('PLAYING (TETRIS)', 'playing');
            overlay.classList.add('hidden');
            lastDropTime = performance.now();
            loop();
        }
    }

    function gameOver() {
        isPlaying = false;
        cancelAnimationFrame(animId);
        btnStart.innerHTML = '<i class="fa-solid fa-play"></i> 새 게임';
        btnStart.disabled = false;
        btnPause.disabled = true;
        hub.setStatusBadge('GAME OVER', 'lost');
        overlayTitle.textContent = 'GAME OVER';
        overlayTitle.style.color = '#ef4444';
        overlayMsg.textContent = `최종 점수: ${score}점 (레벨 ${level})`;
        btnOverlay.textContent = '다시 시작';
        overlay.classList.remove('hidden');
    }

    function reset() {
        isPlaying = false; isPaused = false;
        cancelAnimationFrame(animId);
        grid = createGrid();
        currentPiece = null; nextPiece = null;
        score = 0; level = 1; lines = 0;
        updateStats();
        btnStart.innerHTML = '<i class="fa-solid fa-play"></i> 게임 시작';
        btnStart.disabled = false;
        btnPause.disabled = true;
        overlay.classList.add('hidden');
        hub.setStatusBadge('READY (TETRIS)', '');
        draw();
    }

    function onKeyDown(e) {
        if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Space'].includes(e.code)) {
            if (isPlaying && !isPaused) e.preventDefault();
        }
        switch (e.code) {
            case 'ArrowLeft': move(-1); break;
            case 'ArrowRight': move(1); break;
            case 'ArrowDown': moveDown(); break;
            case 'ArrowUp': rotate(); break;
            case 'Space': hardDrop(); break;
            case 'KeyP': togglePause(); break;
        }
    }

    return {
        init() {
            highScore = parseInt(localStorage.getItem('ym_tetris_high') || '0', 10);
            highScoreEl.textContent = highScore;

            btnStart.onclick = start;
            btnPause.onclick = togglePause;
            btnReset.onclick = reset;
            btnOverlay.onclick = () => isPaused ? togglePause() : start();

            container.querySelectorAll('.tetris-touch-controls .touch-btn').forEach(btn => {
                btn.onclick = (e) => {
                    e.preventDefault();
                    const action = btn.dataset.action;
                    if (action === 'left') move(-1);
                    if (action === 'right') move(1);
                    if (action === 'down') moveDown();
                    if (action === 'rotate') rotate();
                    if (action === 'drop') hardDrop();
                };
            });

            window.addEventListener('keydown', onKeyDown);
            reset();
        },
        destroy() {
            isPaused = true;
            cancelAnimationFrame(animId);
            window.removeEventListener('keydown', onKeyDown);
        }
    };
});
