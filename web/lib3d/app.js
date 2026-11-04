/* BookOasis 3D 서재 - 모던 서점 분위기의 건물 안을 혼자 걸어 다니며 둘러보고, 고른 책을 그 자리에서 읽는다.
 * 세션별로 층(1층 일반 · 2층 성인 · 3층 오디오북 · 4층 비디오 …), 보관함은 서가 구역, 작품(시리즈)은
 * 평대의 표지 · 눈높이 칸의 표지 진열 · 나머지 칸의 책등(제목)으로. 빈칸은 장식용 책으로 채운다.
 * 데이터: api/lib3d/data · 표지: api/lib3d/cover · 열기: api/lib3d/open · 읽기: api/lib3d/volumes|book|page|chapter|pdf
 * 조작: W A S D·방향키 이동(Shift 빠르게), 끌기로 둘러보기, 책 누르기, 휴대폰은 왼쪽 아래 끌기로 이동 */
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
  scene.background = new T.Color(0xf3efe8);
  scene.fog = new T.Fog(0xf3efe8, 40, 120);
  var camera = new T.PerspectiveCamera(60, 1, 0.05, 200);
  var EYE = 1.62, CEIL = 5.4;
  scene.add(new T.HemisphereLight(0xffffff, 0xcbb89c, 0.6));
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
    // 평대 (가장 최근 작품 표지를 눕혀서)
    var tbl = new T.Group(); tbl.position.set(0, 0, 1.6); g.add(tbl);
    var top = new T.Mesh(new T.BoxGeometry(2.8, 0.05, 1.3), M.oak); top.position.y = 0.82; top.castShadow = top.receiveShadow = true; tbl.add(top);
    var body = new T.Mesh(new T.BoxGeometry(2.6, 0.78, 1.1), M.white); body.position.y = 0.4; body.castShadow = body.receiveShadow = true; tbl.add(body);
    for (var t = 0; t < 10 && queue.length; t++) {
      var b = makeBook('flat', queue.shift(), lib);
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
  }

  // ── 건물 (한 층) ──
  var hall = { x0: -20, x1: 20, z0: -40, z1: 10 };
  var elevator = null;
  function addBuilding(fl, cols, rows) {
    var w = cols * BOOTH_W + (cols - 1) * GAP + 12, back = -LOBBY - rows * (BOOTH_D + GAP) - 2, front = 10;
    var d = front - back, cz = (front + back) / 2;
    hall = { x0: -w / 2 + 0.6, x1: w / 2 - 0.6, z0: back + 0.6, z1: front - 0.6 };
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
    // 벽 + 걸레받이
    [[0, front, w, 0], [0, back, w, 0], [-w / 2, cz, d, Math.PI / 2], [w / 2, cz, d, Math.PI / 2]].forEach(function (s) {
      var wall = new T.Mesh(new T.BoxGeometry(s[2], CEIL, 0.2), M.wall);
      wall.rotation.y = s[3]; wall.receiveShadow = true; add(wall, s[0], CEIL / 2, s[1]);
      var base = new T.Mesh(new T.BoxGeometry(s[2], 0.12, 0.24), M.black);
      base.rotation.y = s[3]; add(base, s[0], 0.06, s[1]);
    });
    // 큰 창 (양옆 벽, 검은 창틀)
    for (var wz = front - 6; wz > back + 3; wz -= 7) {
      [-1, 1].forEach(function (side) {
        var gx = side * (w / 2 - 0.11);
        var glass = new T.Mesh(new T.PlaneGeometry(5.4, 3.6), M.sky);
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
    [[w / 2 - 1.2, front - 1.2], [-w / 2 + 1.2, front - 1.2], [w / 2 - 1.2, back + 1.2], [-w / 2 + 1.2, back + 1.2]].forEach(function (p) {
      add(new T.Mesh(new T.CylinderGeometry(0.28, 0.22, 0.55, 28), M.pot), p[0], 0.275, p[1], true);
      var leaf = new T.Mesh(new T.SphereGeometry(0.55, 20, 14), M.green); leaf.scale.set(1, 1.35, 1); add(leaf, p[0], 1.2, p[1], true);
    });
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

  // ── 이동·시점 ──
  var yaw = 0, pitch = 0, keys = {}, moveStick = { x: 0, y: 0 };
  function home() { camera.position.set(0, EYE, 9); yaw = 0; pitch = 0.1; }
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

  // ── 뷰어 (서재 안에서 읽기) ──
  var R = { box: el('l3d-reader'), body: el('l3d-r-body'), vols: el('l3d-r-vols'), pos: el('l3d-r-pos'), mode: el('l3d-r-mode'),
            info: null, idx: 0, list: [], scroll: false, vi: 0 };
  function api(url) {
    return fetch(url, { credentials: 'same-origin' }).then(function (r) { return r.json(); }).then(function (d) {
      if (!d.success) throw new Error(d.error || '불러오지 못했습니다');
      return d;
    });
  }
  function note(t) { var m = el('l3d-r-msg'); m.textContent = t || ''; m.hidden = !t; }
  function openReader(b) {
    reading = true; keys = {};
    R.box.classList.add('on'); R.body.innerHTML = ''; note('불러오는 중...');
    el('l3d-r-title').textContent = b.title;
    var saved = null;
    try { saved = JSON.parse(localStorage.getItem('l3d_read_' + b.key) || 'null'); } catch (e) { saved = null; }
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
  function closeReader() { reading = false; R.box.classList.remove('on'); R.body.innerHTML = ''; }
  function remember() {
    if (!R.info) return;
    try { localStorage.setItem('l3d_read_' + R.series, JSON.stringify({ key: R.info.key, page: R.idx })); } catch (e) { /* 무시 */ }
  }
  function loadVolume(i, page) {
    var v = R.list[i];
    if (!v) return;
    R.vols.value = i;
    note('불러오는 중...');
    api('api/lib3d/book?b=' + encodeURIComponent(v.key)).then(function (info) {
      R.info = info; R.vi = i; R.idx = Math.max(0, Math.min(page || 0, Math.max(0, info.count - 1)));
      R.mode.hidden = info.kind !== 'images';
      if (info.kind === 'unsupported') { R.body.innerHTML = ''; note('이 형식은 여기서 읽을 수 없습니다. [BookOasis 뷰어]로 읽으세요.'); return; }
      if (!info.count) { note('읽을 쪽이 없습니다.'); return; }
      note('');
      render();
    }).catch(function (e) { note(e.message); });
  }
  function pageUrl(i) { return 'api/lib3d/page?b=' + encodeURIComponent(R.info.key) + '&i=' + i; }
  function render() {
    var info = R.info;
    R.body.innerHTML = ''; R.body.className = 'l3d-r-body ' + info.kind + (R.scroll ? ' scroll' : '');
    if (info.kind === 'pdf') {
      var f = document.createElement('iframe'); f.src = 'api/lib3d/pdf?b=' + encodeURIComponent(info.key); f.title = info.title;
      R.body.appendChild(f); R.pos.textContent = 'PDF'; return;
    }
    if (info.kind === 'epub') {
      R.pos.textContent = (R.idx + 1) + ' / ' + info.count + ' 장';
      api('api/lib3d/chapter?b=' + encodeURIComponent(info.key) + '&i=' + R.idx).then(function (d) {
        var art = document.createElement('article'); art.innerHTML = d.html; R.body.appendChild(art); R.body.scrollTop = 0;
      }).catch(function (e) { note(e.message); });
      remember(); return;
    }
    if (R.scroll) {   // 세로 스크롤 (웹툰)
      for (var i = 0; i < info.count; i++) {
        var im = document.createElement('img'); im.loading = 'lazy'; im.src = pageUrl(i); im.alt = (i + 1) + '쪽';
        R.body.appendChild(im);
      }
      R.pos.textContent = info.count + '장 · 스크롤';
      return;
    }
    var img = document.createElement('img'); img.src = pageUrl(R.idx); img.alt = (R.idx + 1) + '쪽';
    R.body.appendChild(img);
    if (R.idx + 1 < info.count) { var pre = new Image(); pre.src = pageUrl(R.idx + 1); }   // 다음 쪽 미리
    R.pos.textContent = (R.idx + 1) + ' / ' + info.count;
    remember();
  }
  function go(dir) {
    if (!R.info) return;
    if (R.info.kind === 'images' && R.scroll) { R.body.scrollBy({ top: dir * R.body.clientHeight * 0.85, behavior: 'smooth' }); return; }
    var n = R.idx + dir;
    if (n < 0) { if (R.vi > 0) loadVolume(R.vi - 1, 1e9); return; }
    if (n >= R.info.count) { if (R.vi + 1 < R.list.length) loadVolume(R.vi + 1, 0); else note('마지막 권의 끝입니다.'); return; }
    R.idx = n; render();
  }
  function readerKey(e) {
    var k = e.key;
    if (k === 'Escape') { closeReader(); return; }
    if (k === 'ArrowRight' || k === 'PageDown' || k === ' ') { e.preventDefault(); go(1); }
    if (k === 'ArrowLeft' || k === 'PageUp') { e.preventDefault(); go(-1); }
  }
  el('l3d-r-prev').addEventListener('click', function () { go(-1); });
  el('l3d-r-next').addEventListener('click', function () { go(1); });
  el('l3d-r-close').addEventListener('click', closeReader);
  R.vols.addEventListener('change', function () { loadVolume(parseInt(R.vols.value, 10) || 0, 0); });
  R.mode.addEventListener('click', function () { R.scroll = !R.scroll; R.mode.textContent = R.scroll ? '한 장씩' : '세로 스크롤'; render(); });
  R.body.addEventListener('click', function (e) {   // 그림 왼쪽·오른쪽 눌러 넘기기
    if (!R.info || R.info.kind !== 'images' || R.scroll) return;
    var r = R.body.getBoundingClientRect();
    go(e.clientX - r.left < r.width / 3 ? -1 : 1);
  });
  el('l3d-r-bo').addEventListener('click', function () {
    if (R.info) location.href = R.info.kiosk + '&return=' + encodeURIComponent(backUrl());
  });

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
  var shared = Object.keys(M).map(function (k) { return M[k]; });
  function disposeGroup(g) {
    g.traverse(function (o) {
      if (o.geometry && o.geometry !== faceGeo) o.geometry.dispose();
      var ms = Array.isArray(o.material) ? o.material : (o.material ? [o.material] : []);
      ms.forEach(function (m) {
        if (shared.indexOf(m) >= 0) return;   // 공용 재질은 그대로
        if (m.map && m.map !== oakTex && m.map !== floorTex && m.map !== skyTex) m.map.dispose();
        m.dispose();
      });
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
    fl.libs.forEach(function (lib, j) { addSection(lib, j); });
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
        floors = makeFloors(libs);
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
    if (acc > 0.3) { acc = 0; loadNear(); where(); }
    if (!reading) renderer.render(scene, camera);
    requestAnimationFrame(frame);
  }
  resize();
  home();
  build(false);
  requestAnimationFrame(frame);
  if ('ResizeObserver' in window) new ResizeObserver(resize).observe(wrap);
})();
