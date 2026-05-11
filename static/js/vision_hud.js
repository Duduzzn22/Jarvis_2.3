/* ═══════════════════════════════════════════════════════════════════════
   J.A.R.V.I.S. — IRON MAN VISION HUD v1.0
   Real-time webcam feed with tactical overlay rendering at 60fps.

   Architecture:
     Socket event 'vision_frame' → VisionHUD.onFrame()
       → drawBackground (video feed)
       → drawScanLines  (moving scan animation)
       → drawGrid       (tactical grid)
       → drawDetections (bounding boxes, labels, confidence)
       → drawReticle    (center tracking cross)
       → drawTelemetry  (FPS, motion, scene text)
       → drawCorners    (Iron Man corner brackets)
   ═══════════════════════════════════════════════════════════════════════ */

'use strict';

const VisionHUD = (() => {

  // ── State ──────────────────────────────────────────────────────────────
  let _canvas        = null;
  let _ctx           = null;
  let _overlay       = null;   // DOM overlay panel
  let _open          = false;
  let _animFrame     = null;
  let _lastFrame     = null;
  let _img           = new Image();
  let _imgLoaded     = false;
  let _scanY         = 0;
  let _scanDir       = 1;
  let _pulse         = 0;
  let _glitchTimer   = 0;
  let _detections    = [];
  let _telemetry     = { fps: 0, motion: 0, scene: '', ocr: '', faces: 0 };
  let _alerts        = [];
  let _bootAnim      = 0;      // 0→1 boot progress
  let _isBooting     = true;
  let _trackHistory  = {};     // id → [{x,y}] trail
  let _engineRunning = false;
  let _lastSceneText = '';
  let _ocrText       = '';

  // ── Color scheme (mirrors CSS vars, but can't use getComputedStyle in loop) ─
  const C = {
    primary:    '#00e5ff',
    secondary:  '#ff8c00',
    green:      '#00ff88',
    red:        '#ff4444',
    amber:      '#ffaa00',
    face:       '#00e5ff',
    object:     '#ff8c00',
    gesture:    '#00ff88',
    motion:     '#ff6b00',
    text_dim:   'rgba(0,229,255,0.4)',
    grid:       'rgba(0,229,255,0.06)',
    scan:       'rgba(0,229,255,0.12)',
  };

  // Swapped colors for Friday theme
  function _getC(key) {
    if (typeof ThemeEngine !== 'undefined' && ThemeEngine.isFriday()) {
      const friday = {
        primary:   '#1a1a2e', secondary: '#5865f2', green: '#22c55e',
        face:      '#1a1a2e', object:    '#5865f2', gesture: '#22c55e',
        grid:      'rgba(26,26,46,0.06)', scan: 'rgba(26,26,46,0.1)',
        text_dim:  'rgba(26,26,46,0.4)',
      };
      return friday[key] || C[key];
    }
    return C[key];
  }

  // ── Detection type → color mapping ────────────────────────────────────
  function _colorForType(type) {
    switch (type) {
      case 'face':    return _getC('face');
      case 'object':  return _getC('object');
      case 'gesture': return _getC('gesture');
      case 'motion':  return _getC('motion');
      default:        return _getC('primary');
    }
  }

  // ── DOM BUILDER ────────────────────────────────────────────────────────
  function _buildDOM() {
    if (document.getElementById('vision-hud-overlay')) return;

    const overlay = document.createElement('div');
    overlay.id    = 'vision-hud-overlay';
    overlay.innerHTML = `
      <div id="vision-hud-panel">
        <!-- Corner brackets -->
        <div class="vhud-corner vhud-tl"></div>
        <div class="vhud-corner vhud-tr"></div>
        <div class="vhud-corner vhud-bl"></div>
        <div class="vhud-corner vhud-br"></div>

        <!-- Header -->
        <div id="vhud-header">
          <div id="vhud-title">
            <span class="vhud-label">JARVIS</span>
            <span class="vhud-sep">◈</span>
            <span class="vhud-label">VISION SYSTEM</span>
          </div>
          <div id="vhud-controls">
            <button class="vhud-btn" id="vhud-pause-btn" onclick="VisionHUD.togglePause()">⏸ PAUSE</button>
            <button class="vhud-btn" id="vhud-snap-btn"  onclick="VisionHUD.snapshot()">📸 SNAP</button>
            <button class="vhud-btn vhud-close" onclick="VisionHUD.close()">✕</button>
          </div>
        </div>

        <!-- Main canvas area -->
        <div id="vhud-main">
          <div id="vhud-feed-wrap">
            <canvas id="vhud-canvas"></canvas>
            <!-- Boot overlay -->
            <div id="vhud-boot">
              <div id="vhud-boot-text">INICIALIZANDO VISION CORE...</div>
              <div id="vhud-boot-bar"><div id="vhud-boot-fill"></div></div>
            </div>
          </div>

          <!-- Right telemetry panel -->
          <div id="vhud-telem">
            <div class="vhud-telem-section">
              <div class="vhud-telem-label">SISTEMA</div>
              <div class="vhud-telem-row">
                <span>FPS</span>
                <span id="vt-fps">—</span>
              </div>
              <div class="vhud-telem-row">
                <span>MOTION</span>
                <span id="vt-motion">—</span>
              </div>
              <div class="vhud-telem-row">
                <span>DETECÇÕES</span>
                <span id="vt-dets">0</span>
              </div>
              <div class="vhud-telem-row">
                <span>FACES</span>
                <span id="vt-faces">0</span>
              </div>
            </div>

            <div class="vhud-telem-section">
              <div class="vhud-telem-label">ML STATUS</div>
              <div class="vhud-telem-row">
                <span>MEDIAPIPE</span>
                <span id="vt-mp" class="vhud-dot">—</span>
              </div>
              <div class="vhud-telem-row">
                <span>YOLO</span>
                <span id="vt-yolo" class="vhud-dot">—</span>
              </div>
              <div class="vhud-telem-row">
                <span>OCR</span>
                <span id="vt-ocr" class="vhud-dot">—</span>
              </div>
            </div>

            <div class="vhud-telem-section" id="vhud-scene-section">
              <div class="vhud-telem-label">CENA IA</div>
              <div id="vt-scene">Aguardando análise...</div>
            </div>

            <div class="vhud-telem-section" id="vhud-ocr-section" style="display:none;">
              <div class="vhud-telem-label">OCR</div>
              <div id="vt-ocr-text">—</div>
            </div>

            <div class="vhud-telem-section">
              <div class="vhud-telem-label">DETECÇÕES ATIVAS</div>
              <div id="vt-det-list"></div>
            </div>
          </div>
        </div>

        <!-- Bottom status bar -->
        <div id="vhud-footer">
          <div id="vhud-status-dot" class="vhud-online"></div>
          <span id="vhud-status-text">VISION CORE ONLINE</span>
          <span id="vhud-timestamp">—</span>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);
    _overlay = overlay;

    _canvas = document.getElementById('vhud-canvas');
    _ctx    = _canvas.getContext('2d');

    overlay.addEventListener('click', e => {
      if (e.target === overlay) close();
    });
  }

  // ── RENDER LOOP ────────────────────────────────────────────────────────
  function _renderLoop() {
    _animFrame = requestAnimationFrame(_renderLoop);
    if (!_open || !_ctx) return;

    const W = _canvas.width;
    const H = _canvas.height;

    // Boot animation
    if (_isBooting) {
      _bootAnim = Math.min(1, _bootAnim + 0.015);
      _drawBoot(W, H);
      if (_bootAnim >= 1) _isBooting = false;
      return;
    }

    _ctx.clearRect(0, 0, W, H);

    // 1. Video frame background
    if (_imgLoaded) {
      _ctx.globalAlpha = 1;
      _ctx.drawImage(_img, 0, 0, W, H);
    } else {
      _drawNoSignal(W, H);
    }

    // 2. Tactical overlays
    _drawGrid(W, H);
    _drawScanLine(W, H);
    _drawDetections(W, H);
    _drawCenterReticle(W, H);
    _drawCornerBrackets(W, H);
    _drawHUDTelemetry(W, H);
    _drawMotionBar(W, H);
    _drawPulse(W, H);

    _scanY  += 2 * _scanDir;
    if (_scanY >= H || _scanY <= 0) _scanDir *= -1;
    _pulse   = (_pulse + 0.03) % (Math.PI * 2);
    _glitchTimer++;
  }

  function _drawBoot(W, H) {
    _ctx.fillStyle = '#020609';
    _ctx.fillRect(0, 0, W, H);

    const prog = _bootAnim;
    _ctx.strokeStyle = _getC('primary');
    _ctx.lineWidth   = 1;
    _ctx.globalAlpha = prog;

    // Boot grid lines
    for (let i = 0; i < 8; i++) {
      _ctx.globalAlpha = Math.random() * 0.3 * prog;
      _ctx.beginPath();
      _ctx.moveTo(0, (H / 8) * i);
      _ctx.lineTo(W * prog, (H / 8) * i);
      _ctx.stroke();
    }

    // Progress text
    _ctx.globalAlpha = 1;
    _ctx.font        = '11px "Share Tech Mono", monospace';
    _ctx.fillStyle   = _getC('primary');
    _ctx.textAlign   = 'center';
    _ctx.fillText('INICIALIZANDO SISTEMA DE VISÃO', W / 2, H / 2 - 20);

    // Progress bar
    _ctx.strokeStyle = _getC('primary');
    _ctx.lineWidth   = 1;
    _ctx.strokeRect(W * 0.2, H / 2, W * 0.6, 4);
    _ctx.fillStyle = _getC('primary');
    _ctx.fillRect(W * 0.2, H / 2, W * 0.6 * prog, 4);
  }

  function _drawNoSignal(W, H) {
    _ctx.fillStyle = '#020609';
    _ctx.fillRect(0, 0, W, H);

    // Noise effect
    for (let i = 0; i < 200; i++) {
      _ctx.fillStyle = `rgba(0,229,255,${Math.random() * 0.05})`;
      _ctx.fillRect(
        Math.random() * W, Math.random() * H,
        Math.random() * 4 + 1, 1
      );
    }
    _ctx.font      = '13px "Share Tech Mono", monospace';
    _ctx.fillStyle = _getC('text_dim');
    _ctx.textAlign = 'center';
    _ctx.fillText('AGUARDANDO SINAL DE CÂMERA...', W / 2, H / 2);
  }

  function _drawGrid(W, H) {
    _ctx.strokeStyle = _getC('grid');
    _ctx.lineWidth   = 0.5;
    const step = 40;
    for (let x = 0; x < W; x += step) {
      _ctx.beginPath(); _ctx.moveTo(x, 0); _ctx.lineTo(x, H); _ctx.stroke();
    }
    for (let y = 0; y < H; y += step) {
      _ctx.beginPath(); _ctx.moveTo(0, y); _ctx.lineTo(W, y); _ctx.stroke();
    }
  }

  function _drawScanLine(W, H) {
    const grad = _ctx.createLinearGradient(0, _scanY - 8, 0, _scanY + 8);
    grad.addColorStop(0,   'transparent');
    grad.addColorStop(0.5, _getC('scan'));
    grad.addColorStop(1,   'transparent');
    _ctx.fillStyle   = grad;
    _ctx.globalAlpha = 0.8;
    _ctx.fillRect(0, _scanY - 8, W, 16);
    _ctx.globalAlpha = 1;
  }

  function _drawDetections(W, H) {
    for (const det of _detections) {
      const x = det.x * W;
      const y = det.y * H;
      const w = det.w * W;
      const h = det.h * H;
      const color = _colorForType(det.type);

      if (w < 1 || h < 1) continue;

      _ctx.globalAlpha = 0.9;

      // Animated corner brackets (Iron Man style)
      const cornerLen = Math.min(w, h) * 0.25;
      _ctx.strokeStyle = color;
      _ctx.lineWidth   = 1.5;

      // TL
      _ctx.beginPath(); _ctx.moveTo(x, y + cornerLen); _ctx.lineTo(x, y); _ctx.lineTo(x + cornerLen, y); _ctx.stroke();
      // TR
      _ctx.beginPath(); _ctx.moveTo(x + w - cornerLen, y); _ctx.lineTo(x + w, y); _ctx.lineTo(x + w, y + cornerLen); _ctx.stroke();
      // BL
      _ctx.beginPath(); _ctx.moveTo(x, y + h - cornerLen); _ctx.lineTo(x, y + h); _ctx.lineTo(x + cornerLen, y + h); _ctx.stroke();
      // BR
      _ctx.beginPath(); _ctx.moveTo(x + w - cornerLen, y + h); _ctx.lineTo(x + w, y + h); _ctx.lineTo(x + w, y + h - cornerLen); _ctx.stroke();

      // Box fill (subtle)
      _ctx.globalAlpha = 0.06;
      _ctx.fillStyle   = color;
      _ctx.fillRect(x, y, w, h);
      _ctx.globalAlpha = 0.9;

      // Label background
      _ctx.fillStyle   = 'rgba(2,6,9,0.75)';
      _ctx.fillRect(x, y - 18, Math.max(w, 80), 17);

      // Label text
      _ctx.font        = '9px "Share Tech Mono", monospace';
      _ctx.fillStyle   = color;
      _ctx.textAlign   = 'left';
      const conf       = Math.round((det.confidence || 0) * 100);
      _ctx.fillText(`${det.label}  ${conf}%`, x + 4, y - 5);

      // Tracking line trail
      if (det.type === 'face' || det.type === 'object') {
        _addTrackPoint(det.id, x + w / 2, y + h / 2);
        _drawTrail(det.id, color);
      }
    }
    _ctx.globalAlpha = 1;
  }

  function _addTrackPoint(id, x, y) {
    if (!_trackHistory[id]) _trackHistory[id] = [];
    _trackHistory[id].push({ x, y });
    if (_trackHistory[id].length > 20) _trackHistory[id].shift();
  }

  function _drawTrail(id, color) {
    const trail = _trackHistory[id];
    if (!trail || trail.length < 2) return;
    _ctx.strokeStyle = color;
    _ctx.lineWidth   = 1;
    for (let i = 1; i < trail.length; i++) {
      _ctx.globalAlpha = (i / trail.length) * 0.4;
      _ctx.beginPath();
      _ctx.moveTo(trail[i - 1].x, trail[i - 1].y);
      _ctx.lineTo(trail[i].x,     trail[i].y);
      _ctx.stroke();
    }
    _ctx.globalAlpha = 1;
  }

  function _drawCenterReticle(W, H) {
    const cx     = W / 2;
    const cy     = H / 2;
    const radius = 20 + Math.sin(_pulse) * 3;
    const color  = _getC('primary');

    _ctx.strokeStyle = color;
    _ctx.lineWidth   = 1;
    _ctx.globalAlpha = 0.6;

    // Outer ring (dashed)
    _ctx.setLineDash([4, 4]);
    _ctx.beginPath();
    _ctx.arc(cx, cy, radius + 10, 0, Math.PI * 2);
    _ctx.stroke();
    _ctx.setLineDash([]);

    // Cross hairs
    const arm = 16;
    _ctx.beginPath();
    _ctx.moveTo(cx - arm - 6, cy); _ctx.lineTo(cx - 6, cy);
    _ctx.moveTo(cx + 6, cy);       _ctx.lineTo(cx + arm + 6, cy);
    _ctx.moveTo(cx, cy - arm - 6); _ctx.lineTo(cx, cy - 6);
    _ctx.moveTo(cx, cy + 6);       _ctx.lineTo(cx, cy + arm + 6);
    _ctx.stroke();

    // Inner dot pulse
    _ctx.globalAlpha = 0.4 + Math.sin(_pulse) * 0.3;
    _ctx.fillStyle   = color;
    _ctx.beginPath();
    _ctx.arc(cx, cy, 3, 0, Math.PI * 2);
    _ctx.fill();

    _ctx.globalAlpha = 1;
  }

  function _drawCornerBrackets(W, H) {
    const color  = _getC('primary');
    const margin = 12;
    const len    = 24;

    _ctx.strokeStyle = color;
    _ctx.lineWidth   = 1.5;
    _ctx.globalAlpha = 0.7;

    // TL
    _ctx.beginPath();
    _ctx.moveTo(margin, margin + len); _ctx.lineTo(margin, margin); _ctx.lineTo(margin + len, margin);
    _ctx.stroke();
    // TR
    _ctx.beginPath();
    _ctx.moveTo(W - margin - len, margin); _ctx.lineTo(W - margin, margin); _ctx.lineTo(W - margin, margin + len);
    _ctx.stroke();
    // BL
    _ctx.beginPath();
    _ctx.moveTo(margin, H - margin - len); _ctx.lineTo(margin, H - margin); _ctx.lineTo(margin + len, H - margin);
    _ctx.stroke();
    // BR
    _ctx.beginPath();
    _ctx.moveTo(W - margin - len, H - margin); _ctx.lineTo(W - margin, H - margin); _ctx.lineTo(W - margin, H - margin - len);
    _ctx.stroke();

    _ctx.globalAlpha = 1;
  }

  function _drawHUDTelemetry(W, H) {
    const color  = _getC('primary');
    const dimmed = _getC('text_dim');
    _ctx.font    = '8px "Share Tech Mono", monospace';
    _ctx.globalAlpha = 0.8;

    // Bottom-left: FPS + motion
    _ctx.fillStyle = dimmed;
    _ctx.textAlign = 'left';
    _ctx.fillText(`FPS ${_telemetry.fps.toFixed(1)}`, 14, H - 26);
    _ctx.fillText(`MOT ${(_telemetry.motion * 100).toFixed(0)}%`, 14, H - 14);

    // Bottom-right: timestamp
    _ctx.textAlign = 'right';
    _ctx.fillText(new Date().toLocaleTimeString('pt-BR'), W - 14, H - 14);

    // Top-left: VISION SYSTEM label
    _ctx.fillStyle = color;
    _ctx.textAlign = 'left';
    _ctx.font      = '9px "Share Tech Mono", monospace';
    _ctx.fillText('VISION CORE v1.0', 14, 18);

    _ctx.globalAlpha = 1;
  }

  function _drawMotionBar(W, H) {
    if (_telemetry.motion < 0.01) return;
    const barW = W * 0.3;
    const barH = 3;
    const x    = (W - barW) / 2;
    const y    = H - 8;
    const fill = barW * Math.min(_telemetry.motion * 5, 1);
    const color = _telemetry.motion > 0.15 ? _getC('motion') : _getC('primary');

    _ctx.globalAlpha = 0.6;
    _ctx.fillStyle   = 'rgba(0,0,0,0.4)';
    _ctx.fillRect(x, y, barW, barH);
    _ctx.fillStyle   = color;
    _ctx.fillRect(x, y, fill, barH);
    _ctx.globalAlpha = 1;
  }

  function _drawPulse(W, H) {
    // Arc-reactor style center pulse (very subtle)
    const cx   = W / 2;
    const cy   = H / 2;
    const r    = 60 + Math.sin(_pulse) * 8;
    const grad = _ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
    grad.addColorStop(0,   'rgba(0,229,255,0.04)');
    grad.addColorStop(0.5, 'rgba(0,229,255,0.01)');
    grad.addColorStop(1,   'transparent');
    _ctx.globalAlpha = 0.5;
    _ctx.fillStyle   = grad;
    _ctx.beginPath(); _ctx.arc(cx, cy, r, 0, Math.PI * 2); _ctx.fill();
    _ctx.globalAlpha = 1;
  }

  // ── DOM UPDATERS ───────────────────────────────────────────────────────
  function _updateDOM(frameData) {
    // Telemetry sidebar
    _setText('vt-fps',    frameData.fps?.toFixed(1) || '—');
    _setText('vt-motion', `${((frameData.motion_level || 0) * 100).toFixed(0)}%`);
    _setText('vt-dets',   frameData.detections?.length || 0);

    const faces = (frameData.detections || []).filter(d => d.type === 'face').length;
    _setText('vt-faces', faces);

    // Detection list
    const list  = document.getElementById('vt-det-list');
    if (list) {
      const items = (frameData.detections || []).slice(0, 8).map(d =>
        `<div class="vhud-det-item" style="color:${_colorForType(d.type)}">
           ${d.label} <span style="opacity:.5">${Math.round((d.confidence||0)*100)}%</span>
         </div>`
      ).join('');
      list.innerHTML = items || '<div style="opacity:.4;font-size:9px;">Sem detecções</div>';
    }

    // Scene description
    if (frameData.scene_desc && frameData.scene_desc !== _lastSceneText) {
      _lastSceneText = frameData.scene_desc;
      const el = document.getElementById('vt-scene');
      if (el) {
        el.textContent = frameData.scene_desc;
        el.style.animation = 'none';
        requestAnimationFrame(() => el.style.animation = 'vhudFadeIn 0.5s ease');
      }
    }

    // Timestamp
    _setText('vhud-timestamp', new Date().toLocaleTimeString('pt-BR'));
  }

  function _setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  }

  // ── PUBLIC API ─────────────────────────────────────────────────────────
  function open() {
    _buildDOM();
    const overlay = document.getElementById('vision-hud-overlay');
    overlay.classList.add('open');
    _open     = true;
    _isBooting = true;
    _bootAnim  = 0;

    // Size canvas to fit container
    const feedWrap = document.getElementById('vhud-feed-wrap');
    if (feedWrap && _canvas) {
      _canvas.width  = feedWrap.clientWidth  || 640;
      _canvas.height = feedWrap.clientHeight || 360;
    }

    _renderLoop();

    // Request backend to start vision
    if (typeof socket !== 'undefined') {
      socket.emit('vision_control', { action: 'start' });
    }
  }

  function close() {
    _open = false;
    if (_animFrame) cancelAnimationFrame(_animFrame);
    const overlay = document.getElementById('vision-hud-overlay');
    if (overlay) overlay.classList.remove('open');

    if (typeof socket !== 'undefined') {
      socket.emit('vision_control', { action: 'stop' });
    }
  }

  function togglePause() {
    if (!typeof socket !== 'undefined') return;
    const paused = !_engineRunning;
    socket.emit('vision_control', { action: paused ? 'resume' : 'pause' });
    const btn = document.getElementById('vhud-pause-btn');
    if (btn) btn.textContent = paused ? '⏸ PAUSE' : '▶ RESUME';
  }

  function snapshot() {
    if (!_canvas) return;
    const link     = document.createElement('a');
    link.download  = `jarvis_vision_${Date.now()}.png`;
    link.href      = _canvas.toDataURL('image/png');
    link.click();
    if (typeof showToast === 'function') showToast('📸 Snapshot salvo', 'success');
  }

  // ── SOCKET HANDLERS ────────────────────────────────────────────────────
  function onFrame(data) {
    if (!_open) return;

    _detections  = data.detections || [];
    _telemetry   = {
      fps:    data.fps    || 0,
      motion: data.motion_level || 0,
      scene:  data.scene_desc   || '',
      ocr:    '',
      faces:  _detections.filter(d => d.type === 'face').length,
    };

    // Update video frame
    if (data.jpeg_b64) {
      _img.onload   = () => { _imgLoaded = true; };
      _img.src      = `data:image/jpeg;base64,${data.jpeg_b64}`;
      _imgLoaded    = _img.complete;
    }

    _updateDOM(data);
  }

  function onScene(data) {
    const el = document.getElementById('vt-scene');
    if (el) el.textContent = data.description || '';
    _lastSceneText = data.description || '';
  }

  function onOCR(data) {
    const el = document.getElementById('vt-ocr-text');
    if (el) {
      el.textContent = data.text || '—';
      const sec = document.getElementById('vhud-ocr-section');
      if (sec) sec.style.display = data.text ? '' : 'none';
    }
  }

  function onMLStatus(data) {
    _setDot('vt-mp',   data.mediapipe);
    _setDot('vt-yolo', data.yolo);
    _setDot('vt-ocr',  data.ocr);
  }

  function _setDot(id, online) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent  = online ? '●' : '○';
    el.style.color  = online ? _getC('green') : _getC('text_dim');
  }

  function onStarted()  { _engineRunning = true;  _isBooting = false; }
  function onStopped()  { _engineRunning = false; _imgLoaded = false; }

  // ── Socket integration — auto-hook ────────────────────────────────────
  function _hookSocket() {
    if (typeof socket === 'undefined') {
      setTimeout(_hookSocket, 800);
      return;
    }
    socket.on('vision_frame',   onFrame);
    socket.on('vision_scene',   onScene);
    socket.on('vision_ocr',     onOCR);
    socket.on('vision_started', onStarted);
    socket.on('vision_stopped', onStopped);
    socket.on('vision_ml_status', onMLStatus);
  }

  _hookSocket();

  return { open, close, togglePause, snapshot, onFrame, onScene, onOCR };
})();

window.VisionHUD = VisionHUD;