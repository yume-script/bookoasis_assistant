// plugins/metadata/ym_mini_game/games/car-racer/game.js

window.YmMiniGameHub.register('car-racer', {
    name: '🚗 카 레이서 (Car Racer)',
    icon: 'fa-solid fa-car',
    order: 9
}, function (container, hub) {
    const HTML = `
    <div class="racer-game-root">
        <div class="game-sub-bar">
            <span class="game-view-name"><i class="fa-solid fa-car"></i> 카 레이서</span>
            <div class="sub-actions">
                <button id="racer-btn-start" class="btn-banner primary"><i class="fa-solid fa-play"></i> 게임 시작</button>
                <button id="racer-btn-pause" class="btn-banner secondary" disabled><i class="fa-solid fa-pause"></i> 일시 정지</button>
                <button id="racer-btn-reset" class="btn-banner danger"><i class="fa-solid fa-rotate-left"></i> 초기화</button>
            </div>
        </div>

        <div class="racer-stage-grid">
            <div class="stage-col left-col" id="racer-left-col">
            <button class="panel-toggle-btn" id="racer-toggle-left" title="패널 접기/펼치기"><i class="fa-solid fa-chevron-left"></i></button>
            <div class="panel-content">
                <div class="mini-panel-card">
                    <div class="panel-header"><i class="fa-solid fa-chart-simple"></i> 기록</div>
                    <div class="stat-grid">
                        <div class="stat-box"><span class="stat-lbl">속도</span><span id="racer-speed" class="stat-val highlight">60 km/h</span></div>
                        <div class="stat-box"><span class="stat-lbl">점수</span><span id="racer-score" class="stat-val">0</span></div>
                        <div class="stat-box"><span class="stat-lbl">최고 기록</span><span id="racer-high-score" class="stat-val">0</span></div>
                        <div class="stat-box"><span class="stat-lbl">생명</span><span id="racer-lives" class="stat-val">🚗🚗🚗</span></div>
                    </div>
                </div>
                <div class="mini-panel-card">
                    <div class="panel-header"><i class="fa-regular fa-lightbulb"></i> 게임 방법</div>
                    <p class="tip-text">
                        • 마주 오는 차량을 피해 최대한 멀리 달려보세요.<br>
                        • 속도를 높이면 점수가 더 빨리 오르지만, 그만큼 반응할 시간이 줄어듭니다.<br>
                        • 차량과 충돌하면 생명을 하나 잃고 잠시 무적 상태로 다시 출발합니다.
                    </p>
                </div>
            
            </div></div>

            <div class="stage-col center-col">
                <div class="racer-board-frame">
                    <canvas id="racer-board" width="340" height="600"></canvas>
                    <div id="racer-overlay" class="game-overlay hidden">
                        <h2 id="racer-overlay-title">게임 오버</h2>
                        <p id="racer-overlay-msg">다시 도전해보세요!</p>
                        <button id="racer-btn-overlay-action" class="btn-banner primary">다시 시작</button>
                    </div>
                </div>
            </div>

            <div class="stage-col right-col" id="racer-right-col">
            <button class="panel-toggle-btn" id="racer-toggle-right" title="패널 접기/펼치기"><i class="fa-solid fa-chevron-right"></i></button>
            <div class="panel-content">
                <div class="mini-panel-card">
                    <div class="panel-header"><i class="fa-regular fa-keyboard"></i> 조작 안내</div>
                    <ul class="key-guide-list">
                        <li><span>차선 변경</span> <div class="key-group"><kbd>←</kbd><kbd>→</kbd></div></li>
                        <li><span>가속 / 감속</span> <div class="key-group"><kbd>↑</kbd><kbd>↓</kbd></div></li>
                        <li><span>일시 정지</span> <kbd>P</kbd></li>
                    </ul>
                </div>
                <div class="racer-touch-controls">
                    <div class="touch-row">
                        <button class="touch-btn" data-action="accel"><i class="fa-solid fa-gauge-high"></i> 가속</button>
                    </div>
                    <div class="touch-row middle">
                        <button class="touch-btn" data-action="left"><i class="fa-solid fa-arrow-left"></i></button>
                        <button class="touch-btn" data-action="right"><i class="fa-solid fa-arrow-right"></i></button>
                    </div>
                    <div class="touch-row">
                        <button class="touch-btn" data-action="brake"><i class="fa-solid fa-gauge-simple"></i> 감속</button>
                    </div>
                </div>
            
            </div></div>
        </div>
    </div>`;

    container.innerHTML = HTML;

    const W = 340, H = 600;
    const ROAD_MARGIN = 24; // 좌우 잔디+연석 폭
    const ROAD_LEFT = ROAD_MARGIN, ROAD_RIGHT = W - ROAD_MARGIN;
    const ROAD_W = ROAD_RIGHT - ROAD_LEFT;
    const LANES = 3;
    const LANE_W = ROAD_W / LANES;
    const CAR_W = 34, CAR_H = 54;
    const PLAYER_Y = H - 120;

    const MIN_SPEED = 40, MAX_SPEED = 200, BASE_SPEED = 60;
    const ACCEL = 0.00009, DECEL = 0.00013, NATURAL_DECAY = 0.00004;

    function laneCenterX(lane) { return ROAD_LEFT + LANE_W * lane + LANE_W / 2; }

    const canvas = container.querySelector('#racer-board');
    const ctx = canvas.getContext('2d');

    const speedEl = container.querySelector('#racer-speed');
    const scoreEl = container.querySelector('#racer-score');
    const highScoreEl = container.querySelector('#racer-high-score');
    const livesEl = container.querySelector('#racer-lives');

    const overlay = container.querySelector('#racer-overlay');
    const overlayTitle = container.querySelector('#racer-overlay-title');
    const overlayMsg = container.querySelector('#racer-overlay-msg');
    const btnOverlay = container.querySelector('#racer-btn-overlay-action');

    const btnStart = container.querySelector('#racer-btn-start');
    const btnPause = container.querySelector('#racer-btn-pause');
    const btnReset = container.querySelector('#racer-btn-reset');

    let keysDown = {};
    let player, traffic, particles;
    let speed = BASE_SPEED, score = 0, highScore = 0, lives = 3;
    let laneOffset = 0; // 차선 점선 스크롤 애니메이션용
    let isPlaying = false, isPaused = false, animId = null, lastTime = 0;
    let invincibleUntil = 0;
    let lastSpawnTime = 0, spawnInterval = 1400;
    let elapsedMs = 0;

    const TRAFFIC_COLORS = ['#f87171', '#fbbf24', '#c084fc', '#fb923c', '#f472b6'];

    function makePlayer() {
        return { lane: 1, x: laneCenterX(1), y: PLAYER_Y, w: CAR_W, h: CAR_H };
    }

    function loadHighScore() {
        highScore = parseInt(localStorage.getItem('ym_car_racer_high') || '0', 10);
        highScoreEl.textContent = String(highScore);
    }
    function saveHighScoreIfNeeded() {
        if (score > highScore) { highScore = Math.floor(score); localStorage.setItem('ym_car_racer_high', String(highScore)); }
    }

    function updateStats() {
        speedEl.textContent = Math.round(speed) + ' km/h';
        scoreEl.textContent = String(Math.floor(score));
        highScoreEl.textContent = String(Math.max(highScore, Math.floor(score)));
        livesEl.textContent = '🚗'.repeat(Math.max(0, lives));
    }

    function rectsOverlap(a, b) {
        return a.x - a.w / 2 < b.x + b.w / 2 && a.x + a.w / 2 > b.x - b.w / 2 &&
               a.y - a.h / 2 < b.y + b.h / 2 && a.y + a.h / 2 > b.y - b.h / 2;
    }

    function spawnParticles(x, y) {
        for (let i = 0; i < 10; i++) {
            const angle = (Math.PI * 2 * i) / 10;
            particles.push({ x, y, vx: Math.cos(angle) * 0.08, vy: Math.sin(angle) * 0.08, life: 0, maxLife: 400 });
        }
    }

    function spawnTraffic() {
        const lane = Math.floor(Math.random() * LANES);
        // 같은 차선 상단 근처에 이미 차량이 있으면 스폰을 건너뛰어(겹침 방지) 다음 시도 때 재시도
        const tooClose = traffic.some(t => t.lane === lane && t.y < CAR_H * 2.2);
        if (tooClose) return;
        traffic.push({
            lane, x: laneCenterX(lane), y: -CAR_H,
            w: CAR_W, h: CAR_H,
            color: TRAFFIC_COLORS[Math.floor(Math.random() * TRAFFIC_COLORS.length)],
        });
    }

    // ---------- 업데이트 ----------
    function updateSpeed(dt) {
        if (keysDown['ArrowUp']) speed += ACCEL * dt * (MAX_SPEED - MIN_SPEED) * 10;
        else if (keysDown['ArrowDown']) speed -= DECEL * dt * (MAX_SPEED - MIN_SPEED) * 10;
        else {
            // 아무 키도 안 누르면 기준 속도로 서서히 수렴
            if (speed > BASE_SPEED) speed -= NATURAL_DECAY * dt * (MAX_SPEED - MIN_SPEED) * 10;
            else if (speed < BASE_SPEED) speed += NATURAL_DECAY * dt * (MAX_SPEED - MIN_SPEED) * 10;
        }
        speed = Math.max(MIN_SPEED, Math.min(MAX_SPEED, speed));
    }

    function updatePlayerLane(dt) {
        const targetX = laneCenterX(player.lane);
        player.x += (targetX - player.x) * Math.min(1, dt / 90);
    }

    function updateTraffic(dt, time) {
        const speedFactor = speed / BASE_SPEED;
        traffic.forEach(t => { t.y += (0.09 * speedFactor) * dt; });
        traffic = traffic.filter(t => t.y - t.h < H + 20);

        const dynamicInterval = Math.max(420, spawnInterval - elapsedMs / 40);
        if (time - lastSpawnTime > dynamicInterval / speedFactor) {
            spawnTraffic();
            lastSpawnTime = time;
        }
    }

    function updateParticles(dt) {
        particles.forEach(p => { p.x += p.vx * dt; p.y += p.vy * dt; p.life += dt; });
        particles = particles.filter(p => p.life < p.maxLife);
    }

    function checkCollisions(time) {
        if (time < invincibleUntil) return;
        for (const t of traffic) {
            if (rectsOverlap(player, t)) {
                onCrash();
                break;
            }
        }
    }

    function onCrash() {
        lives--;
        updateStats();
        spawnParticles(player.x, player.y);
        if (lives <= 0) { gameOver(); return; }
        hub.setStatusBadge('충돌', 'lost');
        player = makePlayer();
        traffic = [];
        speed = BASE_SPEED;
        invincibleUntil = performance.now() + 1800;
    }

    // ---------- 렌더링 ----------
    function draw(time) {
        // 잔디
        ctx.fillStyle = '#1f7a3d';
        ctx.fillRect(0, 0, W, H);

        // 연석
        ctx.fillStyle = '#dc2626';
        ctx.fillRect(ROAD_LEFT - 10, 0, 10, H);
        ctx.fillRect(ROAD_RIGHT, 0, 10, H);

        // 도로
        ctx.fillStyle = '#3f3f46';
        ctx.fillRect(ROAD_LEFT, 0, ROAD_W, H);

        // 차선 점선 (아래로 흐르는 애니메이션)
        ctx.strokeStyle = '#facc15';
        ctx.lineWidth = 4;
        ctx.setLineDash([26, 22]);
        for (let i = 1; i < LANES; i++) {
            const x = ROAD_LEFT + LANE_W * i;
            ctx.beginPath();
            ctx.lineDashOffset = -laneOffset;
            ctx.moveTo(x, 0);
            ctx.lineTo(x, H);
            ctx.stroke();
        }
        ctx.setLineDash([]);

        // 무적 상태 깜빡임 처리
        const invincible = time < invincibleUntil;
        const blink = invincible && Math.floor(time / 100) % 2 === 0;

        // 상대 차량
        traffic.forEach(t => drawCar(t.x, t.y, t.color, false));

        // 플레이어 차량
        if (!blink) drawCar(player.x, player.y, '#38bdf8', true);

        // 파티클(충돌 이펙트)
        particles.forEach(p => {
            const alpha = Math.max(0, 1 - p.life / p.maxLife);
            ctx.globalAlpha = alpha;
            ctx.fillStyle = '#fbbf24';
            ctx.beginPath();
            ctx.arc(p.x, p.y, 2.4, 0, Math.PI * 2);
            ctx.fill();
        });
        ctx.globalAlpha = 1;
    }

    function drawCar(cx, cy, color, isPlayerCar) {
        const w = CAR_W, h = CAR_H;
        ctx.fillStyle = color;
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(cx - w / 2, cy - h / 2, w, h, 8);
        else ctx.rect(cx - w / 2, cy - h / 2, w, h);
        ctx.fill();

        // 창문
        ctx.fillStyle = 'rgba(224,242,254,0.85)';
        ctx.fillRect(cx - w / 2 + 5, cy - h / 2 + 8, w - 10, h * 0.28);
        ctx.fillRect(cx - w / 2 + 5, cy + h / 2 - h * 0.28 - 8, w - 10, h * 0.28);

        // 헤드라이트 / 테일라이트 (플레이어는 앞이 위, 상대는 앞이 아래)
        ctx.fillStyle = isPlayerCar ? '#fde68a' : '#fecaca';
        const lightY = isPlayerCar ? cy - h / 2 + 2 : cy + h / 2 - 4;
        ctx.fillRect(cx - w / 2 + 2, lightY, 6, 4);
        ctx.fillRect(cx + w / 2 - 8, lightY, 6, 4);
    }

    // ---------- 게임 흐름 ----------
    function loop(time = 0) {
        if (!isPlaying || isPaused) return;
        const dt = lastTime ? Math.min(50, time - lastTime) : 16;
        lastTime = time;
        elapsedMs += dt;

        updateSpeed(dt);
        updatePlayerLane(dt);
        updateTraffic(dt, time);
        updateParticles(dt);
        checkCollisions(time);

        laneOffset = (laneOffset + speed * dt * 0.02) % 48;
        score += (speed / BASE_SPEED) * dt * 0.012;

        updateStats();
        draw(time);

        if (isPlaying && !isPaused) animId = requestAnimationFrame(loop);
    }

    function moveLane(dir) {
        if (!isPlaying || isPaused) return;
        player.lane = Math.max(0, Math.min(LANES - 1, player.lane + dir));
    }

    function start() {
        score = 0; lives = 3; speed = BASE_SPEED;
        player = makePlayer();
        traffic = [];
        particles = [];
        keysDown = {};
        laneOffset = 0; elapsedMs = 0; lastSpawnTime = 0; invincibleUntil = 0;
        isPlaying = true; isPaused = false; lastTime = 0;

        btnStart.innerHTML = '<i class="fa-solid fa-gamepad"></i> 주행 중';
        btnStart.disabled = true;
        btnPause.disabled = false;
        btnPause.innerHTML = '<i class="fa-solid fa-pause"></i> 일시 정지';
        overlay.classList.add('hidden');
        hub.setStatusBadge('주행 중', 'playing');
        updateStats();

        cancelAnimationFrame(animId);
        loop(performance.now());
    }

    function togglePause() {
        if (!isPlaying) return;
        isPaused = !isPaused;
        if (isPaused) {
            btnPause.innerHTML = '<i class="fa-solid fa-play"></i> 계속 하기';
            hub.setStatusBadge('일시정지', 'paused');
            overlayTitle.textContent = '일시 정지';
            overlayTitle.style.color = '#f59e0b';
            overlayMsg.textContent = '카 레이서가 일시정지되었습니다.';
            btnOverlay.textContent = '계속 진행';
            overlay.dataset.nextAction = 'resume';
            overlay.classList.remove('hidden');
        } else {
            btnPause.innerHTML = '<i class="fa-solid fa-pause"></i> 일시 정지';
            hub.setStatusBadge('주행 중', 'playing');
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

        hub.setStatusBadge('게임 오버', 'lost');
        overlayTitle.textContent = '💥 게임 오버';
        overlayTitle.style.color = '#ef4444';
        overlayMsg.textContent = `최종 점수 ${Math.floor(score)}점 · 최고 속도 도달 ${Math.round(speed)} km/h`;
        btnOverlay.textContent = '다시 시작';
        overlay.dataset.nextAction = 'restart';
        overlay.classList.remove('hidden');
        updateStats();
        draw(performance.now());
    }

    function reset() {
        isPlaying = false; isPaused = false;
        cancelAnimationFrame(animId);
        score = 0; lives = 3; speed = BASE_SPEED;
        player = makePlayer();
        traffic = []; particles = []; keysDown = {};
        laneOffset = 0; elapsedMs = 0;

        btnStart.innerHTML = '<i class="fa-solid fa-play"></i> 게임 시작';
        btnStart.disabled = false;
        btnPause.disabled = true;
        overlay.classList.add('hidden');

        hub.setStatusBadge('대기 중', '');
        loadHighScore();
        updateStats();
        draw(0);
    }

    function onKeyDown(e) {
        if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(e.code)) {
            if (isPlaying && !isPaused) e.preventDefault();
        }
        if (!keysDown[e.code]) {
            if (e.code === 'ArrowLeft') moveLane(-1);
            if (e.code === 'ArrowRight') moveLane(1);
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

            container.querySelectorAll('.racer-touch-controls .touch-btn').forEach(btn => {
                const action = btn.dataset.action;
                if (action === 'left') btn.onclick = () => moveLane(-1);
                else if (action === 'right') btn.onclick = () => moveLane(1);
                else if (action === 'accel') {
                    btn.onmousedown = () => { keysDown['ArrowUp'] = true; };
                    btn.onmouseup = () => { keysDown['ArrowUp'] = false; };
                    btn.onmouseleave = () => { keysDown['ArrowUp'] = false; };
                    btn.ontouchstart = (e) => { e.preventDefault(); keysDown['ArrowUp'] = true; };
                    btn.ontouchend = (e) => { e.preventDefault(); keysDown['ArrowUp'] = false; };
                } else if (action === 'brake') {
                    btn.onmousedown = () => { keysDown['ArrowDown'] = true; };
                    btn.onmouseup = () => { keysDown['ArrowDown'] = false; };
                    btn.onmouseleave = () => { keysDown['ArrowDown'] = false; };
                    btn.ontouchstart = (e) => { e.preventDefault(); keysDown['ArrowDown'] = true; };
                    btn.ontouchend = (e) => { e.preventDefault(); keysDown['ArrowDown'] = false; };
                }
            });

            window.addEventListener('keydown', onKeyDown);
            window.addEventListener('keyup', onKeyUp);

            reset();
        

            setupPanelToggle('racer-left-col', 'racer-toggle-left', 'fa-solid fa-chevron-left', 'fa-solid fa-chevron-right');
            setupPanelToggle('racer-right-col', 'racer-toggle-right', 'fa-solid fa-chevron-right', 'fa-solid fa-chevron-left');
},
        destroy() {
            isPlaying = false;
            cancelAnimationFrame(animId);
            window.removeEventListener('keydown', onKeyDown);
            window.removeEventListener('keyup', onKeyUp);
        }
    };
});
