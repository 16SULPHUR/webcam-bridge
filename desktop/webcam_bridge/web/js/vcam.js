/**
 * vcam.js — Virtual camera status card: which backend is active and the
 *           install / uninstall button for the built-in camera.
 */
const Vcam = (() => {
  const el = (id) => document.getElementById(id);
  let _busy = false;

  function render(info) {
    const status = el('vcam-status');
    const btn = el('vcam-action');
    if (!status || !btn) return;

    if (!info.supported) {
      status.textContent = 'Built-in camera is Windows-only — using OBS / v4l2loopback.';
      btn.hidden = true;
      return;
    }
    const using = info.backend === 'builtin' ? `“${info.name}”` : 'OBS Virtual Camera';
    if (info.installed) {
      status.innerHTML = `<b>“${info.name}”</b> camera is installed. Output: ${using}.`;
      btn.textContent = 'Uninstall camera';
      btn.dataset.action = 'uninstall';
    } else if (info.available) {
      status.innerHTML = `Install the <b>“${info.name}”</b> camera to stop needing OBS. Output: ${using}.`;
      btn.textContent = 'Install camera';
      btn.dataset.action = 'install';
    } else {
      status.innerHTML = 'Camera files missing — run <code>webcam-bridge fetch vcam</code>.';
      btn.hidden = true;
      return;
    }
    btn.hidden = false;
  }

  async function refresh() {
    try {
      const res = await fetch('/api/vcam');
      render(await res.json());
    } catch (err) {
      console.error('[Vcam] status failed:', err.message);
    }
  }

  async function toggle() {
    const btn = el('vcam-action');
    if (_busy || !btn) return;
    _busy = true;
    btn.disabled = true;
    Toast.show('Approve the administrator prompt on this PC…', 'info');
    try {
      const res = await fetch(`/api/vcam/${btn.dataset.action}`, { method: 'POST' });
      const data = await res.json();
      Toast.show(data.message || data.error, data.success ? 'success' : 'error');
    } catch (err) {
      Toast.show(`Failed: ${err.message}`, 'error');
    } finally {
      _busy = false;
      btn.disabled = false;
      refresh();
    }
  }

  return { refresh, toggle };
})();
