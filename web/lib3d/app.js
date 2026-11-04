/* BookOasis 3D 서재 - 보관함은 부스, 작품(시리즈)은 책장에 표지가 보이게 꽂힌 책. 혼자 둘러보기.
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
  scene.background = new T.Color(0xd9cdb4);
  scene.fog = new T.Fog(0xd9cdb4, 30, 90);
  var camera = new T.PerspectiveCamera(62, 1, 0.1, 200);
  var EYE = 1.6;
  scene.add(new T.HemisphereLight(0xffffff, 0x8a7a5c, 0.8));
  var sun = new T.DirectionalLight(0xffffff, 0.55);
  sun.position.set(20, 40, 15);
  scene.add(sun);
  var floor = new T.Mesh(new T.PlaneGeometry(400, 400), new T.MeshLambertMaterial({ color: 0xc8a97e }));
  floor.rotation.x = -Math.PI / 2;
  scene.add(floor);
  var grid = new T.GridHelper(400, 200, 0xb59368, 0xb59368);
  grid.position.y = 0.002;
  grid.material.opacity = 0.25;
  grid.material.transparent = true;
  scene.add(grid);

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
  var BOOTH_W = 10, BOOTH_D = 8, GAP = 5, COLS = 4;
  var BOOK_W = 0.34, BOOK_H = 0.48, BOOK_T = 0.05, SLOT = 0.42, ROWS = 4, ROW_GAP = 0.62;
  var books = [];       // { mesh, key, title, count, lib, front(material), state }
  var booths = [];      // { name, x, z, count }
  var bookGeo = new T.BoxGeometry(BOOK_W, BOOK_H, BOOK_T);
  var wood = new T.MeshLambertMaterial({ color: 0x8b5a2b });
  var wallMat = new T.MeshLambertMaterial({ color: 0xf2ece0 });
  var tileMat = new T.MeshLambertMaterial({ color: 0xe9e4da });
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
    var cx = (col - (COLS - 1) / 2) * (BOOTH_W + GAP), cz = -12 - row * (BOOTH_D + GAP);
    var g = new T.Group();
    g.position.set(cx, 0, cz);
    scene.add(g);
    var tile = new T.Mesh(new T.BoxGeometry(BOOTH_W, 0.08, BOOTH_D), tileMat);
    tile.position.y = 0.04;
    g.add(tile);
    var wall = new T.Mesh(new T.BoxGeometry(BOOTH_W, 3.2, 0.2), wallMat);
    wall.position.set(0, 1.6, -BOOTH_D / 2);
    g.add(wall);
    var signTex = textCanvas([lib.name, lib.series.length + '작품 · ' + (lib.db_type || '')], 1024, 200, '#1f2328', '#ffffff', 72);
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

  // 입구 안내판
  function addEntrance(libs, total) {
    var tex = textCanvas(['BookOasis 3D 서재', '보관함 ' + libs.length + '개 · 작품 ' + total.toLocaleString() + '개'],
      1024, 360, '#2b2f36', '#ffffff', 96);
    var board = new T.Mesh(new T.PlaneGeometry(8, 2.8), new T.MeshBasicMaterial({ map: tex }));
    board.position.set(0, 3.2, -3);
    scene.add(board);
    var legL = new T.Mesh(new T.BoxGeometry(0.15, 3.2, 0.15), wood), legR = legL.clone();
    legL.position.set(-3.8, 1.6, -3.05); legR.position.set(3.8, 1.6, -3.05);
    scene.add(legL); scene.add(legR);
  }

  // ── 이동·시점 ──
  var yaw = 0, pitch = -0.05, keys = {}, moveStick = { x: 0, y: 0 };
  function home() { camera.position.set(0, EYE, 6); yaw = 0; pitch = -0.05; }
  function teleport(b) { camera.position.set(b.x, EYE, b.z + BOOTH_D / 2 + 3.5); yaw = 0; pitch = -0.08; closeMap(); }
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

  var BOUND = 200;
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
    camera.position.x = Math.max(-BOUND, Math.min(BOUND, camera.position.x));
    camera.position.z = Math.max(-BOUND, Math.min(BOUND, camera.position.z));
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
    var hit = ray.intersectObjects(books.map(function (b) { return b.mesh; }), false)[0];
    if (!hit || hit.distance > 14) { closeCard(); return; }
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
  document.getElementById('l3d-map-btn').addEventListener('click', function () {
    map.textContent = '';
    booths.forEach(function (b) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.innerHTML = '<span></span><small></small>';
      btn.firstChild.textContent = b.name;
      btn.lastChild.textContent = b.count + '작품';
      btn.addEventListener('click', function () { teleport(b); });
      map.appendChild(btn);
    });
    map.classList.toggle('on');
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
    t.textContent = best && bd < 9 ? best.name + ' · ' + best.count + '작품' : 'BookOasis 3D 서재 · 지도로 보관함 이동';
    whereEl.appendChild(t);
  }

  // ── 짓기 ──
  var built = [];
  function clear() {
    built.forEach(function (o) { scene.remove(o); });
    books = []; booths = []; built = [];
  }
  function build(refresh) {
    msg.style.display = '';
    msg.textContent = '서재를 짓는 중...';
    fetch('api/lib3d/data' + (refresh ? '?refresh=1' : ''), { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.success) throw new Error(d.error || '불러오기 실패');
        var before = scene.children.slice();
        clear();
        var libs = d.libraries || [];
        if (!libs.length) {
          msg.textContent = 'BookOasis 보관함을 읽지 못했습니다. .env의 BOOKOASIS_DB_URL을 확인하세요.' +
            ((d.errors || []).length ? ' (' + d.errors.join(' / ') + ')' : '');
          return;
        }
        var total = 0;
        libs.forEach(function (lib, i) { total += lib.series.length; addBooth(lib, i); });
        addEntrance(libs, total);
        built = scene.children.filter(function (o) { return before.indexOf(o) < 0; });
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
