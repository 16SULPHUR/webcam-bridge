/**
 * app.js — Shell: component loading, page routing, the SSE connection,
 *          the log view, and the delegated listeners for bound controls.
 */

const Toast = {
  show(message, type = 'info') {
    let box = document.getElementById('toast-container');
    if (!box) {
      box = document.createElement('div');
      box.id = 'toast-container';
      document.body.appendChild(box);
    }
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    box.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add('show'));
    setTimeout(() => {
      toast.classList.remove('show');
      setTimeout(() => toast.remove(), 300);
    }, 3200);
  },
};

const App = (() => {
  const PAGES = ['live', 'camera', 'image', 'background', 'effects', 'reactions', 'logs'];
  const TITLES = {
    live: 'Live', camera: 'Camera', image: 'Image', background: 'Background',
    effects: 'Effects', reactions: 'Reactions', logs: 'Logs',
  };
  const MAX_LOGS = 600;

  let _logs = [];
  let _logPaused = false;
  let _sse = null;
  let _page = 'live';

  const el = (id) => document.getElementById(id);

  // ── Components ───────────────────────────────────────────────────────────

  async function loadComponents() {
    await Promise.all(Array.from(document.querySelectorAll('[data-component]')).map(async (host) => {
      const name = host.getAttribute('data-component');
      try {
        const res = await fetch(`components/${name}.html`);
        if (!res.ok) throw new Error(res.statusText);
        host.innerHTML = await res.text();
      } catch (err) {
        host.innerHTML = `<div class="component-error">Could not load “${name}”: ${err.message}</div>`;
      }
    }));
  }

  // ── Routing ──────────────────────────────────────────────────────────────

  function navigate(page) {
    if (!PAGES.includes(page)) page = 'live';
    _page = page;
    PAGES.forEach(p => el(`page-${p}`)?.classList.toggle('active', p === page));
    document.querySelectorAll('.nav-item').forEach(b =>
      b.classList.toggle('active', b.dataset.page === page));
    const title = el('topbar-title');
    if (title) title.textContent = TITLES[page];
    if (location.hash.slice(1) !== page) history.replaceState(null, '', `#${page}`);
    if (page === 'background') Config.loadBackgrounds();
    if (page === 'logs') renderLogs();
  }

  /** Dots next to nav entries showing which features are currently on. */
  function markNav() {
    const on = {
      background: Config.bgMode !== 'none',
      effects: document.querySelector('[data-bind="faceTouchupEnabled"]')?.checked
               || document.querySelector('[data-bind="onekoEnabled"]')?.checked,
      reactions: el('rx-master')?.checked,
    };
    document.querySelectorAll('.nav-item').forEach(b => {
      b.classList.toggle('on', !!on[b.dataset.page]);
    });
  }

  // ── Logs ─────────────────────────────────────────────────────────────────

  function pushLog(source, message) {
    const src = source === 'node' ? 'system' : source;
    const clean = String(message).replace(/^\[(FFmpeg-VCam|python|node)\]\s*/i, '').trim();
    if (!clean || /Processed frame #|frame=\s*\d+/.test(clean)) return;
    const low = clean.toLowerCase();
    const level = /error|failed|traceback/.test(low) ? 'error' : (/warn/.test(low) ? 'warn' : '');
    const last = _logs[_logs.length - 1];
    if (last && last.message === clean && last.source === src) {
      last.count += 1;
    } else {
      _logs.push({ time: new Date().toLocaleTimeString(), source: src, message: clean, level, count: 1 });
      if (_logs.length > MAX_LOGS) _logs.shift();
    }
    if (_page === 'logs') renderLogs();
  }

  function renderLogs() {
    const box = el('logbox');
    if (!box || _logPaused) return;
    const filter = (el('log-filter')?.value || '').toLowerCase();
    const rows = _logs.filter(l => !filter || l.message.toLowerCase().includes(filter)
                                             || l.source.includes(filter));
    const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 60;
    box.innerHTML = rows.map(l => `
      <div class="logline ${l.source} ${l.level}">
        <time>${l.time}</time><b>${l.source}</b><span>${escapeHtml(l.message)}${l.count > 1 ? `  ×${l.count}` : ''}</span>
      </div>`).join('') || '<div class="empty">Nothing logged yet.</div>';
    if (atBottom) box.scrollTop = box.scrollHeight;
  }

  function escapeHtml(s) {
    return s.replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
  }

  function toggleLogPause() {
    _logPaused = !_logPaused;
    const btn = el('log-pause');
    if (btn) btn.textContent = _logPaused ? 'Resume' : 'Pause';
    if (!_logPaused) renderLogs();
  }

  function clearLogs() {
    _logs = [];
    renderLogs();
  }

  // ── SSE ──────────────────────────────────────────────────────────────────

  function connect() {
    if (_sse) _sse.close();
    _sse = new EventSource('/logs');
    _sse.onopen = () => Stream.setStatus('connecting', 'Connecting…');
    _sse.onerror = () => Stream.setStatus('error', 'Bridge offline');
    _sse.onmessage = (event) => {
      let data;
      try { data = JSON.parse(event.data); } catch (_) { return; }
      if (data.type === 'log') pushLog(data.source, data.message);
      else if (data.type === 'status') {
        Stream.handleStatus(data);
        Reactions.applyStats(data.reactions);
      }
    };
  }

  // ── Init ─────────────────────────────────────────────────────────────────

  function init() {
    document.querySelectorAll('.nav-item').forEach(btn =>
      btn.addEventListener('click', () => navigate(btn.dataset.page)));
    window.addEventListener('hashchange', () => navigate(location.hash.slice(1)));

    // one listener for every control bound to a config field
    const onBound = (e) => {
      const name = e.target.dataset && e.target.dataset.bind;
      if (name) Config.onFieldInput(name);
    };
    document.addEventListener('input', onBound);
    document.addEventListener('change', onBound);

    document.addEventListener('keydown', (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
      if (e.key === 'f') Stream.toggleFullscreen();
      if (e.key === 'r') Stream.toggleRecording();
      if (e.key === 'Escape') {
        Pets.closeBrowser();
        Reactions.closePicker();
      }
      const index = parseInt(e.key, 10);
      if (index >= 1 && index <= PAGES.length) navigate(PAGES[index - 1]);
    });

    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible' && (!_sse || _sse.readyState === EventSource.CLOSED)) connect();
    });

    navigate(location.hash.slice(1) || 'live');
    Reactions.init();
    Config.load();
    Vcam.refresh();
    connect();
  }

  document.addEventListener('DOMContentLoaded', async () => {
    await loadComponents();
    init();
  });

  return { navigate, markNav, renderLogs, clearLogs, toggleLogPause, pushLog };
})();
