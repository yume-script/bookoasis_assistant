/* BookOasis 3D 서재 - 모던 서점 분위기의 건물 안을 혼자 걸어 다니며 둘러보고, 고른 책을 그 자리에서 읽는다.
 * 세션별로 층(1층 일반 · 2층 성인 · 3층 오디오북 · 4층 비디오 …), 보관함은 서가 구역, 작품(시리즈)은
 * 평대의 표지 · 눈높이 칸의 표지 진열 · 나머지 칸의 책등(제목)으로. 빈칸은 장식용 책으로 채운다.
 * 데이터: api/lib3d/data · 표지: api/lib3d/cover · 열기: api/lib3d/open · 읽기: api/lib3d/volumes|book|page|chapter|pdf
 * 조작: W A S D·방향키 이동(Shift 빠르게), 끌기로 둘러보기, 책 누르기, 휴대폰은 왼쪽 아래 끌기로 이동
 * 읽기: 펼친 책 모양, 책장 넘김(넓은 화면은 두 쪽 펼침, 만화는 오른쪽→왼쪽도). 매장에는 걷고 책을 고르는 사람들.
 * 설정(#settings): 보여 줄 보관함 고르기 - api/lib3d/libraries, POST api/lib3d/settings */
(function () {
  'use strict';
  var wrap = document.getElementById('l3d');
  var msg = document.getElementById('l3d-msg');
  if (!wrap) return;
  if (!window.THREE) { msg.textContent = '3D 라이브러리(three.js)를 불러오지 못했습니다. 인터넷 연결을 확인하세요.'; return; }
  var T = window.THREE;

  // ── 렌더러·장면 (실사 느낌: sRGB, 필름 톤, 부드러운 그림자) ──
  var renderer = new T.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputEncoding = T.sRGBEncoding;
  renderer.toneMapping = T.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = T.PCFSoftShadowMap;
  wrap.insertBefore(renderer.domElement, wrap.firstChild);
  var scene = new T.Scene();
  if (T.RoomEnvironment) {   // 실내 반사광(환경 조명): 나무·금속·유리에 은은한 반사가 생긴다
    try { scene.environment = new T.PMREMGenerator(renderer).fromScene(new T.RoomEnvironment(), 0.04).texture; } catch (e) { /* 없으면 예전대로 */ }
  }
  scene.background = new T.Color(0xf3efe8);
  scene.fog = new T.Fog(0xf3efe8, 40, 120);
  var camera = new T.PerspectiveCamera(60, 1, 0.05, 200);
  var EYE = 1.62, CEIL = 5.4;
  var hemi = new T.HemisphereLight(0xffffff, 0xcbb89c, scene.environment ? 0.3 : 0.6); scene.add(hemi);
  scene.add(new T.AmbientLight(0xffffff, 0.12));
  var sun = new T.DirectionalLight(0xfff4e2, 0.85);   // 창으로 들어오는 빛
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.bias = -0.0004;
  sun.shadow.radius = 3;
  scene.add(sun);
  scene.add(sun.target);

  function resize() {
    var w = wrap.clientWidth, h = wrap.clientHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / Math.max(1, h);
    camera.updateProjectionMatrix();
  }
  window.addEventListener('resize', resize);

  // ── 질감 (캔버스로 만든 나무결·바닥·창) ──
  var FONT = '"Noto Sans KR", "Apple SD Gothic Neo", "Malgun Gothic", sans-serif';
  function canvasTex(w, h, draw, repeat) {
    var c = document.createElement('canvas');
    c.width = w; c.height = h;
    draw(c.getContext('2d'), w, h);
    var t = new T.CanvasTexture(c);
    t.encoding = T.sRGBEncoding;
    t.anisotropy = 8;
    if (repeat) { t.wrapS = t.wrapT = T.RepeatWrapping; t.repeat.set(repeat[0], repeat[1]); }
    return t;
  }
  function rnd(seed) { var s = seed % 2147483647 || 1; return function () { s = s * 16807 % 2147483647; return (s - 1) / 2147483646; }; }
  function grain(g, w, h, base, dark, lines, r) {
    g.fillStyle = base; g.fillRect(0, 0, w, h);
    for (var i = 0; i < lines; i++) {
      var y = r() * h;
      g.strokeStyle = dark; g.globalAlpha = 0.05 + r() * 0.12; g.lineWidth = 0.6 + r() * 2.2;
      g.beginPath(); g.moveTo(0, y);
      for (var x = 0; x <= w; x += 32) g.lineTo(x, y + Math.sin(x / (40 + r() * 60) + i) * (2 + r() * 4));
      g.stroke();
    }
    g.globalAlpha = 1;
  }
  var oakTex = canvasTex(512, 512, function (g, w, h) { grain(g, w, h, '#c9a27a', '#7a5534', 90, rnd(7)); }, [1, 1]);
  var floorTex = canvasTex(1024, 1024, function (g, w, h) {   // 밝은 원목 마루 (판자 이음매가 엇갈림)
    var r = rnd(11), pw = 128;
    for (var col = 0; col < w / pw; col++) {
      var y = -r() * 300;
      while (y < h) {
        var len = 260 + r() * 300, tone = 200 + Math.floor(r() * 26);
        g.fillStyle = 'rgb(' + tone + ',' + (tone - 34) + ',' + (tone - 78) + ')';
        g.fillRect(col * pw, y, pw, len);
        for (var k = 0; k < 14; k++) {
          g.strokeStyle = 'rgba(110,70,40,' + (0.05 + r() * 0.08) + ')'; g.lineWidth = 1 + r() * 2;
          var gx = col * pw + 6 + r() * (pw - 12);
          g.beginPath(); g.moveTo(gx, y); g.bezierCurveTo(gx + 6, y + len / 3, gx - 6, y + len * 2 / 3, gx, y + len); g.stroke();
        }
        g.fillStyle = 'rgba(70,45,25,0.35)'; g.fillRect(col * pw, y + len - 2, pw, 2);
        y += len;
      }
      g.fillStyle = 'rgba(70,45,25,0.35)'; g.fillRect(col * pw + pw - 2, 0, 2, h);
    }
  }, [6, 6]);
  var skyTex = canvasTex(64, 256, function (g, w, h) {   // 창밖 (밝은 하늘)
    var grd = g.createLinearGradient(0, 0, 0, h);
    grd.addColorStop(0, '#dff0ff'); grd.addColorStop(0.7, '#f7fbff'); grd.addColorStop(1, '#e8efe2');
    g.fillStyle = grd; g.fillRect(0, 0, w, h);
  });

  var M = {
    oak: new T.MeshStandardMaterial({ map: oakTex, roughness: 0.62, metalness: 0 }),
    white: new T.MeshStandardMaterial({ color: 0xf7f5f1, roughness: 0.9 }),
    wall: new T.MeshStandardMaterial({ color: 0xf2efea, roughness: 0.95 }),
    black: new T.MeshStandardMaterial({ color: 0x1d1e20, roughness: 0.45, metalness: 0.55 }),
    steel: new T.MeshStandardMaterial({ color: 0xb9bec4, roughness: 0.35, metalness: 0.85 }),
    floor: new T.MeshStandardMaterial({ map: floorTex, roughness: 0.55 }),
    ceil: new T.MeshStandardMaterial({ color: 0xfbfaf8, roughness: 1, side: T.DoubleSide }),
    lamp: new T.MeshBasicMaterial({ color: 0xfffaf0 }),
    sky: new T.MeshBasicMaterial({ map: skyTex }),
    shelfBack: new T.MeshStandardMaterial({ color: 0xece7df, roughness: 0.9 }),
    green: new T.MeshStandardMaterial({ color: 0x4f7a4a, roughness: 0.8 }),
    pot: new T.MeshStandardMaterial({ color: 0xe9e4dc, roughness: 0.7 })
  };

  function textTex(lines, w, h, bg, fg, size, align) {
    return canvasTex(w, h, function (g) {
      g.fillStyle = bg; g.fillRect(0, 0, w, h);
      g.fillStyle = fg; g.textBaseline = 'middle'; g.textAlign = align || 'center';
      var y = h / 2 - (lines.length - 1) * size * 0.6;
      lines.forEach(function (line, i) {
        var s = i === 0 ? size : size * 0.55;
        g.font = (i === 0 ? '700 ' : '400 ') + s + 'px ' + FONT;
        g.fillText(line, align === 'left' ? 40 : w / 2, y + i * size * 1.15, w - 60);
      });
    });
  }
  // 차분한 책 색 (서점 책등처럼)
  var PALETTE = [0x2f4858, 0x8c3b3b, 0xd8cbb0, 0x3e5c47, 0x1f2a44, 0xb5793e, 0x6b4f73, 0xe9e2d0, 0x9a9a8a, 0x41363b,
                 0x7d8f69, 0xc2a35a, 0x5b6b7a, 0xa65f4b, 0x2c2c2c, 0xd9d4c7];
  function hashStr(s) { var h = 0; s = String(s || ''); for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0; return h >>> 0; }
  function colorOf(s) { return PALETTE[hashStr(s) % PALETTE.length]; }
  function inkOn(hex) { var c = new T.Color(hex); return (c.r * 0.3 + c.g * 0.59 + c.b * 0.11) > 0.6 ? '#2a2a2a' : '#f3efe6'; }

  // ── 구조 ──
  var BOOTH_W = 10, BOOTH_D = 8, GAP = 5, COLS = 4, LOBBY = 14;
  var parent = scene, books = [], booths = [];
  function add(mesh, x, y, z, cast) {
    mesh.position.set(x, y, z);
    if (cast) { mesh.castShadow = true; mesh.receiveShadow = true; }
    parent.add(mesh);
    return mesh;
  }
  function box(w, h, d, mat, x, y, z, cast) { return add(new T.Mesh(new T.BoxGeometry(w, h, d), mat), x, y, z, cast); }

  // 책장 하나 (원목 틀 + 흰 뒤판 + 검은 받침), 로컬 +z가 앞. 반환 { unit, width, rows: [{y}] }
  var SHELF_H = 2.3, ROW_Y = [0.14, 0.58, 1.02, 1.46, 1.9], DEPTH = 0.36;
  function shelfUnit(g, x, z, rotY, width) {
    var unit = new T.Group();
    unit.position.set(x, 0, z); unit.rotation.y = rotY;
    g.add(unit);
    function part(w, h, d, mat, px, py, pz) {
      var m = new T.Mesh(new T.BoxGeometry(w, h, d), mat);
      m.position.set(px, py, pz); m.castShadow = true; m.receiveShadow = true; unit.add(m); return m;
    }
    part(width, SHELF_H, 0.02, M.shelfBack, 0, SHELF_H / 2, -DEPTH / 2 + 0.01);
    part(0.04, SHELF_H, DEPTH, M.oak, -width / 2, SHELF_H / 2, 0);
    part(0.04, SHELF_H, DEPTH, M.oak, width / 2, SHELF_H / 2, 0);
    part(width + 0.04, 0.04, DEPTH, M.oak, 0, SHELF_H, 0);
    part(width, 0.1, DEPTH - 0.02, M.black, 0, 0.05, 0);
    ROW_Y.forEach(function (y, i) { if (i) part(width, 0.025, DEPTH, M.oak, 0, y - 0.0125, 0); });
    return { unit: unit, width: width, rows: ROW_Y.map(function (y) { return { y: y }; }) };
  }

  // 책 (작품 하나) - 표지 진열(face), 평대(flat), 책등(spine)
  var faceGeo = new T.BoxGeometry(0.3, 0.42, 0.035);
  function makeBook(kind, s, lib) {
    var base = colorOf(s.title);
    var side = new T.MeshStandardMaterial({ color: 0xf0ebe0, roughness: 0.9 });   // 종이 단면
    var front = new T.MeshStandardMaterial({ color: base, roughness: 0.6 });
    var mesh, b = { key: lib.db_type + ':' + s.last, title: s.title || '(제목 없음)', count: s.count, lib: lib.name,
                    db: lib.db_type, front: front, base: base, state: 0, kind: kind };
    if (kind === 'spine') {
      var th = 0.035 + (hashStr(s.title) % 5) * 0.008, ht = 0.3 + (hashStr(s.title + 'h') % 6) * 0.015;
      mesh = new T.Mesh(new T.BoxGeometry(th, ht, 0.24), [side, side, side, side, front, side]);   // 앞면(+z) = 책등
      b.th = th; b.ht = ht;
    } else {
      mesh = new T.Mesh(faceGeo, [side, side, side, side, front, side]);
    }
    mesh.castShadow = true;
    mesh.userData.book = b;
    b.mesh = mesh;
    books.push(b);
    return b;
  }

  // 장식용 책 (누를 수 없음, 한 구역에 InstancedMesh 하나)
  function fillerBooks(g, items) {
    if (!items.length) return;
    var im = new T.InstancedMesh(new T.BoxGeometry(1, 1, 1), new T.MeshStandardMaterial({ roughness: 0.75 }), items.length);
    var m4 = new T.Matrix4(), q = new T.Quaternion(), c = new T.Color();
    items.forEach(function (it, i) {
      q.setFromEuler(new T.Euler(0, it.ry, 0));
      m4.compose(new T.Vector3(it.x, it.y, it.z), q, new T.Vector3(it.w, it.h, it.d));
      im.setMatrixAt(i, m4);
      im.setColorAt(i, c.setHex(it.c));
    });
    im.castShadow = true; im.receiveShadow = true;
    g.add(im);
  }

  // 책장 칸 채우기: 눈높이 칸(3번째 줄)은 표지 진열, 나머지는 책등. 작품이 모자라면 장식 책
  function stockShelf(su, queue, lib, filler, group) {
    var w = su.width - 0.08, unit = su.unit;
    unit.updateMatrixWorld(true);
    var toGroup = new T.Matrix4().copy(group.matrixWorld).invert().multiply(unit.matrixWorld);
    var p = new T.Vector3(), r = rnd(hashStr(lib.name) + Math.round(su.width * 100 + unit.position.x * 10 + unit.position.z * 7));
    su.rows.forEach(function (row, ri) {
      if (ri === 2) {   // 표지 진열
        var n = Math.floor(w / 0.38);
        for (var i = 0; i < n; i++) {
          var x = -w / 2 + 0.38 * (i + 0.5);
          var s = queue.shift();
          if (s) {
            var b = makeBook('face', s, lib);
            b.mesh.position.set(x, row.y + 0.21, -0.06); b.mesh.rotation.x = -0.1;
            unit.add(b.mesh);
          } else {
            p.set(x, row.y + 0.2, -0.06).applyMatrix4(toGroup);
            filler.push({ x: p.x, y: p.y, z: p.z, w: 0.29, h: 0.4, d: 0.03, ry: unit.rotation.y, c: PALETTE[Math.floor(r() * PALETTE.length)] });
          }
        }
        return;
      }
      var cx = -w / 2;
      while (cx < w / 2 - 0.05) {
        var s2 = r() < 0.75 ? queue.shift() : null;   // 작품 사이사이에 장식 책을 섞어 실제 서가처럼
        if (s2) {
          var b2 = makeBook('spine', s2, lib);
          if (cx + b2.th > w / 2) { queue.unshift(s2); books.pop(); break; }
          b2.mesh.position.set(cx + b2.th / 2, row.y + b2.ht / 2, -0.02);
          unit.add(b2.mesh);
          cx += b2.th + 0.004;
        } else {
          var th = 0.025 + r() * 0.045, ht = 0.26 + r() * 0.11;
          if (cx + th > w / 2) break;
          p.set(cx + th / 2, row.y + ht / 2, -0.02).applyMatrix4(toGroup);
          filler.push({ x: p.x, y: p.y, z: p.z, w: th, h: ht, d: 0.2 + r() * 0.05, ry: unit.rotation.y,
                        c: PALETTE[Math.floor(r() * PALETTE.length)] });
          cx += th + 0.004;
        }
        if (r() < 0.04) cx += 0.12;   // 가끔 빈틈
      }
    });
  }

  function addSection(lib, index) {
    var col = index % COLS, row = Math.floor(index / COLS);
    var cx = (col - (COLS - 1) / 2) * (BOOTH_W + GAP), cz = -LOBBY - BOOTH_D / 2 - row * (BOOTH_D + GAP);
    var g = new T.Group();
    g.position.set(cx, 0, cz);
    parent.add(g);
    g.updateMatrixWorld(true);
    var queue = lib.series.slice();
    // 평대 (작품 표지를 눕혀서)
    var tbl = new T.Group(); tbl.position.set(0, 0, 1.6); g.add(tbl);
    var top = new T.Mesh(new T.BoxGeometry(2.8, 0.05, 1.3), M.oak); top.position.y = 0.82; top.castShadow = top.receiveShadow = true; tbl.add(top);
    var body = new T.Mesh(new T.BoxGeometry(2.6, 0.78, 1.1), M.white); body.position.y = 0.4; body.castShadow = body.receiveShadow = true; tbl.add(body);
    for (var t = 0; t < 10 && queue.length; t++) {   // 평대: 들어올 때마다 이 보관함 작품 중 무작위 10개 (책장에서는 뺀다)
      var b = makeBook('flat', queue.splice(Math.floor(Math.random() * queue.length), 1)[0], lib);
      b.mesh.rotation.x = -Math.PI / 2;
      b.mesh.rotation.z = ((hashStr(b.title) % 7) - 3) * 0.02;
      b.mesh.position.set(-1.12 + (t % 5) * 0.56, 0.86, -0.27 + Math.floor(t / 5) * 0.55);
      tbl.add(b.mesh);
    }
    // 책장: 뒤 2개, 양옆 1개씩
    var units = [shelfUnit(g, -BOOTH_W / 4 + 0.05, -BOOTH_D / 2 + 0.3, 0, BOOTH_W / 2 - 0.3),
                 shelfUnit(g, BOOTH_W / 4 - 0.05, -BOOTH_D / 2 + 0.3, 0, BOOTH_W / 2 - 0.3),
                 shelfUnit(g, -BOOTH_W / 2 + 0.3, -0.3, Math.PI / 2, BOOTH_D - 1.6),
                 shelfUnit(g, BOOTH_W / 2 - 0.3, -0.3, -Math.PI / 2, BOOTH_D - 1.6)];
    var filler = [];
    units.forEach(function (u) { stockShelf(u, queue, lib, filler, g); });
    fillerBooks(g, filler);
    // 천장에 매단 구역 간판 (검정 판, 흰 글씨)
    var sign = new T.Mesh(new T.BoxGeometry(4.2, 0.62, 0.04), [M.black, M.black, M.black, M.black,
      new T.MeshBasicMaterial({ map: textTex([lib.name, lib.series.length + '작품'], 1024, 152, '#1d1e20', '#f5f2ec', 64) }), M.black]);
    sign.position.set(0, 3.75, -0.6); g.add(sign);
    [-1.9, 1.9].forEach(function (sx) {
      var cable = new T.Mesh(new T.CylinderGeometry(0.006, 0.006, CEIL - 4.06, 6), M.black);
      cable.position.set(sx, (CEIL + 4.06) / 2, -0.6); g.add(cable);
    });
    // 평대 위 펜던트 조명
    var shade = new T.Mesh(new T.CylinderGeometry(0.16, 0.34, 0.26, 24, 1, true), M.black);
    shade.position.set(0, 2.45, 1.6); g.add(shade);
    var bulb = new T.Mesh(new T.CircleGeometry(0.33, 24), M.lamp); bulb.rotation.x = Math.PI / 2; bulb.position.set(0, 2.33, 1.6); g.add(bulb);
    var cord = new T.Mesh(new T.CylinderGeometry(0.006, 0.006, CEIL - 2.58, 6), M.black); cord.position.set(0, (CEIL + 2.58) / 2, 1.6); g.add(cord);
    booths.push({ name: lib.name, x: cx, z: cz, count: lib.series.length });
    if (layout) layout.sections.push({ x: cx, z: cz });
  }

  // ── 건물 (한 층) ──
  var hall = { x0: -20, x1: 20, z0: -40, z1: 10 };
  var elevator = null;
  // ── 창밖 경치: 먼 하늘·산·도시(둘러싼 원통 그림) + 길·보도·가로수·건너편 건물(실제 입체, 걸으면 시차가 생긴다) ──
  var SCENE_R = 130;   // 먼 경치 원통 반지름
  var grassTex = canvasTex(256, 256, function (g, w, h) {
    var r = rnd(31); g.fillStyle = '#8aa36f'; g.fillRect(0, 0, w, h);
    for (var i = 0; i < 2200; i++) { g.fillStyle = 'rgba(' + (60 + Math.floor(r() * 60)) + ',' + (100 + Math.floor(r() * 60)) + ',50,' + (0.15 + r() * 0.25) + ')'; g.fillRect(r() * w, r() * h, 2, 2 + r() * 3); }
  }, [60, 60]);
  var paveTex = canvasTex(256, 256, function (g, w, h) {   // 보도블록
    var r = rnd(37); g.fillStyle = '#c9c2b6'; g.fillRect(0, 0, w, h);
    for (var y = 0; y < h; y += 32) for (var x = (y / 32) % 2 ? -32 : 0; x < w; x += 64) {
      var t = 190 + Math.floor(r() * 25); g.fillStyle = 'rgb(' + t + ',' + (t - 6) + ',' + (t - 16) + ')'; g.fillRect(x + 1, y + 1, 62, 30);
    }
  }, [2, 40]);
  var roadTex = canvasTex(256, 512, function (g, w, h) {   // 아스팔트 + 가운데 점선
    var r = rnd(41); g.fillStyle = '#5d6064'; g.fillRect(0, 0, w, h);
    for (var i = 0; i < 3000; i++) { g.fillStyle = 'rgba(255,255,255,' + r() * 0.06 + ')'; g.fillRect(r() * w, r() * h, 1.5, 1.5); }
    g.fillStyle = '#e9d27a'; for (var y = 0; y < h; y += 128) g.fillRect(w / 2 - 4, y, 8, 64);
    g.fillStyle = '#f2f2ee'; g.fillRect(8, 0, 6, h); g.fillRect(w - 14, 0, 6, h);
  }, [1, 20]);
  var facadeTex = canvasTex(256, 512, function (g, w, h) {   // 건너편 건물 외벽 (창 격자)
    var r = rnd(43); g.fillStyle = '#ffffff'; g.fillRect(0, 0, w, h);
    for (var y = 12; y < h - 8; y += 32) for (var x = 10; x < w - 10; x += 30) {
      var lit = r();
      g.fillStyle = lit < 0.12 ? '#f6e7b8' : lit < 0.55 ? '#7c8c9c' : '#93a5b6'; g.fillRect(x, y, 20, 20);
      g.fillStyle = 'rgba(255,255,255,0.25)'; g.fillRect(x, y, 20, 3);
    }
  }, [1, 1]);
  facadeTex.wrapS = facadeTex.wrapT = T.RepeatWrapping;
  Object.assign(M, {
    pano: new T.MeshBasicMaterial({ side: T.BackSide, fog: false }),   // 그림은 applyOutside()가 상태별로
    lightPool: new T.MeshBasicMaterial({ map: canvasTex(64, 64, function (g) { var gr = g.createRadialGradient(32, 32, 2, 32, 32, 31); gr.addColorStop(0, 'rgba(255,214,150,0.55)'); gr.addColorStop(1, 'rgba(255,214,150,0)'); g.fillStyle = gr; g.fillRect(0, 0, 64, 64); }), transparent: true, depthWrite: false, opacity: 0 }),
    streetLight: new T.MeshStandardMaterial({ color: 0xfff6e0, emissive: 0x000000, emissiveIntensity: 1.6, roughness: 0.4 }),
    pole: new T.MeshStandardMaterial({ color: 0x3a3d42, roughness: 0.5, metalness: 0.6 }),
    grass: new T.MeshStandardMaterial({ map: grassTex, roughness: 1 }),
    pave: new T.MeshStandardMaterial({ map: paveTex, roughness: 0.95 }),
    road: new T.MeshStandardMaterial({ map: roadTex, roughness: 0.9 }),
    trunk: new T.MeshStandardMaterial({ color: 0x6b4f3a, roughness: 0.9 }),
    leaf: [0x5d8a4e, 0x6f9a55, 0x4f7a44, 0x83a862].map(function (c) { return new T.MeshStandardMaterial({ color: c, roughness: 0.9, flatShading: true }); }),
    facade: [0xd9d2c4, 0xb8c2cc, 0xe7e1d6, 0xa9b3ab, 0xcfc4b8].map(function (c) { return new T.MeshStandardMaterial({ map: facadeTex, color: c, roughness: 0.85 }); }),
    shopGlass: new T.MeshStandardMaterial({ color: 0x2a3540, roughness: 0.1, metalness: 0.5, emissive: 0x000000, emissiveIntensity: 0.9 }),
    parapet: new T.MeshStandardMaterial({ color: 0x8d9094, roughness: 0.8 }),
    awning: [0x7a2f2f, 0x2f4f6a, 0x3f5f3a, 0xc9a24a].map(function (c) { return new T.MeshStandardMaterial({ color: c, roughness: 0.8 }); }),
    glassPane: new T.MeshStandardMaterial({ color: 0xdfeaf2, roughness: 0.05, metalness: 0.1, transparent: true, opacity: 0.12, depthWrite: false })
  });
  var poolGeo = new T.PlaneGeometry(7, 7); poolGeo.userData.shared = true;
  var trunkGeo = new T.CylinderGeometry(0.12, 0.18, 2.6, 8), crownGeo = new T.IcosahedronGeometry(1.6, 1), unitBox = new T.BoxGeometry(1, 1, 1);
  [trunkGeo, crownGeo, unitBox].forEach(function (gq) { gq.userData.shared = true; });
  // ── 창밖 풍경 상태: 시간(낮·노을·밤) × 계절(봄·여름·가을·겨울) × 날씨(맑음·흐림·비·눈), 각각 자동 가능 ──
  var OUTSIDE = { time: 'auto', season: 'auto', weather: 'clear' };   // 설정값 (lib3d.json outside)
  var OUT = null;                                                       // 지금 적용된 실제 값
  function resolveOutside() {
    var now = new Date(), hr = now.getHours() + now.getMinutes() / 60, mo = now.getMonth() + 1;
    var time = OUTSIDE.time !== 'auto' ? OUTSIDE.time : (hr >= 6.5 && hr < 17 ? 'day' : hr >= 17 && hr < 19 ? 'dusk' : 'night');
    var season = OUTSIDE.season !== 'auto' ? OUTSIDE.season : (mo >= 3 && mo <= 5 ? 'spring' : mo >= 6 && mo <= 8 ? 'summer' : mo >= 9 && mo <= 11 ? 'autumn' : 'winter');
    var weather = OUTSIDE.weather;
    if (weather === 'auto') {   // 날마다 바뀌는 날씨 (겨울은 눈, 여름은 비가 잦게)
      var d = Math.floor(now.getTime() / 86400000), x = ((d * 9301 + 49297) % 233280) / 233280;
      weather = x < 0.55 ? 'clear' : x < 0.75 ? 'cloudy' : season === 'winter' ? 'snow' : 'rain';
    }
    return { time: time, season: season, weather: weather };
  }
  var SEASON_LEAF = {
    spring: [0xf2b8c6, 0xf6c9d4, 0xe9a3b8, 0xffdbe4], summer: [0x5d8a4e, 0x6f9a55, 0x4f7a44, 0x83a862],
    autumn: [0xd9822b, 0xc8562a, 0xe0a43a, 0xb84a2a], winter: [0xe9edf1, 0xdfe5ea, 0xf3f5f7, 0xd5dce2]
  };
  var panoCache = {};
  function makePano(o) {   // 먼 경치 그림 (상태별로 한 번만 그려 둔다)
    var key = o.time + o.season + o.weather;
    if (panoCache[key]) return panoCache[key];
    var night = o.time === 'night', dusk = o.time === 'dusk', grey = o.weather !== 'clear', winter = o.season === 'winter';
    var t = canvasTex(4096, 1024, function (g, w, h) {
      var r = rnd(23), hz = h * 0.7;
      var sky = g.createLinearGradient(0, 0, 0, hz);
      if (night) { sky.addColorStop(0, grey ? '#121722' : '#0b1430'); sky.addColorStop(0.6, grey ? '#1d2330' : '#1a2a52'); sky.addColorStop(1, grey ? '#2a303c' : '#34466e'); }
      else if (dusk) { sky.addColorStop(0, grey ? '#5c5a66' : '#3d4f86'); sky.addColorStop(0.5, grey ? '#8a7d7c' : '#d9877a'); sky.addColorStop(1, grey ? '#b19a88' : '#f4c27c'); }
      else if (grey) { sky.addColorStop(0, o.weather === 'cloudy' ? '#9aa5b0' : '#7f8994'); sky.addColorStop(1, '#c9cfd4'); }
      else { sky.addColorStop(0, '#7fb2e3'); sky.addColorStop(0.55, '#b9d7f0'); sky.addColorStop(1, '#eef4f6'); }
      g.fillStyle = sky; g.fillRect(0, 0, w, hz);
      if (night && !grey) {   // 별·달
        for (var s = 0; s < 700; s++) { g.fillStyle = 'rgba(255,255,255,' + (0.3 + r() * 0.7) + ')'; var sz = r() < 0.08 ? 2.4 : 1.3; g.fillRect(r() * w, r() * hz * 0.85, sz, sz); }
        var mx = w * 0.62, my = hz * 0.28, mg = g.createRadialGradient(mx, my, 10, mx, my, 160);
        mg.addColorStop(0, 'rgba(220,230,255,0.45)'); mg.addColorStop(1, 'rgba(220,230,255,0)');
        g.fillStyle = mg; g.fillRect(mx - 160, my - 160, 320, 320);
        g.fillStyle = '#f4f1e2'; g.beginPath(); g.arc(mx, my, 26, 0, Math.PI * 2); g.fill();
      } else if (!night && !grey) {   // 해 (노을이면 지평선 가까이 크게)
        var sx = w * 0.32, sy = dusk ? hz * 0.82 : hz * 0.35, rad = dusk ? 420 : 260, glow = g.createRadialGradient(sx, sy, 4, sx, sy, rad);
        glow.addColorStop(0, dusk ? 'rgba(255,214,150,1)' : 'rgba(255,250,232,0.95)'); glow.addColorStop(1, 'rgba(255,214,150,0)');
        g.fillStyle = glow; g.fillRect(sx - rad, sy - rad, rad * 2, rad * 2);
      }
      var clouds = grey ? 160 : 46;
      for (var c = 0; c < clouds; c++) {   // 구름
        var cx = r() * w, cy = hz * (0.05 + r() * (grey ? 0.75 : 0.55)), cw = 90 + r() * (grey ? 420 : 260);
        for (var k = 0; k < 7; k++) {
          var a = (grey ? 0.25 : 0.18) + r() * 0.3;
          g.fillStyle = night ? 'rgba(70,78,98,' + a + ')' : dusk ? 'rgba(255,200,180,' + a + ')' : grey ? 'rgba(' + (o.weather === 'cloudy' ? 222 : 170) + ',' + (o.weather === 'cloudy' ? 226 : 176) + ',' + (o.weather === 'cloudy' ? 232 : 186) + ',' + a + ')' : 'rgba(255,255,255,' + a + ')';
          g.beginPath(); g.ellipse(cx + (r() - 0.5) * cw, cy + (r() - 0.5) * 18, cw * (0.25 + r() * 0.3), 12 + r() * 16, 0, 0, Math.PI * 2); g.fill();
        }
      }
      function ridge(base, amp, col, step, cap) {
        var pts = [], y = base;
        for (var x = 0; x <= w; x += step) { y += (r() - 0.5) * amp; y = Math.max(base - amp * 3, Math.min(base + amp, y)); pts.push([x, y]); }
        g.fillStyle = col; g.beginPath(); g.moveTo(0, hz); pts.forEach(function (p) { g.lineTo(p[0], p[1]); }); g.lineTo(w, hz); g.closePath(); g.fill();
        if (cap) {   // 눈 덮인 산마루
          g.strokeStyle = cap; g.lineWidth = 10; g.beginPath(); pts.forEach(function (p, i) { if (i) g.lineTo(p[0], p[1] + 4); else g.moveTo(p[0], p[1] + 4); }); g.stroke();
        }
      }
      var dim = night ? 0.35 : dusk ? 0.75 : grey ? 0.85 : 1;
      function shade(hex, f) { var cc = new T.Color(hex); cc.multiplyScalar(f || dim); return '#' + cc.getHexString(); }
      ridge(hz - 120, 26, shade('#a9bccb'), 40, winter ? shade('#f2f5f8') : null);
      ridge(hz - 70, 22, shade('#8fa7b6'), 30, winter ? shade('#e8eef3') : null);
      for (var b = 0; b < 260; b++) {   // 먼 도시
        var bx = r() * w, bw = 14 + r() * 46, bh = 18 + Math.pow(r(), 2.2) * 150;
        g.fillStyle = shade('#' + new T.Color((120 + Math.floor(r() * 30)) / 255, (138 + Math.floor(r() * 25)) / 255, (155 + Math.floor(r() * 25)) / 255).getHexString());
        g.fillRect(bx, hz - bh, bw, bh);
        for (var wy = hz - bh + 5; wy < hz - 6; wy += 9) for (var wx = bx + 3; wx < bx + bw - 4; wx += 7) {
          var on = r();
          if (night || dusk) { if (on < (night ? 0.45 : 0.2)) { g.fillStyle = r() < 0.8 ? '#ffd98a' : '#cfe3ff'; g.fillRect(wx, wy, 3, 4); } }
          else if (on < 0.5) { g.fillStyle = 'rgba(235,242,248,0.35)'; g.fillRect(wx, wy, 3, 4); }
        }
      }
      var leaf = SEASON_LEAF[o.season];
      for (var tt = 0; tt < 900; tt++) {   // 가까운 나무 줄
        var tx = r() * w, tr = 10 + r() * 22;
        g.fillStyle = shade('#' + new T.Color(leaf[Math.floor(r() * 4)]).getHexString(), dim * 0.9);
        g.beginPath(); g.arc(tx, hz - tr * 0.4, tr, 0, Math.PI * 2); g.fill();
      }
      var ground = g.createLinearGradient(0, hz, 0, h);
      var gc = winter ? '#e9eef2' : o.season === 'autumn' ? '#9c9364' : '#7f9a6c';
      ground.addColorStop(0, shade(gc)); ground.addColorStop(1, shade(gc, dim * 0.88));
      g.fillStyle = ground; g.fillRect(0, hz, w, h - hz);
    });
    t.wrapS = T.RepeatWrapping;
    panoCache[key] = t;
    return t;
  }
  var facadeNightTex = canvasTex(256, 512, function (g, w, h) {   // 밤에 켜진 건물 창 (발광 그림)
    var r = rnd(43); g.fillStyle = '#000000'; g.fillRect(0, 0, w, h);
    for (var y = 12; y < h - 8; y += 32) for (var x = 10; x < w - 10; x += 30) {
      var lit = r(); r();
      if (lit < 0.42) { g.fillStyle = lit < 0.34 ? '#ffd58a' : '#bfd8ff'; g.fillRect(x, y, 20, 20); }
    }
  }, [1, 1]);
  facadeNightTex.wrapS = facadeNightTex.wrapT = T.RepeatWrapping;
  // 비·눈 입자 (건물 바깥 양옆에만, 층마다 새로 만든다)
  var weatherFx = null;
  function addWeather(w, back, front, gy) {
    var N = 4000, pos = new Float32Array(N * 6), sp = new Float32Array(N), r = rnd(71);
    var box = { x0: w / 2 + 0.4, x1: w / 2 + 26, z0: back - 30, z1: front + 30, y0: gy, y1: CEIL + 14 };
    for (var i = 0; i < N; i++) {
      var side = i % 2 ? 1 : -1, x = side * (box.x0 + r() * (box.x1 - box.x0)), y = box.y0 + r() * (box.y1 - box.y0), z = box.z0 + r() * (box.z1 - box.z0);
      pos[i * 6] = pos[i * 6 + 3] = x; pos[i * 6 + 1] = y; pos[i * 6 + 4] = y - 0.35; pos[i * 6 + 2] = pos[i * 6 + 5] = z; sp[i] = 0.7 + r() * 0.6;
    }
    var rainGeo = new T.BufferGeometry(); rainGeo.setAttribute('position', new T.BufferAttribute(pos, 3));
    var rain = new T.LineSegments(rainGeo, new T.LineBasicMaterial({ color: 0xdfe8f2, transparent: true, opacity: 0.75 }));
    var sp2 = new Float32Array(N * 3); for (i = 0; i < N; i++) { sp2[i * 3] = pos[i * 6]; sp2[i * 3 + 1] = pos[i * 6 + 1]; sp2[i * 3 + 2] = pos[i * 6 + 2]; }
    var snowGeo = new T.BufferGeometry(); snowGeo.setAttribute('position', new T.BufferAttribute(sp2, 3));
    var snow = new T.Points(snowGeo, new T.PointsMaterial({ color: 0xffffff, size: 0.22, map: flakeTex, transparent: true, alphaTest: 0.2, depthWrite: false }));
    [rain, snow].forEach(function (m) { m.frustumCulled = false; m.visible = false; parent.add(m); });
    weatherFx = { rain: rain, snow: snow, sp: sp, box: box, N: N };
  }
  var flakeTex = canvasTex(32, 32, function (g, w, h) {
    var gr = g.createRadialGradient(16, 16, 1, 16, 16, 15); gr.addColorStop(0, 'rgba(255,255,255,1)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = gr; g.fillRect(0, 0, w, h);
  });
  function updateWeather(dt, now) {
    if (!weatherFx || !OUT) return;
    var f = weatherFx, b = f.box, H = b.y1 - b.y0;
    if (OUT.weather === 'rain' && f.rain.visible) {
      var a = f.rain.geometry.attributes.position.array;
      for (var i = 0; i < f.N; i++) {
        var o = i * 6, y = a[o + 1] - dt * 16 * f.sp[i];
        if (y < b.y0) y += H;
        a[o + 1] = y; a[o + 4] = y - 0.35;
      }
      f.rain.geometry.attributes.position.needsUpdate = true;
    } else if (OUT.weather === 'snow' && f.snow.visible) {
      var s = f.snow.geometry.attributes.position.array, t = now / 1000;
      for (var j = 0; j < f.N; j++) {
        var q = j * 3, yy = s[q + 1] - dt * 1.1 * f.sp[j];
        if (yy < b.y0) yy += H;
        s[q + 1] = yy; s[q + 2] += Math.sin(t * 0.8 + j) * dt * 0.25;
      }
      f.snow.geometry.attributes.position.needsUpdate = true;
    }
  }
  var streetLamps = [];
  // 상태를 장면에 입힌다 (층을 다시 짓지 않고 재질·빛·입자만 바꾼다)
  function applyOutside() {
    var o = resolveOutside();
    if (OUT && OUT.time === o.time && OUT.season === o.season && OUT.weather === o.weather && !applyOutside.force) return;
    applyOutside.force = false;
    OUT = o;
    var night = o.time === 'night', dusk = o.time === 'dusk', grey = o.weather !== 'clear', winter = o.season === 'winter';
    M.pano.map = makePano(o); M.pano.needsUpdate = true;
    // 바깥 물체는 실내 조명을 같이 받으므로 시간·날씨만큼 색을 어둡게 한다 (밤에는 켜진 창·가로등만 밝게)
    var f = night ? 0.13 : dusk ? 0.7 : grey ? 0.8 : 1;
    function tint(m, hex) { m.color.setHex(hex).multiplyScalar(f); }
    var lc = SEASON_LEAF[o.season]; M.leaf.forEach(function (m, i) { tint(m, lc[i]); });
    tint(M.grass, winter ? 0xf4f7fa : o.season === 'autumn' ? 0xd8c690 : 0xffffff);
    M.grass.map = winter ? null : grassTex; M.grass.needsUpdate = true;
    var wet = o.weather === 'rain';
    M.road.roughness = wet ? 0.25 : 0.9; tint(M.road, wet ? 0x8a8f96 : winter ? 0xe4e8ec : 0xffffff);
    M.pave.roughness = wet ? 0.35 : 0.95; tint(M.pave, winter ? 0xf2f4f6 : wet ? 0xb7b4ae : 0xffffff);
    tint(M.trunk, winter ? 0x5a4a3e : 0x6b4f3a); tint(M.pole, 0x3a3d42);
    var FC = [0xd9d2c4, 0xb8c2cc, 0xe7e1d6, 0xa9b3ab, 0xcfc4b8];
    M.facade.forEach(function (m, i) {
      tint(m, FC[i % FC.length]);
      m.emissiveMap = (night || dusk) ? facadeNightTex : null; m.emissive.setHex((night || dusk) ? 0xffffff : 0x000000);
      m.emissiveIntensity = night ? 1 : 0.5; m.needsUpdate = true;
    });
    M.streetLight.emissive.setHex(night || dusk || grey ? 0xffe2a8 : 0x000000);
    M.lightPool.opacity = night ? 1 : dusk ? 0.5 : 0;
    // 바깥 재질은 실내 반사광을 시간에 맞춰 줄인다 (밤에 실내 빛이 바깥 유리·벽에 비치지 않게)
    var envOut = night ? 0.02 : dusk ? 0.12 : 0.25;
    [].concat(M.leaf, M.facade, M.awning, CAR.paint, [M.grass, M.pave, M.road, M.trunk, M.pole, M.shopGlass, M.parapet, CAR.glass, CAR.tire])
      .forEach(function (m) { m.envMapIntensity = envOut; m.userData.envSet = true; });
    M.shopGlass.emissive.setHex(night ? 0x1c1208 : dusk ? 0x120c05 : 0x000000);   // 빛 세기는 선형값이라 아주 어둡게 줘야 은은하다
    CAR.head.emissive.setHex(night || dusk || grey ? 0xfff6dd : 0x000000); CAR.tail.emissive.setHex(night || dusk || grey ? 0xff2a1a : 0x000000);
    tint(M.parapet, 0x8d9094); M.awning.forEach(function (m, i) { tint(m, [0x7a2f2f, 0x2f4f6a, 0x3f5f3a, 0xc9a24a][i]); });
    CAR.paint.forEach(function (m, i) { tint(m, [0xe8e6e1, 0x1f2328, 0x8b1e2b, 0x2c4a7a, 0x9aa2a8, 0x3d5a45, 0xd9c79c][i]); });
    // 빛: 낮은 지금 그대로, 노을은 따뜻하게 낮게, 밤은 달빛 + 실내 조명
    var bg = night ? 0x1a2030 : dusk ? 0xe9cdb5 : grey ? 0xd9dcde : 0xf3efe8;
    scene.background.setHex(bg); scene.fog.color.setHex(bg);
    scene.fog.near = night ? 70 : 40; scene.fog.far = night ? 170 : 120;
    sun.color.setHex(night ? 0x9fb4e0 : dusk ? 0xffb27a : 0xfff4e2);
    sun.intensity = night ? 0.18 : dusk ? 0.6 : grey ? 0.45 : 0.85;
    if (hemi) { hemi.intensity = (night ? 0.5 : grey ? 0.7 : 0.6) * (scene.environment ? 0.5 : 1); hemi.color.setHex(night ? 0xfff1dc : 0xffffff); }
    if (weatherFx) { weatherFx.rain.visible = o.weather === 'rain'; weatherFx.snow.visible = o.weather === 'snow'; }
    M.glassPane.opacity = o.weather === 'rain' ? 0.22 : night ? 0.08 : 0.12;
  }
  setInterval(function () { applyOutside(); }, 60000);   // 자동(시간·계절·날씨)이면 1분마다 확인


  // 창 구멍이 난 옆벽: 창 아래·위 띠 + 창 사이 기둥
  function sideWall(x, z0, z1, wins) {
    var len = z1 - z0, cz0 = (z0 + z1) / 2;
    add(new T.Mesh(new T.BoxGeometry(0.2, 0.5, len), M.wall), x, 0.25, cz0).receiveShadow = true;
    add(new T.Mesh(new T.BoxGeometry(0.2, CEIL - 4.1, len), M.wall), x, (CEIL + 4.1) / 2, cz0).receiveShadow = true;
    var edges = [z0];
    wins.slice().sort(function (a, b) { return a - b; }).forEach(function (wz) { edges.push(wz - 2.7, wz + 2.7); });
    edges.push(z1);
    for (var i = 0; i < edges.length; i += 2) {
      var a = edges[i], b = edges[i + 1];
      if (b - a > 0.01) add(new T.Mesh(new T.BoxGeometry(0.2, 3.6, b - a), M.wall), x, 2.3, (a + b) / 2).receiveShadow = true;
    }
  }
  // 바깥: 층이 높을수록 땅이 내려간다(위층에서 내려다보는 경치)
  // ── 가구 (모서리를 둥글린 상자로 만든 소파·의자·탁자·스탠드, 잎이 여러 겹인 화분) ──
  function rbox(w, h, d, r) {   // 둥근 모서리 상자 (없으면 보통 상자)
    return T.RoundedBoxGeometry ? new T.RoundedBoxGeometry(w, h, d, 3, Math.min(r || 0.04, w / 2, h / 2, d / 2)) : new T.BoxGeometry(w, h, d);
  }
  var fabricTex = canvasTex(128, 128, function (g, w, h) {   // 직물 결
    var r = rnd(61); g.fillStyle = '#ffffff'; g.fillRect(0, 0, w, h);
    for (var i = 0; i < 1800; i++) { g.fillStyle = 'rgba(0,0,0,' + r() * 0.07 + ')'; g.fillRect(r() * w, r() * h, 1, 1 + r() * 2); }
    for (var y = 0; y < h; y += 2) { g.fillStyle = 'rgba(0,0,0,0.025)'; g.fillRect(0, y, w, 1); }
  }, [3, 3]);
  var rugTex = canvasTex(512, 512, function (g, w, h) {   // 러그 (테두리 + 잔무늬)
    var r = rnd(67); g.fillStyle = '#b9a58a'; g.fillRect(0, 0, w, h);
    g.strokeStyle = '#6f5a44'; g.lineWidth = 14; g.strokeRect(22, 22, w - 44, h - 44);
    g.strokeStyle = '#e8dcc6'; g.lineWidth = 4; g.strokeRect(44, 44, w - 88, h - 88);
    for (var i = 0; i < 9000; i++) { g.fillStyle = 'rgba(' + (r() < 0.5 ? '70,55,40' : '240,230,210') + ',' + r() * 0.12 + ')'; g.fillRect(r() * w, r() * h, 2, 2); }
    g.strokeStyle = 'rgba(111,90,68,0.35)'; g.lineWidth = 3;
    for (var k = 0; k < 6; k++) { g.beginPath(); g.ellipse(w / 2, h / 2, 60 + k * 26, 40 + k * 18, 0, 0, Math.PI * 2); g.stroke(); }
  });
  var FURN = {
    sofa: [0x5b6b5e, 0x8a6f5a, 0x3f4a5a, 0xb9ab97].map(function (c) { return new T.MeshStandardMaterial({ color: c, map: fabricTex, roughness: 0.95 }); }),
    leather: new T.MeshStandardMaterial({ color: 0x7a4a2c, roughness: 0.45, metalness: 0.05 }),
    rug: new T.MeshStandardMaterial({ map: rugTex, roughness: 1 }),
    walnut: new T.MeshStandardMaterial({ map: oakTex, color: 0x8a6a50, roughness: 0.45 }),
    brass: new T.MeshStandardMaterial({ color: 0xb8924a, roughness: 0.3, metalness: 0.9 }),
    shadeOn: new T.MeshStandardMaterial({ color: 0xf6ead2, emissive: 0xffdca0, emissiveIntensity: 0.55, roughness: 0.9, side: T.DoubleSide }),
    soil: new T.MeshStandardMaterial({ color: 0x3b2c22, roughness: 1 }),
    leaves: [0x3f6b3a, 0x4f7d44, 0x5f8f4e, 0x355c33].map(function (c) { return new T.MeshStandardMaterial({ color: c, roughness: 0.7, side: T.DoubleSide }); })
  };
  Object.keys(FURN).forEach(function (k) { [].concat(FURN[k]).forEach(function (m) { m.userData.keep = true; }); });   // 층을 바꿔도 지우지 않음
  function part(g, geo, mat, x, y, z, rx, ry, rz) {
    var m = new T.Mesh(geo, mat); m.position.set(x, y, z); if (rx || ry || rz) m.rotation.set(rx || 0, ry || 0, rz || 0);
    m.castShadow = true; m.receiveShadow = true; g.add(m); return m;
  }
  function sofa(x, z, ry, seats, mat) {   // 소파 (seats=1이면 안락의자)
    var g = new T.Group(); g.position.set(x, 0, z); g.rotation.y = ry; parent.add(g);
    var W = 0.78 * seats + 0.36;
    part(g, rbox(W, 0.22, 0.9, 0.05), mat, 0, 0.21, 0);                                          // 받침
    for (var i = 0; i < seats; i++) part(g, rbox(0.76, 0.16, 0.72, 0.06), mat, (i - (seats - 1) / 2) * 0.78, 0.4, 0.06);   // 방석
    part(g, rbox(W, 0.52, 0.2, 0.07), mat, 0, 0.56, -0.36, -0.12);                                // 등받이
    [-1, 1].forEach(function (s) { part(g, rbox(0.18, 0.5, 0.9, 0.07), mat, s * (W / 2 - 0.09), 0.38, 0); });   // 팔걸이
    [-1, 1].forEach(function (s) { [-1, 1].forEach(function (t) {                                   // 다리
      part(g, new T.CylinderGeometry(0.025, 0.018, 0.12, 10), FURN.walnut, s * (W / 2 - 0.08), 0.06, t * 0.36);
    }); });
    if (seats > 1) part(g, rbox(0.42, 0.36, 0.12, 0.05), FURN.sofa[3], -W / 2 + 0.45, 0.62, -0.18, -0.25, 0.2);   // 쿠션
    return g;
  }
  function coffeeTable(x, z, ry) {
    var g = new T.Group(); g.position.set(x, 0, z); g.rotation.y = ry; parent.add(g);
    part(g, rbox(1.2, 0.05, 0.62, 0.02), FURN.walnut, 0, 0.42, 0);
    part(g, rbox(1.1, 0.03, 0.54, 0.01), FURN.walnut, 0, 0.12, 0);
    [-1, 1].forEach(function (s) { [-1, 1].forEach(function (t) { part(g, new T.CylinderGeometry(0.018, 0.018, 0.4, 8), M.black, s * 0.54, 0.2, t * 0.26); }); });
    var r = rnd(Math.floor(x * 13 + z * 7) + 99);
    for (var i = 0; i < 3; i++) {   // 쌓인 책 + 머그잔
      part(g, new T.BoxGeometry(0.24 + r() * 0.06, 0.035, 0.17), new T.MeshStandardMaterial({ color: PALETTE[Math.floor(r() * PALETTE.length)], roughness: 0.6 }),
        -0.3, 0.465 + i * 0.036, 0, 0, r() * 0.4 - 0.2, 0);
    }
    part(g, new T.CylinderGeometry(0.045, 0.04, 0.1, 16), M.white, 0.32, 0.495, 0.08);
    return g;
  }
  function floorLamp(x, z) {
    var g = new T.Group(); g.position.set(x, 0, z); parent.add(g);
    part(g, new T.CylinderGeometry(0.17, 0.19, 0.03, 24), M.black, 0, 0.015, 0);
    part(g, new T.CylinderGeometry(0.014, 0.014, 1.55, 8), FURN.brass, 0, 0.79, 0);
    part(g, new T.CylinderGeometry(0.17, 0.25, 0.3, 24, 1, true), FURN.shadeOn, 0, 1.66, 0).castShadow = false;
    return g;
  }
  function rug(x, z, w, d, ry) {
    var m = new T.Mesh(new T.PlaneGeometry(w, d), FURN.rug); m.rotation.set(-Math.PI / 2, 0, ry || 0); m.receiveShadow = true;
    add(m, x, 0.006, z); return m;
  }
  var leafGeo = (function () {   // 끝이 뾰족한 잎 한 장 (평면을 휘어서)
    var gq = new T.PlaneGeometry(0.16, 0.62, 2, 6), p = gq.attributes.position;
    for (var i = 0; i < p.count; i++) {
      var y = p.getY(i) + 0.31, t = y / 0.62;
      p.setX(i, p.getX(i) * Math.sin(Math.PI * Math.min(1, t * 1.1)) * 1.1);
      p.setZ(i, -Math.pow(t, 2) * 0.22 + Math.abs(p.getX(i)) * 0.3);
      p.setY(i, y);
    }
    gq.computeVertexNormals(); gq.userData.shared = true; return gq;
  })();
  // ── 3D 모형 파일 (설정 > 3D 모형에서 '모형 파일' 고르면): 소파·의자·화분(Khronos glTF 예제, CC BY 4.0), 자동차(three.js 예제 Ferrari 458) ──
  var REAL_BASE = 'https://cdn.jsdelivr.net/gh/KhronosGroup/glTF-Sample-Assets@main/Models/';
  var REAL_FILES = {
    sofa: REAL_BASE + 'GlamVelvetSofa/glTF-Binary/GlamVelvetSofa.glb',
    chair: REAL_BASE + 'ChairDamaskPurplegold/glTF-Binary/ChairDamaskPurplegold.glb',
    plant: REAL_BASE + 'DiffuseTransmissionPlant/glTF-Binary/DiffuseTransmissionPlant.glb',
    car: 'https://cdn.jsdelivr.net/gh/mrdoob/three.js@r175/examples/models/gltf/ferrari.glb'
  };
  var MODELS = 'basic';   // 설정값: basic(지금 그대로) | real(모형 파일)
  var REAL = {}, realLoading = false, carPaints = null;
  function loadReal() {
    if (realLoading || MODELS !== 'real' || !T.GLTFLoader) return;
    realLoading = true;
    var gl = new T.GLTFLoader();
    if (T.DRACOLoader) { var dr = new T.DRACOLoader(); dr.setDecoderPath('https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/libs/draco/gltf/'); gl.setDRACOLoader(dr); }
    var left = Object.keys(REAL_FILES).length;
    Object.keys(REAL_FILES).forEach(function (k) {
      gl.load(REAL_FILES[k], function (g) {
        var root = g.scene;
        root.traverse(function (o) {
          if (/firefly|light/i.test(o.name) && k === 'plant') o.visible = false;   // 화분 모형의 반딧불이·조명은 뺀다
          if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; }
        });
        keepShared(root); REAL[k] = root;
        if (--left === 0) rebuildForModels();
      }, undefined, function (e) { console.warn('3D 서재 모형 파일:', k, e); if (--left === 0) rebuildForModels(); });
    });
  }
  function rebuildForModels() { if (cur >= 0 && floors[cur]) buildFloor(cur); }
  function useReal(k) { return MODELS === 'real' && REAL[k]; }
  // 모형을 크기에 맞춰 놓는다 (바닥에 붙이고 가운데 정렬). size: {w: 너비} 또는 {h: 높이} 또는 {l: 길이}
  function fitClone(k, size, x, y, z, ry) {
    var src = REAL[k], c = src.clone(), box = new T.Box3().setFromObject(src), sz = new T.Vector3(); box.getSize(sz);
    var sc = size.w ? size.w / sz.x : size.h ? size.h / sz.y : size.l / sz.z;
    var inner = new T.Group(); inner.add(c); c.position.set(-(box.min.x + box.max.x) / 2, -box.min.y, -(box.min.z + box.max.z) / 2);
    var g = new T.Group(); g.add(inner); inner.scale.setScalar(sc); g.position.set(x, y || 0, z); g.rotation.y = ry || 0;
    parent.add(g); return g;
  }
  function plant(x, z, scale, seed) {   // 화분 + 줄기마다 잎이 겹겹이
    if (useReal('plant')) return fitClone('plant', { h: 1.3 * (scale || 1) }, x, 0, z, (seed || 0) * 1.7);
    var g = new T.Group(); g.position.set(x, 0, z); g.scale.setScalar(scale || 1); parent.add(g);
    part(g, new T.CylinderGeometry(0.28, 0.21, 0.55, 28), M.pot, 0, 0.275, 0);
    part(g, new T.CylinderGeometry(0.29, 0.29, 0.03, 28), M.pot, 0, 0.55, 0);
    part(g, new T.CircleGeometry(0.26, 24), FURN.soil, 0, 0.545, 0, -Math.PI / 2);
    var r = rnd(seed || 7);
    for (var s = 0; s < 14; s++) {
      var a = r() * Math.PI * 2, tilt = 0.15 + r() * 0.5, len = 0.55 + r() * 0.75;
      var stem = new T.Group(); stem.position.set(Math.cos(a) * 0.05, 0.55, Math.sin(a) * 0.05); stem.rotation.set(0, -a, 0); g.add(stem);
      var arm = new T.Group(); arm.rotation.z = tilt; stem.add(arm);
      part(arm, new T.CylinderGeometry(0.008, 0.012, len, 5), FURN.leaves[3], 0, len / 2, 0).castShadow = false;
      for (var l = 0; l < 3; l++) {
        var lf = part(arm, leafGeo, FURN.leaves[Math.floor(r() * 3)], 0, len * (0.55 + l * 0.2), 0, -0.6 - r() * 0.5, r() * Math.PI * 2, 0.3);
        lf.scale.setScalar(0.8 + r() * 0.5);
      }
    }
    return g;
  }
  // 로비 라운지: 러그 + 소파 + 안락의자 둘 + 탁자 + 스탠드 (양쪽)
  function lounge(cx, cz, flip) {
    rug(cx, cz, 4.2, 3.2);
    if (useReal('sofa') && useReal('chair')) {   // 모형 파일: 벨벳 소파 + 단추 장식 의자 둘
      fitClone('sofa', { w: 2.5 }, cx, 0, cz - 1.05, 0);
      fitClone('chair', { w: 0.95 }, cx - 1.65, 0, cz + 0.35, Math.PI / 2 + 0.25);
      fitClone('chair', { w: 0.95 }, cx + 1.65, 0, cz + 0.35, -Math.PI / 2 - 0.25);
      coffeeTable(cx, cz + 0.05, 0);
      floorLamp(cx + 1.85, cz - 1.25);
      plant(cx - 2.0, cz - 1.3, 0.8, 11 + (flip ? 3 : 0));
      return;
    }
    sofa(cx, cz - 1.15, 0, 3, FURN.sofa[flip ? 2 : 0]);
    sofa(cx - 1.65, cz + 0.35, Math.PI / 2 + 0.25, 1, FURN.leather);
    sofa(cx + 1.65, cz + 0.35, -Math.PI / 2 - 0.25, 1, FURN.sofa[1]);
    coffeeTable(cx, cz + 0.05, 0);
    floorLamp(cx + 1.85, cz - 1.25);
    plant(cx - 2.0, cz - 1.3, 0.8, 11 + (flip ? 3 : 0));
  }
  // ── 바깥 차 (차도를 오가며 달린다, 밤엔 전조등·후미등) ──
  var CAR = {
    paint: [0xe8e6e1, 0x1f2328, 0x8b1e2b, 0x2c4a7a, 0x9aa2a8, 0x3d5a45, 0xd9c79c].map(function (c) { return new T.MeshStandardMaterial({ color: c, roughness: 0.25, metalness: 0.6 }); }),
    glass: new T.MeshStandardMaterial({ color: 0x1b232c, roughness: 0.08, metalness: 0.4 }),
    tire: new T.MeshStandardMaterial({ color: 0x151515, roughness: 0.9 }),
    head: new T.MeshStandardMaterial({ color: 0xf2f2ea, emissive: 0x000000, emissiveIntensity: 1.5 }),
    tail: new T.MeshStandardMaterial({ color: 0x7a1010, emissive: 0x000000, emissiveIntensity: 1.5 })
  };
  Object.keys(CAR).forEach(function (k) { [].concat(CAR[k]).forEach(function (m) { m.userData.keep = true; }); });
  var carGeo = null;
  function carParts() {
    if (carGeo) return carGeo;
    carGeo = { body: rbox(1.8, 0.62, 4.3, 0.18), cabin: rbox(1.6, 0.55, 2.3, 0.2), wheel: new T.CylinderGeometry(0.33, 0.33, 0.24, 18),
               lamp: new T.BoxGeometry(0.42, 0.12, 0.05) };
    Object.keys(carGeo).forEach(function (k) { carGeo[k].userData.shared = true; });
    return carGeo;
  }
  var cars = [];
  function makeCar(r) {
    if (useReal('car')) {   // 모형 파일 차: 차체 색만 바꾼다 (모형은 앞이 -z라 돌려 세운다)
      if (!carPaints) {
        var bodyMat = null; REAL.car.traverse(function (o) { if (o.isMesh && o.name === 'body' && !bodyMat) bodyMat = o.material; });
        carPaints = [0xe8e6e1, 0x1f2328, 0x8b1e2b, 0x2c4a7a, 0x9aa2a8, 0x3d5a45, 0xd9c79c].map(function (c) {
          var m = bodyMat ? bodyMat.clone() : new T.MeshStandardMaterial({ roughness: 0.25, metalness: 0.6 }); m.color.setHex(c); m.userData.keep = true; return m;
        });
      }
      var holder = parent, tmpG = new T.Group(); parent = tmpG;
      var car = fitClone('car', { l: 4.4 }, 0, 0, 0, Math.PI);
      parent = holder;
      var paint = carPaints[Math.floor(r() * carPaints.length)];
      car.traverse(function (o) { if (!o.isMesh) return; o.castShadow = false; if (o.name === 'body') o.material = paint; });   // 바깥이라 그림자 생략(가볍게)
      return tmpG;
    }
    var G = carParts(), g = new T.Group();
    var paint = CAR.paint[Math.floor(r() * CAR.paint.length)];
    function p(geo, mat, x, y, z, rz) { var m = new T.Mesh(geo, mat); m.position.set(x, y, z); if (rz) m.rotation.z = rz; m.castShadow = true; g.add(m); return m; }
    p(G.body, paint, 0, 0.6, 0);
    var cab = p(G.cabin, CAR.glass, 0, 1.12, -0.25); cab.scale.set(1, 1, 1);
    p(G.cabin, paint, 0, 1.34, -0.25).scale.set(1.01, 0.12, 0.92);   // 지붕
    [-1, 1].forEach(function (s) { [-1.35, 1.35].forEach(function (z) { p(G.wheel, CAR.tire, s * 0.82, 0.33, z, Math.PI / 2); }); });
    [-0.6, 0.6].forEach(function (x) { p(G.lamp, CAR.head, x, 0.7, 2.15); p(G.lamp, CAR.tail, x, 0.72, -2.15); });
    return g;
  }
  function addCars(w, back, front, gy) {
    cars = [];
    var r = rnd(83), span = { z0: back - 60, z1: front + 60 };
    [-1, 1].forEach(function (side) {
      var roadX = side * (w / 2 + 9);
      [-1, 1].forEach(function (dir) {   // 차선 둘 (반대 방향)
        var laneX = roadX + dir * 1.9, n = useReal('car') ? 2 : 3 + Math.floor(r() * 2);   // 모형 차는 무거워 차선마다 2대
        for (var i = 0; i < n; i++) {
          var c = makeCar(r); c.position.set(laneX, gy, span.z0 + r() * (span.z1 - span.z0)); c.rotation.y = dir > 0 ? 0 : Math.PI;
          parent.add(c);
          cars.push({ g: c, dir: dir, speed: 7 + r() * 6, span: span });
        }
      });
    });
  }
  function updateCars(dt) {
    for (var i = 0; i < cars.length; i++) {
      var c = cars[i], z = c.g.position.z + c.dir * c.speed * dt;
      if (z > c.span.z1) z = c.span.z0; else if (z < c.span.z0) z = c.span.z1;
      c.g.position.z = z;
    }
  }
  // 건너편 건물 간판 이름 (오른쪽 서재 옆 건물은 (주)CRARES)
  var SIGN_NAMES = ['betty2859', 'C-Rhapsody', 'colaiuta', 'daydreamrabbit', 'grandfoxx', 'javara999', 'madnite1', 'venushoon'];
  var SIGN_COLORS = [['#1d3557', '#f1faee'], ['#7a1f2b', '#fff4e6'], ['#f4f1ea', '#1d1e20'], ['#2d6a4f', '#ffffff'], ['#f2b705', '#1d1e20'],
                     ['#3a0ca3', '#ffffff'], ['#222222', '#ffd166'], ['#e76f51', '#ffffff']];
  function addOutside(w, back, front, floorIdx) {
    var gy = -floorIdx * 4.5 - 0.05, cz = (front + back) / 2, d = front - back, r = rnd(53 + floorIdx);
    var ground = new T.Mesh(new T.CircleGeometry(SCENE_R - 2, 48), M.grass); ground.rotation.x = -Math.PI / 2; add(ground, 0, gy, cz);
    var pano = new T.Mesh(new T.CylinderGeometry(SCENE_R, SCENE_R, 110, 64, 1, true), M.pano);
    add(pano, 0, EYE - 110 * 0.3 + 110 / 2, cz);   // 그림의 지평선(아래에서 30%)을 눈높이에 맞춘다
    pano.rotation.y = floorIdx * 1.3;
    var len = d + 120;
    var signed = { crares: false, next: 0 };
    [1, -1].forEach(function (side) {
      var walkX = side * (w / 2 + 2.5), roadX = side * (w / 2 + 9), farWalkX = side * (w / 2 + 15.5);
      var walk = new T.Mesh(new T.PlaneGeometry(5, len), M.pave); walk.rotation.x = -Math.PI / 2; add(walk, walkX, gy + 0.02, cz);
      var road = new T.Mesh(new T.PlaneGeometry(8, len), M.road); road.rotation.x = -Math.PI / 2; add(road, roadX, gy + 0.01, cz);
      var walk2 = new T.Mesh(new T.PlaneGeometry(5, len), M.pave); walk2.rotation.x = -Math.PI / 2; add(walk2, farWalkX, gy + 0.02, cz);
      for (var tz = back - 40; tz < front + 40; tz += 7 + r() * 3) {   // 가로수 (양쪽 보도)
        [walkX + side * 1.4, farWalkX - side * 1.4].forEach(function (tx) {
          var trunk = new T.Mesh(trunkGeo, M.trunk); add(trunk, tx, gy + 1.3, tz);
          var ch = gy + 3.4 + r() * 0.5;
          for (var cc = 0; cc < 5; cc++) {   // 잎 덩어리 여러 개를 겹쳐 나무 윤곽을 울퉁불퉁하게
            var crown = new T.Mesh(crownGeo, M.leaf[Math.floor(r() * M.leaf.length)]), sz = cc ? 0.5 + r() * 0.25 : 0.85;
            crown.scale.set(sz * (1 + r() * 0.3), sz * (1 + r() * 0.4), sz * (1 + r() * 0.3)); crown.rotation.set(r() * 3, r() * 3, 0);
            add(crown, tx + (cc ? (r() - 0.5) * 1.8 : 0), ch + (cc ? (r() - 0.3) * 1.4 : 0), tz + (cc ? (r() - 0.5) * 1.8 : 0));
          }
        });
      }
      for (var lz = back - 30; lz < front + 30; lz += 14) {   // 가로등 (밤·흐린 날 켜짐)
        var lx = walkX + side * 2.1;   // 차도 쪽 보도 가장자리
        var pole = new T.Mesh(unitBox, M.pole); pole.scale.set(0.12, 5, 0.12); add(pole, lx, gy + 2.5, lz);
        var arm = new T.Mesh(unitBox, M.pole); arm.scale.set(1.1, 0.08, 0.08); add(arm, lx + side * 0.5, gy + 4.95, lz);
        var bulb = new T.Mesh(unitBox, M.streetLight); bulb.scale.set(0.5, 0.12, 0.28); add(bulb, lx + side * 1.0, gy + 4.85, lz);
        var pool = new T.Mesh(poolGeo, M.lightPool); pool.rotation.x = -Math.PI / 2; add(pool, lx + side * 1.0, gy + 0.04, lz);   // 바닥 불빛
      }
      for (var bz = back - 50; bz < front + 50;) {   // 건너편 건물들
        var bw = 10 + r() * 14, bd = 10 + r() * 10, bh = 9 + Math.pow(r(), 1.6) * 34;
        var mat = M.facade[Math.floor(r() * M.facade.length)];
        var bld = new T.Mesh(unitBox, mat); bld.scale.set(bd, bh, bw);
        var bx = side * (w / 2 + 18 + bd / 2 + r() * 6);
        add(bld, bx, gy + bh / 2, bz + bw / 2);
        var shop = new T.Mesh(unitBox, M.shopGlass); shop.scale.set(bd + 0.2, 3.4, bw + 0.2); add(shop, bx, gy + 1.7, bz + bw / 2);   // 1층 상점 유리
        var aw = new T.Mesh(unitBox, M.awning[Math.floor(r() * M.awning.length)]); aw.scale.set(1.4, 0.12, bw * 0.8);   // 차양
        aw.rotation.z = side * 0.25; add(aw, bx - side * (bd / 2 + 0.6), gy + 3.6, bz + bw / 2);
        var cap = new T.Mesh(unitBox, M.parapet); cap.scale.set(bd + 0.3, 0.5, bw + 0.3); add(cap, bx, gy + bh + 0.25, bz + bw / 2);   // 옥상 난간
        var mid = bz + bw / 2, nm = null;   // 간판: 오른쪽 서재 옆 건물엔 (주)CRARES, 나머지 건물엔 이름 간판을 차례로
        if (side > 0 && !signed.crares && mid > back && mid < front) { signed.crares = true; nm = '(주)CRARES'; }
        else if (mid > back - 35 && mid < front + 35 && signed.next < SIGN_NAMES.length) nm = SIGN_NAMES[signed.next++];
        if (nm) {
          var sw = Math.min(bw * 0.85, 11), sh = sw * 0.22, sy = gy + Math.min(bh - sh, 14), sx = bx - side * (bd / 2 + 0.2), sc0 = SIGN_COLORS[(signed.next + (side > 0 ? 0 : 3)) % SIGN_COLORS.length];
          if (nm === '(주)CRARES') sc0 = ['#14181f', '#ffffff'];
          var sign = new T.Mesh(new T.PlaneGeometry(sw, sh), new T.MeshBasicMaterial({ map: textTex([nm], 1024, 224, sc0[0], sc0[1], nm.length > 10 ? 120 : 150), toneMapped: false }));
          sign.rotation.y = -side * Math.PI / 2; add(sign, sx, sy, mid);   // 서재 쪽을 보게
          var sbk = new T.Mesh(unitBox, M.pole); sbk.scale.set(0.15, sh + 0.25, sw + 0.25); add(sbk, bx - side * (bd / 2 + 0.05), sy, mid);
        }
        if (r() < 0.5) { var hut = new T.Mesh(unitBox, M.parapet); hut.scale.set(bd * 0.3, 2.2, bw * 0.25); add(hut, bx + (r() - 0.5) * bd * 0.4, gy + bh + 1.1, bz + bw / 2 + (r() - 0.5) * bw * 0.4); }
        bz += bw + 2 + r() * 6;
      }
    });
    addWeather(w, back, front, gy);
    addCars(w, back, front, gy);
  }
  function addBuilding(fl, cols, rows) {
    var w = cols * BOOTH_W + (cols - 1) * GAP + 12, back = -LOBBY - rows * (BOOTH_D + GAP) - 2, front = 10;
    var d = front - back, cz = (front + back) / 2;
    hall = { x0: -w / 2 + 0.6, x1: w / 2 - 0.6, z0: back + 0.6, z1: front - 0.6 };
    layout = { w: w, front: front, back: back, cols: cols, rows: rows, sections: [] };
    floorTex.repeat.set(w / 7, d / 7);
    var fl0 = new T.Mesh(new T.PlaneGeometry(w, d), M.floor);
    fl0.rotation.x = -Math.PI / 2; fl0.receiveShadow = true; add(fl0, 0, 0, cz);
    var ceil = new T.Mesh(new T.PlaneGeometry(w, d), M.ceil);
    ceil.rotation.x = Math.PI / 2; add(ceil, 0, CEIL, cz);
    // 매입 조명 (천장의 밝은 사각)
    for (var lz = front - 3; lz > back + 2; lz -= 4.5) {
      for (var lx = -w / 2 + 4; lx < w / 2 - 2; lx += 6) {
        var l = new T.Mesh(new T.PlaneGeometry(0.6, 0.6), M.lamp); l.rotation.x = Math.PI / 2; add(l, lx, CEIL - 0.01, lz);
      }
    }
    // 벽 + 걸레받이 (앞뒤 벽은 통으로, 옆벽은 창 구멍을 내서)
    var wins = [];
    for (var wz0 = front - 6; wz0 > back + 3; wz0 -= 7) wins.push(wz0);
    [[0, front, w, 0], [0, back, w, 0], [-w / 2, cz, d, Math.PI / 2], [w / 2, cz, d, Math.PI / 2]].forEach(function (s, si) {
      if (si < 2) {
        var wall = new T.Mesh(new T.BoxGeometry(s[2], CEIL, 0.2), M.wall);
        wall.rotation.y = s[3]; wall.receiveShadow = true; add(wall, s[0], CEIL / 2, s[1]);
      } else sideWall(s[0], back, front, wins);
      var base = new T.Mesh(new T.BoxGeometry(s[2], 0.12, 0.24), M.black);
      base.rotation.y = s[3]; add(base, s[0], 0.06, s[1]);
    });
    addOutside(w, back, front, Math.max(0, cur));
    // 큰 창 (양옆 벽, 검은 창틀, 거의 투명한 유리 너머로 바깥 경치)
    for (var wz = front - 6; wz > back + 3; wz -= 7) {
      [-1, 1].forEach(function (side) {
        var gx = side * (w / 2 - 0.11);
        var glass = new T.Mesh(new T.PlaneGeometry(5.4, 3.6), M.glassPane);
        glass.rotation.y = -side * Math.PI / 2; add(glass, gx, 2.3, wz);
        [-2.7, 0, 2.7].forEach(function (o) { var mul = new T.Mesh(new T.BoxGeometry(0.05, 3.7, 0.06), M.black); mul.rotation.y = -side * Math.PI / 2; add(mul, gx, 2.3, wz + o); });
        [0.5, 4.1].forEach(function (y) { add(new T.Mesh(new T.BoxGeometry(0.06, 0.05, 5.5), M.black), gx, y, wz); });
      });
    }
    // 창으로 드는 햇빛 방향 + 그림자 범위
    sun.position.set(w / 2 + 10, 14, cz + 6);
    sun.target.position.set(0, 0, cz);
    var sc = sun.shadow.camera, ext = Math.max(w, d) / 2 + 4;
    sc.left = -ext; sc.right = ext; sc.top = ext; sc.bottom = -ext; sc.near = 1; sc.far = 80; sc.updateProjectionMatrix();
    // 입구 유리문
    var door = new T.Mesh(new T.PlaneGeometry(3.6, 2.8), M.sky); door.rotation.y = Math.PI; add(door, 0, 1.4, front - 0.11);
    box(3.7, 0.06, 0.08, M.black, 0, 2.82, front - 0.14); box(0.05, 2.8, 0.08, M.black, 0, 1.4, front - 0.14);
    // 간판 (흰 판, 검은 글씨) - 들어오면 정면 위
    var title = textTex(['BookOasis', fl.label + '  ·  보관함 ' + fl.libs.length + '  ·  작품 ' + fl.total.toLocaleString()],
      1600, 300, '#f7f5f1', '#1d1e20', 118);
    var signBoard = new T.Mesh(new T.BoxGeometry(8.4, 1.58, 0.06), [M.black, M.black, M.black, M.black, new T.MeshBasicMaterial({ map: title }), M.black]);
    add(signBoard, 0, 3.55, front - 7.5);
    [-3.8, 3.8].forEach(function (sx) { add(new T.Mesh(new T.CylinderGeometry(0.006, 0.006, CEIL - 4.34, 6), M.black), sx, (CEIL + 4.34) / 2, front - 7.5); });
    // 계산대 (흰 몸통, 원목 상판) + 벤치 + 화분
    box(4.6, 1.0, 0.9, M.white, w / 2 - 5.5, 0.5, front - 5.5, true);
    box(4.8, 0.05, 1.05, M.oak, w / 2 - 5.5, 1.02, front - 5.5, true);
    var deskSign = new T.Mesh(new T.PlaneGeometry(1.4, 0.28), new T.MeshBasicMaterial({ map: textTex(['INFORMATION · 안내'], 512, 100, '#f7f5f1', '#1d1e20', 46) }));
    add(deskSign, w / 2 - 5.5, 0.72, front - 5.04);
    box(2.4, 0.06, 0.5, M.oak, -2.8, 0.45, front - 3.2, true);
    [-1.05, 1.05].forEach(function (o) { box(0.05, 0.42, 0.42, M.black, -2.8 + o, 0.21, front - 3.2); });
    [[w / 2 - 1.2, front - 1.2], [-w / 2 + 1.2, front - 1.2], [w / 2 - 1.2, back + 1.2], [-w / 2 + 1.2, back + 1.2]].forEach(function (p, i) {
      plant(p[0], p[1], 1.25, 3 + i);
    });
    // 라운지 (로비 양쪽, 통로를 피해서)
    var lx = Math.max(w / 2 - 6.5, 8);
    lounge(-lx, front - 13, false);
    lounge(lx, front - 13, true);
    // 층 안내판 (왼쪽, 이 층의 서가 목록)
    var lines = [fl.label].concat(fl.libs.slice(0, 15).map(function (l) { return l.name; }));
    if (fl.libs.length > 15) lines.push('… 외 ' + (fl.libs.length - 15) + '개');
    var dir = canvasTex(512, 760, function (g) {
      g.fillStyle = '#1d1e20'; g.fillRect(0, 0, 512, 760);
      g.fillStyle = '#f5f2ec'; g.textBaseline = 'top';
      lines.forEach(function (ln, i) { g.font = (i ? '400 30px ' : '700 44px ') + FONT; g.fillText(ln, 32, 28 + i * (i ? 44 : 60), 448); });
    });
    var stand = new T.Mesh(new T.BoxGeometry(1.4, 2.1, 0.05), [M.black, M.black, M.black, M.black, new T.MeshBasicMaterial({ map: dir }), M.black]);
    add(stand, -w / 2 + 5, 1.25, front - 6, true);
    box(0.5, 0.2, 0.3, M.black, -w / 2 + 5, 0.1, front - 6);
    // 엘리베이터 (왼쪽 벽, 스테인리스 문, 누르면 층 고르기)
    var ev = new T.Group(); ev.position.set(-w / 2 + 0.11, 0, front - 3); ev.rotation.y = Math.PI / 2; parent.add(ev);
    var frame = new T.Mesh(new T.BoxGeometry(2.5, 2.9, 0.06), M.black); frame.position.set(0, 1.45, 0.02); ev.add(frame);
    var doorM = new T.Mesh(new T.BoxGeometry(2.2, 2.7, 0.06), M.steel); doorM.position.set(0, 1.35, 0.06); ev.add(doorM);
    var seam = new T.Mesh(new T.BoxGeometry(0.01, 2.7, 0.07), M.black); seam.position.set(0, 1.35, 0.065); ev.add(seam);
    var lab = new T.Mesh(new T.PlaneGeometry(2.2, 0.32), new T.MeshBasicMaterial({ map: textTex(['ELEVATOR  ·  ' + fl.label], 640, 92, '#1d1e20', '#f5f2ec', 44) }));
    lab.position.set(0, 3.05, 0.06); ev.add(lab);
    doorM.userData.elevator = true;
    elevator = doorM;
  }

  // ── 사람들: 통로를 걷는 손님, 서가 앞에서 책을 고르는 손님, 서서 읽는 손님, 벤치에 앉은 손님, 안내 직원 ──
  // 옷 입은 사람 모형(Michelle)·관절 모형(Xbot)을 받으면 그것으로, 못 받으면 둥근 몸통·원통 팔다리로 만든 단순한 사람. 누를 수 없고 걸어 다니는 사람과 부딪히지 않는다.
  var people = [], layout = null, chatPair = null;
  var AI = { chat: false, ask: false, chat_sec: 60 };
  var SKIN = [0xf1c9a5, 0xe5b48e, 0xc99067, 0x9c6845, 0xf6d9c4];
  var CLOTH = [0x2f3b4c, 0x7a3b3b, 0xe4e0d8, 0x3f5a4a, 0x9b8f7a, 0x26292f, 0x5e6f86, 0xb07a4f, 0x6d5a7e, 0xcfc7b8, 0x8a9a6b];
  var PANTS = [0x23262b, 0x3a4352, 0x5b5248, 0x2e3a2f, 0xb9b0a0, 0x1f2633];
  var HAIR = [0x1d1a17, 0x3b2a1e, 0x6b4a2e, 0x9a7b5a, 0x2a2a2a, 0xb8b1a6];
  var torsoGeo = new T.LatheGeometry([new T.Vector2(0.15, 0), new T.Vector2(0.17, 0.14), new T.Vector2(0.195, 0.4),
    new T.Vector2(0.205, 0.5), new T.Vector2(0.17, 0.58), new T.Vector2(0.07, 0.63), new T.Vector2(0.0, 0.64)], 24);
  var legGeo = new T.CylinderGeometry(0.075, 0.058, 0.86, 14);
  var armGeo = new T.CylinderGeometry(0.052, 0.042, 0.6, 12);
  var ballGeo = new T.SphereGeometry(1, 20, 14);
  var hairGeo = new T.SphereGeometry(0.118, 22, 14, 0, Math.PI * 2, 0, Math.PI * 0.56);
  var neckGeo = new T.CylinderGeometry(0.048, 0.052, 0.12, 12);
  function std(c, r) { return new T.MeshStandardMaterial({ color: c, roughness: r || 0.8 }); }

  function person(seed, beach) {
    var r = rnd(seed * 7919 + 13), pick = function (a) { return a[Math.floor(r() * a.length)]; };
    var skin = std(pick(SKIN), 0.7), shirt = std(pick(CLOTH)), pants = std(pick(PANTS)), hair = std(pick(HAIR), 0.9),
        shoe = std(r() < 0.5 ? 0x1b1b1b : 0xe8e4dc, 0.6);
    if (beach) {   // 숨은 인물: 맨팔·맨다리(피부색) 위에 비키니, 샌들
      skin = std(0xf0c4a0, 0.65); shirt = skin; pants = skin; hair = std(0x5a3a22, 0.85); shoe = std(0xd8b47c, 0.7);
    }
    var g = new T.Group(), body = new T.Group();
    g.add(body);
    function limb(geo, mat, px, py, len) {
      var pivot = new T.Group(); pivot.position.set(px, py, 0); body.add(pivot);
      var m = new T.Mesh(geo, mat); m.position.y = -len / 2; m.castShadow = true; pivot.add(m);
      return pivot;
    }
    var legL = limb(legGeo, pants, -0.09, 0.92, 0.86), legR = limb(legGeo, pants, 0.09, 0.92, 0.86);
    [legL, legR].forEach(function (leg) {
      var s = new T.Mesh(ballGeo, shoe); s.scale.set(0.065, 0.045, 0.13); s.position.set(0, -0.88, 0.035); leg.add(s);
    });
    var torso = new T.Mesh(torsoGeo, shirt); torso.position.y = 0.88; torso.castShadow = true; body.add(torso);
    var armL = limb(armGeo, shirt, -0.235, 1.46, 0.6), armR = limb(armGeo, shirt, 0.235, 1.46, 0.6);
    [armL, armR].forEach(function (arm) { var hnd = new T.Mesh(ballGeo, skin); hnd.scale.setScalar(0.048); hnd.position.y = -0.64; arm.add(hnd); });
    var neck = new T.Mesh(neckGeo, skin); neck.position.y = 1.55; body.add(neck);
    var head = new T.Group(); head.position.y = 1.7; body.add(head);
    var face = new T.Mesh(ballGeo, skin); face.scale.set(0.105, 0.125, 0.11); face.castShadow = true; head.add(face);
    var hr = new T.Mesh(hairGeo, hair); hr.position.set(0, 0.025, -0.008); hr.rotation.x = -0.25; head.add(hr);
    if (beach) {
      var suit = std(0xe2465a, 0.5);
      var top = new T.Mesh(new T.CylinderGeometry(0.188, 0.195, 0.11, 24), suit); top.position.y = 1.3; body.add(top);
      [-1, 1].forEach(function (sd) {   // 끈
        var st = new T.Mesh(new T.CylinderGeometry(0.008, 0.008, 0.2, 6), suit); st.position.set(sd * 0.1, 1.42, 0.06); st.rotation.x = 0.3; body.add(st);
      });
      var bottom = new T.Mesh(new T.CylinderGeometry(0.158, 0.15, 0.13, 24), suit); bottom.position.y = 0.93; body.add(bottom);
      var long = new T.Mesh(new T.CylinderGeometry(0.1, 0.06, 0.38, 16), hair); long.position.set(0, -0.15, -0.07); head.add(long);   // 긴 머리
      var straw = std(0xe9d29a, 0.85);
      var brim = new T.Mesh(new T.CylinderGeometry(0.27, 0.27, 0.012, 32), straw); brim.position.y = 0.07; head.add(brim);
      var crown = new T.Mesh(new T.CylinderGeometry(0.1, 0.12, 0.1, 24), straw); crown.position.y = 0.12; head.add(crown);
      var band = new T.Mesh(new T.CylinderGeometry(0.121, 0.121, 0.025, 24), suit); band.position.y = 0.085; head.add(band);
    }
    var sc = beach ? 0.97 : 0.9 + r() * 0.16;
    g.scale.setScalar(sc);
    return { g: g, body: body, legL: legL, legR: legR, armL: armL, armR: armR, head: head, r: r, phase: r() * 6, sc: sc };
  }
  // ── 사람 모형: 옷 입은 사람(three.js 예제의 Michelle)에 Xbot의 걷기·서 있기 동작을 옮겨 입힌다 ──
  // Michelle을 못 받으면 Xbot 마네킹으로, 둘 다 못 받으면 위의 단순한 사람으로 그대로 둔다.
  var MODEL_BASE = 'https://cdn.jsdelivr.net/gh/mrdoob/three.js@r175/examples/models/gltf/';
  var HUMAN = { gltf: null, dressed: null, clips: {}, dclips: {}, looks: [], beachMat: null, man: null };
  // 남자 손님(readyplayer.me 예제 모형): 윗옷·바지 색과 수염
  var MAN_LOOKS = [
    { top: null, bottom: null, beard: true }, { top: 0x34445e, bottom: 0x2a2d35, beard: false },
    { top: 0x5a5f66, bottom: 0x1f2126, beard: true }, { top: 0x7b8a6a, bottom: 0x4a4038, beard: false },
    { top: 0x23252b, bottom: 0x23252b, beard: false }, { top: 0x8a4a3a, bottom: 0x3a4352, beard: true },
  ];
  var POSES = [];   // 덧입히는 동작은 쓰지 않는다(반복 끄덕임이 어색함) — 시선은 setLook()으로
  // 손님 옷차림: 바지·윗옷·피부색
  var LOOKS = [
    { pants: 0x2f4a6e, top: 0xf2efe8, skin: 0xe8b996 }, { pants: 0x1e1f22, top: 0x8c2f39, skin: 0xc68a62 },
    { pants: 0xb8a888, top: 0x2d3e57, skin: 0xf1cdb0 }, { pants: 0x4b5a3a, top: 0xd9c9a8, skin: 0x8d5a3b },
    { pants: 0xe8e4dc, top: 0x1d1d1f, skin: 0xe0ac86 }, { pants: 0x3a4352, top: 0x6f8fa8, skin: 0xf3d2b8 },
    { pants: 0x5b4636, top: 0xe9e2d0, skin: 0xd09a72 }, { pants: 0x26324a, top: 0xc9a227, skin: 0xb07650 },
  ];
  function respawn() {   // 지금 층의 사람들을 새 모형으로 다시 세운다
    if (cur < 0 || !floorGroup) return;
    people.forEach(function (q) { floorGroup.remove(q.g); disposeGroup(q.g); });
    parent = floorGroup; spawnPeople(floors[cur], cur + 1); parent = scene; dimEnv(floorGroup);
  }
  // three.js 예제의 Collada 모형: 걷는 스톰트루퍼(뼈대·동작 포함)와 받침대 위 엘프 피규어(정지 모형)
  var COLLADA_BASE = 'https://cdn.jsdelivr.net/gh/mrdoob/three.js@r175/examples/models/collada/';
  function keepShared(root) {   // 층을 바꿀 때 지워도 원본은 남도록 형상·재질을 공용으로 표시
    root.traverse(function (o) {
      if (o.geometry) o.geometry.userData.shared = true;
      (Array.isArray(o.material) ? o.material : (o.material ? [o.material] : [])).forEach(function (m) { m.userData.keep = true; });
    });
  }
  function loadCollada() {
    if (!T.ColladaLoader || !T.SkeletonUtils) return;
    var cl = new T.ColladaLoader();
    cl.load(COLLADA_BASE + 'stormtrooper/stormtrooper.dae', function (c) {
      if (!c.scene.animations || !c.scene.animations.length) return;
      // 동작 트랙이 개체 고유 ID로 묶여 있어 복제본에 붙지 않는다 → 뼈 이름으로 바꿔 묶는다
      var byId = {}; c.scene.traverse(function (o) { byId[o.uuid] = o; });
      var clip = c.scene.animations[0].clone();
      clip.tracks.forEach(function (t) { var i = t.name.indexOf('.'), o = byId[t.name.slice(0, i)]; if (o && o.name) t.name = o.name + t.name.slice(i); });
      keepShared(c.scene); HUMAN.trooper = c.scene; HUMAN.trooperClip = clip; respawn();
    }, undefined, function (e) { console.warn('3D 서재 스톰트루퍼:', e); });
    cl.load(COLLADA_BASE + 'elf/elf.dae', function (c) {
      keepShared(c.scene); HUMAN.elf = c.scene; makeBunnyHair();
      try { HUMAN.elfRig = rigElf(c.scene); if (HUMAN.elfRig) HUMAN.elfRig.geo.userData.shared = true; }
      catch (e) { console.warn('3D 서재 엘프 뼈대:', e); HUMAN.elfRig = null; }   // 못 심으면 받침대째 피규어로
      respawn();
    }, undefined, function (e) { console.warn('3D 서재 엘프:', e); });
  }
  function trooperHuman(r) {   // 총을 든 채 걷는 동작 하나뿐이라 멈추지 않고 계속 순찰한다
    var model = T.SkeletonUtils.clone(HUMAN.trooper);
    model.traverse(function (o) { if (o.isMesh) { o.castShadow = true; o.frustumCulled = false; } });
    var turn = new T.Group(); turn.rotation.y = Math.PI; turn.scale.setScalar(0.4); turn.add(model);   // 모형이 뒤(-Z)를 보고 있어 돌려 세운다
    var g = new T.Group(); g.add(turn);
    var mixer = new T.AnimationMixer(model), walk = mixer.clipAction(HUMAN.trooperClip);
    walk.play(); mixer.update(r() * 3);
    return { g: g, mixer: mixer, acts: { walk: walk }, clips: {}, model: model, r: r, phase: r() * 6, sc: 1, walkW: 1, alwaysWalk: true };
  }
  // ── 엘프에 사람 뼈대 심기: 뼈대 없는 피규어(elf.dae)에 Mixamo식 뼈대를 맞춰 넣고, 다른 손님과 같은 걷기·서 있기 동작을 입힌다 ──
  // 재질: 0 받침대(뗀다) / 1 몸·옷·부츠 / 2 얼굴 / 3 머리카락.
  // 몸은 이어진 덩어리로 나눠 다리(치마 아래)·부츠·소매·손을 찾고, 그 덩어리에서 관절 위치를 잰다.
  function rigElf(src) {
    src.updateMatrixWorld(true);
    var mesh = null; src.traverse(function (o) { if (o.isMesh && !mesh) mesh = o; });
    if (!mesh) return null;
    var g0 = mesh.geometry.index ? mesh.geometry.toNonIndexed() : mesh.geometry.clone();
    g0.applyMatrix4(mesh.matrixWorld);
    var P = g0.attributes.position, n = P.count, i, t;
    var grp = new Int8Array(n);
    g0.groups.forEach(function (gr) { for (var q = gr.start; q < gr.start + gr.count; q++) grp[q] = gr.materialIndex; });
    if (g0.groups.length < 4) return null;
    var floorY = 1e9, topY = -1e9;
    for (i = 0; i < n; i++) if (grp[i] !== 0) { floorY = Math.min(floorY, P.getY(i)); topY = Math.max(topY, P.getY(i)); }
    var h = topY - floorY;
    function Y(q) { return P.getY(q) - floorY; }
    // 같은 자리 꼭짓점 묶기 + 덩어리 나누기
    var key = {}, vid = new Int32Array(n), nid = 0;
    for (i = 0; i < n; i++) {
      var k = Math.round(P.getX(i) * 1e4) + ',' + Math.round(P.getY(i) * 1e4) + ',' + Math.round(P.getZ(i) * 1e4);
      vid[i] = key[k] === undefined ? (key[k] = nid++) : key[k];
    }
    function components(test) {   // test(삼각형 첫 꼭짓점) 통과한 몸 삼각형만으로 이은 덩어리 → 꼭짓점별 덩어리 번호(-1 없음)
      var par = new Int32Array(nid); for (var a = 0; a < nid; a++) par[a] = a;
      function find(a) { while (par[a] !== a) { par[a] = par[par[a]]; a = par[a]; } return a; }
      var ok = new Uint8Array(n);
      for (var tt = 0; tt < n / 3; tt++) {
        var b = tt * 3;
        if (grp[b] !== 1 || !test(b) || !test(b + 1) || !test(b + 2)) continue;
        ok[b] = ok[b + 1] = ok[b + 2] = 1;
        var x = find(vid[b]); par[x] = find(vid[b + 1]); x = find(vid[b + 1]); par[x] = find(vid[b + 2]);
      }
      var out = new Int32Array(n);
      for (var c = 0; c < n; c++) out[c] = ok[c] ? find(vid[c]) : -1;
      return out;
    }
    function stats(comp) {
      var s = {};
      for (var c = 0; c < n; c++) {
        if (comp[c] < 0) continue;
        var q = s[comp[c]] || (s[comp[c]] = { id: comp[c], n: 0, x: 0, y: 0, z: 0, y0: 1e9, y1: -1e9 });
        q.n++; q.x += P.getX(c); q.y += Y(c); q.z += P.getZ(c); q.y0 = Math.min(q.y0, Y(c)); q.y1 = Math.max(q.y1, Y(c));
      }
      return Object.keys(s).map(function (k2) { var q = s[k2]; q.x /= q.n; q.y /= q.n; q.z /= q.n; return q; }).sort(function (a, b) { return b.n - a.n; });
    }
    function centroid(test) {
      var v = new T.Vector3(), c = 0;
      for (var q = 0; q < n; q++) if (test(q)) { v.x += P.getX(q); v.y += Y(q); v.z += P.getZ(q); c++; }
      return c ? v.multiplyScalar(1 / c) : null;
    }
    function band(sel, y, w) {   // sel 꼭짓점 중 높이 y 둘레의 평균 (없으면 띠를 넓혀 다시)
      for (var k2 = 1; k2 < 40; k2 *= 2) {
        var c = centroid(function (q) { return sel(q) && Math.abs(Y(q) - y) < w * k2; });
        if (c) return c;
      }
      return null;
    }
    // 1) 다리: 사타구니(키의 43.5%) 아래 몸 삼각형의 큰 덩어리 둘 = 왼·오른 다리, 부츠는 가까운 다리로
    var crotch = h * 0.435;
    var lowComp = components(function (q) { return Y(q) < crotch; });
    var low = stats(lowComp);
    if (low.length < 2) return null;
    var legIds = [low[0], low[1]].sort(function (a, b) { return b.x - a.x; });   // [0] = +x = 모형의 왼쪽
    var part = new Int8Array(n).fill(-1);   // 0/1 왼·오른 다리, 2/3 왼·오른 팔
    for (i = 0; i < n; i++) {
      if (lowComp[i] === legIds[0].id) part[i] = 0;
      else if (lowComp[i] === legIds[1].id) part[i] = 1;
    }
    low.slice(2).forEach(function (c) {   // 부츠 등: 가까운 다리 쪽으로
      var d0 = Math.hypot(c.x - legIds[0].x, c.z - legIds[0].z), d1 = Math.hypot(c.x - legIds[1].x, c.z - legIds[1].z);
      for (var q = 0; q < n; q++) if (lowComp[q] === c.id) part[q] = d0 < d1 ? 0 : 1;
    });
    // 2) 팔: 어깨 아래 몸 삼각형 덩어리 중 몸통에서 옆으로 떨어진 것(소매·손)
    var armCut = h * 0.68;   // 이보다 높으면 소매가 어깨에서 스웨터와 이어진다
    var upComp = components(function (q) { return Y(q) > crotch * 0.9 && Y(q) < armCut; });
    var mid = centroid(function (q) { return grp[q] === 1 && Y(q) > crotch && Y(q) < h * 0.7; });
    stats(upComp).forEach(function (c) {
      if (c.n < 60 || Math.abs(c.x - mid.x) < h * 0.1 || c.y1 - c.y0 < h * 0.04) return;
      var sd = c.x > mid.x ? 2 : 3;
      for (var q = 0; q < n; q++) if (upComp[q] === c.id && part[q] < 0) part[q] = sd;
    });
    // 3) 관절 위치
    var J = {};
    [0, 1].forEach(function (s) {
      var tag = s === 0 ? 'Left' : 'Right';
      var legTop = centroid(function (q) { return part[q] === s && Y(q) > crotch - h * 0.05 && Y(q) < crotch; });
      var footMin = 1e9; for (var q = 0; q < n; q++) if (part[q] === s) footMin = Math.min(footMin, Y(q));
      var knee = band(function (q) { return part[q] === s; }, footMin + (crotch - footMin) * 0.5, h * 0.015);
      var ankle = band(function (q) { return part[q] === s; }, footMin + h * 0.07, h * 0.012);
      var maxZ = -1e9; for (q = 0; q < n; q++) if (part[q] === s && Y(q) < footMin + h * 0.03) maxZ = Math.max(maxZ, P.getZ(q));
      var toe = centroid(function (q) { return part[q] === s && Y(q) < footMin + h * 0.03 && P.getZ(q) > maxZ - h * 0.03; });
      J[tag + 'UpLeg'] = legTop.setY(crotch - h * 0.01); J[tag + 'Leg'] = knee; J[tag + 'Foot'] = ankle; J[tag + 'ToeBase'] = toe;
    });
    var hipC = J.LeftUpLeg.clone().add(J.RightUpLeg).multiplyScalar(0.5);
    function torsoAt(y) { var c = centroid(function (q) { return grp[q] === 1 && part[q] < 0 && Math.abs(Y(q) - y) < h * 0.012; }); return c || new T.Vector3(hipC.x, y, hipC.z); }
    J.Hips = new T.Vector3(hipC.x, crotch + h * 0.03, hipC.z);
    J.Spine = torsoAt(crotch + h * 0.10);
    J.Spine1 = torsoAt(crotch + h * 0.17);
    J.Spine2 = torsoAt(crotch + h * 0.24);
    var shY = 1e9, armTop = [null, null];
    var cnt = [0, 0, 0, 0]; for (i = 0; i < n; i++) if (part[i] >= 0) cnt[part[i]]++;
    if (cnt[2] < 50 || cnt[3] < 50) { console.warn('엘프 팔을 찾지 못함', cnt); return null; }
    [2, 3].forEach(function (s, j) {
      var top = -1e9; for (var q = 0; q < n; q++) if (part[q] === s) top = Math.max(top, Y(q));
      armTop[j] = top;
    });
    J.Neck = torsoAt(Math.min(h * 0.79, Math.max(armTop[0], armTop[1]) + h * 0.02));
    J.Neck.y = Math.max(J.Neck.y, J.Spine2.y + h * 0.04);
    var face = centroid(function (q) { return grp[q] === 2; });
    var chin = 1e9; for (i = 0; i < n; i++) if (grp[i] === 2) chin = Math.min(chin, Y(i));
    J.Neck.y = Math.max(J.Spine2.y + h * 0.04, chin - h * 0.075);   // 목 밑동
    J.Head = new T.Vector3(face.x, Math.max(J.Neck.y + h * 0.03, chin - h * 0.01), face.z - h * 0.005);   // 머리뼈 밑(턱 높이)
    J.HeadTop_End = new T.Vector3(face.x, h, face.z);
    // 척추는 골반 중심 → 머리 중심(얼굴+머리카락 중 목 위)으로 곧게: 높이별 단면 중심을 쓰면 가슴 때문에 앞으로 굽어
    // 걷기 동작을 옮길 때 상체가 숙여진다(꾸부정)
    var headC = centroid(function (q) { return (grp[q] === 2 || grp[q] === 3) && Y(q) > J.Neck.y + h * 0.02; }) || face;
    ['Spine', 'Spine1', 'Spine2', 'Neck', 'Head', 'HeadTop_End'].forEach(function (nm) {
      var tq = (J[nm].y - J.Hips.y) / (h - J.Hips.y);
      J[nm].x = J.Hips.x + (headC.x - J.Hips.x) * tq; J[nm].z = J.Hips.z + (headC.z - J.Hips.z) * tq;
    });
    [2, 3].forEach(function (s, j) {
      var tag = s === 2 ? 'Left' : 'Right', top = armTop[j];
      var bot = 1e9; for (var q = 0; q < n; q++) if (part[q] === s) bot = Math.min(bot, Y(q));
      var len = top - bot;
      function at(f, w) { return band(function (q) { return part[q] === s; }, top - len * f, len * (w || 0.03)); }
      var sh = at(0.02, 0.04), el = at(0.36), wr = at(0.70), hd = at(0.97, 0.04);
      sh.y += h * 0.035;   // 찾은 팔 윗끝은 어깨보다 조금 아래
      J[tag + 'Arm'] = sh; J[tag + 'ForeArm'] = el; J[tag + 'Hand'] = wr; J[tag + 'HandEnd'] = hd;
      J[tag + 'Shoulder'] = new T.Vector3(J.Spine2.x + (sh.x - J.Spine2.x) * 0.35, sh.y + h * 0.01, J.Spine2.z + (sh.z - J.Spine2.z) * 0.35);
    });
    // 4) 뼈대 (부모, 자식 순서는 동작 옮기기에서 '첫 자식' 방향을 쓰므로 척추→목을 먼저)
    var TREE = [['Hips', null], ['Spine', 'Hips'], ['Spine1', 'Spine'], ['Spine2', 'Spine1'], ['Neck', 'Spine2'], ['Head', 'Neck'], ['HeadTop_End', 'Head'],
                ['LeftShoulder', 'Spine2'], ['LeftArm', 'LeftShoulder'], ['LeftForeArm', 'LeftArm'], ['LeftHand', 'LeftForeArm'],
                ['RightShoulder', 'Spine2'], ['RightArm', 'RightShoulder'], ['RightForeArm', 'RightArm'], ['RightHand', 'RightForeArm'],
                ['LeftUpLeg', 'Hips'], ['LeftLeg', 'LeftUpLeg'], ['LeftFoot', 'LeftLeg'], ['LeftToeBase', 'LeftFoot'],
                ['RightUpLeg', 'Hips'], ['RightLeg', 'RightUpLeg'], ['RightFoot', 'RightLeg'], ['RightToeBase', 'RightFoot']];
    var BI = {}; TREE.forEach(function (b, j) { BI[b[0]] = j; });
    // 5) 무게: 선분(뼈)까지 거리로 고르고, 이웃 뼈와 부드럽게 섞는다
    function segW(p, a, b) { var ab = b.clone().sub(a), tq = Math.max(0, Math.min(1, p.clone().sub(a).dot(ab) / ab.lengthSq())); return { d: p.distanceTo(a.clone().add(ab.multiplyScalar(tq))), t: tq }; }
    function chainW(p, names, ends) {   // 사슬 [뼈들], 각 뼈 선분 = 관절→다음 관절. 가장 가까운 둘을 거리 반비례로
      var best = [];
      for (var c = 0; c < names.length; c++) {
        var r = segW(p, J[names[c]], ends[c]);
        best.push({ b: BI[names[c]], d: r.d });
      }
      best.sort(function (a, b) { return a.d - b.d; });
      var a0 = best[0], a1 = best[1] || best[0], w0 = 1 / Math.pow(a0.d + 1e-4, 4), w1 = 1 / Math.pow(a1.d + 1e-4, 4);
      return [[a0.b, w0 / (w0 + w1)], [a1.b, w1 / (w0 + w1)]];
    }
    var chains = {
      legL: [['LeftUpLeg', 'LeftLeg', 'LeftFoot'], [J.LeftLeg, J.LeftFoot, J.LeftToeBase]],
      legR: [['RightUpLeg', 'RightLeg', 'RightFoot'], [J.RightLeg, J.RightFoot, J.RightToeBase]],
      armL: [['LeftArm', 'LeftForeArm', 'LeftHand'], [J.LeftForeArm, J.LeftHand, J.LeftHandEnd]],
      armR: [['RightArm', 'RightForeArm', 'RightHand'], [J.RightForeArm, J.RightHand, J.RightHandEnd]],
      body: [['Hips', 'Spine', 'Spine1', 'Spine2', 'Neck', 'Head'], [J.Spine, J.Spine1, J.Spine2, J.Neck, J.Head, J.HeadTop_End]]
    };
    function smooth(e0, e1, x) { var tq = Math.max(0, Math.min(1, (x - e0) / (e1 - e0))); return tq * tq * (3 - 2 * tq); }
    var keep = [];
    g0.groups.forEach(function (gr) { if (gr.materialIndex === 0) return; for (var tt = gr.start / 3; tt < (gr.start + gr.count) / 3; tt++) keep.push([tt, gr.materialIndex]); });
    var names = ['position', 'normal', 'uv'].filter(function (nm) { return g0.attributes[nm]; });
    var m = keep.length * 3, arrs = {};
    names.forEach(function (nm) { arrs[nm] = new Float32Array(m * g0.attributes[nm].itemSize); });
    var sIdx = new Uint16Array(m * 4), sW = new Float32Array(m * 4), geo = new T.BufferGeometry(), lastMat = -1, gStart = 0;
    var pv = new T.Vector3();
    keep.forEach(function (kt, j) {
      if (kt[1] !== lastMat) { if (lastMat >= 0) geo.addGroup(gStart, j * 3 - gStart, lastMat); lastMat = kt[1]; gStart = j * 3; }
      for (var v = 0; v < 3; v++) {
        var srcI = kt[0] * 3 + v, dst = j * 3 + v, o = dst * 4;
        names.forEach(function (nm) { var at = g0.attributes[nm], sz = at.itemSize; for (var q = 0; q < sz; q++) arrs[nm][dst * sz + q] = at.array[srcI * sz + q]; });
        pv.set(P.getX(srcI), Y(srcI), P.getZ(srcI));
        var w;
        if (grp[srcI] === 2) w = [[BI.Head, 1]];
        else if (grp[srcI] === 3) {   // 머리카락: 목 위는 머리, 아래로 늘어진 머리는 가슴과 섞는다
          var hw = smooth(J.Neck.y - h * 0.08, J.Neck.y + h * 0.01, pv.y);
          w = [[BI.Head, hw], [BI.Spine2, 1 - hw]];
        } else if (part[srcI] === 0 || part[srcI] === 1) {
          w = chainW(pv, chains[part[srcI] === 0 ? 'legL' : 'legR'][0], chains[part[srcI] === 0 ? 'legL' : 'legR'][1]);
          var hb = smooth(crotch - h * 0.04, crotch, pv.y) * 0.3;   // 사타구니 근처는 골반과 섞기
          if (hb > 0) { w = w.map(function (x) { return [x[0], x[1] * (1 - hb)]; }); w.push([BI.Hips, hb]); }
        } else if (part[srcI] === 2 || part[srcI] === 3) {
          w = chainW(pv, chains[part[srcI] === 2 ? 'armL' : 'armR'][0], chains[part[srcI] === 2 ? 'armL' : 'armR'][1]);
        } else if (pv.y < crotch + h * 0.08) {   // 치마 속 허벅지 윗부분·엉덩이: 골반과 허벅지 중 가까운 쪽과 섞는다
          w = chainW(pv, ['Hips', 'Spine', 'LeftUpLeg', 'RightUpLeg'], [J.Spine, J.Spine1, J.LeftLeg, J.RightLeg]);
        } else if (pv.y > armCut - h * 0.03 && pv.y < J.Neck.y) {   // 어깨 높이(소매 윗부분·어깨 띠): 몸통과 위팔 중 가까운 쪽과 섞는다
          w = chainW(pv, chains.body[0].concat(['LeftArm', 'RightArm']), chains.body[1].concat([J.LeftForeArm, J.RightForeArm]));
        } else {
          w = chainW(pv, chains.body[0], chains.body[1]);
        }
        for (var q2 = 0; q2 < 4; q2++) { sIdx[o + q2] = w[q2] ? w[q2][0] : 0; sW[o + q2] = w[q2] ? w[q2][1] : 0; }
      }
    });
    geo.addGroup(gStart, m - gStart, lastMat);
    names.forEach(function (nm) { geo.setAttribute(nm, new T.BufferAttribute(arrs[nm], g0.attributes[nm].itemSize)); });
    geo.translate(0, -floorY, 0);
    geo.setAttribute('skinIndex', new T.Uint16BufferAttribute(sIdx, 4));
    geo.setAttribute('skinWeight', new T.Float32BufferAttribute(sW, 4));
    geo.computeBoundingSphere();
    var mats = (Array.isArray(mesh.material) ? mesh.material : [mesh.material]).map(function (mt) { var c2 = mt.clone(); c2.skinning = true; c2.userData.keep = true; return c2; });
    return { geo: geo, mats: mats, J: J, tree: TREE, h: h };
  }
  // 묶어 둔 엘프 하나 (뼈대는 사람마다 따로). 반환하는 root는 동작을 붙일 모형 뿌리
  function elfModel(rig) {
    var bones = [], byName = {};
    rig.tree.forEach(function (b) {
      var bone = new T.Bone(); bone.name = b[0]; byName[b[0]] = bone; bones.push(bone);
      var pos = rig.J[b[0]], parentPos = b[1] ? rig.J[b[1]] : new T.Vector3();
      bone.position.copy(pos).sub(parentPos);
      if (b[1]) byName[b[1]].add(bone);
    });
    var sk = new T.SkinnedMesh(rig.geo, rig.mats);
    sk.add(byName.Hips); sk.bind(new T.Skeleton(bones));
    sk.castShadow = true; sk.frustumCulled = false;
    var root = new T.Group(); root.add(sk);
    return root;
  }
  function elfWalker(r) {   // 사람 뼈대를 심은 엘프: 다른 손님과 같은 걷기·서 있기 동작
    if (!HUMAN.elfClips && HUMAN.gltf) {   // Xbot 동작을 엘프 뼈대로 한 번만 옮겨 둔다
      var tmpl = elfModel(HUMAN.elfRig), cl = {};
      ['idle', 'walk'].forEach(function (nm) { if (HUMAN.clips[nm]) cl[nm] = retargetClip(HUMAN.gltf.scene, tmpl, HUMAN.clips[nm]); });
      HUMAN.elfClips = cl;
    }
    var model = elfModel(HUMAN.elfRig); model.scale.setScalar(0.25);
    var g = new T.Group(); g.add(model);
    var mixer = new T.AnimationMixer(model), acts = {};
    ['idle', 'walk'].forEach(function (nm) { if (HUMAN.elfClips[nm]) acts[nm] = mixer.clipAction(HUMAN.elfClips[nm]); });
    if (acts.idle) acts.idle.play();
    if (acts.walk) { acts.walk.play(); acts.walk.setEffectiveWeight(0); }
    mixer.update(r() * 3);
    return { g: g, mixer: mixer, acts: acts, clips: HUMAN.elfClips, model: model, handL: findBone(model, 'LeftHand'), r: r, phase: r() * 6, sc: 1, walkW: 0, isElf: true };
  }
  function elfStatue() {   // 받침대가 붙은 실물 크기 피규어 (뼈대를 못 심었을 때)
    var e = HUMAN.elf.clone();
    e.traverse(function (o) { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
    var g = new T.Group(); e.scale.setScalar(0.25); g.add(e);
    return { g: g, r: rnd(7), phase: 0, kind: 'statue' };
  }
  function loadHumans() {
    loadCollada();
    if (!T.GLTFLoader || !T.SkeletonUtils) return;
    var loader = new T.GLTFLoader();
    loader.load(MODEL_BASE + 'Xbot.glb', function (gltf) {
      gltf.scene.traverse(function (o) { if (o.geometry) o.geometry.userData.shared = true; });
      var raw = {};
      gltf.animations.forEach(function (c) { raw[c.name] = c; HUMAN.clips[c.name] = c; });
      POSES.forEach(function (n) {
        if (raw[n]) { var c = raw[n].clone(); T.AnimationUtils.makeClipAdditive(c); HUMAN.clips[n] = c; }
      });
      HUMAN.gltf = gltf;
      respawn();
      loader.load(MODEL_BASE + 'Michelle.glb', function (dg) {
        try {
          var base = null;
          dg.scene.traverse(function (o) { if (o.geometry) o.geometry.userData.shared = true; if (o.isMesh) base = o.material; });
          ['idle', 'walk'].concat(POSES).forEach(function (n) {
            if (!raw[n]) return;
            var c = retargetClip(gltf.scene, dg.scene, raw[n]);
            if (POSES.indexOf(n) >= 0) T.AnimationUtils.makeClipAdditive(c);
            HUMAN.dclips[n] = c;
          });
          function mat(look) {
            var m = base.clone(); m.map = recolorSkin(base.map.image, look); m.userData.keep = true; return m;
          }
          HUMAN.looks = LOOKS.map(mat);
          var dmesh = null; dg.scene.traverse(function (o) { if (o.isSkinnedMesh && !dmesh) dmesh = o; });
          try {   // 숨은 인물: 옷 그림을 다시 칠하고 선글라스·헤드폰을 뗀 형상
            HUMAN.beachMat = paintBunny(dg, { pants: 0xf0c8a8, top: 0x8e0a1f, skin: 0xf0c8a8, beach: true });
            HUMAN.beachGeo = bunnyGeometry(dmesh);
            var hinfo = michelleHeadInfo(dmesh), hk = [], bi = HUMAN.beachGeo.index;   // 묶은 머리 떼기
            for (var ti = 0; ti < bi.count; ti += 3) if (!hinfo.hair[hinfo.find(bi.getX(ti))]) hk.push(bi.getX(ti), bi.getX(ti + 1), bi.getX(ti + 2));
            HUMAN.beachNoHair = HUMAN.beachGeo.clone(); HUMAN.beachNoHair.setIndex(hk); HUMAN.beachNoHair.userData.shared = true;
            HUMAN.beachHead = { mesh: dmesh, info: hinfo };
            makeBunnyHair();
          } catch (e) {
            console.warn('3D 서재 숨은 인물 옷:', e);
            HUMAN.beachMat = mat({ pants: 0xf0c8a8, top: 0x8e0a1f, skin: 0xf0c8a8, beach: true }); HUMAN.beachGeo = null;
          }
          HUMAN.dressed = dg;
          respawn();
        } catch (e) { console.warn('3D 서재 사람 모형:', e); HUMAN.dressed = null; }
        loader.load(MODEL_BASE + 'readyplayer.me.glb', function (mg) {
          try {
            var mats = {};
            mg.scene.traverse(function (o) { if (o.geometry) o.geometry.userData.shared = true; if (o.isMesh) mats[o.material.name] = o.material; });
            var mclips = {};
            ['idle', 'walk'].concat(POSES).forEach(function (n) {
              if (!raw[n]) return;
              var c = retargetClip(gltf.scene, mg.scene, raw[n]);
              if (POSES.indexOf(n) >= 0) T.AnimationUtils.makeClipAdditive(c);
              mclips[n] = c;
            });
            function suit(name, col) {
              var b = mats[name]; if (!b || col == null) return b;
              var m = b.clone(); if (b.map) m.map = recolorSuit(b.map.image, col); m.userData.keep = true; return m;
            }
            HUMAN.man = { scene: mg.scene, clips: mclips, looks: MAN_LOOKS.map(function (lk) {
              return { top: suit('Wolf3D_Outfit_Top', lk.top), bottom: suit('Wolf3D_Outfit_Bottom', lk.bottom), beard: lk.beard };
            }) };
            respawn();
          } catch (e) { console.warn('3D 서재 사람 모형:', e); HUMAN.man = null; }
        }, undefined, function (e) { console.warn('3D 서재 사람 모형:', e); /* 못 받으면 여자 손님만 */ });
      }, undefined, function (e) { console.warn('3D 서재 사람 모형:', e); /* 못 받으면 마네킹 그대로 */ });
    }, undefined, function (e) { console.warn('3D 서재 사람 모형:', e); /* 못 받으면 단순한 사람 그대로 */ });
  }
  // ── 옷 입은 사람: Michelle(glTF)에 Xbot의 걷기·서 있기 동작을 옮겨 입힌다 ──
  function boneKey(n) { return n.replace(/^mixamorig:?/, ''); }   // Mixamo 접두사를 빼면 readyplayer.me 뼈 이름과 같다
  function boneMap(root) { var o = {}; root.updateMatrixWorld(true); root.traverse(function (b) { if (b.isBone) o[boneKey(b.name)] = b; }); return o; }
  function worldQ(o) { var q = new T.Quaternion(); o.getWorldQuaternion(q); return q; }
  function worldP(o) { var v = new T.Vector3(); o.getWorldPosition(v); return v; }
  // 대상 모형의 기본 자세를 원본(T자)에 맞춘다: 뼈마다 자식 뼈를 향하는 방향을 원본과 같게 돌린다 (A자 → T자)
  function alignRest(S, root) {
    var order = []; root.traverse(function (b) { if (b.isBone) order.push(b); });
    order.forEach(function (db) {
      var sb = S[boneKey(db.name)]; if (!sb) return;
      var dc = null, sc2 = null;
      db.children.forEach(function (c) { if (!dc && c.isBone && S[boneKey(c.name)]) { dc = c; sc2 = S[boneKey(c.name)]; } });
      if (!dc) return;
      root.updateMatrixWorld(true);
      var sd = worldP(sc2).sub(worldP(sb)), dd = worldP(dc).sub(worldP(db));
      if (sd.lengthSq() < 1e-10 || dd.lengthSq() < 1e-10) return;
      var w = new T.Quaternion().setFromUnitVectors(dd.normalize(), sd.normalize()).multiply(worldQ(db));
      db.quaternion.copy(worldQ(db.parent).invert().multiply(w));
    });
    root.updateMatrixWorld(true);
  }
  // 두 모형의 기본 자세 차이를 뼈마다 앞뒤로 보정해 회전 동작만 옮긴다 (위치 이동 트랙은 버림: 제자리 걷기)
  function retargetClip(srcRoot, dstRoot0, clip) {
    var dstRoot = T.SkeletonUtils.clone(dstRoot0);
    var S = boneMap(srcRoot), D = boneMap(dstRoot), tracks = [];
    alignRest(S, dstRoot);
    clip.tracks.forEach(function (tr) {
      var mm = /^(.*)\.quaternion$/.exec(tr.name); if (!mm) return;
      var key = boneKey(mm[1]), sb = S[key], db = D[key]; if (!sb || !db) return;
      var P = worldQ(db.parent).invert().multiply(worldQ(sb.parent)), Q = worldQ(sb).invert().multiply(worldQ(db));
      var v = tr.values.slice(), q = new T.Quaternion();
      for (var i = 0; i < v.length; i += 4) { q.fromArray(v, i); q.premultiply(P).multiply(Q); q.toArray(v, i); }
      tracks.push(new T.QuaternionKeyframeTrack(db.name + '.quaternion', tr.times, v));
    });
    return new T.AnimationClip(clip.name, clip.duration, tracks);
  }
  function hsl2rgb(h, s, l) { var c = new T.Color(); c.setHSL(h, s, l); return [c.r * 255, c.g * 255, c.b * 255]; }
  // 바지(노란색)·윗옷(회색)·피부(갈색)를 골라 다시 칠한 옷 무늬를 만든다
  function recolorSkin(img, look) {
    var w = img.width, h = img.height, cv = document.createElement('canvas'); cv.width = w; cv.height = h;
    var cx = cv.getContext('2d'); cx.drawImage(img, 0, 0);
    var d = cx.getImageData(0, 0, w, h), a = d.data, hsl = {}, col = new T.Color();
    var pants = new T.Color(look.pants).getHSL({}), top = new T.Color(look.top).getHSL({}), skin = new T.Color(look.skin).getHSL({});
    for (var i = 0; i < a.length; i += 4) {
      col.setRGB(a[i] / 255, a[i + 1] / 255, a[i + 2] / 255); col.getHSL(hsl);
      var out = null;
      if (hsl.h > 0.11 && hsl.h < 0.19 && hsl.s > 0.45 && hsl.l > 0.3) {   // 노란 바지
        out = hsl2rgb(pants.h, pants.s, Math.min(0.95, pants.l * hsl.l / 0.55));
      } else if (hsl.s < 0.1 && hsl.l > 0.3 && hsl.l < 0.62) {   // 회색 윗옷
        out = hsl2rgb(top.h, top.s, Math.min(0.95, top.l * hsl.l / 0.45));
      } else if (hsl.h > 0.02 && hsl.h < 0.1 && hsl.s > 0.25 && hsl.s < 0.75 && hsl.l > 0.12 && hsl.l < 0.6) {   // 피부
        out = hsl2rgb(skin.h, skin.s, Math.min(0.95, skin.l * hsl.l / 0.3));
      }
      if (look.beach && hsl.h > 0.45 && hsl.h < 0.56 && hsl.s > 0.3) out = hsl2rgb(skin.h, skin.s, skin.l);   // 바지 무늬 지우기
      if (out) { a[i] = out[0]; a[i + 1] = out[1]; a[i + 2] = out[2]; }
    }
    cx.putImageData(d, 0, 0);
    var tex = new T.CanvasTexture(cv); tex.flipY = false; tex.encoding = T.sRGBEncoding;
    return tex;
  }

  // 갈색 계열(정장·바지)만 골라 다른 색으로 다시 칠한다. 작게 줄여 칠해 빠르게
  function recolorSuit(img, hex) {
    var w = Math.min(512, img.width), h = Math.min(512, img.height), cv = document.createElement('canvas'); cv.width = w; cv.height = h;
    var cx = cv.getContext('2d'); cx.drawImage(img, 0, 0, w, h);
    var d = cx.getImageData(0, 0, w, h), a = d.data, hsl = {}, col = new T.Color(), to = new T.Color(hex).getHSL({});
    for (var i = 0; i < a.length; i += 4) {
      col.setRGB(a[i] / 255, a[i + 1] / 255, a[i + 2] / 255); col.getHSL(hsl);
      if ((hsl.h < 0.11 || hsl.h > 0.97) && hsl.s > 0.08 && hsl.s < 0.65) {
        var out = hsl2rgb(to.h, to.s, Math.min(0.92, to.l * hsl.l / 0.38));
        a[i] = out[0]; a[i + 1] = out[1]; a[i + 2] = out[2];
      }
    }
    cx.putImageData(d, 0, 0);
    var tex = new T.CanvasTexture(cv); tex.flipY = false; tex.encoding = T.sRGBEncoding;
    return tex;
  }
  function findBone(root, name) {
    var re = new RegExp('(^|mixamorig:?)' + name + '$'), hit = null;
    root.traverse(function (o) { if (!hit && o.isBone && re.test(o.name)) hit = o; });
    return hit;
  }
  function onBone(bone, mesh, pos) {   // 뼈대에 붙이는 소품: 뼈대 축척(0.01)을 되돌려 실제 크기로 붙인다
    bone.updateWorldMatrix(true, false);
    var ws = new T.Vector3(); bone.getWorldScale(ws);
    var k = 1 / (ws.x || 1);
    mesh.scale.multiplyScalar(k);
    if (pos) mesh.position.set(pos[0] * k, pos[1] * k, pos[2] * k);
    bone.add(mesh); return mesh;
  }
  var SHIRT = [0x2f3b4c, 0x7a3b3b, 0xd9d3c7, 0x3f5a4a, 0x9b8f7a, 0x2b2e35, 0x5e6f86, 0xb07a4f, 0x6d5a7e, 0xc4b9a6, 0x8a9a6b, 0x34506b];
  function manHuman(r) {
    var model = T.SkeletonUtils.clone(HUMAN.man.scene), lk = HUMAN.man.looks[Math.floor(r() * HUMAN.man.looks.length)];
    model.traverse(function (o) {
      if (!o.isMesh) return;
      o.castShadow = true; o.frustumCulled = false;
      var n = o.material.name;
      if (n === 'Wolf3D_Outfit_Top' && lk.top) o.material = lk.top;
      else if (n === 'Wolf3D_Outfit_Bottom' && lk.bottom) o.material = lk.bottom;
      else if (n === 'Wolf3D_Beard') o.visible = lk.beard;
    });
    var g = new T.Group(); g.add(model);
    var mixer = new T.AnimationMixer(model), acts = {};
    ['idle', 'walk'].forEach(function (n) { if (HUMAN.man.clips[n]) acts[n] = mixer.clipAction(HUMAN.man.clips[n]); });
    if (acts.idle) acts.idle.play();
    if (acts.walk) { acts.walk.play(); acts.walk.setEffectiveWeight(0); }
    mixer.update(r() * 3);
    var sc = 0.96 + r() * 0.08;
    g.scale.setScalar(sc);
    return { g: g, mixer: mixer, acts: acts, clips: HUMAN.man.clips, model: model, handL: findBone(model, 'LeftHand'), r: r, phase: r() * 6, sc: sc, walkW: 0 };
  }
  // ── 숨은 인물 의상: 크리스마스 토끼 (빨간 벨벳 + 흰 털 테두리, 토끼 귀 머리띠, 털 목장식·리본, 손목 커프스, 빨간 망사 스타킹) ──
  var COSTUME = {
    red: new T.MeshStandardMaterial({ color: 0x8e0a1f, roughness: 0.8 }),   // 벨벳 느낌의 짙은 빨강
    fur: new T.MeshStandardMaterial({ color: 0xfbf8f3, roughness: 1 })
  };
  Object.keys(COSTUME).forEach(function (k) { COSTUME[k].userData.keep = true; });
  // ── 숨은 인물 옷 그림: Michelle 옷 그림을 픽셀마다 다시 칠한다 ──
  // 삼각형마다 옷 그림(UV) 안의 픽셀을 훑으며, 그 픽셀이 몸의 어디(기본 자세 높이, 미터)인지 무게중심 좌표로 구해 칠한다.
  // 바지 → 빨간 하의(옆이 높게 파인 모양)+허리 흰 털 / 맨 허벅지 / 빨간 스타킹 윗단 / 망사 스타킹,
  // 윗옷 → 가슴만 가리는 빨간 상의 + 윗단 흰 털, 나머지는 맨살. 원래 그림의 밝기로 주름 음영을 살린다.
  // 헤드폰 조각을 뺀 형상 (이어진 덩어리 단위: 머리 둘레의 빨간 헤드폰. 선글라스는 남김)
  function bunnyGeometry(mesh) {
    var geo = mesh.geometry, P = geo.attributes.position, UV = geo.attributes.uv, idx = geo.index, n = P.count, i;
    var img = mesh.material.map.image, W = img.width, H = img.height, cv = document.createElement('canvas'); cv.width = W; cv.height = H;
    var g = cv.getContext('2d'); g.drawImage(img, 0, 0); var pd = g.getImageData(0, 0, W, H).data;
    var par = new Int32Array(n); for (i = 0; i < n; i++) par[i] = i;
    function f(a) { while (par[a] !== a) { par[a] = par[par[a]]; a = par[a]; } return a; }
    for (var t = 0; t < idx.count; t += 3) { var a = f(idx.getX(t)), b = f(idx.getX(t + 1)), c = f(idx.getX(t + 2)); par[a] = b; par[f(b)] = f(c); }
    var C = {}, col = new T.Color(), hsl = {};
    for (i = 0; i < n; i++) {
      var r = f(i), q = C[r] || (C[r] = { n: 0, red: 0, mn: [9, 9, 9], mx: [-9, -9, -9] });
      q.n++; [P.getX(i), P.getY(i), P.getZ(i)].forEach(function (v, k) { q.mn[k] = Math.min(q.mn[k], v); q.mx[k] = Math.max(q.mx[k], v); });
      var x = Math.min(W - 1, Math.floor(UV.getX(i) * W)), y = Math.min(H - 1, Math.floor(UV.getY(i) * H)), o = (y * W + x) * 4;
      col.setRGB(pd[o] / 255, pd[o + 1] / 255, pd[o + 2] / 255); col.getHSL(hsl);
      if (hsl.s > 0.45 && (hsl.h < 0.14 || hsl.h > 0.93) && hsl.l > 0.25) q.red++;
    }
    function drop(q) {
      // 선글라스(얼굴 앞, z > 0.06)는 남겨 코를 가린다
      return q.mn[1] > 1.36 && q.red / q.n > 0.3 && q.mn[2] < 0.06;                                                 // 헤드폰
    }
    var keep = [];
    for (t = 0; t < idx.count; t += 3) if (!drop(C[f(idx.getX(t))])) keep.push(idx.getX(t), idx.getX(t + 1), idx.getX(t + 2));
    var out = geo.clone(); out.setIndex(keep); out.userData.shared = true;
    return out;
  }
  function paintBunny(dg, look) {
    var mesh = null; dg.scene.traverse(function (o) { if (o.isSkinnedMesh && !mesh) mesh = o; });
    var base = mesh.material, img = base.map.image, W = img.width, H = img.height;
    var src = document.createElement('canvas'); src.width = W; src.height = H;
    var sx = src.getContext('2d'); sx.drawImage(img, 0, 0);
    var px = sx.getImageData(0, 0, W, H).data;
    var tex = recolorSkin(img, look), cx = tex.image.getContext('2d');
    var outD = cx.getImageData(0, 0, W, H), out = outD.data;
    var col = new T.Color(), hsl = {};
    var CL = new Int8Array(W * H), LUM = new Float32Array(W * H);   // 원래 그림의 부위(1 바지·줄무늬·어두운 단, 2 윗옷)와 밝기
    for (var i = 0; i < W * H; i++) {
      col.setRGB(px[i * 4] / 255, px[i * 4 + 1] / 255, px[i * 4 + 2] / 255); col.getHSL(hsl);
      LUM[i] = hsl.l;
      if (hsl.h > 0.0 && hsl.h < 0.11 && hsl.s > 0.2 && hsl.l > 0.04 && hsl.l < 0.6) CL[i] = 4;   // 피부 (짙은 갈색 포함)
      else if ((hsl.h > 0.11 && hsl.h < 0.19 && hsl.s > 0.45 && hsl.l > 0.3) || (hsl.h > 0.45 && hsl.h < 0.56 && hsl.s > 0.3) || hsl.l < 0.3) CL[i] = 1;
      else if (hsl.s < 0.1 && hsl.l > 0.3 && hsl.l < 0.62) CL[i] = 2;
      else if ((hsl.h < 0.05 || hsl.h > 0.93) && hsl.s > 0.55 && hsl.l > 0.25) CL[i] = 3;   // 빨강 (선글라스·헤드폰)
      else if (hsl.h > 0.02 && hsl.h < 0.1 && hsl.s > 0.25 && hsl.s < 0.75 && hsl.l > 0.12 && hsl.l < 0.6) CL[i] = 4;   // 피부
    }
    // 칠할 맨살 색: 다시 칠한 그림에서 원래 피부였던 픽셀의 평균 (팔·얼굴 피부와 같은 톤)
    var fr = [], fl = [];   // 얼굴 피부(코 아래 볼) 색과 밝기
    var rs = [], gs = [], bs = [];   // 맨살 색: 아래팔 꼭짓점 그림 색의 가운데값 (팔과 같은 톤)
    var PP = mesh.geometry.attributes.position, UU = mesh.geometry.attributes.uv;
    for (i = 0; i < PP.count; i++) {
      var ax0 = Math.abs(PP.getX(i)); if (ax0 < 0.32 || ax0 > 0.5 || PP.getY(i) < 1.2 || PP.getY(i) > 1.36) continue;
      var ux = Math.min(W - 1, Math.floor(UU.getX(i) * W)), uy = Math.min(H - 1, Math.floor(UU.getY(i) * H)), up = (uy * W + ux) * 4;
      rs.push(out[up]); gs.push(out[up + 1]); bs.push(out[up + 2]);
    }
    function med(a) { a.sort(function (x, y) { return x - y; }); return a[Math.floor(a.length / 2)] / 255; }
    var skin = rs.length ? new T.Color(med(rs), med(gs), med(bs)) : new T.Color(look.skin), red = new T.Color(0x8e0a1f), fur = new T.Color(0xf7f3ec), netRed = new T.Color(0xa3102a);
    function put(o, c, shade) {
      out[o] = Math.min(255, c.r * 255 * shade); out[o + 1] = Math.min(255, c.g * 255 * shade); out[o + 2] = Math.min(255, c.b * 255 * shade);
    }
    var P = mesh.geometry.attributes.position, UV = mesh.geometry.attributes.uv, idx = mesh.geometry.index;
    // 얼굴 덩어리(머리 높이에서 가장 큰, 앞으로 나온 덩어리) - 눈·눈썹은 따로라 건드리지 않는다
    var par = new Int32Array(P.count); for (var vi = 0; vi < P.count; vi++) par[vi] = vi;
    function fnd(q) { while (par[q] !== q) { par[q] = par[par[q]]; q = par[q]; } return q; }
    for (var ti = 0; ti < idx.count; ti += 3) { var r1 = fnd(idx.getX(ti)), r2 = fnd(idx.getX(ti + 1)), r3 = fnd(idx.getX(ti + 2)); par[r1] = r2; par[fnd(r2)] = fnd(r3); }
    var cs = {};
    for (vi = 0; vi < P.count; vi++) { var rc = fnd(vi), cq = cs[rc] || (cs[rc] = { n: 0, y0: 9, y1: -9, z1: -9 }); cq.n++; cq.y0 = Math.min(cq.y0, P.getY(vi)); cq.y1 = Math.max(cq.y1, P.getY(vi)); cq.z1 = Math.max(cq.z1, P.getZ(vi)); }
    var faceComp = -1, best = 0;
    Object.keys(cs).forEach(function (kk) { var cq = cs[kk]; if (cq.y0 > 1.3 && cq.y1 < 1.6 && cq.z1 > 0.08 && cq.n > best) { best = cq.n; faceComp = +kk; } });
    for (vi = 0; vi < P.count; vi++) {   // 볼·턱(그늘 아래) 그림 색
      if (fnd(vi) !== faceComp || P.getY(vi) < 1.33 || P.getY(vi) > 1.385 || P.getZ(vi) < 0.03) continue;
      var vx = Math.min(W - 1, Math.floor(UV.getX(vi) * W)), vy = Math.min(H - 1, Math.floor(UV.getY(vi) * H)), vp = vy * W + vx;
      fr.push([out[vp * 4], out[vp * 4 + 1], out[vp * 4 + 2]]); fl.push(LUM[vp]);
    }
    fr.sort(function (p1, p2) { return (p1[0] + p1[1] + p1[2]) - (p2[0] + p2[1] + p2[2]); }); fl.sort();
    var faceC = fr.length ? new T.Color(fr[fr.length >> 1][0] / 255, fr[fr.length >> 1][1] / 255, fr[fr.length >> 1][2] / 255) : skin;
    var faceL = fl.length ? fl[fl.length >> 1] : 0.3;
    var tri = idx ? idx.count / 3 : P.count / 3;
    for (var t = 0; t < tri; t++) {
      var a = idx ? idx.getX(t * 3) : t * 3, b = idx ? idx.getX(t * 3 + 1) : t * 3 + 1, c = idx ? idx.getX(t * 3 + 2) : t * 3 + 2;
      var ya = P.getY(a), yb = P.getY(b), yc = P.getY(c);
      if (Math.max(ya, yb, yc) < 0.12) continue;
      var isFace = fnd(a) === faceComp;
      var xa = Math.abs(P.getX(a)), xb = Math.abs(P.getX(b)), xc = Math.abs(P.getX(c));
      var ax = UV.getX(a) * W, ay = UV.getY(a) * H, bx = UV.getX(b) * W, by = UV.getY(b) * H, cxp = UV.getX(c) * W, cyp = UV.getY(c) * H;
      var den = (by - cyp) * (ax - cxp) + (cxp - bx) * (ay - cyp);
      if (Math.abs(den) < 1e-9) continue;
      var x0 = Math.max(0, Math.floor(Math.min(ax, bx, cxp) - 1)), x1 = Math.min(W - 1, Math.ceil(Math.max(ax, bx, cxp) + 1));
      var y0 = Math.max(0, Math.floor(Math.min(ay, by, cyp) - 1)), y1 = Math.min(H - 1, Math.ceil(Math.max(ay, by, cyp) + 1));
      for (var py = y0; py <= y1; py++) for (var pxx = x0; pxx <= x1; pxx++) {
        var qx = pxx + 0.5, qy = py + 0.5;
        var w1 = ((by - cyp) * (qx - cxp) + (cxp - bx) * (qy - cyp)) / den, w2 = ((cyp - ay) * (qx - cxp) + (ax - cxp) * (qy - cyp)) / den, w3 = 1 - w1 - w2;
        if (w1 < -0.02 || w2 < -0.02 || w3 < -0.02) continue;   // 이음매가 비지 않게 살짝 넓게
        var pi = py * W + pxx, k = CL[pi];
        if (!k && !isFace) continue;
        var y = w1 * ya + w2 * yb + w3 * yc, x = w1 * xa + w2 * xb + w3 * xc, o = pi * 4;
        if (isFace) {   // 얼굴: 몸과 같은 맨살 색에 원래 밝기 음영만 (선글라스 그늘은 걷어 낸다), 속눈썹·입술은 그대로
          col.setRGB(px[pi * 4] / 255, px[pi * 4 + 1] / 255, px[pi * 4 + 2] / 255); col.getHSL(hsl);
          if ((LUM[pi] < 0.1 && y > 1.435) || ((hsl.h < 0.03 || hsl.h > 0.9) && hsl.s > 0.35)) continue;
          var shade = LUM[pi] / faceL;
          if (y > 1.385 && y < 1.47) shade = Math.max(0.95, shade);
          put(o, skin, Math.max(0.6, Math.min(1.12, shade))); continue;
        }
        if (k === 4 && y > 1.2) { put(o, skin, Math.max(0.6, Math.min(1.12, LUM[pi] / faceL))); continue; }   // 목·귀 등도 같은 맨살 색
        if (k === 3 || k === 4) continue;
        if (k === 1 && y > 0.12 && y < 1.06 && x < 0.3) {
          var sh = Math.max(0.65, Math.min(1.25, LUM[pi] / 0.5));   // 원래 바지 주름 음영
          var cut = 0.865 + Math.min(1, x / 0.16) * 0.1;            // 하의 아랫선: 가운데 낮고 옆으로 갈수록 높게
          if (y > 1.0) put(o, skin, 1);
          else if (y > 0.975) put(o, fur, Math.min(1, sh));
          else if (y > cut) put(o, red, sh);
          else if (y > 0.70) put(o, skin, 1);
          else if (y > 0.67) put(o, red, sh);
          else {   // 망사: 옷 그림 좌표로 사선 격자
            var g1 = (pxx + py) % 9, g2 = (pxx - py + 900) % 9;
            put(o, g1 < 1.4 || g2 < 1.4 ? netRed : skin, g1 < 1.4 || g2 < 1.4 ? sh : 1);
          }
        } else if (k === 2 && y > 1.0 && y < 1.45) {
          var sh2 = Math.max(0.7, Math.min(1.25, LUM[pi] / 0.45));
          if (y > 1.155 && y < 1.255) put(o, red, sh2);          // 가슴만 가리는 상의
          else if (y >= 1.255 && y < 1.28) put(o, fur, Math.min(1, sh2));
          else put(o, skin, 1);
        }
      }
    }
    cx.putImageData(outD, 0, 0);
    tex.needsUpdate = true;
    var m = base.clone(); m.map = tex; m.userData.keep = true;

    return m;
  }
  // ── 숨은 인물 머리: Michelle의 묶은 머리를 떼고, 엘프의 긴 머리카락을 크기·위치를 맞춰 머리뼈에 붙인다 ──
  function michelleHeadInfo(mesh) {   // 얼굴 덩어리(머리 높이에서 가장 큰, 앞으로 나온) 중심·높이, 떼어 낼 머리카락 덩어리
    var geo = mesh.geometry, P = geo.attributes.position, UV = geo.attributes.uv, idx = geo.index, n = P.count, i, t;
    var img = mesh.material.map.image, W = img.width, H = img.height, cv = document.createElement('canvas'); cv.width = W; cv.height = H;
    var g = cv.getContext('2d'); g.drawImage(img, 0, 0); var pd = g.getImageData(0, 0, W, H).data;
    var par = new Int32Array(n); for (i = 0; i < n; i++) par[i] = i;
    function f(a) { while (par[a] !== a) { par[a] = par[par[a]]; a = par[a]; } return a; }
    for (t = 0; t < idx.count; t += 3) { var a = f(idx.getX(t)), b = f(idx.getX(t + 1)), c = f(idx.getX(t + 2)); par[a] = b; par[f(b)] = f(c); }
    var C = {}, col = new T.Color(), hsl = {};
    for (i = 0; i < n; i++) {
      var r = f(i), q = C[r] || (C[r] = { id: r, n: 0, dark: 0, s: new T.Vector3(), mn: [9, 9, 9], mx: [-9, -9, -9] });
      q.n++; q.s.x += P.getX(i); q.s.y += P.getY(i); q.s.z += P.getZ(i);
      [P.getX(i), P.getY(i), P.getZ(i)].forEach(function (v, k) { q.mn[k] = Math.min(q.mn[k], v); q.mx[k] = Math.max(q.mx[k], v); });
      var x = Math.min(W - 1, Math.floor(UV.getX(i) * W)), y = Math.min(H - 1, Math.floor(UV.getY(i) * H)), o = (y * W + x) * 4;
      col.setRGB(pd[o] / 255, pd[o + 1] / 255, pd[o + 2] / 255); col.getHSL(hsl);
      if (hsl.l < 0.2 && hsl.s < 0.5) q.dark++;
    }
    var face = null;
    Object.keys(C).forEach(function (k) { var q = C[k]; if (q.mn[1] > 1.3 && q.mx[1] < 1.6 && q.mx[2] > 0.08 && (!face || q.n > face.n)) face = q; });
    var hair = {};
    Object.keys(C).forEach(function (k) {   // 머리 높이의 어두운 덩어리 = 머리카락 (눈썹·속눈썹처럼 얼굴 앞에 붙은 것은 남김)
      var q = C[k];
      if (q !== face && q.mx[1] > 1.4 && q.mn[1] > 1.25 && q.dark / q.n > 0.5 && q.mn[2] < 0.03) hair[q.id] = 1;
    });
    return { find: f, hair: hair, center: face.s.clone().multiplyScalar(1 / face.n), h: face.mx[1] - face.mn[1], top: face.mx[1] };
  }
  function elfHairGeometry(src) {   // 엘프 모형에서 머리카락(재질 3)만, 얼굴(재질 2) 기준 중심·높이와 함께
    src.updateMatrixWorld(true);
    var mesh = null; src.traverse(function (o) { if (o.isMesh && !mesh) mesh = o; });
    var g0 = mesh.geometry.index ? mesh.geometry.toNonIndexed() : mesh.geometry.clone();
    g0.applyMatrix4(mesh.matrixWorld);
    var grp = {}; g0.groups.forEach(function (gr) { grp[gr.materialIndex] = gr; });
    if (!grp[2] || !grp[3]) return null;
    var P = g0.attributes.position, fc = new T.Vector3(), fy0 = 1e9, fy1 = -1e9;
    for (var i = grp[2].start; i < grp[2].start + grp[2].count; i++) { fc.x += P.getX(i); fc.y += P.getY(i); fc.z += P.getZ(i); fy0 = Math.min(fy0, P.getY(i)); fy1 = Math.max(fy1, P.getY(i)); }
    fc.multiplyScalar(1 / grp[2].count);
    var hair = new T.BufferGeometry();
    ['position', 'normal', 'uv'].forEach(function (nm) {
      var at = g0.attributes[nm]; if (!at) return;
      hair.setAttribute(nm, new T.BufferAttribute(at.array.slice(grp[3].start * at.itemSize, (grp[3].start + grp[3].count) * at.itemSize), at.itemSize));
    });
    var mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    return { geo: hair, mat: mats[3], center: fc, h: fy1 - fy0 };
  }
  // 엘프 머리카락을 Michelle 머리뼈에 붙일 형상(머리뼈 좌표계)으로
  function bunnyHair(mesh, info, elf) {
    var s = info.h / elf.h, geo = elf.geo.clone();
    geo.translate(-elf.center.x, -elf.center.y, -elf.center.z);
    geo.scale(s, s, s);
    geo.translate(info.center.x, info.center.y + info.h * 0.03, info.center.z - info.h * 0.04);
    var sk = mesh.skeleton, hi = sk.bones.findIndex(function (b) { return /Head$/.test(b.name); });
    geo.applyMatrix4(sk.boneInverses[hi]);   // 기본 자세(형상 공간) → 머리뼈 공간
    geo.computeBoundingSphere(); geo.userData.shared = true;
    var mat = elf.mat.clone(); mat.skinning = false; mat.color = new T.Color(0x3a2216); mat.userData.keep = true;   // 금발을 짙은 갈색으로
    return { geo: geo, mat: mat, bone: sk.bones[hi].name };
  }
  function makeBunnyHair() {   // 엘프와 Michelle이 모두 준비되면 한 번 만든다
    if (HUMAN.bunnyHair || !HUMAN.elf || !HUMAN.beachHead) return;
    try {
      var elf = elfHairGeometry(HUMAN.elf);
      if (elf) HUMAN.bunnyHair = bunnyHair(HUMAN.beachHead.mesh, HUMAN.beachHead.info, elf);
    } catch (e) { console.warn('3D 서재 숨은 인물 머리:', e); }
  }
  function santaBunny(model, hips, head) {
    hips.updateWorldMatrix(true, false);
    var ws = new T.Vector3(); hips.getWorldScale(ws);
    var k = 1 / (ws.x || 1);   // 뼈대 축척(0.01)을 되돌려 미터 단위로 붙인다 (가늘게 줄인 다리 뼈에 붙인 것은 같이 가늘어진다)
    function put(bone, geo, mat, pos, rot, scl) {
      if (!bone) return null;
      var m = new T.Mesh(geo, mat); m.castShadow = true;
      m.scale.setScalar(k); if (scl) m.scale.set(k * scl[0], k * scl[1], k * scl[2]);
      if (pos) m.position.set(pos[0] * k, pos[1] * k, pos[2] * k);
      if (rot) m.rotation.set(rot[0], rot[1], rot[2]);
      bone.add(m); return m;
    }
    function len(bone) { var c = bone && bone.children.filter(function (x) { return x.isBone; })[0]; return c ? c.position.length() / k : 0.3; }
    // 헐렁한 바지 몸매를 맨다리·좁은 골반으로 (자식 뼈에서 축척을 되돌려 몸통·발은 그대로)
    var spine = findBone(model, 'Spine');
    hips.scale.set(0.82, 1, 0.85); if (spine) spine.scale.set(1 / 0.82, 1, 1 / 0.85);
    ['Left', 'Right'].forEach(function (sd) {
      var up = findBone(model, sd + 'UpLeg'), lg = findBone(model, sd + 'Leg'), ft = findBone(model, sd + 'Foot');
      if (up) up.scale.set(0.62 / 0.82, 1, 0.62 / 0.85);
      if (lg) lg.scale.set(0.72, 1, 0.72);
      if (ft) ft.scale.set(1 / (0.62 * 0.72), 1, 1 / (0.62 * 0.72));
    });
    var spine2 = findBone(model, 'Spine2'), neck = findBone(model, 'Neck');
    // 토끼 귀 머리띠
    put(head, new T.TorusGeometry(0.1, 0.008, 6, 24, Math.PI), COSTUME.red, [0, 0.15, 0.01]);
    [-1, 1].forEach(function (sd) {
      var ear = put(head, new T.SphereGeometry(1, 16, 12), COSTUME.fur, [sd * 0.055, 0.31, 0], [0, 0, -sd * 0.22], [0.034, 0.12, 0.016]);
      if (ear) put(head, new T.SphereGeometry(1, 16, 12), COSTUME.red, [sd * 0.057, 0.30, 0.009], [0, 0, -sd * 0.22], [0.02, 0.095, 0.01]);
    });
    // 털 목장식 + 빨간 리본
    put(neck, new T.TorusGeometry(0.047, 0.013, 8, 24), COSTUME.fur, [0, 0.055, 0.008], [Math.PI / 2, 0, 0]);
    [-1, 1].forEach(function (sd) { put(neck, new T.SphereGeometry(1, 10, 8), COSTUME.red, [sd * 0.013, 0.04, 0.058], [0, 0, sd * 0.6], [0.015, 0.009, 0.007]); });
    // 상의·하의·스타킹은 옷 그림을 다시 칠해 표현한다 (paintBunny)
    // 손목 커프스 (아래팔 끝)
    ['Left', 'Right'].forEach(function (sd) {
      var fa = findBone(model, sd + 'ForeArm'), L = len(fa);
      put(fa, new T.CylinderGeometry(0.036, 0.033, 0.07, 16), COSTUME.red, [0, L * 0.86, 0]);
      put(fa, new T.TorusGeometry(0.037, 0.012, 8, 20), COSTUME.fur, [0, L * 0.8, 0], [Math.PI / 2, 0, 0]);
    });
  }
  function dressedHuman(seed, beach) {
    var r = rnd(seed * 7919 + 13);
    if (!beach && HUMAN.man && r() < 0.5) return manHuman(r);
    var model = T.SkeletonUtils.clone(HUMAN.dressed.scene);
    var mat = beach ? HUMAN.beachMat : HUMAN.looks[Math.floor(r() * HUMAN.looks.length)];
    model.traverse(function (o) {
      if (!o.isMesh) return;
      o.material = mat; o.castShadow = true; o.frustumCulled = false;
      if (beach && HUMAN.beachGeo && o.isSkinnedMesh) o.geometry = HUMAN.bunnyHair ? HUMAN.beachNoHair : HUMAN.beachGeo;
    });
    var g = new T.Group(); g.add(model);
    var head = findBone(model, 'Head'), hips = findBone(model, 'Hips'), handL = findBone(model, 'LeftHand');
    if (beach && hips && head) {
      santaBunny(model, hips, head);
      if (HUMAN.bunnyHair) {   // 엘프 머리 모양의 긴 갈색 머리
        var hb = null; model.traverse(function (o) { if (o.isBone && o.name === HUMAN.bunnyHair.bone) hb = o; });
        if (hb) { var hm = new T.Mesh(HUMAN.bunnyHair.geo, HUMAN.bunnyHair.mat); hm.castShadow = true; hm.frustumCulled = false; hb.add(hm); }
      }
    }
    var mixer = new T.AnimationMixer(model), acts = {};
    ['idle', 'walk'].forEach(function (n) { if (HUMAN.dclips[n]) acts[n] = mixer.clipAction(HUMAN.dclips[n]); });
    if (acts.idle) acts.idle.play();
    if (acts.walk) { acts.walk.play(); acts.walk.setEffectiveWeight(0); }
    mixer.update(r() * 3);
    var sc = beach ? 1.04 : 0.98 + r() * 0.1;
    g.scale.setScalar(sc);
    return { g: g, mixer: mixer, acts: acts, clips: HUMAN.dclips, model: model, handL: handL, r: r, phase: r() * 6, sc: sc, walkW: 0 };
  }
  function human(seed, beach) {
    if (HUMAN.dressed) return dressedHuman(seed, beach);
    var r = rnd(seed * 7919 + 13), pick = function (a) { return a[Math.floor(r() * a.length)]; };
    var model = T.SkeletonUtils.clone(HUMAN.gltf.scene);
    var bodyCol = beach ? 0xf0c4a0 : pick(SHIRT), jointCol = beach ? 0xe2b18b : pick(PANTS);
    model.traverse(function (o) {
      if (!o.isMesh) return;
      o.castShadow = true; o.frustumCulled = false;
      var joint = /Joints/i.test(o.material.name);
      var m = new T.MeshStandardMaterial({ color: joint ? jointCol : bodyCol, roughness: beach ? 0.55 : (joint ? 0.6 : 0.85),
        metalness: 0, skinning: true });
      o.material = m;
    });
    var g = new T.Group(); g.add(model);
    var head = findBone(model, 'Head'), spine = findBone(model, 'Spine2'), hips = findBone(model, 'Hips'),
        handL = findBone(model, 'LeftHand');
    var hairM = std(beach ? 0x5a3a22 : pick(HAIR), 0.9);
    if (head && (beach || r() < 0.75)) {   // 머리카락
      var cap = new T.Mesh(new T.SphereGeometry(0.108, 22, 14, 0, Math.PI * 2, 0, Math.PI * 0.55), hairM);
      cap.rotation.x = -0.2; onBone(head, cap, [0, 0.11, -0.01]);
      if (beach || r() < 0.35) {   // 긴 머리
        var lg = new T.Mesh(new T.CylinderGeometry(0.095, 0.06, beach ? 0.36 : 0.26, 16), hairM);
        onBone(head, lg, [0, beach ? -0.02 : 0.02, -0.075]);
      }
    }
    if (beach && spine && hips && head) {   // 숨은 인물: 빨간 비키니와 밀짚모자
      var suit = std(0xe2465a, 0.45);
      var top = new T.Mesh(new T.CylinderGeometry(0.135, 0.14, 0.09, 24), suit); top.scale.z = 0.85; onBone(spine, top, [0, 0.115, 0.015]);
      var bot = new T.Mesh(new T.CylinderGeometry(0.15, 0.13, 0.1, 24), suit); bot.scale.z = 0.8; onBone(hips, bot, [0, -0.065, 0]);
      var straw = std(0xe9d29a, 0.85);
      var brim = new T.Mesh(new T.CylinderGeometry(0.26, 0.26, 0.012, 32), straw); onBone(head, brim, [0, 0.135, 0]);
      var crown = new T.Mesh(new T.CylinderGeometry(0.1, 0.12, 0.1, 24), straw); onBone(head, crown, [0, 0.185, 0]);
      var band = new T.Mesh(new T.CylinderGeometry(0.121, 0.121, 0.025, 24), suit); onBone(head, band, [0, 0.15, 0]);
    }
    var mixer = new T.AnimationMixer(model), acts = {};
    ['idle', 'walk'].forEach(function (n) { if (HUMAN.clips[n]) acts[n] = mixer.clipAction(HUMAN.clips[n]); });
    if (acts.idle) acts.idle.play();
    if (acts.walk) { acts.walk.play(); acts.walk.setEffectiveWeight(0); }
    mixer.update(r() * 3);   // 모두 같은 박자로 움직이지 않게
    var sc = beach ? 1.0 : 0.93 + r() * 0.12;
    g.scale.setScalar(sc);
    return { g: g, mixer: mixer, acts: acts, clips: HUMAN.clips, model: model, handL: handL, r: r, phase: r() * 6, sc: sc, walkW: 0 };
  }
  // 서 있는 사람의 시선: 반복 끄덕임 동작 대신 머리 뼈를 천천히 돌린다
  // read: 고개를 숙이고 책을 본다 / browse: 서가를 따라 천천히 둘러본다 / calm: 가끔 주변을 본다
  function setLook(p, kind) {
    if (!p.mixer) return;
    p.look = kind; p.headBone = p.headBone || findBone(p.model, 'Head'); p.neckBone = p.neckBone || findBone(p.model, 'Neck');
  }
  function applyLook(p, now) {
    if (!p.look || !p.headBone || p.walkW > 0.5) return;
    var t = now / 1000 + p.phase * 7, pitch = 0, yaw = 0;
    if (p.look === 'read') { pitch = 0.42 + Math.sin(t * 0.35) * 0.03; yaw = Math.sin(t * 0.13) * 0.06; }
    else if (p.look === 'browse') {   // 몇 초씩 한곳을 보다가 천천히 옮긴다
      var s = Math.sin(t * 0.18) + 0.35 * Math.sin(t * 0.07 + 1.3);
      yaw = Math.max(-1, Math.min(1, s * 1.6)) * 0.45; pitch = 0.12 + Math.sin(t * 0.11 + 0.7) * 0.06;
    } else { yaw = Math.sin(t * 0.09) * 0.3; pitch = 0.04; }
    var k = 1 - p.walkW * 2;
    if (p.neckBone) { p.neckBone.rotateY(yaw * 0.4 * k); p.neckBone.rotateX(pitch * 0.4 * k); }
    p.headBone.rotateY(yaw * 0.6 * k); p.headBone.rotateX(pitch * 0.6 * k);
  }
  function carryBook(p) {   // 왼손에 든 책
    if (!p.handL) return;
    var bk = new T.Mesh(new T.BoxGeometry(0.16, 0.23, 0.03), [M.white, M.white, M.white, M.white,
      std(PALETTE[Math.floor(p.r() * PALETTE.length)], 0.6), std(PALETTE[Math.floor(p.r() * PALETTE.length)], 0.6)]);
    bk.rotation.y = Math.PI / 2;
    onBone(p.handL, bk, [0.02, 0.09, 0.03]);
  }
  function makePerson(seed, beach) { return HUMAN.gltf ? human(seed, beach) : person(seed, beach); }

  function heldBook(p) {   // 가슴 앞에 펼쳐 든 책
    var bk = new T.Mesh(new T.BoxGeometry(0.32, 0.22, 0.03), [M.white, M.white, M.white, M.white, std(PALETTE[Math.floor(p.r() * PALETTE.length)], 0.6), M.white]);
    bk.position.set(0, 1.22, 0.3); bk.rotation.x = -0.9; (p.body || p.g).add(bk);
    if (p.mixer) { bk.parent.remove(bk); carryBook(p); setLook(p, 'read'); return; }
    p.armL.rotation.set(-1.15, 0, 0.25); p.armR.rotation.set(-1.15, 0, -0.25);
    p.head.rotation.x = 0.35;
  }

  // 층별 인물 수 ([설정 > 인물 수], lib3d.json의 people.{층 키}.{종류}) - 비우면 자동
  var PEOPLE = {};
  var PEOPLE_KINDS = [
    { k: 'walk', label: '걷는 손님' }, { k: 'browse', label: '책 고르는 손님' }, { k: 'read', label: '서서 읽는 손님' },
    { k: 'sit', label: '벤치 손님' }, { k: 'chat', label: '대화하는 손님(쌍)' }, { k: 'staff', label: '안내 직원' },
    { k: 'trooper', label: '스톰트루퍼' }, { k: 'elf', label: '엘프' }, { k: 'beach', label: '숨은 인물(산타 토끼)' },
  ];
  var PEOPLE_MAX = 20;
  function spawnPeople(fl, seed) {
    people = [];
    chatPair = null;
    if (!layout) return;
    var r = rnd(seed + 99), L = layout, n = 0, secs = L.sections || [];
    var cfg = PEOPLE[fl.key] || {};
    function cnt(kind, auto) {   // 저장한 수가 있으면 그 수, 없으면 자동
      var v = cfg[kind];
      return (typeof v === 'number' && v >= 0) ? Math.min(PEOPLE_MAX, v) : auto;
    }
    function place(p, x, z, ry) { p.g.position.set(x, 0, z); p.g.rotation.y = ry; parent.add(p.g); people.push(p); n++; return p; }
    // 통로 격자 (서가 사이 세로 통로 x, 서가 줄 앞 가로 통로 z, 로비)
    var lanes = [], rowsZ = [L.front - 6.5];
    for (var c = 0; c <= L.cols; c++) lanes.push((c - L.cols / 2) * (BOOTH_W + GAP));
    for (var rr = 0; rr < L.rows; rr++) rowsZ.push(-LOBBY + GAP / 2 - rr * (BOOTH_D + GAP));
    L.lanes = lanes; L.rowsZ = rowsZ;
    function walker(p, speed, row) {   // 통로를 걷는 사람으로 세운다
      var li = Math.floor(r() * lanes.length), zi = row === undefined ? Math.floor(r() * rowsZ.length) : Math.min(row, rowsZ.length - 1);
      p.kind = 'walk'; p.node = [li, zi]; p.speed = speed;
      place(p, lanes[li], rowsZ[zi], 0);
      nextNode(p);
      return p;
    }
    // 정한 수만큼 구역을 고른다 (자동이면 구역마다 확률로)
    function pickSections(kind, chance) {
      var out = [];
      if (!secs.length) return out;
      var v = cnt(kind, -1);
      if (v < 0) { secs.forEach(function (s, j) { if (r() < chance) out.push([s, j]); }); return out; }
      var start = Math.floor(r() * secs.length);
      for (var q = 0; q < v; q++) out.push([secs[(start + q) % secs.length], q]);
      return out;
    }
    var i;
    // 걷는 손님
    var walkers = cnt('walk', Math.min(5, 2 + Math.floor(fl.libs.length / 2)));
    for (i = 0; i < walkers; i++) walker(makePerson(seed * 31 + i), 0.95 + r() * 0.45);
    // 서가 앞에서 고르는 손님 (평대 앞 또는 옆 서가 앞)
    pickSections('browse', 0.3).forEach(function (sj, q) {
      var s = sj[0], p2 = makePerson(seed * 53 + sj[1] + 400 + q * 7);
      p2.kind = 'browse'; p2.t = r() * 4;
      if (p2.mixer) { setLook(p2, 'browse'); if (r() < 0.4) carryBook(p2); }
      if (r() < 0.5) place(p2, s.x + (r() - 0.5) * 2.4, s.z + 3.15, Math.PI);
      else place(p2, s.x - BOOTH_W / 2 + 1.05, s.z - 0.2 + (r() - 0.5) * 3, Math.PI / 2);
    });
    // 서서 읽는 손님
    pickSections('read', 0.12).forEach(function (sj, q) {
      var s = sj[0], p3 = makePerson(seed * 71 + sj[1] + 800 + q * 7);
      p3.kind = 'read'; place(p3, s.x + BOOTH_W / 2 - 1.2, s.z + 2.6 - Math.floor(q / secs.length) * 1.4, -Math.PI / 2 - 0.4); heldBook(p3);
    });
    // 벤치 손님 (관절 모형은 벤치 옆에 서서 읽는다)
    var sits = cnt('sit', 1);
    for (i = 0; i < sits; i++) {
      var sit = makePerson(seed * 97 + 5 + i * 11);
      if (sit.mixer) {
        sit.kind = 'read'; place(sit, -1.6 - i * 0.9, L.front - 2.6, Math.PI + 0.5); heldBook(sit);
      } else {
        sit.kind = 'sit'; place(sit, -2.8 + (i % 3) * 0.75, L.front - 3.25, Math.PI);
        sit.body.position.y = -0.47; sit.legL.rotation.x = -1.5; sit.legR.rotation.x = -1.5; heldBook(sit);
      }
    }
    // 숨은 인물: 자동이면 층에 들어올 때 가끔(약 3번에 1번)
    var beach = cnt('beach', r() < 0.34 ? 1 : 0);
    for (i = 0; i < beach; i++) { var bk = walker(makePerson(seed * 101 + 3 + i * 13, true), 1.25, 0); bk.hidden = true; }
    // 책 이야기를 나누는 두 손님: 서가 입구 쪽에서 마주 본다 (AI 손님 대화가 켜지면 첫 쌍이 말풍선으로 이야기)
    var pairs = secs.length ? cnt('chat', AI.chat ? 1 : 0) : 0, pstart = Math.floor(r() * Math.max(1, secs.length));
    for (i = 0; i < pairs; i++) {
      var cs = secs[(pstart + i) % secs.length], dz = Math.floor(i / secs.length) * 1.6;
      var ca = makePerson(seed * 151 + 11 + i * 17), cb = makePerson(seed * 157 + 13 + i * 17);
      ca.kind = 'chat'; cb.kind = 'chat';
      place(ca, cs.x + 2.3, cs.z + 3.3 - dz, Math.PI / 2 + 0.3);
      place(cb, cs.x + 3.3, cs.z + 3.3 - dz, -Math.PI / 2 - 0.3);
      if (!chatPair) chatPair = [ca, cb];
    }
    // 스톰트루퍼: 통로를 순찰
    if (HUMAN.trooper) {
      var troops = cnt('trooper', 1);
      for (i = 0; i < troops; i++) walker(trooperHuman(rnd(seed * 131 + 9 + i * 19)), 0.85, i === 0 ? 1 : undefined);
    }
    // 엘프: 로비에서 시작해 통로를 걷는다 (뼈대를 못 심었으면 로비에 피규어로)
    var elves = cnt('elf', 1);
    for (i = 0; i < elves; i++) {
      if (HUMAN.elfRig && HUMAN.gltf) walker(elfWalker(rnd(seed * 163 + 17 + i * 23)), 1.0, i === 0 ? 0 : undefined);
      else if (HUMAN.elf) place(elfStatue(), 4 + i * 1.6, L.front - 8.5, -0.3);
    }
    // 안내 데스크 직원
    var staffs = cnt('staff', 1);
    for (i = 0; i < staffs; i++) {
      var staff = makePerson(seed * 13 + 7 + i * 29);
      staff.kind = 'staff'; place(staff, L.w / 2 - 5.5 - i * 1.1, L.front - 6.35, 0);
      if (staff.mixer) setLook(staff, 'calm');
    }
  }

  function nextNode(p) {
    var L = layout, li = p.node[0], zi = p.node[1], opts = [];
    if (li > 0) opts.push([li - 1, zi]);
    if (li < L.lanes.length - 1) opts.push([li + 1, zi]);
    if (zi > 0) opts.push([li, zi - 1]);
    if (zi < L.rowsZ.length - 1) opts.push([li, zi + 1]);
    if (p.prev && opts.length > 1) opts = opts.filter(function (o) { return o[0] !== p.prev[0] || o[1] !== p.prev[1]; });
    var o = opts[Math.floor(p.r() * opts.length)];
    p.prev = p.node; p.node = o;
    p.tx = L.lanes[o[0]] + (p.r() - 0.5) * 1.2; p.tz = L.rowsZ[o[1]] + (p.r() - 0.5) * 1.2;
    if (!p.alwaysWalk && p.r() < 0.18) p.pause = 1 + p.r() * 3;   // 가끔 멈춰 두리번
  }

  function updateHuman(p, dt, now) {
    var moving = false;
    if (p.kind === 'walk') {
      if (p.pause > 0) p.pause -= dt;
      else {
        var dx = p.tx - p.g.position.x, dz = p.tz - p.g.position.z, d = Math.hypot(dx, dz);
        if (d < 0.15) nextNode(p);
        else {
          moving = true;
          var want = Math.atan2(dx, dz), cur0 = p.g.rotation.y, diff = Math.atan2(Math.sin(want - cur0), Math.cos(want - cur0));
          p.g.rotation.y = cur0 + diff * Math.min(1, dt * 5);
          var stepLen = Math.min(d, p.speed * dt * p.walkW);
          p.g.position.x += dx / d * stepLen; p.g.position.z += dz / d * stepLen;
        }
      }
    }
    // 걷기 ↔ 서 있기를 부드럽게 섞는다
    if (p.alwaysWalk) { p.mixer.update(dt * 0.9); return; }
    p.walkW += ((moving ? 1 : 0) - p.walkW) * Math.min(1, dt * 4);
    if (p.acts.walk) { p.acts.walk.setEffectiveWeight(p.walkW); p.acts.walk.timeScale = p.speed / 1.25; }
    if (p.acts.idle) p.acts.idle.setEffectiveWeight(1 - p.walkW);
    p.mixer.update(dt);
    applyLook(p, now);
  }

  function updatePeople(dt, now) {
    for (var i = 0; i < people.length; i++) {
      var p = people[i];
      if (p.mixer) { updateHuman(p, dt, now); continue; }
      if (p.kind === 'walk') {
        if (p.pause > 0) {
          p.pause -= dt;
          p.legL.rotation.x *= 0.85; p.legR.rotation.x *= 0.85; p.armL.rotation.x *= 0.85; p.armR.rotation.x *= 0.85;
          p.head.rotation.y = Math.sin(now / 700 + p.phase) * 0.6;
          continue;
        }
        var dx = p.tx - p.g.position.x, dz = p.tz - p.g.position.z, d = Math.hypot(dx, dz);
        if (d < 0.15) { nextNode(p); continue; }
        var want = Math.atan2(dx, dz), cur = p.g.rotation.y, diff = Math.atan2(Math.sin(want - cur), Math.cos(want - cur));
        p.g.rotation.y = cur + diff * Math.min(1, dt * 6);
        var stepLen = Math.min(d, p.speed * dt);
        p.g.position.x += dx / d * stepLen; p.g.position.z += dz / d * stepLen;
        p.phase += dt * p.speed * 5.2;
        var sw = Math.sin(p.phase);
        p.legL.rotation.x = sw * 0.5; p.legR.rotation.x = -sw * 0.5;
        p.armL.rotation.x = -sw * 0.38; p.armR.rotation.x = sw * 0.38;
        p.body.position.y = Math.abs(Math.cos(p.phase)) * 0.025;
        p.head.rotation.y *= 0.9;
      } else if (p.kind === 'browse') {   // 책장을 훑어보다 가끔 손을 뻗는다
        p.t += dt;
        p.head.rotation.y = Math.sin(now / 1500 + p.phase) * 0.45;
        p.head.rotation.x = 0.1 + Math.sin(now / 2300 + p.phase) * 0.12;
        var reach = Math.max(0, Math.sin(p.t * 0.6 + p.phase)) ;
        p.armR.rotation.x = -reach * 1.25;
        p.body.rotation.y = Math.sin(now / 4000 + p.phase) * 0.08;
      } else if (p.kind === 'read' || p.kind === 'sit') {   // 숨쉬기·고개 끄덕임
        p.body.rotation.x = Math.sin(now / 1800 + p.phase) * 0.015;
        p.head.rotation.y = Math.sin(now / 3000 + p.phase) * 0.12;
      } else if (p.kind === 'staff') {
        p.head.rotation.y = Math.sin(now / 2600 + p.phase) * 0.5;
      }
    }
  }

  // ── 이동·시점 ──
  var yaw = 0, pitch = 0, keys = {}, moveStick = { x: 0, y: 0 };
  function home() { camera.position.set(0, EYE, 9); yaw = 0; pitch = 0.1; }
  // 나갔던 자리 기억 (이 브라우저에): 층·위치·시선. 다음에 들어오면 그 자리에서 시작
  var POS_KEY = 'l3d_pos', posRestored = false, posSavedAt = 0;
  function savePos() {
    if (cur < 0 || !floors[cur]) return;
    try {
      localStorage.setItem(POS_KEY, JSON.stringify({ floor: floors[cur].key, x: +camera.position.x.toFixed(2), z: +camera.position.z.toFixed(2),
                                                     yaw: +yaw.toFixed(3), pitch: +pitch.toFixed(3) }));
    } catch (e) { /* 저장 못 하면 다음에 입구에서 시작 */ }
  }
  function restorePos() {   // 처음 지을 때 한 번: 저장한 층을 짓고 그 자리로. 못 하면 false
    var p = null;
    try { p = JSON.parse(localStorage.getItem(POS_KEY) || 'null'); } catch (e) { p = null; }
    if (!p || typeof p.x !== 'number') return false;
    var idx = floors.map(function (f) { return f.key; }).indexOf(p.floor);
    if (idx < 0) return false;
    buildFloor(idx);
    if (p.x < hall.x0 || p.x > hall.x1 || p.z < hall.z0 || p.z > hall.z1) { home(); return true; }   // 서가 배치가 바뀌어 밖이면 입구로
    camera.position.set(p.x, EYE, p.z); yaw = p.yaw || 0; pitch = p.pitch || 0;
    return true;
  }
  window.addEventListener('pagehide', savePos);
  document.addEventListener('visibilitychange', function () { if (document.visibilityState === 'hidden') savePos(); });
  function teleport(b) {
    if (b.floor !== cur) buildFloor(b.floor);
    camera.position.set(b.x, EYE, b.z + BOOTH_D / 2 + 3.8); yaw = 0; pitch = -0.05; closeMap();
  }
  var reading = false;
  window.addEventListener('keydown', function (e) {
    if (e.target && /input|textarea|select/i.test(e.target.tagName)) return;
    if (reading) { readerKey(e); return; }
    keys[e.key.toLowerCase()] = true;
    if (['arrowup', 'arrowdown', 'arrowleft', 'arrowright', ' '].indexOf(e.key.toLowerCase()) >= 0) e.preventDefault();
  });
  window.addEventListener('keyup', function (e) { keys[e.key.toLowerCase()] = false; });
  window.addEventListener('blur', function () { keys = {}; });

  var drag = null;
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
      yaw -= dx * 0.004;
      pitch = Math.max(-1.1, Math.min(1.1, pitch - dy * 0.0035));
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

  var vel = new T.Vector2();
  function step(dt) {
    var f = 0, s = 0;
    if (!reading) {
      if (keys.w || keys.arrowup) f += 1;
      if (keys.s || keys.arrowdown) f -= 1;
      if (keys.a) s -= 1;
      if (keys.d) s += 1;
      if (keys.arrowleft) yaw += dt * 1.6;
      if (keys.arrowright) yaw -= dt * 1.6;
      f -= moveStick.y; s += moveStick.x;
    }
    var speed = keys.shift ? 7 : 3.4;
    var sin = Math.sin(yaw), cos = Math.cos(yaw);
    var tx = (-sin * f + cos * s) * speed, tz = (-cos * f - sin * s) * speed;
    vel.x += (tx - vel.x) * Math.min(1, dt * 8);     // 부드럽게 출발·멈춤
    vel.y += (tz - vel.y) * Math.min(1, dt * 8);
    camera.position.x = Math.max(hall.x0, Math.min(hall.x1, camera.position.x + vel.x * dt));
    camera.position.z = Math.max(hall.z0, Math.min(hall.z1, camera.position.z + vel.y * dt));
    var moving = Math.hypot(vel.x, vel.y);
    camera.position.y = EYE + Math.sin(performance.now() / 160) * 0.012 * Math.min(1, moving / 3);   // 걸음 흔들림
    camera.rotation.set(pitch, yaw, 0, 'YXZ');
  }

  // ── 표지·책등 글자: 가까운 책만 ──
  var loading = 0, MAX_LOAD = 6, NEAR = 9;
  var tmp = new T.Vector3(), loader = new T.TextureLoader();
  function spineTex(b) {
    var hex = '#' + new T.Color(b.base).getHexString();
    return canvasTex(96, 768, function (g, w, h) {
      g.fillStyle = hex; g.fillRect(0, 0, w, h);
      g.fillStyle = 'rgba(255,255,255,0.08)'; g.fillRect(0, 40, w, 6); g.fillRect(0, h - 46, w, 6);
      g.save(); g.translate(w / 2, h / 2); g.rotate(Math.PI / 2);
      g.fillStyle = inkOn(b.base); g.textAlign = 'center'; g.textBaseline = 'middle';
      g.font = '700 46px ' + FONT;
      g.fillText(b.title, 0, 0, h - 120);
      g.restore();
    });
  }
  function titleCover(b) {
    var hex = '#' + new T.Color(b.base).getHexString(), ink = inkOn(b.base);
    b.front.map = canvasTex(300, 420, function (g, w, h) {
      g.fillStyle = hex; g.fillRect(0, 0, w, h);
      g.fillStyle = ink; g.globalAlpha = 0.25; g.fillRect(24, 24, w - 48, 3); g.fillRect(24, h - 60, w - 48, 3); g.globalAlpha = 1;
      g.textAlign = 'center'; g.textBaseline = 'middle';
      var words = String(b.title), lines = [];
      while (words && lines.length < 5) { lines.push(words.slice(0, 8)); words = words.slice(8); }
      g.font = '700 34px ' + FONT;
      lines.forEach(function (ln, i) { g.fillText(ln, w / 2, 110 + i * 46, w - 40); });
      g.font = '400 22px ' + FONT; g.fillText(b.count + '권', w / 2, h - 34);
    });
    b.front.color.set(0xffffff); b.front.needsUpdate = true;
  }
  function loadNear() {
    var cand = [];
    for (var i = 0; i < books.length; i++) {
      var b = books[i];
      if (b.state) continue;
      b.mesh.getWorldPosition(tmp);
      var d = tmp.distanceTo(camera.position);
      if (d < NEAR) cand.push([d, b]);
    }
    cand.sort(function (a, c) { return a[0] - c[0]; });
    cand.forEach(function (pair) {
      var b = pair[1];
      if (b.kind === 'spine') {   // 책등은 글자만 (바로 그림)
        if (pair[0] > 6) return;
        b.state = 2; b.front.map = spineTex(b); b.front.color.set(0xffffff); b.front.needsUpdate = true;
        return;
      }
      if (loading >= MAX_LOAD) return;
      b.state = 1; loading++;
      loader.load('api/lib3d/cover?k=' + encodeURIComponent(b.key), function (tex) {
        loading--; tex.encoding = T.sRGBEncoding; tex.anisotropy = 8;
        b.front.map = tex; b.front.color.set(0xffffff); b.front.needsUpdate = true; b.state = 2; b.cover = true;
      }, undefined, function () { loading--; b.state = 3; titleCover(b); });
    });
  }

  // ── 책 누르기 → 카드 ──
  var ray = new T.Raycaster(), ndc = new T.Vector2();
  var card = document.getElementById('l3d-card');
  var picked = null, pickedInfo = null;
  function pick(cx, cy) {
    var r = renderer.domElement.getBoundingClientRect();
    ndc.set(((cx - r.left) / r.width) * 2 - 1, -((cy - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ndc, camera);
    var targets = books.map(function (b) { return b.mesh; });
    if (elevator) targets.push(elevator);
    var hit = ray.intersectObjects(targets, false)[0];
    if (hit && hit.object === elevator && hit.distance < 8) { openFloors(); return; }
    if (!hit || hit.distance > 12 || !hit.object.userData.book) { closeCard(); return; }
    showCard(hit.object.userData.book);
  }
  function el(id) { return document.getElementById(id); }
  function showCard(b) {
    picked = b; pickedInfo = null;
    el('l3d-card-title').textContent = b.title;
    el('l3d-card-sub').textContent = b.lib + ' · ' + b.count.toLocaleString() + '권';
    el('l3d-card-path').textContent = '';
    var img = el('l3d-card-img');
    img.hidden = false;
    img.onerror = function () { img.hidden = true; };
    img.src = 'api/lib3d/cover?k=' + encodeURIComponent(b.key);
    el('l3d-open').hidden = true;
    card.classList.add('on');
    fetch('api/lib3d/open?k=' + encodeURIComponent(b.key), { credentials: 'same-origin' }).then(function (r) { return r.json(); })
      .then(function (d) {
        if (picked !== b) return;
        pickedInfo = d;
        el('l3d-card-path').textContent = d.path || '';
        el('l3d-open').hidden = !d.url;
      }).catch(function () {});
  }
  function closeCard() { picked = null; card.classList.remove('on'); }
  el('l3d-close').addEventListener('click', closeCard);
  el('l3d-open').addEventListener('click', function () { if (pickedInfo && pickedInfo.url) window.open(pickedInfo.url, '_blank', 'noopener'); });
  el('l3d-read').addEventListener('click', function () { if (picked) openReader(picked); });
  function backUrl() { return location.href.split('#')[0] + '#hall'; }
  el('l3d-read-bo').addEventListener('click', function () {
    if (!picked) return;
    api('api/lib3d/book?b=' + encodeURIComponent(picked.key)).then(function (info) {
      location.href = info.kiosk + '&return=' + encodeURIComponent(backUrl());
    }).catch(function (e) { el('l3d-card-path').textContent = e.message; });
  });

  // ── 뷰어 (서재 안에서 읽기): 두 손에 든 책, 책장 넘김 ──
  // 만화·웹툰(그림)과 epub은 책 모양으로 펼쳐 한 장씩 넘긴다(넓은 화면은 두 쪽 펼침). 웹툰은 '세로 스크롤'로도.
  // epub은 장(章) 본문을 쪽 크기로 나눠(CSS 다단) 책장처럼 넘긴다. pdf는 브라우저 PDF 보기.
  var R = { box: el('l3d-reader'), stage: el('l3d-r-stage'), body: el('l3d-r-body'), vols: el('l3d-r-vols'),
            pos: el('l3d-r-pos'), mode: el('l3d-r-mode'), dirBtn: el('l3d-r-dir'),
            info: null, idx: 0, list: [], scroll: false, vi: 0, rtl: false, busy: false, pages: 0, html: '' };
  var book = el('l3d-book'), pgL = el('l3d-pg-l'), pgR = el('l3d-pg-r'), leaf = el('l3d-leaf');
  var leafF = leaf.querySelector('.front'), leafB = leaf.querySelector('.back');
  function api(url) {
    return fetch(url, { credentials: 'same-origin' }).then(function (r) { return r.json(); }).then(function (d) {
      if (!d.success) throw new Error(d.error || '불러오지 못했습니다');
      return d;
    });
  }
  function note(t) { var m = el('l3d-r-msg'); m.textContent = t || ''; m.hidden = !t; }
  function spread() { return R.box.clientWidth > 900 && R.info && R.info.kind !== 'pdf'; }
  function openReader(b) {
    reading = true; keys = {};
    R.box.classList.add('on'); note('불러오는 중...');
    el('l3d-r-title').textContent = b.title;
    var saved = null;
    try { saved = JSON.parse(localStorage.getItem('l3d_read_' + b.key) || 'null'); } catch (e) { saved = null; }
    try { R.rtl = localStorage.getItem('l3d_rtl') === '1'; } catch (e) { R.rtl = false; }
    R.series = b.key;
    api('api/lib3d/volumes?k=' + encodeURIComponent(b.key)).then(function (d) {
      R.list = d.volumes || [];
      R.vols.innerHTML = '';
      R.list.forEach(function (v, i) {
        var o = document.createElement('option'); o.value = i; o.textContent = v.title; R.vols.appendChild(o);
      });
      var start = 0;
      if (saved && saved.key) R.list.forEach(function (v, i) { if (v.key === saved.key) start = i; });
      loadVolume(start, saved && saved.key ? saved.page || 0 : 0);
    }).catch(function (e) { note(e.message); });
  }
  function closeReader() { reading = false; R.box.classList.remove('on'); R.body.innerHTML = ''; clearPage(pgL); clearPage(pgR); }
  function remember() {
    if (!R.info) return;
    var at = R.info.kind === 'epub' ? { c: R.chap || 0, p: R.idx } : R.idx;
    try { localStorage.setItem('l3d_read_' + R.series, JSON.stringify({ key: R.info.key, page: at })); } catch (e) { /* 무시 */ }
  }
  function loadVolume(i, page) {
    var v = R.list[i];
    if (!v) return;
    R.vols.value = i;
    note('불러오는 중...');
    api('api/lib3d/book?b=' + encodeURIComponent(v.key)).then(function (info) {
      R.info = info; R.vi = i;
      R.mode.hidden = info.kind !== 'images';
      R.dirBtn.hidden = info.kind !== 'images';
      if (info.kind === 'unsupported') { showStage(false); note('이 형식은 여기서 읽을 수 없습니다. [BookOasis 뷰어]로 읽으세요.'); return; }
      if (info.kind === 'epub') { loadChapter(page && page.c || 0, page && page.p || 0); return; }
      if (!info.count) { note('읽을 쪽이 없습니다.'); return; }
      R.pages = info.count;
      R.idx = Math.max(0, Math.min(typeof page === 'number' ? page : 0, info.count - 1));
      note('');
      render();
    }).catch(function (e) { note(e.message); });
  }
  function pageUrl(i) { return 'api/lib3d/page?b=' + encodeURIComponent(R.info.key) + '&i=' + i; }
  function showStage(on) { R.stage.hidden = !on; R.body.hidden = on; }

  // 한 쪽 그리기: 그림 / epub 쪽 / 빈 종이
  function clearPage(node) { node.innerHTML = ''; node.classList.remove('blank'); }
  function fillPage(node, i) {
    clearPage(node);
    if (i < 0 || i >= R.pages) { node.classList.add('blank'); return; }
    if (R.info.kind === 'epub') {
      var view = document.createElement('div'); view.className = 'l3d-txt';
      var art = document.createElement('article'); art.innerHTML = R.html;
      view.appendChild(art); node.appendChild(view);
      requestAnimationFrame(function () {   // 한 단 = 한 쪽 (단 너비 = 쪽 안쪽 너비)
        art.style.columnWidth = view.clientWidth + 'px';
        art.style.transform = 'translateX(' + (-i * (view.clientWidth + 48)) + 'px)';
      });
      var no = document.createElement('span'); no.className = 'l3d-pno'; no.textContent = i + 1; node.appendChild(no);
      return;
    }
    var img = document.createElement('img'); img.alt = (i + 1) + '쪽'; img.draggable = false;
    img.onerror = function () {   // 빈 종이로 남지 않게 이유를 적는다
      fetch(pageUrl(i), { credentials: 'same-origin' }).then(function (r) { return r.json(); }).catch(function () { return {}; })
        .then(function (d) {
          if (img.parentNode !== node) return;
          var e = document.createElement('div'); e.className = 'l3d-pgerr';
          e.textContent = (i + 1) + '쪽을 불러오지 못했습니다' + (d && d.error ? ' - ' + d.error : '');
          node.replaceChild(e, img);
        });
    };
    img.src = pageUrl(i);
    node.appendChild(img);
  }
  function pageStep() { var v = pgR.querySelector('.l3d-txt'); return v ? v.clientWidth + 48 : 0; }

  function render() {
    var info = R.info;
    if (info.kind === 'pdf') {
      showStage(false);
      R.body.className = 'l3d-r-body pdf'; R.body.innerHTML = '';
      var f = document.createElement('iframe'); f.src = 'api/lib3d/pdf?b=' + encodeURIComponent(info.key); f.title = info.title;
      R.body.appendChild(f); R.pos.textContent = 'PDF'; return;
    }
    if (info.kind === 'images' && R.scroll) {   // 세로 스크롤 (웹툰)
      showStage(false);
      R.body.className = 'l3d-r-body scroll'; R.body.innerHTML = '';
      for (var i = 0; i < info.count; i++) {
        var im = document.createElement('img'); im.loading = 'lazy'; im.src = pageUrl(i); im.alt = (i + 1) + '쪽';
        R.body.appendChild(im);
      }
      R.pos.textContent = info.count + '장 · 스크롤';
      return;
    }
    showStage(true);
    book.classList.toggle('two', spread());
    book.classList.toggle('rtl', R.rtl && info.kind === 'images');
    if (spread()) { R.idx -= R.idx % 2; fillPage(pgL, R.idx); fillPage(pgR, R.idx + 1); }
    else fillPage(pgR, R.idx);
    var last = spread() ? Math.min(R.idx + 2, R.pages) : R.idx + 1;
    R.pos.textContent = (info.kind === 'epub' ? (R.chap + 1) + '장 · ' : '') + (R.idx + 1) + (spread() && last > R.idx + 1 ? '-' + last : '') + ' / ' + R.pages;
    if (info.kind === 'images') for (var k = 1; k <= 2; k++) if (R.idx + k + 1 < R.pages) { var pre = new Image(); pre.src = pageUrl(R.idx + k + 1); }
    remember();
  }

  // 책장 넘김: 앞면·뒷면이 있는 한 장(leaf)을 책등을 축으로 180도 돌린다
  function flip(dir) {
    if (R.busy) return;
    var n = spread() ? 2 : 1, to = R.idx + dir * n;
    if (to < 0 || to >= R.pages) {
      if (R.info.kind === 'epub') { nextChapter(dir); return; }
      if (dir > 0) { if (R.vi + 1 < R.list.length) loadVolume(R.vi + 1, 0); else note('마지막 권의 끝입니다.'); }
      else if (R.vi > 0) loadVolume(R.vi - 1, 1e9);
      return;
    }
    R.busy = true;
    var two = spread();
    leaf.className = 'l3d-leaf ' + (two ? 'half' : 'full') + (dir > 0 ? ' fwd' : ' back');
    if (dir > 0) {
      fillPage(leafF, two ? R.idx + 1 : R.idx);           // 지금 오른쪽 쪽이 넘어간다
      fillPage(leafB, two ? R.idx + 2 : -1);              // 넘어간 장의 뒷면 = 다음 왼쪽 쪽
      fillPage(pgR, two ? R.idx + 3 : R.idx + 1);         // 그 아래 = 다음 오른쪽 쪽
    } else {
      fillPage(leafF, two ? R.idx - 1 : R.idx - 1);       // 되돌아오는 장의 앞면 = 이전 오른쪽 쪽
      fillPage(leafB, two ? R.idx : -1);
      if (two) fillPage(pgL, R.idx - 2);
    }
    void leaf.offsetWidth;   // 시작 자세를 먼저 그리고
    leaf.classList.add('go');
    book.classList.add('turning');
    setTimeout(function () {
      R.idx = to; leaf.className = 'l3d-leaf'; clearPage(leafF); clearPage(leafB);
      book.classList.remove('turning'); R.busy = false; render();
    }, 620);
  }
  function go(dir) {
    if (!R.info) return;
    if (R.info.kind === 'images' && R.scroll) { R.body.scrollBy({ top: dir * R.body.clientHeight * 0.85, behavior: 'smooth' }); return; }
    if (R.info.kind === 'pdf') return;
    flip(dir);
  }

  // epub: 장 본문을 쪽 크기로 나눈다 (CSS 다단 - 한 단이 한 쪽)
  function loadChapter(c, p) {
    note('불러오는 중...');
    api('api/lib3d/chapter?b=' + encodeURIComponent(R.info.key) + '&i=' + c).then(function (d) {
      R.chap = c; R.html = d.html; R.pages = 1; R.idx = 0;
      showStage(true);
      book.classList.toggle('two', spread()); book.classList.remove('rtl');
      fillPage(pgR, 0);
      requestAnimationFrame(function () {   // 쪽 수 세기
        var art = pgR.querySelector('article');
        R.pages = Math.max(1, Math.round((art.scrollWidth + 48) / pageStep()));
        R.idx = p === 'end' ? R.pages - 1 : Math.max(0, Math.min(p || 0, R.pages - 1));
        note(''); render();
      });
    }).catch(function (e) { note(e.message); });
  }
  function nextChapter(dir) {
    var c = (R.chap || 0) + dir;
    if (c < 0) { if (R.vi > 0) loadVolume(R.vi - 1, { c: 0, p: 0 }); return; }
    if (c >= R.info.count) { if (R.vi + 1 < R.list.length) loadVolume(R.vi + 1, { c: 0, p: 0 }); else note('마지막 장입니다.'); return; }
    loadChapter(c, dir < 0 ? 'end' : 0);
  }

  function readerKey(e) {
    var k = e.key;
    if (k === 'Escape') { closeReader(); return; }
    var fwd = R.rtl && R.info && R.info.kind === 'images' ? 'ArrowLeft' : 'ArrowRight';
    var bwd = fwd === 'ArrowLeft' ? 'ArrowRight' : 'ArrowLeft';
    if (k === fwd || k === 'PageDown' || k === ' ') { e.preventDefault(); go(1); }
    if (k === bwd || k === 'PageUp') { e.preventDefault(); go(-1); }
  }
  el('l3d-r-prev').addEventListener('click', function () { go(R.rtl && R.info && R.info.kind === 'images' ? 1 : -1); });
  el('l3d-r-next').addEventListener('click', function () { go(R.rtl && R.info && R.info.kind === 'images' ? -1 : 1); });
  el('l3d-r-close').addEventListener('click', closeReader);
  R.vols.addEventListener('change', function () { loadVolume(parseInt(R.vols.value, 10) || 0, 0); });
  R.mode.addEventListener('click', function () { R.scroll = !R.scroll; R.mode.textContent = R.scroll ? '책으로' : '세로 스크롤'; render(); });
  R.dirBtn.addEventListener('click', function () {
    R.rtl = !R.rtl;
    try { localStorage.setItem('l3d_rtl', R.rtl ? '1' : '0'); } catch (e) { /* 무시 */ }
    R.dirBtn.textContent = R.rtl ? '오른쪽→왼쪽' : '왼쪽→오른쪽';
    render();
  });
  R.stage.addEventListener('click', function (e) {   // 책 왼쪽·오른쪽을 눌러 넘기기
    if (!R.info || R.info.kind === 'pdf') return;
    var r = book.getBoundingClientRect();
    var left = e.clientX < r.left + r.width / 2;
    var dir = left ? -1 : 1;
    if (R.rtl && R.info.kind === 'images') dir = -dir;
    go(dir);
  });
  window.addEventListener('resize', function () { if (reading && R.info && !R.scroll && R.info.kind !== 'pdf') render(); });
  el('l3d-r-bo').addEventListener('click', function () {
    if (R.info) location.href = R.info.kiosk + '&return=' + encodeURIComponent(backUrl());
  });

  // ── 설정: 보여 줄 보관함 ──
  var setBox = el('l3d-set');
  function openSettings() {
    setBox.classList.add('on');
    var list = el('l3d-set-list');
    list.textContent = '불러오는 중...';
    api('api/lib3d/libraries').then(function (d) {
      list.textContent = '';
      var groups = {};
      d.libraries.forEach(function (l) { (groups[l.db_type] = groups[l.db_type] || []).push(l); });
      FLOOR_ORDER.concat(Object.keys(groups).filter(function (k) { return FLOOR_ORDER.indexOf(k) < 0; })).forEach(function (k) {
        if (!groups[k]) return;
        var h = document.createElement('div'); h.className = 'l3d-set-h';
        var all = document.createElement('input'); all.type = 'checkbox';
        all.checked = groups[k].every(function (l) { return l.shown; });
        var lab = document.createElement('label'); lab.appendChild(all); lab.appendChild(document.createTextNode(' ' + (FLOOR_NAMES[k] || k) + ' (' + groups[k].length + ')'));
        h.appendChild(lab); list.appendChild(h);
        var boxes = [];
        groups[k].forEach(function (l) {
          var row = document.createElement('label'); row.className = 'l3d-set-row';
          var c = document.createElement('input'); c.type = 'checkbox'; c.checked = l.shown; c.value = l.key;
          row.appendChild(c); row.appendChild(document.createTextNode(' ' + l.name));
          list.appendChild(row); boxes.push(c);
        });
        all.addEventListener('change', function () { boxes.forEach(function (c) { c.checked = all.checked; }); });
      });
      if ((d.errors || []).length) { var er = document.createElement('p'); er.textContent = d.errors.join(' / '); list.appendChild(er); }
    }).catch(function (e) { list.textContent = e.message; });
  }
  function saveSettings(all) {
    var keys = all ? null : Array.prototype.map.call(setBox.querySelectorAll('.l3d-set-row input:checked'), function (c) { return c.value; });
    fetch('api/lib3d/settings', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
                                  body: JSON.stringify({ libraries: keys }) })
      .then(function (r) { return r.json(); })
      .then(function (d) { if (!d.success) throw new Error(d.error || '저장 실패'); setBox.classList.remove('on'); cur = 0; build(true); })
      .catch(function (e) { el('l3d-set-msg').textContent = e.message; });
  }
  el('l3d-set-btn').addEventListener('click', openSettings);
  el('l3d-set-save').addEventListener('click', function () { saveSettings(false); });
  el('l3d-set-all').addEventListener('click', function () { saveSettings(true); });
  el('l3d-set-close').addEventListener('click', function () { setBox.classList.remove('on'); });
  // ── AI: 설정 / 질문하기 / 손님 대화 ──
  function setAI(a) {
    AI = { chat: !!a.chat, ask: !!a.ask, chat_sec: a.chat_sec || 60 };
    el('l3d-ask-btn').hidden = !AI.ask;
    if (!AI.ask) el('l3d-ask').classList.remove('on');
  }
  function postJSON(url, body) {
    return fetch(url, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(function (r) { return r.json(); })
      .then(function (d) { if (!d.success) throw new Error(d.error || '실패'); return d; });
  }
  var aiBox = el('l3d-ai');
  function aiProvider() {   // 연결 방식에 따라 주소 칸·모델 예시·패키지 안내를 바꾼다
    var claude = el('l3d-ai-provider').value === 'anthropic';
    el('l3d-ai-base-f').hidden = claude;
    el('l3d-ai-sdk').hidden = !claude || aiSdk;
    el('l3d-ai-model').placeholder = claude ? 'claude-opus-5-5' : '예: gemini-free3_1';
    var dl = el('l3d-ai-models'); dl.textContent = '';
    (claude ? ['claude-opus-5-5', 'claude-sonnet-5-5', 'claude-haiku-5-5'] : []).forEach(function (m) {
      var o = document.createElement('option'); o.value = m; dl.appendChild(o);
    });
  }
  var aiSdk = true;
  el('l3d-ai-provider').addEventListener('change', aiProvider);
  function openAI() {
    setBox.classList.remove('on'); aiBox.classList.add('on');
    el('l3d-ai-msg').textContent = '불러오는 중...';
    api('api/lib3d/ai/settings').then(function (d) {
      aiSdk = d.sdk; el('l3d-ai-provider').value = d.provider; el('l3d-ai-base').value = d.base_url || '';
      el('l3d-ai-key').value = ''; el('l3d-ai-clear').checked = false;
      el('l3d-ai-key').placeholder = d.api_key_set ? '저장됨 - 바꿀 때만 입력' : 'sk-...';
      el('l3d-ai-model').value = d.model; el('l3d-ai-chat').checked = d.chat; el('l3d-ai-sec').value = d.chat_sec;
      el('l3d-ai-ask').checked = d.ask; el('l3d-ai-mcp').value = d.mcp_command || '';
      aiProvider();
      var ids = { LIB3D_AI_PROVIDER: 'l3d-ai-provider', LIB3D_AI_BASE_URL: 'l3d-ai-base', LIB3D_AI_API_KEY: 'l3d-ai-key', LIB3D_AI_MODEL: 'l3d-ai-model', LIB3D_AI_CHAT: 'l3d-ai-chat', LIB3D_AI_CHAT_SEC: 'l3d-ai-sec',
                  LIB3D_AI_ASK: 'l3d-ai-ask', LIB3D_MCP_COMMAND: 'l3d-ai-mcp' };
      Object.keys(ids).forEach(function (k) { el(ids[k]).disabled = (d.fixed || []).indexOf(k) >= 0; });
      el('l3d-ai-msg').textContent = (d.fixed || []).length ? '환경변수로 정해진 항목은 바꿀 수 없습니다: ' + d.fixed.join(', ') : '';
    }).catch(function (e) { el('l3d-ai-msg').textContent = e.message; });
  }
  el('l3d-set-ai').addEventListener('click', openAI);
  el('l3d-ai-close').addEventListener('click', function () { aiBox.classList.remove('on'); });
  el('l3d-ai-save').addEventListener('click', function () {
    var body = { provider: el('l3d-ai-provider').value, base_url: el('l3d-ai-base').value, model: el('l3d-ai-model').value, chat: el('l3d-ai-chat').checked, chat_sec: +el('l3d-ai-sec').value || 60,
                 ask: el('l3d-ai-ask').checked, mcp_command: el('l3d-ai-mcp').value };
    if (el('l3d-ai-key').value) body.api_key = el('l3d-ai-key').value;
    if (el('l3d-ai-clear').checked) body.clear_key = true;
    el('l3d-ai-msg').textContent = '저장 중...';
    postJSON('api/lib3d/ai/settings', body).then(function (d) {
      var had = AI.chat;
      setAI(d); el('l3d-ai-key').value = '';
      el('l3d-ai-key').placeholder = d.api_key_set ? '저장됨 - 바꿀 때만 입력' : 'sk-...';
      el('l3d-ai-msg').textContent = '저장했습니다.';
      if (had !== AI.chat) { stopChat(); respawn(); }
    }).catch(function (e) { el('l3d-ai-msg').textContent = e.message; });
  });
  el('l3d-ai-test').addEventListener('click', function () {
    el('l3d-ai-msg').textContent = 'BookOasis MCP에 연결하는 중... (저장한 명령으로 시험)';
    api('api/lib3d/ai/test').then(function (d) {
      el('l3d-ai-msg').textContent = '연결됨 - 쓸 수 있는 도구 ' + d.tools.length + '개: ' + d.tools.join(', ');
    }).catch(function (e) { el('l3d-ai-msg').textContent = e.message; });
  });

  // 질문하기: 안내 데스크 직원(LLM)이 BookOasis MCP로 찾아보고 답한다
  var askBox = el('l3d-ask'), askLog = el('l3d-ask-log'), askHist = [], asking = false;
  function askLine(cls, text, tools) {
    var d = document.createElement('div'); d.className = cls; d.textContent = text;
    if (tools && tools.length) { var t = document.createElement('div'); t.className = 't'; t.textContent = '찾아본 도구: ' + tools.join(', '); d.appendChild(t); }
    askLog.appendChild(d); askLog.scrollTop = askLog.scrollHeight; return d;
  }
  el('l3d-ask-btn').addEventListener('click', function () { askBox.classList.toggle('on'); if (askBox.classList.contains('on')) el('l3d-ask-q').focus(); });
  el('l3d-ask-close').addEventListener('click', function () { askBox.classList.remove('on'); });
  el('l3d-ask-q').addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); el('l3d-ask-form').requestSubmit(); }
  });
  el('l3d-ask-form').addEventListener('submit', function (e) {
    e.preventDefault();
    var q = el('l3d-ask-q').value.trim();
    if (!q || asking) return;
    asking = true; el('l3d-ask-send').disabled = true; el('l3d-ask-q').value = '';
    askLine('q', q);
    var wait = askLine('a', '찾아보는 중...');
    postJSON('api/lib3d/ai/ask', { question: q, history: askHist.slice(-6) }).then(function (d) {
      wait.remove(); askLine('a', d.answer, d.tools);
      askHist.push({ q: q, a: d.answer });
    }).catch(function (er) { wait.textContent = '답하지 못했습니다: ' + er.message; })
      .then(function () { asking = false; el('l3d-ask-send').disabled = false; });
  });

  // 손님 대화: 층의 두 손님이 책 한 권을 두고 나누는 말을 말풍선으로 번갈아 띄운다
  var bubble = el('l3d-bubble'), talk = null, chatNext = 0, chatBusy = false, tmpV = new T.Vector3();
  function stopChat() { talk = null; bubble.style.display = 'none'; }
  function chatTick() {
    var now = performance.now();
    if (!AI.chat || !chatPair || reading || chatBusy || talk || now < chatNext || document.visibilityState !== 'visible') return;
    var a = chatPair[0].g.position;
    if (Math.hypot(camera.position.x - a.x, camera.position.z - a.z) > 26) return;   // 멀리 있으면 부르지 않는다(요금)
    chatBusy = true;
    var keys = (floors[cur] ? floors[cur].libs : []).map(function (l) { return l.key; }).join(',');
    api('api/lib3d/ai/chat?libs=' + encodeURIComponent(keys)).then(function (d) {
      if (!d.lines || !d.lines.length) { chatNext = performance.now() + (d.wait || AI.chat_sec) * 1000; return; }
      talk = { lines: d.lines, i: 0, title: d.book && d.book.title, until: 0, pair: chatPair };
      chatNext = performance.now() + AI.chat_sec * 1000;
    }).catch(function (e) {
      console.warn('3D 서재 손님 대화:', e.message);
      chatNext = performance.now() + AI.chat_sec * 2000;
    }).then(function () { chatBusy = false; });
  }
  setInterval(chatTick, 2000);
  function placeBubble() {
    if (!talk) return;
    if (talk.pair !== chatPair || reading) { stopChat(); return; }
    var now = performance.now();
    if (now > talk.until) {
      if (talk.until && ++talk.i >= talk.lines.length) { stopChat(); return; }
      var ln = talk.lines[talk.i];
      bubble.textContent = '';
      if (talk.i === 0 && talk.title) { var b = document.createElement('b'); b.textContent = '「' + talk.title + '」'; bubble.appendChild(b); }
      bubble.appendChild(document.createTextNode(ln.text));
      talk.until = now + 2600 + ln.text.length * 70;
    }
    var p = talk.pair[talk.lines[talk.i].who % 2];
    tmpV.set(p.g.position.x, p.g.position.y + 1.85 * (p.sc || 1), p.g.position.z);
    var dist = camera.position.distanceTo(tmpV);
    tmpV.project(camera);
    if (tmpV.z > 1 || dist > 30 || Math.abs(tmpV.x) > 1.1 || Math.abs(tmpV.y) > 1.1) { bubble.style.display = 'none'; return; }
    bubble.style.display = 'block';
    bubble.style.left = ((tmpV.x + 1) / 2 * wrap.clientWidth) + 'px';
    bubble.style.top = ((1 - tmpV.y) / 2 * wrap.clientHeight - 6) + 'px';
  }
  // 층별 인물 수: 층(열) × 인물 종류(행) 숫자 칸, 비우면 자동
  var pplBox = el('l3d-ppl');
  function openPeople() {
    setBox.classList.remove('on'); aiBox.classList.remove('on'); pplBox.classList.add('on');
    var t = el('l3d-ppl-t'); t.textContent = ''; el('l3d-ppl-msg').textContent = '';
    if (!floors.length) { el('l3d-ppl-msg').textContent = '서재를 다 지은 뒤 다시 여세요.'; return; }
    var hr = document.createElement('tr'); hr.appendChild(document.createElement('th'));
    floors.forEach(function (f) { var th = document.createElement('th'); th.textContent = f.label; hr.appendChild(th); });
    t.appendChild(hr);
    PEOPLE_KINDS.forEach(function (pk) {
      var tr = document.createElement('tr'), th = document.createElement('th'); th.textContent = pk.label; tr.appendChild(th);
      floors.forEach(function (f) {
        var td = document.createElement('td'), inp = document.createElement('input');
        inp.type = 'number'; inp.min = 0; inp.max = PEOPLE_MAX; inp.placeholder = '자동';
        inp.dataset.floor = f.key; inp.dataset.kind = pk.k;
        var v = (PEOPLE[f.key] || {})[pk.k]; if (typeof v === 'number') inp.value = v;
        td.appendChild(inp); tr.appendChild(td);
      });
      t.appendChild(tr);
    });
  }
  function savePeople(auto) {
    var out = {};
    if (!auto) Array.prototype.forEach.call(pplBox.querySelectorAll('input[data-floor]'), function (inp) {
      if (inp.value === '') return;
      (out[inp.dataset.floor] = out[inp.dataset.floor] || {})[inp.dataset.kind] = Math.max(0, Math.min(PEOPLE_MAX, parseInt(inp.value, 10) || 0));
    });
    el('l3d-ppl-msg').textContent = '저장 중...';
    postJSON('api/lib3d/settings', { people: out }).then(function (d) {
      PEOPLE = d.people || {}; respawn(); stopChat();
      if (auto) openPeople();
      el('l3d-ppl-msg').textContent = '저장했습니다. 지금 층에 바로 반영했습니다.';
    }).catch(function (e) { el('l3d-ppl-msg').textContent = e.message; });
  }
  el('l3d-set-ppl').addEventListener('click', openPeople);
  el('l3d-ppl-save').addEventListener('click', function () { savePeople(false); });
  el('l3d-ppl-auto').addEventListener('click', function () { savePeople(true); });
  el('l3d-ppl-close').addEventListener('click', function () { pplBox.classList.remove('on'); });
  // 창밖 풍경 설정: 고르는 즉시 미리 보이고, [저장]하면 lib3d.json에 남는다
  var outBox = el('l3d-out');
  function openOutside() {
    setBox.classList.remove('on'); aiBox.classList.remove('on'); pplBox.classList.remove('on'); outBox.classList.add('on');
    el('l3d-out-time').value = OUTSIDE.time; el('l3d-out-season').value = OUTSIDE.season; el('l3d-out-weather').value = OUTSIDE.weather;
    el('l3d-out-msg').textContent = '';
  }
  function outsideForm() { return { time: el('l3d-out-time').value, season: el('l3d-out-season').value, weather: el('l3d-out-weather').value }; }
  ['l3d-out-time', 'l3d-out-season', 'l3d-out-weather'].forEach(function (id) {
    el(id).addEventListener('change', function () { OUTSIDE = outsideForm(); applyOutside.force = true; applyOutside(); el('l3d-out-msg').textContent = '미리 보기 중 - 저장해야 남습니다.'; });
  });
  el('l3d-out-save').addEventListener('click', function () {
    postJSON('api/lib3d/settings', { outside: outsideForm() }).then(function (d) {
      OUTSIDE = d.outside; applyOutside.force = true; applyOutside(); el('l3d-out-msg').textContent = '저장했습니다.';
    }).catch(function (e) { el('l3d-out-msg').textContent = e.message; });
  });
  el('l3d-out-close').addEventListener('click', function () { outBox.classList.remove('on'); });
  el('l3d-set-out').addEventListener('click', openOutside);
  // 3D 모형: 지금 그대로(코드로 그린 가구) | 모형 파일
  var mdlBox = el('l3d-mdl');
  function openModels() {
    [setBox, aiBox, pplBox, outBox].forEach(function (b) { b.classList.remove('on'); }); mdlBox.classList.add('on');
    Array.prototype.forEach.call(mdlBox.querySelectorAll('input[name=l3d-mdl]'), function (i) { i.checked = i.value === MODELS; });
    el('l3d-mdl-msg').textContent = '';
  }
  el('l3d-set-mdl').addEventListener('click', openModels);
  el('l3d-mdl-close').addEventListener('click', function () { mdlBox.classList.remove('on'); });
  el('l3d-mdl-save').addEventListener('click', function () {
    var v = (mdlBox.querySelector('input[name=l3d-mdl]:checked') || {}).value || 'basic';
    el('l3d-mdl-msg').textContent = '저장 중...';
    postJSON('api/lib3d/settings', { models: v }).then(function (d) {
      MODELS = d.models;
      if (MODELS === 'real' && !(REAL.sofa || REAL.car)) { el('l3d-mdl-msg').textContent = '저장했습니다. 모형 파일을 받는 중 (약 14MB) - 다 받으면 바로 바뀝니다.'; loadReal(); }
      else { el('l3d-mdl-msg').textContent = '저장했습니다.'; rebuildForModels(); }
    }).catch(function (e) { el('l3d-mdl-msg').textContent = e.message; });
  });
  function hashNav() {
    if (location.hash === '#outside') openOutside();
    if (location.hash === '#models') openModels();
    if (location.hash === '#settings') openSettings();
    if (location.hash === '#ai') openAI();
    if (location.hash === '#people') { if (floors.length) openPeople(); else pendingPeople = true; }
  }
  var pendingPeople = false;
  window.addEventListener('hashchange', hashNav);
  setTimeout(hashNav, 0);

  // ── 지도·층 ──
  var map = el('l3d-map');
  function closeMap() { map.classList.remove('on'); }
  function menuButton(text, sub, fn, strong) {
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.innerHTML = '<span></span><small></small>';
    btn.firstChild.textContent = text; btn.lastChild.textContent = sub;
    if (strong) btn.style.fontWeight = '700';
    btn.addEventListener('click', fn);
    map.appendChild(btn);
  }
  function openFloors() {
    map.textContent = '';
    floors.forEach(function (f, i) {
      menuButton((i === cur ? '▶ ' : '') + f.label, '보관함 ' + f.libs.length + ' · 작품 ' + f.total.toLocaleString(),
        function () { buildFloor(i); home(); closeMap(); }, i === cur);
    });
    map.classList.add('on');
  }
  el('l3d-map-btn').addEventListener('click', function () {
    if (map.classList.contains('on')) { closeMap(); return; }
    map.textContent = '';
    floors.forEach(function (f) {
      var head = document.createElement('div');
      head.textContent = f.label;
      head.style.cssText = 'padding:8px 10px 2px;font-size:.75rem;opacity:.65;font-weight:700';
      map.appendChild(head);
      f.booths.forEach(function (b) { menuButton(b.name, b.count + '작품', function () { teleport(b); }); });
    });
    map.classList.add('on');
  });
  el('l3d-floor-btn').addEventListener('click', function () { if (map.classList.contains('on')) closeMap(); else openFloors(); });
  el('l3d-home').addEventListener('click', function () { home(); closeMap(); });
  el('l3d-reload').addEventListener('click', function () { build(true); });

  var whereEl = el('l3d-where');
  function where() {
    var best = null, bd = 1e9;
    booths.forEach(function (b) {
      var d = Math.hypot(camera.position.x - b.x, camera.position.z - b.z);
      if (d < bd) { bd = d; best = b; }
    });
    var fl = floors[cur] ? floors[cur].label + ' · ' : '';
    whereEl.textContent = fl + (best && bd < 9 ? best.name + ' · ' + best.count + '작품' : '로비 · 엘리베이터나 [층]으로 다른 층');
  }

  // ── 짓기: 세션(db_type)마다 한 층 ──
  var FLOOR_NAMES = { general: '일반', adult: '성인', audiobook: '오디오북', video: '비디오' };
  var FLOOR_ORDER = ['general', 'adult', 'audiobook', 'video'];
  var floors = [], cur = -1, floorGroup = null;
  function makeFloors(libs) {
    var by = {};
    libs.forEach(function (l) { (by[l.db_type] = by[l.db_type] || []).push(l); });
    return Object.keys(by).sort(function (a, b) {
      var ia = FLOOR_ORDER.indexOf(a), ib = FLOOR_ORDER.indexOf(b);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || a.localeCompare(b);
    }).map(function (k, i) {
      var list = by[k], total = 0;
      list.forEach(function (l) { total += l.series.length; });
      return { key: k, label: (i + 1) + '층 ' + (FLOOR_NAMES[k] || k), libs: list, total: total, booths: [] };
    });
  }
  var shared = [].concat.apply([], Object.keys(M).map(function (k) { return M[k]; }));   // 배열(나뭇잎·외벽 색)도 펼친다
  function disposeGroup(g) {
    g.traverse(function (o) {
      if (o.geometry && !o.geometry.userData.shared && [faceGeo, torsoGeo, legGeo, armGeo, ballGeo, hairGeo, neckGeo].indexOf(o.geometry) < 0) o.geometry.dispose();
      var ms = Array.isArray(o.material) ? o.material : (o.material ? [o.material] : []);
      ms.forEach(function (m) {
        if (shared.indexOf(m) >= 0 || m.userData.keep) return;   // 공용 재질은 그대로
        if (m.map && m.map !== oakTex && m.map !== floorTex && m.map !== skyTex) m.map.dispose();
        m.dispose();
      });
    });
  }
  // 입구 벽·안쪽 벽에 이 층 책 표지를 포스터처럼 (무작위, 누르면 작품 카드)
  var posterGeo = new T.PlaneGeometry(1, 1); posterGeo.userData.shared = true;
  function addPosters(fl, seed) {
    if (!layout) return;
    var r = rnd(seed * 211 + 5), pool = [];
    fl.libs.forEach(function (lib) { lib.series.forEach(function (s) { if (s.last) pool.push([lib, s]); }); });
    if (!pool.length) return;
    var L = layout, PW = 1.5, PH = 2.15, frame = 0.07;
    function poster(x, z, rotY) {
      var pick0 = pool.splice(Math.floor(r() * pool.length), 1)[0];
      if (!pick0) return;
      var lib = pick0[0], s = pick0[1], base = colorOf(s.title);
      var mat = new T.MeshStandardMaterial({ color: base, roughness: 0.55 });
      var b = { key: lib.db_type + ':' + s.last, title: s.title || '(제목 없음)', count: s.count, lib: lib.name, db: lib.db_type,
                front: mat, base: base, state: 2, kind: 'poster' };
      var g = new T.Group(); g.position.set(x, 2.55 + (r() - 0.5) * 0.25, z); g.rotation.y = rotY; parent.add(g);
      var back = new T.Mesh(unitBox, M.black); back.scale.set(PW + frame * 2, PH + frame * 2, 0.04); back.position.z = 0.02; g.add(back);
      var m = new T.Mesh(posterGeo, mat); m.scale.set(PW, PH, 1); m.position.z = 0.045; m.userData.book = b; g.add(m);
      b.mesh = m; books.push(b);
      loader.load('api/lib3d/cover?k=' + encodeURIComponent(b.key), function (tex) {
        tex.encoding = T.sRGBEncoding; tex.anisotropy = 8; mat.map = tex; mat.color.set(0xffffff); mat.needsUpdate = true; b.cover = true;
      }, undefined, function () { b.state = 3; titleCover(b); });
    }
    var step = 2.6, x;
    // 입구 벽 (안쪽을 보게, 문·엘리베이터 앞은 비움)
    for (x = -L.w / 2 + 3.5; x < L.w / 2 - 2; x += step + r() * 0.8) {
      if (Math.abs(x) < 3.2) continue;
      if (r() < 0.85) poster(x, L.front - 0.12, Math.PI);
    }
    // 안쪽 벽
    for (x = -L.w / 2 + 2.5; x < L.w / 2 - 2; x += step + r() * 0.8) if (r() < 0.85) poster(x, L.back + 0.12, 0);
  }
  function dimEnv(root) {   // 환경 반사광은 은은하게 (재질마다 한 번)
    if (!scene.environment) return;
    root.traverse(function (o) {
      [].concat(o.material || []).forEach(function (m) { if (m && m.isMeshStandardMaterial && !m.userData.envSet) { m.envMapIntensity = m === M.floor ? 0.12 : 0.3; m.userData.envSet = true; } });
    });
  }
  function buildFloor(i) {
    if (floorGroup) { scene.remove(floorGroup); disposeGroup(floorGroup); }
    books = []; booths = [];
    cur = i;
    var fl = floors[i];
    floorGroup = new T.Group();
    scene.add(floorGroup);
    parent = floorGroup;
    COLS = Math.max(2, Math.min(4, fl.libs.length));
    addBuilding(fl, COLS, Math.ceil(fl.libs.length / COLS));
    applyOutside.force = true; applyOutside();
    fl.libs.forEach(function (lib, j) { addSection(lib, j); });
    addPosters(fl, i + 1);
    spawnPeople(fl, i + 1);
    dimEnv(floorGroup);
    booths.forEach(function (b) { b.floor = i; });
    fl.booths = booths.slice();
    parent = scene;
    closeCard();
  }
  function build(refresh) {
    msg.style.display = '';
    msg.textContent = '서점을 여는 중...';
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
        if (d.ai) setAI(d.ai);
        PEOPLE = d.people || {};
        MODELS = d.models === 'real' ? 'real' : 'basic'; loadReal();
        if (d.outside) OUTSIDE = Object.assign({ time: 'auto', season: 'auto', weather: 'clear' }, d.outside);
        floors = makeFloors(libs);
        floors.forEach(function (f, i) {
          var cols = Math.max(2, Math.min(4, f.libs.length));
          f.booths = f.libs.map(function (l, j) {
            return { name: l.name, count: l.series.length, floor: i,
                     x: (j % cols - (cols - 1) / 2) * (BOOTH_W + GAP), z: -LOBBY - BOOTH_D / 2 - Math.floor(j / cols) * (BOOTH_D + GAP) };
          });
        });
        var first = !posRestored; posRestored = true;
        if (!(first && restorePos())) { buildFloor(Math.max(0, Math.min(cur, floors.length - 1))); home(); }
        msg.style.display = 'none';
        if (pendingPeople) { pendingPeople = false; openPeople(); }
      })
      .catch(function (e) { msg.textContent = '불러오지 못했습니다: ' + e.message; });
  }

  // ── 그리기 ──
  var last = performance.now(), acc = 0;
  function frame(now) {
    var dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    step(dt);
    if (!reading) { updatePeople(dt, now); updateWeather(dt, now); updateCars(dt); }
    acc += dt;
    if (acc > 0.3) { acc = 0; loadNear(); where(); if (now - posSavedAt > 2000) { posSavedAt = now; savePos(); } }
    if (!reading) renderer.render(scene, camera);
    placeBubble();
    requestAnimationFrame(frame);
  }
  resize();
  home();
  loadHumans();
  build(false);
  requestAnimationFrame(frame);
  if ('ResizeObserver' in window) new ResizeObserver(resize).observe(wrap);
})();
