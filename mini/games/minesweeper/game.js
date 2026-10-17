// plugins/metadata/ym_mini_game/games/minesweeper/game.js

window.YmMiniGameHub.register('minesweeper', {
    name: '💣 지뢰찾기 (Minesweeper)',
    icon: 'fa-solid fa-bomb',
    order: 2
}, function (container, hub) {
    const HTML = `
    <div class="mine-game-root">
        <div class="game-sub-bar">
            <span class="game-view-name"><i class="fa-solid fa-bomb"></i> MINESWEEPER</span>
            <div class="sub-actions">
                <button id="mine-btn-restart" class="btn-banner primary"><i class="fa-solid fa-rotate-left"></i> 새 게임</button>
                <button id="mine-btn-flag-toggle" class="btn-banner secondary"><i class="fa-solid fa-flag"></i> 깃발 모드: <span id="mine-flag-mode-text">OFF</span></button>
            </div>
        </div>
        <div class="mine-stage-grid">
            <div class="stage-col left-col" id="mine-left-col">
                <button class="panel-toggle-btn" id="mine-toggle-left" title="패널 접기/펼치기"><i class="fa-solid fa-chevron-left"></i></button>
                <div class="panel-content">
                <div class="mini-panel-card">
                    <div class="panel-header"><i class="fa-solid fa-sliders"></i> 난이도 선택</div>
                    <div class="diff-btn-group">
                        <button class="diff-btn active" data-level="beginner">
                            <span class="diff-title">초급 (Easy)</span>
                            <span class="diff-spec">9 × 9 · 지뢰 10</span>
                        </button>
                        <button class="diff-btn" data-level="intermediate">
                            <span class="diff-title">중급 (Medium)</span>
                            <span class="diff-spec">16 × 16 · 지뢰 40</span>
                        </button>
                        <button class="diff-btn" data-level="expert">
                            <span class="diff-title">고급 (Hard)</span>
                            <span class="diff-spec">30 × 16 · 지뢰 99</span>
                        </button>
                    </div>
                </div>
                <div class="mini-panel-card">
                    <div class="panel-header"><i class="fa-solid fa-trophy"></i> 최단 시간 기록</div>
                    <div class="stat-grid">
                        <div class="stat-box"><span class="stat-lbl">초급</span><span id="best-beginner" class="stat-val">-</span></div>
                        <div class="stat-box"><span class="stat-lbl">중급</span><span id="best-intermediate" class="stat-val">-</span></div>
                        <div class="stat-box"><span class="stat-lbl">고급</span><span id="best-expert" class="stat-val">-</span></div>
                    </div>
                </div>
                </div>
            </div>
            <div class="stage-col center-col">
                <div class="mine-board-frame">
                    <div class="board-hud">
                        <div class="hud-box"><i class="fa-solid fa-bomb hud-icon"></i><span id="hud-mines-left" class="hud-num">010</span></div>
                        <button id="btn-hud-face" class="hud-face-btn" title="새 게임"><span id="hud-face-icon">😊</span></button>
                        <div class="hud-box"><i class="fa-solid fa-stopwatch hud-icon"></i><span id="hud-timer" class="hud-num">000</span></div>
                    </div>
                    <div id="mine-grid" class="mine-grid-wrapper"></div>
                    <div id="mine-overlay" class="game-overlay hidden">
                        <h2 id="mine-overlay-title">GAME OVER</h2>
                        <p id="mine-overlay-msg">지뢰를 밟았습니다!</p>
                        <button id="mine-btn-overlay-retry" class="btn-banner primary">다시 도전</button>
                    </div>
                </div>
            </div>
            <div class="stage-col right-col" id="mine-right-col">
                <button class="panel-toggle-btn" id="mine-toggle-right" title="패널 접기/펼치기"><i class="fa-solid fa-chevron-right"></i></button>
                <div class="panel-content">
                <div class="mini-panel-card">
                    <div class="panel-header"><i class="fa-regular fa-keyboard"></i> 조작 가이드</div>
                    <ul class="key-guide-list">
                        <li><span>셀 열기</span> <kbd>좌클릭</kbd></li>
                        <li><span>깃발</span> <kbd>우클릭</kbd></li>
                        <li><span>주변 동시 오픈</span> <kbd>더블클릭</kbd></li>
                        <li><span>모바일</span> <kbd>깃발 모드 버튼</kbd></li>
                    </ul>
                </div>
                <div class="mini-panel-card">
                    <div class="panel-header"><i class="fa-regular fa-lightbulb"></i> 첫 클릭 보장</div>
                    <p class="tip-text">• 첫 번째 클릭은 100% 안전하며 넓은 빈 공간이 먼저 열립니다.</p>
                </div>
                </div>
            </div>
        </div>
    </div>`;

    container.innerHTML = HTML;

    const LEVELS = {
        beginner: { rows: 9, cols: 9, mines: 10 },
        intermediate: { rows: 16, cols: 16, mines: 40 },
        expert: { rows: 16, cols: 30, mines: 99 }
    };
    let currentLevel = 'beginner', config = LEVELS[currentLevel];
    let grid = [], isGameOver = false, isGameWon = false, isFirstClick = true;
    let timer = 0, timerInterval = null, flagsPlaced = 0, isFlagMode = false;

    const gridEl = container.querySelector('#mine-grid');
    const hudMinesLeft = container.querySelector('#hud-mines-left');
    const hudTimer = container.querySelector('#hud-timer');
    const hudFaceIcon = container.querySelector('#hud-face-icon');
    const btnHudFace = container.querySelector('#btn-hud-face');
    const overlay = container.querySelector('#mine-overlay');
    const overlayTitle = container.querySelector('#mine-overlay-title');
    const overlayMsg = container.querySelector('#mine-overlay-msg');
    const btnOverlayRetry = container.querySelector('#mine-btn-overlay-retry');
    const btnRestart = container.querySelector('#mine-btn-restart');
    const btnFlagToggle = container.querySelector('#mine-btn-flag-toggle');
    const flagModeText = container.querySelector('#mine-flag-mode-text');

    function reset() {
        clearInterval(timerInterval);
        timer = 0; flagsPlaced = 0; isGameOver = false; isGameWon = false; isFirstClick = true;
        hudTimer.textContent = '000';
        hudFaceIcon.textContent = '😊';
        overlay.classList.add('hidden');
        hub.setStatusBadge('READY (MINES)', '');
        config = LEVELS[currentLevel];
        updateMinesLeft();
        createBoard();
    }

    function createBoard() {
        gridEl.innerHTML = '';
        gridEl.style.gridTemplateColumns = `repeat(${config.cols}, 32px)`;
        grid = [];
        for (let r = 0; r < config.rows; r++) {
            grid[r] = [];
            for (let c = 0; c < config.cols; c++) {
                const cellObj = { r, c, isMine: false, isRevealed: false, isFlagged: false, neighborMines: 0, el: null };
                const cellEl = document.createElement('div');
                cellEl.className = 'mine-cell';
                cellEl.onclick = () => onCellClick(r, c);
                cellEl.oncontextmenu = (e) => { e.preventDefault(); toggleFlag(r, c); };
                cellEl.ondblclick = () => onCellDblClick(r, c);
                cellObj.el = cellEl;
                grid[r][c] = cellObj;
                gridEl.appendChild(cellEl);
            }
        }
    }

    function placeMines(firstR, firstC) {
        let placed = 0;
        while (placed < config.mines) {
            const r = Math.floor(Math.random() * config.rows);
            const c = Math.floor(Math.random() * config.cols);
            const isNearFirst = Math.abs(r - firstR) <= 1 && Math.abs(c - firstC) <= 1;
            if (!grid[r][c].isMine && !isNearFirst) {
                grid[r][c].isMine = true;
                placed++;
            }
        }
        for (let r = 0; r < config.rows; r++) {
            for (let c = 0; c < config.cols; c++) {
                if (!grid[r][c].isMine) {
                    let count = 0;
                    for (let dr = -1; dr <= 1; dr++) {
                        for (let dc = -1; dc <= 1; dc++) {
                            const nr = r + dr, nc = c + dc;
                            if (nr >= 0 && nr < config.rows && nc >= 0 && nc < config.cols) {
                                if (grid[nr][nc].isMine) count++;
                            }
                        }
                    }
                    grid[r][c].neighborMines = count;
                }
            }
        }
    }

    function onCellClick(r, c) {
        if (isGameOver || isGameWon) return;
        if (isFlagMode) { toggleFlag(r, c); return; }
        const cell = grid[r][c];
        if (cell.isRevealed || cell.isFlagged) return;

        if (isFirstClick) {
            isFirstClick = false;
            placeMines(r, c);
            startTimer();
            hub.setStatusBadge('PLAYING (MINES)', 'playing');
        }

        if (cell.isMine) { gameOver(cell); return; }
        revealCell(r, c);
        checkWin();
    }

    function revealCell(r, c) {
        const cell = grid[r][c];
        if (cell.isRevealed || cell.isFlagged) return;
        cell.isRevealed = true;
        cell.el.classList.add('revealed');
        if (cell.neighborMines > 0) {
            cell.el.textContent = cell.neighborMines;
            cell.el.classList.add(`c-${cell.neighborMines}`);
        } else {
            for (let dr = -1; dr <= 1; dr++) {
                for (let dc = -1; dc <= 1; dc++) {
                    const nr = r + dr, nc = c + dc;
                    if (nr >= 0 && nr < config.rows && nc >= 0 && nc < config.cols) revealCell(nr, nc);
                }
            }
        }
    }

    function toggleFlag(r, c) {
        if (isGameOver || isGameWon) return;
        const cell = grid[r][c];
        if (cell.isRevealed) return;
        cell.isFlagged = !cell.isFlagged;
        if (cell.isFlagged) {
            cell.el.classList.add('flagged');
            cell.el.innerHTML = '<i class="fa-solid fa-flag"></i>';
            flagsPlaced++;
        } else {
            cell.el.classList.remove('flagged');
            cell.el.innerHTML = '';
            flagsPlaced--;
        }
        updateMinesLeft();
    }

    function updateMinesLeft() {
        const left = Math.max(0, config.mines - flagsPlaced);
        hudMinesLeft.textContent = String(left).padStart(3, '0');
    }

    function onCellDblClick(r, c) {
        if (isGameOver || isGameWon) return;
        const cell = grid[r][c];
        if (!cell.isRevealed || cell.neighborMines === 0) return;
        let flagCount = 0;
        for (let dr = -1; dr <= 1; dr++) {
            for (let dc = -1; dc <= 1; dc++) {
                const nr = r + dr, nc = c + dc;
                if (nr >= 0 && nr < config.rows && nc >= 0 && nc < config.cols) {
                    if (grid[nr][nc].isFlagged) flagCount++;
                }
            }
        }
        if (flagCount === cell.neighborMines) {
            for (let dr = -1; dr <= 1; dr++) {
                for (let dc = -1; dc <= 1; dc++) {
                    const nr = r + dr, nc = c + dc;
                    if (nr >= 0 && nr < config.rows && nc >= 0 && nc < config.cols) {
                        const target = grid[nr][nc];
                        if (!target.isRevealed && !target.isFlagged) {
                            if (target.isMine) { gameOver(target); return; }
                            revealCell(nr, nc);
                        }
                    }
                }
            }
            checkWin();
        }
    }

    function startTimer() {
        timerInterval = setInterval(() => {
            timer++;
            hudTimer.textContent = String(Math.min(999, timer)).padStart(3, '0');
        }, 1000);
    }

    function checkWin() {
        let unrevealedSafe = 0;
        for (let r = 0; r < config.rows; r++) {
            for (let c = 0; c < config.cols; c++) {
                if (!grid[r][c].isMine && !grid[r][c].isRevealed) unrevealedSafe++;
            }
        }
        if (unrevealedSafe === 0) {
            isGameWon = true;
            clearInterval(timerInterval);
            hudFaceIcon.textContent = '😎';
            hub.setStatusBadge('WON', 'won');
            saveBestScore(currentLevel, timer);
            overlayTitle.textContent = '🎉 승리했습니다!';
            overlayTitle.style.color = '#10b981';
            overlayMsg.textContent = `${timer}초 만에 클리어!`;
            overlay.classList.remove('hidden');
        }
    }

    function gameOver(hitCell) {
        isGameOver = true;
        clearInterval(timerInterval);
        hudFaceIcon.textContent = '😵';
        hub.setStatusBadge('LOST', 'lost');
        for (let r = 0; r < config.rows; r++) {
            for (let c = 0; c < config.cols; c++) {
                if (grid[r][c].isMine) {
                    grid[r][c].el.classList.add('revealed', 'mine');
                    grid[r][c].el.innerHTML = '<i class="fa-solid fa-bomb"></i>';
                }
            }
        }
        if (hitCell) hitCell.el.style.backgroundColor = '#dc2626';
        overlayTitle.textContent = '💥 GAME OVER';
        overlayTitle.style.color = '#ef4444';
        overlayMsg.textContent = '지뢰를 밟았습니다!';
        overlay.classList.remove('hidden');
    }

    function saveBestScore(lvl, sec) {
        const key = `ym_mines_best_${lvl}`;
        const best = parseInt(localStorage.getItem(key) || '999999', 10);
        if (sec < best) localStorage.setItem(key, sec);
        loadBestScores();
    }

    function loadBestScores() {
        ['beginner', 'intermediate', 'expert'].forEach(lvl => {
            const b = localStorage.getItem(`ym_mines_best_${lvl}`);
            const el = container.querySelector(`#best-${lvl}`);
            if (el) el.textContent = b ? `${b}초` : '-';
        });
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
            btnRestart.onclick = reset;
            btnHudFace.onclick = reset;
            btnOverlayRetry.onclick = reset;
            btnFlagToggle.onclick = () => {
                isFlagMode = !isFlagMode;
                flagModeText.textContent = isFlagMode ? 'ON' : 'OFF';
                btnFlagToggle.classList.toggle('active-flag', isFlagMode);
            };

            container.querySelectorAll('.diff-btn').forEach(btn => {
                btn.onclick = () => {
                    container.querySelectorAll('.diff-btn').forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    currentLevel = btn.dataset.level;
                    reset();
                };
            });

            setupPanelToggle('mine-left-col', 'mine-toggle-left', 'fa-solid fa-chevron-left', 'fa-solid fa-chevron-right');
            setupPanelToggle('mine-right-col', 'mine-toggle-right', 'fa-solid fa-chevron-right', 'fa-solid fa-chevron-left');

            loadBestScores();
            reset();
        },
        destroy() {
            clearInterval(timerInterval);
        }
    };
});
