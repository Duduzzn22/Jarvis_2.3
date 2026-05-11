/* ═══════════════════════════════════════════════════════════════
   JARVIS OS — SETUP WIZARD MODULE
   First-run configuration wizard
   ═══════════════════════════════════════════════════════════════ */

const SETUP_STEPS = [
  {
    title: 'IDENTIDADE',
    sub: 'Qual é o seu nome? O JARVIS usará isso em todas as interações.',
    type: 'input',
    placeholder: 'Seu primeiro nome...',
    field: 'user_name',
    memory_category: 'pessoal',
    memory_prefix: 'Usuário se chama ',
    importance: 3,
    transform: v => v.charAt(0).toUpperCase() + v.slice(1),
  },
  {
    title: 'OCUPAÇÃO',
    sub: 'Em qual área você trabalha? Isso ajuda o JARVIS a personalizar respostas técnicas.',
    type: 'input',
    placeholder: 'Desenvolvedor, designer, engenheiro...',
    field: 'occupation',
    memory_category: 'trabalho',
    memory_prefix: 'Trabalha como ',
    importance: 2,
    optional: true,
  },
  {
    title: 'SISTEMA OPERACIONAL',
    sub: 'Qual sistema você usa? O JARVIS vai adaptar os comandos ao seu ambiente.',
    type: 'options',
    field: 'os',
    options: ['Windows', 'macOS', 'Linux'],
    memory_category: 'tecnologia',
    memory_prefix: 'Usa ',
    memory_suffix: ' como sistema operacional',
    importance: 2,
  },
  {
    title: 'HORÁRIO DE TRABALHO',
    sub: 'Quando você costuma trabalhar? Isso permite ao JARVIS adaptar as saudações.',
    type: 'options',
    field: 'work_hours',
    options: ['Manhã (6h–12h)', 'Tarde (12h–18h)', 'Noite (18h–00h)', 'Variado'],
    memory_category: 'habito',
    memory_prefix: 'Trabalha no período: ',
    importance: 1,
  },
  {
    title: 'ESTILO DE RESPOSTA',
    sub: 'Como prefere que o JARVIS responda?',
    type: 'options',
    field: 'response_style',
    options: ['Curtas e diretas', 'Detalhadas quando necessário', 'Sempre detalhadas'],
    memory_category: 'preferencia',
    memory_map: {
      'Curtas e diretas': 'Prefere respostas curtas e diretas',
      'Detalhadas quando necessário': 'Prefere respostas detalhadas quando o assunto exige',
      'Sempre detalhadas': 'Prefere respostas sempre detalhadas e completas',
    },
    importance: 2,
  },
  {
    title: 'NOTA FINAL',
    sub: 'Há algo mais que o JARVIS deva saber sobre você? Hobbies, projetos, preferências?',
    type: 'input',
    placeholder: 'Gosto de música eletrônica, trabalho com IA... (opcional)',
    field: 'extra_info',
    memory_category: 'pessoal',
    memory_prefix: '',
    importance: 2,
    optional: true,
  },
];

let setupCurrentStep = 0;
let setupAnswers     = {};

async function checkAndShowSetup() {
  try {
    const res   = await fetch('/api/nexus/setup/state');
    const state = await res.json();
    if (!state.completed && (!state.profile || !state.profile.user_name)) {
      setTimeout(() => openSetupWizard(), 3800);
    }
  } catch(e) {}
}

function openSetupWizard() {
  setupCurrentStep = 0;
  setupAnswers     = {};
  document.getElementById('setup-overlay').classList.add('open');
  renderSetupStep(0);
}

function renderSetupStep(stepIdx) {
  const step = SETUP_STEPS[stepIdx];
  if (!step) { finalizeSetupWizard(); return; }

  const dots = document.getElementById('setup-progress-dots');
  dots.innerHTML = SETUP_STEPS.map((_, i) => {
    const cls = i < stepIdx ? 'done' : i === stepIdx ? 'current' : '';
    return `<div class="setup-dot ${cls}"></div>`;
  }).join('');

  document.getElementById('setup-next').textContent = stepIdx === SETUP_STEPS.length - 1 ? 'Concluir ✓' : 'Continuar →';
  document.getElementById('setup-skip').style.display = step.optional ? 'block' : 'none';

  const body = document.getElementById('setup-body');
  let content = `
    <div class="setup-step-title">${step.title}</div>
    <div class="setup-step-sub">${step.sub}</div>
  `;

  if (step.type === 'input') {
    const val = setupAnswers[step.field] || '';
    content += `<input class="setup-input" id="setup-input-field" type="text"
      placeholder="${step.placeholder || ''}" value="${val}"
      onkeydown="if(event.key==='Enter') nextSetupStep()" autofocus>`;
  } else if (step.type === 'options') {
    const sel = setupAnswers[step.field] || step.options[0];
    content += `<div class="setup-options">` +
      step.options.map(opt => `
        <div class="setup-option ${sel === opt ? 'selected' : ''}" onclick="selectSetupOption('${step.field}', '${opt}', this)">
          <div class="setup-option-dot"></div>
          ${opt}
        </div>
      `).join('') + `</div>`;
    if (!setupAnswers[step.field]) setupAnswers[step.field] = step.options[0];
  }

  body.innerHTML = content;
  const input = document.getElementById('setup-input-field');
  if (input) setTimeout(() => input.focus(), 50);
}

function selectSetupOption(field, value, el) {
  setupAnswers[field] = value;
  document.querySelectorAll('.setup-option').forEach(o => o.classList.remove('selected'));
  el.classList.add('selected');
}

async function nextSetupStep() {
  const step = SETUP_STEPS[setupCurrentStep];
  if (!step) { finalizeSetupWizard(); return; }

  if (step.type === 'input') {
    const inp = document.getElementById('setup-input-field');
    const val = inp ? inp.value.trim() : '';
    if (!val && !step.optional) {
      inp.style.borderColor = '#ff4444';
      setTimeout(() => { inp.style.borderColor = ''; }, 1000);
      return;
    }
    if (val) {
      setupAnswers[step.field] = step.transform ? step.transform(val) : val;
    }
  }

  const answer = setupAnswers[step.field];
  if (answer) {
    let memoryText = '';
    if (step.memory_map) {
      memoryText = step.memory_map[answer] || (step.memory_prefix + answer);
    } else if (step.memory_prefix !== undefined) {
      memoryText = step.memory_prefix + answer + (step.memory_suffix || '');
    }

    try {
      await fetch('/api/nexus/setup/step', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({
          step:            setupCurrentStep,
          field:           step.field,
          value:           answer,
          memory_category: step.memory_category,
          memory_text:     memoryText,
          importance:      step.importance || 1,
        })
      });
    } catch(e) {}
  }

  setupCurrentStep++;
  if (setupCurrentStep >= SETUP_STEPS.length) {
    finalizeSetupWizard();
  } else {
    renderSetupStep(setupCurrentStep);
  }
}

function skipSetup() {
  setupCurrentStep++;
  if (setupCurrentStep >= SETUP_STEPS.length) {
    finalizeSetupWizard();
  } else {
    renderSetupStep(setupCurrentStep);
  }
}

async function finalizeSetupWizard() {
  const body = document.getElementById('setup-body');
  body.innerHTML = `
    <div style="text-align:center;padding:20px 0">
      <div style="font-size:32px;margin-bottom:16px">✓</div>
      <div class="setup-step-title" style="justify-content:center">CONFIGURAÇÃO CONCLUÍDA</div>
      <div class="setup-step-sub" style="text-align:center;margin-top:8px">
        Bem-vindo, ${setupAnswers.user_name || 'Senhor'}.<br>
        O JARVIS está pronto para servi-lo.
      </div>
    </div>
  `;
  document.getElementById('setup-next').style.display = 'none';
  document.getElementById('setup-skip').style.display = 'none';

  try {
    await fetch('/api/nexus/setup/finalize', { method: 'POST' });
  } catch(e) {}

  if (setupAnswers.user_name) {
    const hudName = document.getElementById('hud-username');
    if (hudName) {
      hudName.textContent = `SENHOR ${setupAnswers.user_name.toUpperCase()}`;
      hudName.style.display = 'inline';
    }
  }

  setTimeout(() => {
    document.getElementById('setup-overlay').classList.remove('open');
    document.getElementById('setup-next').style.display = '';
    window.showToast(`✓ Bem-vindo, ${setupAnswers.user_name || 'Senhor'}.`, 'success');
  }, 2200);
}

window.openSetupWizard    = openSetupWizard;
window.renderSetupStep    = renderSetupStep;
window.selectSetupOption  = selectSetupOption;
window.nextSetupStep      = nextSetupStep;
window.skipSetup          = skipSetup;

// Socket events
document.addEventListener('DOMContentLoaded', () => {
  const socket = window.JARVIS?.socket;
  if (!socket) return;

  socket.on('connect', () => {
    setTimeout(checkAndShowSetup, 500);
  });

  socket.on('setup_completed', () => {
    document.getElementById('setup-overlay').classList.remove('open');
  });
});
