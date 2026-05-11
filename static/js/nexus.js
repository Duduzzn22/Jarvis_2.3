/* ═══════════════════════════════════════════════════════════════
   JARVIS OS — NEXUS MODULE
   Dashboard, Plugins, Health, Sync
   ═══════════════════════════════════════════════════════════════ */

let nexusCurrentTab = 'dashboard';

function openNexusPanel() {
  document.getElementById('nexus-overlay').classList.add('open');
  refreshNexus();
}

function closeNexusPanel(e) {
  if (!e || e.target === document.getElementById('nexus-overlay') || !e.target) {
    document.getElementById('nexus-overlay').classList.remove('open');
  }
}

function switchNexusTab(tab, btn) {
  nexusCurrentTab = tab;
  document.querySelectorAll('.nx-tab').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  ['dashboard','plugins','health','sync'].forEach(t => {
    document.getElementById(`nx-tab-${t}`).style.display = t === tab ? '' : 'none';
  });
  refreshNexusTab(tab);
}

async function refreshNexus() {
  refreshNexusTab(nexusCurrentTab);
}

async function refreshNexusTab(tab) {
  if      (tab === 'dashboard') await loadNexusDashboard();
  else if (tab === 'plugins')   await loadNexusPlugins();
  else if (tab === 'health')    await loadNexusHealth();
  else if (tab === 'sync')      renderNexusSync();
}

// ─── Dashboard ──────────────────────────────────────────────────
function clampUsagePct(value) {
  const pct = Number(value);
  if (!Number.isFinite(pct)) return 0;
  return Math.min(100, Math.max(0, Math.round(pct)));
}

function getUsageClass(value) {
  const pct = clampUsagePct(value);
  if (pct >= 85) return 'danger';
  if (pct >= 70) return 'warn';
  return '';
}

async function loadNexusDashboard() {
  const el = document.getElementById('nx-tab-dashboard');
  el.innerHTML = '<div style="color:#223344;font-size:11px;padding:20px 0;text-align:center;">Carregando...</div>';
  try {
    const res = await fetch('/api/nexus/dashboard');
    const d   = await res.json();
    const cpuPct = clampUsagePct(d.cpu_pct);
    const ramPct = clampUsagePct(d.ram_pct);

    const overallColor = { healthy:'#00ff88', partial:'#ffaa00', degraded:'#ff4444', warning:'#ffaa00' };
    const overallLabel = { healthy:'OPERACIONAL', partial:'PARCIAL', degraded:'DEGRADADO', warning:'ATENÇÃO' };
    const oc = overallColor[d.overall] || '#446688';

    const badge = document.getElementById('nexus-overall-badge');
    if (badge) {
      badge.style.color = oc;
      badge.textContent = `● ${overallLabel[d.overall] || d.overall.toUpperCase()}`;
    }

    const aiStatus = [];
    if (d.ai_available?.cerebras) aiStatus.push('<span class="nx-badge ok">CEREBRAS</span>');
    else aiStatus.push('<span class="nx-badge off">CEREBRAS</span>');
    if (d.ai_available?.groq) aiStatus.push('<span class="nx-badge ok">GROQ</span>');
    else aiStatus.push('<span class="nx-badge off">GROQ</span>');

    el.innerHTML = `
      <div class="nx-stat-grid">
        <div class="nx-stat usage ${getUsageClass(cpuPct)}">
          <div class="nx-usage-head">
            <div class="nx-stat-label" style="margin-top:0">CPU</div>
            <span class="nx-stat-value">${cpuPct}%</span>
          </div>
          <div class="nx-usage-bar" aria-label="Uso de CPU ${cpuPct}%">
            <div class="nx-usage-fill" style="width:${cpuPct}%"></div>
          </div>
        </div>
        <div class="nx-stat usage ${getUsageClass(ramPct)}">
          <div class="nx-usage-head">
            <div class="nx-stat-label" style="margin-top:0">RAM</div>
            <span class="nx-stat-value">${ramPct}%</span>
          </div>
          <div class="nx-usage-bar" aria-label="Uso de RAM ${ramPct}%">
            <div class="nx-usage-fill" style="width:${ramPct}%"></div>
          </div>
        </div>
        <div class="nx-stat">
          <span class="nx-stat-value">${d.total_memories}</span>
          <div class="nx-stat-label">Memórias</div>
        </div>
        <div class="nx-stat">
          <span class="nx-stat-value">${d.scheduled_tasks}</span>
          <div class="nx-stat-label">Tarefas</div>
        </div>
        <div class="nx-stat">
          <span class="nx-stat-value">${d.active_plugins}</span>
          <div class="nx-stat-label">Plugins</div>
        </div>
        <div class="nx-stat">
          <span class="nx-stat-value" style="font-size:13px">${d.uptime}</span>
          <div class="nx-stat-label">Uptime</div>
        </div>
      </div>

      <div class="nx-section-title">Sistema</div>
      <div class="nx-row">
        <span class="nx-row-label">Usuário</span>
        <span class="nx-row-value">${d.user_name}</span>
      </div>
      <div class="nx-row">
        <span class="nx-row-label">Personalidade</span>
        <span class="nx-row-value" style="color:${d.personality.color}">${d.personality.name}</span>
      </div>
      <div class="nx-row">
        <span class="nx-row-label">Motores IA</span>
        <span style="display:flex;gap:6px">${aiStatus.join('')}</span>
      </div>
      <div class="nx-row">
        <span class="nx-row-label">Interações log</span>
        <span class="nx-row-value">${d.log_count} recentes</span>
      </div>
      <div class="nx-row">
        <span class="nx-row-label">Timestamp</span>
        <span class="nx-row-value" style="font-size:9px">${new Date(d.timestamp).toLocaleTimeString('pt-BR')}</span>
      </div>
    `;
  } catch(e) {
    el.innerHTML = '<div style="color:#ff4444;font-size:11px;padding:20px 0;text-align:center;">Erro ao carregar dashboard</div>';
  }
}

// ─── Plugins ────────────────────────────────────────────────────
async function loadNexusPlugins() {
  const el = document.getElementById('nx-tab-plugins');
  el.innerHTML = '<div style="color:#223344;font-size:11px;padding:20px 0;text-align:center;">Carregando...</div>';
  try {
    const res     = await fetch('/api/nexus/plugins');
    const plugins = await res.json();
    el.innerHTML = plugins.map(p => `
      <div class="nx-plugin-card ${p.enabled ? 'active' : ''}">
        <span class="nx-plugin-icon">${p.icon}</span>
        <div class="nx-plugin-info">
          <div class="nx-plugin-name">${p.name}</div>
          <div class="nx-plugin-desc">${p.description}</div>
          ${p.env_keys && p.env_keys.length && !p.enabled
            ? `<div style="font-size:9px;color:#334444;margin-top:3px">Requer: ${p.env_keys.join(', ')}</div>`
            : ''}
        </div>
        <div class="nx-plugin-toggle ${p.enabled ? 'on' : ''}"
             onclick="togglePlugin('${p.id}', ${!p.enabled})"
             title="${p.enabled ? 'Desativar' : 'Ativar'}">
        </div>
      </div>
    `).join('');
  } catch(e) {
    el.innerHTML = '<div style="color:#ff4444;font-size:11px;padding:20px 0;text-align:center;">Erro ao carregar plugins</div>';
  }
}

async function togglePlugin(pluginId, enabled) {
  try {
    await fetch('/api/nexus/plugins/toggle', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ plugin_id: pluginId, enabled })
    });
    await loadNexusPlugins();
    window.showToast(enabled ? '✓ Plugin ativado' : '✗ Plugin desativado', enabled ? 'success' : '');
  } catch(e) {
    window.showToast('Erro ao alterar plugin', 'error');
  }
}

// ─── Health Check ────────────────────────────────────────────────
async function loadNexusHealth() {
  const el = document.getElementById('nx-tab-health');
  el.innerHTML = '<div style="color:#223344;font-size:11px;padding:20px 0;text-align:center;">Executando diagnóstico...</div>';
  try {
    const res = await fetch('/api/nexus/health');
    const h   = await res.json();

    const overallColors = { healthy:'#00ff88', partial:'#ffaa00', degraded:'#ff4444', warning:'#ffaa00' };
    const overallLabels = {
      healthy:  'TODOS OS SISTEMAS OPERACIONAIS',
      partial:  'ALGUNS SISTEMAS INDISPONÍVEIS',
      degraded: 'SISTEMA DEGRADADO',
      warning:  'ATENÇÃO NECESSÁRIA',
    };
    const oc = overallColors[h.overall] || '#446688';

    const items = Object.values(h.checks).map(c => {
      const dot = c.status === 'ok' ? 'ok' : c.status === 'warning' ? 'warn' : c.status === 'missing' ? 'missing' : c.status === 'error' ? 'error' : 'unknown';
      return `
        <div class="nx-health-item">
          <div class="nx-health-dot ${dot}"></div>
          <span class="nx-health-label">${c.label}</span>
          <span class="nx-health-detail">${c.detail}</span>
        </div>
      `;
    }).join('');

    el.innerHTML = `
      <div style="padding:10px 12px;border:1px solid ${oc}33;border-radius:3px;margin-bottom:14px;background:${oc}08;">
        <span style="color:${oc};font-size:10px;letter-spacing:2px;text-transform:uppercase;">● ${overallLabels[h.overall] || h.overall}</span>
        <span style="color:#334455;font-size:9px;float:right;margin-top:1px">${h.elapsed_ms}ms</span>
      </div>
      ${items}
    `;
  } catch(e) {
    el.innerHTML = '<div style="color:#ff4444;font-size:11px;padding:20px 0;text-align:center;">Erro ao executar health check</div>';
  }
}

// ─── Sync ────────────────────────────────────────────────────────
function renderNexusSync() {
  const el = document.getElementById('nx-tab-sync');
  el.innerHTML = `
    <div class="nx-sync-card">
      <h4>Exportar Backup</h4>
      <p>Salva todo o seu perfil e memórias em um arquivo JSON que pode ser importado em outra instância do JARVIS.</p>
      <button class="nx-sync-btn" onclick="nexusExport()">↓ Baixar Backup</button>
    </div>
    <div class="nx-sync-card">
      <h4>Importar Backup</h4>
      <p>Restaura perfil e memórias de um arquivo de backup anterior. O perfil atual será sobrescrito.</p>
      <input type="file" id="nx-import-file" accept=".json" style="display:none" onchange="nexusImport(this)"/>
      <button class="nx-sync-btn" onclick="document.getElementById('nx-import-file').click()">↑ Carregar Arquivo</button>
    </div>
    <div class="nx-sync-card">
      <h4>Reconfigurar Perfil</h4>
      <p>Abre o assistente de configuração para atualizar nome, preferências e informações do JARVIS.</p>
      <button class="nx-sync-btn" onclick="closeNexusPanel();openSetupWizard()">⚙ Abrir Wizard</button>
    </div>
  `;
}

async function nexusExport() {
  window.showToast('Preparando backup...', '');
  try {
    const res  = await fetch('/api/nexus/export');
    if (!res.ok) throw new Error('Falha');
    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href = url;
    const cd   = res.headers.get('Content-Disposition') || '';
    const name = cd.match(/filename="?([^"]+)"?/)?.[1] || 'jarvis_backup.json';
    a.download = name;
    a.click();
    URL.revokeObjectURL(url);
    window.showToast('✓ Backup exportado com sucesso', 'success');
  } catch(e) {
    window.showToast('Erro ao exportar backup', 'error');
  }
}

async function nexusImport(input) {
  const file = input.files[0];
  if (!file) return;
  window.showToast('Importando...', '');
  try {
    const fd = new FormData();
    fd.append('file', file);
    const res  = await fetch('/api/nexus/import', { method: 'POST', body: fd });
    const data = await res.json();
    if (data.success) {
      window.showToast(`✓ ${data.memories_restored} memórias restauradas`, 'success');
    } else {
      window.showToast(`Erro: ${data.error}`, 'error');
    }
  } catch(e) {
    window.showToast('Erro ao importar backup', 'error');
  }
}

window.openNexusPanel   = openNexusPanel;
window.closeNexusPanel  = closeNexusPanel;
window.switchNexusTab   = switchNexusTab;
window.togglePlugin     = togglePlugin;
window.nexusExport      = nexusExport;
window.nexusImport      = nexusImport;

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeNexusPanel();
});
