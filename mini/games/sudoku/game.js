// plugins/metadata/ym_mini_game/games/sudoku/game.js

window.YmMiniGameHub.register('sudoku', {
    name: '🔢 스도쿠 (Sudoku)',
    icon: 'fa-solid fa-table-cells',
    order: 7
}, function (container, hub) {
    const HTML = `
    <div class="sudoku-game-root">
        <div class="game-sub-bar">
            <span class="game-view-name"><i class="fa-solid fa-table-cells"></i> SUDOKU</span>
            <div class="sub-actions">
                <div class="diff-select-wrapper">
                    <button class="diff-pill active" data-diff="easy">쉬움</button>
                    <button class="diff-pill" data-diff="medium">보통</button>
                    <button class="diff-pill" data-diff="hard">어려움</button>
                </div>
                <button id="sudoku-btn-new" class="btn-banner primary"><i class="fa-solid fa-plus"></i> 새 게임</button>
            </div>
        </div>

        <div class="sudoku-stage-grid">
            <div class="stage-col left-col" id="sudoku-left-col">
            <button class="panel-toggle-btn" id="sudoku-toggle-left" title="패널 접기/펼치기"><i class="fa-solid fa-chevron-left"></i></button>
            <div class="panel-content">
                <div class="mini-panel-card">
                    <div class="panel-header"><i class="fa-solid fa-chart-simple"></i> STATISTICS</div>
                    <div class="stat-grid">
                        <div class="stat-box"><span class="stat-lbl">시간</span><span id="sudoku-timer" class="stat-val highlight">00:00</span></div>
                        <div class="stat-box"><span class="stat-lbl">실수</span><span id="sudoku-mistakes" class="stat-val">0</span></div>
                        <div class="stat-box"><span class="stat-lbl">힌트 남음</span><span id="sudoku-hints" class="stat-val">3</span></div>
                        <div class="stat-box"><span class="stat-lbl">최고 기록</span><span id="sudoku-best" class="stat-val">-</span></div>
                    </div>
                </div>
                <div class="mini-panel-card">
                    <div class="panel-header"><i class="fa-regular fa-lightbulb"></i> 게임 방법</div>
                    <p class="tip-text">
                        • 각 가로줄·세로줄·3×3 박스에 1~9 숫자가 겹치지 않게 채우세요.<br>
                        • 셀을 선택하고 숫자 버튼(또는 키보드 1~9)으로 입력합니다.<br>
                        • 메모 모드를 켜면 후보 숫자를 작게 적어둘 수 있습니다.<br>
                        • 충돌하는 숫자는 빨간색으로 표시됩니다.
                    </p>
                </div>
            
            </div></div>

            <div class="stage-col center-col">
                <div class="sudoku-board-frame">
                    <canvas id="sudoku-board" width="450" height="450"></canvas>
                    <div id="sudoku-overlay" class="game-overlay hidden">
                        <h2 id="sudoku-overlay-title">CLEAR!</h2>
                        <p id="sudoku-overlay-msg"></p>
                        <button id="sudoku-btn-overlay-action" class="btn-banner primary">새 게임</button>
                    </div>
                </div>
            </div>

            <div class="stage-col right-col" id="sudoku-right-col">
            <button class="panel-toggle-btn" id="sudoku-toggle-right" title="패널 접기/펼치기"><i class="fa-solid fa-chevron-right"></i></button>
            <div class="panel-content">
                <div class="mini-panel-card">
                    <div class="panel-header"><i class="fa-solid fa-keyboard"></i> 숫자 입력</div>
                    <div class="number-pad">
                        <button class="num-btn" data-num="1">1</button>
                        <button class="num-btn" data-num="2">2</button>
                        <button class="num-btn" data-num="3">3</button>
                        <button class="num-btn" data-num="4">4</button>
                        <button class="num-btn" data-num="5">5</button>
                        <button class="num-btn" data-num="6">6</button>
                        <button class="num-btn" data-num="7">7</button>
                        <button class="num-btn" data-num="8">8</button>
                        <button class="num-btn" data-num="9">9</button>
                    </div>
                    <div class="pad-actions">
                        <button id="sudoku-btn-erase" class="btn-banner secondary"><i class="fa-solid fa-eraser"></i> 지우기</button>
                        <button id="sudoku-btn-note" class="btn-banner secondary"><i class="fa-solid fa-pencil"></i> 메모 모드: <span id="sudoku-note-status">OFF</span></button>
                        <button id="sudoku-btn-hint" class="btn-banner primary"><i class="fa-solid fa-wand-magic-sparkles"></i> 힌트</button>
                    </div>
                </div>
            
            </div></div>
        </div>
    </div>`;

    container.innerHTML = HTML;

    // ---------- 스도쿠 생성/솔버 핵심 로직 (독립 검증 완료) ----------
    function makeEmptyGrid() { return Array.from({ length: 9 }, () => new Array(9).fill(0)); }

    function shuffle(arr) {
        for (let i = arr.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [arr[i], arr[j]] = [arr[j], arr[i]];
        }
        return arr;
    }

    function isValidPlacement(grid, row, col, val) {
        for (let i = 0; i < 9; i++) {
            if (i !== col && grid[row][i] === val) return false;
            if (i !== row && grid[i][col] === val) return false;
        }
        const br = Math.floor(row / 3) * 3, bc = Math.floor(col / 3) * 3;
        for (let r = br; r < br + 3; r++) {
            for (let c = bc; c < bc + 3; c++) {
                if ((r !== row || c !== col) && grid[r][c] === val) return false;
            }
        }
        return true;
    }

    function findEmpty(grid) {
        for (let r = 0; r < 9; r++) for (let c = 0; c < 9; c++) if (grid[r][c] === 0) return [r, c];
        return null;
    }

    function fillGrid(grid) {
        const pos = findEmpty(grid);
        if (!pos) return true;
        const [r, c] = pos;
        for (const v of shuffle([1, 2, 3, 4, 5, 6, 7, 8, 9])) {
            if (isValidPlacement(grid, r, c, v)) {
                grid[r][c] = v;
                if (fillGrid(grid)) return true;
                grid[r][c] = 0;
            }
        }
        return false;
    }

    function generateFullGrid() { const g = makeEmptyGrid(); fillGrid(g); return g; }

    function countSolutions(grid, cap) {
        let count = 0;
        function backtrack() {
            if (count >= cap) return;
            const pos = findEmpty(grid);
            if (!pos) { count++; return; }
            const [r, c] = pos;
            for (let v = 1; v <= 9; v++) {
                if (count >= cap) return;
                if (isValidPlacement(grid, r, c, v)) {
                    grid[r][c] = v;
                    backtrack();
                    grid[r][c] = 0;
                    if (count >= cap) return;
                }
            }
        }
        backtrack();
        return count;
    }

    function allPositions() {
        const list = [];
        for (let r = 0; r < 9; r++) for (let c = 0; c < 9; c++) list.push([r, c]);
        return list;
    }

    function generatePuzzle(targetClues) {
        const solved = generateFullGrid();
        const puzzle = solved.map(row => row.slice());
        const positions = shuffle(allPositions());
        let clues = 81;

        for (const [r, c] of positions) {
            if (clues <= targetClues) break;
            const backup = puzzle[r][c];
            if (backup === 0) continue;
            puzzle[r][c] = 0;
            const testGrid = puzzle.map(row => row.slice());
            if (countSolutions(testGrid, 2) === 1) {
                clues--;
            } else {
                puzzle[r][c] = backup;
            }
        }
        return { puzzle, solution: solved };
    }

    // ---------- 게임 상태 ----------
    const CELL = 50;
    const DIFF_CLUES = { easy: 40, medium: 32, hard: 26 };

    const canvas = container.querySelector('#sudoku-board');
    const ctx = canvas.getContext('2d');

    const timerEl = container.querySelector('#sudoku-timer');
    const mistakesEl = container.querySelector('#sudoku-mistakes');
    const hintsEl = container.querySelector('#sudoku-hints');
    const bestEl = container.querySelector('#sudoku-best');

    const overlay = container.querySelector('#sudoku-overlay');
    const overlayTitle = container.querySelector('#sudoku-overlay-title');
    const overlayMsg = container.querySelector('#sudoku-overlay-msg');
    const btnOverlay = container.querySelector('#sudoku-btn-overlay-action');

    const btnNew = container.querySelector('#sudoku-btn-new');
    const btnErase = container.querySelector('#sudoku-btn-erase');
    const btnNote = container.querySelector('#sudoku-btn-note');
    const btnHint = container.querySelector('#sudoku-btn-hint');
    const noteStatusEl = container.querySelector('#sudoku-note-status');

    let difficulty = 'easy';
    let given, userGrid, solution, notes;
    let selected = null;
    let noteMode = false;
    let mistakes = 0, hintsLeft = 3, seconds = 0, timerInterval = null;
    let isWon = false;

    function loadBest() {
        const raw = localStorage.getItem('ym_sudoku_best_' + difficulty);
        bestEl.textContent = raw ? formatTime(parseInt(raw, 10)) : '-';
    }

    function saveBestIfNeeded() {
        const key = 'ym_sudoku_best_' + difficulty;
        const prev = parseInt(localStorage.getItem(key) || '999999', 10);
        if (seconds < prev) localStorage.setItem(key, String(seconds));
        loadBest();
    }

    function formatTime(s) {
        const m = Math.floor(s / 60), sec = s % 60;
        return String(m).padStart(2, '0') + ':' + String(sec).padStart(2, '0');
    }

    function updateStats() {
        timerEl.textContent = formatTime(seconds);
        mistakesEl.textContent = String(mistakes);
        hintsEl.textContent = String(hintsLeft);
    }

    function startTimer() {
        clearInterval(timerInterval);
        timerInterval = setInterval(() => {
            if (!isWon) { seconds++; updateStats(); }
        }, 1000);
    }

    function newGame(diff) {
        difficulty = diff || difficulty;
        container.querySelectorAll('.diff-pill').forEach(p => p.classList.toggle('active', p.dataset.diff === difficulty));

        const { puzzle, solution: sol } = generatePuzzle(DIFF_CLUES[difficulty]);
        given = puzzle.map(row => row.map(v => v !== 0));
        userGrid = puzzle.map(row => row.slice());
        solution = sol;
        notes = Array.from({ length: 9 }, () => Array.from({ length: 9 }, () => new Set()));

        selected = null;
        mistakes = 0; hintsLeft = 3; seconds = 0; isWon = false;
        noteMode = false;
        noteStatusEl.textContent = 'OFF';

        overlay.classList.add('hidden');
        hub.setStatusBadge('PLAYING (SUDOKU)', 'playing');
        loadBest();
        updateStats();
        startTimer();
        draw();
    }

    function getConflictSet() {
        const conflicts = new Set();
        for (let r = 0; r < 9; r++) {
            for (let c = 0; c < 9; c++) {
                const v = userGrid[r][c];
                if (v !== 0 && !isValidPlacement(userGrid, r, c, v)) conflicts.add(r + ',' + c);
            }
        }
        return conflicts;
    }

    function isBoardFull() {
        for (let r = 0; r < 9; r++) for (let c = 0; c < 9; c++) if (userGrid[r][c] === 0) return false;
        return true;
    }

    function checkWin() {
        if (isBoardFull() && getConflictSet().size === 0) {
            isWon = true;
            clearInterval(timerInterval);
            saveBestIfNeeded();
            hub.setStatusBadge('CLEAR', 'won');
            overlayTitle.textContent = '🎉 클리어!';
            overlayTitle.style.color = '#10b981';
            overlayMsg.textContent = `${formatTime(seconds)} · 실수 ${mistakes}회 · 힌트 ${3 - hintsLeft}회 사용`;
            btnOverlay.textContent = '새 게임';
            overlay.classList.remove('hidden');
            draw();
            return true;
        }
        return false;
    }

    function selectCell(r, c) {
        selected = { r, c };
        draw();
    }

    function inputNumber(n) {
        if (!selected || isWon) return;
        const { r, c } = selected;
        if (given[r][c]) return;

        if (noteMode) {
            if (userGrid[r][c] !== 0) return;
            if (notes[r][c].has(n)) notes[r][c].delete(n);
            else notes[r][c].add(n);
            draw();
            return;
        }

        const wasConflictFree = userGrid[r][c] === 0 || isValidPlacement(userGrid, r, c, userGrid[r][c]);
        userGrid[r][c] = n;
        notes[r][c].clear();

        if (!isValidPlacement(userGrid, r, c, n)) {
            mistakes++;
        }
        updateStats();
        draw();
        checkWin();
    }

    function eraseCell() {
        if (!selected || isWon) return;
        const { r, c } = selected;
        if (given[r][c]) return;
        userGrid[r][c] = 0;
        notes[r][c].clear();
        draw();
    }

    function useHint() {
        if (isWon || hintsLeft <= 0) return;
        let target = null;
        if (selected && !given[selected.r][selected.c] && userGrid[selected.r][selected.c] === 0) {
            target = selected;
        } else {
            const emptyCells = [];
            for (let r = 0; r < 9; r++) for (let c = 0; c < 9; c++) if (userGrid[r][c] === 0) emptyCells.push({ r, c });
            if (emptyCells.length === 0) return;
            target = emptyCells[Math.floor(Math.random() * emptyCells.length)];
        }
        userGrid[target.r][target.c] = solution[target.r][target.c];
        notes[target.r][target.c].clear();
        hintsLeft--;
        selected = target;
        updateStats();
        draw();
        checkWin();
    }

    function toggleNoteMode() {
        noteMode = !noteMode;
        noteStatusEl.textContent = noteMode ? 'ON' : 'OFF';
    }

    // ---------- 렌더링 ----------
    function draw() {
        ctx.fillStyle = '#fdfaf3';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        const conflicts = getConflictSet();

        // 선택 셀의 행/열/박스 하이라이트
        if (selected) {
            ctx.fillStyle = 'rgba(56,189,248,0.12)';
            ctx.fillRect(0, selected.r * CELL, canvas.width, CELL);
            ctx.fillRect(selected.c * CELL, 0, CELL, canvas.height);
            const br = Math.floor(selected.r / 3) * 3, bc = Math.floor(selected.c / 3) * 3;
            ctx.fillRect(bc * CELL, br * CELL, CELL * 3, CELL * 3);
        }

        // 숫자/노트
        for (let r = 0; r < 9; r++) {
            for (let c = 0; c < 9; c++) {
                const px = c * CELL, py = r * CELL;
                const isSelected = selected && selected.r === r && selected.c === c;
                const isConflict = conflicts.has(r + ',' + c);

                if (isSelected) {
                    ctx.fillStyle = 'rgba(56,189,248,0.28)';
                    ctx.fillRect(px, py, CELL, CELL);
                }

                const v = userGrid[r][c];
                if (v !== 0) {
                    ctx.font = given[r][c] ? 'bold 24px sans-serif' : '24px sans-serif';
                    ctx.textAlign = 'center';
                    ctx.textBaseline = 'middle';
                    ctx.fillStyle = isConflict ? '#ef4444' : (given[r][c] ? '#1c1917' : '#0369a1');
                    ctx.fillText(String(v), px + CELL / 2, py + CELL / 2 + 1);
                } else if (notes[r][c].size > 0) {
                    ctx.font = '9px sans-serif';
                    ctx.fillStyle = '#78716c';
                    ctx.textAlign = 'center';
                    ctx.textBaseline = 'middle';
                    notes[r][c].forEach(n => {
                        const nr = Math.floor((n - 1) / 3), nc = (n - 1) % 3;
                        ctx.fillText(String(n), px + CELL / 6 + nc * CELL / 3, py + CELL / 6 + nr * CELL / 3);
                    });
                }
            }
        }

        // 그리드 선
        for (let i = 0; i <= 9; i++) {
            ctx.strokeStyle = i % 3 === 0 ? '#1c1917' : '#d6d3d1';
            ctx.lineWidth = i % 3 === 0 ? 2.5 : 1;
            ctx.beginPath(); ctx.moveTo(i * CELL, 0); ctx.lineTo(i * CELL, canvas.height); ctx.stroke();
            ctx.beginPath(); ctx.moveTo(0, i * CELL); ctx.lineTo(canvas.width, i * CELL); ctx.stroke();
        }
    }

    function onCanvasClick(evt) {
        if (isWon) return;
        const rect = canvas.getBoundingClientRect();
        const scaleX = canvas.width / rect.width;
        const scaleY = canvas.height / rect.height;
        const px = (evt.clientX - rect.left) * scaleX;
        const py = (evt.clientY - rect.top) * scaleY;
        const c = Math.floor(px / CELL), r = Math.floor(py / CELL);
        if (r >= 0 && r < 9 && c >= 0 && c < 9) selectCell(r, c);
    }

    function onKeyDown(e) {
        if (e.code >= 'Digit1' && e.code <= 'Digit9') {
            inputNumber(parseInt(e.code.replace('Digit', ''), 10));
            return;
        }
        if (e.code === 'Backspace' || e.code === 'Delete') { eraseCell(); return; }
        if (!selected) return;
        let { r, c } = selected;
        if (e.code === 'ArrowUp') { r = Math.max(0, r - 1); e.preventDefault(); }
        else if (e.code === 'ArrowDown') { r = Math.min(8, r + 1); e.preventDefault(); }
        else if (e.code === 'ArrowLeft') { c = Math.max(0, c - 1); e.preventDefault(); }
        else if (e.code === 'ArrowRight') { c = Math.min(8, c + 1); e.preventDefault(); }
        else return;
        selectCell(r, c);
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
            canvas.addEventListener('click', onCanvasClick);
            window.addEventListener('keydown', onKeyDown);

            container.querySelectorAll('.num-btn').forEach(btn => {
                btn.onclick = () => inputNumber(parseInt(btn.dataset.num, 10));
            });
            container.querySelectorAll('.diff-pill').forEach(btn => {
                btn.onclick = () => newGame(btn.dataset.diff);
            });

            btnNew.onclick = () => newGame(difficulty);
            btnErase.onclick = eraseCell;
            btnNote.onclick = toggleNoteMode;
            btnHint.onclick = useHint;
            btnOverlay.onclick = () => newGame(difficulty);

            newGame('easy');
        

            setupPanelToggle('sudoku-left-col', 'sudoku-toggle-left', 'fa-solid fa-chevron-left', 'fa-solid fa-chevron-right');
            setupPanelToggle('sudoku-right-col', 'sudoku-toggle-right', 'fa-solid fa-chevron-right', 'fa-solid fa-chevron-left');
},
        destroy() {
            clearInterval(timerInterval);
            canvas.removeEventListener('click', onCanvasClick);
            window.removeEventListener('keydown', onKeyDown);
        }
    };
});
