/**
 * connection.js — USB or Wi-Fi, and finding the phone on the network.
 */
const Connection = (() => {
  const el = (id) => document.getElementById(id);

  function setHostField(host) {
    const input = el('wifi-host');
    if (input && document.activeElement !== input) input.value = host || '';
  }

  function applyFromConfig(cfg) {
    setHostField(cfg.wifiHost);
  }

  function applyStatus(data) {
    if (data.wifiHost !== undefined) setHostField(data.wifiHost);
    const via = el('conn-via');
    if (via) via.textContent = data.androidConnected && data.connectedVia ? 'Streaming over ' + data.connectedVia : '';
  }

  async function save(body) {
    const res = await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(res.statusText);
  }

  async function setHost(value) {
    const host = value.trim();
    try {
      await save({ wifiHost: host, wifiPort: 8080 });
      if (host) Toast.show(`Connecting to ${host} over Wi-Fi…`, 'info');
    } catch (err) {
      Toast.show(`Save failed: ${err.message}`, 'error');
    }
  }

  async function find() {
    const btn = el('wifi-find');
    if (btn) btn.disabled = true;
    try {
      const res = await fetch('/api/wifi/discover', { method: 'POST' });
      const data = await res.json();
      const phone = (data.phones || [])[0];
      if (!phone) {
        Toast.show('No phone found. Open Webcam Bridge on the phone and check it is on the same Wi-Fi.', 'error');
        return;
      }
      Config.load();
      Toast.show(`Found ${phone.name} at ${phone.host}`, 'success');
    } catch (err) {
      Toast.show(`Search failed: ${err.message}`, 'error');
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  return { applyFromConfig, applyStatus, setHost, find };
})();
