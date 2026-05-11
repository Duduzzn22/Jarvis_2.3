/* ═══════════════════════════════════════════════════════════════
   JARVIS OS — CORE APPLICATION
   Socket, boot, clock, state management, utilities
   ═══════════════════════════════════════════════════════════════ */

'use strict';

// ── Global Namespace ──
window.JARVIS = {
  socket:       null,
  state:        'idle',       // idle | thinking | speaking | listening
  analyser:     null,
  audioContext: null,
  waveAnimFrame: null,
  ttsMediaSource: null,
  isJarvisTalking: false,
};

// ── DOM references ──
const chatMessages  = document.getElementById('chat-messages');
const textInput     = document.getElementById('text-input');
const sendBtn       = document.getElementById('send-btn');
const micBtn        = document.getElementById('mic-btn');
const systemStatus  = document.getElementById('system-status');
const ringsContainer= document.getElementById('rings-container');
const ttsAudio      = document.getElementById('tts-audio');
const clockEl       = document.getElementById('clock');
const dotGroq       = document.getElementById('dot-groq');
const dotCerebras   = document.getElementById('dot-cerebras');

// ── Socket Initialization ──
const socket = io();
JARVIS.socket = socket;

// ══════════════════════════════════════════
//  BOOT SEQUENCE
// ══════════════════════════════════════════

(function bootSequence() {
  const lines = [0,1,2,3,4,5,6];
  lines.forEach((i, idx) => {
    setTimeout(() => {
      const el = document.getElementById(`b${i}`);
      if (el) el.classList.add('visible');
    }, idx * 350);
  });

  setTimeout(() => {
    const fill = document.getElementById('boot-fill');
    if (fill) fill.style.width = '100%';
  }, 150);

  setTimeout(() => {
    document.getElementById('boot-screen').classList.add('fade-out');
    const main = document.getElementById('main-interface');
    main.style.display = 'flex';
    setTimeout(() => main.classList.add('visible'), 50);

    setTimeout(() => {
      const params = new URLSearchParams(window.location.search);
      if (params.get('wake') === '1') {
        socket.emit('wake_word_greeting');
        window.history.replaceState({}, document.title, '/');
      } else {
        socket.emit('greeting_request');
      }
    }, 600);
  }, 3200);
})();

// ══════════════════════════════════════════
//  AUDIO AUTOPLAY
// ══════════════════════════════════════════

let audioEnabled = false;

function enableAudio() {
  if (audioEnabled) return;
  audioEnabled = true;
  document.removeEventListener('click', enableAudio);
  document.removeEventListener('keydown', enableAudio);
}

document.addEventListener('click', enableAudio);
document.addEventListener('keydown', enableAudio);

// ══════════════════════════════════════════
//  AUDIO CONTEXT
// ══════════════════════════════════════════

function initAudioContext() {
  if (!JARVIS.audioContext) {
    JARVIS.audioContext = new (window.AudioContext || window.webkitAudioContext)();
    JARVIS.analyser = JARVIS.audioContext.createAnalyser();
    JARVIS.analyser.fftSize = 128;
  }
  // aliases for legacy code
  window.audioContext = JARVIS.audioContext;
  window.analyser     = JARVIS.analyser;
}

function initTTSAudio() {
  initAudioContext();
  if (!JARVIS.ttsMediaSource) {
    JARVIS.ttsMediaSource = JARVIS.audioContext.createMediaElementSource(ttsAudio);
    JARVIS.ttsMediaSource.connect(JARVIS.analyser);
    JARVIS.analyser.connect(JARVIS.audioContext.destination);
  }
}

// ══════════════════════════════════════════
//  ORB / RING STATE
// ══════════════════════════════════════════

function setRingState(state) {
  JARVIS.state = state;
  window.currentJarvisState = state;
  ringsContainer.className = '';
  if (state !== 'idle') ringsContainer.classList.add(state);

  const statusEl = document.getElementById('assistant-status-display');
  if (statusEl) {
    const labels = {
      idle:     'ONLINE',
      speaking: 'TRANSMITINDO...',
      thinking: 'PROCESSANDO...',
      listening:'OUVINDO...',
    };
    statusEl.textContent = labels[state] || 'ONLINE';
  }
}

// expose globally for legacy canvas code
window.currentJarvisState = 'idle';
window.setRingState = setRingState;

// ══════════════════════════════════════════
//  CHAT SYSTEM
// ══════════════════════════════════════════

function addMessage(type, text) {
  const msg = document.createElement('div');
  msg.className = `msg ${type}`;

  const label = document.createElement('div');
  label.className = 'msg-label';
  const labels = { user:'[ SIR ]', jarvis:'[ J.A.R.V.I.S. ]', status:'[ SYS ]' };
  label.textContent = labels[type] || `[ ${type.toUpperCase()} ]`;

  const textEl = document.createElement('div');
  textEl.className = 'msg-text';

  msg.appendChild(label);
  msg.appendChild(textEl);
  chatMessages.appendChild(msg);
  chatMessages.scrollTop = chatMessages.scrollHeight;

  if (type === 'jarvis') {
    textEl.classList.add('typing-cursor');
    let i = 0;
    const interval = setInterval(() => {
      if (i < text.length) {
        textEl.textContent += text[i++];
        chatMessages.scrollTop = chatMessages.scrollHeight;
      } else {
        textEl.classList.remove('typing-cursor');
        clearInterval(interval);
      }
    }, 16);
  } else {
    textEl.textContent = text;
  }

  return msg;
}

window.addMessage = addMessage;

function updateSystemStatus(text, cls = '') {
  if (!systemStatus) return;
  systemStatus.className = cls;
  systemStatus.textContent = text;
}

window.updateSystemStatus = updateSystemStatus;

// ══════════════════════════════════════════
//  TOAST SYSTEM
// ══════════════════════════════════════════

function showToast(text, type = '') {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = text;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.animation = 'toastOut 0.3s ease forwards';
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

window.showToast = showToast;

// ══════════════════════════════════════════
//  SEND MESSAGE
// ══════════════════════════════════════════

function sendMessage() {
  const text = textInput.value.trim();
  if (!text) return;
  addMessage('user', text);
  textInput.value = '';
  setRingState('thinking');
  updateSystemStatus('PROCESSANDO...', 'processing');
  socket.emit('user_message', { text });
}

window.sendMessage = sendMessage;

// ══════════════════════════════════════════
//  FILE UPLOAD (Images, PDF, TXT, XLSX)
// ══════════════════════════════════════════

let selectedFile = null;

// File type icons
const FILE_ICONS = {
  'pdf': '📄', 'txt': '📝', 'csv': '📋', 'md': '📝', 'log': '📋',
  'xlsx': '📊', 'xls': '📊',
  'jpg': '🖼️', 'jpeg': '🖼️', 'png': '🖼️', 'gif': '🖼️', 'webp': '🖼️', 'bmp': '🖼️',
};

function getFileIcon(filename) {
  const ext = filename.split('.').pop().toLowerCase();
  return FILE_ICONS[ext] || '📎';
}

function isImageFile(filename) {
  const ext = filename.split('.').pop().toLowerCase();
  return ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp'].includes(ext);
}

function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / 1048576).toFixed(1) + ' MB';
}

function handleFileSelect(event) {
  const file = event.target.files[0];
  if (!file) return;
  attachFile(file);
}

function attachFile(file) {
  selectedFile = file;
  const previewWrap = document.getElementById('image-preview-wrap');
  const previewImg = document.getElementById('image-preview');
  const previewName = document.getElementById('image-preview-name');

  if (isImageFile(file.name)) {
    const url = URL.createObjectURL(file);
    previewImg.src = url;
    previewImg.style.display = 'block';
  } else {
    previewImg.style.display = 'none';
    previewImg.src = '';
  }

  const icon = getFileIcon(file.name);
  const size = formatFileSize(file.size);
  previewName.innerHTML = `${icon} <strong>${file.name}</strong> <span style="opacity:0.5">(${size})</span>`;
  previewWrap.classList.add('visible');
  showToast(`${icon} ${file.name} anexado`, 'success');
}

function clearFileUpload() {
  selectedFile = null;
  const fileInput = document.getElementById('file-input');
  if (fileInput) fileInput.value = '';
  document.getElementById('image-preview').src = '';
  document.getElementById('image-preview').style.display = 'block';
  document.getElementById('image-preview-name').textContent = '';
  document.getElementById('image-preview-wrap').classList.remove('visible');
}

async function sendFileForAnalysis(file, query = '') {
  const formData = new FormData();
  const isImg = isImageFile(file.name);

  if (isImg) {
    formData.append('image', file);
  } else {
    formData.append('file', file);
  }
  formData.append('query', query || '');
  formData.append('sid', socket.id || '');

  // Show in chat
  const msgDiv = document.createElement('div');
  msgDiv.className = 'msg user';
  const icon = getFileIcon(file.name);
  const size = formatFileSize(file.size);

  if (isImg) {
    const imgUrl = URL.createObjectURL(file);
    msgDiv.innerHTML = `
      <div class="msg-label">[ SIR ]</div>
      <div class="msg-text">
        <img src="${imgUrl}" class="msg-image" alt="imagem"/>
        <span style="font-size:10px;color:rgba(60,100,130,0.7)">${query || 'ANALISAR IMAGEM'}</span>
      </div>`;
  } else {
    msgDiv.innerHTML = `
      <div class="msg-label">[ SIR ]</div>
      <div class="msg-text">
        <div class="msg-file-card">
          <span class="msg-file-icon">${icon}</span>
          <div class="msg-file-info">
            <strong>${file.name}</strong>
            <small>${size}</small>
          </div>
        </div>
        ${query ? `<span style="font-size:10px;color:rgba(60,100,130,0.7)">${query}</span>` : ''}
      </div>`;
  }
  chatMessages.appendChild(msgDiv);
  chatMessages.scrollTop = chatMessages.scrollHeight;

  setRingState('thinking');
  updateSystemStatus('ANALISANDO ARQUIVO...', 'processing');

  try {
    const endpoint = isImg ? '/api/analyze_image' : '/api/analyze_file';
    const res  = await fetch(endpoint, { method: 'POST', body: formData });
    const data = await res.json();

    if (data.success && data.text) {
      addMessage('jarvis', data.text);
      updateSystemStatus('SISTEMA ONLINE');
      setRingState('speaking');

      if (data.audio_b64) {
        await playTTSAudio(`data:audio/mpeg;base64,${data.audio_b64}`);
      } else {
        setTimeout(() => setRingState('idle'), 2000);
      }
    } else {
      showToast('Erro ao analisar arquivo', 'error');
      updateSystemStatus('SISTEMA ONLINE');
      setRingState('idle');
    }
  } catch(e) {
    showToast('Falha na conexão', 'error');
    updateSystemStatus('SISTEMA ONLINE');
    setRingState('idle');
  }

  clearFileUpload();
}

function checkAndSend() {
  if (selectedFile) {
    const query = textInput.value.trim() || '';
    textInput.value = '';
    sendFileForAnalysis(selectedFile, query);
    return;
  }
  sendMessage();
}

// ── Drag & Drop ──
const chatPanel = document.getElementById('chat-panel');
const dropOverlay = document.getElementById('drop-overlay');
let dragCounter = 0;

chatPanel.addEventListener('dragenter', (e) => {
  e.preventDefault();
  dragCounter++;
  dropOverlay.classList.add('visible');
});

chatPanel.addEventListener('dragover', (e) => {
  e.preventDefault();
  e.dataTransfer.dropEffect = 'copy';
});

chatPanel.addEventListener('dragleave', (e) => {
  e.preventDefault();
  dragCounter--;
  if (dragCounter <= 0) {
    dragCounter = 0;
    dropOverlay.classList.remove('visible');
  }
});

chatPanel.addEventListener('drop', (e) => {
  e.preventDefault();
  dragCounter = 0;
  dropOverlay.classList.remove('visible');

  const files = e.dataTransfer.files;
  if (files.length > 0) {
    attachFile(files[0]);
    showToast('Arquivo anexado — pressione Enter para enviar', 'success');
  }
});

// Also handle paste (Ctrl+V images)
document.addEventListener('paste', (e) => {
  const items = e.clipboardData?.items;
  if (!items) return;
  for (const item of items) {
    if (item.type.startsWith('image/')) {
      e.preventDefault();
      const file = item.getAsFile();
      if (file) attachFile(file);
      break;
    }
  }
});

// Legacy aliases
window.handleImageSelect  = handleFileSelect;
window.clearImageUpload   = clearFileUpload;
window.handleFileSelect   = handleFileSelect;
window.clearFileUpload    = clearFileUpload;
window.checkAndSend       = checkAndSend;

// ══════════════════════════════════════════
//  TTS AUDIO PLAYBACK
// ══════════════════════════════════════════

async function playTTSAudio(src) {
  ttsAudio.src = src;
  try {
    initTTSAudio();
    if (JARVIS.audioContext.state === 'suspended') {
      await JARVIS.audioContext.resume();
    }
    if (typeof setJarvisTalking === 'function') setJarvisTalking(true);
    await ttsAudio.play();

    // Drive waveform from TTS audio
    cancelAnimationFrame(JARVIS.waveAnimFrame);
    const dataArray = new Uint8Array(JARVIS.analyser.frequencyBinCount);

    function drawTTS() {
      JARVIS.analyser.getByteFrequencyData(dataArray);
      if (typeof drawWaveform === 'function') {
        drawWaveform(Array.from(dataArray).map(v => v / 255));
      }
      JARVIS.waveAnimFrame = requestAnimationFrame(drawTTS);
    }

    drawTTS();

    ttsAudio.onended = () => {
      cancelAnimationFrame(JARVIS.waveAnimFrame);
      if (typeof animateIdle === 'function') animateIdle();
      setRingState('idle');
      setTimeout(() => {
        if (typeof setJarvisTalking === 'function') setJarvisTalking(false);
      }, 600);
    };

  } catch(error) {
    showToast('Clique para ativar áudio', 'info');
    const retry = async () => {
      try {
        initTTSAudio();
        if (JARVIS.audioContext.state === 'suspended') await JARVIS.audioContext.resume();
        if (typeof setJarvisTalking === 'function') setJarvisTalking(true);
        await ttsAudio.play();
      } catch(e) {}
      document.removeEventListener('click', retry);
    };
    document.addEventListener('click', retry);
  }
}

// ══════════════════════════════════════════
//  SOCKET EVENTS
// ══════════════════════════════════════════

socket.on('connect', () => {
  if (dotCerebras) dotCerebras.classList.add('active');
});

socket.on('disconnect', () => {
  if (dotCerebras) dotCerebras.classList.remove('active');
  if (dotGroq)     dotGroq.classList.remove('active');
  updateSystemStatus('DESCONECTADO', 'error');
});

socket.on('status_update', data => {
  const stepMap = {
    thinking:  ['ANALISANDO...', 'processing'],
    executing: ['EXECUTANDO COMANDO...', 'executing'],
    speaking:  ['SINTETIZANDO VOZ...', 'processing'],
  };
  const [label, cls] = stepMap[data.step] || [data.message, 'processing'];
  updateSystemStatus(label, cls);

  if (data.step === 'executing' && data.message) {
    addMessage('status', `▸ ${data.message}`);
  }
});

socket.on('jarvis_response', data => {
  addMessage('jarvis', data.text);
  updateSystemStatus('SISTEMA ONLINE');
  setRingState('speaking');

  if (data.audio_b64) {
    playTTSAudio(`data:audio/mpeg;base64,${data.audio_b64}`);
  } else {
    setTimeout(() => setRingState('idle'), 3000);
  }

  // API indicator updates
  if (dotCerebras) dotCerebras.classList.remove('active');
  if (dotGroq)     dotGroq.classList.remove('active');

  const sbDotOllama = document.getElementById('sb-dot-ollama');
  const sbDotGroq   = document.getElementById('sb-dot-groq');
  const sbDotEl     = document.getElementById('sb-dot-el');

  if (sbDotOllama) sbDotOllama.className = 'sb-status-dot';
  if (sbDotGroq)   sbDotGroq.className   = 'sb-status-dot';

  if (data.api_used) {
    if (data.api_used.startsWith('ollama')) {
      if (sbDotOllama) sbDotOllama.classList.add('on');
    } else if (data.api_used.startsWith('groq')) {
      if (dotGroq)     dotGroq.classList.add('active');
      if (sbDotOllama) sbDotOllama.classList.add('warn');
      if (sbDotGroq)   sbDotGroq.classList.add('on');
    } else if (data.api_used.startsWith('gemini')) {
      if (sbDotOllama) sbDotOllama.classList.add('warn');
    }
  }

  if (sbDotEl) sbDotEl.classList.toggle('on', !!data.audio_b64);
});

socket.on('action_result', data => {
  showToast(`${data.success ? '✓' : '✗'} ${data.message}`, data.success ? 'success' : 'error');
});

socket.on('error', data => {
  showToast(`${data.message}`, 'error');
  updateSystemStatus('SISTEMA ONLINE');
  setRingState('idle');
});

socket.on('profile_loaded', profile => {
  if (profile && profile.user_name) {
    const hudName = document.getElementById('hud-username');
    if (hudName) {
      hudName.textContent = `SENHOR ${profile.user_name.toUpperCase()}`;
      hudName.style.display = 'inline';
    }
  }
});

// Thinking streaming
socket.on('jarvis_thinking', data => {
  const el = document.createElement('div');
  el.className = 'msg thinking';
  el.innerHTML = `
    <div class="msg-label">[ PROCESSANDO ]</div>
    <div class="thinking-text">↳ ${data.text}</div>
  `;
  chatMessages.appendChild(el);
  chatMessages.scrollTop = chatMessages.scrollHeight;
});

// Neural reflection flag
socket.on('jarvis_response', data => {
  if (data.intent === 'neural_reflection') {
    const msg = document.querySelector('.msg.jarvis:last-child');
    if (msg) msg.classList.add('reflection');
  }
});

// ══════════════════════════════════════════
//  INPUT CONTROLS
// ══════════════════════════════════════════

textInput.addEventListener('keydown', e => {
  if (e.key === 'Enter') checkAndSend();
});

// Space hold = mic
let spaceTimer;
window.addEventListener('keydown', e => {
  if (e.code === 'Space' && document.activeElement !== textInput) {
    e.preventDefault();
    if (!spaceTimer) {
      spaceTimer = setTimeout(() => {
        if (typeof toggleRecording === 'function' && !window.isRecording) {
          toggleRecording();
        }
      }, 500);
    }
  }
});

window.addEventListener('keyup', e => {
  if (e.code === 'Space') {
    clearTimeout(spaceTimer);
    spaceTimer = null;
    if (window.isRecording && typeof stopRecording === 'function') stopRecording();
  }
});

// Escape closes all panels
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    if (typeof closeMemoryPanel    === 'function') closeMemoryPanel();
    if (typeof closePersonalityPanel === 'function') closePersonalityPanel();
    if (typeof closeTemporalPanel  === 'function') closeTemporalPanel();
    if (typeof closeNexusPanel     === 'function') closeNexusPanel();
  }
});

// ══════════════════════════════════════════
//  CLOCK
// ══════════════════════════════════════════

function updateClock() {
  if (!clockEl) return;
  const now = new Date();
  clockEl.textContent = [
    String(now.getHours()).padStart(2,'0'),
    String(now.getMinutes()).padStart(2,'0'),
    String(now.getSeconds()).padStart(2,'0'),
  ].join(':');
}

updateClock();
setInterval(updateClock, 1000);

// ══════════════════════════════════════════
//  THINKING TOGGLE
// ══════════════════════════════════════════

async function toggleThinking() {
  try {
    const res   = await fetch('/api/neural/thinking');
    const state = await res.json();
    const newVal = !state.enabled;
    await fetch('/api/neural/thinking', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ enabled: newVal }),
    });
    showToast(newVal ? 'Thinking Visible ativado' : 'Thinking Visible desativado', newVal ? 'success' : '');
    updateThinkingBtn(newVal);
  } catch(e) {}
}

function updateThinkingBtn(enabled) {
  const btn = document.getElementById('thinking-btn');
  if (!btn) return;
  if (enabled) {
    btn.classList.add('active');
  } else {
    btn.classList.remove('active');
  }
}

window.toggleThinking  = toggleThinking;
window.updateThinkingBtn = updateThinkingBtn;

// Load initial thinking state
(async () => {
  try {
    const res   = await fetch('/api/neural/thinking');
    const state = await res.json();
    updateThinkingBtn(state.enabled);
  } catch(e) {}
})();

// ── Load personalities on start ──
setTimeout(() => {
  if (typeof loadPersonalities === 'function') loadPersonalities();
}, 800);

// ══════════════════════════════════════════
//  EVENTOS v2.3 — Pomodoro, Wake Word, Briefing
// ══════════════════════════════════════════

// ── Pomodoro update ──
socket.on('pomodoro_update', data => {
  const state    = data.state    || 'idle';
  const remaining = data.remaining_seconds || 0;
  const done     = data.pomodoros_done || 0;
  const pct      = data.progress_pct  || 0;

  // Atualiza HUD badge se existir
  const badge = document.getElementById('pomodoro-badge');
  if (badge) {
    if (state === 'idle') {
      badge.style.display = 'none';
    } else {
      badge.style.display = 'inline-flex';
      const mins = String(Math.floor(remaining / 60)).padStart(2, '0');
      const secs = String(remaining % 60).padStart(2, '0');
      badge.textContent = `🍅 ${mins}:${secs}`;

      const colors = {
        working:     '#00ff88',
        short_break: '#00d4ff',
        long_break:  '#a855f7',
        paused:      '#fbbf24',
      };
      badge.style.color = colors[state] || '#fff';
    }
  }

  // Emite toast nas transições de estado
  const stateToasts = {
    short_break: '☕ Pausa curta iniciada!',
    long_break:  '🎉 Pausa longa — você merece!',
    working:     '🎯 Foco iniciado!',
  };
  if (stateToasts[state] && data._transition) {
    showToast(stateToasts[state], 'success');
  }
});

// ── Wake Word detectada ──
socket.on('wake_word_detected', data => {
  showToast('🎙 Hey Jarvis! Ouvindo...', 'success');
  updateSystemStatus('WAKE WORD ATIVADA', 'processing');
  setRingState('listening');
  setTimeout(() => {
    updateSystemStatus('SISTEMA ONLINE');
    setRingState('idle');
  }, 3000);
  console.log('[WAKE WORD] Detectada:', data.text);
});

// Atalho global para pedir briefing
window.requestBriefing = () => socket.emit('briefing_request');

// Atalho global para Pomodoro
window.pomodoroCmd = (cmd) => socket.emit('pomodoro_command', { command: cmd });