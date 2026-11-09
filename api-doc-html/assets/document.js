(() => {
  'use strict';
  document.documentElement.classList.add('js');
  const views = [...document.querySelectorAll('.view')];
  const menu = document.querySelector('#menu-toggle');
  const search = document.querySelector('#search');
  const method = document.querySelector('#method-filter');
  const mobile = window.matchMedia('(max-width: 760px)');
  const syncMenu = () => {
    document.querySelector('.sidebar').inert = mobile.matches && !document.body.classList.contains('menu-open');
  };
  const closeMenu = () => {
    document.body.classList.remove('menu-open');
    menu.setAttribute('aria-expanded', 'false');
    syncMenu();
  };
  mobile.addEventListener('change', syncMenu);
  function route() {
    const id = location.hash.slice(1) || 'overview';
    const target = document.getElementById(id);
    const view = target?.closest('.view') || document.querySelector('#overview');
    views.forEach(item => item.classList.toggle('active', item === view));
    document.querySelectorAll('.sidebar a').forEach(link => {
      const active = link.hash === '#' + view.id;
      link.classList.toggle('active', active);
      if (active) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    });
    document.querySelector('#current-title').textContent = view.dataset.title;
    closeMenu();
    if (target && target !== view) target.scrollIntoView();
    else window.scrollTo(0, 0);
  }
  window.addEventListener('hashchange', route);
  document.querySelectorAll('.sidebar a').forEach(link => link.addEventListener('click', () => {
    // Clicking the current endpoint emits no hashchange, but should still close the drawer.
    closeMenu();
    if (link.hash === location.hash) route();
  }));
  document.querySelectorAll('.tabs').forEach(tablist => {
    const tabs = [...tablist.querySelectorAll('[role=tab]')];
    function select(tab, focus = false) {
      tabs.forEach(item => {
        const active = item === tab;
        item.setAttribute('aria-selected', String(active));
        item.tabIndex = active ? 0 : -1;
        document.getElementById(item.getAttribute('aria-controls')).classList.toggle('active', active);
      });
      if (focus) tab.focus();
    }
    tabs.forEach(tab => tab.addEventListener('click', () => select(tab)));
    tablist.addEventListener('keydown', event => {
      const current = tabs.indexOf(document.activeElement);
      let next;
      if (event.key === 'ArrowRight') next = (current + 1) % tabs.length;
      if (event.key === 'ArrowLeft') next = (current - 1 + tabs.length) % tabs.length;
      if (event.key === 'Home') next = 0;
      if (event.key === 'End') next = tabs.length - 1;
      if (next !== undefined) { event.preventDefault(); select(tabs[next], true); }
    });
    select(tabs[0]);
  });
  document.querySelectorAll('.snippet-select').forEach(select => {
    const update = () => select.closest('.code-rail').querySelectorAll('.snippet').forEach(
      panel => panel.classList.toggle('active', panel.id === select.value));
    select.addEventListener('change', update);
    update();
  });
  // Tokenize into text nodes, never interpret contract content as executable HTML.
  document.querySelectorAll('pre code').forEach(code => {
    const source = code.textContent;
    const tokens = /("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\/\/[^\n]*|\b(?:true|false|null|\d+(?:\.\d+)?)\b)/g;
    const fragment = document.createDocumentFragment();
    let start = 0;
    for (const match of source.matchAll(tokens)) {
      fragment.append(document.createTextNode(source.slice(start, match.index)));
      const span = document.createElement('span');
      const token = match[0];
      span.className = 'token-' + (token.startsWith('//') ? 'comment' :
        /^["']/.test(token) ? (/^\s*:/.test(source.slice(match.index + token.length)) ? 'key' : 'string') : 'number');
      span.textContent = token;
      fragment.append(span);
      start = match.index + token.length;
    }
    fragment.append(document.createTextNode(source.slice(start)));
    code.replaceChildren(fragment);
  });
  let toastTimer;
  function notify(text) {
    const toast = document.querySelector('.toast');
    toast.textContent = text; toast.hidden = false;
    clearTimeout(toastTimer); toastTimer = setTimeout(() => toast.hidden = true, 2600);
  }
  async function copy(text) {
    try { await navigator.clipboard.writeText(text); return true; }
    catch (_) {
      const field = document.createElement('textarea');
      field.value = text; field.style.cssText = 'position:fixed;left:-9999px';
      document.body.append(field); field.select();
      let result = false;
      try { result = document.execCommand('copy'); } catch (_) { /* report failure below */ }
      field.remove(); return result;
    }
  }
  const handoffData = JSON.parse(document.querySelector('#agent-data').textContent);
  const agentScope = document.querySelector('#agent-scope');
  const agentTask = document.querySelector('#agent-task');
  const agentPrompt = document.querySelector('#agent-prompt');
  let agentPacket;
  function updateHandoff() {
    agentPacket = ApiHandoff.createPacket(handoffData, agentScope.value, agentTask.value);
    agentPrompt.value = ApiHandoff.markdown(agentPacket);
    const count = agentPacket.modules.reduce((sum, module) => sum + module.operations.length, 0);
    document.querySelector('#agent-summary').textContent = `${count} 个接口 · ${agentPacket.pending.length} 项待确认 · 含契约与引用模型`;
  }
  agentScope.addEventListener('change', updateHandoff);
  agentTask.addEventListener('input', updateHandoff);
  document.querySelectorAll('[data-agent-scope]').forEach(link => link.addEventListener('click', () => {
    agentScope.value = link.dataset.agentScope;
    updateHandoff();
  }));
  function downloadPacket(format) {
    const isJson = format === 'json';
    const text = isJson ? JSON.stringify(agentPacket, null, 2) : agentPrompt.value;
    const blob = new Blob([text], {type: isJson ? 'application/json;charset=utf-8' : 'text/markdown;charset=utf-8'});
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url; link.download = `frontend-agent-handoff.${format}`;
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  document.querySelector('#agent-download-md').addEventListener('click', () => downloadPacket('md'));
  document.querySelector('#agent-download-json').addEventListener('click', () => downloadPacket('json'));
  updateHandoff();
  document.querySelectorAll('[data-copy]').forEach(button => button.addEventListener('click', async () => {
    const target = document.getElementById(button.dataset.copy);
    const text = target instanceof HTMLTextAreaElement ? target.value : target.textContent;
    const previous = document.activeElement;
    notify(await copy(text) ? '已复制到剪贴板' : '复制失败，请选中代码手动复制');
    previous?.focus({preventScroll: true});
  }));
  function filter() {
    const terms = search.value.toLowerCase().trim().split(/\s+/).filter(Boolean);
    let count = 0;
    document.querySelectorAll('.nav-item').forEach(link => {
      const visible = (!method.value || link.dataset.method === method.value) && terms.every(t => link.dataset.search.includes(t));
      link.hidden = !visible;
      if (visible) count++;
    });
    document.querySelectorAll('.nav-group').forEach(group => group.hidden = !group.querySelector('.nav-item:not([hidden])'));
    document.querySelector('#no-results').hidden = count > 0;
  }
  search.addEventListener('input', filter); method.addEventListener('change', filter);
  document.addEventListener('keydown', event => {
    if (event.key === '/' && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) {
      event.preventDefault(); document.body.classList.add('menu-open');
      menu.setAttribute('aria-expanded', 'true'); syncMenu(); search.focus();
    }
    if (event.key === 'Escape') { closeMenu(); search.blur(); }
  });
  menu.addEventListener('click', () => {
    const open = document.body.classList.toggle('menu-open');
    menu.setAttribute('aria-expanded', String(open));
    syncMenu();
  });
  document.addEventListener('click', event => {
    if (!event.target.closest('.sidebar, #menu-toggle')) closeMenu();
  });
  document.querySelector('#print-button').addEventListener('click', () => window.print());
  route();
})();
