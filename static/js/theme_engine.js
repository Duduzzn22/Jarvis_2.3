/* ═══════════════════════════════════════════════════════════════════════
   J.A.R.V.I.S. OS — THEME ENGINE v2.0
   Cinematic dual-theme switcher + Plugin/AI Model panel
   ═══════════════════════════════════════════════════════════════════════ */

'use strict';

// ─── THEME SYSTEM ────────────────────────────────────────────────────────────

const ThemeEngine = (() => {
  const STORAGE_KEY = 'jarvis_theme_v2';
  let _current = localStorage.getItem(STORAGE_KEY) || 'stark';
  let _switching = false;

  // Inject flash element once
  function _injectFlash() {
    if (document.getElementById('theme-flash')) return;
    const el = document.createElement('div');
    el.id = 'theme-flash';
    document.body.appendChild(el);
  }

  function current() { return _current; }
  function isFriday() { return _current === 'friday'; }

  function apply(theme, animate = false) {
    _current = theme;
    localStorage.setItem(STORAGE_KEY, theme);

    if (theme === 'friday') {
      document.body.classList.add('theme-friday');
    } else {
      document.body.classList.remove('theme-friday');
    }

    _updateSwitchBtn();
    _updateOrbColors(theme);
    _updateSidebarStatus(theme);
    _updateBootScreenTheme(theme);

    console.log(`[JARVIS] Theme: ${theme.toUpperCase()}`);
  }

  function toggle() {
    if (_switching) return;
    _switching = true;
    _injectFlash();

    const next      = _current === 'stark' ? 'friday' : 'stark';
    const flashEl   = document.getElementById('theme-flash');
    const flashClass = _current === 'stark' ? 'stark-to-friday' : 'friday-to-stark';

    // Play cinematic flash
    flashEl.className = flashClass;

    // Emit a subtle audio cue if Jarvis is online
    setTimeout(() => {
      apply(next, true);
      // Announce to Jarvis backend
      if (typeof socket !== 'undefined') {
        socket.emit('theme_change', { theme: next });
      }
    }, 150);

    setTimeout(() => {
      flashEl.className = '';
      _switching = false;
      PluginPanel.updateThemeLabel();
    }, 700);
  }

  function _updateSwitchBtn() {
    const btn   = document.getElementById('theme-switch-btn');
    const label = document.getElementById('theme-switch-label');
    const mode  = document.getElementById('theme-switch-mode');
    const icon  = document.getElementById('theme-switch-icon');
    if (!btn) return;

    if (_current === 'friday') {
      if (label) label.textContent = 'STARK MODE';
      if (mode)  mode.textContent  = 'MUDAR PARA HOLOGRÁFICO';
      if (icon)  icon.textContent  = '⚡';
    } else {
      if (label) label.textContent = 'FRIDAY MODE';
      if (mode)  mode.textContent  = 'MUDAR PARA ELEGANTE';
      if (icon)  icon.textContent  = '◐';
    }
  }

  function _updateOrbColors(theme) {
    // Signal to orb.js if it has a setTheme function
    if (typeof setOrbTheme === 'function') {
      setOrbTheme(theme);
      return;
    }
    // Fallback: update CSS vars directly
    const root = document.documentElement;
    if (theme === 'friday') {
      root.style.setProperty('--orb-primary', '#1a1a2e');
      root.style.setProperty('--orb-accent',  '#5865f2');
    } else {
      root.style.setProperty('--orb-primary', '#00e5ff');
      root.style.setProperty('--orb-accent',  '#80f2ff');
    }
  }

  function _updateSidebarStatus(theme) {
    // Update sidebar GROQ label
    const groqLabel = document.querySelector('#sb-status .sb-status-row:last-child span:last-child');
    if (groqLabel) {
      groqLabel.textContent = theme === 'friday' ? 'GROQ' : 'GROQ BACKUP';
    }
  }

  function _updateBootScreenTheme(theme) {
    const boot = document.getElementById('boot-screen');
    if (!boot) return;
    // Boot screen colors handled by CSS
  }

  // Init on load
  function init() {
    _injectFlash();
    apply(_current);
    setTimeout(_updateSwitchBtn, 100);
  }

  return { init, toggle, apply, current, isFriday };
})();


// ─── PLUGIN PANEL ────────────────────────────────────────────────────────────

const PluginPanel = (() => {
  let _open    = false;
  let _tab     = 'plugins';
  let _plugins = [];
  let _models  = [];
  let _monitor = { cpu: 0, ram: 0, uptime: 0, requests: 0, logs: [] };
  let _monitorInterval = null;

  // Built-in plugins definition
  const BUILTIN_PLUGINS = [
    { id: 'spotify',   name: 'SPOTIFY',        icon: '🎵', desc: 'Controle de músicas via API Spotify. Tocar, pausar, próxima faixa.', version: '2.1', active: true  },
    { id: 'sheets',    name: 'GOOGLE SHEETS',  icon: '📊', desc: 'Criação e edição de planilhas. Inserção NLP via voz.', version: '2.0', active: true  },
    { id: 'calendar',  name: 'GOOGLE CALENDAR',icon: '📅', desc: 'Agendamento de eventos e consulta de agenda.', version: '1.5', active: true  },
    { id: 'maps',      name: 'GOOGLE MAPS',    icon: '🗺️', desc: 'Navegação e busca de locais. Abertura do Maps.', version: '1.2', active: true  },
    { id: 'browser',   name: 'BROWSER SEARCH', icon: '🔍', desc: 'Pesquisas em tempo real. Futebol, clima, cotações.', version: '1.0', active: true  },
    { id: 'vision',    name: 'COMPUTER VISION',icon: '👁️', desc: 'Análise de screenshots e imagens em tempo real.', version: '1.8', active: true  },
    { id: 'instagram', name: 'INSTAGRAM',      icon: '📸', desc: 'Posts, stories e DMs via Instagrapi.', version: '1.1', active: false },
    { id: 'weather',   name: 'WEATHER',        icon: '🌤️', desc: 'Previsão do tempo por cidade. API OpenWeather.', version: '1.0', active: true  },
    { id: 'scheduler', name: 'SCHEDULER',      icon: '⏰', desc: 'Lembretes e tarefas agendadas automáticas.', version: '2.0', active: true  },
    { id: 'pc_agent',  name: 'PC AGENT',       icon: '🖥️', desc: 'Controle do computador via automação de desktop.', version: '1.3', active: true  },
    { id: 'trello',    name: 'TRELLO',         icon: '📋', desc: 'Gerenciamento de tarefas e boards.', version: '1.0', active: false },
    { id: 'nexus',     name: 'NEXUS CORE',     icon: '⬡',  desc: 'Motor de memória e contexto persistente.', version: '3.0', active: true  },
  ];

  // AI Models definition
  const AI_MODELS = [
    { id: 'groq-llama3-70b',  name: 'LLAMA 3.3 70B', provider: 'GROQ CLOUD', ctx: '128K', speed: '~600 t/s', status: 'online',  priority: 1, usage: 92 },
    { id: 'gemini-2-flash',   name: 'GEMINI 2 FLASH', provider: 'GOOGLE AI', ctx: '1M',   speed: '~400 t/s', status: 'online',  priority: 2, usage: 74 },
    { id: 'ollama-llama3',    name: 'LLAMA 3 LOCAL',  provider: 'OLLAMA',    ctx: '8K',   speed: '~25 t/s',  status: 'offline', priority: 3, usage: 0  },
    { id: 'groq-llama3-8b',   name: 'LLAMA 3.1 8B',   provider: 'GROQ FAST', ctx: '128K', speed: '~1200 t/s',status: 'online',  priority: 4, usage: 45 },
    { id: 'gemini-1-flash',   name: 'GEMINI 1.5 FLASH',provider: 'GOOGLE AI',ctx: '1M',   speed: '~300 t/s', status: 'online',  priority: 5, usage: 30 },
  ];

  function open() {
    if (_open) return;
    _open = true;

    const overlay = document.getElementById('plugin-overlay');
    const panel   = document.getElementById('plugin-panel');
    if (!overlay || !panel) { _buildDOM(); return open(); }

    overlay.classList.add('open');
    panel.classList.add('open');
    _render();
    _startMonitor();
  }

  function close() {
    if (!_open) return;
    _open = false;

    const overlay = document.getElementById('plugin-overlay');
    const panel   = document.getElementById('plugin-panel');
    if (overlay) overlay.classList.remove('open');
    if (panel) {
      panel.style.opacity = '0';
      panel.style.transform = 'translate(-50%, -50%) scale(0.96)';
      setTimeout(() => { panel.classList.remove('open'); panel.style.transform = ''; panel.style.opacity = ''; }, 300);
    }
    _stopMonitor();
  }

  function switchTab(id) {
    _tab = id;
    document.querySelectorAll('.plugin-tab').forEach(t => {
      t.classList.toggle('active', t.dataset.tab === id);
    });
    document.querySelectorAll('#plugin-panel-body > div').forEach(d => {
      d.classList.toggle('active', d.id === `${id}-tab`);
    });
    if (id === 'monitor') _renderMonitor();
    if (id === 'ai')      _renderAI();
    if (id === 'plugins') _renderPlugins();
  }

  function updateThemeLabel() {
    // Re-render if open
    if (_open) _render();
  }

  // ── DOM Builder ─────────────────────────────────────────────────────────
  function _buildDOM() {
    // Overlay
    if (!document.getElementById('plugin-overlay')) {
      const ov = document.createElement('div');
      ov.id = 'plugin-overlay';
      ov.onclick = close;
      document.body.appendChild(ov);
    }

    // Panel
    const existing = document.getElementById('plugin-panel');
    if (existing) existing.remove();

    const panel = document.createElement('div');
    panel.id    = 'plugin-panel';
    panel.innerHTML = `
      <div id="plugin-panel-header">
        <div class="plugin-panel-title">⬡ JARVIS SYSTEM CENTER</div>
        <button class="plugin-panel-close" onclick="PluginPanel.close()">✕ FECHAR</button>
      </div>
      <div id="plugin-panel-tabs">
        <button class="plugin-tab active" data-tab="plugins" onclick="PluginPanel.switchTab('plugins')">PLUGINS</button>
        <button class="plugin-tab" data-tab="ai"       onclick="PluginPanel.switchTab('ai')">MODELOS IA</button>
        <button class="plugin-tab" data-tab="monitor"  onclick="PluginPanel.switchTab('monitor')">MONITOR</button>
      </div>
      <div id="plugin-panel-body">
        <div id="plugins-tab" class="active"></div>
        <div id="ai-tab"></div>
        <div id="monitor-tab"></div>
      </div>
    `;
    document.body.appendChild(panel);
    _render();
  }

  // ── Renderers ────────────────────────────────────────────────────────────
  function _render() {
    if (_tab === 'plugins') _renderPlugins();
    if (_tab === 'ai')      _renderAI();
    if (_tab === 'monitor') _renderMonitor();
  }

  function _renderPlugins() {
    const container = document.getElementById('plugins-tab');
    if (!container) return;
    container.innerHTML = `
      <div class="plugin-grid">
        ${BUILTIN_PLUGINS.map(p => `
          <div class="plugin-card" id="plugin-card-${p.id}">
            <div class="plugin-card-header">
              <span class="plugin-icon">${p.icon}</span>
              <button class="plugin-toggle ${p.active ? 'on' : ''}"
                      onclick="PluginPanel.togglePlugin('${p.id}')"
                      title="${p.active ? 'Desativar' : 'Ativar'}"></button>
            </div>
            <div class="plugin-name">${p.name}</div>
            <div class="plugin-desc">${p.desc}</div>
            <div class="plugin-meta">
              <span class="plugin-version">v${p.version}</span>
              <span class="plugin-status-dot ${p.active ? 'on' : ''}"></span>
            </div>
          </div>
        `).join('')}
      </div>
    `;
  }

  function _renderAI() {
    const container = document.getElementById('ai-tab');
    if (!container) return;
    const active = AI_MODELS[0];
    container.innerHTML = `
      <div class="ai-status-section">
        <span class="ai-status-dot online"></span>
        MODELO ATIVO: ${active.name} — ${active.provider}
        <span style="margin-left:auto;opacity:0.5;">${active.speed}</span>
      </div>
      <div class="ai-model-grid">
        ${AI_MODELS.map((m, i) => `
          <div class="ai-model-card ${i === 0 ? 'active' : ''}"
               onclick="PluginPanel.selectModel('${m.id}')">
            <div class="ai-model-name">${m.name}</div>
            <div class="ai-model-provider">${m.provider}</div>
            <div class="ai-model-stats">
              <div class="ai-model-stat">
                <span class="ai-model-stat-label">CONTEXTO</span>
                <span class="ai-model-stat-value">${m.ctx}</span>
              </div>
              <div class="ai-model-stat">
                <span class="ai-model-stat-label">VELOCIDADE</span>
                <span class="ai-model-stat-value">${m.speed}</span>
              </div>
              <div class="ai-model-stat">
                <span class="ai-model-stat-label">STATUS</span>
                <span class="ai-model-stat-value" style="color:${m.status==='online'?'var(--c-green,#00ff88)':'var(--c-red,#ff4444)'}">
                  ${m.status.toUpperCase()}
                </span>
              </div>
              <div class="ai-model-stat">
                <span class="ai-model-stat-label">PRIORIDADE</span>
                <span class="ai-model-stat-value">#${m.priority}</span>
              </div>
            </div>
            <div class="ai-model-bar">
              <div class="ai-model-bar-fill" style="width:${m.usage}%"></div>
            </div>
          </div>
        `).join('')}
      </div>
    `;
  }

  function _renderMonitor() {
    const container = document.getElementById('monitor-tab');
    if (!container) return;
    const upMin = Math.floor(_monitor.uptime / 60);
    const upSec = _monitor.uptime % 60;

    const cpuClass = _monitor.cpu > 80 ? 'crit' : _monitor.cpu > 60 ? 'warn' : '';
    const ramClass = _monitor.ram > 80 ? 'crit' : _monitor.ram > 60 ? 'warn' : '';

    container.innerHTML = `
      <div class="monitor-grid">
        <div class="monitor-card">
          <div class="monitor-card-label">CPU</div>
          <div class="monitor-card-value" id="mon-cpu">${_monitor.cpu}%</div>
          <div class="monitor-card-sub">Processo Jarvis</div>
          <div class="monitor-bar"><div class="monitor-bar-fill ${cpuClass}" id="mon-cpu-bar" style="width:${_monitor.cpu}%"></div></div>
        </div>
        <div class="monitor-card">
          <div class="monitor-card-label">RAM</div>
          <div class="monitor-card-value" id="mon-ram">${_monitor.ram}%</div>
          <div class="monitor-card-sub">Memória utilizada</div>
          <div class="monitor-bar"><div class="monitor-bar-fill ${ramClass}" id="mon-ram-bar" style="width:${_monitor.ram}%"></div></div>
        </div>
        <div class="monitor-card">
          <div class="monitor-card-label">UPTIME</div>
          <div class="monitor-card-value" id="mon-uptime">${String(upMin).padStart(2,'0')}:${String(upSec).padStart(2,'0')}</div>
          <div class="monitor-card-sub">Sessão atual</div>
        </div>
        <div class="monitor-card">
          <div class="monitor-card-label">REQUESTS</div>
          <div class="monitor-card-value" id="mon-req">${_monitor.requests}</div>
          <div class="monitor-card-sub">Total desta sessão</div>
        </div>
        <div class="monitor-card">
          <div class="monitor-card-label">PLUGINS ATIVOS</div>
          <div class="monitor-card-value">${BUILTIN_PLUGINS.filter(p=>p.active).length}</div>
          <div class="monitor-card-sub">de ${BUILTIN_PLUGINS.length} instalados</div>
        </div>
        <div class="monitor-card">
          <div class="monitor-card-label">TEMA ATIVO</div>
          <div class="monitor-card-value" style="font-size:14px;">${ThemeEngine.current().toUpperCase()}</div>
          <div class="monitor-card-sub">Interface mode</div>
        </div>
      </div>

      <div class="monitor-card-label" style="margin-bottom:8px;">LOG DE EVENTOS</div>
      <div class="event-log" id="monitor-event-log">
        ${_monitor.logs.slice(-20).reverse().map(l => `
          <div class="event-log-entry">
            <span class="event-time">${l.time}</span>
            <span class="event-type">${l.type}</span>
            <span class="event-msg">${l.msg}</span>
          </div>
        `).join('') || '<div style="color:var(--c-text-dim);padding:8px 0;font-size:9px;">Sem eventos registrados.</div>'}
      </div>
    `;
  }

  // ── Actions ──────────────────────────────────────────────────────────────
  function togglePlugin(id) {
    const plugin = BUILTIN_PLUGINS.find(p => p.id === id);
    if (!plugin) return;
    plugin.active = !plugin.active;
    _renderPlugins();
    _addLog('PLUGIN', `${plugin.name} ${plugin.active ? 'ATIVADO' : 'DESATIVADO'}`);
    if (typeof showToast === 'function') {
      showToast(`${plugin.icon} ${plugin.name}: ${plugin.active ? 'Ativado' : 'Desativado'}`, plugin.active ? 'success' : 'info');
    }
    if (typeof socket !== 'undefined') {
      socket.emit('plugin_toggle', { id, active: plugin.active });
    }
  }

  function selectModel(id) {
    // Visual feedback only — actual routing done by backend
    document.querySelectorAll('.ai-model-card').forEach(c => c.classList.remove('active'));
    const card = document.querySelector(`.ai-model-card[onclick*="${id}"]`);
    if (card) card.classList.add('active');
    if (typeof showToast === 'function') {
      const m = AI_MODELS.find(m => m.id === id);
      if (m) showToast(`⚡ Modelo: ${m.name}`, 'info');
    }
  }

  // ── Monitor polling ───────────────────────────────────────────────────────
  function _startMonitor() {
    _monitor.uptime = 0;
    _pollStats();
    _monitorInterval = setInterval(() => {
      _monitor.uptime++;
      _pollStats();
    }, 2000);
  }

  function _stopMonitor() {
    if (_monitorInterval) { clearInterval(_monitorInterval); _monitorInterval = null; }
  }

  async function _pollStats() {
    try {
      const res = await fetch('/api/system_stats');
      if (res.ok) {
        const data = await res.json();
        _monitor.cpu      = Math.round(data.cpu      || 0);
        _monitor.ram      = Math.round(data.ram      || 0);
        _monitor.requests = data.requests || _monitor.requests;
      }
    } catch (_) {
      // Simulate stats if endpoint doesn't exist
      _monitor.cpu = Math.round(15 + Math.random() * 20);
      _monitor.ram = Math.round(35 + Math.random() * 15);
    }

    if (_open && _tab === 'monitor') {
      _updateMonitorDOM();
    }
  }

  function _updateMonitorDOM() {
    const cpuEl = document.getElementById('mon-cpu');
    const ramEl = document.getElementById('mon-ram');
    const reqEl = document.getElementById('mon-req');
    const upEl  = document.getElementById('mon-uptime');
    const upMin = Math.floor(_monitor.uptime / 60);
    const upSec = _monitor.uptime % 60;

    if (cpuEl) cpuEl.textContent = `${_monitor.cpu}%`;
    if (ramEl) ramEl.textContent = `${_monitor.ram}%`;
    if (reqEl) reqEl.textContent = _monitor.requests;
    if (upEl)  upEl.textContent  = `${String(upMin).padStart(2,'0')}:${String(upSec).padStart(2,'0')}`;

    const cpuBar = document.getElementById('mon-cpu-bar');
    const ramBar = document.getElementById('mon-ram-bar');
    if (cpuBar) { cpuBar.style.width = `${_monitor.cpu}%`; cpuBar.className = `monitor-bar-fill ${_monitor.cpu>80?'crit':_monitor.cpu>60?'warn':''}`; }
    if (ramBar) { ramBar.style.width = `${_monitor.ram}%`; ramBar.className = `monitor-bar-fill ${_monitor.ram>80?'crit':_monitor.ram>60?'warn':''}`; }
  }

  function _addLog(type, msg) {
    const now  = new Date();
    const time = `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}:${String(now.getSeconds()).padStart(2,'0')}`;
    _monitor.logs.push({ time, type, msg });
    if (_monitor.logs.length > 100) _monitor.logs.shift();
  }

  // Public logger — can be called by other modules
  function log(type, msg) { _addLog(type, msg); }

  // Socket integration — listen for backend events
  function _setupSocketListeners() {
    if (typeof socket === 'undefined') {
      setTimeout(_setupSocketListeners, 1000);
      return;
    }
    socket.on('plugin_event', data => {
      _addLog(data.type || 'EVENT', data.msg || '');
      _monitor.requests++;
    });
    socket.on('jarvis_response', () => { _monitor.requests++; });
  }

  _setupSocketListeners();

  return { open, close, switchTab, togglePlugin, selectModel, updateThemeLabel, log };
})();


// ─── SIDEBAR BUTTON INJECTION ────────────────────────────────────────────────

function _injectThemeSwitcher() {
  const nav = document.getElementById('sb-nav');
  if (!nav || document.getElementById('theme-switch-btn')) return;

  // Theme switcher button at bottom of nav
  const btn = document.createElement('button');
  btn.id        = 'theme-switch-btn';
  btn.className = 'floating-btn';
  btn.onclick   = () => ThemeEngine.toggle();
  btn.title     = 'Alternar tema Stark / Friday';
  btn.innerHTML = `
    <span class="theme-switch-icon" id="theme-switch-icon">◐</span>
    <span class="sb-label" id="theme-switch-label">FRIDAY MODE</span>
  `;

  // Plugin panel button
  const pluginBtn = document.createElement('button');
  pluginBtn.id        = 'plugin-panel-btn';
  pluginBtn.className = 'floating-btn';
  pluginBtn.onclick   = () => PluginPanel.open();
  pluginBtn.title     = 'System Center — Plugins & IA';
  pluginBtn.innerHTML = `
    <svg class="sb-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
      <rect x="2" y="3" width="6" height="6" rx="1"/>
      <rect x="9" y="3" width="6" height="6" rx="1"/>
      <rect x="16" y="3" width="6" height="6" rx="1"/>
      <rect x="2" y="12" width="6" height="6" rx="1"/>
      <rect x="9" y="12" width="6" height="6" rx="1"/>
      <rect x="16" y="12" width="6" height="6" rx="1"/>
      <rect x="5" y="18" width="14" height="3" rx="1"/>
    </svg>
    <span class="sb-label">SYSTEM CENTER</span>
    <span class="sb-badge"></span>
  `;

  // Insert a separator before
  const sep = document.createElement('div');
  sep.className = 'sb-group-label';
  sep.textContent = 'INTERFACE';

  nav.appendChild(sep);
  nav.appendChild(pluginBtn);
  nav.appendChild(btn);
}


// ─── INIT ─────────────────────────────────────────────────────────────────────

window.ThemeEngine  = ThemeEngine;
window.PluginPanel  = PluginPanel;

// Boot when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', _boot);
} else {
  _boot();
}

function _boot() {
  ThemeEngine.init();
  _injectThemeSwitcher();

  // Keyboard shortcut: Ctrl+Shift+T = toggle theme
  document.addEventListener('keydown', e => {
    if (e.ctrlKey && e.shiftKey && e.key === 'T') { e.preventDefault(); ThemeEngine.toggle(); }
    if (e.ctrlKey && e.shiftKey && e.key === 'P') { e.preventDefault(); PluginPanel.open(); }
    if (e.key === 'Escape' && PluginPanel) { PluginPanel.close(); }
  });

  console.log('[JARVIS] Theme Engine v2.0 ONLINE');
}