/* Atlas Mobile SPA — standalone mobile web app */
(function () {
  'use strict';

  /* ============================================================
     CONFIG
     ============================================================ */
  var API_BASE = '/api';
  var STORAGE_TOKEN = 'fuxi_mobile_token';
  var STORAGE_USER = 'fuxi_mobile_user';
  var STORAGE_SESSION = 'fuxi_mobile_session';
  var CHAT_STORAGE = 'fuxi_mobile_chat';

  /* ============================================================
     STATE
     ============================================================ */
  var state = {
    token: localStorage.getItem(STORAGE_TOKEN) || null,
    user: JSON.parse(localStorage.getItem(STORAGE_USER) || 'null'),
    screen: 'home',
    params: {},
    loading: false,
    error: null,
    notes: [],
    notesTotal: 0,
    note: null,
    chat: JSON.parse(sessionStorage.getItem(CHAT_STORAGE) || '[]'),
    chatStreaming: false,
    chatAbort: null,
    graphData: null,
    systemStatus: null,
    searchHistory: [],
    searchResults: null
  };

  var redirectTimer = null;

  /* ============================================================
     UI HELPERS
     ============================================================ */
  function $(sel, ctx) { return (ctx || document).querySelector(sel); }

  function $$(sel, ctx) { return Array.from((ctx || document).querySelectorAll(sel)); }

  function escapeHtml(str) {
    var d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
  }

  function timeAgo(dateStr) {
    if (!dateStr) return '';
    var now = Date.now();
    var d = new Date(dateStr);
    var diff = Math.floor((now - d) / 1000);
    if (diff < 60) return '刚刚';
    if (diff < 3600) return Math.floor(diff / 60) + ' 分钟前';
    if (diff < 86400) return Math.floor(diff / 3600) + ' 小时前';
    if (diff < 2592000) return Math.floor(diff / 86400) + ' 天前';
    return d.toLocaleDateString('zh-CN');
  }

  function notify(msg) {
    if (!_snackEl) _snackEl = document.getElementById('snack');
    if (!_snackEl) return;
    _snackEl.textContent = msg;
    _snackEl.classList.add('show');
    clearTimeout(notify._timer);
    notify._timer = setTimeout(function () { _snackEl.classList.remove('show'); }, 2000);
  }

  function setLoading(v) {
    state.loading = v;
    var el = $('.loading-indicator');
    if (el) el.style.display = v ? 'block' : 'none';
  }

  var ICONS = {
    home: '<path d="M3 11.5 12 4l9 7.5"/><path d="M5.5 10.5V20h13v-9.5M9 20v-6h6v6"/>',
    chat: '<path d="M20 14a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h9a4 4 0 0 1 4 4z"/><path d="M8 9h8M8 13h5"/>',
    note: '<path d="M6 3h9l3 3v15H6z"/><path d="M14 3v4h4M9 11h6M9 15h6"/>',
    graph: '<circle cx="12" cy="5" r="2.5"/><circle cx="5" cy="17" r="2.5"/><circle cx="19" cy="17" r="2.5"/><path d="m10.8 7.2-4.5 7.6m6.9-7.6 4.5 7.6M7.5 17h9"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-1.6v-.2h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1z"/>',
    search: '<circle cx="10.8" cy="10.8" r="6.8"/><path d="m16 16 5 5"/>',
    mic: '<rect x="9" y="3" width="6" height="12" rx="3"/><path d="M6 11a6 6 0 0 0 12 0M12 17v4"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    back: '<path d="m15 18-6-6 6-6"/>',
    more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
    send: '<path d="m4 4 17 8-17 8 3-8zM7 12h14"/>',
    close: '<path d="M18 6 6 18M6 6l12 12"/>',
    check: '<path d="M20 6 9 17l-5-5"/>',
    link: '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
    tag: '<path d="M2 2h7l11 11-7 7L2 9V2z"/><circle cx="6" cy="6" r="1"/>',
    clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    refresh: '<path d="M1 4v6h6M23 20v-6h-6"/><path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4-4.64 4.36A9 9 0 0 1 3.51 15"/>',
    logOut: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
    alertCircle: '<circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/>',
    file: '<path d="M6 3h9l3 3v15H6z"/><path d="M14 3v4h4"/>'
  };

  function icon(name) {
    return '<svg class="icon" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' + (ICONS[name] || '') + '</svg>';
  }

  function statusBar() {
    return '<div class="status"><span>09:41</span><span class="sys"><span>▮▮▮</span><span>◒</span><span>87%</span></span></div>';
  }

  function appBar(title, subtitle, opts) {
    opts = opts || {};
    var left = opts.back ? '<button class="icon-btn" aria-label="返回" data-nav="back">' + icon('back') + '</button>' : '';
    var right = opts.action || '<button class="icon-btn" aria-label="更多" data-notify="更多操作">' + icon('more') + '</button>';
    return '<header class="appbar">' + left + '<div class="title-wrap"><h1>' + escapeHtml(title) + '</h1>' + (subtitle ? '<small>' + escapeHtml(subtitle) + '</small>' : '') + '</div>' + right + '</header>';
  }

  function bottomNav(current) {
    var items = [
      { id: 'home', label: '首页', icon: 'home' },
      { id: 'chat', label: 'AI 对话', icon: 'chat' },
      { id: 'note', label: '笔记', icon: 'note' },
      { id: 'graph', label: '图谱', icon: 'graph' },
      { id: 'settings', label: '设置', icon: 'settings' }
    ];
    return '<nav class="bottom-nav" aria-label="主导航">' +
      items.map(function (item) {
        var active = item.id === current ? ' active' : '';
        return '<button class="nav-item' + active + '" data-nav="' + item.id + '"><span class="icon-wrap">' + icon(item.icon) + '</span><span>' + item.label + '</span></button>';
      }).join('') +
      '</nav><div class="home-indicator"></div>';
  }

  function rowHTML(iconName, title, meta, badge, href) {
    var badgeHtml = badge ? '<span class="chip' + (badge === '已同步' ? ' sync' : '') + '">' + escapeHtml(badge) + '</span>' : '';
    return '<div class="row" data-href="' + (href || '') + '"><span class="row-icon">' + icon(iconName) + '</span><span class="row-main"><span class="row-title">' + escapeHtml(title) + '</span><span class="row-meta">' + escapeHtml(meta) + '</span></span>' + badgeHtml + '</div>';
  }

  function loadingHTML() {
    return '<div class="loading-indicator" style="' + (state.loading ? 'display:block' : 'display:none') + ';text-align:center;padding:40px 0;color:var(--muted);font-size:13px">加载中…</div>';
  }

  function emptyHTML(msg) {
    return '<div style="text-align:center;padding:40px 20px;color:var(--muted);font-size:14px;line-height:1.6">' + escapeHtml(msg) + '</div>';
  }

  function errorHTML(msg) {
    return '<div style="text-align:center;padding:40px 20px;color:var(--danger);font-size:14px"><span style="display:block;margin-bottom:8px">' + icon('alertCircle') + '</span>' + escapeHtml(msg) + '</div>';
  }

  /* ============================================================
     API CLIENT
     ============================================================ */
  function api(method, path, data) {
    var url = API_BASE + path;
    var opts = {
      method: method,
      headers: { 'Content-Type': 'application/json' }
    };
    if (state.token) opts.headers['Authorization'] = 'Bearer ' + state.token;
    if (data) opts.body = JSON.stringify(data);

    return fetch(url, opts).then(function (res) {
      if (res.status === 401 && state.token) {
        return tryRefresh().then(function (refreshed) {
          if (refreshed) {
            opts.headers['Authorization'] = 'Bearer ' + state.token;
            return fetch(url, opts);
          }
          logout();
          throw new Error('登录已过期，请重新登录');
        });
      }
      if (res.status === 423) { logout(); throw new Error('账户已锁定'); }
      if (res.status === 403) { logout(); throw new Error('账户未激活或权限不足'); }
      if (!res.ok) {
        return res.json().then(function (body) {
          throw new Error((body.error && body.error.message) || '请求失败 (' + res.status + ')');
        }).catch(function (e) {
          if (e.message && e.message !== '请求失败 (' + res.status + ')') throw e;
          throw new Error('请求失败 (' + res.status + ')');
        });
      }
      if (res.status === 204) return null;
      return res.json();
    });
  }

  function apiGet(path) { return api('GET', path); }

  function apiPost(path, data) { return api('POST', path, data); }

  function apiPatch(path, data) { return api('PATCH', path, data); }

  function apiDelete(path) { return api('DELETE', path); }

  function tryRefresh() {
    var refreshToken = localStorage.getItem('fuxi_mobile_refresh');
    if (!refreshToken) return Promise.resolve(false);
    return fetch(API_BASE + '/auth/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken })
    }).then(function (res) {
      if (!res.ok) return false;
      return res.json().then(function (data) {
        state.token = data.access_token;
        localStorage.setItem(STORAGE_TOKEN, data.access_token);
        return true;
      });
    }).catch(function () { return false; });
  }

  function login(identifier, password) {
    return apiPost('/auth/login', {
      identifier: identifier,
      password: password,
      client: 'mobile'
    }).then(function (data) {
      state.token = data.access_token;
      state.user = data.user;
      localStorage.setItem(STORAGE_TOKEN, data.access_token);
      localStorage.setItem(STORAGE_USER, JSON.stringify(data.user));
      if (data.refresh_token) localStorage.setItem('fuxi_mobile_refresh', data.refresh_token);
      return data;
    });
  }

  function logout() {
    if (state.token) {
      apiPost('/auth/logout').catch(function () {});
    }
    state.token = null;
    state.user = null;
    localStorage.removeItem(STORAGE_TOKEN);
    localStorage.removeItem(STORAGE_USER);
    localStorage.removeItem('fuxi_mobile_refresh');
    navigate('login');
  }

  function loadNotes(page, size) {
    page = page || 1;
    size = size || 20;
    return apiGet('/notes?page=' + page + '&size=' + size).then(function (data) {
      state.notes = data.items || [];
      state.notesTotal = data.total || 0;
      return data;
    });
  }

  function loadNote(id) {
    return apiGet('/notes/' + id).then(function (data) {
      state.note = data;
      return data;
    });
  }

  function updateNote(id, data) {
    return apiPatch('/notes/' + id, data);
  }

  function loadSystemStatus() {
    return apiGet('/system/status').then(function (data) {
      state.systemStatus = data;
      return data;
    });
  }

  function loadGraph(filter) {
    return apiGet('/graph' + (filter ? '?filter=' + filter : '')).then(function (data) {
      state.graphData = data;
      return data;
    });
  }

  function loadSearchHistory() {
    return apiGet('/search/history').then(function (data) {
      state.searchHistory = data.items || [];
      return data;
    });
  }

  function search(query, mode) {
    mode = mode || 'hybrid';
    return apiPost('/search', { q: query, mode: mode }).then(function (data) {
      state.searchResults = data;
      return data;
    });
  }

  /* ============================================================
     CHAT / QA
     ============================================================ */
  function loadChatHistory() {
    return apiGet('/qa/history').then(function (data) {
      return data.items || [];
    });
  }

  function sendQuestion(question, history, callbacks) {
    state.chatStreaming = true;
    var url = API_BASE + '/qa/stream';
    var opts = {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + state.token
      },
      body: JSON.stringify({
        question: question,
        history: history || []
      })
    };

    var controller = new AbortController();
    state.chatAbort = controller;
    opts.signal = controller.signal;

    return fetch(url, opts).then(function (res) {
      if (!res.ok) {
        state.chatStreaming = false;
        throw new Error('请求失败 (' + res.status + ')');
      }
      var reader = res.body.getReader();
      var decoder = new TextDecoder();
      var buffer = '';

      function read() {
        return reader.read().then(function (result) {
          if (result.done) {
            state.chatStreaming = false;
            state.chatAbort = null;
            if (callbacks.onDone) callbacks.onDone();
            return;
          }
          buffer += decoder.decode(result.value, { stream: true });
          var lines = buffer.split('\n');
          buffer = lines.pop() || '';

          lines.forEach(function (line) {
            if (line.startsWith('data: ')) {
              try {
                var data = JSON.parse(line.slice(6));
                if (data.type === 'sources' || (data.length !== undefined && callbacks.onSources)) {
                  if (callbacks.onSources) callbacks.onSources(data);
                } else if (data.text !== undefined && callbacks.onToken) {
                  callbacks.onToken(data.text);
                } else if (data.generated !== undefined && callbacks.onDone) {
                  if (callbacks.onDone) callbacks.onDone(data);
                }
              } catch (_) {}
            }
          });
          return read();
        });
      }
      return read();
    }).catch(function (err) {
      state.chatStreaming = false;
      state.chatAbort = null;
      if (err.name === 'AbortError') return;
      throw err;
    });
  }

  function stopChat() {
    if (state.chatAbort) {
      state.chatAbort.abort();
      state.chatAbort = null;
      state.chatStreaming = false;
    }
  }

  function saveChat() {
    sessionStorage.setItem(CHAT_STORAGE, JSON.stringify(state.chat));
  }

  /* ============================================================
     ROUTER
     ============================================================ */
  function navigate(screen, params) {
    screen = screen || 'home';
    if (screen === 'back') {
      window.history.back();
      return;
    }
    state.screen = screen;
    state.params = params || {};
    state.error = null;

    if (screen !== 'login') {
      var hash = screen;
      if (params && params.id) hash += '/' + params.id;
      if (window.location.hash !== '#' + hash) {
        window.location.hash = hash;
      }
      render();
    } else {
      if (window.location.hash) window.location.hash = '';
      render();
    }
  }

  function parseHash() {
    var hash = window.location.hash.replace(/^#/, '') || '';
    if (!hash) return { screen: state.user ? 'home' : 'login', params: {} };
    var parts = hash.split('/');
    return { screen: parts[0], params: { id: parts[1] } };
  }

  /* ============================================================
     SCREEN RENDERERS
     ============================================================ */
  var _snackEl = null;

  function render() {
    var phone = document.getElementById('phone');
    if (!phone) return;

    if (!state.user) {
      state.screen = 'login';
    }

    var screen = state.screen;
    var params = state.params;
    var html = statusBar();

    switch (screen) {
      case 'login':
        html += renderLogin();
        break;
      case 'home':
        html += renderHome();
        break;
      case 'chat':
        html += renderChat();
        break;
      case 'note':
        html += renderNote(params.id);
        break;
      case 'graph':
        html += renderGraph();
        break;
      case 'settings':
        html += renderSettings();
        break;
      default:
        html += renderHome();
        state.screen = 'home';
    }

    if (screen !== 'login') {
      html += bottomNav(screen);
    }

    if (!_snackEl) _snackEl = document.getElementById('snack');
    phone.innerHTML = html;
    if (_snackEl) phone.appendChild(_snackEl);
    bindEvents();
    afterRender();
  }

  function afterRender() {
    if (state.screen === 'home' && state.user) {
      refreshHome();
    } else if (state.screen === 'chat') {
      scrollChat();
    } else if (state.screen === 'settings') {
      refreshSettings();
    } else if (state.screen === 'graph') {
      renderGraphNodes();
    } else if (state.screen === 'note' && state.params && state.params.id) {
      refreshNote(state.params.id);
    }
  }

  function bindEvents() {
    /* Nav buttons */
    $$('[data-nav]').forEach(function (el) {
      el.addEventListener('click', function () {
        var target = el.dataset.nav;
        if (target === 'back') {
          navigate('home');
        } else {
          navigate(target);
        }
      });
    });

    /* Login form */
    var loginForm = $('#login-form');
    if (loginForm) {
      loginForm.addEventListener('submit', function (e) {
        e.preventDefault();
        var username = $('#login-username');
        var password = $('#login-password');
        if (!username || !password) return;
        var btn = loginForm.querySelector('.login-submit');
        btn.disabled = true;
        btn.textContent = '登录中…';
        login(username.value, password.value).then(function () {
          navigate('home');
        }).catch(function (err) {
          notify(err.message || '登录失败');
          btn.disabled = false;
          btn.textContent = '登录';
        });
      });
    }

    /* Search */
    var searchInput = $('[data-search]');
    if (searchInput) {
      searchInput.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && searchInput.value.trim()) {
          var q = searchInput.value.trim();
          notify('正在检索「' + q + '」');
          search(q).then(function (res) {
            showSearchResults(res);
          }).catch(function (err) {
            notify(err.message || '搜索失败');
          });
        }
      });
      searchInput.addEventListener('focus', function () {
        showSearchSuggestions();
      });
      searchInput.addEventListener('blur', function (e) {
        setTimeout(function () {
          var panel = $('#search-panel');
          if (!panel) return;
          if (document.activeElement && panel.contains(document.activeElement)) return;
          panel.style.display = 'none';
        }, 300);
      });
    }

    /* Quick capture */
    var captureInput = $('[data-capture]');
    var captureBtn = $('[data-capture-submit]');
    if (captureInput && captureBtn) {
      captureBtn.addEventListener('click', function () {
        var text = captureInput.value.trim();
        if (!text) { notify('先写下一条想法'); return; }
        var isUrl = /^https?:\/\/\S+/.test(text);
        if (!isUrl) { notify('暂仅支持链接保存，文字笔记请使用 Web 端'); return; }
        captureBtn.disabled = true;
        captureBtn.textContent = '保存中…';
        apiPost('/ingest/url', { url: text }).then(function () {
          notify('已添加到知识库');
          captureInput.value = '';
          captureBtn.disabled = false;
          captureBtn.textContent = '保存';
          refreshHome();
        }).catch(function (err) {
          notify(err.message || '保存失败');
          captureBtn.disabled = false;
          captureBtn.textContent = '保存';
        });
      });
    }

    /* Chat composer */
    var composer = $('[data-composer]');
    var sendBtn = $('[data-send]');
    if (composer && sendBtn) {
      sendBtn.addEventListener('click', function () {
        var text = composer.value.trim();
        if (!text) { notify('请输入问题'); return; }
        composer.value = '';
        composer.style.height = 'auto';
        addChatMessage('user', text);
        doChatStream(text);
      });
      composer.addEventListener('input', function () {
        composer.style.height = 'auto';
        var maxH = Math.min(composer.scrollHeight, 100);
        if (maxH > 40) composer.style.height = maxH + 'px';
      });
      composer.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          sendBtn.click();
        }
      });
    }

    /* Note editor */
    var noteTitle = $('.editor-title');
    var noteBody = $('.editor-body');
    var noteSave = $('[data-save]');
    if (noteSave && noteTitle && noteBody) {
      var saveTimer = null;
      function triggerSave() {
        clearTimeout(saveTimer);
        saveTimer = setTimeout(function () {
          var id = state.params.id;
          if (!id) return;
          updateNote(id, {
            title: noteTitle.value,
            content: noteBody.value
          }).then(function () {
            notify('笔记已保存');
          }).catch(function (err) {
            notify(err.message || '保存失败');
          });
        }, 1500);
      }
      noteTitle.addEventListener('input', triggerSave);
      noteBody.addEventListener('input', triggerSave);
      noteSave.addEventListener('click', function () {
        clearTimeout(saveTimer);
        var id = state.params.id;
        if (!id) return;
        updateNote(id, {
          title: noteTitle.value,
          content: noteBody.value
        }).then(function () {
          notify('笔记已同步');
        }).catch(function (err) {
          notify(err.message || '同步失败');
        });
      });
    }

    /* Settings — switches */
    $$('.switch').forEach(function (el) {
      el.addEventListener('click', function () {
        el.classList.toggle('on');
        el.setAttribute('aria-checked', String(el.classList.contains('on')));
        notify(el.classList.contains('on') ? '已开启' : '已关闭');
      });
    });

    /* Settings — logout */
    var logoutBtn = $('[data-logout]');
    if (logoutBtn) {
      logoutBtn.addEventListener('click', function () {
        logout();
      });
    }

    /* Graph node click */
    $$('.node').forEach(function (el) {
      el.addEventListener('click', function () {
        hoverNode(el.dataset.entityId, el.textContent.trim(), el.dataset.count || '');
      });
    });

    /* Data-notify buttons */
    $$('[data-notify]').forEach(function (el) {
      el.addEventListener('click', function () {
        notify(el.dataset.notify);
      });
    });

    /* Row click → navigate */
    $$('.row[data-href]').forEach(function (el) {
      el.addEventListener('click', function () {
        var href = el.dataset.href;
        if (href) navigate('note', { id: href });
      });
    });

    /* Search result click */
    $$('[data-search-result]').forEach(function (el) {
      el.addEventListener('click', function () {
        navigate('note', { id: el.dataset.searchResult });
      });
    });

    /* Chat history items */
    $$('[data-chat-item]').forEach(function (el) {
      el.addEventListener('click', function () {
        var id = el.dataset.chatItem;
        loadChatFromHistory(id);
      });
    });

    /* Stop streaming */
    var stopBtn = $('[data-stop-chat]');
    if (stopBtn) {
      stopBtn.addEventListener('click', function () {
        stopChat();
      });
    }
  }

  /* ============================================================
     LOGIN SCREEN
     ============================================================ */
  function renderLogin() {
    return '<main class="content" style="display:flex;flex-direction:column;align-items:center;justify-content:center;padding:40px 32px;min-height:100%">' +
      '<div style="width:100%;max-width:320px">' +
      '<h1 style="font-size:28px;font-weight:600;letter-spacing:-.02em;margin:0 0 4px">Atlas</h1>' +
      '<p style="color:var(--muted);margin:0 0 32px;font-size:14px">登录你的知识库</p>' +
      '<form id="login-form">' +
      '<div style="margin-bottom:16px">' +
      '<label style="display:block;font-size:12px;color:var(--muted);margin-bottom:6px;font-family:var(--font-mono);letter-spacing:.05em">用户名 / 邮箱</label>' +
      '<input id="login-username" type="text" autocomplete="username" style="width:100%;min-height:48px;padding:0 14px;border:1px solid var(--border-strong);border-radius:12px;outline:0;background:var(--surface);font-size:15px" placeholder="zhangsan" required>' +
      '</div>' +
      '<div style="margin-bottom:24px">' +
      '<label style="display:block;font-size:12px;color:var(--muted);margin-bottom:6px;font-family:var(--font-mono);letter-spacing:.05em">密码</label>' +
      '<input id="login-password" type="password" autocomplete="current-password" style="width:100%;min-height:48px;padding:0 14px;border:1px solid var(--border-strong);border-radius:12px;outline:0;background:var(--surface);font-size:15px" placeholder="••••••••" required>' +
      '</div>' +
      '<button type="submit" class="login-submit" style="width:100%;min-height:48px;border-radius:24px;background:var(--fg);color:var(--surface);font-weight:600;font-size:15px;letter-spacing:.02em;border:0;cursor:pointer">登录</button>' +
      '</form>' +
      '<p style="text-align:center;margin-top:20px;color:var(--muted-2);font-size:11px;font-family:var(--font-mono)">Atlas 移动端 v0.5</p>' +
      '</div></main>';
  }

  /* ============================================================
     HOME SCREEN
     ============================================================ */
  function renderHome() {
    var greeting = '下午好';
    var hour = new Date().getHours();
    if (hour < 6) greeting = '夜深了';
    else if (hour < 9) greeting = '早上好';
    else if (hour < 12) greeting = '上午好';
    else if (hour < 14) greeting = '中午好';
    else if (hour < 18) greeting = '下午好';
    else greeting = '晚上好';

    var displayName = state.user ? (state.user.display_name || state.user.username || '') : '';

    var recentHTML = '';
    if (state.notes.length === 0) {
      recentHTML = '<div class="card">' + emptyHTML('还没有知识，开始记录吧') + '</div>';
    } else {
      recentHTML = '<div class="card">' +
        state.notes.slice(0, 5).map(function (note) {
          var iconName = note.type === 'chat' ? 'chat' : 'file';
          var badge = note.ingest_status === 'done' ? '已同步' : (note.ingest_status === 'error' ? '失败' : '处理中');
          return rowHTML(iconName, note.title || '无标题', timeAgo(note.date || note.created_at), badge, note.id);
        }).join('') +
        '</div>';
    }

    return appBar(greeting + '，' + displayName, '知识库 · ' + state.notesTotal + ' 条笔记', {
      action: '<button class="icon-btn" aria-label="新建笔记" data-notify="请在 Web 端创建新笔记">' + icon('plus') + '</button>'
    }) +
    '<main class="content">' +
    '<div class="search-hero">' + icon('search') +
    '<input class="search-input" data-search aria-label="搜索知识库" placeholder="搜索笔记、网页与对话" />' +
    '<button class="icon-btn search-action" aria-label="语音搜索" data-notify="语音输入已就绪">' + icon('mic') + '</button>' +
    '</div>' +
    '<div id="search-panel" style="display:none"></div>' +
    '<section><div class="section-head"><h2>快速记录</h2><span>自动归档</span></div>' +
    '<div class="card capture"><textarea data-capture aria-label="快速记录" placeholder="记下一条想法，或粘贴链接…"></textarea>' +
    '<div class="capture-foot"><div class="tools"><button class="icon-btn" aria-label="添加附件" data-notify="选择附件">' + icon('plus') + '</button><button class="icon-btn" aria-label="语音记录" data-notify="开始语音记录">' + icon('mic') + '</button></div>' +
    '<button class="primary" data-capture-submit>保存</button></div></div></section>' +
    '<section><div class="section-head"><h2>最近知识</h2><button data-nav="home" data-notify="已在首页展示最近知识">查看全部</button></div>' +
    recentHTML + '</section>' +
    loadingHTML() +
    '</main>';
  }

  function refreshHome() {
    if (state.screen !== 'home') return;
    setLoading(true);
    loadNotes(1, 10).then(function () {
      setLoading(false);
      if (state.screen === 'home') {
        /* update recent list */
        var recentSection = $('.content > section:last-child');
        if (recentSection) {
          var head = recentSection.querySelector('.section-head');
          var card = recentSection.querySelector('.card');
          if (head && card) {
            var newHTML = '';
            if (state.notes.length === 0) {
              newHTML = emptyHTML('还没有知识，开始记录吧');
            } else {
              newHTML = state.notes.slice(0, 5).map(function (note) {
                var iconName = note.type === 'chat' ? 'chat' : 'file';
                var badge = note.ingest_status === 'done' ? '已同步' : (note.ingest_status === 'error' ? '失败' : '处理中');
                return rowHTML(iconName, note.title || '无标题', timeAgo(note.date || note.created_at), badge, note.id);
              }).join('');
            }
            /* replace card content, re-bind */
            card.innerHTML = newHTML;
            $$('.row[data-href]', card).forEach(function (el) {
              el.addEventListener('click', function () {
                var href = el.dataset.href;
                if (href) navigate('note', { id: href });
              });
            });
          }
        }
        /* update subtitle */
        var subtitle = $('.appbar small');
        if (subtitle) subtitle.textContent = '知识库 · ' + state.notesTotal + ' 条笔记';
      }
    }).catch(function (err) {
      setLoading(false);
    });
  }

  function showSearchSuggestions() {
    var panel = $('#search-panel');
    if (!panel) return;
    if (state.searchHistory.length === 0) {
      loadSearchHistory().then(function () {
        renderSearchSuggestions();
      }).catch(function () {});
    } else {
      renderSearchSuggestions();
    }
  }

  function renderSearchSuggestions() {
    var panel = $('#search-panel');
    if (!panel || state.screen !== 'home') return;
    if (state.searchHistory.length === 0) {
      panel.innerHTML = '<div class="card" style="margin-top:4px;padding:12px 14px;color:var(--muted);font-size:12px">最近没有搜索记录</div>';
    } else {
      panel.innerHTML = '<div class="card" style="margin-top:4px">' +
        state.searchHistory.slice(0, 5).map(function (item) {
          return '<div class="row" style="min-height:48px" data-chat-item="' + item.id + '"><span class="row-icon">' + icon('clock') + '</span><span class="row-main"><span class="row-title">' + escapeHtml(item.q) + '</span><span class="row-meta">' + item.hits + ' 条结果 · ' + timeAgo(item.created_at) + '</span></span></div>';
        }).join('') + '</div>';
    }
    panel.style.display = 'block';
  }

  function showSearchResults(res) {
    var panel = $('#search-panel');
    if (!panel) return;
    if (!res || !res.results || res.results.length === 0) {
      panel.innerHTML = '<div class="card" style="margin-top:4px;padding:12px 14px;color:var(--muted);font-size:12px">没有找到结果</div>';
    } else {
      panel.innerHTML = '<div class="card" style="margin-top:4px">' +
        '<div class="section-head" style="padding:8px 14px 4px;margin:0"><h2>' + res.total + ' 条结果</h2><span>' + Math.round(res.took_ms) + 'ms</span></div>' +
        res.results.slice(0, 5).map(function (r) {
          return '<div class="row" style="min-height:48px" data-search-result="' + r.id + '"><span class="row-icon">' + icon('file') + '</span><span class="row-main"><span class="row-title">' + escapeHtml(r.title) + '</span><span class="row-meta">' + (r.snippet ? r.snippet.replace(/<\/?em>/g, '') : r.summary || '').slice(0, 60) + '</span></span><span class="chip">' + (r.score ? Math.round(r.score * 100) + '%' : '') + '</span></div>';
        }).join('') +
        (res.total > 5 ? '<div style="padding:10px 14px;text-align:center;color:var(--muted);font-size:12px;border-top:1px solid var(--border)">还有 ' + (res.total - 5) + ' 条结果</div>' : '') +
        '</div>';
    }
    panel.style.display = 'block';
    $$('[data-search-result]', panel).forEach(function (el) {
      el.addEventListener('click', function () {
        navigate('note', { id: el.dataset.searchResult });
      });
    });
  }

  /* ============================================================
     CHAT SCREEN
     ============================================================ */
  function renderChat() {
    var msgs = state.chat.length > 0 ? state.chat : [
      { role: 'ai', text: '你好！我是 Atlas AI 助手。我可以回答你关于知识库的问题，引用笔记中的内容来提供准确的答案。试试问我关于你的研究或笔记的内容。' }
    ];
    return appBar('AI 对话', state.notesTotal + ' 条知识') +
    '<main class="content" style="padding-bottom:140px">' +
    '<div class="chat" id="chat-messages">' +
    msgs.map(function (msg) {
      if (msg.role === 'user') {
        return '<div class="bubble user">' + escapeHtml(msg.text) + '</div>';
      } else {
        return '<article class="bubble ai">' +
          (msg.sources && msg.sources.length > 0
            ? '<div class="sources">' + msg.sources.map(function (s) { return '<span class="chip ai-chip">' + escapeHtml(s.title || s.id || '来源') + '</span>'; }).join('') + '</div>'
            : '') +
          '<strong style="display:block;margin-bottom:6px;font-weight:600">AI</strong>' + renderMarkdown(msg.text) + '</article>';
      }
    }).join('') +
    (state.chatStreaming ? '<article class="bubble ai" id="streaming-bubble"><strong style="display:block;margin-bottom:6px;font-weight:600">AI</strong><span id="streaming-text"></span></article>' : '') +
    (state.chatStreaming ? '' : '') +
    '</div>' +
    loadingHTML() +
    '</main>' +
    '<div class="composer">' +
    (state.chatStreaming
      ? '<button class="send" data-stop-chat aria-label="停止生成" style="background:var(--danger)">' + icon('close') + '</button>'
      : '<textarea data-composer aria-label="继续提问" placeholder="继续提问…"></textarea><button class="send" data-send aria-label="发送">' + icon('send') + '</button>'
    ) +
    '</div>';
  }

  function scrollChat() {
    var msgs = $('#chat-messages');
    if (msgs) msgs.scrollTop = msgs.scrollHeight;
  }

  function addChatMessage(role, text, sources) {
    state.chat.push({ role: role, text: text, sources: sources || [] });
    saveChat();
    var msgs = $('#chat-messages');
    if (!msgs) return;
    var div = document.createElement('div');
    if (role === 'user') {
      div.className = 'bubble user';
      div.textContent = text;
    } else {
      div.className = 'bubble ai';
      var sourcesHtml = sources && sources.length > 0
        ? '<div class="sources">' + sources.map(function (s) { return '<span class="chip ai-chip">' + escapeHtml(s.title || s.id) + '</span>'; }).join('') + '</div>'
        : '';
      div.innerHTML = sourcesHtml + '<strong style="display:block;margin-bottom:6px;font-weight:600">AI</strong>' + renderMarkdown(text);
    }
    msgs.appendChild(div);
    scrollChat();
  }

  function doChatStream(question) {
    var msgs = $('#chat-messages');
    if (!msgs) return;

    var bubble = document.createElement('article');
    bubble.className = 'bubble ai';
    bubble.innerHTML = '<strong style="display:block;margin-bottom:6px;font-weight:600">AI</strong><span id="streaming-text"></span>';
    msgs.appendChild(bubble);
    scrollChat();

    var textSpan = document.getElementById('streaming-text');
    var chatSources = [];

    sendQuestion(question, state.chat.map(function (m) { return { role: m.role, text: m.text }; }), {
      onSources: function (sources) {
        chatSources = sources;
        var sourcesDiv = document.createElement('div');
        sourcesDiv.className = 'sources';
        sourcesDiv.innerHTML = sources.map(function (s) { return '<span class="chip ai-chip">' + escapeHtml(s.title || s.id) + '</span>'; }).join('');
        bubble.insertBefore(sourcesDiv, bubble.firstChild);
      },
      onToken: function (text) {
        if (textSpan) textSpan.textContent += text;
        scrollChat();
      },
      onDone: function () {
        var finalText = textSpan ? textSpan.textContent : '';
        state.chat.push({ role: 'ai', text: finalText, sources: chatSources });
        saveChat();
        render();
      }
    }).catch(function (err) {
      notify(err.message || '对话失败');
      render();
    });
  }

  function loadChatFromHistory(id) {
    /* For now, just navigate to chat screen */
    navigate('chat');
  }

  /* minimal markdown renderer */
  function renderMarkdown(text) {
    if (!text) return '';
    var html = escapeHtml(text);
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\n/g, '<br>');
    return html;
  }

  /* ============================================================
     NOTE SCREEN
     ============================================================ */
  function renderNote(id) {
    if (state.note && state.note.id === id) {
      return renderNoteContent(state.note);
    }
    return appBar('笔记', '加载中…', {
      back: true,
      action: '<button class="icon-btn" data-save aria-label="保存笔记"><span class="save-state">保存</span></button>'
    }) +
    '<main class="content">' + loadingHTML() + '</main>';
  }

  function renderNoteContent(note) {
    var tags = (note.tags || []).map(function (t) { return '<span class="chip">' + escapeHtml(typeof t === 'string' ? t : (t.name || t)) + '</span>'; }).join('');
    var entities = (note.entities || []).map(function (e) { return '<span class="chip ' + (e.cat === 'ai' ? 'ai-chip' : '') + '">' + escapeHtml(e.name) + '</span>'; }).join('');
    var body = (note.original || []).join('\n\n') || note.summary || note.content || '';

    return appBar('笔记', note.title || '无标题', {
      back: true,
      action: '<button class="icon-btn" data-save aria-label="保存笔记"><span class="save-state">保存</span></button>'
    }) +
    '<main class="content">' +
    '<input class="editor-title" aria-label="笔记标题" value="' + escapeHtml(note.title || '') + '" />' +
    '<div class="editor-meta">' + tags + entities + (note.ingest_status === 'done' ? '<span class="chip sync">已索引</span>' : '') + '</div>' +
    '<textarea class="editor-body" aria-label="笔记正文">' + escapeHtml(body) + '</textarea>' +
    '</main>';
  }

  function refreshNote(id) {
    if (!id) return;
    setLoading(true);
    loadNote(id).then(function () {
      setLoading(false);
      if (state.screen === 'note' && state.params.id === id) {
        var content = $('.content');
        if (content) {
          var appbar = $('.appbar');
          var existingBody = content.querySelector('.editor-body');
          if (existingBody) {
            /* update in place without full re-render */
            var titleInput = $('.editor-title');
            var metaDiv = $('.editor-meta');
            if (titleInput) titleInput.value = state.note.title || '';
            if (metaDiv) {
              var tags = (state.note.tags || []).map(function (t) { return '<span class="chip">' + escapeHtml(typeof t === 'string' ? t : (t.name || t)) + '</span>'; }).join('');
              var entities = (state.note.entities || []).map(function (e) { return '<span class="chip ' + (e.cat === 'ai' ? 'ai-chip' : '') + '">' + escapeHtml(e.name) + '</span>'; }).join('');
              metaDiv.innerHTML = tags + entities + (state.note.ingest_status === 'done' ? '<span class="chip sync">已索引</span>' : '');
            }
            existingBody.value = (state.note.original || []).join('\n\n') || state.note.summary || state.note.content || '';
          } else {
            render();
          }
          if (appbar) {
            var sub = appbar.querySelector('small');
            if (sub) sub.textContent = state.note.title || '无标题';
          }
        }
      }
    }).catch(function (err) {
      setLoading(false);
      notify(err.message || '加载笔记失败');
    });
  }

  /* ============================================================
     GRAPH SCREEN
     ============================================================ */
  function renderGraph() {
    return appBar('知识图谱', '触控节点以展开关联', {
      back: false,
      action: '<button class="icon-btn" aria-label="图谱筛选" data-nav="graph" data-notify="筛选器已打开">' + icon('search') + '</button>'
    }) +
    '<main class="content" style="padding:0;overflow:hidden">' +
    '<div class="graph-wrap"><div class="graph-grid"></div><div id="graph-nodes"></div></div>' +
    '<aside class="graph-sheet" id="graph-sheet" style="display:none"><b id="graph-sheet-title"></b><p id="graph-sheet-desc"></p></aside>' +
    loadingHTML() +
    '</main>';
  }

  function renderGraphNodes() {
    if (state.graphData) {
      drawGraph(state.graphData);
      return;
    }
    setLoading(true);
    loadGraph().then(function () {
      setLoading(false);
      drawGraph(state.graphData);
    }).catch(function (err) {
      setLoading(false);
      var container = $('#graph-nodes');
      if (container) container.innerHTML = '<div style="text-align:center;padding:40px;color:var(--muted)">图谱加载失败</div>';
    });
  }

  function drawGraph(data) {
    var container = $('#graph-nodes');
    if (!container || !data) return;

    if (!data.nodes || data.nodes.length === 0) {
      container.innerHTML = emptyHTML('还没有知识关联');
      return;
    }

    var wrap = container.parentElement;
    var rect = wrap ? wrap.getBoundingClientRect() : { width: 400, height: 520 };
    var w = rect.width || 400;
    var h = rect.height || 520;
    var cx = w / 2;
    var cy = h / 2;
    var radius = Math.min(w, h) * 0.32;

    /* simple circular layout */
    var nodes = data.nodes;
    var edges = data.edges || [];
    var nodeMap = {};
    var positions = [];

    var halfNode = 23;
    nodes.forEach(function (n, i) {
      var angle = (i / nodes.length) * 2 * Math.PI - Math.PI / 2;
      var x = cx + radius * Math.cos(angle) - halfNode;
      var y = cy + radius * Math.sin(angle) - halfNode;
      positions.push({ x: x, y: y, node: n });
      nodeMap[n.id] = { x: x + halfNode, y: y + halfNode, name: n.name, cat: n.cat };
    });

    /* draw edges */
    var edgeHtml = edges.map(function (edge) {
      var from = nodeMap[edge[0]];
      var to = nodeMap[edge[1]];
      if (!from || !to) return '';
      var dx = to.x - from.x;
      var dy = to.y - from.y;
      var length = Math.sqrt(dx * dx + dy * dy);
      var angle = Math.atan2(dy, dx) * 180 / Math.PI;
      return '<span class="edge" style="left:' + from.x + 'px;top:' + from.y + 'px;width:' + length + 'px;transform:rotate(' + angle + 'deg)"></span>';
    }).join('');

    /* draw nodes */
    var nodeHtml = positions.map(function (p) {
      var catClass = p.node.cat === 'concept' ? 'ai' : '';
      var coreClass = p.node.count > 3 ? 'core' : '';
      return '<button class="node ' + catClass + ' ' + coreClass + '" style="left:' + p.x + 'px;top:' + p.y + 'px" data-entity-id="' + escapeHtml(p.node.id) + '" data-count="' + (p.node.count || 0) + '">' + escapeHtml(p.node.name) + '</button>';
    }).join('');

    container.innerHTML = edgeHtml + nodeHtml;

    /* bind node clicks */
    $$('.node', container).forEach(function (el) {
      el.addEventListener('click', function () {
        hoverNode(el.dataset.entityId, el.textContent.trim(), el.dataset.count || '');
      });
    });
  }

  function hoverNode(id, name, count) {
    var sheet = $('#graph-sheet');
    var title = $('#graph-sheet-title');
    var desc = $('#graph-sheet-desc');
    if (!sheet || !title || !desc) return;
    title.textContent = name || '未知实体';
    desc.textContent = count ? count + ' 个关联笔记' : '暂无关联';
    sheet.style.display = 'block';

    $$('.node.core').forEach(function (el) { el.classList.remove('core'); });
    var active = document.querySelector('.node[data-entity-id="' + id + '"]');
    if (active) active.classList.add('core');
  }

  /* ============================================================
     SETTINGS SCREEN
     ============================================================ */
  function renderSettings() {
    var user = state.user || {};
    var displayName = user.display_name || user.username || '';
    var role = user.role || 'member';
    var status = state.systemStatus || {};
    return appBar('设置', 'Atlas 移动端') +
    '<main class="content">' +
    '<section class="setting-group"><p class="setting-label">账户</p><div class="card">' +
    '<div class="setting-row"><span>' + escapeHtml(displayName) + '</span><small>' + escapeHtml(role) + '</small></div>' +
    '<div class="setting-row"><span>邮箱</span><small>' + escapeHtml(user.email || '—') + '</small></div>' +
    '</div></section>' +
    '<section class="setting-group"><p class="setting-label">同步与索引</p><div class="card">' +
    '<div class="setting-row"><span>知识库同步</span><button class="switch on" role="switch" aria-checked="true" aria-label="知识库同步"></button></div>' +
    '<div class="setting-row"><span>笔记数量</span><span class="chip sync">' + (status.notes || state.notesTotal || '—') + ' 条</span></div>' +
    '<div class="setting-row"><span>实体数量</span><span class="chip">' + (status.entities || '—') + '</span></div>' +
    '<div class="setting-row"><span>索引状态</span><small class="sync">' + (status.pg_version ? '正常' : '—') + '</small></div>' +
    '</div></section>' +
    '<section class="setting-group"><p class="setting-label">AI</p><div class="card">' +
    '<div class="setting-row"><span>仅使用我的知识</span><button class="switch on" role="switch" aria-checked="true" aria-label="仅使用我的知识"></button></div>' +
    '<div class="setting-row"><span>显示引用来源</span><button class="switch on" role="switch" aria-checked="true" aria-label="显示引用来源"></button></div>' +
    '</div></section>' +
    '<section class="setting-group"><p class="setting-label">其他</p><div class="card">' +
    '<div class="setting-row"><span>缓存</span><small>' + (status.db_size_bytes ? Math.round(status.db_size_bytes / 1048576) + ' MB' : '—') + '</small></div>' +
    '<div class="setting-row" data-logout style="color:var(--danger);cursor:pointer"><span>退出登录</span>' + icon('logOut') + '</div>' +
    '</div></section>' +
    '<p style="text-align:center;color:var(--muted-2);font-size:10px;font-family:var(--font-mono);margin-top:20px">Atlas v' + (status.version || '0.5') + '</p>' +
    '</main>';
  }

  function refreshSettings() {
    if (state.screen !== 'settings') return;
    loadSystemStatus().then(function () {
      if (state.screen === 'settings') {
        /* update status values in place */
        var noteCount = $('.setting-row:nth-child(2) .chip');
        if (noteCount) noteCount.textContent = (state.systemStatus.notes || '—') + ' 条';
        var entityCount = $('.setting-row:nth-child(3) .chip');
        if (entityCount) entityCount.textContent = (state.systemStatus.entities || '—');
        var p = $('.setting-group:last-child + p');
        if (p) p.textContent = 'Atlas v' + (state.systemStatus.version || '0.5');
      }
    }).catch(function () {});
  }

  /* ============================================================
     INIT
     ============================================================ */
  function init() {
    var hash = parseHash();
    if (state.user) {
      state.screen = hash.screen;
      state.params = hash.params;
    } else {
      state.screen = 'login';
    }

    render();

    window.addEventListener('hashchange', function () {
      var h = parseHash();
      state.screen = h.screen;
      state.params = h.params;
      render();
    });
  }

  document.addEventListener('DOMContentLoaded', init);
})();
