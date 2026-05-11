/* ═══════════════════════════════════════════════════════════════
   JARVIS OS — VOICE SYSTEM
   Microphone recording, VAD, clap detection, wake word
   ═══════════════════════════════════════════════════════════════ */

'use strict';

// ══════════════════════════════════════════
//  MICROPHONE RECORDING
// ══════════════════════════════════════════

let isRecording    = false;
let mediaRecorder  = null;
let audioChunks    = [];
let micStream      = null;
let isMicAnalysing = false;

window.isRecording = isRecording;

// micBtn declarado em app.js — usar getElementById inline

async function toggleRecording() {
  if (isRecording) { stopRecording(); return; }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
    });

    micStream  = stream;
    audioChunks = [];

    mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
    mediaRecorder.ondataavailable = e => {
      if (e.data.size > 0) audioChunks.push(e.data);
    };
    mediaRecorder.onstop = async () => {
      if (audioChunks.length > 0) {
        const blob = new Blob(audioChunks, { type: 'audio/webm' });
        await transcribeAudio(blob);
      } else {
        showToast('Nenhum áudio gravado', 'error');
        updateSystemStatus('SISTEMA ONLINE');
      }
      stream.getTracks().forEach(t => t.stop());
    };

    mediaRecorder.start(100);
    isRecording = true;
    window.isRecording = true;
    document.getElementById('mic-btn').classList.add('recording');
    showToast('Gravando...', 'success');

    // Live mic waveform
    initAudioContext();
    const micSource = JARVIS.audioContext.createMediaStreamSource(stream);
    micSource.connect(JARVIS.analyser);
    isMicAnalysing = true;

    cancelAnimationFrame(JARVIS.waveAnimFrame);
    const bufferLength = JARVIS.analyser.frequencyBinCount;
    const dataArray    = new Uint8Array(bufferLength);

    function drawMic() {
      if (!isMicAnalysing) return;
      JARVIS.analyser.getByteFrequencyData(dataArray);
      drawWaveform(Array.from(dataArray).map(v => v / 255));
      JARVIS.waveAnimFrame = requestAnimationFrame(drawMic);
    }

    drawMic();
    setTimeout(() => { if (isRecording) stopRecording(); }, 15000);

  } catch(err) {
    let msg = 'Microfone não acessível';
    if (err.name === 'NotAllowedError')  msg = 'Permissão de microfone negada';
    if (err.name === 'NotFoundError')    msg = 'Nenhum microfone encontrado';
    if (err.name === 'NotReadableError') msg = 'Microfone ocupado por outro programa';
    showToast(msg, 'error');
    updateSystemStatus('SISTEMA ONLINE');
  }
}

function stopRecording() {
  if (!isRecording) return;
  isRecording = false;
  window.isRecording = false;
  isMicAnalysing = false;
  document.getElementById('mic-btn').classList.remove('recording');
  mediaRecorder?.stop();
  cancelAnimationFrame(JARVIS.waveAnimFrame);
  animateIdle();
}

async function transcribeAudio(blob) {
  updateSystemStatus('TRANSCREVENDO...', 'processing');
  showToast('Processando áudio...', 'info');

  const formData = new FormData();
  formData.append('audio', blob, 'recording.webm');

  try {
    const res  = await fetch('/api/transcribe', { method: 'POST', body: formData });
    const data = await res.json();

    if (res.ok && data.text && data.text.trim()) {
      const transcribed = data.text.trim();
      document.getElementById('text-input').value = transcribed;
      showToast(`"${transcribed}"`, 'success');
      checkAndSend();
    } else {
      showToast(`${data.error || 'Não foi possível transcrever'}`, 'error');
      updateSystemStatus('SISTEMA ONLINE');
    }
  } catch(err) {
    showToast('Erro na transcrição', 'error');
    updateSystemStatus('SISTEMA ONLINE');
  }
}

window.toggleRecording = toggleRecording;
window.stopRecording   = stopRecording;

// ══════════════════════════════════════════
//  CLAP DETECTOR
// ══════════════════════════════════════════

const clapBtn = document.getElementById('clap-btn');
let clapListening = false;
let clapStream    = null;
let clapAudioCtx  = null;
let clapAnalyser  = null;
let clapRAF       = null;

let CLAP_THRESHOLD    = 0.35;
let CLAP_HF_THRESHOLD = 0.05;
const CLAP_MIN_INTERVAL = 120;
const CLAP_MAX_INTERVAL = 1200;
const CLAP_COOLDOWN     = 3000;

let lastClapTime    = 0;
let clapCount       = 0;
let lastTriggerTime = 0;
let maxPeakObserved = 0;

window.setClapThreshold  = (v) => { CLAP_THRESHOLD = v; };
window.setClapHF         = (v) => { CLAP_HF_THRESHOLD = v; };

async function toggleClapDetection() {
  if (clapListening) { stopClapDetection(); return; }

  try {
    clapStream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false }
    });

    clapAudioCtx  = new (window.AudioContext || window.webkitAudioContext)();
    const source  = clapAudioCtx.createMediaStreamSource(clapStream);
    clapAnalyser  = clapAudioCtx.createAnalyser();
    clapAnalyser.fftSize = 1024;
    clapAnalyser.smoothingTimeConstant = 0.1;
    source.connect(clapAnalyser);

    const timeData = new Uint8Array(clapAnalyser.fftSize);
    const freqData = new Uint8Array(clapAnalyser.frequencyBinCount);
    let lastVisualUpdate = 0;

    function detect() {
      if (!clapListening) return;

      clapAnalyser.getByteTimeDomainData(timeData);
      clapAnalyser.getByteFrequencyData(freqData);

      let peak = 0;
      for (let i = 0; i < timeData.length; i++) {
        const v = Math.abs(timeData[i] - 128) / 128;
        if (v > peak) peak = v;
      }

      let highFreqEnergy = 0;
      const startBin = 30;
      const endBin   = Math.min(240, freqData.length);
      for (let i = startBin; i < endBin; i++) highFreqEnergy += freqData[i];
      highFreqEnergy /= (endBin - startBin) * 255;

      const now = performance.now();

      if (now - lastVisualUpdate > 80) {
        lastVisualUpdate = now;
        const intensity = Math.min(1, peak * 1.5);
        if (clapBtn) {
          clapBtn.style.background = `rgba(255,170,0,${0.12 + intensity * 0.45})`;
          clapBtn.style.boxShadow  = `0 0 ${8 + intensity * 18}px rgba(255,170,0,${0.28 + intensity * 0.45})`;
        }
        if (peak > maxPeakObserved) maxPeakObserved = peak;
      }

      const isClap = peak > CLAP_THRESHOLD
                  && highFreqEnergy > CLAP_HF_THRESHOLD
                  && (now - lastClapTime)    > CLAP_MIN_INTERVAL
                  && (now - lastTriggerTime) > CLAP_COOLDOWN;

      if (isClap) {
        const interval = now - lastClapTime;
        lastClapTime = now;

        if (interval < CLAP_MAX_INTERVAL && clapCount > 0) {
          clapCount++;
        } else {
          clapCount = 1;
        }

        if (clapBtn) {
          clapBtn.style.background = 'rgba(255,170,0,0.85)';
          setTimeout(() => {
            if (clapListening && clapBtn) clapBtn.style.background = 'rgba(255,170,0,0.12)';
          }, 140);
        }

        showToast(`Palma ${clapCount}/2`, 'success');

        if (clapCount >= 2) {
          showToast('PROTOCOLO ATIVADO!', 'success');
          lastTriggerTime = now;
          clapCount = 0;
          JARVIS.socket.emit('clap_detected');
        }
      }

      if (clapCount > 0 && (now - lastClapTime) > CLAP_MAX_INTERVAL) {
        clapCount = 0;
      }

      clapRAF = requestAnimationFrame(detect);
    }

    clapListening = true;
    if (clapBtn) clapBtn.classList.add('listening');
    maxPeakObserved = 0;
    showToast('Detecção ativa — bata palmas duplas', 'success');
    detect();

  } catch(err) {
    let msg = 'Erro ao acessar microfone para palmas';
    if (err.name === 'NotAllowedError')  msg = 'Permissão de microfone negada';
    if (err.name === 'NotReadableError') msg = 'Microfone ocupado';
    showToast(msg, 'error');
  }
}

function stopClapDetection() {
  clapListening = false;
  if (clapBtn) {
    clapBtn.classList.remove('listening');
    clapBtn.style.background = '';
    clapBtn.style.boxShadow  = '';
  }
  cancelAnimationFrame(clapRAF);
  if (clapStream)   { clapStream.getTracks().forEach(t => t.stop()); clapStream = null; }
  if (clapAudioCtx) { clapAudioCtx.close(); clapAudioCtx = null; }
  clapCount = 0;
  showToast(`Desativado`, '');
}

// ══════════════════════════════════════════
//  VAD — VOICE ACTIVITY DETECTION
// ══════════════════════════════════════════

const vadBtn       = document.getElementById('vad-btn');
const vadIndicator = document.getElementById('vad-indicator');
const vadLevelBar  = document.getElementById('vad-level-bar');
const vadLevelFill = document.getElementById('vad-level-fill');

let vadActive          = false;
let vadStream          = null;
let vadAudioCtx        = null;
let vadAnalyser        = null;
let vadRAF             = null;
let vadRecorder        = null;
let vadChunks          = [];
let vadSpeaking        = false;
let vadSilenceTimer    = null;
let vadCalibrated      = false;
let vadNoiseFloor      = 0;
let vadThreshold       = 0;
let vadCalibSamples    = [];
let vadIsJarvisTalking = false;

let VAD_SILENCE_MS     = 1500;
let VAD_MIN_BLOB_BYTES = 6000;
let VAD_CALIB_MS       = 2500;
let VAD_MULTIPLIER     = 5.5;

window.setVadSilence    = v => { VAD_SILENCE_MS = v; };
window.setVadMultiplier = v => {
  VAD_MULTIPLIER = v;
  vadThreshold = Math.max(0.008, Math.min(0.15, vadNoiseFloor * v));
};

function setJarvisTalking(state) {
  vadIsJarvisTalking = state;
  if (state && vadSpeaking) cancelVadCapture();
}

window.setJarvisTalking = setJarvisTalking;

function cancelVadCapture() {
  clearTimeout(vadSilenceTimer);
  vadSilenceTimer = null;
  if (vadRecorder && vadRecorder.state !== 'inactive') {
    try { vadRecorder.stop(); } catch(e) {}
  }
  vadChunks   = [];
  vadSpeaking = false;
  if (vadBtn) {
    vadBtn.classList.remove('vad-speaking');
    if (vadActive) vadBtn.classList.add('vad-on');
  }
  setVadIndicator('listen');
}

async function toggleVAD() {
  if (vadActive) { stopVAD(); return; }
  await startVAD();
}

async function startVAD() {
  try {
    vadStream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
    });
    vadAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const source = vadAudioCtx.createMediaStreamSource(vadStream);
    vadAnalyser  = vadAudioCtx.createAnalyser();
    vadAnalyser.fftSize = 512;
    vadAnalyser.smoothingTimeConstant = 0.1;
    source.connect(vadAnalyser);

    vadCalibrated   = false;
    vadCalibSamples = [];
    vadNoiseFloor   = 0;
    vadThreshold    = 0;
    vadSpeaking     = false;
    vadChunks       = [];
    const calibStart = performance.now();

    vadActive = true;
    if (vadBtn) vadBtn.classList.add('vad-calibrating');
    if (vadIndicator) vadIndicator.classList.add('visible');
    if (vadLevelBar)  vadLevelBar.classList.add('visible');
    setVadIndicator('calib');
    showToast('Calibrando... fique em silêncio por 2s', 'success');

    const timeData = new Uint8Array(vadAnalyser.fftSize);

    function loop() {
      if (!vadActive) return;

      vadAnalyser.getByteTimeDomainData(timeData);
      let sum = 0;
      for (let i = 0; i < timeData.length; i++) {
        const v = (timeData[i] - 128) / 128;
        sum += v * v;
      }
      const rms = Math.sqrt(sum / timeData.length);

      const pct = Math.min(100, rms * 700);
      if (vadLevelFill) {
        vadLevelFill.style.height     = pct + '%';
        vadLevelFill.style.background = !vadCalibrated
          ? 'linear-gradient(to top, #00d4ff, #0088ff)'
          : (rms > vadThreshold
            ? 'linear-gradient(to top, #ff4444, #ffaa00)'
            : 'linear-gradient(to top, #00ff88, #00d4ff)');
      }

      const now = performance.now();

      if (!vadCalibrated) {
        vadCalibSamples.push(rms);
        if (now - calibStart >= VAD_CALIB_MS) {
          const sorted  = [...vadCalibSamples].sort((a,b) => a - b);
          vadNoiseFloor = sorted[Math.floor(sorted.length * 0.85)];
          vadThreshold  = Math.max(0.015, Math.min(0.20, vadNoiseFloor * VAD_MULTIPLIER));
          vadCalibrated = true;
          if (vadBtn) {
            vadBtn.classList.remove('vad-calibrating');
            vadBtn.classList.add('vad-on');
          }
          setVadIndicator('listen');
          showToast(`Pronto — fale normalmente! (th=${vadThreshold.toFixed(3)})`, 'success');
        }
        vadRAF = requestAnimationFrame(loop);
        return;
      }

      const isVoice = rms > vadThreshold;

      if (isVoice && !vadSpeaking && !vadIsJarvisTalking && !isRecording) {
        vadSpeaking = true;
        vadChunks   = [];
        clearTimeout(vadSilenceTimer);
        vadSilenceTimer = null;

        if (vadBtn) {
          vadBtn.classList.remove('vad-on');
          vadBtn.classList.add('vad-speaking');
        }

        setVadIndicator('active');

        try {
          vadRecorder = new MediaRecorder(vadStream, { mimeType: 'audio/webm' });
          vadRecorder.ondataavailable = e => { if (e.data.size > 0) vadChunks.push(e.data); };
          vadRecorder.onstop = () => { processVadAudio(); };
          vadRecorder.start(80);
        } catch(e) {
          vadSpeaking = false;
          if (vadBtn) {
            vadBtn.classList.remove('vad-speaking');
            vadBtn.classList.add('vad-on');
          }
        }
      }

      if (vadSpeaking) {
        if (!isVoice) {
          if (!vadSilenceTimer) {
            vadSilenceTimer = setTimeout(() => {
              if (!vadSpeaking) return;
              vadSpeaking     = false;
              vadSilenceTimer = null;
              if (vadRecorder && vadRecorder.state !== 'inactive') vadRecorder.stop();
              if (vadBtn) {
                vadBtn.classList.remove('vad-speaking');
                if (vadActive) vadBtn.classList.add('vad-on');
              }
              setVadIndicator('processing');
            }, VAD_SILENCE_MS);
          }
        } else {
          clearTimeout(vadSilenceTimer);
          vadSilenceTimer = null;
        }
      }

      vadRAF = requestAnimationFrame(loop);
    }

    loop();

  } catch(err) {
    vadActive = false;
    let msg = 'Erro ao acessar microfone';
    if (err.name === 'NotAllowedError')  msg = 'Permissão de microfone negada';
    if (err.name === 'NotReadableError') msg = 'Microfone ocupado';
    showToast(msg, 'error');
  }
}

async function processVadAudio() {
  if (vadChunks.length === 0) { setVadIndicator('listen'); return; }

  const blob = new Blob(vadChunks, { type: 'audio/webm' });
  vadChunks  = [];

  if (blob.size < VAD_MIN_BLOB_BYTES) {
    if (vadActive) setVadIndicator('listen');
    return;
  }

  setVadIndicator('processing');
  updateSystemStatus('TRANSCREVENDO...', 'processing');

  const formData = new FormData();
  formData.append('audio', blob, 'recording.webm');

  try {
    const res  = await fetch('/api/transcribe', { method: 'POST', body: formData });
    const data = await res.json();

    if (res.ok && data.text && data.text.trim()) {
      const text = data.text.trim();
      const artifacts = ['obrigado.','obrigada.','...','…','[música]','[aplausos]','[silencio]','subtitle','subtitles'];
      if (artifacts.some(a => text.toLowerCase().includes(a)) || text.length < 3) {
        updateSystemStatus('SISTEMA ONLINE');
        if (vadActive) setVadIndicator('listen');
        return;
      }

      addMessage('user', text);
      showToast(`"${text.length > 50 ? text.slice(0,50)+'…' : text}"`, 'success');
      setRingState('thinking');
      updateSystemStatus('PROCESSANDO...', 'processing');
      JARVIS.socket.emit('user_message', { text });
    } else {
      updateSystemStatus('SISTEMA ONLINE');
    }
  } catch(err) {
    updateSystemStatus('SISTEMA ONLINE');
  }

  if (vadActive) setVadIndicator('listen');
}

function stopVAD() {
  vadActive   = false;
  vadSpeaking = false;
  clearTimeout(vadSilenceTimer);
  vadSilenceTimer = null;
  cancelAnimationFrame(vadRAF);

  if (vadRecorder && vadRecorder.state !== 'inactive') {
    try { vadRecorder.stop(); } catch(e) {}
    vadChunks = [];
  }

  if (vadStream)   { vadStream.getTracks().forEach(t => t.stop()); vadStream = null; }
  if (vadAudioCtx) { vadAudioCtx.close(); vadAudioCtx = null; }

  if (vadBtn) vadBtn.classList.remove('vad-on','vad-speaking','vad-calibrating');
  if (vadIndicator) vadIndicator.classList.remove('visible','active','processing');
  if (vadLevelBar)  vadLevelBar.classList.remove('visible');

  updateSystemStatus('SISTEMA ONLINE');
  showToast('Modo conversação desativado', '');
}

function setVadIndicator(mode) {
  const span = document.getElementById('vad-text');
  if (vadIndicator) vadIndicator.classList.remove('active','processing');
  if (span) {
    if      (mode === 'calib')       span.textContent = 'CALIBRANDO MICROFONE...';
    else if (mode === 'listen')      span.textContent = 'ESCUTANDO...';
    else if (mode === 'active')    { if (vadIndicator) vadIndicator.classList.add('active');     span.textContent = 'CAPTANDO FALA...'; }
    else if (mode === 'processing'){ if (vadIndicator) vadIndicator.classList.add('processing'); span.textContent = 'PROCESSANDO...'; }
  }
}

// ══════════════════════════════════════════
//  WAKE WORD
// ══════════════════════════════════════════

let wakeWordActive  = false;
let wakeRecognition = null;
let wakeCommandMode = false;

const WAKE_WORDS = ['jarvis', 'jarves', 'jarwis', 'járvis', 'jávis'];

function toggleWakeWord() {
  if (wakeWordActive) { stopWakeWord(); return; }
  startWakeWord();
}

function startWakeWord() {
  if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
    showToast('Wake word não suportada. Use Chrome.', 'error');
    return;
  }

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  wakeRecognition = new SpeechRecognition();
  wakeRecognition.continuous       = true;
  wakeRecognition.interimResults   = true;
  wakeRecognition.lang             = 'pt-BR';
  wakeRecognition.maxAlternatives  = 3;

  wakeRecognition.onstart = () => { showWakeIndicator('AGUARDANDO "JARVIS"', false); };

  wakeRecognition.onresult = (event) => {
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const result = event.results[i];
      for (let j = 0; j < result.length; j++) {
        const transcript = result[j].transcript.toLowerCase().trim();

        if (!wakeCommandMode) {
          const detected = WAKE_WORDS.some(w => transcript.includes(w));
          if (detected) {
            wakeCommandMode = true;
            showWakeIndicator('OUVINDO COMANDO...', true);
            setRingState('thinking');
            const afterJarvis = extractAfterWakeWord(transcript);
            if (afterJarvis && afterJarvis.length > 3) {
              processWakeCommand(afterJarvis);
              return;
            }
          }
        } else {
          if (result.isFinal && transcript.length > 2) {
            const cmd = extractAfterWakeWord(transcript) || transcript;
            if (cmd.length > 2) { processWakeCommand(cmd); return; }
          }
        }
      }
    }
  };

  wakeRecognition.onerror = (e) => {
    if (e.error !== 'no-speech') console.warn('[WAKE]', e.error);
  };

  wakeRecognition.onend = () => {
    if (wakeWordActive) {
      setTimeout(() => { try { wakeRecognition.start(); } catch(e) {} }, 300);
    }
  };

  wakeWordActive = true;
  const wakeBtn = document.getElementById('wake-btn');
  if (wakeBtn) {
    wakeBtn.classList.add('active');
    const label = wakeBtn.querySelector('.sb-label');
    if (label) label.textContent = 'WAKE ON';
  }

  try {
    wakeRecognition.start();
    showToast('Wake word ativa — diga "Jarvis" para começar', 'success');
  } catch(e) {
    showToast('Erro ao iniciar wake word', 'error');
  }
}

function stopWakeWord() {
  wakeWordActive  = false;
  wakeCommandMode = false;
  if (wakeRecognition) {
    try { wakeRecognition.stop(); } catch(e) {}
    wakeRecognition = null;
  }
  hideWakeIndicator();
  const wakeBtn = document.getElementById('wake-btn');
  if (wakeBtn) {
    wakeBtn.classList.remove('active');
    const label = wakeBtn.querySelector('.sb-label');
    if (label) label.textContent = 'WAKE WORD';
  }
  showToast('Wake word desativada', '');
}

function extractAfterWakeWord(transcript) {
  for (const w of WAKE_WORDS) {
    const idx = transcript.indexOf(w);
    if (idx !== -1) {
      const after = transcript.slice(idx + w.length).trim().replace(/^[,.]\s*/, '');
      if (after.length > 2) return after;
    }
  }
  return null;
}

function processWakeCommand(command) {
  wakeCommandMode = false;
  showWakeIndicator('PROCESSANDO...', true);
  const textInput = document.getElementById('text-input');
  if (textInput) textInput.value = command;
  showToast(`"${command}"`, 'success');
  setTimeout(() => {
    checkAndSend();
    showWakeIndicator('AGUARDANDO "JARVIS"', false);
    setRingState('idle');
  }, 200);
}

function showWakeIndicator(text, isListening) {
  const el   = document.getElementById('wake-indicator');
  const dot  = document.getElementById('wake-dot');
  const span = document.getElementById('wake-text');
  if (!el) return;
  el.classList.add('visible');
  if (span) span.textContent = text;
  if (isListening) {
    el.classList.add('listening');
    if (dot) dot.classList.add('red');
  } else {
    el.classList.remove('listening');
    if (dot) dot.classList.remove('red');
  }
}

function hideWakeIndicator() {
  const el = document.getElementById('wake-indicator');
  if (el) el.classList.remove('visible','listening');
}

window.toggleWakeWord      = toggleWakeWord;
window.stopWakeWord        = stopWakeWord;
window.toggleRecording     = toggleRecording;
window.toggleClapDetection = toggleClapDetection;
window.toggleVAD           = toggleVAD;