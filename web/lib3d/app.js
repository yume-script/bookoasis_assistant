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
    if (layout) layout.sections.push({ x: cx, z: cz });
  }

  // ── 건물 (한 층) ──
  var hall = { x0: -20, x1: 20, z0: -40, z1: 10 };
  var elevator = null;
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
    parent = floorGroup; spawnPeople(floors[cur], cur + 1); parent = scene;
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
      keepShared(c.scene); HUMAN.elf = c.scene;
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
  // ── 엘프 피규어를 걷는 사람으로: 뼈대 없는 정지 모형에 다리 뼈대를 직접 심는다 ──
  // 받침대를 떼고, 치마 아래 다리를 이어진 덩어리별로 왼·오른 다리로 나눠 허벅지·종아리 뼈에 묶는다(나머지는 골반에 붙어 함께 움직임).
  // 원래 자세가 한 발 앞·한 발 뒤인 걷는 모습이라 그 자세를 기준으로 다리를 앞뒤로 흔든다.
  function rigElf(src) {
    src.updateMatrixWorld(true);
    var mesh = null; src.traverse(function (o) { if (o.isMesh && !mesh) mesh = o; });
    if (!mesh) return null;
    var g0 = mesh.geometry.index ? mesh.geometry.toNonIndexed() : mesh.geometry.clone();
    g0.applyMatrix4(mesh.matrixWorld);
    var P = g0.attributes.position, n = P.count, tri = n / 3;
    // 같은 자리 꼭짓점을 하나로 보고 삼각형끼리 이어진 덩어리(union-find)를 만든다
    var key = {}, vid = new Int32Array(n), nid = 0;
    for (var i = 0; i < n; i++) {
      var k = Math.round(P.getX(i) * 1e4) + ',' + Math.round(P.getY(i) * 1e4) + ',' + Math.round(P.getZ(i) * 1e4);
      vid[i] = key[k] === undefined ? (key[k] = nid++) : key[k];
    }
    var par = new Int32Array(nid); for (i = 0; i < nid; i++) par[i] = i;
    function find(a) { while (par[a] !== a) { par[a] = par[par[a]]; a = par[a]; } return a; }
    function uni(a, b) { a = find(a); b = find(b); if (a !== b) par[a] = b; }
    var box = new T.Box3().setFromBufferAttribute(P), H = box.max.y - box.min.y;
    // 1) 받침대: 바닥에 붙은 납작한 덩어리들
    for (var t = 0; t < tri; t++) { uni(vid[t * 3], vid[t * 3 + 1]); uni(vid[t * 3], vid[t * 3 + 2]); }
    var cb = {};
    for (i = 0; i < n; i++) {
      var r0 = find(vid[i]), c = cb[r0] || (cb[r0] = { minX: 1e9, maxX: -1e9, minY: 1e9, maxY: -1e9 });
      c.minX = Math.min(c.minX, P.getX(i)); c.maxX = Math.max(c.maxX, P.getX(i));
      c.minY = Math.min(c.minY, P.getY(i)); c.maxY = Math.max(c.maxY, P.getY(i));
    }
    var base = new Uint8Array(n);   // 덩어리를 다시 나누기 전에 받침대 꼭짓점을 표시해 둔다
    for (i = 0; i < n; i++) { var cq = cb[find(vid[i])]; base[i] = cq.maxY < box.min.y + H * 0.085 ? 1 : 0; }   // 바닥 가까이 납작한 덩어리 = 받침대(원판·무늬)
    function isBase(i) { return base[i] === 1; }
    // 받침대 위(발바닥)부터 키를 다시 잰다
    var floorY = 1e9, topY = -1e9;
    for (i = 0; i < n; i++) if (!isBase(i)) { floorY = Math.min(floorY, P.getY(i)); topY = Math.max(topY, P.getY(i)); }
    var h = topY - floorY;
    // 2) 치마 아래 다리: 사타구니보다 낮은 삼각형만으로 덩어리를 다시 나눈다
    var crotch = floorY + h * 0.435;
    for (i = 0; i < nid; i++) par[i] = i;
    for (t = 0; t < tri; t++) {
      var a = t * 3;
      if (isBase(a)) continue;
      if (P.getY(a) < crotch && P.getY(a + 1) < crotch && P.getY(a + 2) < crotch) { uni(vid[a], vid[a + 1]); uni(vid[a], vid[a + 2]); }
    }
    var comp = {};
    for (i = 0; i < n; i++) {
      if (isBase(i) || P.getY(i) >= crotch) continue;
      var rr = find(vid[i]), cc = comp[rr] || (comp[rr] = { n: 0, x: 0, y: 0, z: 0, id: rr });
      cc.n++; cc.x += P.getX(i); cc.y += P.getY(i); cc.z += P.getZ(i);
    }
    var comps = Object.keys(comp).map(function (k) { var c = comp[k]; c.x /= c.n; c.y /= c.n; c.z /= c.n; return c; })
      .sort(function (a, b) { return b.n - a.n; });
    if (comps.length < 2) return null;
    var legA = comps[0], legB = comps[1];
    var side = {}; side[legA.id] = legA.x > legB.x ? 0 : 1; side[legB.id] = 1 - side[legA.id];   // 0 = 모형의 왼쪽(+x)
    // 작은 덩어리(부츠·밴드 등)는 가까운 다리로
    var legPts = [[], []];
    for (i = 0; i < n; i += 7) {
      var ri = find(vid[i]);
      if (side[ri] !== undefined && P.getY(i) < crotch) legPts[side[ri]].push([P.getX(i), P.getY(i), P.getZ(i)]);
    }
    comps.slice(2).forEach(function (c) {
      var best = 0, bd = 1e9;
      [0, 1].forEach(function (s) {
        legPts[s].forEach(function (q) { var d = (q[0] - c.x) * (q[0] - c.x) + (q[1] - c.y) * (q[1] - c.y) + (q[2] - c.z) * (q[2] - c.z); if (d < bd) { bd = d; best = s; } });
      });
      side[c.id] = best;
    });
    // 3) 관절 위치: 엉덩이(사타구니 바로 아래 평균), 무릎(다리 가운데 높이 평균)
    var knee = floorY + (crotch - floorY) * 0.5 + h * 0.02;
    var hipJ = [new T.Vector3(), new T.Vector3()], kneeJ = [new T.Vector3(), new T.Vector3()], hc = [0, 0], kc = [0, 0];
    for (i = 0; i < n; i++) {
      var s = side[find(vid[i])], y = P.getY(i);
      if (s === undefined || y >= crotch) continue;
      if (y > crotch - h * 0.05) { hipJ[s].x += P.getX(i); hipJ[s].z += P.getZ(i); hc[s]++; }
      if (Math.abs(y - knee) < h * 0.015) { kneeJ[s].x += P.getX(i); kneeJ[s].z += P.getZ(i); kc[s]++; }
    }
    [0, 1].forEach(function (s) {
      hipJ[s].set(hipJ[s].x / Math.max(1, hc[s]), crotch, hipJ[s].z / Math.max(1, hc[s]));
      kneeJ[s].set(kneeJ[s].x / Math.max(1, kc[s]), knee, kneeJ[s].z / Math.max(1, kc[s]));
    });
    // 4) 받침대를 뺀 새 형상 + 뼈 무게
    var keep = [];
    g0.groups.forEach(function (gr, gi) {
      for (var tt = gr.start / 3; tt < (gr.start + gr.count) / 3; tt++) if (!isBase(tt * 3)) keep.push([tt, gr.materialIndex]);
    });
    if (!g0.groups.length) for (t = 0; t < tri; t++) if (!isBase(t * 3)) keep.push([t, 0]);
    var names = ['position', 'normal', 'uv'].filter(function (nm) { return g0.attributes[nm]; });
    var arrs = {}, m = keep.length * 3;
    names.forEach(function (nm) { arrs[nm] = new Float32Array(m * g0.attributes[nm].itemSize); });
    var sIdx = new Uint16Array(m * 4), sW = new Float32Array(m * 4);
    var geo = new T.BufferGeometry(), lastMat = -1, gStart = 0;
    function smooth(e0, e1, x) { var tq = Math.max(0, Math.min(1, (x - e0) / (e1 - e0))); return tq * tq * (3 - 2 * tq); }
    keep.forEach(function (kt, j) {
      if (kt[1] !== lastMat) { if (lastMat >= 0) geo.addGroup(gStart, j * 3 - gStart, lastMat); lastMat = kt[1]; gStart = j * 3; }
      for (var v = 0; v < 3; v++) {
        var src = kt[0] * 3 + v, dst = j * 3 + v;
        names.forEach(function (nm) {
          var at = g0.attributes[nm], sz = at.itemSize;
          for (var q = 0; q < sz; q++) arrs[nm][dst * sz + q] = at.array[src * sz + q];
        });
        // 뼈: 0 골반(몸·치마·팔·머리), 1/2 왼 허벅지/종아리, 3/4 오른 허벅지/종아리
        var sd = side[find(vid[src])], yy = P.getY(src), o = dst * 4;
        if (sd === undefined || yy >= crotch) { sIdx[o] = 0; sW[o] = 1; continue; }
        var up = 1 + sd * 2, lo = up + 1;
        var wl = smooth(knee + h * 0.03, knee - h * 0.03, yy);          // 무릎 아래로 갈수록 종아리
        var wh = smooth(crotch - h * 0.06, crotch, yy) * 0.6;           // 사타구니 근처는 골반과 섞는다
        sIdx[o] = up; sW[o] = (1 - wl) * (1 - wh);
        sIdx[o + 1] = lo; sW[o + 1] = wl * (1 - wh);
        sIdx[o + 2] = 0; sW[o + 2] = wh;
      }
    });
    geo.addGroup(gStart, m - gStart, lastMat);
    names.forEach(function (nm) { geo.setAttribute(nm, new T.BufferAttribute(arrs[nm], g0.attributes[nm].itemSize)); });
    geo.setAttribute('skinIndex', new T.Uint16BufferAttribute(sIdx, 4));
    geo.setAttribute('skinWeight', new T.Float32BufferAttribute(sW, 4));
    geo.translate(0, -floorY, 0);
    hipJ.forEach(function (v) { v.y -= floorY; }); kneeJ.forEach(function (v) { v.y -= floorY; });
    geo.computeBoundingSphere();
    var mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    return { geo: geo, mats: mats.map(function (mt) { var c2 = mt.clone(); c2.skinning = true; c2.userData.keep = true; return c2; }),
             hip: hipJ, knee: kneeJ, crotch: crotch - floorY, h: h };
  }
  // 묶어 둔 엘프 하나를 만든다 (뼈대는 사람마다 따로)
  function elfWalkerModel(rig) {
    var root = new T.Bone(), pelvis = new T.Bone(); root.add(pelvis); pelvis.position.set(0, rig.crotch, 0);
    var bones = [pelvis], legs = [];
    [0, 1].forEach(function (s) {
      var up = new T.Bone(), lo = new T.Bone();
      up.position.copy(rig.hip[s]).sub(pelvis.position); pelvis.add(up);
      lo.position.copy(rig.knee[s]).sub(rig.hip[s]); up.add(lo);
      bones.push(up, lo); legs.push([up, lo]);
    });
    var sk = new T.SkinnedMesh(rig.geo, rig.mats.length > 1 ? rig.mats : rig.mats[0]);
    sk.add(root); sk.bind(new T.Skeleton(bones));
    sk.castShadow = true; sk.frustumCulled = false;
    return { mesh: sk, root: root, pelvis: pelvis, legs: legs, crotch: rig.crotch };
  }
  // 걷기: 다리를 원래 자세 기준으로 앞뒤로 흔들고, 앞으로 나오는 다리의 무릎을 굽힌다. 골반은 살짝 오르내리고 비튼다.
  function elfPose(m, ph, amt) {
    var s0 = Math.sin(ph), s1 = Math.sin(ph + Math.PI);
    m.legs[0][0].rotation.x = -0.32 * s0 * amt; m.legs[1][0].rotation.x = -0.32 * s1 * amt;
    m.legs[0][1].rotation.x = 0.55 * Math.max(0, Math.sin(ph + 1.1)) * amt;
    m.legs[1][1].rotation.x = 0.55 * Math.max(0, Math.sin(ph + 1.1 + Math.PI)) * amt;
    m.pelvis.position.y = m.crotch + Math.abs(Math.cos(ph)) * m.crotch * 0.025 * amt;
    m.pelvis.rotation.y = 0.06 * s0 * amt;
    m.pelvis.rotation.z = 0.025 * s0 * amt;
  }
  function elfWalker(r) {   // 받침대를 떼고 다리 뼈대를 심은 엘프 (다른 손님처럼 통로를 걷는다)
    var m = elfWalkerModel(HUMAN.elfRig), g = new T.Group();
    m.mesh.scale.setScalar(0.25); g.add(m.mesh);
    return { g: g, elf: m, r: r, phase: r() * 6, sc: 1, walkW: 0 };
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
          HUMAN.beachMat = mat({ pants: 0xe9b995, top: 0xd92f45, skin: 0xe9b995, beach: true });
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
  function dressedHuman(seed, beach) {
    var r = rnd(seed * 7919 + 13);
    if (!beach && HUMAN.man && r() < 0.5) return manHuman(r);
    var model = T.SkeletonUtils.clone(HUMAN.dressed.scene);
    var mat = beach ? HUMAN.beachMat : HUMAN.looks[Math.floor(r() * HUMAN.looks.length)];
    model.traverse(function (o) { if (o.isMesh) { o.material = mat; o.castShadow = true; o.frustumCulled = false; } });
    var g = new T.Group(); g.add(model);
    var head = findBone(model, 'Head'), hips = findBone(model, 'Hips'), handL = findBone(model, 'LeftHand');
    if (beach && hips && head) {   // 숨은 인물: 빨간 비키니 아랫도리·맨다리·밀짚모자
      ['Left', 'Right'].forEach(function (sd) {   // 헐렁한 바지 다리를 맨다리 굵기로
        var up = findBone(model, sd + 'UpLeg'), ft = findBone(model, sd + 'Foot');
        if (up) up.scale.set(0.6, 1, 0.6);
        if (ft) ft.scale.set(1 / 0.6, 1, 1 / 0.6);
      });
      var suit = std(0xd92f45, 0.45);
      var bot = new T.Mesh(new T.CylinderGeometry(0.128, 0.11, 0.085, 24), suit); bot.scale.z = 0.8; onBone(hips, bot, [0, -0.095, 0]);
      var straw = std(0xe9d29a, 0.85);
      var brim = new T.Mesh(new T.CylinderGeometry(0.3, 0.3, 0.012, 32), straw); onBone(head, brim, [0, 0.2, 0]);
      var crown = new T.Mesh(new T.CylinderGeometry(0.11, 0.13, 0.11, 24), straw); onBone(head, crown, [0, 0.255, 0]);
      var band = new T.Mesh(new T.CylinderGeometry(0.131, 0.131, 0.025, 24), suit); onBone(head, band, [0, 0.215, 0]);
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
    { k: 'trooper', label: '스톰트루퍼' }, { k: 'elf', label: '엘프' }, { k: 'beach', label: '숨은 인물(비키니)' },
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
      if (HUMAN.elfRig) walker(elfWalker(rnd(seed * 163 + 17 + i * 23)), 1.0, i === 0 ? 0 : undefined);
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
    if (p.elf) {   // 엘프는 직접 심은 다리 뼈대를 걸음에 맞춰 흔든다 (한 걸음 주기 약 0.95m)
      p.phase += dt * p.speed * p.walkW * (Math.PI * 2 / 0.95);
      elfPose(p.elf, p.phase, p.walkW);
      return;
    }
    if (p.acts.walk) { p.acts.walk.setEffectiveWeight(p.walkW); p.acts.walk.timeScale = p.speed / 1.25; }
    if (p.acts.idle) p.acts.idle.setEffectiveWeight(1 - p.walkW);
    p.mixer.update(dt);
    applyLook(p, now);
  }

  function updatePeople(dt, now) {
    for (var i = 0; i < people.length; i++) {
      var p = people[i];
      if (p.mixer || p.elf) { updateHuman(p, dt, now); continue; }
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
  function hashNav() {
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
  var shared = Object.keys(M).map(function (k) { return M[k]; });
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
    spawnPeople(fl, i + 1);
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
    if (!reading) updatePeople(dt, now);
    acc += dt;
    if (acc > 0.3) { acc = 0; loadNear(); where(); }
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
