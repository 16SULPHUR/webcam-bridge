/**
 * stream.js — Live preview, status handling, recording, snapshot,
 *             fullscreen, picture-in-picture and the FPS sparkline.
 */
const Stream = (() => {
  const el = (id) => document.getElementById(id);

  let prevFrames = null;
  let prevStamp = Date.now();
  let fpsHistory = [];
  let isRecording = false;
  let wasConnected = false;
  let keepalive = null;
  let retry = null;

  // ── Feed ─────────────────────────────────────────────────────────────────

  function reloadFeed() {
    const img = el('feed-img');
    if (img) img.src = '/video_feed?' + Date.now();
  }

  function startKeepalive() {
    stopKeepalive();
    keepalive = setInterval(reloadFeed, 30000);
  }

  function stopKeepalive() {
    if (keepalive) { clearInterval(keepalive); keepalive = null; }
    if (retry) { clearTimeout(retry); retry = null; }
  }

  function setOrientation() {
    // Rotation happens server-side; nothing to do in CSS.
  }

  function setResolution(res) {
    const out = el('stat-res');
    if (out) out.textContent = (!res || res === 'auto') ? '1280×720' : res.replace('x', '×');
  }

  // ── Status ───────────────────────────────────────────────────────────────

  function setStatus(state, text) {
    const dot = el('status-dot');
    const label = el('status-text');
    if (dot) dot.className = 'dot ' + state;
    if (label) label.textContent = text;
  }

  function handleStatus(data) {
    const connected = !!data.androidConnected;
    const justConnected = connected && !wasConnected;
    wasConnected = connected;

    const img = el('feed-img');
    const placeholder = el('feed-placeholder');
    const badge = el('feed-badge');
    const fps = el('overlay-fps');

    if (connected) {
      setStatus('connected', 'Streaming');
      if (img) {
        img.style.display = 'block';
        if (justConnected) {
          reloadFeed();
          startKeepalive();
          img.onerror = () => {
            if (!wasConnected) return;
            clearTimeout(retry);
            retry = setTimeout(reloadFeed, 1500);
          };
        }
      }
      if (placeholder) placeholder.style.display = 'none';
      if (fps) fps.style.display = 'block';
      if (badge) { badge.textContent = '● LIVE'; badge.className = 'stage-tag live'; }
    } else {
      setStatus('connecting', data.deviceState === 'installing' ? 'Installing app' : 'Waiting for phone');
      if (data.deviceHint) setText('feed-hint', data.deviceHint);
      stopKeepalive();
      if (img) { img.style.display = 'none'; img.onerror = null; }
      if (placeholder) placeholder.style.display = 'flex';
      if (fps) fps.style.display = 'none';
      if (badge) { badge.textContent = 'OFFLINE'; badge.className = 'stage-tag'; }
    }

    if (data.h264ReceivedBytes !== undefined) {
      const mb = data.h264ReceivedBytes / 1048576;
      setText('stat-h264', mb.toFixed(1));
    }

    if (data.decodedFrames !== undefined) {
      setText('hdr-frames', data.decodedFrames.toLocaleString());
      setText('stat-frames', data.decodedFrames.toLocaleString());

      if (prevFrames === null) {          // first sample only sets the baseline
        prevFrames = data.decodedFrames;
        prevStamp = Date.now();
      }
      const dt = (Date.now() - prevStamp) / 1000;
      if (dt >= 0.5) {
        const fpsNow = Math.max(0, Math.round((data.decodedFrames - prevFrames) / dt));
        prevFrames = data.decodedFrames;
        prevStamp = Date.now();
        fpsHistory.push(fpsNow);
        if (fpsHistory.length > 30) fpsHistory.shift();
        const avg = Math.round(fpsHistory.reduce((a, b) => a + b, 0) / fpsHistory.length);
        setText('hdr-fps', avg);
        setText('overlay-fps', avg + ' fps');
        drawSparkline();
        const bar = el('health-signal');
        if (bar) bar.style.width = Math.min(100, (avg / 30) * 100) + '%';
      }
    }

    if (data.bitrateKBs !== undefined) {
      setText('hdr-bitrate', data.bitrateKBs.toFixed(1));
      setText('stat-bitrate', data.bitrateKBs.toFixed(1));
    }

    if (data.vcamActive !== undefined) {
      const tag = el('health-vcam');
      if (tag) {
        tag.textContent = data.vcamActive ? 'VCam live' : 'VCam off';
        tag.className = 'tag ' + (data.vcamActive ? 'ok' : '');
      }
    }

    if (data.recording !== undefined) setRecordingUI(data.recording);
    if (data.updateAvailable) {
      const link = el('update-link');
      if (link) {
        link.textContent = 'Update available: v' + data.updateAvailable;
        link.style.display = '';
      }
    }
    phoneStats(data);
  }

  function setText(id, value) {
    const node = el(id);
    if (node) node.textContent = value;
  }

  function phoneStats(data) {
    if (data.phoneModel) setText('phone-model', data.phoneModel);
    if (data.phoneAndroidVersion) setText('phone-version', data.phoneAndroidVersion);

    if (data.phoneBattery != null) {
      const charging = ['charging', 'full'].includes(data.phoneBatteryStatus);
      setText('phone-battery', data.phoneBattery + '%');
      setText('phone-battery-icon', charging ? '🔌' : (data.phoneBattery > 25 ? '🔋' : '🪫'));
      const bar = el('phone-battery-bar');
      if (bar) {
        bar.style.width = Math.min(100, data.phoneBattery) + '%';
        bar.style.background = data.phoneBattery > 60 ? 'var(--ok)'
          : (data.phoneBattery > 25 ? 'var(--warn)' : 'var(--bad)');
      }
    }
    if (data.phoneTemperature != null) {
      const node = el('phone-temp');
      if (node) {
        node.textContent = data.phoneTemperature.toFixed(1) + '°';
        node.style.color = data.phoneTemperature > 40 ? 'var(--bad)' : '';
      }
    }
    if (data.phoneUptime != null) {
      const h = Math.floor(data.phoneUptime / 3600);
      const m = Math.floor((data.phoneUptime % 3600) / 60);
      setText('phone-uptime', `${h}h ${m}m`);
    }
  }

  // ── Sparkline ────────────────────────────────────────────────────────────

  function drawSparkline() {
    const canvas = el('fps-sparkline');
    if (!canvas || fpsHistory.length < 2) return;
    const ctx = canvas.getContext('2d');
    const { width: W, height: H } = canvas;
    ctx.clearRect(0, 0, W, H);
    const max = Math.max(30, ...fpsHistory);
    const step = W / (fpsHistory.length - 1);
    const point = (fps, i) => [i * step, H - (fps / max) * (H - 2) - 1];

    ctx.beginPath();
    ctx.moveTo(0, H);
    fpsHistory.forEach((f, i) => ctx.lineTo(...point(f, i)));
    ctx.lineTo(W, H);
    ctx.closePath();
    const grad = ctx.createLinearGradient(0, 0, 0, H);
    grad.addColorStop(0, 'rgba(56,189,248,0.35)');
    grad.addColorStop(1, 'rgba(56,189,248,0.02)');
    ctx.fillStyle = grad;
    ctx.fill();

    ctx.beginPath();
    fpsHistory.forEach((f, i) => {
      const [x, y] = point(f, i);
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.strokeStyle = '#38bdf8';
    ctx.lineWidth = 1.5;
    ctx.stroke();
  }

  // ── Recording ────────────────────────────────────────────────────────────

  function setRecordingUI(active) {
    isRecording = active;
    el('btn-record')?.classList.toggle('recording', active);
    const dot = el('record-dot');
    if (dot) dot.className = 'dot' + (active ? ' error' : '');
    setText('record-label', active ? 'Stop' : 'Record');
  }

  async function toggleRecording() {
    const path = isRecording ? '/api/record/stop' : '/api/record/start';
    try {
      const res = await fetch(path, { method: 'POST' });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || res.statusText);
      setRecordingUI(!isRecording);
      Toast.show(isRecording ? `Saved → ${json.file}` : 'Recording started', 'success');
    } catch (err) {
      Toast.show(`Recording: ${err.message}`, 'error');
    }
  }

  async function reconnect() {
    setStatus('connecting', 'Restarting…');
    try {
      const res = await fetch('/api/reconnect', { method: 'POST' });
      if (!res.ok) throw new Error(res.statusText);
      Toast.show('Pipeline restarting…', 'info');
    } catch (err) {
      Toast.show(`Restart failed: ${err.message}`, 'error');
    }
  }

  // ── Snapshot / fullscreen / PiP ──────────────────────────────────────────

  function snapshot() {
    const img = el('feed-img');
    if (!img || img.style.display === 'none') {
      Toast.show('No stream to capture.', 'error');
      return;
    }
    try {
      const canvas = document.createElement('canvas');
      canvas.width = img.naturalWidth || 1280;
      canvas.height = img.naturalHeight || 720;
      canvas.getContext('2d').drawImage(img, 0, 0);
      const link = document.createElement('a');
      link.download = `snapshot-${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.png`;
      link.href = canvas.toDataURL('image/png');
      link.click();
      Toast.show('Snapshot saved.', 'success');
    } catch (err) {
      Toast.show(`Snapshot: ${err.message}`, 'error');
    }
  }

  async function toggleFullscreen() {
    const stage = el('stage');
    if (!stage) return;
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await stage.requestFullscreen();
    } catch (err) {
      Toast.show(`Fullscreen: ${err.message}`, 'error');
    }
  }

  document.addEventListener('fullscreenchange', () => {
    el('stage')?.classList.toggle('fullscreen-mode', !!document.fullscreenElement);
  });

  async function togglePiP() {
    const img = el('feed-img');
    if (!img || img.style.display === 'none') {
      Toast.show('PiP needs an active stream.', 'error');
      return;
    }
    try {
      if (document.pictureInPictureElement) {
        await document.exitPictureInPicture();
        return;
      }
      const video = el('pip-video');
      const canvas = document.createElement('canvas');
      canvas.width = 640; canvas.height = 360;
      const ctx = canvas.getContext('2d');
      let frame;
      const paint = () => {
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        frame = requestAnimationFrame(paint);
      };
      paint();
      video.srcObject = canvas.captureStream(30);
      await video.play();
      await video.requestPictureInPicture();
      video.addEventListener('leavepictureinpicture', () => {
        cancelAnimationFrame(frame);
        video.srcObject = null;
      }, { once: true });
    } catch (err) {
      Toast.show(`PiP: ${err.message}`, 'error');
    }
  }

  return { setStatus, handleStatus, setOrientation, setResolution, reloadFeed,
           reconnect, snapshot, toggleFullscreen, togglePiP, toggleRecording };
})();
