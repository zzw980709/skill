(() => {
  'use strict';

  const views = [...document.querySelectorAll('.view')];
  const menuToggle = document.querySelector('#menu-toggle');
  const title = document.querySelector('#current-title');
  const search = document.querySelector('#nav-search');
  const method = document.querySelector('#method-filter');
  const changedOnly = document.querySelector('#changed-only');
  const noResults = document.querySelector('#no-results');
  const toastEl = document.querySelector('#toast');

  function closeMenu() {
    document.body.classList.remove('menu-open');
    if (menuToggle) menuToggle.setAttribute('aria-expanded', 'false');
  }

  function route() {
    const id = location.hash.slice(1) || 'overview';
    const target = document.getElementById(id);
    const view = target?.closest('.view') || document.querySelector('#overview');
    if (!view) return;
    views.forEach(item => item.classList.toggle('active', item === view));
    document.querySelectorAll('.sidebar a').forEach(link => {
      const active = link.hash === '#' + view.id;
      link.classList.toggle('active', active);
      if (active) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    });
    if (title) title.textContent = view.dataset.title || '开始对接';
    closeMenu();
    window.scrollTo(0, 0);
  }

  window.addEventListener('hashchange', route);
  document.querySelectorAll('.sidebar a').forEach(link => link.addEventListener('click', closeMenu));
  if (menuToggle) {
    menuToggle.addEventListener('click', () => {
      const open = document.body.classList.toggle('menu-open');
      menuToggle.setAttribute('aria-expanded', String(open));
    });
  }

  // Tabs
  document.querySelectorAll('.tabs').forEach(tablist => {
    const tabs = [...tablist.querySelectorAll('[role="tab"]')];
    if (!tabs.length) return;
    function select(tab) {
      tabs.forEach(item => {
        const active = item === tab;
        item.setAttribute('aria-selected', String(active));
        item.tabIndex = active ? 0 : -1;
        const panel = document.getElementById(item.getAttribute('aria-controls'));
        if (panel) panel.classList.toggle('active', active);
      });
    }
    tabs.forEach(tab => tab.addEventListener('click', () => select(tab)));
    tablist.addEventListener('keydown', event => {
      const current = tabs.indexOf(document.activeElement);
      let next;
      if (event.key === 'ArrowRight') next = (current + 1) % tabs.length;
      if (event.key === 'ArrowLeft') next = (current - 1 + tabs.length) % tabs.length;
      if (event.key === 'Home') next = 0;
      if (event.key === 'End') next = tabs.length - 1;
      if (next !== undefined) { event.preventDefault(); select(tabs[next]); tabs[next].focus(); }
    });
    select(tabs[0]);
  });

  // Sidebar filters
  function filterNav() {
    if (!search) return;
    const terms = search.value.toLowerCase().trim().split(/\s+/).filter(Boolean);
    let count = 0;
    document.querySelectorAll('.nav-item').forEach(link => {
      const visible = (!method?.value || link.dataset.method === method.value)
        && (!changedOnly?.checked || link.dataset.changed)
        && terms.every(term => (link.dataset.search || '').includes(term));
      link.hidden = !visible;
      if (visible) count++;
    });
    document.querySelectorAll('.nav-group').forEach(group => {
      group.hidden = !group.querySelector('.nav-item:not([hidden])');
    });
    if (noResults) noResults.hidden = count > 0;
  }
  search?.addEventListener('input', filterNav);
  method?.addEventListener('change', filterNav);
  changedOnly?.addEventListener('change', filterNav);
  filterNav();

  // Changes page filters
  let changeFilter = 'all';
  const breakingOnly = document.querySelector('#breaking-only');
  document.querySelectorAll('[data-change-filter]').forEach(button => {
    button.addEventListener('click', () => {
      changeFilter = button.dataset.changeFilter;
      document.querySelectorAll('[data-change-filter]').forEach(item => item.classList.toggle('active', item === button));
      filterChanges();
    });
  });
  function filterChanges() {
    document.querySelectorAll('.change-detail').forEach(card => {
      const statusOk = changeFilter === 'all' || card.dataset.status === changeFilter;
      const breakingOk = !breakingOnly?.checked || card.dataset.breaking === 'true';
      card.hidden = !(statusOk && breakingOk);
    });
    document.querySelectorAll('.change-group').forEach(group => {
      group.hidden = !group.querySelector('.change-detail:not([hidden])');
    });
  }
  breakingOnly?.addEventListener('change', filterChanges);
  filterChanges();

  // Copy
  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (_) {
      const field = document.createElement('textarea');
      field.value = text;
      field.style.cssText = 'position:fixed;left:-9999px';
      document.body.append(field);
      field.select();
      let ok = false;
      try { ok = document.execCommand('copy'); } catch (_) { ok = false; }
      field.remove();
      return ok;
    }
  }
  let toastTimer;
  function toast(text) {
    if (!toastEl) return;
    toastEl.textContent = text;
    toastEl.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toastEl.classList.remove('show'), 2200);
  }
  document.querySelectorAll('[data-copy]').forEach(button => {
    button.addEventListener('click', async () => {
      const target = document.getElementById(button.dataset.copy);
      if (!target) return;
      const text = target instanceof HTMLTextAreaElement ? target.value : target.textContent;
      toast(await copyText(text) ? '已复制到剪贴板' : '复制失败，请手动选择');
    });
  });

  // Agent handoff
  const agentDataEl = document.querySelector('#agent-data');
  const agentScope = document.querySelector('#agent-scope');
  const agentTask = document.querySelector('#agent-task');
  const agentPacketEl = document.querySelector('#agent-packet');
  const agentSummary = document.querySelector('#agent-summary');
  let agentPacket;
  if (agentDataEl && agentScope && agentTask && agentPacketEl && window.ApiHandoff) {
    const handoffData = JSON.parse(agentDataEl.textContent);
    function updateHandoff() {
      agentPacket = ApiHandoff.createPacket(handoffData, agentScope.value, agentTask.value);
      agentPacketEl.textContent = ApiHandoff.markdown(agentPacket);
      const count = agentPacket.modules.reduce((sum, module) => sum + module.operations.length, 0);
      const changeCount = agentPacket.changes.length;
      if (agentSummary) {
        agentSummary.textContent = `${count} 个接口 · ${changeCount} 项接口变更 · ${agentPacket.pending.length} 项待确认 · 含最新契约`;
      }
    }
    agentScope.addEventListener('change', updateHandoff);
    agentTask.addEventListener('input', updateHandoff);
    document.querySelectorAll('[data-agent-scope]').forEach(link => link.addEventListener('click', () => {
      agentScope.value = link.dataset.agentScope;
      updateHandoff();
    }));
    function downloadPacket(format) {
      const isJson = format === 'json';
      const text = isJson ? JSON.stringify(agentPacket, null, 2) : agentPacketEl.textContent;
      const blob = new Blob([text], {type: isJson ? 'application/json;charset=utf-8' : 'text/markdown;charset=utf-8'});
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `frontend-agent-handoff.${format}`;
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
    document.querySelector('#agent-download-md')?.addEventListener('click', () => downloadPacket('md'));
    document.querySelector('#agent-download-json')?.addEventListener('click', () => downloadPacket('json'));
    updateHandoff();
  }

  // Mobile search and print
  document.addEventListener('keydown', event => {
    if (event.key === '/' && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName) && search) {
      event.preventDefault();
      document.body.classList.add('menu-open');
      menuToggle?.setAttribute('aria-expanded', 'true');
      search.focus();
    }
    if (event.key === 'Escape') { closeMenu(); search?.blur(); }
  });
  document.addEventListener('click', event => {
    if (!event.target.closest('#sidebar, #menu-toggle')) closeMenu();
  });
  document.querySelector('#print-button')?.addEventListener('click', () => window.print());

  route();
})();
