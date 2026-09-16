/**
 * config.js — Reads and writes config.json through /api/config.
 *
 * Simple fields are declared in FIELDS and bound to the DOM by a data-bind
 * attribute, so a control can appear on several pages without any syncing
 * code. Everything with its own state (background picker, pets, reactions)
 * lives in its own module and only contributes to the save payload.
 */
const Config = (() => {
  // name → [type, default, formatter]
  const FIELDS = {
    resolution:          ['string', 'auto'],
    targetFps:           ['int', 30],
    orientation:         ['int', 0],
    cameraFacing:        ['string', 'back'],
    mirror:              ['bool', false],
    vcamEnabled:         ['bool', true],
    zoom:                ['float', 1.0,  v => v.toFixed(1) + '×'],
    brightness:          ['float', 0.0,  v => v.toFixed(2)],
    contrast:            ['float', 1.0,  v => v.toFixed(2)],
    saturation:          ['float', 1.0,  v => v.toFixed(2)],
    sharpness:           ['float', 0.0,  v => v.toFixed(1)],
    blur:                ['int', 0,      v => v === 0 ? 'Off' : v + ' px'],
    segmentationEngine:  ['string', 'mediapipe'],
    rvmDownsampleRatio:  ['ratio', 0.25, v => v.toFixed(2) + '×'],
    faceTouchupEnabled:  ['bool', false],
    faceTouchupStrength: ['int', 35,     v => v + '%'],
    onekoEnabled:        ['bool', false],
    onekoSize:           ['float', 2.0,  v => v.toFixed(1) + '×'],
  };

  // Fields that restart the pipeline — worth a longer debounce
  const RESTARTS = ['resolution', 'targetFps'];

  let _loading = false;
  let _saveTimer = null;
  let _bgMode = 'none';
  let _bgImage = '';
  let _bgLoaded = false;

  const nodes = (name) => document.querySelectorAll(`[data-bind="${name}"]`);

  function parse(type, raw) {
    if (type === 'bool') return !!raw;
    if (type === 'int') return parseInt(raw, 10) || 0;
    if (type === 'float') return parseFloat(raw) || 0;
    if (type === 'ratio') return parseFloat((parseInt(raw, 10) / 100).toFixed(2));
    return String(raw);
  }

  function readField(name) {
    const [type, fallback] = FIELDS[name];
    const el = nodes(name)[0];
    if (!el) return fallback;
    return parse(type, el.type === 'checkbox' ? el.checked : el.value);
  }

  function writeField(name, value) {
    const [type, , format] = FIELDS[name];
    nodes(name).forEach(el => {
      if (el.type === 'checkbox') el.checked = !!value;
      else el.value = type === 'ratio' ? Math.round(value * 100) : value;
    });
    const label = format ? format(value) : String(value);
    document.querySelectorAll(`[data-out="${name}"]`).forEach(el => { el.textContent = label; });
  }

  function refreshLabels() {
    Object.keys(FIELDS).forEach(name => writeField(name, readField(name)));
  }

  // ── Load ─────────────────────────────────────────────────────────────────

  async function load() {
    _loading = true;
    try {
      const res = await fetch('/api/config');
      if (!res.ok) throw new Error(res.statusText);
      const cfg = await res.json();

      Object.keys(FIELDS).forEach(name => {
        writeField(name, cfg[name] !== undefined ? cfg[name] : FIELDS[name][1]);
      });

      _bgMode = cfg.bgMode || 'none';
      _bgImage = cfg.bgImage || '';
      applyBgUI();
      applyConditionalUI();

      Pets.applyFromConfig(cfg);
      Reactions.applyFromConfig(cfg);
      Stream.setResolution(cfg.resolution);
      App.markNav();
      console.log('[Config] loaded');
    } catch (err) {
      Toast.show(`Could not load settings: ${err.message}`, 'error');
    } finally {
      _loading = false;
    }
  }

  // ── Save ─────────────────────────────────────────────────────────────────

  function payload() {
    const out = {};
    Object.keys(FIELDS).forEach(name => { out[name] = readField(name); });
    out.bgMode = _bgMode;
    out.bgImage = _bgImage;
    Object.assign(out, Pets.getConfig());
    out.reactions = Reactions.getConfig();
    return out;
  }

  async function update() {
    if (_loading) return;
    try {
      const res = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload()),
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(json.error || res.statusText);
      if (json.restarted) {
        Toast.show('Restarting pipeline — resolution or FPS changed…', 'info');
        setTimeout(() => Stream.reloadFeed(), 2500);
      }
      App.markNav();
    } catch (err) {
      Toast.show(`Save failed: ${err.message}`, 'error');
    }
  }

  function save(delay = 250) {
    if (_loading) return;
    clearTimeout(_saveTimer);
    _saveTimer = setTimeout(update, delay);
  }

  /** Called by the delegated listeners in app.js whenever a bound control moves. */
  function onFieldInput(name) {
    const value = readField(name);
    writeField(name, value);
    applyConditionalUI();
    if (name === 'orientation') Stream.setOrientation(value);
    if (name === 'resolution') Stream.setResolution(value);
    save(RESTARTS.includes(name) ? 700 : 250);
  }

  /** Show only the controls that matter for the current mode. */
  function applyConditionalUI() {
    const show = (id, on) => {
      const el = document.getElementById(id);
      if (el) el.style.display = on ? '' : 'none';
    };
    const rvm = readField('segmentationEngine') === 'rvm';
    show('rvm-field', rvm);
    show('rvm-note', rvm);
    show('touchup-field', readField('faceTouchupEnabled'));
    show('bg-blur-field', _bgMode === 'blur');
    show('bg-replace-field', _bgMode === 'replace');
  }

  // ── Resets ───────────────────────────────────────────────────────────────

  function resetSingle(name) {
    writeField(name, FIELDS[name][1]);
    update();
  }

  function resetProcessing() {
    ['brightness', 'contrast', 'saturation', 'sharpness'].forEach(n => writeField(n, FIELDS[n][1]));
    update();
    Toast.show('Image adjustments reset.', 'success');
  }

  // ── Virtual background ───────────────────────────────────────────────────

  function applyBgUI() {
    document.querySelectorAll('#bg-mode-seg button').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.mode === _bgMode);
    });
    applyConditionalUI();
    if (_bgMode === 'replace' && !_bgLoaded) loadBackgrounds();
    else syncBgSelection();
  }

  function setBgMode(mode) {
    _bgMode = mode;
    applyBgUI();
    update();
  }

  async function loadBackgrounds() {
    const grid = document.getElementById('bg-grid');
    if (!grid) return;
    _bgLoaded = true;
    try {
      const res = await fetch('/api/backgrounds');
      const data = await res.json();
      const items = data.backgrounds || [];
      if (!items.length) {
        grid.innerHTML = '<div class="empty">No images yet — upload one, or drop files into the <code>backgrounds</code> folder of your data directory.</div>';
        return;
      }
      grid.innerHTML = items.map(item => `
        <div class="thumb${item.filename === _bgImage ? ' selected' : ''}" data-filename="${item.filename}">
          <img src="${item.url}" alt="" loading="lazy">
          <span>${item.filename.replace(/\.[^.]+$/, '')}</span>
        </div>`).join('');
      grid.querySelectorAll('.thumb').forEach(t => {
        t.addEventListener('click', () => {
          _bgImage = t.dataset.filename;
          syncBgSelection();
          update();
        });
      });
    } catch (err) {
      grid.innerHTML = `<div class="empty">Could not load backgrounds: ${err.message}</div>`;
    }
  }

  function syncBgSelection() {
    document.querySelectorAll('#bg-grid .thumb').forEach(t => {
      t.classList.toggle('selected', t.dataset.filename === _bgImage);
    });
  }

  async function uploadBackground(event) {
    const file = event.target.files[0];
    event.target.value = '';
    if (!file) return;
    Toast.show('Uploading background…', 'info');
    try {
      const res = await fetch(`/api/upload_background?filename=${encodeURIComponent(file.name)}`, {
        method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: file,
      });
      const data = await res.json();
      if (!data.success) throw new Error(data.error || res.statusText);
      _bgImage = data.filename;
      _bgLoaded = false;
      await loadBackgrounds();
      update();
      Toast.show('Background added.', 'success');
    } catch (err) {
      Toast.show(`Upload failed: ${err.message}`, 'error');
    }
  }

  return {
    load, update, save, onFieldInput, refreshLabels, applyConditionalUI,
    resetSingle, resetProcessing,
    setBgMode, loadBackgrounds, uploadBackground,
    get bgMode() { return _bgMode; },
  };
})();
