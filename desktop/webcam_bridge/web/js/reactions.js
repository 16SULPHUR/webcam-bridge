/**
 * reactions.js — Reaction overlay feature module.
 *
 * Owns the whole feature config (config.json → "reactions"): master switch,
 * tracking overlay, detection tuning and the trigger → artwork mappings, all
 * surfaced on the Reactions page. Config.update() picks the object up via
 * Reactions.getConfig(), so saving follows the normal dashboard path.
 */
const Reactions = (() => {
  const DEFAULTS = {
    enabled: false,
    detectionFps: 12,
    sensitivity: 1.0,
    holdFrames: 2,
    cooldownMs: 1800,
    maxConcurrent: 4,
    globalScale: 1.0,
    showLabel: false,
    showTracking: false,
    mappings: [],
  };

  const KIND_BADGE = {
    hand:  { label: '✋ Hand', cls: '' },
    hands: { label: '🙌 Two hands', cls: 'hands' },
    face:  { label: '😊 Face', cls: 'face' },
  };

  let _catalog = { triggers: [], animations: [], placements: [], defaults: [], images: [], bundledEmoji: [], emojiRenderer: {} };
  let _cfg = Object.assign({}, DEFAULTS, { mappings: [] });
  let _saveTimer = null;
  let _pickerIndex = null;
  let _catalogLoaded = false;

  function el(id) { return document.getElementById(id); }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
  function uid() { return 'rx_' + Math.random().toString(36).slice(2, 9); }
  function clamp(v, lo, hi) { return Math.min(hi, Math.max(lo, v)); }

  function triggerDef(id) { return _catalog.triggers.find(t => t.id === id); }
  function animDef(id) { return _catalog.animations.find(a => a.id === id); }

  // ── Catalog ──────────────────────────────────────────────────────────────

  async function loadCatalog() {
    if (_catalogLoaded) return;
    try {
      const res = await fetch('/api/reactions/catalog');
      if (!res.ok) throw new Error(res.statusText);
      _catalog = await res.json();
      _catalogLoaded = true;
      renderPicker();
      renderNote();
      renderList();
    } catch (err) {
      console.error('[Reactions] catalog load failed:', err.message);
    }
  }

  // ── Config plumbing ──────────────────────────────────────────────────────

  function normalize(raw) {
    const cfg = Object.assign({}, DEFAULTS, raw || {});
    delete cfg.testFire;
    cfg.mappings = (Array.isArray(raw && raw.mappings) ? raw.mappings : []).map(m => ({
      id: m.id || uid(),
      trigger: m.trigger || 'thumbs_up',
      enabled: m.enabled !== false,
      type: m.type === 'image' ? 'image' : 'emoji',
      value: m.value || '',
      animation: m.animation || 'pop',
      placement: m.placement || 'anchor',
      size: Number(m.size) || 0.2,
      duration: Number(m.duration) || 1.4,
      cooldownMs: m.cooldownMs == null ? null : Number(m.cooldownMs),
    }));
    return cfg;
  }

  function applyFromConfig(fullCfg) {
    _cfg = normalize(fullCfg && fullCfg.reactions);
    syncSwitches();
    renderGlobals();
    renderList();
  }

  function getConfig() { return _cfg; }

  function save() {
    clearTimeout(_saveTimer);
    _saveTimer = setTimeout(() => Config.update(), 300);
  }

  // ── Master switch (dialog + controller panel stay in sync) ───────────────

  function syncSwitches() {
    ['rx-master', 'rx-quick-toggle'].forEach(id => {
      const node = el(id);
      if (node) node.checked = !!_cfg.enabled;
    });
    ['rx-tracking', 'rx-quick-tracking'].forEach(id => {
      const node = el(id);
      if (node) node.checked = !!_cfg.showTracking;
    });
    if (typeof App !== 'undefined') App.markNav();
  }

  function setEnabled(on) {
    _cfg.enabled = !!on;
    syncSwitches();
    save();
  }

  function setTracking(on) {
    _cfg.showTracking = !!on;
    syncSwitches();
    if (on && !_cfg.enabled) {
      Toast.show('Tracking shown on the preview only — reactions are still off.', 'info');
    }
    save();
  }

  /** Live detector readout, fed by the SSE status channel. */
  function applyStats(rx) {
    if (!rx) return;
    const set = (id, value) => { const n = el(id); if (n) n.textContent = value; };
    set('rx-live-hands', rx.hands ?? 0);
    set('rx-live-faces', rx.faces ?? 0);
    set('rx-live-fps', rx.detectorFps ?? 0);
    set('rx-live-overlays', rx.overlays ?? 0);
    set('rx-live-match', (rx.matched && rx.matched.length) ? rx.matched.join(', ') : '—');
  }

  // ── Page ─────────────────────────────────────────────────────────────────

  async function openSettings() {
    if (typeof App !== 'undefined') App.navigate('reactions');
    await loadCatalog();
    syncSwitches();
    renderGlobals();
    renderList();
  }

  // ── Global settings ──────────────────────────────────────────────────────

  const GLOBAL_LABELS = {
    detectionFps: (v) => `${v} fps`,
    sensitivity: (v) => `${Number(v).toFixed(2)}×`,
    holdFrames: (v) => `${v}`,
    cooldownMs: (v) => `${v} ms`,
    maxConcurrent: (v) => `${v}`,
    globalScale: (v) => `${Number(v).toFixed(2)}×`,
  };

  const GLOBAL_INPUTS = {
    detectionFps: ['rx-fps', 'rx-fps-val'],
    sensitivity: ['rx-sens', 'rx-sens-val'],
    holdFrames: ['rx-hold', 'rx-hold-val'],
    cooldownMs: ['rx-cooldown', 'rx-cooldown-val'],
    maxConcurrent: ['rx-max', 'rx-max-val'],
    globalScale: ['rx-scale', 'rx-scale-val'],
  };

  function renderGlobals() {
    Object.entries(GLOBAL_INPUTS).forEach(([key, [inputId, valId]]) => {
      const input = el(inputId);
      if (input) input.value = _cfg[key];
      const label = el(valId);
      if (label) label.textContent = GLOBAL_LABELS[key](_cfg[key]);
    });
    const showLabel = el('rx-showlabel');
    if (showLabel) showLabel.checked = !!_cfg.showLabel;
  }

  function onGlobal(key, value) {
    _cfg[key] = typeof value === 'boolean' ? value
      : (key === 'sensitivity' || key === 'globalScale') ? parseFloat(value) : parseInt(value, 10);
    const entry = GLOBAL_INPUTS[key];
    if (entry) {
      const label = el(entry[1]);
      if (label) label.textContent = GLOBAL_LABELS[key](_cfg[key]);
    }
    save();
  }

  // ── Mapping list ─────────────────────────────────────────────────────────

  function artHtml(m) {
    if (m.type === 'image' && m.value) {
      return `<img src="/reactions/assets/${encodeURI(m.value)}" alt="">`;
    }
    return esc(m.value || '❓');
  }

  function warningFor(m) {
    if (m.type === 'image') {
      if (!m.value) return 'Pick an image — upload one if the list is empty.';
      if (_catalog.images.length && !_catalog.images.includes(m.value)) return `“${m.value}” is missing from your reactions folder.`;
      return '';
    }
    if (!m.value) return 'Type or pick an emoji.';
    const bundled = (_catalog.bundledEmoji || []).includes(m.value);
    if (!bundled && !(_catalog.emojiRenderer || {}).available) {
      return `No sprite bundled for ${m.value} and it can't be rendered — ${_catalog.emojiRenderer.reason || 'renderer unavailable'}.`;
    }
    return '';
  }

  function cardHtml(m, i) {
    const tdef = triggerDef(m.trigger);
    const adef = animDef(m.animation) || {};
    const badge = KIND_BADGE[tdef ? tdef.kind : 'hand'];
    const triggers = _catalog.triggers.map(t =>
      `<option value="${esc(t.id)}"${t.id === m.trigger ? ' selected' : ''}>${esc(t.label)}</option>`).join('');
    const anims = _catalog.animations.map(a =>
      `<option value="${esc(a.id)}"${a.id === m.animation ? ' selected' : ''}>${esc(a.label)}</option>`).join('');
    const places = _catalog.placements.map(p =>
      `<option value="${esc(p.id)}"${p.id === m.placement ? ' selected' : ''}>${esc(p.label)}</option>`).join('');
    const images = _catalog.images.map(f =>
      `<option value="${esc(f)}"${f === m.value ? ' selected' : ''}>${esc(f)}</option>`).join('');
    const warn = warningFor(m);

    const valueField = m.type === 'image'
      ? `<select class="rx-select" data-k="value" style="flex:1 1 140px;max-width:230px">
           <option value="">— choose artwork —</option>${images}
         </select>`
      : `<input class="rx-input emoji" data-k="value" maxlength="8" value="${esc(m.value)}" title="Any emoji">
         <button class="btn icon sm" data-act="pick" title="Pick a bundled emoji">😀</button>`;

    return `
      <div class="rx-card${m.enabled ? '' : ' off'}" data-i="${i}">
        <div class="rx-row">
          <label class="switch" title="Enable this reaction">
            <input type="checkbox" data-k="enabled"${m.enabled ? ' checked' : ''}><i></i>
          </label>
          <div class="rx-art">${artHtml(m)}</div>
          <select class="rx-select" data-k="trigger" style="flex:1 1 150px;max-width:230px">${triggers}</select>
          <span class="rx-kind ${badge.cls}">${badge.label}</span>
          <select class="rx-select" data-k="type" style="flex:0 0 78px">
            <option value="emoji"${m.type === 'emoji' ? ' selected' : ''}>Emoji</option>
            <option value="image"${m.type === 'image' ? ' selected' : ''}>Image</option>
          </select>
          ${valueField}
          <button class="btn icon sm" data-act="preview" title="Preview on the live feed">▶</button>
          <button class="btn icon sm" data-act="delete" title="Remove">🗑</button>
        </div>
        <div class="rx-row wrap-grid">
          <div class="rx-field">
            <label>Animation</label>
            <select class="rx-select" data-k="animation">${anims}</select>
          </div>
          <div class="rx-field">
            <label>Placement</label>
            <select class="rx-select" data-k="placement"${adef.spread ? ' disabled title="This animation covers the whole frame"' : ''}>${places}</select>
          </div>
          <div class="rx-field">
            <label>Size <span class="rx-num" data-out="size">${Math.round(m.size * 100)}%</span></label>
            <input type="range" data-k="size" min="4" max="70" step="1" value="${Math.round(m.size * 100)}">
          </div>
          <div class="rx-field">
            <label>Duration <span class="rx-num" data-out="duration">${m.duration.toFixed(1)}s</span></label>
            <input type="range" data-k="duration" min="0.4" max="5" step="0.1" value="${m.duration}">
          </div>
        </div>
        ${warn ? `<div class="rx-warn">⚠ ${esc(warn)}</div>` : ''}
      </div>`;
  }

  function renderList() {
    const list = el('rx-list');
    if (!list) return;
    if (!_cfg.mappings.length) {
      list.innerHTML = `<div class="rx-empty">No reactions yet — add one, or restore the built-in pack.</div>`;
      return;
    }
    list.innerHTML = _cfg.mappings.map(cardHtml).join('');
    list.querySelectorAll('.rx-card').forEach(card => {
      const i = Number(card.dataset.i);
      card.querySelectorAll('[data-k]').forEach(input => {
        const key = input.dataset.k;
        const evt = input.type === 'range' ? 'input' : 'change';
        input.addEventListener(evt, () => onField(i, key, input));
      });
      card.querySelectorAll('[data-act]').forEach(btn => {
        btn.addEventListener('click', () => {
          const act = btn.dataset.act;
          if (act === 'delete') removeMapping(i);
          else if (act === 'preview') preview(i);
          else if (act === 'pick') openPicker(i);
        });
      });
    });
  }

  function onField(i, key, input) {
    const m = _cfg.mappings[i];
    if (!m) return;
    const card = input.closest('.rx-card');

    if (key === 'enabled') {
      m.enabled = input.checked;
      card.classList.toggle('off', !m.enabled);
    } else if (key === 'size') {
      m.size = clamp(parseInt(input.value, 10), 4, 70) / 100;
      card.querySelector('[data-out="size"]').textContent = `${Math.round(m.size * 100)}%`;
    } else if (key === 'duration') {
      m.duration = clamp(parseFloat(input.value), 0.2, 6);
      card.querySelector('[data-out="duration"]').textContent = `${m.duration.toFixed(1)}s`;
    } else if (key === 'type') {
      m.type = input.value;
      m.value = m.type === 'emoji' ? (triggerDef(m.trigger) || {}).emoji || '👍' : '';
      renderList();
    } else if (key === 'trigger') {
      m.trigger = input.value;
      renderList();
    } else if (key === 'value') {
      m.value = input.value.trim();
      renderList();
    } else if (key === 'animation') {
      m.animation = input.value;
      renderList();
    } else {
      m[key] = input.value;
    }
    save();
  }

  function addMapping() {
    const used = new Set(_cfg.mappings.map(m => m.trigger));
    const next = _catalog.triggers.find(t => !used.has(t.id)) || _catalog.triggers[0];
    if (!next) return;
    _cfg.mappings.push({
      id: uid(),
      trigger: next.id,
      enabled: true,
      type: 'emoji',
      value: next.emoji || '👍',
      animation: 'pop',
      placement: 'anchor',
      size: 0.2,
      duration: 1.4,
      cooldownMs: null,
    });
    renderList();
    save();
  }

  function removeMapping(i) {
    _cfg.mappings.splice(i, 1);
    renderList();
    save();
  }

  function restoreDefaults() {
    if (!_catalog.defaults.length) return;
    if (!confirm('Replace the current reaction list with the built-in pack?')) return;
    _cfg.mappings = normalize({ mappings: _catalog.defaults }).mappings;
    renderList();
    save();
    Toast.show('✓ Built-in reaction pack restored.', 'success');
  }

  async function preview(i) {
    const m = _cfg.mappings[i];
    if (!m) return;
    try {
      const res = await fetch('/api/reactions/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(m),
      });
      if (!res.ok) throw new Error(res.statusText);
      Toast.show(`▶ Previewing ${m.value} on the live feed`, 'info');
    } catch (err) {
      Toast.show(`⚠️ Preview failed: ${err.message}`, 'error');
    }
  }

  // ── Emoji picker ─────────────────────────────────────────────────────────

  function renderPicker() {
    const grid = el('rx-picker-grid');
    if (!grid) return;
    grid.innerHTML = (_catalog.bundledEmoji || [])
      .map(c => `<button type="button" title="${esc(c)}">${esc(c)}</button>`).join('');
    grid.querySelectorAll('button').forEach(btn => {
      btn.addEventListener('click', () => pickEmoji(btn.textContent));
    });
  }

  function openPicker(i) {
    _pickerIndex = i;
    const picker = el('rx-picker');
    if (picker) picker.classList.add('open');
  }

  function closePicker() {
    _pickerIndex = null;
    const picker = el('rx-picker');
    if (picker) picker.classList.remove('open');
  }

  function pickEmoji(char) {
    if (_pickerIndex == null) return;
    const m = _cfg.mappings[_pickerIndex];
    if (m) {
      m.type = 'emoji';
      m.value = char;
      renderList();
      save();
    }
    closePicker();
  }

  // ── Artwork upload ───────────────────────────────────────────────────────

  async function uploadAsset(event) {
    const file = event.target.files[0];
    event.target.value = '';
    if (!file) return;
    Toast.show('Uploading artwork…', 'info');
    try {
      const res = await fetch(`/api/reactions/upload?filename=${encodeURIComponent(file.name)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/octet-stream' },
        body: file,
      });
      const data = await res.json();
      if (!res.ok || !data.success) throw new Error(data.error || res.statusText);
      _catalogLoaded = false;
      await loadCatalog();
      Toast.show(`✓ ${data.filename} added to your artwork.`, 'success');
    } catch (err) {
      Toast.show(`⚠️ Upload failed: ${err.message}`, 'error');
    }
  }

  // ── Footer note ──────────────────────────────────────────────────────────

  function renderNote() {
    const note = el('rx-note');
    if (!note) return;
    const r = _catalog.emojiRenderer || {};
    const renderLine = r.available
      ? `Any emoji you type is rendered from <code>${esc(r.font || 'the system emoji font')}</code> and cached.`
      : `⚠ Custom emoji can't be rendered here (${esc(r.reason || 'renderer unavailable')}) — the ${(_catalog.bundledEmoji || []).length} bundled ones still work.`;
    note.innerHTML = `
      Drop your own PNG / GIF memes into the <code>reactions</code> folder of your data directory (or use Upload) and pick them as <b>Image</b>.
      Add bundled emoji with <code>python tools/build_emoji_assets.py 🦄</code>.<br>${renderLine}<br>
      New gestures live in <code>webcam_bridge/reactions/triggers.py</code>, new motion presets in <code>animations.py</code>.`;
  }

  // ── Init ─────────────────────────────────────────────────────────────────

  function init() {
    loadCatalog();
  }

  return {
    init,
    applyFromConfig,
    getConfig,
    applyStats,
    openSettings,
    setEnabled,
    setTracking,
    onGlobal,
    addMapping,
    removeMapping,
    restoreDefaults,
    preview,
    openPicker,
    closePicker,
    uploadAsset,
  };
})();
