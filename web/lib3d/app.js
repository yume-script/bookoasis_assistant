/* BookOasis 3D 서재 - 도서관 건물 안, 세션별로 층(1층 일반 · 2층 성인 · 3층 오디오북 · 4층 비디오 …),
 * 보관함은 서가 구역(부스), 작품(시리즈)은 책장에 표지가 보이게 꽂힌 책. 혼자 둘러보기, 층은 엘리베이터로.
 * 데이터: GET api/lib3d/data / 표지: api/lib3d/cover?k=세션:도서번호 (가까이 간 책만) / 열기: api/lib3d/open?k=…
 * 조작: W A S D·방향키 이동(Shift 빠르게), 마우스·손가락 끌기로 둘러보기, 책 누르기, 휴대폰은 왼쪽 아래 끌기로 이동 */
(function () {
  'use strict';
  var wrap = document.getElementById('l3d');
  var msg = document.getElementById('l3d-msg');
  if (!wrap) return;
  if (!window.THREE) { msg.textContent = '3D 라이브러리(three.js)를 불러오지 못했습니다. 인터넷 연결을 확인하세요.'; return; }
  var T = window.THREE;

  // ── 장면 ──
  var renderer = new T.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  wrap.insertBefore(renderer.domElement, wrap.firstChild);
  var scene = new T.Scene();
  scene.background = new T.Color(0x2a241e);
  scene.fog = new T.Fog(0x2a241e, 45, 110);
  var camera = new T.PerspectiveCamera(62, 1, 0.1, 200);
  var EYE = 1.6, CEIL = 6.2;
  scene.add(new T.HemisphereLight(0xfff6e5, 0x6b5a45, 0.85));
  var sun = new T.DirectionalLight(0xfff3dd, 0.35);
  sun.position.set(10, 30, 20);
  scene.add(sun);

  function resize() {
    var w = wrap.clientWidth, h = wrap.clientHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / Math.max(1, h);
    camera.updateProjectionMatrix();
  }
  window.addEventListener('resize', resize);

  // ── 글자 그림 (간판·표지 없는 책) ──
  function textCanvas(lines, w, h, bg, fg, size) {
    var c = document.createElement('canvas');
    c.width = w; c.height = h;
    var g = c.getContext('2d');
    g.fillStyle = bg; g.fillRect(0, 0, w, h);
    g.fillStyle = fg; g.textAlign = 'center'; g.textBaseline = 'middle';
    var fam = '"Noto Sans KR", "Apple SD Gothic Neo", "Malgun Gothic", sans-serif';
    var y = h / 2 - (lines.length - 1) * size * 0.6;
    lines.forEach(function (line, i) {
      var s = i === 0 ? size : size * 0.62;
      g.font = (i === 0 ? '700 ' : '500 ') + s + 'px ' + fam;
      g.fillText(line, w / 2, y + i * size * 1.2, w - 24);
    });
    var tex = new T.CanvasTexture(c);
    tex.anisotropy = 4;
    return tex;
  }
  function wrapTitle(title, per, max) {
    var out = [], s = String(title || '');
    while (s && out.length < max) { out.push(s.slice(0, per)); s = s.slice(per); }
    if (s && out.length) out[out.length - 1] = out[out.length - 1].slice(0, per - 1) + '…';
    return out;
  }
  function hue(str) {
    var hsh = 0;
    for (var i = 0; i < str.length; i++) hsh = (hsh * 31 + str.charCodeAt(i)) | 0;
    return new T.Color().setHSL(((hsh >>> 0) % 360) / 360, 0.45, 0.42);
  }

  // ── 부스 (보관함) ──
  var BOOTH_W = 10, BOOTH_D = 8, GAP = 5, COLS = 4, LOBBY = 14;
  var BOOK_W = 0.34, BOOK_H = 0.48, BOOK_T = 0.05, SLOT = 0.42, ROWS = 4, ROW_GAP = 0.62;
  var books = [];       // { mesh, key, title, count, lib, front(material), state }
  var booths = [];      // { name, x, z, count }
  var bookGeo = new T.BoxGeometry(BOOK_W, BOOK_H, BOOK_T);
  var wood = new T.MeshLambertMaterial({ color: 0x8b5a2b });
  var wallMat = new T.MeshLambertMaterial({ color: 0xf2ece0 });
  var tileMat = new T.MeshLambertMaterial({ color: 0x6e3b2e });          // 서가 구역 카펫
  var hallWall = new T.MeshLambertMaterial({ color: 0xeee4cf });
  var panelMat = new T.MeshLambertMaterial({ color: 0x5a3a22 });          // 벽 아래 나무 판
  var floorMat = new T.MeshLambertMaterial({ color: 0xb58a5a });
  var ceilMat = new T.MeshBasicMaterial({ color: 0xe9e1d0, side: T.DoubleSide });
  var lampMat = new T.MeshBasicMaterial({ color: 0xfffbea });
  var glassMat = new T.MeshBasicMaterial({ color: 0xbfe0f5 });
  var parent = scene;   // 지금 짓는 층 (층을 바꾸면 통째로 바꿈)
  var ropeMat = new T.MeshLambertMaterial({ color: 0xb3262b });

  function shelfUnit(group, x, z, rotY, width) {
    // 책장 하나: 뒤판 + 선반 ROWS줄. 반환: 칸 위치 [{x, y, z, rot}] (책장 앞쪽 = 로컬 +z)
    var unit = new T.Group();
    unit.position.set(x, 0, z);
    unit.rotation.y = rotY;
    group.add(unit);
    var back = new T.Mesh(new T.BoxGeometry(width, ROWS * ROW_GAP + 0.5, 0.06), wood);
    back.position.set(0, (ROWS * ROW_GAP + 0.5) / 2, -0.2);
    unit.add(back);
    var slots = [];
    var per = Math.floor((width - 0.2) / SLOT);
    for (var r = 0; r < ROWS; r++) {
      var y = 0.35 + r * ROW_GAP;
      var board = new T.Mesh(new T.BoxGeometry(width, 0.04, 0.42), wood);
      board.position.set(0, y - 0.02, 0);
      unit.add(board);
      for (var i = 0; i < per; i++) {
        slots.push({ unit: unit, x: -width / 2 + 0.1 + SLOT * (i + 0.5), y: y + BOOK_H / 2, z: -0.08 });
      }
    }
    // 위에서부터 채우도록 (눈높이 줄이 먼저)
    return slots.sort(function (a, b) { return Math.abs(a.y - 1.3) - Math.abs(b.y - 1.3); });
  }

  function addBook(slot, s, lib) {
    var side = new T.MeshLambertMaterial({ color: hue(s.title || '') });
    var front = new T.MeshLambertMaterial({ color: hue(s.title || '') });
    var mesh = new T.Mesh(bookGeo, [side, side, side, side, front, side]);
    mesh.position.set(slot.x, slot.y, slot.z);
    mesh.rotation.x = -0.12;   // 살짝 기대 세움
    slot.unit.add(mesh);
    var b = { mesh: mesh, key: lib.db_type + ':' + s.last, title: s.title || '(제목 없음)', count: s.count, lib: lib.name,
              front: front, state: 0 };
    mesh.userData.book = b;
    books.push(b);
  }

  function addBooth(lib, index) {
    var col = index % COLS, row = Math.floor(index / COLS);
    var cx = (col - (COLS - 1) / 2) * (BOOTH_W + GAP), cz = -LOBBY - BOOTH_D / 2 - row * (BOOTH_D + GAP);
    var g = new T.Group();
    g.position.set(cx, 0, cz);
    parent.add(g);
    var tile = new T.Mesh(new T.BoxGeometry(BOOTH_W, 0.08, BOOTH_D), tileMat);
    tile.position.y = 0.04;
    g.add(tile);
    var wall = new T.Mesh(new T.BoxGeometry(BOOTH_W, 3.2, 0.2), wallMat);
    wall.position.set(0, 1.6, -BOOTH_D / 2);
    g.add(wall);
    var signTex = textCanvas([lib.name, lib.series.length + '작품'], 1024, 200, '#1f2328', '#ffffff', 72);
    var sign = new T.Mesh(new T.PlaneGeometry(BOOTH_W * 0.8, 1.55), new T.MeshBasicMaterial({ map: signTex }));
    sign.position.set(0, 3.9, -BOOTH_D / 2 + 0.12);
    g.add(sign);
    // 줄 기둥 (앞쪽 입구는 비움)
    [[-1, 1], [1, 1]].forEach(function (p) {
      var post = new T.Mesh(new T.CylinderGeometry(0.05, 0.05, 1, 8), ropeMat);
      post.position.set(p[0] * BOOTH_W / 2, 0.5, p[1] * BOOTH_D / 2);
      g.add(post);
    });
    // 책장: 뒤 2개, 왼쪽·오른쪽 벽 1개씩
    var slots = []
      .concat(shelfUnit(g, -BOOTH_W / 4, -BOOTH_D / 2 + 0.35, 0, BOOTH_W / 2 - 0.3))
      .concat(shelfUnit(g, BOOTH_W / 4, -BOOTH_D / 2 + 0.35, 0, BOOTH_W / 2 - 0.3))
      .concat(shelfUnit(g, -BOOTH_W / 2 + 0.35, 0, Math.PI / 2, BOOTH_D - 1.2))
      .concat(shelfUnit(g, BOOTH_W / 2 - 0.35, 0, -Math.PI / 2, BOOTH_D - 1.2));
    lib.series.slice(0, slots.length).forEach(function (s, i) { addBook(slots[i], s, lib); });
    booths.push({ name: lib.name, x: cx, z: cz, count: lib.series.length });
  }

  // ── 도서관 건물: 한 층 ──
  var hall = { x0: -20, x1: 20, z0: -40, z1: 10 };   // 걸어 다닐 수 있는 범위
  var elevator = null;
  function box(w, h, d, mat, x, y, z) {
    var m = new T.Mesh(new T.BoxGeometry(w, h, d), mat);
    m.position.set(x, y, z);
    parent.add(m);
    return m;
  }
  function plane(w, h, mat, x, y, z, ry) {
    var m = new T.Mesh(new T.PlaneGeometry(w, h), mat);
    m.position.set(x, y, z);
    m.rotation.y = ry || 0;
    parent.add(m);
    return m;
  }
  function addBuilding(fl, cols, rows) {
    var w = cols * BOOTH_W + (cols - 1) * GAP + 12, back = -LOBBY - rows * (BOOTH_D + GAP) - 2, front = 10;
    var d = front - back, cz = (front + back) / 2;
    hall = { x0: -w / 2 + 0.6, x1: w / 2 - 0.6, z0: back + 0.6, z1: front - 0.6 };
    // 바닥 (나무) + 가운데 통로 카펫
    var fl0 = new T.Mesh(new T.PlaneGeometry(w, d), floorMat);
    fl0.rotation.x = -Math.PI / 2; fl0.position.set(0, 0, cz); parent.add(fl0);
    var runner = new T.Mesh(new T.PlaneGeometry(3, d - 2), new T.MeshLambertMaterial({ color: 0x7a2730 }));
    runner.rotation.x = -Math.PI / 2; runner.position.set(0, 0.01, cz); parent.add(runner);
    // 천장 + 조명 줄
    var ceil = new T.Mesh(new T.PlaneGeometry(w, d), ceilMat);
    ceil.rotation.x = Math.PI / 2; ceil.position.set(0, CEIL, cz); parent.add(ceil);
    for (var lz = front - 4; lz > back + 2; lz -= 7) {
      for (var lx = -w / 2 + 6; lx < w / 2 - 4; lx += 10) box(3, 0.08, 0.6, lampMat, lx, CEIL - 0.05, lz);
    }
    // 벽 4면 + 아래 나무 판 + 옆벽 창문
    [[0, front, w, 0], [0, back, w, 0], [-w / 2, cz, d, Math.PI / 2], [w / 2, cz, d, Math.PI / 2]].forEach(function (s) {
      var wall = new T.Mesh(new T.BoxGeometry(s[2], CEIL, 0.3), hallWall);
      wall.position.set(s[0], CEIL / 2, s[1]); wall.rotation.y = s[3]; parent.add(wall);
      var pan = new T.Mesh(new T.BoxGeometry(s[2], 1.1, 0.34), panelMat);
      pan.position.set(s[0], 0.55, s[1]); pan.rotation.y = s[3]; parent.add(pan);
    });
    for (var wz = front - 8; wz > back + 4; wz -= 9) {
      plane(4, 2.4, glassMat, -w / 2 + 0.17, 3.4, wz, Math.PI / 2);
      plane(4, 2.4, glassMat, w / 2 - 0.17, 3.4, wz, -Math.PI / 2);
    }
    // 입구 문 (뒤쪽 벽)
    box(4.4, 3.2, 0.1, panelMat, 0, 1.6, front - 0.2);
    box(0.06, 3.2, 0.12, wood, 0, 1.6, front - 0.26);
    // 안내 간판 (천장에 매달림, 통로 위)
    var title = textCanvas(['BookOasis 도서관', fl.label + ' · 보관함 ' + fl.libs.length + '개 · 작품 ' + fl.total.toLocaleString() + '개'],
      1400, 300, '#2b2f36', '#ffffff', 104);
    plane(9, 1.93, new T.MeshBasicMaterial({ map: title }), 0, 3.85, front - 7.5);
    box(0.05, CEIL - 4.8, 0.05, wood, -4, (CEIL + 4.8) / 2, front - 7.5); box(0.05, CEIL - 4.8, 0.05, wood, 4, (CEIL + 4.8) / 2, front - 7.5);
    // 안내 데스크 (오른쪽)
    box(4.2, 1.05, 1.1, wood, w / 2 - 5.5, 0.53, front - 6.5);
    box(4.4, 0.06, 1.3, panelMat, w / 2 - 5.5, 1.08, front - 6.5);
    var desk = textCanvas(['안내'], 256, 96, '#5a3a22', '#f5e6c8', 64);
    plane(1.2, 0.45, new T.MeshBasicMaterial({ map: desk }), w / 2 - 5.5, 0.6, front - 5.93);
    // 층 안내판 (왼쪽, 이 층의 서가 구역 목록)
    var lines = ['층 안내 · ' + fl.label].concat(fl.libs.slice(0, 16).map(function (l) { return l.name + '  ' + l.series.length; }));
    if (fl.libs.length > 16) lines.push('… 외 ' + (fl.libs.length - 16) + '개');
    var dir = document.createElement('canvas');
    dir.width = 512; dir.height = 720;
    var g2 = dir.getContext('2d');
    g2.fillStyle = '#1f2328'; g2.fillRect(0, 0, 512, 720);
    g2.fillStyle = '#ffffff'; g2.textBaseline = 'top';
    lines.forEach(function (ln, i) {
      g2.font = (i ? '500 30px ' : '700 40px ') + '"Noto Sans KR", sans-serif';
      g2.fillText(ln, 28, 24 + i * 40, 456);
    });
    var dtex = new T.CanvasTexture(dir);
    var stand = box(2.2, 3.1, 0.12, wood, -w / 2 + 5, 1.55, front - 6.5);
    stand.rotation.y = 0;
    plane(2.0, 2.8, new T.MeshBasicMaterial({ map: dtex }), -w / 2 + 5, 1.6, front - 6.43);
    // 엘리베이터 (왼쪽 벽, 누르면 층 고르기)
    var ev = new T.Group();
    ev.position.set(-w / 2 + 0.2, 0, front - 3);
    ev.rotation.y = Math.PI / 2;
    parent.add(ev);
    var door = new T.Mesh(new T.BoxGeometry(2.2, 2.6, 0.12), new T.MeshLambertMaterial({ color: 0xa7adb5 }));
    door.position.set(0, 1.3, 0.1); ev.add(door);
    var seam = new T.Mesh(new T.BoxGeometry(0.03, 2.6, 0.14), new T.MeshLambertMaterial({ color: 0x5b6068 }));
    seam.position.set(0, 1.3, 0.1); ev.add(seam);
    var elab = textCanvas(['엘리베이터 ' + fl.label], 512, 96, '#1f2328', '#ffd36b', 48);
    var lab = new T.Mesh(new T.PlaneGeometry(2.2, 0.42), new T.MeshBasicMaterial({ map: elab }));
    lab.position.set(0, 2.95, 0.17); ev.add(lab);
    door.userData.elevator = true;
    elevator = door;
  }

  // ── 이동·시점 ──
  var yaw = 0, pitch = -0.05, keys = {}, moveStick = { x: 0, y: 0 };
  function home() { camera.position.set(0, EYE, 9); yaw = 0; pitch = 0.12; }
  function teleport(b) {
    if (b.floor !== cur) { buildFloor(b.floor); }
    camera.position.set(b.x, EYE, b.z + BOOTH_D / 2 + 3.5); yaw = 0; pitch = -0.08; closeMap();
  }
  window.addEventListener('keydown', function (e) {
    if (e.target && /input|textarea|select/i.test(e.target.tagName)) return;
    keys[e.key.toLowerCase()] = true;
    if (['arrowup', 'arrowdown', 'arrowleft', 'arrowright', ' '].indexOf(e.key.toLowerCase()) >= 0) e.preventDefault();
  });
  window.addEventListener('keyup', function (e) { keys[e.key.toLowerCase()] = false; });
  window.addEventListener('blur', function () { keys = {}; });

  var drag = null;   // { id, x, y, moved, stick }
  var stickEl = document.getElementById('l3d-stick'), stickKnob = stickEl.firstChild;
  renderer.domElement.addEventListener('pointerdown', function (e) {
    var r = wrap.getBoundingClientRect();
    var isStick = e.pointerType === 'touch' && e.clientX - r.left < r.width * 0.4 && e.clientY - r.top > r.height * 0.45;
    drag = { id: e.pointerId, x: e.clientX, y: e.clientY, sx: e.clientX, sy: e.clientY, moved: false, stick: isStick };
    if (isStick) {
      stickEl.style.display = 'block';
      stickEl.style.left = (e.clientX - r.left - 48) + 'px';
      stickEl.style.top = (e.clientY - r.top - 48) + 'px';
    }
    renderer.domElement.setPointerCapture(e.pointerId);
  });
  renderer.domElement.addEventListener('pointermove', function (e) {
    if (!drag || e.pointerId !== drag.id) return;
    var dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (Math.abs(e.clientX - drag.sx) + Math.abs(e.clientY - drag.sy) > 6) drag.moved = true;
    if (drag.stick) {
      var ox = Math.max(-40, Math.min(40, e.clientX - drag.sx)), oy = Math.max(-40, Math.min(40, e.clientY - drag.sy));
      moveStick.x = ox / 40; moveStick.y = oy / 40;
      stickKnob.style.transform = 'translate(' + ox + 'px,' + oy + 'px)';
    } else {
      yaw -= dx * 0.005;
      pitch = Math.max(-1.2, Math.min(1.2, pitch - dy * 0.004));
    }
    drag.x = e.clientX; drag.y = e.clientY;
  });
  function endDrag(e) {
    if (!drag || e.pointerId !== drag.id) return;
    if (!drag.moved && !drag.stick) pick(e.clientX, e.clientY);
    if (drag.stick) { moveStick.x = moveStick.y = 0; stickEl.style.display = 'none'; stickKnob.style.transform = ''; }
    drag = null;
  }
  renderer.domElement.addEventListener('pointerup', endDrag);
  renderer.domElement.addEventListener('pointercancel', endDrag);

  function step(dt) {
    var f = 0, s = 0;
    if (keys.w || keys.arrowup) f += 1;
    if (keys.s || keys.arrowdown) f -= 1;
    if (keys.a) s -= 1;
    if (keys.d) s += 1;
    if (keys.arrowleft) yaw += dt * 1.8;
    if (keys.arrowright) yaw -= dt * 1.8;
    f -= moveStick.y; s += moveStick.x;
    var speed = (keys.shift ? 9 : 4.5) * dt;
    var sin = Math.sin(yaw), cos = Math.cos(yaw);
    camera.position.x += (-sin * f + cos * s) * speed;
    camera.position.z += (-cos * f - sin * s) * speed;
    camera.position.x = Math.max(hall.x0, Math.min(hall.x1, camera.position.x));   // 건물 안에서만
    camera.position.z = Math.max(hall.z0, Math.min(hall.z1, camera.position.z));
    camera.position.y = EYE;
    camera.rotation.set(pitch, yaw, 0, 'YXZ');
  }

  // ── 표지: 가까이(10m) 있는 책만, 6개씩 ──
  var loading = 0, MAX_LOAD = 6, NEAR = 10;
  var tmp = new T.Vector3(), loader = new T.TextureLoader();
  function titleTexture(b) {
    b.front.map = textCanvas(wrapTitle(b.title, 7, 4).concat([b.count + '권']), 256, 360, '#' + b.front.color.getHexString(),
      '#ffffff', 34);
    b.front.color.set(0xffffff);
    b.front.needsUpdate = true;
  }
  function loadCovers() {
    if (loading >= MAX_LOAD) return;
    var cand = [];
    for (var i = 0; i < books.length; i++) {
      var b = books[i];
      if (b.state) continue;
      b.mesh.getWorldPosition(tmp);
      var d = tmp.distanceTo(camera.position);
      if (d < NEAR) cand.push([d, b]);
    }
    cand.sort(function (a, c) { return a[0] - c[0]; });
    cand.slice(0, MAX_LOAD - loading).forEach(function (pair) {
      var b = pair[1];
      b.state = 1;
      loading++;
      loader.load('api/lib3d/cover?k=' + encodeURIComponent(b.key), function (tex) {
        loading--;
        tex.anisotropy = 4;
        b.front.map = tex; b.front.color.set(0xffffff); b.front.needsUpdate = true; b.state = 2; b.cover = true;
      }, undefined, function () { loading--; b.state = 3; titleTexture(b); });
    });
  }

  // ── 책 누르기 ──
  var ray = new T.Raycaster(), ndc = new T.Vector2();
  var card = document.getElementById('l3d-card'), openBtn = document.getElementById('l3d-open');
  var picked = null;
  function pick(cx, cy) {
    var r = renderer.domElement.getBoundingClientRect();
    ndc.set(((cx - r.left) / r.width) * 2 - 1, -((cy - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ndc, camera);
    var targets = books.map(function (b) { return b.mesh; });
    if (elevator) targets.push(elevator);
    var hit = ray.intersectObjects(targets, false)[0];
    if (hit && hit.object === elevator && hit.distance < 8) { openFloors(); return; }
    if (!hit || hit.distance > 14 || !hit.object.userData.book) { closeCard(); return; }
    showCard(hit.object.userData.book);
  }
  function showCard(b) {
    picked = b;
    document.getElementById('l3d-card-title').textContent = b.title;
    document.getElementById('l3d-card-sub').textContent = b.lib + ' · ' + b.count.toLocaleString() + '권';
    document.getElementById('l3d-card-path').textContent = '';
    var img = document.getElementById('l3d-card-img');
    img.hidden = !b.cover;
    if (b.cover) img.src = 'api/lib3d/cover?k=' + encodeURIComponent(b.key);
    openBtn.hidden = true;
    card.classList.add('on');
    fetch('api/lib3d/open?k=' + encodeURIComponent(b.key), { credentials: 'same-origin' }).then(function (r) { return r.json(); })
      .then(function (d) {
        if (picked !== b) return;
        document.getElementById('l3d-card-path').textContent = d.path || '';
        openBtn.hidden = !d.url;
        openBtn.onclick = function () { window.open(d.url, '_blank', 'noopener'); };
      }).catch(function () {});
  }
  function closeCard() { picked = null; card.classList.remove('on'); }
  document.getElementById('l3d-close').addEventListener('click', closeCard);

  // ── 지도 ──
  var map = document.getElementById('l3d-map');
  function closeMap() { map.classList.remove('on'); }
  function menuButton(text, sub, fn, strong) {
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.innerHTML = '<span></span><small></small>';
    btn.firstChild.textContent = text;
    btn.lastChild.textContent = sub;
    if (strong) btn.style.fontWeight = '700';
    btn.addEventListener('click', fn);
    map.appendChild(btn);
  }
  function openFloors() {   // 엘리베이터: 층 고르기
    map.textContent = '';
    floors.forEach(function (f, i) {
      menuButton((i === cur ? '▶ ' : '') + f.label, '보관함 ' + f.libs.length + ' · 작품 ' + f.total.toLocaleString(),
        function () { buildFloor(i); home(); closeMap(); }, i === cur);
    });
    map.classList.add('on');
  }
  document.getElementById('l3d-map-btn').addEventListener('click', function () {
    if (map.classList.contains('on')) { closeMap(); return; }
    map.textContent = '';
    floors.forEach(function (f, i) {
      var head = document.createElement('div');
      head.textContent = f.label;
      head.style.cssText = 'padding:8px 10px 2px;font-size:.75rem;opacity:.65;font-weight:700';
      map.appendChild(head);
      f.booths.forEach(function (b) { menuButton(b.name, b.count + '작품', function () { teleport(b); }); });
    });
    map.classList.add('on');
  });
  document.getElementById('l3d-floor-btn').addEventListener('click', function () {
    if (map.classList.contains('on')) closeMap(); else openFloors();
  });
  document.getElementById('l3d-home').addEventListener('click', function () { home(); closeMap(); });
  document.getElementById('l3d-reload').addEventListener('click', function () { build(true); });

  // 지금 어느 부스 앞인지
  var whereEl = document.getElementById('l3d-where');
  function where() {
    var best = null, bd = 1e9;
    booths.forEach(function (b) {
      var d = Math.hypot(camera.position.x - b.x, camera.position.z - b.z);
      if (d < bd) { bd = d; best = b; }
    });
    whereEl.innerHTML = '';
    var t = document.createElement('span');
    var fl = floors[cur] ? floors[cur].label + ' · ' : '';
    t.textContent = fl + (best && bd < 9 ? best.name + ' · ' + best.count + '작품' : '로비 · 엘리베이터나 [층]으로 다른 층');
    whereEl.appendChild(t);
  }

  // ── 짓기: 세션(db_type)마다 한 층 ──
  var FLOOR_NAMES = { general: '일반', adult: '성인', audiobook: '오디오북', video: '비디오' };
  var FLOOR_ORDER = ['general', 'adult', 'audiobook', 'video'];
  var floors = [], cur = -1, floorGroup = null;
  function makeFloors(libs) {
    var by = {};
    libs.forEach(function (l) { (by[l.db_type] = by[l.db_type] || []).push(l); });
    var keys = Object.keys(by).sort(function (a, b) {
      var ia = FLOOR_ORDER.indexOf(a), ib = FLOOR_ORDER.indexOf(b);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || a.localeCompare(b);
    });
    return keys.map(function (k, i) {
      var list = by[k], total = 0;
      list.forEach(function (l) { total += l.series.length; });
      return { key: k, label: (i + 1) + '층 ' + (FLOOR_NAMES[k] || k), libs: list, total: total, booths: [] };
    });
  }
  function buildFloor(i) {
    if (floorGroup) scene.remove(floorGroup);
    books = []; booths = [];
    cur = i;
    var fl = floors[i];
    floorGroup = new T.Group();
    scene.add(floorGroup);
    parent = floorGroup;
    COLS = Math.max(2, Math.min(4, fl.libs.length));
    addBuilding(fl, COLS, Math.ceil(fl.libs.length / COLS));
    fl.libs.forEach(function (lib, j) { addBooth(lib, j); });
    booths.forEach(function (b) { b.floor = i; });
    fl.booths = booths.slice();
    parent = scene;
    closeCard();
  }
  function build(refresh) {
    msg.style.display = '';
    msg.textContent = '서재를 짓는 중...';
    fetch('api/lib3d/data' + (refresh ? '?refresh=1' : ''), { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.success) throw new Error(d.error || '불러오기 실패');
        var libs = d.libraries || [];
        if (!libs.length) {
          msg.textContent = 'BookOasis 보관함을 읽지 못했습니다. .env의 BOOKOASIS_DB_URL을 확인하세요.' +
            ((d.errors || []).length ? ' (' + d.errors.join(' / ') + ')' : '');
          return;
        }
        floors = makeFloors(libs);
        // 다른 층의 지도 목록을 위해 층마다 부스 자리를 미리 계산해 둔다
        floors.forEach(function (f, i) {
          var cols = Math.max(2, Math.min(4, f.libs.length));
          f.booths = f.libs.map(function (l, j) {
            return { name: l.name, count: l.series.length, floor: i,
                     x: (j % cols - (cols - 1) / 2) * (BOOTH_W + GAP), z: -LOBBY - BOOTH_D / 2 - Math.floor(j / cols) * (BOOTH_D + GAP) };
          });
        });
        buildFloor(Math.max(0, Math.min(cur, floors.length - 1)));
        home();
        msg.style.display = 'none';
        where();
      })
      .catch(function (e) { msg.textContent = '불러오지 못했습니다: ' + e.message; });
  }

  // ── 그리기 ──
  var last = performance.now(), acc = 0;
  function frame(now) {
    var dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    step(dt);
    acc += dt;
    if (acc > 0.35) { acc = 0; loadCovers(); where(); }
    renderer.render(scene, camera);
    requestAnimationFrame(frame);
  }
  resize();
  home();
  build(false);
  requestAnimationFrame(frame);
  if ('ResizeObserver' in window) new ResizeObserver(resize).observe(wrap);
})();
