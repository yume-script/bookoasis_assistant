// plugins/metadata/ym_mini_game/games/sokoban/game.js

window.YmMiniGameHub.register('sokoban', {
    name: '📦 소코반 (Sokoban)',
    icon: 'fa-solid fa-dolly',
    order: 6
}, function (container, hub) {
    const HTML = `
    <div class="sokoban-game-root">
        <div class="game-sub-bar">
            <span class="game-view-name"><i class="fa-solid fa-dolly"></i> SOKOBAN</span>
            <div class="sub-actions">
                <button id="soko-btn-restart" class="btn-banner primary"><i class="fa-solid fa-rotate-left"></i> 레벨 재시작</button>
                <button id="soko-btn-undo" class="btn-banner secondary"><i class="fa-solid fa-arrow-rotate-left"></i> 실행 취소</button>
                <button id="soko-btn-reset-all" class="btn-banner danger"><i class="fa-solid fa-house"></i> 처음부터</button>
            </div>
        </div>

        <div class="sokoban-stage-grid">
            <div class="stage-col left-col" id="soko-left-col">
            <button class="panel-toggle-btn" id="soko-toggle-left" title="패널 접기/펼치기"><i class="fa-solid fa-chevron-left"></i></button>
            <div class="panel-content">
                <div class="mini-panel-card">
                    <div class="panel-header"><i class="fa-solid fa-chart-simple"></i> STATISTICS</div>
                    <div class="stat-grid">
                        <div class="stat-box"><span class="stat-lbl">레벨</span><span id="soko-level" class="stat-val highlight">1 / 6</span></div>
                        <div class="stat-box"><span class="stat-lbl">이동 수</span><span id="soko-moves" class="stat-val">0</span></div>
                        <div class="stat-box"><span class="stat-lbl">민 횟수</span><span id="soko-pushes" class="stat-val">0</span></div>
                        <div class="stat-box"><span class="stat-lbl">최고 기록(이 레벨)</span><span id="soko-best" class="stat-val">-</span></div>
                    </div>
                </div>
                <div class="mini-panel-card">
                    <div class="panel-header"><i class="fa-regular fa-lightbulb"></i> 게임 방법</div>
                    <p class="tip-text">
                        • 방향키(또는 버튼)로 캐릭터를 움직여 박스(📦)를 목표 지점(◎)까지 밀어 넣으세요.<br>
                        • 박스는 밀 수만 있고 당길 수는 없습니다. 벽이나 다른 박스가 있으면 밀 수 없습니다.<br>
                        • 모든 박스를 목표 지점에 올리면 레벨 클리어!
                    </p>
                </div>
            
            </div></div>

            <div class="stage-col center-col">
                <div class="sokoban-board-frame">
                    <canvas id="soko-board" width="440" height="380"></canvas>
                    <div id="soko-overlay" class="game-overlay hidden">
                        <h2 id="soko-overlay-title">LEVEL CLEAR</h2>
                        <p id="soko-overlay-msg"></p>
                        <button id="soko-btn-overlay-action" class="btn-banner primary">다음 레벨</button>
                    </div>
                </div>
            </div>

            <div class="stage-col right-col" id="soko-right-col">
            <button class="panel-toggle-btn" id="soko-toggle-right" title="패널 접기/펼치기"><i class="fa-solid fa-chevron-right"></i></button>
            <div class="panel-content">
                <div class="mini-panel-card">
                    <div class="panel-header"><i class="fa-regular fa-keyboard"></i> 조작 가이드</div>
                    <ul class="key-guide-list">
                        <li><span>이동/밀기</span> <div class="key-group"><kbd>↑</kbd><kbd>↓</kbd><kbd>←</kbd><kbd>→</kbd></div></li>
                        <li><span>실행 취소</span> <kbd>Z</kbd></li>
                        <li><span>레벨 재시작</span> <kbd>R</kbd></li>
                    </ul>
                </div>
                <div class="sokoban-touch-controls">
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

    // BFS 솔버로 전부 해결 가능함을 검증한 레벨입니다 (# 벽, 공백 바닥, . 목표, $ 박스, @ 플레이어)
    const LEVELS = [
        "#######\n#     #\n#  .  #\n#  $  #\n#  @  #\n#     #\n#######",
        "########\n#      #\n#  .   #\n#  $   #\n#      #\n#   $  #\n#   .  #\n#  @   #\n########",
        "#########\n#   #   #\n# .   . #\n#  $ $  #\n#   @   #\n#   #   #\n#########",
        "##########\n#        #\n#  .  .  #\n#  $  $  #\n#    .   #\n#    $   #\n#   @    #\n#        #\n##########",
        "###########\n#    #    #\n# .  #  . #\n# $     $ #\n#    .    #\n#    $    #\n#  @      #\n#         #\n###########",
        "############\n#          #\n#  .    .  #\n#  $    $  #\n#          #\n#     .    #\n#     $    #\n#  .       #\n#  $  @    #\n#          #\n############",
    ];

    const CELL = 40;
    const canvas = container.querySelector('#soko-board');
    const ctx = canvas.getContext('2d');

    const levelEl = container.querySelector('#soko-level');
    const movesEl = container.querySelector('#soko-moves');
    const pushesEl = container.querySelector('#soko-pushes');
    const bestEl = container.querySelector('#soko-best');

    const overlay = container.querySelector('#soko-overlay');
    const overlayTitle = container.querySelector('#soko-overlay-title');
    const overlayMsg = container.querySelector('#soko-overlay-msg');
    const btnOverlay = container.querySelector('#soko-btn-overlay-action');

    const btnRestart = container.querySelector('#soko-btn-restart');
    const btnUndo = container.querySelector('#soko-btn-undo');
    const btnResetAll = container.querySelector('#soko-btn-reset-all');

    let currentLevelIndex = 0;
    let walls, targets, boxes, player, cols, rows;
    let initialBoxes, initialPlayer;
    let moves = 0, pushes = 0;
    let history = [];
    let isCleared = false;

    function key(x, y) { return x + ',' + y; }

    function parseLevel(str) {
        const lines = str.split('\n');
        const w = Math.max(...lines.map(l => l.length));
        const wallsSet = new Set();
        const targetsSet = new Set();
        const boxesSet = new Set();
        let playerPos = null;

        lines.forEach((line, y) => {
            for (let x = 0; x < w; x++) {
                const ch = line[x] || ' ';
                if (ch === '#') wallsSet.add(key(x, y));
                else if (ch === '.') targetsSet.add(key(x, y));
                else if (ch === '$') boxesSet.add(key(x, y));
                else if (ch === '@') playerPos = { x, y };
            }
        });

        return { walls: wallsSet, targets: targetsSet, boxes: boxesSet, player: playerPos, cols: w, rows: lines.length };
    }

    function loadLevel(index) {
        const parsed = parseLevel(LEVELS[index]);
        walls = parsed.walls;
        targets = parsed.targets;
        boxes = new Set(parsed.boxes);
        player = { x: parsed.player.x, y: parsed.player.y };
        cols = parsed.cols; rows = parsed.rows;

        initialBoxes = new Set(boxes);
        initialPlayer = { x: player.x, y: player.y };

        moves = 0; pushes = 0;
        history = [];
        isCleared = false;

        canvas.width = cols * CELL;
        canvas.height = rows * CELL;

        overlay.classList.add('hidden');
        updateStats();
        draw();
    }

    function loadBest() {
        const raw = localStorage.getItem('ym_sokoban_best_L' + (currentLevelIndex + 1));
        bestEl.textContent = raw ? raw + '수' : '-';
    }

    function saveBestIfNeeded() {
        const key = 'ym_sokoban_best_L' + (currentLevelIndex + 1);
        const prev = parseInt(localStorage.getItem(key) || '999999', 10);
        if (moves < prev) localStorage.setItem(key, String(moves));
        loadBest();
    }

    function updateStats() {
        levelEl.textContent = (currentLevelIndex + 1) + ' / ' + LEVELS.length;
        movesEl.textContent = String(moves);
        pushesEl.textContent = String(pushes);
        loadBest();
    }

    function isWin() {
        if (boxes.size !== targets.size) return false;
        for (const b of boxes) if (!targets.has(b)) return false;
        return true;
    }

    function tryMove(dx, dy) {
        if (isCleared) return;
        const nx = player.x + dx, ny = player.y + dy;
        const nk = key(nx, ny);
        if (walls.has(nk)) return;

        let pushedBox = null;
        if (boxes.has(nk)) {
            const bnx = nx + dx, bny = ny + dy;
            const bnk = key(bnx, bny);
            if (walls.has(bnk) || boxes.has(bnk)) return; // 밀 수 없음
            boxes.delete(nk);
            boxes.add(bnk);
            pushedBox = { from: nk, to: bnk };
            pushes++;
        }

        history.push({ playerFrom: { x: player.x, y: player.y }, playerTo: { x: nx, y: ny }, pushedBox });
        player = { x: nx, y: ny };
        moves++;
        updateStats();
        draw();

        if (isWin()) {
            onLevelClear();
        }
    }

    function undo() {
        if (history.length === 0 || isCleared) return;
        const last = history.pop();
        player = { x: last.playerFrom.x, y: last.playerFrom.y };
        if (last.pushedBox) {
            boxes.delete(last.pushedBox.to);
            boxes.add(last.pushedBox.from);
            pushes = Math.max(0, pushes - 1);
        }
        moves = Math.max(0, moves - 1);
        updateStats();
        draw();
    }

    function onLevelClear() {
        isCleared = true;
        saveBestIfNeeded();
        hub.setStatusBadge('LEVEL CLEAR', 'won');

        const isLast = currentLevelIndex >= LEVELS.length - 1;
        overlayTitle.textContent = isLast ? '🏆 전체 클리어!' : '🎉 레벨 클리어!';
        overlayTitle.style.color = '#10b981';
        overlayMsg.textContent = isLast
            ? `모든 레벨을 완료했습니다! (이 레벨 ${moves}수, ${pushes}회 밀기)`
            : `${moves}수 만에 클리어! (${pushes}회 밀기)`;
        btnOverlay.textContent = isLast ? '처음부터 다시' : '다음 레벨';
        overlay.dataset.nextAction = isLast ? 'restartAll' : 'nextLevel';
        overlay.classList.remove('hidden');
        draw();
    }

    function nextLevel() {
        currentLevelIndex = Math.min(currentLevelIndex + 1, LEVELS.length - 1);
        loadLevel(currentLevelIndex);
        hub.setStatusBadge('PLAYING (SOKOBAN)', 'playing');
    }

    function restartLevel() {
        boxes = new Set(initialBoxes);
        player = { x: initialPlayer.x, y: initialPlayer.y };
        moves = 0; pushes = 0; history = []; isCleared = false;
        overlay.classList.add('hidden');
        updateStats();
        draw();
        hub.setStatusBadge('PLAYING (SOKOBAN)', 'playing');
    }

    function resetAll() {
        currentLevelIndex = 0;
        loadLevel(currentLevelIndex);
        hub.setStatusBadge('READY (SOKOBAN)', '');
    }

    // ---------- 렌더링 ----------
    function draw() {
        ctx.fillStyle = '#1c1917';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        for (let y = 0; y < rows; y++) {
            for (let x = 0; x < cols; x++) {
                const k = key(x, y);
                const px = x * CELL, py = y * CELL;

                if (walls.has(k)) {
                    ctx.fillStyle = '#44403c';
                    ctx.fillRect(px, py, CELL, CELL);
                    ctx.strokeStyle = '#292524';
                    ctx.lineWidth = 2;
                    ctx.strokeRect(px + 1, py + 1, CELL - 2, CELL - 2);
                } else {
                    ctx.fillStyle = '#292524';
                    ctx.fillRect(px, py, CELL, CELL);
                    if (targets.has(k)) {
                        ctx.strokeStyle = '#facc15';
                        ctx.lineWidth = 2;
                        ctx.beginPath();
                        ctx.arc(px + CELL / 2, py + CELL / 2, CELL * 0.22, 0, Math.PI * 2);
                        ctx.stroke();
                    }
                }
            }
        }

        // 박스
        boxes.forEach(k => {
            const [x, y] = k.split(',').map(Number);
            const px = x * CELL, py = y * CELL;
            const onTarget = targets.has(k);
            ctx.fillStyle = onTarget ? '#16a34a' : '#b45309';
            ctx.fillRect(px + 4, py + 4, CELL - 8, CELL - 8);
            ctx.strokeStyle = onTarget ? '#166534' : '#78350f';
            ctx.lineWidth = 2;
            ctx.strokeRect(px + 4, py + 4, CELL - 8, CELL - 8);
            ctx.beginPath();
            ctx.moveTo(px + 4, py + 4);
            ctx.lineTo(px + CELL - 4, py + CELL - 4);
            ctx.moveTo(px + CELL - 4, py + 4);
            ctx.lineTo(px + 4, py + CELL - 4);
            ctx.stroke();
        });

        // 플레이어
        const ppx = player.x * CELL, ppy = player.y * CELL;
        ctx.fillStyle = '#38bdf8';
        ctx.beginPath();
        ctx.arc(ppx + CELL / 2, ppy + CELL / 2, CELL * 0.32, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = '#0f172a';
        ctx.beginPath();
        ctx.arc(ppx + CELL / 2 - 5, ppy + CELL / 2 - 3, 2.2, 0, Math.PI * 2);
        ctx.arc(ppx + CELL / 2 + 5, ppy + CELL / 2 - 3, 2.2, 0, Math.PI * 2);
        ctx.fill();
    }

    function onKeyDown(e) {
        if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.code)) e.preventDefault();
        switch (e.code) {
            case 'ArrowUp': tryMove(0, -1); break;
            case 'ArrowDown': tryMove(0, 1); break;
            case 'ArrowLeft': tryMove(-1, 0); break;
            case 'ArrowRight': tryMove(1, 0); break;
            case 'KeyZ': undo(); break;
            case 'KeyR': restartLevel(); break;
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
            btnRestart.onclick = restartLevel;
            btnUndo.onclick = undo;
            btnResetAll.onclick = resetAll;
            btnOverlay.onclick = () => {
                const action = overlay.dataset.nextAction;
                if (action === 'nextLevel') nextLevel();
                else resetAll();
            };

            container.querySelectorAll('.sokoban-touch-controls .touch-btn').forEach(btn => {
                btn.onclick = () => {
                    const dir = btn.dataset.dir;
                    if (dir === 'up') tryMove(0, -1);
                    if (dir === 'down') tryMove(0, 1);
                    if (dir === 'left') tryMove(-1, 0);
                    if (dir === 'right') tryMove(1, 0);
                };
            });

            window.addEventListener('keydown', onKeyDown);

            currentLevelIndex = 0;
            loadLevel(currentLevelIndex);
            hub.setStatusBadge('READY (SOKOBAN)', '');
        

            setupPanelToggle('soko-left-col', 'soko-toggle-left', 'fa-solid fa-chevron-left', 'fa-solid fa-chevron-right');
            setupPanelToggle('soko-right-col', 'soko-toggle-right', 'fa-solid fa-chevron-right', 'fa-solid fa-chevron-left');
},
        destroy() {
            window.removeEventListener('keydown', onKeyDown);
        }
    };
});
