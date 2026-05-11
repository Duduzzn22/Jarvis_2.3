/* ═══════════════════════════════════════════════════════════════
   JARVIS OS — PANELS MODULE
   Memory panel, Personality panel, Confirm overlay, Temporal lobe
   ═══════════════════════════════════════════════════════════════ */

// ─── MEMORY PANEL ───────────────────────────────────────────────
let currentTab = 'profile';
let memoryData = null;

function openMemoryPanel() {
  document.getElementById('memory-overlay').classList.add('open');
  refreshMemory();
}

function closeMemoryPanel(e) {
  if (!e || e.target === document.getElementById('memory-overlay') || !e.target) {
    document.getElementById('memory-overlay').classList.remove('open');
  }
}

function switchTab(tab, btn) {
  currentTab = tab;
  document.querySelectorAll('.mem-tab').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('tab-profile').style.display  = tab === 'profile'  ? '' : 'none';
  document.getElementById('tab-memories').style.display = tab === 'memories' ? '' : 'none';
  document.getElementById('tab-log').style.display      = tab === 'log'      ? '' : 'none';
}

async function refreshMemory() {
  try {
    const res = await fetch('/api/memory');
    memoryData = await res.json();
    renderProfile(memoryData.profile || {});
    renderMemories(memoryData.memories || []);
    renderLog(memoryData.recent_log || []);
  } catch(e) {
    console.error('[JARVIS] Erro ao carregar memória:', e);
  }
}

function renderProfile(profile) {
  const el = document.getElementById('tab-profile');
  const labels = {
    user_name:      'Nome',
    occupation:     'Ocupação',
    work_hours:     'Horário',
    os:             'Sistema',
    browser:        'Navegador',
    music_app:      'Música',
    response_style: 'Estilo',
    extra_info:     'Extra',
  };
  const keys = Object.keys(labels).filter(k => profile[k]);
  if (!keys.length) {
    el.innerHTML = `<p style="color:#446688;font-size:12px;text-align:center;padding:24px 0;">
      Nenhum perfil configurado.<br>
      <button onclick="closeMemoryPanel();openSetupWizard()" style="background:rgba(0,212,255,0.08);border:1px solid rgba(0,212,255,0.3);color:var(--c-primary);font-family:var(--font-mono);font-size:10px;padding:6px 14px;cursor:pointer;border-radius:2px;margin-top:8px;letter-spacing:1px;display:inline-block;">⚙ Abrir Setup Wizard</button>
    </p>`;
    return;
  }
  el.innerHTML = `
    <div class="mem-section-title">Dados cadastrados</div>
    <div class="profile-grid">
      ${keys.map(k => `
        <div class="profile-item">
          <div class="profile-item-label">${labels[k]}</div>
          <div class="profile-item-value">${profile[k]}</div>
        </div>
      `).join('')}
    </div>
    <div class="mem-section-title" style="margin-top:16px">Total de memórias: ${memoryData ? memoryData.total_memories : '—'}</div>
  `;
}

function renderMemories(memories) {
  const el = document.getElementById('tab-memories');
  if (!memories.length) {
    el.innerHTML = `<p style="color:#446688;font-size:12px;text-align:center;padding:24px 0;">
      Nenhuma memória aprendida ainda.<br>
      <span style="font-size:11px">Converse com o JARVIS para ele aprender sobre você.</span>
    </p>`;
    return;
  }
  el.innerHTML = `
    <div class="mem-section-title">O que o JARVIS lembra de você</div>
    ${memories.map(m => `
      <div class="memory-item">
        <span class="mem-cat ${m.category}">${m.category}</span>
        <span class="mem-content">${m.content}</span>
        <div class="mem-importance">
          ${[1,2,3].map(i => `<div class="imp-dot ${m.importance >= i ? 'lit' : ''}"></div>`).join('')}
        </div>
      </div>
    `).join('')}
  `;
}

function renderLog(log) {
  const el = document.getElementById('tab-log');
  if (!log.length) {
    el.innerHTML = `<p style="color:#446688;font-size:12px;text-align:center;padding:24px 0;">
      Nenhuma conversa registrada ainda.
    </p>`;
    return;
  }
  const reversed = [...log].reverse();
  el.innerHTML = `
    <div class="mem-section-title">Últimas interações</div>
    ${reversed.map(m => `
      <div class="log-item">
        <div class="log-role ${m.role}">${m.role === 'user' ? '[ SIR ]' : '[ J.A.R.V.I.S. ]'}</div>
        <div class="log-text">${m.content.slice(0, 120)}${m.content.length > 120 ? '…' : ''}</div>
      </div>
    `).join('')}
  `;
}

async function clearMemory() {
  if (!confirm('Apagar todas as memórias e histórico? O perfil será mantido.')) return;
  try {
    await fetch('/api/memory/clear', { method: 'POST' });
    window.showToast('✓ Memórias apagadas', 'success');
    refreshMemory();
  } catch(e) {
    window.showToast('✗ Erro ao apagar memórias', 'error');
  }
}

window.openMemoryPanel    = openMemoryPanel;
window.closeMemoryPanel   = closeMemoryPanel;
window.switchTab          = switchTab;
window.refreshMemory      = refreshMemory;
window.clearMemory        = clearMemory;

// ─── PERSONALITY PANEL ──────────────────────────────────────────
let personalitiesData = [];

async function openPersonalityPanel() {
  document.getElementById('personality-overlay').classList.add('open');
  await loadPersonalities();
}

function closePersonalityPanel(e) {
  if (!e || e.target === document.getElementById('personality-overlay') || !e.target) {
    document.getElementById('personality-overlay').classList.remove('open');
  }
}

async function loadPersonalities() {
  try {
    const res = await fetch('/api/personalities');
    personalitiesData = await res.json();
    renderPersonalityGrid();
  } catch(e) {
    console.error('[JARVIS] Erro ao carregar personalidades:', e);
  }
}

function renderPersonalityGrid() {
  const grid = document.getElementById('personality-grid');
  grid.innerHTML = personalitiesData.map(p => `
    <div class="personality-card ${p.active ? 'active' : ''}"
         style="--p-color:${p.color}"
         onclick="selectPersonality('${p.id}', '${p.name}', '${p.color}', '${p.accent}', '${p.emoji}')">
      <span class="p-emoji">${p.emoji}</span>
      <div class="p-info">
        <div class="p-name">${p.name}</div>
        <div class="p-desc">${p.description}</div>
        <div class="p-active-badge">● ATIVO</div>
      </div>
    </div>
  `).join('');
}

async function selectPersonality(id, name, color, accent, emoji) {
  try {
    const res = await fetch('/api/personality/set', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ personality: id }),
    });
    const data = await res.json();
    if (data.success) {
      applyPersonality(id, name, color, accent, emoji);
      closePersonalityPanel();
      window.showToast(`${emoji} Personalidade: ${name}`, 'success');
    }
  } catch(e) {
    window.showToast('✗ Erro ao trocar personalidade', 'error');
  }
}

function applyPersonality(id, name, color, accent, emoji) {
  const hudP = document.getElementById('hud-personality');
  if (hudP) { hudP.textContent = `${emoji} ${name.toUpperCase()}`; hudP.style.color = color; }

  const chipName = document.getElementById('mode-chip-name');
  const chipSub  = document.getElementById('mode-chip-sub');
  if (chipName) chipName.textContent = name.toUpperCase();
  if (chipSub)  chipSub.textContent  = `${emoji} ATIVO`;

  const nameDisp = document.getElementById('assistant-name-display');
  if (nameDisp) nameDisp.textContent = name.toUpperCase();

  const isFriday = id === 'friday' || name.toLowerCase().includes('sexta') || name.toLowerCase().includes('friday');
  document.body.classList.toggle('theme-friday', isFriday);

  if (!isFriday) {
    document.documentElement.style.setProperty('--cyan', color);
    document.documentElement.style.setProperty('--cyan-glow', accent);
    document.documentElement.style.setProperty('--c-primary', color);
    document.documentElement.style.setProperty('--c-primary-glow', accent);
  } else {
    document.documentElement.style.removeProperty('--cyan');
    document.documentElement.style.removeProperty('--cyan-glow');
    document.documentElement.style.removeProperty('--c-primary');
    document.documentElement.style.removeProperty('--c-primary-glow');
  }

  if (personalitiesData.length) {
    personalitiesData.forEach(p => p.active = p.id === id);
    renderPersonalityGrid();
  }
}

window.openPersonalityPanel  = openPersonalityPanel;
window.closePersonalityPanel = closePersonalityPanel;
window.selectPersonality     = selectPersonality;
window.applyPersonality      = applyPersonality;

setTimeout(loadPersonalities, 1000);

// ─── CONFIRMATION OVERLAY ───────────────────────────────────────
let confirmResolve  = null;
let confirmInterval = null;

const CONFIRM_ICONS = {
  open_app:      '⚡',
  send_telegram: '📡',
  send_whatsapp: '💬',
  manage_files:  '📁',
  default:       '⚠',
};

function showConfirm(action, detail, intent) {
  return new Promise(resolve => {
    confirmResolve = resolve;

    const icon = CONFIRM_ICONS[intent] || CONFIRM_ICONS.default;
    document.getElementById('confirm-icon').textContent       = icon;
    document.getElementById('confirm-action-text').textContent = action;
    document.getElementById('confirm-detail').textContent     = detail || 'Confirme para prosseguir.';
    document.getElementById('confirm-overlay').classList.add('open');

    let secs = 15;
    document.getElementById('confirm-sec').textContent = secs;
    const bar = document.getElementById('confirm-bar');
    bar.style.transition = 'none';
    bar.style.width = '100%';
    requestAnimationFrame(() => {
      bar.style.transition = `width ${secs}s linear`;
      bar.style.width = '0%';
    });

    clearInterval(confirmInterval);
    confirmInterval = setInterval(() => {
      secs--;
      document.getElementById('confirm-sec').textContent = secs;
      if (secs <= 0) respondConfirm(false);
    }, 1000);
  });
}

function respondConfirm(yes) {
  clearInterval(confirmInterval);
  document.getElementById('confirm-overlay').classList.remove('open');
  if (confirmResolve) {
    confirmResolve(yes);
    confirmResolve = null;
  }
}

window.showConfirm   = showConfirm;
window.respondConfirm = respondConfirm;

// ─── TEMPORAL LOBE PANEL ────────────────────────────────────────
let temporalCurrentTab = 'timeline';

function openTemporalPanel() {
  document.getElementById('temporal-overlay').classList.add('open');
  refreshTemporalTab();
}

function closeTemporalPanel(e) {
  if (!e || e.target === document.getElementById('temporal-overlay') || !e.target)
    document.getElementById('temporal-overlay').classList.remove('open');
}

function switchTemporalTab(tab, btn) {
  temporalCurrentTab = tab;
  document.querySelectorAll('.tl-tab').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  ['timeline','reminders','episodes','context'].forEach(t => {
    document.getElementById(`tl-tab-${t}`).style.display = t === tab ? '' : 'none';
  });
  refreshTemporalTab();
}

function refreshTemporalTab() {
  if      (temporalCurrentTab === 'timeline')  loadTimeline();
  else if (temporalCurrentTab === 'reminders') loadReminders();
  else if (temporalCurrentTab === 'episodes')  loadEpisodes();
  else if (temporalCurrentTab === 'context')   loadTemporalContext();
}

async function loadTimeline(period = 'hoje') {
  const el = document.getElementById('tl-tab-timeline');
  el.innerHTML = `
    <div style="display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap">
      ${['hoje','ontem','semana','mes'].map(p => `
        <button onclick="loadTimeline('${p}')" style="
          background:${period===p?'rgba(255,170,0,0.12)':'none'};
          border:1px solid ${period===p?'rgba(255,170,0,0.5)':'rgba(255,170,0,0.15)'};
          color:${period===p?'#ffaa00':'#664400'};
          font-family:var(--font-mono);font-size:9px;letter-spacing:1.5px;
          padding:4px 12px;cursor:pointer;border-radius:2px;text-transform:uppercase;
          transition:all 0.2s">${p}</button>
      `).join('')}
    </div>
    <div id="tl-loading" style="color:#554400;font-size:11px;padding:10px 0;">Carregando...</div>
  `;

  try {
    const res  = await fetch('/api/temporal/timeline?period=' + period);
    const data = await res.json();
    const log  = data.log  || [];
    const mems = data.memories || [];
    const lbl  = data.period_label || period;

    const loadingEl = document.getElementById('tl-loading');
    if (loadingEl) loadingEl.remove();

    if (!log.length && !mems.length) {
      el.insertAdjacentHTML('beforeend', `<div style="color:#554400;font-size:12px;text-align:center;padding:24px 0;">Sem registros para ${lbl}.</div>`);
      return;
    }

    let content = '';
    if (log.length) {
      content += `<div style="font-size:9px;color:#664400;letter-spacing:2px;text-transform:uppercase;margin-bottom:8px;padding-bottom:4px;border-bottom:1px solid rgba(255,170,0,0.08)">Conversas (${log.length})</div>`;
      content += log.slice(-15).map(e => `
        <div class="tl-item">
          <div class="tl-item-time">${e.timestamp ? new Date(e.timestamp).toLocaleTimeString('pt-BR') : ''} · ${e.role === 'user' ? 'Sir' : 'JARVIS'}</div>
          <div class="tl-item-content">${e.content.slice(0, 120)}${e.content.length > 120 ? '…' : ''}</div>
        </div>
      `).join('');
    }

    if (mems.length) {
      content += `<div style="font-size:9px;color:#664400;letter-spacing:2px;text-transform:uppercase;margin:14px 0 8px;padding-bottom:4px;border-bottom:1px solid rgba(255,170,0,0.08)">Memórias aprendidas (${mems.length})</div>`;
      content += mems.map(m => `
        <div class="tl-item">
          <div class="tl-item-time">${m.category}</div>
          <div class="tl-item-content">${m.content}</div>
        </div>
      `).join('');
    }

    el.insertAdjacentHTML('beforeend', content);
  } catch(e) {
    el.innerHTML = '<div style="color:#ff4444;font-size:11px;padding:20px 0;text-align:center;">Erro ao carregar timeline</div>';
  }
}

async function loadReminders() {
  const el = document.getElementById('tl-tab-reminders');
  const inputHtml = `
    <div style="display:flex;gap:8px;margin-bottom:14px">
      <input id="tl-reminder-input" type="text"
        placeholder="Ex: reunião amanhã às 15h..."
        style="flex:1;background:rgba(0,20,40,0.6);border:1px solid rgba(255,170,0,0.2);
               color:#ffaa00;font-family:var(--font-mono);font-size:11px;padding:7px 12px;
               border-radius:2px;outline:none;"
        onkeydown="if(event.key==='Enter') addReminderManual()"/>
      <button onclick="addReminderManual()" style="
        background:rgba(255,170,0,0.08);border:1px solid rgba(255,170,0,0.3);
        color:#ffaa00;font-family:var(--font-mono);font-size:10px;padding:7px 14px;
        cursor:pointer;border-radius:2px;letter-spacing:1px">+ ADD</button>
    </div>
  `;
  el.innerHTML = inputHtml + '<div id="tl-reminders-list"><div style="color:#554400;font-size:11px;padding:10px 0;">Carregando...</div></div>';

  try {
    const res  = await fetch('/api/temporal/reminders');
    const list = await res.json();
    const listEl = document.getElementById('tl-reminders-list');

    if (!list.length) {
      listEl.innerHTML = '<div style="color:#554400;font-size:12px;text-align:center;padding:20px 0;">Nenhum lembrete pendente.</div>';
      return;
    }

    listEl.innerHTML = list.map(r => {
      const dt = new Date(r.remind_at);
      const fmt = dt.toLocaleDateString('pt-BR') + ' ' + dt.toLocaleTimeString('pt-BR', {hour:'2-digit',minute:'2-digit'});
      return `
        <div class="tl-reminder" id="reminder-${r.id}">
          <div class="tl-reminder-time">${fmt}</div>
          <div class="tl-reminder-text">${r.content.slice(0, 120)}</div>
          <button class="tl-reminder-del" onclick="deleteReminder(${r.id})" title="Remover">✕</button>
        </div>
      `;
    }).join('');
  } catch(e) {
    document.getElementById('tl-reminders-list').innerHTML = '<div style="color:#ff4444;font-size:11px;">Erro ao carregar lembretes</div>';
  }
}

async function addReminderManual() {
  const inp = document.getElementById('tl-reminder-input');
  if (!inp || !inp.value.trim()) return;
  try {
    const res  = await fetch('/api/temporal/reminders/add', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({text: inp.value.trim()})
    });
    const data = await res.json();
    if (data.success) {
      inp.value = '';
      window.showToast(`⏱ Lembrete criado: ${data.reminder.remind_fmt}`, 'success');
      loadReminders();
    } else {
      window.showToast('Não consegui interpretar o lembrete, Sir.', 'error');
    }
  } catch(e) {
    window.showToast('Erro ao criar lembrete', 'error');
  }
}

async function deleteReminder(id) {
  await fetch('/api/temporal/reminders/delete', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({id})
  });
  const el = document.getElementById(`reminder-${id}`);
  if (el) el.remove();
  window.showToast('Lembrete removido', '');
}

async function loadEpisodes() {
  const el = document.getElementById('tl-tab-episodes');
  el.innerHTML = `
    <div style="display:flex;gap:6px;margin-bottom:12px">
      ${['todos','positivo','negativo','neutro'].map(m => `
        <button onclick="loadEpisodesByMood('${m}')" style="
          background:none;border:1px solid rgba(255,170,0,0.15);color:#664400;
          font-family:var(--font-mono);font-size:9px;letter-spacing:1px;
          padding:3px 10px;cursor:pointer;border-radius:2px;
          text-transform:uppercase;transition:all 0.2s">${m}</button>
      `).join('')}
    </div>
    <div id="tl-episodes-list"><div style="color:#554400;font-size:11px;padding:10px 0;">Carregando...</div></div>
  `;
  loadEpisodesByMood('todos');
}

async function loadEpisodesByMood(mood) {
  const listEl = document.getElementById('tl-episodes-list');
  if (!listEl) return;
  try {
    const url = '/api/temporal/episodes?limit=30' + (mood !== 'todos' ? '&mood=' + mood : '');
    const res  = await fetch(url);
    const eps  = await res.json();
    if (!eps.length) {
      listEl.innerHTML = '<div style="color:#554400;font-size:12px;text-align:center;padding:20px 0;">Nenhum episódio registrado ainda.</div>';
      return;
    }
    listEl.innerHTML = eps.map(e => `
      <div class="tl-item">
        <div class="tl-item-time">
          ${e.date_label} · ${e.created_at ? new Date(e.created_at).toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'}) : ''}
          <span class="tl-mood ${e.mood}">${e.mood}</span>
        </div>
        <div class="tl-item-content">${e.summary.slice(0,150)}${e.summary.length>150?'…':''}</div>
      </div>
    `).join('');
  } catch(err) {
    listEl.innerHTML = '<div style="color:#ff4444;font-size:11px;">Erro ao carregar episódios</div>';
  }
}

async function loadTemporalContext() {
  const el = document.getElementById('tl-tab-context');
  el.innerHTML = '<div style="color:#554400;font-size:11px;padding:10px 0;">Carregando...</div>';
  try {
    const tz  = -(new Date().getTimezoneOffset() / 60);
    const res = await fetch('/api/temporal/context?tz=' + tz);
    const ctx = await res.json();

    el.innerHTML = `
      <div class="tl-ctx-grid">
        <div class="tl-ctx-card">
          <span class="tl-ctx-value">${ctx.local_time}</span>
          <div class="tl-ctx-label">Hora Local</div>
        </div>
        <div class="tl-ctx-card">
          <span class="tl-ctx-value" style="font-size:12px">${ctx.period}</span>
          <div class="tl-ctx-label">Período</div>
        </div>
        <div class="tl-ctx-card">
          <span class="tl-ctx-value" style="font-size:11px;letter-spacing:0.5px">${ctx.weekday.split('-')[0]}</span>
          <div class="tl-ctx-label">Dia</div>
        </div>
      </div>
      ${ctx.is_holiday ? `
        <div style="padding:10px 12px;border:1px solid rgba(255,170,0,0.3);border-radius:3px;margin-bottom:12px;background:rgba(255,170,0,0.06);">
          <span style="color:#ffaa00;font-size:11px;letter-spacing:1px;">🎉 Feriado: ${ctx.holiday_name}</span>
        </div>` : ''}
      ${ctx.is_weekend ? `
        <div style="padding:8px 12px;border:1px solid rgba(255,170,0,0.15);border-radius:3px;margin-bottom:12px;">
          <span style="color:#cc8800;font-size:11px;">🌅 Fim de semana</span>
        </div>` : ''}
      ${ctx.suggestions.length ? `
        <div style="font-size:9px;color:#664400;letter-spacing:2px;text-transform:uppercase;margin-bottom:8px;">Sugestões Contextuais</div>
        ${ctx.suggestions.map(s => `
          <div style="padding:6px 0;border-bottom:1px solid rgba(255,170,0,0.06);font-size:11px;color:#aa8833;">→ ${s}</div>
        `).join('')}` : ''}
    `;
  } catch(e) {
    el.innerHTML = '<div style="color:#ff4444;font-size:11px;">Erro ao carregar contexto</div>';
  }
}

async function runDecayCleanup() {
  try {
    const res  = await fetch('/api/temporal/decay/run', { method: 'POST' });
    const data = await res.json();
    window.showToast(data.removed > 0 ? `⌛ ${data.removed} memórias expiradas removidas` : '⌛ Nenhuma memória expirada', data.removed > 0 ? 'success' : '');
  } catch(e) {
    window.showToast('Erro no decay cleanup', 'error');
  }
}

window.openTemporalPanel    = openTemporalPanel;
window.closeTemporalPanel   = closeTemporalPanel;
window.switchTemporalTab    = switchTemporalTab;
window.loadTimeline         = loadTimeline;
window.addReminderManual    = addReminderManual;
window.deleteReminder       = deleteReminder;
window.loadEpisodesByMood   = loadEpisodesByMood;
window.runDecayCleanup      = runDecayCleanup;

// ─── SOCKET EVENTS (panels) ─────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const socket = window.JARVIS?.socket;
  if (!socket) return;

  socket.on('personality_changed', data => {
    applyPersonality(data.id, data.name, data.color, data.accent, data.emoji);
    window.showToast(`${data.emoji} Personalidade: ${data.name}`, 'success');
  });

  socket.on('confirm_action', async data => {
    const ok = await showConfirm(data.action, data.detail, data.intent);
    socket.emit('confirm_response', { id: data.id, confirmed: ok });
    if (!ok) window.showToast('✕ Ação cancelada, Sir', 'error');
  });

  socket.on('jarvis_reminder', data => {
    if (data.audio_b64) {
      const audio = document.getElementById('tts-audio');
      audio.src = 'data:audio/mpeg;base64,' + data.audio_b64;
      audio.play().catch(() => {});
    }
    window.showToast(`⏱ Lembrete: ${data.text.slice(0,60)}`, 'success');
    const msgs = document.getElementById('chat-messages');
    const el = document.createElement('div');
    el.className = 'msg jarvis';
    el.innerHTML = `
      <div class="msg-label">[ LEMBRETE ]</div>
      <div class="tl-reminder-toast">${data.text}</div>
    `;
    msgs.appendChild(el);
    msgs.scrollTop = msgs.scrollHeight;
  });

  socket.on('temporal_reminder_created', data => {
    window.showToast(`⏱ Lembrete detectado: ${data.remind_fmt}`, 'success');
  });
});

// Keyboard close for all overlays
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    closeMemoryPanel();
    closePersonalityPanel();
    closeTemporalPanel();
  }
});
