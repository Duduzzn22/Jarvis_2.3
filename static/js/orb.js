/* ═══════════════════════════════════════════════════════════════
   JARVIS OS — ORB SYSTEM
   HUD Orb canvas, neural background, waveform visualization
   ═══════════════════════════════════════════════════════════════ */

'use strict';

// ══════════════════════════════════════════
//  WAVEFORM
// ══════════════════════════════════════════

const waveCanvas = document.getElementById('waveform-canvas');
const waveCtx    = waveCanvas ? waveCanvas.getContext('2d') : null;
if (waveCanvas) {
  waveCanvas.width  = 300;
  waveCanvas.height = 70;
}

const NUM_BARS = 64;
let waveData   = new Array(NUM_BARS).fill(0);

function drawWaveform(data) {
  if (!waveCtx) return;
  waveCtx.clearRect(0, 0, 300, 70);
  const barW   = 300 / NUM_BARS - 0.8;
  const centerY = 35;

  data.forEach((val, i) => {
    const h = Math.max(2, val * 58);
    const x = i * (barW + 0.8);

    const gradient = waveCtx.createLinearGradient(0, centerY - h/2, 0, centerY + h/2);
    gradient.addColorStop(0,   '#ffffff');
    gradient.addColorStop(0.5, '#00d4ff');
    gradient.addColorStop(1,   '#003366');

    waveCtx.fillStyle   = gradient;
    waveCtx.globalAlpha = 0.75;
    waveCtx.beginPath();
    if (waveCtx.roundRect) {
      waveCtx.roundRect(x, centerY - h/2, barW, h, 1);
    } else {
      waveCtx.rect(x, centerY - h/2, barW, h);
    }
    waveCtx.fill();
  });

  waveCtx.globalAlpha = 1;
}

window.drawWaveform = drawWaveform;

// Idle animation
let idlePhase   = 0;
let waveAnimFrame = null;
JARVIS.waveAnimFrame = waveAnimFrame;

function animateIdle() {
  idlePhase += 0.045;
  const idleData = Array.from({ length: NUM_BARS }, (_, i) => {
    const base  = 0.025;
    const wave1 = Math.sin(idlePhase + i * 0.2) * 0.035;
    const wave2 = Math.sin(idlePhase * 0.65 + i * 0.35) * 0.018;
    return Math.max(0, base + wave1 + wave2);
  });
  drawWaveform(idleData);
  JARVIS.waveAnimFrame = requestAnimationFrame(animateIdle);
}

animateIdle();
window.animateIdle = animateIdle;
window.waveAnimFrame = 0;

// ══════════════════════════════════════════
//  HUD ORB — Sci-Fi Reactive Core
// ══════════════════════════════════════════

(function initHudOrb() {
  const canvas = document.getElementById('hud-orb-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const S = 400;
  canvas.width  = S;
  canvas.height = S;
  const CX = S / 2, CY = S / 2;

  let rotOuter  = 0;
  let rotMiddle = 0;
  let rotInner  = 0;
  let rotData   = 0;
  let animT     = 0;

  const dataLabels = [
    { ang: 0.3,  r: 155, text: '4.2', phase: 0   },
    { ang: 1.1,  r: 162, text: '42',  phase: 1.2 },
    { ang: 2.0,  r: 148, text: '6.2', phase: 2.4 },
    { ang: 2.9,  r: 160, text: '0.2', phase: 3.6 },
    { ang: 3.7,  r: 152, text: '7.8', phase: 0.8 },
    { ang: 4.6,  r: 158, text: '1.4', phase: 2.0 },
    { ang: 5.4,  r: 150, text: '3.6', phase: 4.0 },
    { ang: 6.0,  r: 164, text: '9.1', phase: 5.2 },
  ];

  function getAudioAmplitude() {
    if (!JARVIS.analyser) return 0;
    try {
      const data = new Uint8Array(JARVIS.analyser.frequencyBinCount);
      JARVIS.analyser.getByteFrequencyData(data);
      let sum = 0;
      for (let i = 0; i < data.length; i++) sum += data[i];
      return sum / data.length / 255;
    } catch(e) { return 0; }
  }

  function getSpectrumBands(count) {
    const bands = new Array(count).fill(0);
    if (!JARVIS.analyser) return bands;
    try {
      const data    = new Uint8Array(JARVIS.analyser.frequencyBinCount);
      JARVIS.analyser.getByteFrequencyData(data);
      const perBand = Math.floor(data.length / count);
      for (let i = 0; i < count; i++) {
        let sum = 0;
        for (let j = 0; j < perBand; j++) sum += data[i * perBand + j];
        bands[i] = sum / perBand / 255;
      }
    } catch(e) {}
    return bands;
  }

  function getPrimaryColor() {
    if (document.body.classList.contains('theme-friday')) return '244,114,182';
    return '0,229,255';
  }

  function getDimColor() {
    if (document.body.classList.contains('theme-friday')) return '219,39,119';
    return '0,153,204';
  }

  function drawSegmentedRing(cx, cy, radius, lineWidth, segments, gapAngle, rotation, alpha, color) {
    const segAngle = (Math.PI * 2 - segments * gapAngle) / segments;
    ctx.lineWidth = lineWidth;
    ctx.lineCap   = 'butt';
    for (let i = 0; i < segments; i++) {
      const start = rotation + i * (segAngle + gapAngle);
      const end   = start + segAngle;
      ctx.beginPath();
      ctx.arc(cx, cy, radius, start, end);
      ctx.strokeStyle = `rgba(${color},${alpha})`;
      ctx.stroke();
    }
  }

  function drawArrowArc(cx, cy, radius, startAngle, arcLength, rotation, lineWidth, alpha, color) {
    const start = rotation + startAngle;
    const end   = start + arcLength;
    ctx.lineWidth = lineWidth;
    ctx.lineCap   = 'round';
    ctx.beginPath();
    ctx.arc(cx, cy, radius, start, end);
    ctx.strokeStyle = `rgba(${color},${alpha})`;
    ctx.stroke();

    const ax = cx + Math.cos(end) * radius;
    const ay = cy + Math.sin(end) * radius;
    const headLen = 5;
    const headAng = end + Math.PI / 2;
    ctx.beginPath();
    ctx.moveTo(ax + Math.cos(headAng - 0.5) * headLen, ay + Math.sin(headAng - 0.5) * headLen);
    ctx.lineTo(ax, ay);
    ctx.lineTo(ax + Math.cos(headAng + 0.5) * headLen, ay + Math.sin(headAng + 0.5) * headLen);
    ctx.strokeStyle = `rgba(${color},${alpha})`;
    ctx.lineWidth   = lineWidth * 0.75;
    ctx.stroke();
  }

  function drawCrosshair(cx, cy, size, alpha, color) {
    ctx.lineWidth  = 0.5;
    ctx.strokeStyle = `rgba(${color},${alpha * 0.5})`;
    ctx.beginPath(); ctx.moveTo(cx - size, cy); ctx.lineTo(cx - 8, cy); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(cx + 8, cy);    ctx.lineTo(cx + size, cy); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(cx, cy - size); ctx.lineTo(cx, cy - 8); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(cx, cy + 8);    ctx.lineTo(cx, cy + size); ctx.stroke();
    ctx.lineWidth   = 0.7;
    ctx.beginPath();
    ctx.moveTo(cx, cy - 4);
    ctx.lineTo(cx + 4, cy);
    ctx.lineTo(cx, cy + 4);
    ctx.lineTo(cx - 4, cy);
    ctx.closePath();
    ctx.strokeStyle = `rgba(${color},${alpha * 0.4})`;
    ctx.stroke();
  }

  function draw() {
    animT += 0.016;
    ctx.clearRect(0, 0, S, S);

    const state    = JARVIS.state || 'idle';
    const speaking = state === 'speaking';
    const thinking = state === 'thinking';
    const amp      = speaking ? getAudioAmplitude() : 0;

    const speedMul = speaking ? 1.5 : thinking ? 1.25 : 1.0;
    rotOuter  += 0.003 * speedMul;
    rotMiddle -= 0.005 * speedMul;
    rotInner  += 0.008 * speedMul;
    rotData   += 0.001 * speedMul;

    const COL     = getPrimaryColor();
    const COL_DIM = getDimColor();

    // 1. Core glow
    const coreRadius = 30 + (speaking ? amp * 10 : 0);
    const corePulse  = 0.85 + Math.sin(animT * 2.5) * 0.15;
    const coreGlow   = ctx.createRadialGradient(CX, CY, 0, CX, CY, coreRadius * 2.5);
    coreGlow.addColorStop(0,   `rgba(220,245,255,${0.95 * corePulse})`);
    coreGlow.addColorStop(0.15,`rgba(${COL},${0.8 * corePulse})`);
    coreGlow.addColorStop(0.4, `rgba(${COL},${0.22 * corePulse})`);
    coreGlow.addColorStop(0.7, `rgba(${COL_DIM},${0.07 * corePulse})`);
    coreGlow.addColorStop(1,   'rgba(0,0,0,0)');
    ctx.beginPath();
    ctx.arc(CX, CY, coreRadius * 2.5, 0, Math.PI * 2);
    ctx.fillStyle = coreGlow;
    ctx.fill();

    const innerGlow = ctx.createRadialGradient(CX, CY, 0, CX, CY, coreRadius);
    innerGlow.addColorStop(0,   `rgba(255,255,255,${0.9 * corePulse})`);
    innerGlow.addColorStop(0.3, `rgba(210,248,255,${0.7 * corePulse})`);
    innerGlow.addColorStop(0.7, `rgba(${COL},${0.35 * corePulse})`);
    innerGlow.addColorStop(1,   'rgba(0,0,0,0)');
    ctx.beginPath();
    ctx.arc(CX, CY, coreRadius, 0, Math.PI * 2);
    ctx.fillStyle = innerGlow;
    ctx.fill();

    // 2. Crosshair
    drawCrosshair(CX, CY, 44, 0.45 + amp * 0.3, COL);

    // 3. Inner thin ring
    ctx.beginPath();
    ctx.arc(CX, CY, 52, 0, Math.PI * 2);
    ctx.strokeStyle = `rgba(${COL_DIM},0.2)`;
    ctx.lineWidth   = 0.5;
    ctx.stroke();

    // 4. Inner segmented ring
    drawSegmentedRing(CX, CY, 65, 1.5, 12, 0.08, rotInner, 0.5, COL);

    // 5. Middle segmented ring
    drawSegmentedRing(CX, CY, 85, 1.2, 16, 0.06, rotMiddle, 0.38, COL_DIM);

    // 6. Tick marks
    for (let i = 0; i < 36; i++) {
      const a      = rotMiddle + (i / 36) * Math.PI * 2;
      const inner  = 80;
      const outer  = i % 3 === 0 ? 92 : 87;
      ctx.beginPath();
      ctx.moveTo(CX + Math.cos(a) * inner, CY + Math.sin(a) * inner);
      ctx.lineTo(CX + Math.cos(a) * outer, CY + Math.sin(a) * outer);
      ctx.strokeStyle = `rgba(${COL},${i % 3 === 0 ? 0.38 : 0.13})`;
      ctx.lineWidth   = i % 3 === 0 ? 1.2 : 0.6;
      ctx.stroke();
    }

    // 7. Outer segmented ring
    drawSegmentedRing(CX, CY, 110, 2, 8, 0.12, rotOuter, 0.42, COL);

    // 8. Arrow arcs
    drawArrowArc(CX, CY, 125, 0,        0.7,  rotOuter,        2.5, 0.5,  COL);
    drawArrowArc(CX, CY, 125, Math.PI,  0.7,  rotOuter,        2.5, 0.5,  COL);
    drawArrowArc(CX, CY, 130, 0.5,      0.5, -rotOuter * 0.7,  1.8, 0.32, COL_DIM);
    drawArrowArc(CX, CY, 130, 3.6,      0.5, -rotOuter * 0.7,  1.8, 0.32, COL_DIM);
    drawArrowArc(CX, CY, 138, 1.2,      0.4,  rotOuter * 0.5,  1.5, 0.22, COL_DIM);
    drawArrowArc(CX, CY, 138, 4.3,      0.4,  rotOuter * 0.5,  1.5, 0.22, COL_DIM);

    // 9. Outermost thin ring
    drawSegmentedRing(CX, CY, 145, 0.5, 24, 0.04, -rotOuter * 0.3, 0.18, COL_DIM);

    // 10. Floating data labels
    ctx.font          = '9px monospace';
    ctx.textAlign     = 'center';
    ctx.textBaseline  = 'middle';
    dataLabels.forEach(d => {
      const a       = d.ang + rotData;
      const flicker = 0.35 + Math.sin(animT * 3 + d.phase) * 0.25;
      const x = CX + Math.cos(a) * d.r;
      const y = CY + Math.sin(a) * d.r;
      ctx.fillStyle = `rgba(${COL},${flicker})`;
      ctx.fillText(d.text, x, y);
    });

    // 11. Audio-reactive radial spectrum (when speaking)
    if (speaking) {
      const NUM_SPIKES = 64;
      const spectrum   = getSpectrumBands(NUM_SPIKES);
      const baseRadius = 148;

      for (let i = 0; i < NUM_SPIKES; i++) {
        const a   = (i / NUM_SPIKES) * Math.PI * 2 - Math.PI / 2;
        const val = spectrum[i];
        if (val < 0.02) continue;

        const spikeLen = val * 48 + 2;
        const x1 = CX + Math.cos(a) * baseRadius;
        const y1 = CY + Math.sin(a) * baseRadius;
        const x2 = CX + Math.cos(a) * (baseRadius + spikeLen);
        const y2 = CY + Math.sin(a) * (baseRadius + spikeLen);

        const sAlpha = Math.min(val * 2.5, 1);
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.strokeStyle = `rgba(${val > 0.5 ? '210,250,255' : COL},${sAlpha})`;
        ctx.lineWidth   = 1.4 + val * 1.8;
        ctx.lineCap     = 'round';
        ctx.stroke();

        if (val > 0.2) {
          ctx.beginPath();
          ctx.arc(x2, y2, val * 5, 0, Math.PI * 2);
          ctx.fillStyle = `rgba(${COL},${val * 0.35})`;
          ctx.fill();
        }
      }

      if (amp > 0.15) {
        const bloomGlow = ctx.createRadialGradient(CX, CY, 140, CX, CY, 195);
        bloomGlow.addColorStop(0, `rgba(${COL},${amp * 0.12})`);
        bloomGlow.addColorStop(1, 'rgba(0,0,0,0)');
        ctx.beginPath();
        ctx.arc(CX, CY, 195, 0, Math.PI * 2);
        ctx.fillStyle = bloomGlow;
        ctx.fill();
      }
    }

    // 12. Thinking pulse ring
    if (thinking) {
      const thinkPulse = 0.25 + Math.sin(animT * 4) * 0.18;
      ctx.beginPath();
      ctx.arc(CX, CY, 148, 0, Math.PI * 2);
      ctx.strokeStyle = `rgba(155,89,182,${thinkPulse})`;
      ctx.lineWidth   = 1.8;
      ctx.stroke();

      const haloR    = 154 + Math.sin(animT * 3) * 5;
      const haloGlow = ctx.createRadialGradient(CX, CY, 130, CX, CY, haloR + 15);
      haloGlow.addColorStop(0, 'rgba(155,89,182,0.07)');
      haloGlow.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.beginPath();
      ctx.arc(CX, CY, haloR + 15, 0, Math.PI * 2);
      ctx.fillStyle = haloGlow;
      ctx.fill();
    }

    requestAnimationFrame(draw);
  }

  draw();
})();

// ══════════════════════════════════════════
//  NEURAL BACKGROUND (disabled in Stark)
// ══════════════════════════════════════════

(function initNeuralBackground() {
  const canvas = document.getElementById('neural-bg-canvas');
  if (!canvas || canvas.style.display === 'none !important') return;
  const ctx   = canvas.getContext('2d');
  const panel = document.getElementById('core-panel');

  let W, H;

  function resize() {
    W = panel.offsetWidth  || 600;
    H = panel.offsetHeight || 500;
    canvas.width  = W;
    canvas.height = H;
  }

  resize();
  window.addEventListener('resize', resize);

  const N = 50;
  const nodes = Array.from({ length: N }, () => ({
    x: Math.random() * (W || 600),
    y: Math.random() * (H || 500),
    vx: (Math.random() - 0.5) * 0.22,
    vy: (Math.random() - 0.5) * 0.22,
    r:  1 + Math.random() * 1.8,
    firing: 0,
    pulse:  Math.random() * Math.PI * 2,
    pSpeed: 0.01 + Math.random() * 0.018,
  }));

  const DIST = 155;

  function getBgColor() {
    if (document.body.classList.contains('theme-friday')) return '244,114,182';
    const st = JARVIS.state;
    if (st === 'thinking') return '155,89,182';
    if (st === 'speaking') return '0,229,255';
    return '155,89,182';
  }

  function draw() {
    if (!canvas.offsetParent) { requestAnimationFrame(draw); return; }
    ctx.clearRect(0, 0, W, H);

    const speaking = JARVIS.state === 'speaking';
    const thinking = JARVIS.state === 'thinking';
    const speed    = speaking ? 1.8 : thinking ? 1.2 : 0.65;
    const fireRate = speaking ? 0.07 : thinking ? 0.04 : 0.01;
    const col      = getBgColor();

    panel.classList.toggle('nn-speaking', speaking);
    panel.classList.toggle('nn-thinking', thinking && !speaking);
    panel.classList.toggle('nn-idle',     !speaking && !thinking);

    nodes.forEach(n => {
      n.x += n.vx * speed;
      n.y += n.vy * speed;
      if (n.x < 0 || n.x > W) n.vx *= -1;
      if (n.y < 0 || n.y > H) n.vy *= -1;
      n.pulse  += n.pSpeed * (speaking ? 2 : 1);
      n.firing  = Math.max(0, n.firing - 0.04);
      if (Math.random() < fireRate) n.firing = 1;
    });

    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j];
        const dx = a.x - b.x, dy = a.y - b.y;
        const d  = Math.sqrt(dx*dx + dy*dy);
        if (d > DIST) continue;
        const s  = 1 - d / DIST;
        const fb = Math.max(a.firing, b.firing);
        const alpha = s * (speaking ? 0.16 : 0.08) + fb * 0.28;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.strokeStyle = `rgba(${col},${Math.min(alpha, 0.45)})`;
        ctx.lineWidth   = 0.4 + fb * 1.1;
        ctx.stroke();
      }
    }

    nodes.forEach(n => {
      const g = n.firing > 0 ? n.firing : (Math.sin(n.pulse) * 0.5 + 0.5) * 0.35;
      ctx.beginPath();
      ctx.arc(n.x, n.y, n.r * (1 + Math.sin(n.pulse) * 0.3), 0, Math.PI * 2);
      ctx.fillStyle = `rgba(${col},${0.25 + g * 0.5})`;
      ctx.fill();
    });

    requestAnimationFrame(draw);
  }

  draw();
})();

// ══════════════════════════════════════════
//  ORB REATIVO À EMOÇÃO — v2.3
//  Recebe evento 'emotion_detected' do backend
//  e transiciona cor/velocidade do Orb suavemente
// ══════════════════════════════════════════

(function initEmotionOrb() {
  let _currentEmotion = 'neutro';
  let _currentColor   = [0, 212, 255];
  let _transitionRAF  = null;

  const EMOTION_COLORS = {
    positivo:   [0,   255, 136],
    animado:    [255, 200,   0],
    neutro:     [0,   212, 255],
    curioso:    [160,  80, 255],
    focado:     [180, 220, 255],
    frustrado:  [255, 120,   0],
    irritado:   [255,  40,  60],
    triste:     [0,    80, 180],
    estressado: [255, 170,   0],
  };

  const EMOTION_LABELS = {
    positivo:'POSITIVO', animado:'ANIMADO', neutro:'ONLINE',
    curioso:'CURIOSO', focado:'FOCADO', frustrado:'FRUSTRADO',
    irritado:'ALERTA', triste:'REFLEXIVO', estressado:'ESTRESSADO',
  };

  function lerp(a, b, t) { return a + (b - a) * t; }
  function lerpColor(cur, tgt, t) { return tgt.map((v, i) => Math.round(lerp(cur[i], v, t))); }

  function applyOrbColor(rgb) {
    const [r, g, b] = rgb;
    document.documentElement.style.setProperty('--orb-emotion-color', `${r},${g},${b}`);
    document.documentElement.style.setProperty('--orb-emotion-rgb', `rgb(${r},${g},${b})`);
  }

  function transitionTo(targetRgb, ms = 800) {
    cancelAnimationFrame(_transitionRAF);
    const start = [..._currentColor];
    const t0    = performance.now();
    function step(now) {
      const t = Math.min(1, (now - t0) / ms);
      _currentColor = lerpColor(start, targetRgb, t);
      applyOrbColor(_currentColor);
      if (t < 1) _transitionRAF = requestAnimationFrame(step);
    }
    _transitionRAF = requestAnimationFrame(step);
  }

  function applyEmotion(data) {
    const emotion = data.emotion  || 'neutro';
    const color   = data.color    || EMOTION_COLORS['neutro'];
    const conf    = data.confidence || 0;
    if (emotion === _currentEmotion && conf < 0.6) return;
    _currentEmotion = emotion;
    transitionTo(color, 800);

    const statusEl = document.getElementById('assistant-status-display');
    if (statusEl && JARVIS.state === 'idle') {
      statusEl.textContent = EMOTION_LABELS[emotion] || 'ONLINE';
      setTimeout(() => { if (JARVIS.state === 'idle') statusEl.textContent = 'ONLINE'; }, 4000);
    }
    document.body.dataset.emotion = emotion;
  }

  function connect() {
    if (!JARVIS.socket) { setTimeout(connect, 500); return; }
    JARVIS.socket.on('emotion_detected', applyEmotion);
  }

  window.orbSetEmotion = applyEmotion;
  window.orbGetEmotion = () => _currentEmotion;
  connect();
  applyOrbColor(_currentColor);
})();