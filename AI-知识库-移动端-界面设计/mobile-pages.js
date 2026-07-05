(function () {
  var body = document.body;
  var platform = body.dataset.platform;
  var screen = body.dataset.screen;
  var isIOS = platform === 'ios';
  var names = { home: '首页', chat: 'AI 对话', note: '笔记', graph: '图谱', settings: '设置' };
  var rowIndex = 0;
  var settingIndex = 0;
  var files = {
    ios: { home: 'ios-home.html', chat: 'ios-chat.html', note: 'ios-note.html', graph: 'ios-graph.html', settings: 'ios-settings.html' },
    android: { home: 'android-home.html', chat: 'android-chat.html', note: 'android-note.html', graph: 'android-graph.html', settings: 'android-settings.html' }
  };
  var icons = {
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
    send: '<path d="m4 4 17 8-17 8 3-8zM7 12h14"/>'
  };
  function icon(name) { return '<svg class="icon" aria-hidden="true" viewBox="0 0 24 24">' + icons[name] + '</svg>'; }
  function status() {
    return '<div class="status" data-od-id="' + platform + '-status-bar"><span>' + (isIOS ? '9:41' : '09:41') + '</span><span class="sys"><span>▮▮▮</span><span>◒</span><span>87%</span></span></div>';
  }
  function nav() {
    return '<nav class="bottom-nav" data-od-id="' + platform + '-primary-nav" aria-label="主导航">' +
      ['home', 'chat', 'note', 'graph', 'settings'].map(function (item) {
        return '<a class="nav-item ' + (item === screen ? 'active' : '') + '" data-od-id="' + platform + '-nav-' + item + '" href="' + files[platform][item] + '"><span class="icon-wrap">' + icon(item) + '</span><span>' + names[item] + '</span></a>';
      }).join('') + '</nav><div class="home-indicator"></div>';
  }
  function appbar(title, subtitle, action) {
    return '<header class="appbar" data-od-id="' + platform + '-' + screen + '-appbar">' +
      (screen === 'home' ? '' : '<a class="icon-btn" aria-label="返回" href="' + files[platform].home + '">' + icon('back') + '</a>') +
      '<div class="title-wrap"><h1 data-od-id="' + platform + '-' + screen + '-title">' + title + '</h1>' + (subtitle ? '<small>' + subtitle + '</small>' : '') + '</div>' +
      (action || '<button class="icon-btn" aria-label="更多" data-notify="更多操作">' + icon('more') + '</button>') + '</header>';
  }
  function searchBox() {
    return '<div class="search-hero" data-od-id="' + platform + '-' + screen + '-search">' + icon('search') +
      '<input class="search-input" data-search aria-label="搜索知识库" placeholder="搜索笔记、网页与对话" />' +
      '<button class="icon-btn search-action" aria-label="语音搜索" data-notify="语音输入已就绪">' + icon('mic') + '</button></div>';
  }
  function home() {
    return appbar('下午好，Raymond', '知识库已同步 · 刚刚', '<button class="icon-btn" aria-label="新增笔记" data-notify="已新建空白笔记">' + icon('plus') + '</button>') +
      '<main class="content" data-od-id="' + platform + '-home-content">' + searchBox() +
      '<section data-od-id="' + platform + '-quick-capture"><div class="section-head"><h2>快速记录</h2><span>自动归档</span></div><div class="card capture"><textarea data-capture aria-label="快速记录" placeholder="记下一条想法，或粘贴链接…"></textarea><div class="capture-foot"><div class="tools"><button class="icon-btn" aria-label="添加附件" data-notify="选择附件">' + icon('plus') + '</button><button class="icon-btn" aria-label="语音记录" data-notify="开始语音记录">' + icon('mic') + '</button></div><button class="primary" data-capture-submit>保存</button></div></div></section>' +
      '<section data-od-id="' + platform + '-recent-knowledge"><div class="section-head"><h2>最近知识</h2><button data-notify="已切换为全部内容">查看全部</button></div><div class="card">' +
      row('note', 'Sparse autoencoders 的层级语义提取', '研究笔记 · 12 分钟前', '已同步') +
      row('chat', 'RAG 重排序策略对比', 'AI 对话 · 昨天', '6 个来源') +
      row('note', '个人知识库的信息架构', '产品思考 · 6 月 28 日', '3 个关联') +
      '</div></section></main>';
  }
  function row(type, title, meta, tail) {
    rowIndex += 1;
    return '<a class="row" data-od-id="' + platform + '-recent-row-' + rowIndex + '" href="' + (type === 'chat' ? files[platform].chat : files[platform].note) + '"><span class="row-icon">' + icon(type) + '</span><span class="row-main"><span class="row-title">' + title + '</span><span class="row-meta">' + meta + '</span></span><span class="chip ' + (tail === '已同步' ? 'sync' : '') + '">' + tail + '</span></a>';
  }
  function chat() {
    return appbar('AI 对话', '基于 1,284 条知识') +
      '<main class="content" data-od-id="' + platform + '-chat-content"><div class="chat">' +
      '<div class="bubble user" data-od-id="' + platform + '-chat-question">SAE 在不同层级的可解释性有什么区别？</div>' +
      '<article class="bubble ai" data-od-id="' + platform + '-chat-answer"><strong>可以分成“原子—组合—回路”三个层级。</strong>浅层 SAE 更容易对应局部词法特征；中层开始形成跨 token 的概念组合；深层则更接近任务策略与回路行为。判断解释质量时，不能只看单个特征的可读性，还要看它在上下文中的稳定激活。<div class="sources"><span class="chip ai-chip">1 · Anthropic SAE</span><span class="chip ai-chip">2 · 我的实验</span><span class="chip">查看 4 个来源</span></div></article>' +
      '<div class="bubble user" data-od-id="' + platform + '-chat-followup">把这个结论和我的实验笔记对照一下。</div>' +
      '<article class="bubble ai" data-od-id="' + platform + '-chat-comparison"><strong>你的记录支持中层特征更稳定，但深层结果仍不充分。</strong>“层 12 / 特征 1847”在三个数据切片中都保持概念一致；“层 24 / 特征 907”只在代码语料上稳定。建议下一轮补做跨域对照。</article></div></main>' +
      '<div class="composer" data-od-id="' + platform + '-chat-composer"><textarea data-composer aria-label="继续提问" placeholder="继续提问…"></textarea><button class="send" data-send aria-label="发送">' + icon('send') + '</button></div>';
  }
  function note() {
    var action = '<button class="icon-btn" data-save aria-label="保存笔记"><span class="save-state">保存</span></button>';
    return appbar('编辑笔记', '刚刚自动保存', action) +
      '<main class="content" data-od-id="' + platform + '-note-content"><input class="editor-title" aria-label="笔记标题" value="Sparse autoencoders 的层级语义提取" /><div class="editor-meta"><span class="chip">research</span><span class="chip">llm-agents</span><span class="chip sync">已索引</span></div><textarea class="editor-body" aria-label="笔记正文">三档可解释性\n\n浅层特征通常对应词法、格式与局部模式；中层特征开始表达跨 token 的组合概念；深层特征可能映射到任务策略与完整回路。\n\n我的实验\n\n层 12 的特征 1847 在论文、代码和访谈三个数据切片中保持稳定。层 24 的特征 907 只在代码语料中有一致语义，暂时不能把它视为通用特征。\n\n下一步：补充跨域激活对照，并记录每个特征的反例。</textarea></main>';
  }
  function graph() {
    return appbar('知识图谱', '触控节点以展开关联', '<button class="icon-btn" aria-label="图谱筛选" data-notify="筛选器已打开">' + icon('search') + '</button>') +
      '<main class="content" data-od-id="' + platform + '-graph-content"><div class="graph-wrap"><div class="graph-grid"></div>' +
      '<span class="edge" style="left:48%;top:48%;width:150px;transform:rotate(-30deg)"></span><span class="edge" style="left:30%;top:39%;width:120px;transform:rotate(24deg)"></span><span class="edge" style="left:49%;top:52%;width:135px;transform:rotate(58deg)"></span><span class="edge" style="left:25%;top:65%;width:120px;transform:rotate(-32deg)"></span>' +
      '<button class="node core" style="left:39%;top:37%" data-notify="已选中：稀疏自编码器">稀疏<br>自编码器</button><button class="node ai" style="left:69%;top:22%" data-notify="已选中：特征解释">特征解释</button><button class="node" style="left:11%;top:23%" data-notify="已选中：机制解释性">机制<br>解释性</button><button class="node" style="left:68%;top:66%" data-notify="已选中：跨层分析">跨层分析</button><button class="node" style="left:14%;top:70%" data-notify="已选中：RAG 实验">RAG 实验</button></div></main>' +
      '<aside class="graph-sheet" data-od-id="' + platform + '-graph-selection"><b>Sparse autoencoders 的层级语义提取</b><p>研究笔记 · 4 个直接关联 · 12 个二级关联</p></aside>';
  }
  function settings() {
    return appbar('设置', 'Atlas 移动端') +
      '<main class="content" data-od-id="' + platform + '-settings-content">' +
      group('同步与索引', setting('知识库同步', '<button class="switch on" role="switch" aria-checked="true" aria-label="知识库同步"></button>') + setting('离线笔记', '<span class="chip sync">328 条</span>') + setting('索引状态', '<small class="sync">已完成</small>')) +
      group('AI', setting('回答模型', '<small>Claude Sonnet</small>') + setting('仅使用我的知识', '<button class="switch on" role="switch" aria-checked="true" aria-label="仅使用我的知识"></button>') + setting('显示引用来源', '<button class="switch on" role="switch" aria-checked="true" aria-label="显示引用来源"></button>')) +
      group('外观与隐私', setting('跟随系统深色模式', '<button class="switch" role="switch" aria-checked="false" aria-label="跟随系统深色模式"></button>') + setting('Face ID / 生物识别锁定', '<button class="switch on" role="switch" aria-checked="true" aria-label="生物识别锁定"></button>') + setting('清除本地缓存', '<small>42 MB</small>')) + '</main>';
  }
  function setting(label, value) {
    settingIndex += 1;
    return '<div class="setting-row" data-od-id="' + platform + '-setting-row-' + settingIndex + '"><span>' + label + '</span>' + value + '</div>';
  }
  function group(label, content) { return '<section class="setting-group"><p class="setting-label">' + label + '</p><div class="card">' + content + '</div></section>'; }
  var renderers = { home: home, chat: chat, note: note, graph: graph, settings: settings };
  document.title = 'Atlas — ' + (isIOS ? 'iOS' : 'Android') + ' ' + names[screen];
  body.innerHTML = '<div class="preview"><div class="phone ' + platform + '" data-od-id="' + platform + '-' + screen + '-screen">' + status() + renderers[screen]() + nav() + '<div class="snack" role="status"></div></div></div>';
})();
