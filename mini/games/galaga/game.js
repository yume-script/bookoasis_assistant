// plugins/metadata/ym_mini_game/games/galaga/game.js

window.YmMiniGameHub.register('galaga', {
    name: '🚀 갤러그 (Galaga)',
    icon: 'fa-solid fa-rocket',
    order: 5
}, function (container, hub) {
    const HTML = `
    <div class="galaga-game-root">
        <div class="game-sub-bar">
            <span class="game-view-name"><i class="fa-solid fa-rocket"></i> GALAGA</span>
            <div class="sub-actions">
                <button id="gal-btn-start" class="btn-banner primary"><i class="fa-solid fa-play"></i> 게임 시작</button>
                <button id="gal-btn-pause" class="btn-banner secondary" disabled><i class="fa-solid fa-pause"></i> 일시 정지</button>
                <button id="gal-btn-reset" class="btn-banner danger"><i class="fa-solid fa-rotate-left"></i> 초기화</button>
            </div>
        </div>

        <div class="galaga-stage-grid">
            <div class="stage-col left-col" id="gal-left-col">
            <button class="panel-toggle-btn" id="gal-toggle-left" title="패널 접기/펼치기"><i class="fa-solid fa-chevron-left"></i></button>
            <div class="panel-content">
                <div class="mini-panel-card">
                    <div class="panel-header"><i class="fa-solid fa-chart-simple"></i> STATISTICS</div>
                    <div class="stat-grid">
                        <div class="stat-box"><span class="stat-lbl">SCORE</span><span id="gal-score" class="stat-val highlight">0</span></div>
                        <div class="stat-box"><span class="stat-lbl">HIGH SCORE</span><span id="gal-high-score" class="stat-val">0</span></div>
                        <div class="stat-box"><span class="stat-lbl">WAVE</span><span id="gal-wave" class="stat-val">1</span></div>
                        <div class="stat-box"><span class="stat-lbl">생명</span><span id="gal-lives" class="stat-val">🚀🚀🚀</span></div>
                    </div>
                </div>
                <div class="mini-panel-card">
                    <div class="panel-header"><i class="fa-regular fa-keyboard"></i> 조작 가이드</div>
                    <ul class="key-guide-list">
                        <li><span>이동</span> <div class="key-group"><kbd>←</kbd><kbd>→</kbd></div></li>
                        <li><span>발사</span> <kbd>Space</kbd></li>
                        <li><span>일시 정지</span> <kbd>P</kbd></li>
                    </ul>
                </div>
            
            </div></div>

            <div class="stage-col center-col">
                <div class="galaga-board-frame">
                    <canvas id="gal-board" width="380" height="540"></canvas>
                    <div id="gal-overlay" class="game-overlay hidden">
                        <h2 id="gal-overlay-title">GAME OVER</h2>
                        <p id="gal-overlay-msg">다시 도전해보세요!</p>
                        <button id="gal-btn-overlay-action" class="btn-banner primary">다시 시작</button>
                    </div>
                </div>
            </div>

            <div class="stage-col right-col" id="gal-right-col">
            <button class="panel-toggle-btn" id="gal-toggle-right" title="패널 접기/펼치기"><i class="fa-solid fa-chevron-right"></i></button>
            <div class="panel-content">
                <div class="mini-panel-card">
                    <div class="panel-header"><i class="fa-regular fa-lightbulb"></i> 게임 방법</div>
                    <p class="tip-text">
                        • 편대를 이루어 좌우로 움직이며 서서히 내려오는 적을 격추하세요.<br>
                        • 가끔 대열에서 이탈해 급강하 공격하는 적을 조심하세요(충돌 시 생명 감소).<br>
                        • 적탄에 맞거나 급강하 적과 충돌하면 생명을 잃습니다.<br>
                        • 웨이브를 모두 격추하면 다음 웨이브(적 증가·속도 상승)로 진행합니다.
                    </p>
                </div>
                <div class="galaga-touch-controls">
                    <div class="touch-row">
                        <button class="touch-btn" data-action="left"><i class="fa-solid fa-arrow-left"></i></button>
                        <button class="touch-btn fire-btn" data-action="fire"><i class="fa-solid fa-bolt"></i> FIRE</button>
                        <button class="touch-btn" data-action="right"><i class="fa-solid fa-arrow-right"></i></button>
                    </div>
                </div>
            
            </div></div>
        </div>
    </div>`;

    container.innerHTML = HTML;

    const W = 380, H = 540;
    const PLAYER_W = 30, PLAYER_H = 22, PLAYER_SPEED = 0.28; // px/ms
    const BULLET_SPEED = 0.55, ENEMY_BULLET_SPEED = 0.22;
    const ENEMY_W = 26, ENEMY_H = 18;
    const ROWS = 4, COLS = 8;
    const SPACING_X = 38, SPACING_Y = 32;
    const FORMATION_START_Y = 46;
    const MAX_PLAYER_BULLETS = 3;
    const INVASION_LINE = H - 110;

    const ROW_COLORS = ['#f472b6', '#fbbf24', '#34d399', '#60a5fa'];
    const ROW_COLORS_LIGHT = ['#fce7f3', '#fef3c7', '#d1fae5', '#dbeafe'];
    const ROW_POINTS = [80, 60, 40, 20];

    let canvas, ctx;
    let player, bullets, enemyBullets, enemies, particles;
    let keysDown = {};
    let score = 0, highScore = 0, wave = 1, lives = 3;
    let isPlaying = false, isPaused = false, animId = null;
    let lastTime = 0, lastShotTime = 0, lastEnemyFireTime = 0, lastDiveTime = 0;
    let formationOffsetX = 0, formationDir = 1, formationDropY = 0;
    let formationSpeed = 0.02, enemyFireInterval = 1800, diveInterval = 2600;
    let starField = [];

    canvas = container.querySelector('#gal-board');
    ctx = canvas.getContext('2d');

    const scoreEl = container.querySelector('#gal-score');
    const highScoreEl = container.querySelector('#gal-high-score');
    const waveEl = container.querySelector('#gal-wave');
    const livesEl = container.querySelector('#gal-lives');

    const overlay = container.querySelector('#gal-overlay');
    const overlayTitle = container.querySelector('#gal-overlay-title');
    const overlayMsg = container.querySelector('#gal-overlay-msg');
    const btnOverlay = container.querySelector('#gal-btn-overlay-action');

    const btnStart = container.querySelector('#gal-btn-start');
    const btnPause = container.querySelector('#gal-btn-pause');
    const btnReset = container.querySelector('#gal-btn-reset');

    function initStarField() {
        starField = [];
        for (let i = 0; i < 60; i++) {
            starField.push({ x: Math.random() * W, y: Math.random() * H, r: Math.random() * 1.6 + 0.4, speed: Math.random() * 0.05 + 0.02 });
        }
    }

    function makePlayer() {
        return { x: W / 2 - PLAYER_W / 2, y: H - 46, w: PLAYER_W, h: PLAYER_H };
    }

    function spawnWave(waveNum) {
        const rows = Math.min(ROWS + Math.floor((waveNum - 1) / 2), 6);
        const cols = Math.min(COLS + Math.floor((waveNum - 1) / 3), 10);
        const startX = (W - (cols - 1) * SPACING_X) / 2;

        const list = [];
        for (let r = 0; r < rows; r++) {
            for (let c = 0; c < cols; c++) {
                list.push({
                    col: c, row: r,
                    baseX: startX + c * SPACING_X,
                    baseY: FORMATION_START_Y + r * SPACING_Y,
                    x: startX + c * SPACING_X,
                    y: FORMATION_START_Y + r * SPACING_Y,
                    alive: true,
                    state: 'formation', // formation | diving
                    diveT: 0,
                    diveStartX: 0, diveStartY: 0, diveTargetX: 0,
                    colorRow: r % ROW_COLORS.length,
                });
            }
        }
        return list;
    }

    function resetRunState() {
        player = makePlayer();
        bullets = [];
        enemyBullets = [];
        particles = [];
        keysDown = {};
        formationOffsetX = 0;
        formationDir = 1;
        formationDropY = 0;
        lastShotTime = 0; lastEnemyFireTime = 0; lastDiveTime = 0;
    }

    function loadHighScore() {
        highScore = parseInt(localStorage.getItem('ym_galaga_high') || '0', 10);
        highScoreEl.textContent = String(highScore);
    }

    function saveHighScoreIfNeeded() {
        if (score > highScore) {
            highScore = score;
            localStorage.setItem('ym_galaga_high', String(highScore));
        }
    }

    function updateStats() {
        scoreEl.textContent = String(score);
        highScoreEl.textContent = String(Math.max(highScore, score));
        waveEl.textContent = String(wave);
        livesEl.textContent = '🚀'.repeat(Math.max(0, lives));
    }

    function rectsOverlap(a, b) {
        return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
    }

    function spawnParticles(x, y, color) {
        for (let i = 0; i < 8; i++) {
            const angle = (Math.PI * 2 * i) / 8;
            particles.push({
                x, y,
                vx: Math.cos(angle) * (0.06 + Math.random() * 0.05),
                vy: Math.sin(angle) * (0.06 + Math.random() * 0.05),
                life: 0, maxLife: 380 + Math.random() * 120,
                color,
            });
        }
    }

    // ---------- 업데이트 로직 ----------
    function updatePlayer(dt) {
        if (keysDown['ArrowLeft']) player.x -= PLAYER_SPEED * dt;
        if (keysDown['ArrowRight']) player.x += PLAYER_SPEED * dt;
        player.x = Math.max(4, Math.min(W - PLAYER_W - 4, player.x));
    }

    function tryFire(time) {
        if (!isPlaying || isPaused) return;
        if (time - lastShotTime < 320) return;
        const activePlayerBullets = bullets.filter(b => b.owner === 'player').length;
        if (activePlayerBullets >= MAX_PLAYER_BULLETS) return;
        bullets.push({ x: player.x + player.w / 2 - 2, y: player.y - 6, w: 4, h: 10, owner: 'player' });
        lastShotTime = time;
    }

    function updateBullets(dt) {
        bullets.forEach(b => { b.y -= BULLET_SPEED * dt; });
        bullets = bullets.filter(b => b.y + b.h > 0);

        enemyBullets.forEach(b => { b.y += ENEMY_BULLET_SPEED * dt; });
        enemyBullets = enemyBullets.filter(b => b.y < H);
    }

    function anyAlive() { return enemies.some(e => e.alive); }

    function updateFormation(dt) {
        const alive = enemies.filter(e => e.alive && e.state === 'formation');
        if (alive.length === 0) return;

        const maxOffset = 40;
        formationOffsetX += formationDir * formationSpeed * dt;
        if (formationOffsetX > maxOffset || formationOffsetX < -maxOffset) {
            formationDir *= -1;
            formationOffsetX = Math.max(-maxOffset, Math.min(maxOffset, formationOffsetX));
            formationDropY += 10;
        }

        alive.forEach(e => {
            e.x = e.baseX + formationOffsetX;
            e.y = e.baseY + formationDropY;
        });
    }

    function startDive(time) {
        const candidates = enemies.filter(e => e.alive && e.state === 'formation');
        if (candidates.length === 0) return;
        const e = candidates[Math.floor(Math.random() * candidates.length)];
        e.state = 'diving';
        e.diveT = 0;
        e.diveStartX = e.x;
        e.diveStartY = e.y;
        e.diveTargetX = player.x + player.w / 2;
    }

    function updateDiving(dt) {
        enemies.forEach(e => {
            if (!e.alive || e.state !== 'diving') return;
            e.diveT += dt;
            const t = e.diveT / 1600; // 다이브 총 소요 시간(ms) 기준 진행률
            e.x = e.diveStartX + (e.diveTargetX - e.diveStartX) * Math.min(1, t * 1.2);
            e.y = e.diveStartY + t * (H - e.diveStartY + 60);

            if (e.y > H + 20) {
                // 화면 밖으로 나가면 대형으로 즉시 복귀
                e.state = 'formation';
                e.x = e.baseX + formationOffsetX;
                e.y = e.baseY + formationDropY;
            }
        });
    }

    function updateEnemyFire(time) {
        if (time - lastEnemyFireTime < enemyFireInterval) return;
        const shooters = enemies.filter(e => e.alive);
        if (shooters.length === 0) return;
        const e = shooters[Math.floor(Math.random() * shooters.length)];
        enemyBullets.push({ x: e.x + ENEMY_W / 2 - 2, y: e.y + ENEMY_H, w: 4, h: 10, owner: 'enemy' });
        lastEnemyFireTime = time;
    }

    function updateParticles(dt) {
        particles.forEach(p => { p.x += p.vx * dt; p.y += p.vy * dt; p.life += dt; });
        particles = particles.filter(p => p.life < p.maxLife);
    }

    function checkCollisions() {
        // 플레이어 총알 vs 적
        bullets.forEach(b => {
            if (b.owner !== 'player' || b.hit) return;
            enemies.forEach(e => {
                if (!e.alive || b.hit) return;
                const eb = { x: e.x, y: e.y, w: ENEMY_W, h: ENEMY_H };
                if (rectsOverlap({ x: b.x, y: b.y, w: b.w, h: b.h }, eb)) {
                    b.hit = true;
                    e.alive = false;
                    score += ROW_POINTS[e.colorRow] || 20;
                    spawnParticles(e.x + ENEMY_W / 2, e.y + ENEMY_H / 2, ROW_COLORS[e.colorRow]);
                }
            });
        });
        bullets = bullets.filter(b => !b.hit);

        // 적 총알 vs 플레이어
        enemyBullets.forEach(b => {
            if (b.hit) return;
            if (rectsOverlap({ x: b.x, y: b.y, w: b.w, h: b.h }, player)) {
                b.hit = true;
                onPlayerHit();
            }
        });
        enemyBullets = enemyBullets.filter(b => !b.hit);

        // 급강하 적 vs 플레이어(직접 충돌)
        enemies.forEach(e => {
            if (!e.alive || e.state !== 'diving') return;
            const eb = { x: e.x, y: e.y, w: ENEMY_W, h: ENEMY_H };
            if (rectsOverlap(eb, player)) {
                e.alive = false;
                spawnParticles(e.x + ENEMY_W / 2, e.y + ENEMY_H / 2, ROW_COLORS[e.colorRow]);
                onPlayerHit();
            }
        });

        // 편대가 침공 라인을 넘으면 즉시 게임오버
        const alive = enemies.filter(e => e.alive && e.state === 'formation');
        if (alive.some(e => e.y + ENEMY_H >= INVASION_LINE)) {
            gameOver();
        }
    }

    function onPlayerHit() {
        lives--;
        updateStats();
        if (lives <= 0) { gameOver(); return; }
        hub.setStatusBadge('LIFE LOST', 'lost');
        player = makePlayer();
    }

    // ---------- 렌더링 ----------
    function draw() {
        ctx.fillStyle = '#05060f';
        ctx.fillRect(0, 0, W, H);

        ctx.fillStyle = '#94a3b8';
        starField.forEach(s => {
            s.y += s.speed * 16;
            if (s.y > H) s.y = 0;
            ctx.globalAlpha = 0.5;
            ctx.beginPath();
            ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
            ctx.fill();
        });
        ctx.globalAlpha = 1;

        // 플레이어
        drawPlayer();

        // 적
        enemies.forEach(e => { if (e.alive) drawEnemy(e); });

        // 총알 (레이저 느낌의 발광 효과)
        ctx.save();
        ctx.shadowColor = '#facc15';
        ctx.shadowBlur = 6;
        ctx.fillStyle = '#fde68a';
        bullets.forEach(b => {
            ctx.fillRect(b.x, b.y, b.w, b.h);
        });
        ctx.restore();

        ctx.save();
        ctx.shadowColor = '#f87171';
        ctx.shadowBlur = 6;
        ctx.fillStyle = '#fecaca';
        enemyBullets.forEach(b => {
            ctx.fillRect(b.x, b.y, b.w, b.h);
        });
        ctx.restore();

        // 파티클(폭발) - 중심 발광 + 바깥 파편
        particles.forEach(p => {
            const alpha = Math.max(0, 1 - p.life / p.maxLife);
            ctx.globalAlpha = alpha;
            ctx.save();
            ctx.shadowColor = p.color;
            ctx.shadowBlur = 8;
            ctx.fillStyle = p.color;
            ctx.beginPath();
            ctx.arc(p.x, p.y, 2.4 * (1 - p.life / p.maxLife * 0.4), 0, Math.PI * 2);
            ctx.fill();
            ctx.restore();
        });
        ctx.globalAlpha = 1;
    }

    function drawPlayer() {
        const cx = player.x + player.w / 2;
        const topY = player.y;
        const bottomY = player.y + player.h;

        // 엔진 불꽃 (시간에 따라 깜빡이며 흔들림)
        const flicker = 0.55 + Math.sin(lastTime / 45) * 0.35 + Math.random() * 0.1;
        const flameLen = 9 + flicker * 10;
        const flameGrad = ctx.createLinearGradient(cx, bottomY - 3, cx, bottomY + flameLen);
        flameGrad.addColorStop(0, 'rgba(191,219,254,0.95)');
        flameGrad.addColorStop(0.45, 'rgba(96,165,250,0.75)');
        flameGrad.addColorStop(1, 'rgba(59,130,246,0)');
        ctx.fillStyle = flameGrad;
        ctx.beginPath();
        ctx.moveTo(cx - 5, bottomY - 3);
        ctx.lineTo(cx, bottomY + flameLen);
        ctx.lineTo(cx + 5, bottomY - 3);
        ctx.closePath();
        ctx.fill();

        ctx.save();
        ctx.shadowColor = 'rgba(56,189,248,0.75)';
        ctx.shadowBlur = 10;

        // 동체 그라데이션 (위쪽 밝게, 아래쪽 진하게)
        const bodyGrad = ctx.createLinearGradient(player.x, topY, player.x, bottomY);
        bodyGrad.addColorStop(0, '#bae6fd');
        bodyGrad.addColorStop(0.5, '#38bdf8');
        bodyGrad.addColorStop(1, '#0369a1');
        ctx.fillStyle = bodyGrad;

        ctx.beginPath();
        ctx.moveTo(cx, topY);                                   // 기수
        ctx.lineTo(player.x + player.w, bottomY);               // 오른쪽 날개 끝
        ctx.lineTo(cx + player.w * 0.16, bottomY - 5);          // 오른쪽 안쪽
        ctx.lineTo(cx, bottomY - 9);                            // 엔진 노즐 중앙
        ctx.lineTo(cx - player.w * 0.16, bottomY - 5);          // 왼쪽 안쪽
        ctx.lineTo(player.x, bottomY);                          // 왼쪽 날개 끝
        ctx.closePath();
        ctx.fill();

        // 날개 하이라이트 선 + 중앙 라인
        ctx.strokeStyle = 'rgba(255,255,255,0.55)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(cx, topY + 2);
        ctx.lineTo(cx, bottomY - 7);
        ctx.stroke();

        // 콕핏(캐노피)
        const cockpitGrad = ctx.createRadialGradient(cx, topY + player.h * 0.4, 0.5, cx, topY + player.h * 0.4, player.w * 0.14);
        cockpitGrad.addColorStop(0, '#ffffff');
        cockpitGrad.addColorStop(1, '#7dd3fc');
        ctx.fillStyle = cockpitGrad;
        ctx.beginPath();
        ctx.ellipse(cx, topY + player.h * 0.4, player.w * 0.09, player.h * 0.17, 0, 0, Math.PI * 2);
        ctx.fill();

        ctx.restore();
    }

    function drawEnemy(e) {
        const cx = e.x + ENEMY_W / 2;
        const cy = e.y + ENEMY_H / 2;
        const color = ROW_COLORS[e.colorRow];
        const lightColor = ROW_COLORS_LIGHT[e.colorRow];
        const diving = e.state === 'diving';

        ctx.save();
        ctx.shadowColor = color;
        ctx.shadowBlur = diving ? 14 : 5;

        const grad = ctx.createRadialGradient(cx, cy - ENEMY_H * 0.18, 1, cx, cy, ENEMY_W * 0.62);
        grad.addColorStop(0, lightColor);
        grad.addColorStop(1, color);
        ctx.fillStyle = grad;

        // 몸통(곤충형 함선: 머리 - 날개 - 꼬리)
        ctx.beginPath();
        ctx.moveTo(cx, e.y);                                     // 머리 끝
        ctx.lineTo(e.x + ENEMY_W, cy - 1);                       // 오른쪽 날개
        ctx.lineTo(cx + ENEMY_W * 0.2, e.y + ENEMY_H);           // 오른쪽 꼬리
        ctx.lineTo(cx - ENEMY_W * 0.2, e.y + ENEMY_H);           // 왼쪽 꼬리
        ctx.lineTo(e.x, cy - 1);                                 // 왼쪽 날개
        ctx.closePath();
        ctx.fill();

        ctx.strokeStyle = 'rgba(255,255,255,0.4)';
        ctx.lineWidth = 1;
        ctx.stroke();

        // 더듬이(급강하 중일 때 더 또렷하게)
        ctx.strokeStyle = diving ? 'rgba(255,255,255,0.85)' : 'rgba(255,255,255,0.4)';
        ctx.beginPath();
        ctx.moveTo(cx - 3, e.y + 1);
        ctx.lineTo(cx - 6, e.y - 4);
        ctx.moveTo(cx + 3, e.y + 1);
        ctx.lineTo(cx + 6, e.y - 4);
        ctx.stroke();

        // 눈(발광점)
        ctx.shadowBlur = 0;
        ctx.fillStyle = diving ? '#fff7ed' : '#0f172a';
        ctx.beginPath();
        ctx.arc(cx - 3, cy, 1.5, 0, Math.PI * 2);
        ctx.arc(cx + 3, cy, 1.5, 0, Math.PI * 2);
        ctx.fill();

        ctx.restore();
    }

    // ---------- 게임 흐름 ----------
    function loop(time = 0) {
        if (!isPlaying || isPaused) return;
        const dt = lastTime ? Math.min(50, time - lastTime) : 16;
        lastTime = time;

        updatePlayer(dt);
        updateFormation(dt);
        updateDiving(dt);
        updateBullets(dt);
        updateParticles(dt);
        updateEnemyFire(time);

        if (time - lastDiveTime > diveInterval) {
            startDive(time);
            lastDiveTime = time;
        }

        checkCollisions();
        updateStats();
        draw();

        if (isPlaying && !anyAlive()) {
            nextWave();
        }

        if (isPlaying && !isPaused) animId = requestAnimationFrame(loop);
    }

    function nextWave() {
        wave++;
        formationSpeed = Math.min(0.06, 0.02 + (wave - 1) * 0.004);
        enemyFireInterval = Math.max(700, 1800 - (wave - 1) * 120);
        diveInterval = Math.max(1400, 2600 - (wave - 1) * 150);
        enemies = spawnWave(wave);
        formationOffsetX = 0; formationDir = 1; formationDropY = 0;
        hub.setStatusBadge(`WAVE ${wave}`, 'playing');
        updateStats();
    }

    function start() {
        score = 0; wave = 1; lives = 3;
        formationSpeed = 0.02; enemyFireInterval = 1800; diveInterval = 2600;
        resetRunState();
        enemies = spawnWave(wave);
        isPlaying = true; isPaused = false;
        lastTime = 0;

        btnStart.innerHTML = '<i class="fa-solid fa-gamepad"></i> 진행 중';
        btnStart.disabled = true;
        btnPause.disabled = false;
        btnPause.innerHTML = '<i class="fa-solid fa-pause"></i> 일시 정지';
        overlay.classList.add('hidden');
        hub.setStatusBadge('PLAYING (GALAGA)', 'playing');
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
            overlayMsg.textContent = '갤러그가 일시정지되었습니다.';
            btnOverlay.textContent = '계속 진행';
            overlay.dataset.nextAction = 'resume';
            overlay.classList.remove('hidden');
        } else {
            btnPause.innerHTML = '<i class="fa-solid fa-pause"></i> 일시 정지';
            hub.setStatusBadge('PLAYING (GALAGA)', 'playing');
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
        overlayMsg.textContent = `최종 점수 ${score}점 · WAVE ${wave}`;
        btnOverlay.textContent = '다시 시작';
        overlay.dataset.nextAction = 'restart';
        overlay.classList.remove('hidden');
        updateStats();
        draw();
    }

    function reset() {
        isPlaying = false; isPaused = false;
        cancelAnimationFrame(animId);
        score = 0; wave = 1; lives = 3;
        resetRunState();
        enemies = spawnWave(wave);

        btnStart.innerHTML = '<i class="fa-solid fa-play"></i> 게임 시작';
        btnStart.disabled = false;
        btnPause.disabled = true;
        overlay.classList.add('hidden');

        hub.setStatusBadge('READY (GALAGA)', '');
        loadHighScore();
        updateStats();
        draw();
    }

    function onKeyDown(e) {
        if (['ArrowLeft', 'ArrowRight', 'Space'].includes(e.code)) {
            if (isPlaying && !isPaused) e.preventDefault();
        }
        keysDown[e.code] = true;
        if (e.code === 'KeyP') togglePause();
    }
    function onKeyUp(e) { keysDown[e.code] = false; }

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

            container.querySelectorAll('.galaga-touch-controls .touch-btn').forEach(btn => {
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
                    const fire = (e) => { e.preventDefault(); tryFire(performance.now()); };
                    btn.onmousedown = fire;
                    btn.ontouchstart = fire;
                }
            });

            window.addEventListener('keydown', onKeyDown);
            window.addEventListener('keyup', onKeyUp);

            initStarField();
            reset();

            // Space 발사는 keydown 루프가 아니라 매 프레임 cooldown 체크로 처리하기 위해
            // 별도의 감시 루프를 두지 않고, requestAnimationFrame 루프(loop) 밖에서도
            // 키를 누르고 있는 동안 주기적으로 발사 시도하도록 별도 인터벌 사용.
            this._fireTimer = setInterval(() => {
                if (keysDown['Space']) tryFire(performance.now());
            }, 50);
        

            setupPanelToggle('gal-left-col', 'gal-toggle-left', 'fa-solid fa-chevron-left', 'fa-solid fa-chevron-right');
            setupPanelToggle('gal-right-col', 'gal-toggle-right', 'fa-solid fa-chevron-right', 'fa-solid fa-chevron-left');
},
        destroy() {
            isPlaying = false;
            cancelAnimationFrame(animId);
            if (this._fireTimer) clearInterval(this._fireTimer);
            window.removeEventListener('keydown', onKeyDown);
            window.removeEventListener('keyup', onKeyUp);
        }
    };
});
