// plugins/metadata/ym_mini_game/games/breakout/game.js

window.YmMiniGameHub.register('breakout', {
    name: '🧱 벽돌깨기 (Breakout)',
    icon: 'fa-solid fa-square',
    order: 8
}, function (container, hub) {
    const HTML = `
    <div class="breakout-game-root">
        <div class="game-sub-bar">
            <span class="game-view-name"><i class="fa-solid fa-square"></i> BREAKOUT</span>
            <div class="sub-actions">
                <button id="brk-btn-start" class="btn-banner primary"><i class="fa-solid fa-play"></i> 게임 시작</button>
                <button id="brk-btn-pause" class="btn-banner secondary" disabled><i class="fa-solid fa-pause"></i> 일시 정지</button>
                <button id="brk-btn-reset" class="btn-banner danger"><i class="fa-solid fa-rotate-left"></i> 초기화</button>
            </div>
        </div>

        <div class="breakout-stage-grid">
            <div class="stage-col left-col" id="brk-left-col">
            <button class="panel-toggle-btn" id="brk-toggle-left" title="패널 접기/펼치기"><i class="fa-solid fa-chevron-left"></i></button>
            <div class="panel-content">
                <div class="mini-panel-card">
                    <div class="panel-header"><i class="fa-solid fa-chart-simple"></i> STATISTICS</div>
                    <div class="stat-grid">
                        <div class="stat-box"><span class="stat-lbl">SCORE</span><span id="brk-score" class="stat-val highlight">0</span></div>
                        <div class="stat-box"><span class="stat-lbl">HIGH SCORE</span><span id="brk-high-score" class="stat-val">0</span></div>
                        <div class="stat-box"><span class="stat-lbl">LEVEL</span><span id="brk-level" class="stat-val">1</span></div>
                        <div class="stat-box"><span class="stat-lbl">생명</span><span id="brk-lives" class="stat-val">🧱🧱🧱</span></div>
                    </div>
                </div>
                <div class="mini-panel-card">
                    <div class="panel-header"><i class="fa-regular fa-lightbulb"></i> 아이템 안내</div>
                    <ul class="key-guide-list">
                        <li><span><span class="cap-badge" style="background:#38bdf8;">E</span> 패들 확장</span></li>
                        <li><span><span class="cap-badge" style="background:#a78bfa;">S</span> 공 감속</span></li>
                        <li><span><span class="cap-badge" style="background:#4ade80;">L</span> 생명 +1</span></li>
                        <li><span><span class="cap-badge" style="background:#fb923c;">M</span> 멀티볼</span></li>
                    </ul>
                </div>
            
            </div></div>

            <div class="stage-col center-col">
                <div class="breakout-board-frame">
                    <canvas id="brk-board" width="400" height="520"></canvas>
                    <div id="brk-overlay" class="game-overlay hidden">
                        <h2 id="brk-overlay-title">GAME OVER</h2>
                        <p id="brk-overlay-msg">다시 도전해보세요!</p>
                        <button id="brk-btn-overlay-action" class="btn-banner primary">다시 시작</button>
                    </div>
                </div>
            </div>

            <div class="stage-col right-col" id="brk-right-col">
            <button class="panel-toggle-btn" id="brk-toggle-right" title="패널 접기/펼치기"><i class="fa-solid fa-chevron-right"></i></button>
            <div class="panel-content">
                <div class="mini-panel-card">
                    <div class="panel-header"><i class="fa-regular fa-keyboard"></i> 조작 가이드</div>
                    <ul class="key-guide-list">
                        <li><span>이동</span> <div class="key-group"><kbd>←</kbd><kbd>→</kbd></div></li>
                        <li><span>발사</span> <kbd>Space</kbd></li>
                        <li><span>일시 정지</span> <kbd>P</kbd></li>
                        <li><span>PC</span> <kbd>마우스 이동도 가능</kbd></li>
                    </ul>
                </div>
                <div class="breakout-touch-controls">
                    <div class="touch-row">
                        <button class="touch-btn" data-action="left"><i class="fa-solid fa-arrow-left"></i></button>
                        <button class="touch-btn fire-btn" data-action="fire"><i class="fa-solid fa-bolt"></i> 발사</button>
                        <button class="touch-btn" data-action="right"><i class="fa-solid fa-arrow-right"></i></button>
                    </div>
                </div>
            
            </div></div>
        </div>
    </div>`;

    container.innerHTML = HTML;

    const W = 400, H = 520;
    const PADDLE_H = 12, PADDLE_BASE_W = 70, PADDLE_Y = H - 30, PADDLE_SPEED = 0.32;
    const BALL_R = 6;
    const COLS = 8, MARGIN = 10, GAP = 4, BRICK_H = 16, BRICK_TOP = 46;
    const BRICK_W = (W - MARGIN * 2 - GAP * (COLS - 1)) / COLS;
    const ROW_COLORS = ['#f87171', '#fbbf24', '#f472b6', '#4ade80', '#60a5fa', '#c084fc'];
    const CAPSULE_COLORS = { expand: '#38bdf8', slow: '#a78bfa', life: '#4ade80', multi: '#fb923c' };
    const CAPSULE_TYPES = ['expand', 'expand', 'slow', 'slow', 'multi', 'multi', 'life'];

    const canvas = container.querySelector('#brk-board');
    const ctx = canvas.getContext('2d');

    const scoreEl = container.querySelector('#brk-score');
    const highScoreEl = container.querySelector('#brk-high-score');
    const levelEl = container.querySelector('#brk-level');
    const livesEl = container.querySelector('#brk-lives');

    const overlay = container.querySelector('#brk-overlay');
    const overlayTitle = container.querySelector('#brk-overlay-title');
    const overlayMsg = container.querySelector('#brk-overlay-msg');
    const btnOverlay = container.querySelector('#brk-btn-overlay-action');

    const btnStart = container.querySelector('#brk-btn-start');
    const btnPause = container.querySelector('#brk-btn-pause');
    const btnReset = container.querySelector('#brk-btn-reset');

    let keysDown = {};
    let paddle, balls, bricks, capsules, particles;
    let score = 0, highScore = 0, level = 1, lives = 3;
    let isPlaying = false, isPaused = false, animId = null, lastTime = 0;
    let expandUntil = 0, slowUntil = 0;

    function makePaddle() {
        return { x: W / 2 - PADDLE_BASE_W / 2, y: PADDLE_Y, w: PADDLE_BASE_W, h: PADDLE_H };
    }

    function makeBall(attached) {
        return {
            x: paddle.x + paddle.w / 2, y: paddle.y - BALL_R - 1,
            vx: 0, vy: 0, r: BALL_R, attached: !!attached,
        };
    }

    function ballSpeedForLevel() { return 0.24 + (level - 1) * 0.012; }

    function launchBall(ball) {
        if (!ball.attached) return;
        ball.attached = false;
        const speed = ballSpeedForLevel();
        const angle = (Math.random() * 0.5 - 0.25); // 살짝 랜덤한 초기 각도
        ball.vx = speed * Math.sin(angle);
        ball.vy = -speed * Math.cos(angle);
    }

    function buildBricks(lvl) {
        const rows = Math.min(4 + Math.floor((lvl - 1) / 2), 7);
        const list = [];
        for (let r = 0; r < rows; r++) {
            let hits = 1;
            if (lvl >= 3 && r === 0) hits = 2;
            if (lvl >= 6 && r <= 1) hits = 2;
            for (let c = 0; c < COLS; c++) {
                list.push({
                    x: MARGIN + c * (BRICK_W + GAP),
                    y: BRICK_TOP + r * (BRICK_H + GAP),
                    w: BRICK_W, h: BRICK_H,
                    hits, maxHits: hits,
                    colorRow: r % ROW_COLORS.length,
                    points: (rows - r) * 10,
                    alive: true,
                });
            }
        }
        return list;
    }

    function resetRunObjects() {
        paddle = makePaddle();
        balls = [makeBall(true)];
        capsules = [];
        particles = [];
        expandUntil = 0; slowUntil = 0;
        keysDown = {};
    }

    function loadHighScore() {
        highScore = parseInt(localStorage.getItem('ym_breakout_high') || '0', 10);
        highScoreEl.textContent = String(highScore);
    }
    function saveHighScoreIfNeeded() {
        if (score > highScore) { highScore = score; localStorage.setItem('ym_breakout_high', String(highScore)); }
    }

    function updateStats() {
        scoreEl.textContent = String(score);
        highScoreEl.textContent = String(Math.max(highScore, score));
        levelEl.textContent = String(level);
        livesEl.textContent = '🧱'.repeat(Math.max(0, lives));
    }

    function rectsOverlap(a, b) {
        return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
    }

    function spawnParticles(x, y, color) {
        for (let i = 0; i < 6; i++) {
            const angle = (Math.PI * 2 * i) / 6;
            particles.push({ x, y, vx: Math.cos(angle) * 0.07, vy: Math.sin(angle) * 0.07, life: 0, maxLife: 300, color });
        }
    }

    function speedMultiplier(time) { return time < slowUntil ? 0.55 : 1; }

    // ---------- 업데이트 ----------
    function updatePaddle(dt) {
        if (keysDown['ArrowLeft']) paddle.x -= PADDLE_SPEED * dt;
        if (keysDown['ArrowRight']) paddle.x += PADDLE_SPEED * dt;
        paddle.x = Math.max(4, Math.min(W - paddle.w - 4, paddle.x));

        const now = performance.now();
        const targetW = now < expandUntil ? PADDLE_BASE_W * 1.6 : PADDLE_BASE_W;
        if (Math.abs(paddle.w - targetW) > 0.5) {
            const cx = paddle.x + paddle.w / 2;
            paddle.w += (targetW - paddle.w) * Math.min(1, dt / 120);
            paddle.x = cx - paddle.w / 2;
            paddle.x = Math.max(4, Math.min(W - paddle.w - 4, paddle.x));
        } else {
            paddle.w = targetW;
        }
    }

    function updateBalls(dt, time) {
        const mul = speedMultiplier(time);
        balls.forEach(ball => {
            if (ball.attached) {
                ball.x = paddle.x + paddle.w / 2;
                ball.y = paddle.y - ball.r - 1;
                return;
            }
            ball.x += ball.vx * mul * dt;
            ball.y += ball.vy * mul * dt;

            if (ball.x - ball.r < 0) { ball.x = ball.r; ball.vx *= -1; }
            if (ball.x + ball.r > W) { ball.x = W - ball.r; ball.vx *= -1; }
            if (ball.y - ball.r < 0) { ball.y = ball.r; ball.vy *= -1; }

            // 패들 충돌
            if (ball.vy > 0 &&
                ball.y + ball.r >= paddle.y && ball.y + ball.r <= paddle.y + paddle.h + 8 &&
                ball.x >= paddle.x - ball.r && ball.x <= paddle.x + paddle.w + ball.r) {
                const rel = ((ball.x - (paddle.x + paddle.w / 2)) / (paddle.w / 2));
                const clampedRel = Math.max(-1, Math.min(1, rel));
                const speed = Math.hypot(ball.vx, ball.vy) || ballSpeedForLevel();
                const maxAngle = Math.PI / 3; // 60도
                const angle = clampedRel * maxAngle;
                ball.vx = speed * Math.sin(angle);
                ball.vy = -Math.abs(speed * Math.cos(angle));
                ball.y = paddle.y - ball.r - 0.5;
            }
        });

        // 화면 아래로 떨어진 공 제거
        balls = balls.filter(b => b.attached || b.y - b.r < H);

        if (balls.length === 0) {
            onLifeLost();
        }
    }

    function updateBricks() {
        balls.forEach(ball => {
            if (ball.attached) return;
            for (const brick of bricks) {
                if (!brick.alive) continue;
                const box = { x: ball.x - ball.r, y: ball.y - ball.r, w: ball.r * 2, h: ball.r * 2 };
                if (!rectsOverlap(box, brick)) continue;

                const overlapLeft = box.x + box.w - brick.x;
                const overlapRight = brick.x + brick.w - box.x;
                const overlapTop = box.y + box.h - brick.y;
                const overlapBottom = brick.y + brick.h - box.y;
                const minOverlapX = Math.min(overlapLeft, overlapRight);
                const minOverlapY = Math.min(overlapTop, overlapBottom);

                if (minOverlapX < minOverlapY) ball.vx *= -1;
                else ball.vy *= -1;

                brick.hits--;
                if (brick.hits <= 0) {
                    brick.alive = false;
                    score += brick.points;
                    spawnParticles(brick.x + brick.w / 2, brick.y + brick.h / 2, ROW_COLORS[brick.colorRow]);
                    maybeDropCapsule(brick);
                }
                break; // 한 프레임에 한 벽돌만 처리 (여러 겹 충돌 방지)
            }
        });
    }

    function maybeDropCapsule(brick) {
        if (Math.random() > 0.18) return;
        const type = CAPSULE_TYPES[Math.floor(Math.random() * CAPSULE_TYPES.length)];
        capsules.push({ x: brick.x + brick.w / 2 - 13, y: brick.y, w: 26, h: 14, type, vy: 0.1 });
    }

    function updateCapsules(dt) {
        capsules.forEach(cap => { cap.y += cap.vy * dt; });
        capsules = capsules.filter(cap => {
            if (cap.y > H) return false;
            if (rectsOverlap(cap, paddle)) {
                applyCapsule(cap.type);
                return false;
            }
            return true;
        });
    }

    function applyCapsule(type) {
        const now = performance.now();
        if (type === 'expand') {
            expandUntil = now + 9000;
        } else if (type === 'slow') {
            slowUntil = now + 7000;
        } else if (type === 'life') {
            lives = Math.min(9, lives + 1);
        } else if (type === 'multi') {
            const base = balls.find(b => !b.attached) || balls[0];
            if (base) {
                for (const offset of [-0.4, 0.4]) {
                    const speed = Math.hypot(base.vx, base.vy) || ballSpeedForLevel();
                    const baseAngle = Math.atan2(base.vx, -base.vy);
                    const angle = baseAngle + offset;
                    balls.push({
                        x: base.x, y: base.y, r: BALL_R, attached: false,
                        vx: speed * Math.sin(angle), vy: -Math.abs(speed * Math.cos(angle)),
                    });
                }
            }
        }
        updateStats();
    }

    function updateParticles(dt) {
        particles.forEach(p => { p.x += p.vx * dt; p.y += p.vy * dt; p.life += dt; });
        particles = particles.filter(p => p.life < p.maxLife);
    }

    function onLifeLost() {
        lives--;
        updateStats();
        if (lives <= 0) { gameOver(); return; }
        hub.setStatusBadge('LIFE LOST', 'lost');
        paddle = makePaddle();
        balls = [makeBall(true)];
        capsules = [];
    }

    function anyBrickAlive() { return bricks.some(b => b.alive); }

    function nextLevel() {
        level++;
        bricks = buildBricks(level);
        paddle = makePaddle();
        balls = [makeBall(true)];
        capsules = [];
        hub.setStatusBadge(`LEVEL ${level}`, 'playing');
        updateStats();
    }

    // ---------- 렌더링 ----------
    function draw() {
        ctx.fillStyle = '#0b1020';
        ctx.fillRect(0, 0, W, H);

        // 벽돌
        bricks.forEach(b => {
            if (!b.alive) return;
            const damaged = b.hits < b.maxHits;
            ctx.fillStyle = ROW_COLORS[b.colorRow];
            ctx.globalAlpha = damaged ? 0.55 : 1;
            ctx.fillRect(b.x, b.y, b.w, b.h);
            ctx.globalAlpha = 1;
            ctx.strokeStyle = 'rgba(0,0,0,0.25)';
            ctx.lineWidth = 1;
            ctx.strokeRect(b.x + 0.5, b.y + 0.5, b.w - 1, b.h - 1);
        });

        // 캡슐 아이템
        capsules.forEach(cap => {
            ctx.fillStyle = CAPSULE_COLORS[cap.type];
            ctx.beginPath();
            if (ctx.roundRect) ctx.roundRect(cap.x, cap.y, cap.w, cap.h, 6);
            else ctx.rect(cap.x, cap.y, cap.w, cap.h);
            ctx.fill();
            ctx.fillStyle = '#0f172a';
            ctx.font = 'bold 10px sans-serif';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(cap.type[0].toUpperCase(), cap.x + cap.w / 2, cap.y + cap.h / 2 + 1);
        });

        // 패들
        ctx.fillStyle = '#38bdf8';
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(paddle.x, paddle.y, paddle.w, paddle.h, 6);
        else ctx.rect(paddle.x, paddle.y, paddle.w, paddle.h);
        ctx.fill();

        // 공
        ctx.fillStyle = '#f8fafc';
        balls.forEach(ball => {
            ctx.beginPath();
            ctx.arc(ball.x, ball.y, ball.r, 0, Math.PI * 2);
            ctx.fill();
        });

        // 파티클
        particles.forEach(p => {
            const alpha = Math.max(0, 1 - p.life / p.maxLife);
            ctx.globalAlpha = alpha;
            ctx.fillStyle = p.color;
            ctx.beginPath();
            ctx.arc(p.x, p.y, 2.2, 0, Math.PI * 2);
            ctx.fill();
        });
        ctx.globalAlpha = 1;
    }

    // ---------- 게임 흐름 ----------
    function loop(time = 0) {
        if (!isPlaying || isPaused) return;
        const dt = lastTime ? Math.min(50, time - lastTime) : 16;
        lastTime = time;

        updatePaddle(dt);
        updateBalls(dt, time);
        updateBricks();
        updateCapsules(dt);
        updateParticles(dt);

        updateStats();
        draw();

        if (isPlaying && !anyBrickAlive()) nextLevel();

        if (isPlaying && !isPaused) animId = requestAnimationFrame(loop);
    }

    function tryLaunch() {
        if (!isPlaying || isPaused) return;
        const attachedBall = balls.find(b => b.attached);
        if (attachedBall) launchBall(attachedBall);
    }

    function start() {
        score = 0; level = 1; lives = 3;
        resetRunObjects();
        bricks = buildBricks(level);
        isPlaying = true; isPaused = false; lastTime = 0;

        btnStart.innerHTML = '<i class="fa-solid fa-gamepad"></i> 진행 중';
        btnStart.disabled = true;
        btnPause.disabled = false;
        btnPause.innerHTML = '<i class="fa-solid fa-pause"></i> 일시 정지';
        overlay.classList.add('hidden');
        hub.setStatusBadge('PLAYING (BREAKOUT)', 'playing');
        updateStats();

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
            overlayMsg.textContent = '벽돌깨기가 일시정지되었습니다.';
            btnOverlay.textContent = '계속 진행';
            overlay.dataset.nextAction = 'resume';
            overlay.classList.remove('hidden');
        } else {
            btnPause.innerHTML = '<i class="fa-solid fa-pause"></i> 일시 정지';
            hub.setStatusBadge('PLAYING (BREAKOUT)', 'playing');
            overlay.classList.add('hidden');
            lastTime = 0;
            loop(performance.now());
        }
    }

    function gameOver() {
        if (!isPlaying) return;
        isPlaying = false;
        cancelAnimationFrame(animId);
        saveHighScoreIfNeeded();

        btnStart.innerHTML = '<i class="fa-solid fa-play"></i> 새 게임';
        btnStart.disabled = false;
        btnPause.disabled = true;

        hub.setStatusBadge('GAME OVER', 'lost');
        overlayTitle.textContent = '💥 GAME OVER';
        overlayTitle.style.color = '#ef4444';
        overlayMsg.textContent = `최종 점수 ${score}점 · LEVEL ${level}`;
        btnOverlay.textContent = '다시 시작';
        overlay.dataset.nextAction = 'restart';
        overlay.classList.remove('hidden');
        updateStats();
        draw();
    }

    function reset() {
        isPlaying = false; isPaused = false;
        cancelAnimationFrame(animId);
        score = 0; level = 1; lives = 3;
        resetRunObjects();
        bricks = buildBricks(level);

        btnStart.innerHTML = '<i class="fa-solid fa-play"></i> 게임 시작';
        btnStart.disabled = false;
        btnPause.disabled = true;
        overlay.classList.add('hidden');

        hub.setStatusBadge('READY (BREAKOUT)', '');
        loadHighScore();
        updateStats();
        draw();
    }

    function onKeyDown(e) {
        if (['ArrowLeft', 'ArrowRight', 'Space'].includes(e.code)) {
            if (isPlaying && !isPaused) e.preventDefault();
        }
        keysDown[e.code] = true;
        if (e.code === 'Space') tryLaunch();
        if (e.code === 'KeyP') togglePause();
    }
    function onKeyUp(e) { keysDown[e.code] = false; }

    function onMouseMove(evt) {
        if (!isPlaying || isPaused) return;
        const rect = canvas.getBoundingClientRect();
        const scaleX = canvas.width / rect.width;
        const px = (evt.clientX - rect.left) * scaleX;
        paddle.x = Math.max(4, Math.min(W - paddle.w - 4, px - paddle.w / 2));
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
                if (action === 'resume') togglePause();
                else start();
            };

            canvas.addEventListener('mousemove', onMouseMove);
            canvas.addEventListener('click', tryLaunch);

            container.querySelectorAll('.breakout-touch-controls .touch-btn').forEach(btn => {
                const action = btn.dataset.action;
                const setKey = (code, val) => { keysDown[code] = val; };
                if (action === 'left') {
                    btn.onmousedown = () => setKey('ArrowLeft', true);
                    btn.onmouseup = () => setKey('ArrowLeft', false);
                    btn.onmouseleave = () => setKey('ArrowLeft', false);
                    btn.ontouchstart = (e) => { e.preventDefault(); setKey('ArrowLeft', true); };
                    btn.ontouchend = (e) => { e.preventDefault(); setKey('ArrowLeft', false); };
                } else if (action === 'right') {
                    btn.onmousedown = () => setKey('ArrowRight', true);
                    btn.onmouseup = () => setKey('ArrowRight', false);
                    btn.onmouseleave = () => setKey('ArrowRight', false);
                    btn.ontouchstart = (e) => { e.preventDefault(); setKey('ArrowRight', true); };
                    btn.ontouchend = (e) => { e.preventDefault(); setKey('ArrowRight', false); };
                } else if (action === 'fire') {
                    const fire = (e) => { e.preventDefault(); tryLaunch(); };
                    btn.onmousedown = fire;
                    btn.ontouchstart = fire;
                }
            });

            window.addEventListener('keydown', onKeyDown);
            window.addEventListener('keyup', onKeyUp);

            reset();
        

            setupPanelToggle('brk-left-col', 'brk-toggle-left', 'fa-solid fa-chevron-left', 'fa-solid fa-chevron-right');
            setupPanelToggle('brk-right-col', 'brk-toggle-right', 'fa-solid fa-chevron-right', 'fa-solid fa-chevron-left');
},
        destroy() {
            isPlaying = false;
            cancelAnimationFrame(animId);
            window.removeEventListener('keydown', onKeyDown);
            window.removeEventListener('keyup', onKeyUp);
            canvas.removeEventListener('mousemove', onMouseMove);
            canvas.removeEventListener('click', tryLaunch);
        }
    };
});
