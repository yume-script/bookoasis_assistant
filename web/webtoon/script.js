(function () {
  // 이 파일은 코어에 의해 new Function('pluginId', 'container', js)(pluginId, container)
  // 형태로 실행되는 것으로 확인됨(RCLONE_MANAGER 등 기존 플러그인과 동일 컨벤션).
  // pluginId, container 는 바깥 스코프에서 주입됨.

  // 같은 탭 컨테이너에 이 스크립트가 두 번 이상 실행되면(탭 재진입 등) 클릭 핸들러와
  // 폴링이 중복 등록되어 확인창/알림창이 두 번씩 뜬다. 가장 최근 실행만 동작하게 한다.
  var myInst = {};
  container.__wtmInst = myInst;
  function alive() { return container.__wtmInst === myInst; }

  var dbType = (container.dataset && container.dataset.dbType) ||
    (window.currentDbType) ||
    (window.BookOasisDbType) ||
    'general';

  // 독립형: app.py 웹 서버의 /api/wtm/… (플러그인 시절 BookOasis 대시보드 위젯 데이터 경로 대신)
  var DATA_URL = 'api/wtm/data';

  // 코어 소스(api/routes/plugin_routes.py)를 직접 grep해서 확인된 유일한 진짜
  // 액션 엔드포인트. run_context_menu_action(db_type, action_id, context)로
  // 라우팅되며, 요청 바디는 최상위 필드로 type/plugin_id/action_id/context 만
  // 읽는다(item_data, book_id, db_type 같은 이름은 서버가 읽지 않음 — 넣어도
  // 무해하지만 무시됨).
  var ACTION_URL = 'api/wtm/action';

  function el(sel) { return container.querySelector(sel); }
  function els(sel) { return Array.prototype.slice.call(container.querySelectorAll(sel)); }

  function fmtDate(ts) {
    if (!ts) return '';
    var d = new Date(ts * 1000);
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' +
      String(d.getDate()).padStart(2, '0') + ' ' + String(d.getHours()).padStart(2, '0') + ':' +
      String(d.getMinutes()).padStart(2, '0');
  }

  async function fetchData() {
    var resp = await fetch(DATA_URL, { credentials: 'same-origin' });
    if (!resp.ok) throw new Error('데이터 조회 실패: HTTP ' + resp.status);
    var body = await resp.json();
    var items = body.items || (body.data && body.data.items) || [];
    return items[0] || {
      titles: [], authors_tags: { authors: [], tags: [] }, history: [], job: {}, log_tail: [],
      update_status: {}, repo_url: 'https://github.com/yume-script/webtoon_manager'
    };
  }

  async function callAction(actionId, payload) {
    payload = payload || {};
    // 코어 라우트가 실제로 읽는 필드만 최상위에 둔다: type(=db_type), plugin_id,
    // action_id, context. (예전엔 db_type이라는 이름으로 보내서 서버가 못 읽고
    // 매번 general로 취급되던 버그가 있었음 — type으로 고침.)
    var body = {
      type: dbType,
      plugin_id: pluginId,
      action_id: actionId,
      context: Object.assign({ action: actionId }, payload)
    };

    try {
      var bodyText = JSON.stringify(body);
      var sendText = bodyText;
      // 쿠키 JSON처럼 큰 요청은 gzip으로 줄여 보낸다 - 앞단 프록시가 8~16KB가 넘는 요청에서 오류를 내는 경우가 있다
      if (bodyText.length > 4000 && window.CompressionStream) {
        try {
          var gzBuf = await new Response(new Blob([bodyText]).stream().pipeThrough(new CompressionStream('gzip'))).arrayBuffer();
          var bytes = new Uint8Array(gzBuf), bin = '';
          for (var bi = 0; bi < bytes.length; bi += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(bi, bi + 0x8000));
          sendText = JSON.stringify({ gz: btoa(bin) });
        } catch (gzErr) { sendText = bodyText; }
      }
      var resp = await fetch(ACTION_URL, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: sendText
      });
      var respText = await resp.text();
      var data;
      try {
        data = JSON.parse(respText);
      } catch (parseErr) {
        // 이 프로그램은 오류도 JSON으로 답한다. HTML이 왔다면 앞단(리버스 프록시 등)이 요청을 막은 것
        var t = /<title>([^<]*)<\/title>/i.exec(respText) || /<h1>([^<]*)<\/h1>/i.exec(respText);
        var why = t ? t[1].trim() : 'HTTP ' + resp.status;  // nginx 제목에는 상태 코드가 들어 있다
        var hint = resp.status === 413
          ? '리버스 프록시의 요청 크기 제한에 걸렸습니다(nginx: client_max_body_size 10m; 추가 후 nginx 재시작)'
          : '리버스 프록시(nginx 등)가 요청을 이 프로그램에 전달하지 않았습니다 - 프록시 오류 로그를 확인하세요';
        return { success: false, message: '요청이 거부됨: ' + why + ' (보낸 크기 ' + Math.round(sendText.length / 1024) + 'KB)\n' + hint };
      }
      // 코어는 run_context_menu_action()이 {'success': bool, 'message'|'error': str}
      // dict를 반환할 것으로 기대하고, success=false면 HTTP 400으로 내려준다.
      // resp.ok(2xx) 여부가 아니라 data.success로 성공/실패를 판단해야 한다.
      var success = !!data.success;
      var message = data.message || data.error || '';
      return { success: success, message: message, raw: data };
    } catch (e) {
      var errMsg = e.message || String(e);
      console.error('[webtoon_manager] 액션 호출 실패:', errMsg);
      return { success: false, message: '액션 호출 실패: ' + errMsg };
    }
  }

  function parseMaybeJson(text) {
    if (typeof text !== 'string') return text;
    try { return JSON.parse(text); } catch (e) { return null; }
  }

  // ------------------------------------------------------------------
  // 상태
  // ------------------------------------------------------------------
  var state = { titles: [], authors_tags: { authors: [], tags: [] }, history: [], job: {}, log_tail: [] };
  var currentTab = 'all';
  var searchQuery = '';
  var dayFilter = 'all';
  var platformFilter = 'all';
  var sortMode = 'default';
  var lookupResult = null;
  var pollTimer = null;
  var pollFastUntil = 0;
  var librariesLoaded = false;

  function statusOf(t) {
    if (t.excluded) return 'excluded';
    if (t.unsubscribed) return 'unsubscribed';
    if (t.subscribed) return 'subscribed';
    return 'all';
  }

  function filteredTitles() {
    var list = state.titles.slice();
    if ((state.config_public || {}).HIDE_BL_GL) list = list.filter(function (t) { return !t.bl && !t.gl; });  // 설정 > 공통
    if (currentTab === 'subscribed') list = list.filter(function (t) { return t.subscribed && !t.excluded && !t.unsubscribed; });
    else if (currentTab === 'unsubscribed') list = list.filter(function (t) { return t.unsubscribed; });
    else if (currentTab === 'excluded') list = list.filter(function (t) { return t.excluded; });
    else if (currentTab === 'duplicate') list = list.filter(function (t) { return t.in_library === true; });
    // 'all' 은 필터 없이 전체

    if (platformFilter === 'novel') {
      list = list.filter(function (t) { return !!t.novel; });
    } else if (platformFilter === 'kakao') {
      list = list.filter(function (t) { return t.platform === 'kakao' && !t.novel; });
    } else if (platformFilter !== 'all') {
      list = list.filter(function (t) { return (t.platform || 'naver') === platformFilter; });
    }

    if (dayFilter === 'finished') {
      list = list.filter(function (t) { return t.status === '완결'; });
    } else if (dayFilter === 'new') {
      list = list.filter(function (t) { return !!t.new; });
    } else if (dayFilter === 'waitfree') {
      list = list.filter(function (t) { return !!t.waitfree && t.status !== '완결'; });
    } else if (dayFilter !== 'all') {
      list = list.filter(function (t) { return (t.weekdays || []).indexOf(dayFilter) >= 0; });
    }

    if (searchQuery) {
      var q = searchQuery.toLowerCase();
      list = list.filter(function (t) {
        return (t.title || '').toLowerCase().indexOf(q) >= 0 ||
          (t.author || '').toLowerCase().indexOf(q) >= 0;
      });
    }

    if (sortMode === 'rating') {
      list.sort(function (a, b) {
        var diff = (b.rating == null ? -1 : b.rating) - (a.rating == null ? -1 : a.rating);
        if (diff !== 0) return diff;
        // 평점이 같으면(=동점) titleId로 순서를 고정한다. 서버가 주는 원래
        // 배열 순서(last_seen_at)로 동점자를 처리하면, 스캔이 진행 중일 때
        // last_seen_at이 계속 바뀌면서 화면이 매번 흔들리기 때문.
        return String(a.titleId).localeCompare(String(b.titleId));
      });
    } else if (sortMode === 'title') {
      list.sort(function (a, b) {
        var diff = (a.title || '').localeCompare(b.title || '', 'ko');
        if (diff !== 0) return diff;
        return String(a.titleId).localeCompare(String(b.titleId));
      });
    }
    // 'default' 는 이미 last_seen_at 내림차순으로 정렬된 state.titles 순서 그대로 사용

    return list;
  }

  function badgeHtml(t) {
    var out = '';
    if (t.platform === 'kakao') {
      out += '<span class="wtm-badge" style="background:color-mix(in srgb, #f5c400 30%, transparent);color:color-mix(in srgb, #b08a00 90%, var(--app-text-primary))">카카오</span>';
    } else {
      out += '<span class="wtm-badge" style="background:color-mix(in srgb, #03c75a 22%, transparent);color:color-mix(in srgb, #03a14a 90%, var(--app-text-primary))">네이버</span>';
    }
    if (t.waitfree) {  // 기다무: 충전 주기(3시간 등)와 다음 대여권 사용 가능 시각
      var wp = t.waitfree_period_min || 1440;
      var wl = wp % 1440 === 0 ? (wp / 1440 === 1 ? '' : (wp / 1440) + '일 ') : (wp % 60 === 0 ? (wp / 60) + '시간 ' : wp + '분 ');
      var when = function (sec) {
        var d = new Date(sec * 1000);
        return d <= new Date() ? '충전됨' : (d.getMonth() + 1) + '/' + d.getDate() + ' ' +
          String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
      };
      var wt = (t.waitfree_accounts || []).length > 1
        ? '다음 대여권 - ' + t.waitfree_accounts.map(function (a) { return '계정' + a[0] + ' ' + when(a[1]); }).join(' / ')
        : (t.waitfree_next ? '다음 대여권 ' + when(t.waitfree_next) : '');
      out += '<span class="wtm-badge up"' + (wt ? ' title="' + wt + '"' : '') + '>' + wl + '기다무</span>';
    }
    if (t.purchased) out += '<span class="wtm-badge new" title="카카오페이지 보관함 > 구매 목록에 있는 작품 - 구독하지 않아도 구매·대여 회차를 받습니다">구매</span>';
    if (t.bl) out += '<span class="wtm-badge rest" title="' + ((state.config_public || {}).ALLOW_BL ? 'BL 장르' : 'BL 장르 - [설정] > [공통]에서 허용해야 다운로드됨') + '">BL' + ((state.config_public || {}).ALLOW_BL ? '' : ' (받지 않음)') + '</span>';
    if (t.gl) out += '<span class="wtm-badge rest" title="' + ((state.config_public || {}).ALLOW_GL ? 'GL 장르' : 'GL 장르 - [설정] > [공통]에서 허용해야 다운로드됨') + '">GL' + ((state.config_public || {}).ALLOW_GL ? '' : ' (받지 않음)') + '</span>';
    if (t.novel) out += '<span class="wtm-badge" style="background:color-mix(in srgb, #8a63d2 22%, transparent);color:color-mix(in srgb, #8a63d2 90%, var(--app-text-primary))"' +
      ((state.config_public || {}).KAKAO_NOVEL_ENABLE ? '>웹소설' : ' title="[설정] > [카카오페이지]에서 카카오 웹소설 사용을 켜야 받음">웹소설(사용 꺼짐)') + '</span>';
    if (t.new) out += '<span class="wtm-badge new">신작</span>';
    if (t.status === '완결') out += '<span class="wtm-badge finished">완결</span>';
    if (t.rest) out += '<span class="wtm-badge rest">휴재</span>';
    if (t.up_flag) out += '<span class="wtm-badge up">UP</span>';
    if (t.in_library === true) {
      var srcTip = (t.in_library_src && t.in_library_src.length) ? ('\n' + t.in_library_src.join('\n')) : '';
      out += '<span class="wtm-badge" style="background:color-mix(in srgb, #c58a3a 22%, transparent);' +
        'color:color-mix(in srgb, #c58a3a 90%, var(--app-text-primary))" ' +
        'title="' + escapeHtml('같은 이름의 시리즈가 이미 있습니다(제목 비교라 정확하지 않을 수 있음)' + srcTip) + '">' +
        '📚 보유중</span>';
    }
    return out;
  }

  function cardActionsHtml(t) {
    var st = statusOf(t);
    var pAttr = ' data-platform="' + (t.platform || 'naver') + '"';
    // 새 회차 디스코드 알림 켜기/끄기(구독 중인 작품에만 표시)
    var bell = '<button class="wtm-btn wtm-btn-small' + (t.notify_new ? ' wtm-btn-primary' : ' wtm-btn-ghost') +
      '" data-card-action="toggle_notify" data-title-id="' + escapeHtml(t.titleId) + '"' + pAttr +
      ' title="' + (t.notify_new ? '새 회차 알림 켜짐 - 누르면 끔' : '새 회차를 받으면 디스코드로 알림') + '">' +
      (t.notify_new ? '🔔' : '🔕') + '</button>';
    // 텔레그램 채널 업로드 켜기/끄기: 켜면 받은 회차 전부 + 이후 새 회차
    var tg = '<button class="wtm-btn wtm-btn-small' + (t.telegram_upload ? ' wtm-btn-primary' : ' wtm-btn-ghost') +
      '" data-card-action="toggle_telegram" data-title-id="' + escapeHtml(t.titleId) + '"' + pAttr +
      ' title="' + (t.telegram_upload ? '텔레그램 업로드 켜짐 - 누르면 끔(대기 중인 회차 취소)' : '받은 회차 전부와 이후 새 회차를 텔레그램 채널에 올림') + '">' +
      '📤 텔레그램' + (t.telegram_upload ? ' ON' : '') + '</button>';
    if (t.platform === 'kakao') {
      var sid = escapeHtml(t.titleId);
      var open = '<a class="wtm-btn wtm-btn-small wtm-btn-ghost" href="https://page.kakao.com/content/' + sid + '" target="_blank" rel="noopener">열기</a>';
      var res = t.last_result ? '<div class="wtm-card-author" style="width:100%" title="마지막 확인 결과">' + escapeHtml(t.last_result) + '</div>' : '';
      if (st === 'subscribed') {
        return res + '<button class="wtm-btn wtm-btn-small wtm-btn-primary" data-card-action="download_title" data-title-id="' + sid + '"' + pAttr + ' title="받지 않은 회차 중 볼 수 있는 회차(무료/대여·소장)를 지금 받습니다">새회차 다운로드</button>' +
          '<button class="wtm-btn wtm-btn-small" data-goto-manual="' + sid + '"' + pAttr + '>선택 회차 다운로드</button>' +
          '<button class="wtm-btn wtm-btn-small" data-card-action="resync_title" data-title-id="' + sid + '"' + pAttr + ' title="파일을 직접 지운 회차가 있으면 눌러주세요 - 다음 다운로드 때 전체 회차를 다시 확인합니다">다시 확인</button>' +
          '<button class="wtm-btn wtm-btn-small" data-card-action="unsubscribe" data-title-id="' + sid + '"' + pAttr + '>구독해제</button>' +
          '<button class="wtm-btn wtm-btn-small wtm-btn-danger" data-card-action="exclude" data-title-id="' + sid + '"' + pAttr + '>제외</button>' + bell + tg + open;
      }
      if (st === 'unsubscribed' || st === 'excluded') {
        return res + '<button class="wtm-btn wtm-btn-small wtm-btn-primary" data-card-action="restore" data-title-id="' + sid + '"' + pAttr + '>다시 구독</button>' + tg + open;
      }
      return '<button class="wtm-btn wtm-btn-small wtm-btn-primary" data-card-action="subscribe" data-title-id="' + sid + '"' + pAttr + '>구독</button>' +
        '<button class="wtm-btn wtm-btn-small wtm-btn-danger" data-card-action="exclude" data-title-id="' + sid + '"' + pAttr + '>제외</button>' + open;
    }
    // 네이버 작품 페이지로 이동(카카오 카드의 [열기]와 동일)
    var nOpen = '<a class="wtm-btn wtm-btn-small wtm-btn-ghost" href="https://comic.naver.com/webtoon/list?titleId=' +
      encodeURIComponent(t.titleId) + '" target="_blank" rel="noopener">열기</a>';
    if (st === 'subscribed') {
      return '<button class="wtm-btn wtm-btn-small wtm-btn-primary" data-card-action="download_title" data-title-id="' + t.titleId + '" title="last_downloaded_no 이후의 새 회차를 지금 바로 찾아서 받습니다">새회차 다운로드</button>' +
        '<button class="wtm-btn wtm-btn-small" data-goto-manual="' + t.titleId + '">선택 회차 다운로드</button>' +
        '<button class="wtm-btn wtm-btn-small" data-card-action="resync_title" data-title-id="' + t.titleId + '" title="파일을 직접 지운 회차가 있으면 눌러주세요 - 다음 다운로드 때 전체 회차를 다시 확인합니다">다시 확인</button>' +
        '<button class="wtm-btn wtm-btn-small" data-card-action="unsubscribe" data-title-id="' + t.titleId + '">구독해제</button>' +
        '<button class="wtm-btn wtm-btn-small wtm-btn-danger" data-card-action="exclude" data-title-id="' + t.titleId + '">제외</button>' + bell + tg + nOpen;
    }
    if (st === 'unsubscribed' || st === 'excluded') {
      return '<button class="wtm-btn wtm-btn-small wtm-btn-primary" data-card-action="restore" data-title-id="' + t.titleId + '">다시 구독</button>' + tg + nOpen;
    }
    return '<button class="wtm-btn wtm-btn-small wtm-btn-primary" data-card-action="subscribe" data-title-id="' + t.titleId + '">구독</button>' +
      '<button class="wtm-btn wtm-btn-small wtm-btn-danger" data-card-action="exclude" data-title-id="' + t.titleId + '">제외</button>' + nOpen;
  }

  function compareStatusText() {
    var cs = state.compare_status || {};
    var warn = (cs.errors && cs.errors.length) ? ('⚠️ ' + escapeHtml(cs.errors.join(' / ')) + '<br>') : '';
    if (warn && !cs.enabled) return warn;
    if (!cs.enabled) {
      return '중복 확인이 설정되지 않았습니다. [설정]의 <b>[공통] 중복 확인 폴더(공통)</b>, ' +
        '<b>[네이버] 중복 확인 폴더</b>, <b>[카카오페이지] 중복 확인 폴더(웹툰/웹소설)</b>에 ' +
        '이미 갖고 있는 폴더 경로를 한 줄에 하나씩 넣어주세요.';
    }
    return warn + '중복 확인 기준: ' + escapeHtml((cs.sources || []).join(' + ')) +
      ' / 비교 대상 시리즈 ' + (cs.count || 0) + '개';
  }

  function emptyMessage() {
    if (currentTab === 'duplicate') {
      var cs = state.compare_status || {};
      if (!cs.enabled || (cs.errors && cs.errors.length)) return compareStatusText();
      return '중복된 작품이 없습니다. (' + compareStatusText() + ')';
    }
    return '표시할 작품이 없습니다. "지금 스캔"을 먼저 실행해보세요.';
  }

  // 카드는 한 번에 GRID_PAGE개씩만 그린다(수천 장을 한꺼번에 DOM에 넣으면
  // 브라우저 CPU/메모리를 크게 잡아먹음). 필터가 바뀌면 처음부터 다시.
  var GRID_PAGE = 120;
  var gridLimit = GRID_PAGE;
  var gridFilterKey = '';

  function renderGrid() {
    var grid = el('[data-el="title-grid"]');
    if (!grid) return;
    var fkey = [currentTab, dayFilter, platformFilter, searchQuery].join('|');
    if (fkey !== gridFilterKey) { gridFilterKey = fkey; gridLimit = GRID_PAGE; }
    var fullList = filteredTitles();
    if (!fullList.length) {
      grid.innerHTML = '<div class="wtm-hint">' + emptyMessage() + '</div>';
      return;
    }
    var list = fullList.slice(0, gridLimit);
    var more = fullList.length - list.length;
    grid.innerHTML = list.map(function (t) {
      return '<div class="wtm-card">' +
        (t.thumbnail ? '<img class="wtm-card-thumb" src="' + escapeHtml(t.thumbnail) + '" loading="lazy"' + (t.platform === 'kakao' ? ' referrerpolicy="no-referrer"' : '') + '>' :
          '<div class="wtm-card-thumb"></div>') +
        '<div class="wtm-card-body">' +
        '<div class="wtm-card-title">' + escapeHtml(t.title || t.titleId) + '</div>' +
        '<div class="wtm-card-author">' + escapeHtml(t.author || '') + '</div>' +
        (t.rating != null ? '<div class="wtm-card-rating">★ ' + t.rating.toFixed(2) + '</div>' : '') +
        '<div class="wtm-badges">' + badgeHtml(t) + '</div>' +
        '<div class="wtm-card-actions">' + cardActionsHtml(t) + '</div>' +
        '</div></div>';
    }).join('') + (more > 0
      ? '<div style="grid-column:1/-1;text-align:center;padding:8px"><button class="wtm-btn wtm-btn-secondary" data-el="grid-more">더 보기 (' +
        list.length + ' / ' + fullList.length + ')</button></div>'
      : '');
  }

  function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function renderAuthorsTags() {
    var at = state.authors_tags || { authors: [], tags: [] };
    var authorList = el('[data-el="author-list"]');
    var tagList = el('[data-el="tag-list"]');
    if (authorList) {
      authorList.innerHTML = (at.authors || []).map(function (a) {
        return '<span class="wtm-chip">' + escapeHtml(a) +
          '<button data-chip-remove="author" data-value="' + escapeHtml(a) + '">&times;</button></span>';
      }).join('') || '<span class="wtm-hint">등록된 작가 없음</span>';
    }
    if (tagList) {
      tagList.innerHTML = (at.tags || []).map(function (a) {
        return '<span class="wtm-chip">' + escapeHtml(a) +
          '<button data-chip-remove="tag" data-value="' + escapeHtml(a) + '">&times;</button></span>';
      }).join('') || '<span class="wtm-hint">등록된 태그 없음</span>';
    }
  }

  var historyFilter = 'all';
  var PLATFORM_LABELS = { naver: '네이버웹툰', kakao: '카카오웹툰', kakao_novel: '카카오웹소설' };
  var PLATFORM_COLORS = { naver: '#03c75a', kakao: '#e0b400', kakao_novel: '#8a63d2' };

  function historyPlatform(h) {
    if (h.platform === 'kakao_novel' || h.platform === 'naver') return h.platform;
    var isKakao = h.platform === 'kakao' || h.source === 'kakao' || /^\[카카오\]/.test(h.title || '');
    if (!isKakao) return 'naver';
    // 예전 이력은 웹소설 여부가 없어 목록 정보로 판단
    var tt = (state.titles || []).filter(function (x) { return x.platform === 'kakao' && String(x.titleId) === String(h.title_id); })[0];
    return tt && tt.novel ? 'kakao_novel' : 'kakao';
  }

  var _wfMap = { src: null, map: {} };
  function waitfreeLabel(h) {  // 카카오 작품의 기다무 충전 주기 → '3시간 기다무' (작품 목록에 없으면 '')
    if (_wfMap.src !== state.titles) {
      _wfMap = { src: state.titles, map: {} };
      (state.titles || []).forEach(function (x) {
        if (x.platform === 'kakao' && x.waitfree) _wfMap.map[String(x.titleId)] = x.waitfree_period_min || 1440;
      });
    }
    var m = _wfMap.map[String(h.title_id)];
    if (!m) return '';
    return (m % 1440 === 0 ? (m / 1440) + '일' : (m % 60 === 0 ? (m / 60) + '시간' : m + '분')) + ' 기다무';
  }

  function lateText(sec) {  // 기다무 지연: '정시', '12분 지연', '2시간 5분 지연'
    var m = Math.floor((sec || 0) / 60);
    if (m < 1) return '정시';
    var t = m < 60 ? m + '분' : (m < 1440 ? Math.floor(m / 60) + '시간' + (m % 60 ? ' ' + (m % 60) + '분' : '')
      : Math.floor(m / 1440) + '일' + (m % 1440 >= 60 ? ' ' + Math.floor(m % 1440 / 60) + '시간' : ''));
    return t + ' 지연';
  }

  function platformBadge(p) {
    var c = PLATFORM_COLORS[p] || '#888';
    return '<span class="wtm-badge" style="margin-right:6px;background:color-mix(in srgb, ' + c + ' 22%, transparent);' +
      'color:color-mix(in srgb, ' + c + ' 85%, var(--app-text-primary))">' + (PLATFORM_LABELS[p] || p) + '</span>';
  }

  function historyEpLabel(h) {
    var no = h.episode_no;
    var label = (no >= 9000) ? ('특별회차(파일 ' + no + '화)') : (no + '화');
    var sub = (h.subtitle || '').trim();
    var title = (h.title || '').replace(/^\[카카오\]\s*/, '');
    // 회차 제목이 "작품명 N화"면 중복이라 생략, 그 외(프롤로그/외전 등)는 함께 표시
    if (sub && sub !== title + ' ' + no + '화' && sub.indexOf(title) !== 0) label += ' "' + escapeHtml(sub) + '"';
    else if (sub && no >= 9000) label += ' "' + escapeHtml(sub.replace(title, '').trim()) + '"';
    return label;
  }

  function renderHistory() {
    var box = el('[data-el="history-list"]');
    if (!box) return;
    // '전체'는 플랫폼마다 최근 200개씩 받아 섞은 것이라, 많이 받는 플랫폼(카카오)의 200개가 끝나는 시각보다 오래된
    // 것은 빼고 보여 준다 (그 아래로는 다른 플랫폼만 남아 이력이 끊긴 것처럼 보였다). 더 이전 것은 플랫폼 탭에서.
    var cutoff = historyFilter === 'all' ? (state.history_cutoff || 0) : 0;
    var all = (state.history || []).filter(function (h) {
      return historyFilter === 'all' || historyPlatform(h) === historyFilter;
    });
    var list = all.filter(function (h) { return !cutoff || (h.ts || 0) >= cutoff; });
    var hidden = all.length - list.length;
    if (!list.length) { box.innerHTML = daysTable() + '<div class="wtm-hint">다운로드 이력이 없습니다.</div>'; return; }
    box.innerHTML = daysTable() + list.map(function (h) {
      var isFail = (h.type || '').indexOf('fail') >= 0;
      // source 필드가 없는 예전 이력(업데이트 전에 쌓인 기록)은 type 이름으로
      // 대신 추정한다 - manual_download(_fail)만 수동이고 나머지는 자동.
      var isManual = h.source ? h.source === 'manual' : (h.type || '').indexOf('manual') >= 0;
      var isPurchased = h.source === 'purchased';
      var sourceBadge = '<span class="wtm-badge' + (isManual ? '' : ' new') + '" style="margin-right:6px">' +
        (isPurchased ? '구매' : (isManual ? '수동' : '자동')) + '</span>';
      var plat = historyPlatform(h);
      var title = escapeHtml((h.title || '').replace(/^\[카카오\]\s*/, ''));
      var unit = (h.unit === 'words' || plat === 'kakao_novel') ? '단어' : '장';
      var text = '';
      if (h.type === 'download' || h.type === 'manual_download') {
        text = '<b>' + title + '</b> - ' + historyEpLabel(h) + ' (' + (h.image_count || 0) + unit + ')';
        // 카카오: 어느 계정으로, 무엇(기다무·대여권·대여/소장·무료)으로 연 회차인지
        if (h.account || h.via) {
          var via = h.via || '';
          if (via === '기다무') via = waitfreeLabel(h) || via;  // 예전 이력: 작품 정보의 충전 주기로 '3시간 기다무'
          // 기다무: 충전 예정 시각보다 얼마나 늦게 썼는지 (처음 쓰는 작품은 기록 없음)
          if (h.late_sec != null && /기다무/.test(via)) via += ' · ' + lateText(h.late_sec);
          var viaPaid = via && via !== '무료';
          text += ' <span class="wtm-badge' + (viaPaid ? ' up' : '') + '">' +
            escapeHtml((h.account ? '계정' + h.account : '') + (h.account && via ? ' · ' : '') + via) + '</span>';
        }
      } else if (h.type === 'skipped_paid') {
        text = '<b>' + title + '</b> - ' + historyEpLabel(h) + ': 유료라 건너뜀' +
          (h.error ? ' (' + escapeHtml(h.error) + ')' : '');
      } else if (isFail) {
        text = '<b>' + title + '</b> - ' + historyEpLabel(h) + ' 실패: ' + escapeHtml(h.error || '');
      } else {
        text = escapeHtml(JSON.stringify(h));
      }
      return '<div class="wtm-history-item' + (isFail ? ' fail' : '') + '">' +
        sourceBadge + platformBadge(plat) + '<span>' + fmtDate(h.ts) + '</span> &middot; ' + text + '</div>';
    }).join('') + (hidden > 0 ? '<div class="wtm-hint">' + fmtDate(cutoff) + ' 이전 이력 ' + hidden +
      '개는 네이버웹툰·카카오웹툰·카카오웹소설 탭에서 볼 수 있습니다 (전체 탭은 플랫폼마다 최근 200개를 섞어 보여 주므로 그보다 오래된 것은 뺌).</div>' : '');
  }


  function renderSettingsSummary() {
    var box = el('[data-el="settings-summary"]');
    if (!box) return;
    var cfg = state.config_public || {};
    var rows = [
      ['쿠키 등록', cfg.has_cookie ? '등록됨' : '(미설정)'],
      ['다운로드 경로', cfg.DOWNLOAD_ROOT || '(기본값)'],
      ['임시 작업 경로', cfg.TEMP_DOWNLOAD_ROOT || '(기본값)'],
      ['자동 실행', cfg.ENABLE_SCHEDULER ? ('사용 / ' + cfg.INTERVAL_MINUTES + '분 주기') : '사용 안 함'],
      ['신간 자동 구독', cfg.AUTO_SUBSCRIBE_NEW_TITLES ? '사용' : '사용 안 함(관심 작가만 자동구독)'],
      ['매일+ 작품 받기', cfg.NAVER_DOWNLOAD_DAILY_PLUS ? '받음' : '받지 않음'],
      ['ComicInfo.xml 생성', cfg.GENERATE_COMICINFO_XML ? '사용' : '사용 안 함'],
      ['메인 이미지 1페이지 포함', cfg.ADD_COVER_AS_FIRST_PAGE ? '사용' : '사용 안 함'],
      ['series.json 생성(BookOasis 스캐너용)', cfg.GENERATE_SERIES_JSON ? '사용' : '사용 안 함'],
      ['카카오페이지', cfg.KAKAO_ENABLE ? ('사용' + (cfg.KAKAO_DOWNLOAD_WAITFREE ? ' / 기다무 받음' : ' / 기다무 안 받음') + (cfg.KAKAO_USE_WAITFREE ? ' / 대여권 사용' : '') + (cfg.KAKAO_AUTO ? ' / 자동 실행 포함' : '')) : '사용 안 함'],
      ['kavita.yaml 생성', cfg.GENERATE_KAVITA_YAML ? ('사용' + (cfg.KAVITA_YAML_EMBED_COVER ? ' / 표지 포함' : '')) : '사용 안 함'],
      ['서버 리소스 양보', cfg.LOW_PRIORITY_MODE ? ('사용 / nice ' + cfg.DOWNLOAD_NICE_LEVEL) : '사용 안 함'],
      ['중복 확인', (state.compare_status && state.compare_status.enabled) ?
        ((state.compare_status.sources || []).join(' + ') + ' / ' + state.compare_status.count + '개') :
        '설정 안 됨'],
      ['zip 무압축 저장', cfg.ZIP_STORED ? '사용(CPU 절약)' : '사용 안 함(DEFLATE 압축)'],
      ['작품당 최대 신규 다운로드', cfg.MAX_NEW_EPISODES_PER_TITLE],
      ['알림', (cfg.notify_channels && cfg.notify_channels.length) ? cfg.notify_channels.join(', ') : '(미설정)']
    ];
    box.innerHTML = rows.map(function (r) {
      return '<div><b>' + r[0] + '</b><br>' + escapeHtml(String(r[1])) + '</div>';
    }).join('');

    var logBox = el('[data-el="log-tail"]');
    if (logBox) logBox.textContent = (state.log_tail || []).join('\n');

    syncCompareLibrarySelect();
  }

  async function loadLibraryOptionsIfNeeded() {
    var sel = el('[data-el="compare-library-select"]');
    if (!sel || librariesLoaded) { syncCompareLibrarySelect(); return; }
    var r = await callAction('list_libraries', {});
    if (r.success) {
      var data = parseMaybeJson(r.message);
      var libs = (data && data.libraries) || [];
      sel.innerHTML = '<option value="">사용 안 함</option>' +
        libs.map(function (l) {
          return '<option value="' + l.id + '">' + escapeHtml(l.name) + '</option>';
        }).join('');
      librariesLoaded = true;
    }
    syncCompareLibrarySelect();
  }

  function syncCompareLibrarySelect() {
    var sel = el('[data-el="compare-library-select"]');
    if (!sel) return;
    var cfg = state.config_public || {};
    var current = sel.getAttribute('data-current') || cfg.COMPARE_LIBRARY_ID || '';
    // 옵션 목록이 아직 안 불러와졌으면(첫 렌더) 값만 기억해뒀다가, 목록이
    // 로드된 뒤 다시 이 함수가 불려서 실제로 선택된다.
    if (sel.value !== current && el('option[value="' + current + '"]')) {
      sel.value = current;
    }
    var statusEl = el('[data-el="compare-library-status"]');
    if (statusEl) {
      var lines = [];
      ((state.compare_status || {}).folders || []).forEach(function (f) {
        lines.push(escapeHtml(f.scope) + ' 폴더: ' + escapeHtml(f.path) +
          (f.error ? ' ⚠️ ' + escapeHtml(f.error) : ' (' + (f.count || 0) + '개)'));
      });
      if (cfg.COMPARE_LIBRARY_ID) {
        lines.push('라이브러리: ' + escapeHtml(cfg.COMPARE_LIBRARY_NAME || cfg.COMPARE_LIBRARY_ID));
      }
      statusEl.innerHTML = (lines.length ? lines.join('<br>') + '<br>' : '') + compareStatusText();
    }
  }

  function fmtBytes(n) {
    n = n || 0;
    return n >= 107374182 ? (n / 1073741824).toFixed(2) + 'GB' : Math.round(n / 1048576) + 'MB';
  }

  // 날짜별 받은 회차·용량 (다운로드 이력 탭 위)
  function daysTable() {
    var days = (state.speed && state.speed.days) || [];
    if (!days.length) return '';
    var cell = function (r) { return r && r.count ? r.count + '화 · ' + fmtBytes(r.bytes) : '-'; };
    var rows = days.map(function (d) {
      return '<tr><td>' + escapeHtml(d.day.slice(5)) + '</td><td><b>' + cell(d) + '</b></td><td>' + cell(d.naver) +
        '</td><td>' + cell(d.kakao) + '</td><td>' + cell(d.kakao_novel) + '</td></tr>';
    }).join('');
    return '<table class="wtm-days-table"><thead><tr><th>날짜</th><th>합계</th><th>네이버웹툰</th><th>카카오웹툰</th>' +
      '<th>카카오웹소설</th></tr></thead><tbody>' + rows + '</tbody></table>';
  }

  // 최근 1시간 다운로드 속도 + 고속 모드/서버 제한 상태
  function speedLine() {
    var sp = state.speed;
    if (!sp) return '';
    var txt = '최근 1시간 ' + (sp.total || 0) + '화 (네이버 ' + (sp.naver || 0) + ' · 카카오 ' + (sp.kakao || 0) + ')';
    if (sp.days && sp.days[0] && sp.days[0].count) txt += ' · 오늘 ' + sp.days[0].count + '화 ' + fmtBytes(sp.days[0].bytes);
    txt += sp.fast ? ' · 고속 모드' : '';
    if (sp.telegram) {  // 텔레그램 채널 업로드 대기열
      var tg = sp.telegram;
      txt += ' · 텔레그램 업로드 ' + (tg.done || 0) + '개 완료' + (tg.pending ? ', 대기 ' + tg.pending : '') +
        (tg.failed ? ', 실패 ' + tg.failed : '') + (tg.skipped ? ', 건너뜀 ' + tg.skipped : '');
    }
    if (sp.worker) txt += sp.worker.pid ? (' · 별도 작업 프로세스(' + (typeof sp.worker.nice === 'number' ? 'nice ' + sp.worker.nice : 'CPU 우선순위 ' + sp.worker.nice) + ')') : ' · 작업 프로세스 시작 중';
    var th = sp.throttle || {};
    Object.keys(th).forEach(function (k) {
      if (th[k].cooling > 0) txt += ' · ' + k + ' 서버 제한으로 ' + th[k].cooling + '초 쉬는 중';
      else if (th[k].level > 0) txt += ' · ' + k + ' 속도 조절 ' + th[k].level + '단계';
    });
    return '<div class="wtm-hint" style="margin:2px 0 0 0">' + escapeHtml(txt) + '</div>';
  }

  function renderStatusBar() {
    var job = state.job || {};
    var pill = el('[data-el="status-pill"]');
    var msg = el('[data-el="status-message"]');
    var progWrap = el('[data-el="progress-wrap"]');
    var progBar = el('[data-el="progress-bar"]');
    var cancelBtn = el('[data-el="cancel-btn"]');

    if (pill) {
      pill.className = 'wtm-status-pill' + (job.running ? ' running' : (job.stage === 'error' ? ' error' : (job.stage === 'done' ? ' done' : '')));
      pill.textContent = job.running ? '실행 중' : (job.stage === 'error' ? '오류' : (job.stage === 'done' ? '완료' : '대기 중'));
    }
    // 네이버/카카오가 동시에 돌 때는 각각의 진행 상황을 따로 보여준다
    var parts = [job.naver, job.kakao].filter(function (p) { return p && p.running; });
    var progText = el('[data-el="progress-text"]');
    if (msg) {
      if (job.running && parts.length) {
        msg.innerHTML = parts.map(function (p) {
          return '<div>' + escapeHtml(p.msg || '') + ' <span class="wtm-hint" style="margin:0">· 작품 ' +
            (p.done || 0) + '/' + (p.total || 0) + '</span></div>';
        }).join('') + speedLine();
      } else {
        msg.textContent = job.message || '';
      }
    }
    var pDone = 0, pTotal = 0;
    if (parts.length) {
      parts.forEach(function (p) { pDone += (p.done || 0); pTotal += (p.total || 0); });
    } else {
      pDone = job.progress || 0; pTotal = job.total || 0;
    }
    if (progWrap && progBar) {
      if (job.running && pTotal) {
        progWrap.style.display = '';
        progBar.style.width = Math.max(2, Math.min(100, Math.round((pDone / pTotal) * 100))) + '%';
        if (progText) { progText.style.display = ''; progText.textContent = Math.round((pDone / pTotal) * 100) + '% (' + pDone + '/' + pTotal + ')'; }
      } else {
        progWrap.style.display = 'none';
        if (progText) progText.style.display = 'none';
      }
    }
    if (cancelBtn) cancelBtn.style.display = job.running ? '' : 'none';

    pollFastUntil = job.running ? (Date.now() + 30000) : pollFastUntil;

    // 스캔/전체실행과 독립된 개별 작품 다운로드 상태(title_job)도 함께 표시
    var tjob = state.title_job || {};
    var tbar = el('[data-el="title-job-bar"]');
    var tmsg = el('[data-el="title-job-message"]');
    var recentlyDone = !tjob.running && tjob.finished_at && (Date.now() / 1000 - tjob.finished_at) < 120;
    if (tbar) tbar.style.display = (tjob.running || recentlyDone) ? '' : 'none';
    if (tmsg) tmsg.textContent = (recentlyDone ? (tjob.last_error ? '❌ ' : '✅ ') : '') +
      (tjob.message || '') + (recentlyDone && tjob.last_error ? ' (' + tjob.last_error + ')' : '') +
      ((state.kakao_queue || []).length ? ' · 카카오 대기 ' + state.kakao_queue.length + '개' : '');
    var tcancel = tbar ? tbar.querySelector('[data-action="cancel_title_job"]') : null;
    if (tcancel) tcancel.style.display = tjob.running ? '' : 'none';
    if (tjob.running) pollFastUntil = Date.now() + 30000;
  }

  function renderKakaoStatus() {
    var status = el('[data-el="kakao-status"]');
    if (!status) return;
    var cfg = state.config_public || {};
    if (!cfg.KAKAO_ENABLE) {
      status.innerHTML = '⚠️ [설정] &gt; [카카오웹툰] 탭에서 <b>"카카오페이지 사용"</b>을 켜야 목록 수집/다운로드가 동작합니다.';
      return;
    }
    var kcount = (state.titles || []).filter(function (t) { return t.platform === 'kakao'; }).length;
    status.textContent = '작품 ' + kcount + '개 / 저장 경로: ' + (cfg.KAKAO_DOWNLOAD_ROOT || '') +
      ' / 로그인 쿠키: ' + (cfg.has_kakao_cookie ? '설정됨' : '없음(무료 회차만)') +
      ' / 기다무 작품 받기: 웹툰 ' + (cfg.KAKAO_DOWNLOAD_WAITFREE ? '켜짐' : '꺼짐') +
      ', 웹소설 ' + (cfg.KAKAO_NOVEL_DOWNLOAD_WAITFREE ? '켜짐' : '꺼짐') +
      ' / 기다무 대여권 사용: ' + (cfg.KAKAO_USE_WAITFREE ? '켜짐' : '꺼짐') +
      ' / 자동 실행 포함: ' + (cfg.KAKAO_AUTO ? '예' : '아니오');
  }

  function renderAll() {
    renderStatusBar();
    renderGrid();
    renderKakaoStatus();
    renderAuthorsTags();
    renderHistory();
    renderSettingsSummary();
    var verEl = el('[data-el="plugin-version"]');
    if (verEl) verEl.textContent = state.plugin_version ? ('v' + state.plugin_version) : '';
    renderUpdateBadge();
  }

  function renderUpdateBadge() {
    var badge = el('[data-el="update-badge"]');
    if (!badge) return;
    var upd = state.update_status || {};
    if (upd.update_available && upd.latest_version) {
      badge.style.display = '';
      badge.title = '현재 v' + (state.plugin_version || '?') + ' \u2192 최신 v' + upd.latest_version +
        ' (GitHub 저장소 열기, 새 코드를 직접 받아 교체하거나 환경설정의 업데이트 버튼을 사용하세요)';
      badge.innerHTML = '<i class="fa-solid fa-arrow-up"></i> 업데이트 가능 (v' + escapeHtml(upd.latest_version) + ')';
      badge.href = state.repo_url || 'https://github.com/yume-script/webtoon_manager';
    } else {
      badge.style.display = 'none';
    }
  }

  var lastListRefresh = 0;
  async function refresh() {
    lastListRefresh = Date.now();
    try {
      state = await fetchData();
      renderAll();
    } catch (e) {
      console.error('[webtoon_manager] 새로고침 실패:', e);
      var msg = el('[data-el="status-message"]');
      if (msg) msg.textContent = '데이터 로드 실패: ' + e.message;
    }
  }

  // 주기적 폴링은 작업 상태/로그/이력만 받는 가벼운 요청(poll_status)으로 한다.
  // 작품 목록(수천 개)은 서버의 titles_rev가 바뀌었을 때만 전체를 다시 받는다.
  async function pollLight() {
    var r = await callAction('poll_status', {});
    var data = r.success ? parseMaybeJson(r.message) : null;
    if (!data || typeof data !== 'object') { await refresh(); return; }
    state.job = data.job || state.job;
    state.title_job = data.title_job || state.title_job;
    state.kakao_queue = data.kakao_queue || [];
    state.log_tail = data.log_tail || state.log_tail;
    state.history = data.history || state.history;
    if (data.history_cutoff !== undefined) state.history_cutoff = data.history_cutoff;
    state.speed = data.speed || state.speed;
    if (data.titles_rev && data.titles_rev !== state.titles_rev) {
      // 다운로드 중에는 작품 정보가 몇 초마다 바뀐다. 그때마다 수천 개 목록을 다시
      // 받아 그리면 서버/브라우저 CPU를 많이 쓰므로 작업 중엔 60초에 한 번만 갱신.
      var busy = (state.job && state.job.running) || (state.title_job && state.title_job.running);
      if (!busy || Date.now() - lastListRefresh > 60000) {
        await refresh();
        return;
      }
    }
    renderStatusBar();
    renderHistory();
    var logBox = el('[data-el="log-tail"]');
    if (logBox) logBox.textContent = (state.log_tail || []).join('\n');
  }

  function schedulePoll() {
    if (pollTimer) clearTimeout(pollTimer);
    var interval = (Date.now() < pollFastUntil) ? 2500 : 10000;
    if (!alive()) return;   // 새로 실행된 스크립트가 폴링을 이어받음
    pollTimer = setTimeout(function () {
      if (!alive()) return;
      if (!document.hidden && currentTab === 'hourly') loadHourly(false);
      if (!document.hidden) pollLight().catch(function () {}).then(schedulePoll);
      else schedulePoll();
    }, interval);
  }

  // ------------------------------------------------------------------
  // 탭 전환
  // ------------------------------------------------------------------
  // ------------------------------------------------------------------
  // 설정 폼 (코어 플러그인 설정 화면 대신 여기서 모든 값을 편집)
  // ------------------------------------------------------------------
  var settingsLoaded = false;
  var settingsMeta = null;

  async function loadSettingsForm(force) {
    var box = el('[data-el="settings-form"]');
    if (!box || (settingsLoaded && !force)) return;
    box.innerHTML = '<div class="wtm-hint">불러오는 중...</div>';
    var r = await callAction('get_settings', {});
    var data = r.success ? parseMaybeJson(r.message) : null;
    if (!data || !data.groups) {
      box.innerHTML = '<div class="wtm-hint">설정을 불러오지 못했습니다: ' + escapeHtml(r.message || '') + '</div>';
      return;
    }
    settingsMeta = data;
    settingsLoaded = true;
    var sections = data.sections || [{ id: 'common', label: '설정' }];
    // [공통][네이버][카카오페이지] 섹션 탭 - 입력값은 탭을 바꿔도 DOM에 남아 있어서
    // "설정 저장" 한 번으로 세 섹션이 함께 저장된다.
    var tabs = '<div class="wtm-daytabs" style="margin-bottom:6px">' + sections.map(function (sec) {
      return '<button class="wtm-daytab' + (sec.id === settingsSection ? ' active' : '') +
        '" data-settings-section="' + escapeHtml(sec.id) + '">' + escapeHtml(sec.label) + '</button>';
    }).join('') + '</div>';
    box.innerHTML = tabs + sections.map(function (sec) {
      var groups = data.groups.filter(function (g) { return (g.section || 'common') === sec.id; });
      return '<div data-settings-pane="' + escapeHtml(sec.id) + '"' + (sec.id === settingsSection ? '' : ' style="display:none"') + '>' +
        groups.map(function (g) {
          var fields = g.fields.filter(function (f) { return f.type !== 'hidden'; });
          return '<div class="wtm-set-group">' +
            '<div class="wtm-set-group-title">' + escapeHtml(g.label) + '</div>' +
            (g.desc ? '<div class="wtm-hint" style="margin:0 0 8px">' + escapeHtml(g.desc) + '</div>' : '') +
            '<div class="wtm-set-grid">' +
            fields.map(function (f) { return settingFieldHtml(f, data.values[f.key], (data.secret_set || {})[f.key]); }).join('') +
            '</div></div>';
        }).join('') + '</div>';
    }).join('');
    // 라이브러리 드롭다운은 폼을 새로 그릴 때마다 목록을 다시 채운다
    librariesLoaded = false;
    loadLibraryOptionsIfNeeded();
  }
  var settingsSection = 'common';

  function settingFieldHtml(f, value, secretSet) {
    var key = escapeHtml(f.key);
    var label = escapeHtml(f.label || f.key);
    if (f.type === 'heading') {
      return '<div class="wtm-set-subhead">' + label + '</div>';
    }
    var hint = f.hint ? '<span class="wtm-set-hint">' + escapeHtml(f.hint) + '</span>' : '';
    if (f.type === 'checkbox') {
      return '<label class="wtm-set-field wtm-set-check">' +
        '<input type="checkbox" data-setting="' + key + '"' + (value ? ' checked' : '') + '>' +
        '<span><span class="wtm-set-label">' + label + '</span>' + hint + '</span></label>';
    }
    var input;
    if (f.type === 'library') {
      input = '<select class="wtm-input" data-setting="' + key + '" data-el="compare-library-select" data-current="' +
        escapeHtml(value == null ? '' : String(value)) + '"><option value="">사용 안 함</option></select>' +
        '<div class="wtm-hint" data-el="compare-library-status" style="margin:0"></div>';
    } else if (f.type === 'select') {
      input = '<select class="wtm-input" data-setting="' + key + '">' + (f.options || []).map(function (o) {
        return '<option value="' + escapeHtml(o[0]) + '"' + (String(value) === String(o[0]) ? ' selected' : '') + '>' +
          escapeHtml(o[1]) + '</option>';
      }).join('') + '</select>';
    } else if (f.type === 'password') {
      input = '<div style="display:flex;gap:6px;align-items:center">' +
        // type=password면 브라우저가 저장된 로그인 비밀번호를 자동으로 채워 쿠키 대신 저장되는 일이 있어, 글자만 가린 일반 칸으로
        '<input type="text" class="wtm-input wtm-secret" autocomplete="off" autocapitalize="off" spellcheck="false" ' +
        'data-lpignore="true" data-1p-ignore="true" data-form-type="other" data-setting="' + key + '" placeholder="' +
        (secretSet ? '저장됨 - 바꾸려면 새 값 입력' : '(비어 있음)') + '">' +
        (/COOKIE/.test(key) ? '<button type="button" class="wtm-btn wtm-btn-secondary wtm-btn-small" data-cookie-file="' + key + '" ' +
          'title="Cookie-Editor로 내보낸 .json 파일을 골라 이 칸에 넣습니다 (저장은 [설정 저장])" style="white-space:nowrap">파일에서 불러오기</button>' : '') +
        (secretSet ? '<label style="font-size:11px;white-space:nowrap"><input type="checkbox" data-setting-clear="' + key + '"> 지우기</label>' : '') +
        '</div>';
    } else if (f.type === 'textarea') {
      input = '<textarea class="wtm-input" rows="3" data-setting="' + key + '" placeholder="예) /mnt/library/웹툰&#10;/mnt/library2/완결작" ' +
        'style="resize:vertical;font-family:inherit">' + escapeHtml(value == null ? '' : String(value)) + '</textarea>';
    } else {
      var isLong = /COOKIE|JSON/.test(f.key);
      input = '<input type="' + (f.type === 'number' ? 'number' : 'text') + '" class="wtm-input" data-setting="' + key + '"' +
        (f.type === 'number' ? ' step="any"' : '') + (isLong ? '' : '') +
        ' value="' + escapeHtml(value == null ? '' : String(value)) + '">';
    }
    if (f.key === 'NAVER_COOKIE_JSON') {
      input += '<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">' +
        '<button class="wtm-btn wtm-btn-secondary wtm-btn-small" data-cookie-verify="naver">쿠키 검증(로그인·성인 인증 확인)</button>' +
        '<span class="wtm-hint" data-verify-msg="naver" style="margin:0;white-space:pre-line"></span></div>' +
        '<span class="wtm-hint" style="margin:0">성인 작품은 <b>성인 인증된 네이버 계정</b>으로 comic.naver.com에 로그인한 뒤 ' +
        'Cookie-Editor로 내보낸 JSON 전체를 붙여넣어야 받을 수 있습니다(로그인 쿠키 NID_AUT, NID_SES 필요).</span>';
    }
    if (/^KAKAO_COOKIE_\d$/.test(f.key)) {  // 추가 계정: 계정마다 검증 버튼
      input += '<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">' +
        '<button class="wtm-btn wtm-btn-secondary wtm-btn-small" data-cookie-verify="kakao" data-cookie-key="' + f.key + '">쿠키 검증</button>' +
        '<span class="wtm-hint" data-verify-msg="' + f.key + '" style="margin:0;white-space:pre-line"></span></div>';
    }
    if (f.key === 'KAKAO_COOKIE') {
      input += '<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">' +
        '<button class="wtm-btn wtm-btn-secondary wtm-btn-small" data-cookie-verify="kakao">쿠키 검증(로그인·성인 인증 확인)</button>' +
        '<span class="wtm-hint" data-verify-msg="kakao" style="margin:0;white-space:pre-line"></span></div>' +
        '<span class="wtm-hint" style="margin:0">성인 작품은 <b>성인 인증된 카카오 계정</b>으로 page.kakao.com에 로그인한 뒤 ' +
        'Cookie-Editor로 내보낸 JSON 전체를 붙여넣어야 받을 수 있습니다(필수: _kau, _kpwtkn, _T_ANO, _karmt, _kahai, _kawlt, _kpdid).</span>';
    }
    var wide = (f.type === 'textarea' || f.key === 'NAVER_COOKIE_JSON' || /^KAKAO_COOKIE(_\d)?$/.test(f.key)) ? ' wtm-set-wide' : '';
    return '<div class="wtm-set-field' + wide + '">' +
      '<span class="wtm-set-label">' + label + '</span>' + input + hint + '</div>';
  }

  // 저장하지 않은 설정 (쿠키를 붙여 넣고 검증만 한 채 떠나면 사라지므로 알려 준다)
  var settingsDirty = false;
  function markSettingsDirty(on) {
    settingsDirty = on;
    var msg = el('[data-el="settings-save-msg"]');
    if (msg && on) msg.textContent = '⚠️ 저장하지 않은 변경이 있습니다 - [설정 저장]을 눌러야 유지됩니다';
  }
  document.addEventListener('input', function (ev) {
    if (ev.target.closest && ev.target.closest('[data-setting], [data-setting-clear]')) markSettingsDirty(true);
  });
  document.addEventListener('change', function (ev) {
    if (ev.target.closest && ev.target.closest('[data-setting], [data-setting-clear]')) markSettingsDirty(true);
  });
  window.addEventListener('beforeunload', function (ev) {
    if (settingsDirty) { ev.preventDefault(); ev.returnValue = ''; }
  });

  async function saveSettingsForm() {
    var msg = el('[data-el="settings-save-msg"]');
    var values = {};
    var clear = [];
    els('[data-setting]').forEach(function (inp) {
      var k = inp.getAttribute('data-setting');
      values[k] = inp.type === 'checkbox' ? inp.checked : inp.value;
      if (k === 'COMPARE_LIBRARY_ID') {
        var opt = inp.options && inp.options[inp.selectedIndex];
        values.COMPARE_LIBRARY_NAME = (inp.value && opt) ? opt.textContent : '';
      }
    });
    els('[data-setting-clear]').forEach(function (c) { if (c.checked) clear.push(c.getAttribute('data-setting-clear')); });
    els('[data-el="settings-save"]').forEach(function (b) { b.disabled = true; });
    var r = await callAction('save_settings', { values: values, clear: clear });
    els('[data-el="settings-save"]').forEach(function (b) { b.disabled = false; });
    if (msg) msg.textContent = (r.success ? '✅ ' : '❌ ') + (r.message || '').split('\n')[0];
    window.alert((r.success ? '✅ ' : '❌ 저장하지 못했습니다\n\n') + (r.message || ''));
    if (r.success) {
      settingsDirty = false;
      await loadSettingsForm(true);
      await refresh();
    }
  }

  // ------------------------------------------------------------------
  // 시간대별 다운로드 (예상 / 실제) - GET api/wtm/hourly?day=
  // ------------------------------------------------------------------
  var hourlyRange = '24h';
  var hourlyAt = 0;
  async function loadHourly(force) {
    if (!force && Date.now() - hourlyAt < 60000) return;
    hourlyAt = Date.now();
    var body = el('[data-el="hourly-body"]');
    try {
      var resp = await fetch('api/wtm/hourly?range=' + encodeURIComponent(hourlyRange), { credentials: 'same-origin' });
      var d = await resp.json();
      if (!d.success) throw new Error(d.error || ('HTTP ' + resp.status));
      renderHourly(d);
    } catch (e) {
      if (body) body.innerHTML = '<div class="wtm-hint">불러오지 못했습니다: ' + escapeHtml(e.message || String(e)) + '</div>';
    }
  }

  function renderHourly(d) {
    var sel = el('[data-el="hourly-range"]');
    if (sel) {
      sel.innerHTML = d.ranges.map(function (r) {
        return '<option value="' + r[0] + '"' + (r[0] === d.range ? ' selected' : '') + '>실제: ' + escapeHtml(r[1]) + '</option>';
      }).join('');
    }
    var n = function (v) { return Math.round(v * 10) / 10; };
    var cellText = function (v) { return v >= 10 ? String(Math.round(v)) : (v ? String(n(v)) : ''); };
    var even = function (v) {
      if (v === null || v === undefined) return '<span class="wtm-hm-even">-</span>';
      var cls = v >= 80 ? 'good' : v >= 60 ? 'mid' : 'bad';
      return '<span class="wtm-hm-even ' + cls + '">' + v + '%</span>';
    };
    var hourHead = '<div class="wtm-hm-row wtm-hm-head"><div class="wtm-hm-label"></div><div class="wtm-hm-tag"></div>' +
      Array.apply(null, Array(24)).map(function (_x, h) {
        return '<div class="wtm-hm-h' + (h === d.now_hour ? ' now' : '') + '">' + h + '</div>';
      }).join('') + '<div class="wtm-hm-stat">하루 · 고른 정도</div></div>';
    var line = function (label, tag, arr, total, ev, unit, sub) {
      var max = Math.max.apply(null, arr.concat([0.0001]));
      var cells = arr.map(function (v, h) {
        var a = v / max;
        return '<div class="wtm-hm-c' + (h === d.now_hour ? ' now' : '') + '" title="' + h + '시 ' + tag + ' ' + n(v) + unit + '"' +
          ' style="--a:' + (v ? (0.12 + a * 0.88).toFixed(2) : 0) + '"><span' + (a > 0.6 ? ' class="on"' : '') + '>' + cellText(v) + '</span></div>';
      }).join('');
      return '<div class="wtm-hm-row' + (sub ? ' sub' : '') + '"><div class="wtm-hm-label">' + label + '</div><div class="wtm-hm-tag">' + tag + '</div>' +
        cells + '<div class="wtm-hm-stat">' + n(total) + unit + ' · ' + even(ev) + '</div></div>';
    };
    var html = '', curP = '';
    d.rows.forEach(function (r) {
      if (r.platform !== curP) {
        curP = r.platform;
        html += '<div class="wtm-hm-platform">' + escapeHtml(r.platform_label) + '</div>' + hourHead;
      }
      var label = '<b>' + escapeHtml(r.kind) + '</b>' + (r.titles ? '<small>' + r.titles + '작품' + (r.ideal !== null && r.ideal !== undefined ?
        ' · 이상 시간당 ' + n(r.ideal) : '') + (r.window ? ' · ' + r.window[0] + '~' + r.window[1] + '시' : '') + '</small>' : '') +
        (r.backlog ? '<small class="wtm-hm-backlog" title="충전됐는데 아직 쓰지 못한 대여권 (작품×계정)">밀림 ' + r.backlog + '장</small>' : '');
      if (r.schedule) {
        html += '<div class="wtm-hm-group">' + line(label, '예약', r.schedule, r.sched_total, r.sched_even, '회', false) +
          line('', '실제', r.actual, r.actual_total, r.actual_even, '화', true) + '</div>';
      } else {
        html += '<div class="wtm-hm-group">' + line(label, '실제', r.actual, r.actual_total, r.actual_even, '화', false) + '</div>';
      }
    });
    if (!d.rows.length) html = '<div class="wtm-hint">아직 받은 기록이 없습니다.</div>';
    var need = 0, used = 0, back = 0;
    d.rows.forEach(function (r) { if (r.schedule) { need += r.sched_total; used += r.actual_total; back += r.backlog || 0; } });
    var rangeLabel = (d.ranges.filter(function (x) { return x[0] === d.range; })[0] || ['', ''])[1];
    var info = '<div class="wtm-hourly-summary"><span>기다무 하루 필요 <b>' + n(need) + '장</b></span><span>실제 사용(' + escapeHtml(rangeLabel) +
      ') <b>' + n(used) + '장</b>' + (need ? ' (' + Math.round(used / need * 100) + '%)' : '') + '</span><span>지금 밀린 대여권 <b' +
      (back ? ' class="wtm-hm-backlog"' : '') + '>' + back + '장</b></span><span>평균 지연 <b>' + Math.round(d.delay / 60) +
      '분</b></span><span>계정 ' + d.accounts + '개</span></div>';
    el('[data-el="hourly-body"]').innerHTML = info + '<div class="wtm-hm">' + html + '</div>';
  }

  function setTab(tab) {
    currentTab = tab;
    els('.wtm-tab').forEach(function (b) { b.classList.toggle('active', b.getAttribute('data-tab') === tab); });

    var isListTab = ['all', 'subscribed', 'unsubscribed', 'excluded', 'duplicate'].indexOf(tab) >= 0;
    els('[data-panel-view]').forEach(function (p) {
      var views = p.getAttribute('data-panel-view').split(',');
      p.style.display = views.indexOf(tab) >= 0 ? '' : 'none';
    });
    // 목록 탭이 아닐 때(설정/이력 등)는 검색·필터 줄을 숨긴다
    var toolbar = el('.wtm-toolbar[data-panel]');
    if (toolbar) toolbar.style.display = isListTab ? '' : 'none';

    if (tab === 'settings') { loadLibraryOptionsIfNeeded(); loadSettingsForm(false); }
    if (tab === 'hourly') loadHourly(true);

    renderGrid();
  }

  // ------------------------------------------------------------------
  // 이벤트 바인딩
  // ------------------------------------------------------------------
  container.addEventListener('click', async function (ev) {
    if (!alive()) return;
    var tabBtn = ev.target.closest('.wtm-tab');
    if (tabBtn) { setTab(tabBtn.getAttribute('data-tab')); return; }

    var secBtn = ev.target.closest('[data-settings-section]');
    if (secBtn) {
      settingsSection = secBtn.getAttribute('data-settings-section');
      els('[data-settings-section]').forEach(function (b) { b.classList.toggle('active', b === secBtn); });
      els('[data-settings-pane]').forEach(function (p) {
        p.style.display = p.getAttribute('data-settings-pane') === settingsSection ? '' : 'none';
      });
      return;
    }

    var fileBtn = ev.target.closest('[data-cookie-file]');
    if (fileBtn) {  // 쿠키 JSON 파일을 골라 칸에 넣는다 (브라우저에서 읽기만, 서버 전송은 [설정 저장] 때)
      var fkey = fileBtn.getAttribute('data-cookie-file');
      var picker = document.createElement('input');
      picker.type = 'file';
      picker.accept = '.json,.txt,application/json,text/plain';
      picker.onchange = function () {
        var file = picker.files && picker.files[0];
        if (!file) return;
        file.text().then(function (text) {
          var field = el('[data-setting="' + fkey + '"]');
          if (!field) return;
          field.value = text.trim();
          markSettingsDirty(true);
          var m = el('[data-el="settings-save-msg"]');
          if (m) m.textContent = '📄 ' + file.name + ' (' + Math.round(text.length / 1024) + 'KB)을 넣었습니다 - [설정 저장]을 눌러야 저장됩니다';
        });
      };
      picker.click();
      return;
    }

    var verifyBtn = ev.target.closest('[data-cookie-verify]');
    if (verifyBtn) {
      var plat = verifyBtn.getAttribute('data-cookie-verify');
      var ckey = verifyBtn.getAttribute('data-cookie-key');  // 카카오 추가 계정 칸
      var vmsg = el('[data-verify-msg="' + (ckey || plat) + '"]');
      var cin = el('[data-setting="' + (ckey || (plat === 'naver' ? 'NAVER_COOKIE_JSON' : 'KAKAO_COOKIE')) + '"]');
      verifyBtn.disabled = true;
      if (vmsg) vmsg.textContent = '확인 중...';
      var rv = await callAction(plat + '_verify_cookie', { cookie: cin ? cin.value : '', key: ckey || '' });
      verifyBtn.disabled = false;
      if (vmsg) vmsg.textContent = (rv.message || '').split(' / ').join('\n');
      return;
    }

    var saveBtn = ev.target.closest('[data-el="settings-save"]');
    if (saveBtn) { saveSettingsForm(); return; }
    var reloadBtn = ev.target.closest('[data-el="settings-reload"]');
    if (reloadBtn) { settingsDirty = false; loadSettingsForm(true); return; }
    if (ev.target.closest('[data-el="hourly-reload"]')) { loadHourly(true); return; }

    var moreBtn = ev.target.closest('[data-el="grid-more"]');
    if (moreBtn) {
      gridLimit += GRID_PAGE;
      renderGrid();
      return;
    }

    var histBtn = ev.target.closest('[data-history-filter]');
    if (histBtn) {
      historyFilter = histBtn.getAttribute('data-history-filter');
      els('[data-history-filter]').forEach(function (b) { b.classList.toggle('active', b === histBtn); });
      renderHistory();
      return;
    }

    var platBtn = ev.target.closest('[data-platform-filter]');
    if (platBtn) {
      platformFilter = platBtn.getAttribute('data-platform-filter');
      els('[data-platform-filter]').forEach(function (b) { b.classList.toggle('active', b === platBtn); });
      renderGrid();
      return;
    }

    var dayBtn = ev.target.closest('.wtm-daytab[data-day]');
    if (dayBtn) {
      dayFilter = dayBtn.getAttribute('data-day');
      els('.wtm-daytab[data-day]').forEach(function (b) { b.classList.toggle('active', b === dayBtn); });
      renderGrid();
      return;
    }

    var headerAction = ev.target.closest('[data-action]');
    if (headerAction) {
      var action = headerAction.getAttribute('data-action');
      if (action === 'refresh') { await refresh(); return; }
      if (action === 'scan_now' || action === 'scan_finished_now' || action === 'run_full_cycle_now' || action === 'cancel_job' ||
          action === 'cancel_title_job' || action === 'test_discord' || action === 'force_reset_job' ||
          action === 'kavita_yaml_all' || action === 'kakao_run_all' || action === 'kakao_scan' ||
          action === 'kakao_sync_purchased') {
        if (headerAction.disabled) return;
        if (action === 'force_reset_job' && !confirm('정말로 작업 상태를 강제 초기화할까요? 지금 실제로 뭔가 진행 중이라면 중간에 끊길 수 있습니다.')) return;
        headerAction.disabled = true;
        var r = await callAction(action, {});
        headerAction.disabled = false;
        if (!r.success) alert(r.message || '실패');
        else if (action === 'test_discord') alert(r.message || '보냄');
        await refresh();
        return;
      }
      if (action === 'save_compare_library') {
        var sel = el('[data-el="compare-library-select"]');
        if (!sel) return;
        var opt = sel.options[sel.selectedIndex];
        headerAction.disabled = true;
        var r6 = await callAction('set_compare_library', {
          libraryId: sel.value, libraryName: opt ? opt.textContent : '',
        });
        headerAction.disabled = false;
        var statusEl = el('[data-el="compare-library-status"]');
        if (statusEl) statusEl.textContent = r6.message || (r6.success ? '저장됨' : '실패');
        if (r6.success) await refresh();
        return;
      }
      if (action === 'kakao_add') {
        var kin = el('[data-el="kakao-input"]');
        if (!kin || !kin.value.trim()) return;
        headerAction.disabled = true;
        var rk = await callAction('kakao_add', { value: kin.value.trim() });
        headerAction.disabled = false;
        if (rk.success) { kin.value = ''; await refresh(); } else { alert(rk.message || '등록 실패'); }
        return;
      }
      if (action === 'add_author' || action === 'add_tag') {
        var key = action === 'add_author' ? 'author-input' : 'tag-input';
        var input = el('[data-el="' + key + '"]');
        if (!input || !input.value.trim()) return;
        var r2 = await callAction(action, { value: input.value.trim() });
        if (r2.success) { input.value = ''; await refresh(); } else { alert(r2.message); }
        return;
      }
      if (action === 'manual_lookup') {
        var idInput = el('[data-el="manual-title-id"]');
        var titleId = idInput && idInput.value.trim();
        if (!titleId) return;
        var resultBox = el('[data-el="manual-result"]');
        if (resultBox) resultBox.innerHTML = '<div class="wtm-hint">조회 중...</div>';
        var platSel = el('[data-el="manual-platform"]');
        var manualPlatform = platSel ? platSel.value : 'naver';
        if (/kakao\.com/.test(titleId)) { manualPlatform = 'kakao'; if (platSel) platSel.value = 'kakao'; }
        var r3 = await callAction('manual_lookup', { titleId: titleId, platform: manualPlatform });
        var parsed = r3.success ? parseMaybeJson(r3.message) : null;
        if (!r3.success || !parsed) {
          if (resultBox) resultBox.innerHTML = '<div class="wtm-hint">조회 실패: ' + escapeHtml(r3.message || '') + '</div>';
          return;
        }
        lookupResult = parsed;
        renderManualResult();
        return;
      }
      if (action === 'manual_download_selected') {
        if (!lookupResult) return;
        var checkedBoxes = els('[data-ep-checkbox]:checked');
        var checked = checkedBoxes.map(function (c) { return parseInt(c.getAttribute('data-ep-checkbox'), 10); });
        if (!checked.length) { alert('회차를 선택하세요'); return; }
        var epByNo = {};
        (lookupResult.episodes || []).forEach(function (e) { epByNo[e.no] = e; });
        var alreadyDoneChecked = checked.filter(function (no) { return epByNo[no] && epByNo[no].downloaded; }).length;
        // 여기서 선택한 회차는 명시적 재다운로드 요청으로 보고 force: true를
        // 보낸다 - 이미 zip이 있어도 지우고 처음부터 다시 받는다(파일이
        // 잘못됐을 때 쓰는 용도).
        if (alreadyDoneChecked > 0) {
          if (!confirm('선택한 ' + checked.length + '개 중 이미 받은 ' + alreadyDoneChecked +
            '개도 포함되어 있습니다. 그 회차들은 기존 파일을 지우고 처음부터 다시 받습니다 - 계속할까요?')) {
            return;
          }
        }
        var r4 = await callAction('manual_download', { titleId: lookupResult.titleId, title: lookupResult.title, episodeNos: checked, force: true, platform: lookupResult.platform || 'naver' });
        alert(r4.message || (r4.success ? '시작됨' : '실패'));
        await refresh();
        return;
      }
      if (action === 'manual_download_all') {
        if (!lookupResult) return;
        var freeAllEps = (lookupResult.episodes || []).filter(function (e) { return !e.charge; });
        var freeEps = freeAllEps.map(function (e) { return e.no; });
        if (!freeEps.length) { alert('다운로드 가능한(무료) 회차가 없습니다'); return; }
        var alreadyDone = freeAllEps.filter(function (e) { return e.downloaded; }).length;
        var confirmMsg = '무료 회차 ' + freeEps.length + '개를 전부 다운로드할까요?';
        if (alreadyDone > 0) {
          confirmMsg += ' (이미 받은 ' + alreadyDone + '개는 건너뛰고 나머지 ' +
            (freeEps.length - alreadyDone) + '개만 실제로 받습니다)';
        }
        if (!confirm(confirmMsg)) return;
        // "전체 다운로드"는 밀린 걸 채우는 용도라 이미 받은 건 그대로 둔다
        // (force: false) - 잘못된 파일 재다운로드는 위의 "선택 회차
        // 다운로드"로 콕 찍어서 하도록 분리했다.
        var r4b = await callAction('manual_download', { titleId: lookupResult.titleId, title: lookupResult.title, episodeNos: freeEps, force: false, platform: lookupResult.platform || 'naver' });
        alert(r4b.message || (r4b.success ? '시작됨' : '실패'));
        await refresh();
        return;
      }
    }

    var gotoManual = ev.target.closest('[data-goto-manual]');
    if (gotoManual) {
      var tidForManual = gotoManual.getAttribute('data-goto-manual');
      var platForManual = gotoManual.getAttribute('data-platform') || 'naver';
      setTab('manual');
      var platSelForManual = el('[data-el="manual-platform"]');
      if (platSelForManual) platSelForManual.value = platForManual;
      var idInputForManual = el('[data-el="manual-title-id"]');
      if (idInputForManual) idInputForManual.value = tidForManual;
      var lookupBtn = document.querySelector('[data-action="manual_lookup"]');
      if (lookupBtn) lookupBtn.click();
      return;
    }

    var kakaoAction = ev.target.closest('[data-kakao-action]');
    if (kakaoAction) {
      var kAct = kakaoAction.getAttribute('data-kakao-action');
      var kSid = kakaoAction.getAttribute('data-series-id');
      if (kAct === 'kakao_remove' && !confirm('목록에서 삭제할까요? (받은 파일은 지우지 않습니다)')) return;
      kakaoAction.disabled = true;
      var rk2 = await callAction(kAct, { seriesId: kSid });
      kakaoAction.disabled = false;
      if (!rk2.success) alert(rk2.message || '실패');
      else if (kAct === 'kakao_download') pollFastUntil = Date.now() + 30000;
      await refresh();
      return;
    }

    var cardAction = ev.target.closest('[data-card-action]');
    if (cardAction) {
      var actName = cardAction.getAttribute('data-card-action');
      var titleId2 = cardAction.getAttribute('data-title-id');
      var platform2 = cardAction.getAttribute('data-platform') || 'naver';
      cardAction.disabled = true;
      var r5 = await callAction(actName, { titleId: titleId2, platform: platform2 });
      if (actName === 'download_title') {
        pollFastUntil = Date.now() + 30000;
        var tmsg2 = el('[data-el="title-job-message"]');
        var tbar2 = el('[data-el="title-job-bar"]');
        if (tbar2 && tmsg2) { tbar2.style.display = ''; tmsg2.textContent = (r5.success ? '' : '❌ ') + (r5.message || ''); }
      }
      cardAction.disabled = false;
      if (!r5.success) alert(r5.message || '실패');
      else if (actName === 'toggle_notify' && /설정이 비어/.test(r5.message || '')) alert(r5.message);
      else if (actName === 'toggle_telegram' && r5.message) alert(r5.message);
      await refresh();
      return;
    }

    var chipRemove = ev.target.closest('[data-chip-remove]');
    if (chipRemove) {
      var kind = chipRemove.getAttribute('data-chip-remove');
      var value = chipRemove.getAttribute('data-value');
      var act = kind === 'author' ? 'remove_author' : 'remove_tag';
      var r6 = await callAction(act, { value: value });
      if (r6.success) await refresh(); else alert(r6.message);
      return;
    }
  });

  var searchInput = el('[data-el="search-input"]');
  if (searchInput) {
    searchInput.addEventListener('input', function () {
      if (!alive()) return;
      searchQuery = searchInput.value.trim();
      renderGrid();
    });
  }

  var hourlySel = el('[data-el="hourly-range"]');
  if (hourlySel) {
    hourlySel.addEventListener('change', function () {
      if (!alive()) return;
      hourlyRange = hourlySel.value;
      loadHourly(true);
    });
  }

  var sortSelect = el('[data-el="sort-select"]');
  if (sortSelect) {
    sortSelect.addEventListener('change', function () {
      if (!alive()) return;
      sortMode = sortSelect.value;
      renderGrid();
    });
  }

  function renderManualResult() {
    var box = el('[data-el="manual-result"]');
    if (!box || !lookupResult) return;
    var eps = lookupResult.episodes || [];
    var downloadedCount = eps.filter(function (e) { return e.downloaded; }).length;
    box.innerHTML =
      '<div class="wtm-box" style="margin-top:10px">' +
      '<div class="wtm-box-title">' + (lookupResult.platform === 'kakao' ? '[카카오] ' : '[네이버] ') + escapeHtml(lookupResult.title) +
      ' (' + (lookupResult.platform === 'kakao' ? '작품번호' : 'titleId') + '=' + lookupResult.titleId + ')' +
      ' <span class="wtm-hint" style="margin:0">- 받음 ' + downloadedCount + '/' + eps.length + '화</span></div>' +
      '<div style="max-height:260px;overflow:auto">' +
      eps.map(function (e) {
        var cfgp = state.config_public || {};
        // 로그인 쿠키가 있으면 유료 회차도 고를 수 있다(구매·대여한 회차만 실제로 받아짐)
        var loggedIn = lookupResult.platform === 'kakao' ? !!cfgp.has_kakao_cookie : !!cfgp.has_cookie;
        var isPaid = !!e.charge && !loggedIn;
        var paidButSelectable = !!e.charge && loggedIn;
        var isDone = !!e.downloaded;
        return '<label style="display:flex;align-items:center;gap:8px;padding:3px 0;font-size:12px;' + (isPaid ? 'opacity:.5' : '') + '">' +
          '<input type="checkbox" data-ep-checkbox="' + e.no + '"' +
          (isPaid ? ' disabled title="유료 회차는 로그인 쿠키를 넣어야 선택할 수 있습니다(구매·대여한 회차만 받아짐)"' :
            (isDone ? ' title="이미 받은 회차입니다 - 체크 후 \'선택 회차 다운로드\'를 누르면 기존 파일을 지우고 강제로 다시 받습니다(파일이 잘못됐을 때 사용)"' : '')) +
          '> ' +
          '<span' + (isDone ? ' style="opacity:.6"' : '') + '>' +
          (e.special ? '특별회차(파일 ' + e.no + '화)' : e.no + '화') + ' - ' + escapeHtml(e.subtitle || '') + '</span>' +
          (isPaid ? ' <b>(유료 - 선택불가)</b>' : '') +
          (paidButSelectable && !e.rented ? ' <span class="wtm-hint" style="margin:0">(유료 - ' +
            (lookupResult.platform === 'kakao' && (cfgp.KAKAO_USE_WAITFREE || cfgp.KAKAO_USE_OWNED_TICKETS)
              ? '구매·대여했거나 ' + [cfgp.KAKAO_USE_WAITFREE ? '기다무' : '', cfgp.KAKAO_USE_OWNED_TICKETS ? '보유 대여권' : '']
                  .filter(Boolean).join('·') + '으로 열 수 있으면 받아짐' + (cfgp.KAKAO_USE_WAITFREE ? ', 기다무는 계정마다 1장' : '') + ')'
              : '구매·대여한 경우만 받아짐)') + '</span>' : '') +
          (e.rented ? ' <span class="wtm-badge up">대여·소장</span>' : '') +
          (isDone ? ' <span class="wtm-badge" style="background:color-mix(in srgb, #4f9d76 22%, transparent);color:color-mix(in srgb, #4f9d76 90%, var(--app-text-primary))">받음</span>' : '') +
          '</label>';
      }).join('') +
      '</div>' +
      '<div style="display:flex;gap:8px;margin-top:8px;flex-wrap:wrap">' +
      '<button class="wtm-btn wtm-btn-primary" data-action="manual_download_selected" title="이미 받은 회차를 체크하면 기존 파일을 지우고 강제로 다시 받습니다">선택 회차 다운로드</button>' +
      '<button class="wtm-btn wtm-btn-secondary" data-action="manual_download_all" title="아직 안 받은 무료 회차만 채워 받습니다(이미 받은 건 건너뜀)">전체 다운로드(무료만)</button>' +
      '</div>' +
      '</div>';
  }

  // ------------------------------------------------------------------
  // 초기화
  // ------------------------------------------------------------------
  setTab('all');
  refresh().then(schedulePoll);
})();
