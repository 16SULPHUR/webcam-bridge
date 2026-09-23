/**
 * pets.js — Oneko custom-skin pets: list, skin browser, favourites.
 */
const Pets = (() => {
  let _pets = [];
  let _skins = [];
  let _favourites = JSON.parse(localStorage.getItem('neko_favorites') || '[]');
  let _target = null;
  let _filter = 'all';
  let _preview = null;

  const el = (id) => document.getElementById(id);

  function applyFromConfig(cfg) {
    _pets = Array.isArray(cfg.customPets) ? cfg.customPets.map(p => ({
      skin: p.skin || 'socks', enabled: !!p.enabled,
    })) : [];
    loadSkins().then(render);
    render();
  }

  function getConfig() {
    return {
      customPets: _pets,
      customOnekoEnabled: _pets[0] ? _pets[0].enabled : false,
      customOnekoSkin: _pets[0] ? _pets[0].skin : 'socks',
    };
  }

  async function loadSkins() {
    if (_skins.length) return;
    try {
      const res = await fetch('/api/skins');
      const data = await res.json();
      _skins = data.skins || [];
    } catch (err) {
      console.error('[Pets] skin list failed:', err.message);
    }
  }

  function sorted(list) {
    return [...list].sort((a, b) => {
      const fa = _favourites.includes(a), fb = _favourites.includes(b);
      if (fa !== fb) return fa ? -1 : 1;
      return a.localeCompare(b);
    });
  }

  function render() {
    const list = el('pets-list');
    if (!list) return;
    if (!_pets.length) {
      list.innerHTML = '<div class="empty">No custom pets. Add one to pick a skin.</div>';
      return;
    }
    if (!_skins.length) {
      list.insertAdjacentHTML('beforebegin', '');
    }
    list.innerHTML = _pets.map((pet, i) => `
      <div class="pet" data-i="${i}">
        <label class="switch"><input type="checkbox" data-act="toggle"${pet.enabled ? ' checked' : ''}><i></i></label>
        <img src="/skins/${encodeURIComponent(pet.skin)}/still.png" alt="" onerror="this.style.visibility='hidden'">
        <select data-act="skin">
          ${_skins.length
            ? sorted(_skins).map(s => `<option value="${s}"${s === pet.skin ? ' selected' : ''}>${s}${_favourites.includes(s) ? ' ♥' : ''}</option>`).join('')
            : `<option value="${pet.skin}">${pet.skin}</option>`}
        </select>
        <button class="btn sm" data-act="browse">Browse</button>
        <button class="btn icon danger" data-act="remove">✕</button>
      </div>`).join('');

    list.querySelectorAll('.pet').forEach(row => {
      const i = Number(row.dataset.i);
      row.querySelector('[data-act="toggle"]').addEventListener('change', (e) => {
        _pets[i].enabled = e.target.checked;
        Config.update();
      });
      row.querySelector('[data-act="skin"]').addEventListener('change', (e) => {
        _pets[i].skin = e.target.value;
        render();
        Config.update();
      });
      row.querySelector('[data-act="browse"]').addEventListener('click', () => openBrowser(i));
      row.querySelector('[data-act="remove"]').addEventListener('click', () => remove(i));
    });
  }

  function add() {
    _pets.push({ skin: _skins[0] || 'socks', enabled: true });
    render();
    Config.update();
  }

  function remove(i) {
    _pets.splice(i, 1);
    render();
    Config.update();
  }

  // ── Skin browser ─────────────────────────────────────────────────────────

  async function openBrowser(index) {
    _target = index;
    await loadSkins();
    renderBrowser();
    const modal = el('skin-modal');
    if (modal) modal.classList.add('open');
  }

  function closeBrowser() {
    const modal = el('skin-modal');
    if (modal) modal.classList.remove('open');
    if (_preview) { clearInterval(_preview); _preview = null; }
    _target = null;
  }

  function setFilter(mode) {
    _filter = mode;
    el('skin-filter-all')?.classList.toggle('active', mode === 'all');
    el('skin-filter-fav')?.classList.toggle('active', mode === 'fav');
    renderBrowser();
  }

  function renderBrowser() {
    const grid = el('skin-grid');
    if (!grid) return;
    const query = (el('skin-search')?.value || '').toLowerCase().trim();
    const list = sorted(_skins).filter(s =>
      (_filter !== 'fav' || _favourites.includes(s)) && (!query || s.toLowerCase().includes(query)));

    if (!list.length) {
      grid.innerHTML = `<div class="empty" style="grid-column:1/-1">${
        _skins.length ? 'No skins match.'
                      : 'No skins installed — run <code>webcam-bridge fetch skins</code> or put skin folders in the <code>skins</code> folder of your data directory.'}</div>`;
      return;
    }
    grid.innerHTML = list.map(skin => `
      <div class="skin" data-skin="${skin}">
        <button class="fav" data-act="fav" title="Favourite">${_favourites.includes(skin) ? '❤️' : '🤍'}</button>
        <img src="/skins/${encodeURIComponent(skin)}/still.png" alt="${skin}" onerror="this.style.visibility='hidden'">
        <span>${skin}</span>
      </div>`).join('');

    grid.querySelectorAll('.skin').forEach(card => {
      const skin = card.dataset.skin;
      const img = card.querySelector('img');
      card.addEventListener('click', () => select(skin));
      card.querySelector('[data-act="fav"]').addEventListener('click', (e) => {
        e.stopPropagation();
        toggleFavourite(skin);
      });
      card.addEventListener('mouseenter', () => {
        let phase = 1;
        if (_preview) clearInterval(_preview);
        _preview = setInterval(() => {
          img.src = `/skins/${encodeURIComponent(skin)}/${phase === 1 ? 'erun1' : 'erun2'}.png`;
          phase = phase === 1 ? 2 : 1;
        }, 150);
      });
      card.addEventListener('mouseleave', () => {
        if (_preview) { clearInterval(_preview); _preview = null; }
        img.src = `/skins/${encodeURIComponent(skin)}/still.png`;
      });
    });
  }

  function toggleFavourite(skin) {
    const i = _favourites.indexOf(skin);
    if (i === -1) _favourites.push(skin); else _favourites.splice(i, 1);
    localStorage.setItem('neko_favorites', JSON.stringify(_favourites));
    renderBrowser();
    render();
  }

  function select(skin) {
    if (_target !== null && _pets[_target]) {
      _pets[_target].skin = skin;
      render();
      Config.update();
    }
    closeBrowser();
  }

  return { applyFromConfig, getConfig, add, remove, openBrowser, closeBrowser,
           renderBrowser, setFilter, select };
})();
