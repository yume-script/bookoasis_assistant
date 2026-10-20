/* web/login.js - 로그인 화면 (YMPlayer login.js와 같은 동작). 사용자가 아직 없으면 "관리자 계정 만들기"로 바뀐다. */
(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  var form = $('loginForm'), errorEl = $('loginError');
  var setup = false;

  function showError(msg) {
    errorEl.textContent = msg;
    errorEl.hidden = !msg;
  }
  function post(path, body) {
    return fetch(path, { method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify(body) })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (data) {
          if (!res.ok || data.success === false) throw new Error(data.error || 'HTTP ' + res.status);
          return data;
        });
      });
  }

  function init() {
    fetch('api/auth/state', { credentials: 'same-origin', headers: { Accept: 'application/json' } })
      .then(function (r) { return r.json(); })
      .then(function (st) {
        if (st.user) { location.replace('./'); return; }
        setup = !!st.setup;
        if (st.ui && window.GdwShell) window.GdwShell.setDefaults(st.ui);
        if (setup) {
          $('loginTitle').textContent = '관리자 계정 만들기';
          $('setupNote').hidden = false;
          $('confirmField').hidden = false;
          $('password').autocomplete = 'new-password';
          $('loginBtn').textContent = '계정 만들고 시작하기';
        }
      })
      .catch(function () { showError('서버에 연결할 수 없습니다.'); });
    $('username').focus();
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    showError('');
    var username = $('username').value.trim(), password = $('password').value;
    if (!username || !password) { showError('아이디와 비밀번호를 넣어 주세요.'); return; }
    if (setup && password !== $('confirm').value) { showError('비밀번호 확인이 다릅니다.'); return; }
    var btn = $('loginBtn');
    btn.disabled = true;
    post(setup ? 'api/auth/setup' : 'api/auth/login', { username: username, password: password, remember: $('remember').checked })
      .then(function () {
        var next = decodeURIComponent((location.hash || '').slice(1));  // 로그인 전에 보던 화면
        location.replace(/^(webtoon|games)?(#[\w%.-]*)?$/.test(next) ? './' + next : './');
      })
      .catch(function (err) { showError(err.message); $('password').select(); })
      .then(function () { btn.disabled = false; });
  });

  init();
})();
