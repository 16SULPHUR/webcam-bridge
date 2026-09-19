/**
 * setup.js — First-run wizard: renders the checklist from /api/setup and runs
 *            the one-click fixes. Polls only while the page is open, or while
 *            an action (an admin prompt, a download) is still running.
 */
const Setup = (() => {
  const POLL_MS = 2500;
  const ICONS = { ok: '✓', todo: '!', blocked: '·', working: '…', error: '×' };

  const el = (id) => document.getElementById(id);
  let _timer = null;
  let _ready = false;
  let _lastJobError = '';

  function escapeHtml(s) {
    return String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  }

  function stepHtml(step) {
    const parts = [`<div class="step-body"><b>${escapeHtml(step.title)}</b>`,
                   `<span>${escapeHtml(step.detail || '')}</span>`];
    if (step.actionNote && step.state === 'todo') {
      parts.push(`<span class="step-note">${escapeHtml(step.actionNote)}</span>`);
    }
    parts.push('</div>');

    const buttons = [];
    if (step.action && step.state !== 'ok' && step.state !== 'blocked') {
      buttons.push(`<button class="btn sm primary" data-setup-action="${escapeHtml(step.action)}"
                     ${step.state === 'working' ? 'disabled' : ''}>
                     ${escapeHtml(step.state === 'working' ? 'Working…' : step.actionLabel || 'Fix')}</button>`);
    }
    if (step.link && step.state !== 'ok') {
      buttons.push(`<a class="btn sm" href="${escapeHtml(step.link)}" target="_blank" rel="noopener">
                     ${escapeHtml(step.linkLabel || 'Help')}</a>`);
    }

    return `<li class="step ${step.state}">
      <i class="step-mark">${ICONS[step.state] || '·'}</i>
      ${parts.join('')}
      <div class="step-actions">${buttons.join('')}</div>
    </li>`;
  }

  function render(data) {
    const list = el('setup-steps');
    if (!list) return;
    list.innerHTML = data.steps.map(stepHtml).join('');

    const done = data.steps.filter(s => s.state === 'ok').length;
    const summary = el('setup-summary');
    if (summary) {
      summary.textContent = data.ready ? 'All set' : `${done} of ${data.steps.length} done`;
      summary.className = `tag ${data.ready ? 'ok' : 'warn'}`;
    }
    const panel = el('setup-done');
    if (panel) panel.hidden = !data.ready;
    _ready = data.ready;

    // Surface an action failure once, not on every poll.
    const error = data.job && data.job.error;
    if (error && error !== _lastJobError) Toast.show(error, 'error');
    else if (!error && data.job && data.job.message && data.job.message !== _lastJobError) {
      Toast.show(data.job.message, 'success');
    }
    _lastJobError = error || (data.job && data.job.message) || '';

    if (data.job && data.job.running) schedule(1200);
  }

  function schedule(delay = POLL_MS) {
    clearTimeout(_timer);
    _timer = setTimeout(() => refresh(), delay);
  }

  async function refresh(manual = false) {
    clearTimeout(_timer);
    try {
      const res = await fetch('/api/setup');
      render(await res.json());
    } catch (err) {
      if (manual) Toast.show(`Could not check setup: ${err.message}`, 'error');
    }
    if (App.currentPage() === 'setup') schedule();
  }

  async function run(action) {
    try {
      const res = await fetch('/api/setup/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action }),
      });
      const data = await res.json();
      if (!data.success) Toast.show(data.error || 'Could not start', 'error');
      else if (action === 'camera-install') Toast.show('Approve the administrator prompt on this PC…', 'info');
    } catch (err) {
      Toast.show(`Failed: ${err.message}`, 'error');
    }
    refresh();
  }

  /** Leave the wizard and remember not to open on it again. */
  function finish() {
    Config.markSetupComplete();
    App.navigate('live');
  }

  function stop() {
    clearTimeout(_timer);
  }

  function init() {
    document.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-setup-action]');
      if (btn) run(btn.dataset.setupAction);
    });
  }

  return { init, refresh, stop, finish, get ready() { return _ready; } };
})();
