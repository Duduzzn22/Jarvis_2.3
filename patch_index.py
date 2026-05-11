import re

with open('index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update :root and add body.theme-friday
root_css_old = """:root {
    --cyan: #00d4ff;
    --cyan-dim: #0099cc;
    --cyan-dark: #003366;
    --cyan-glow: rgba(0,212,255,0.4);
    --orange: #ff8c00;
    --purple: #9b59b6;
    --bg: #000000;
    --bg2: #050810;
    --text: #e0f7ff;
    --mono: 'Share Tech Mono', monospace;
    --display: 'Orbitron', sans-serif;
  }"""
  
root_css_new = """:root {
    --cyan: #00d4ff;
    --cyan-dim: #0099cc;
    --cyan-dark: #003366;
    --cyan-glow: rgba(0,212,255,0.4);
    --orange: #ff8c00;
    --purple: #9b59b6;
    --bg: #000000;
    --bg2: #050810;
    --text: #e0f7ff;
    --mono: 'Share Tech Mono', monospace;
    --display: 'Orbitron', sans-serif;
    --glass-bg: rgba(0, 5, 15, 0.4);
    --glass-border: rgba(0, 212, 255, 0.2);
  }

  body.theme-friday {
    --cyan: #ff007f;
    --cyan-dim: #cc0066;
    --cyan-dark: #4a0033;
    --cyan-glow: rgba(255,0,127,0.4);
    --orange: #ffaa00;
    --purple: #9b59b6;
    --bg: #05000a;
    --bg2: #0a0015;
    --text: #ffeef7;
    --glass-bg: rgba(10, 0, 15, 0.4);
    --glass-border: rgba(255, 0, 127, 0.2);
  }"""

content = content.replace(root_css_old, root_css_new)

# 2. Update Background (body::before)
bg_old = """/* Scanlines */
  body::before {
    content: '';
    position: fixed;
    top: 0; left: 0;
    width: 100%; height: 100%;
    background: repeating-linear-gradient(
      0deg,
      transparent,
      transparent 2px,
      rgba(0,212,255,0.015) 2px,
      rgba(0,212,255,0.015) 4px
    );
    pointer-events: none;
    z-index: 1000;
  }"""

bg_new = """/* Anti-Gravity Background */
  body::before {
    content: '';
    position: fixed;
    top: 0; left: 0;
    width: 100%; height: 100%;
    background: radial-gradient(circle at center, transparent 30%, var(--bg) 100%);
    pointer-events: none;
    z-index: 0;
  }"""

content = content.replace(bg_old, bg_new)

# 3. Update #particle-canvas
particle_old = """/* Canvas particles behind everything */
  #particle-canvas {
    position: fixed;
    top: 0; left: 0;
    width: 100%; height: 100%;
    z-index: 0;
  }"""

particle_new = """/* Canvas particles behind everything */
  #particle-canvas {
    position: fixed;
    top: 0; left: 0;
    width: 100%; height: 100%;
    z-index: -1;
    filter: blur(2px);
    transition: filter 0.5s ease;
  }
  
  body.theme-friday #particle-canvas {
    filter: blur(8px);
  }"""

content = content.replace(particle_old, particle_new)

# 4. Update Chat Panel Glassmorphism
chat_old = """/* ── RIGHT: CHAT PANEL ── */
  #chat-panel {
    display: flex;
    flex-direction: column;
    border-left: 1px solid rgba(0,212,255,0.2);
    background: rgba(0,5,15,0.7);
    backdrop-filter: blur(20px);
    overflow: hidden;
    min-height: 0;
  }"""

chat_new = """/* ── RIGHT: CHAT PANEL ── */
  #chat-panel {
    display: flex;
    flex-direction: column;
    border-left: 1px solid var(--glass-border);
    background: var(--glass-bg);
    backdrop-filter: blur(15px);
    -webkit-backdrop-filter: blur(15px);
    overflow: hidden;
    min-height: 0;
    box-shadow: -5px 0 25px rgba(0,0,0,0.5);
  }"""

content = content.replace(chat_old, chat_new)

# 5. Update Input Area Glassmorphism
input_old = """/* ── INPUT AREA ── */
  #input-area {
    padding: 12px;
    border-top: 1px solid rgba(0,212,255,0.2);
    display: flex;
    gap: 8px;
    align-items: center;
    background: rgba(0,3,10,0.8);
    flex-shrink: 0;
    position: relative;
    z-index: 20;
  }"""

input_new = """/* ── INPUT AREA ── */
  #input-area {
    padding: 12px;
    border-top: 1px solid var(--glass-border);
    display: flex;
    gap: 8px;
    align-items: center;
    background: transparent;
    flex-shrink: 0;
    position: relative;
    z-index: 20;
  }"""

content = content.replace(input_old, input_new)

# 6. Holo-Dock CSS
wake_css_old = """  #wake-btn {
    position: fixed;
    bottom: 20px;
    left: calc(50% - 220px);
    z-index: 100;
    background: rgba(0,8,20,0.85);
    border: 1px solid rgba(0,212,255,0.25);
    color: #446688;
    font-family: var(--mono);
    font-size: 10px;
    letter-spacing: 2px;
    padding: 6px 14px;
    cursor: pointer;
    border-radius: 2px;
    transition: all 0.2s;
    text-transform: uppercase;
  }
  #wake-btn.active {
    border-color: rgba(0,212,255,0.5);
    color: var(--cyan);
    box-shadow: 0 0 10px rgba(0,212,255,0.1);
  }
  #wake-btn:hover { border-color: rgba(0,212,255,0.4); color: var(--cyan-dim); }"""

holo_dock_css = """  /* ── HOLO-DOCK INFERIOR ── */
  #holo-dock {
    position: fixed;
    bottom: 20px;
    left: 50%;
    transform: translateX(-50%);
    display: flex;
    gap: 15px;
    padding: 10px 25px;
    background: var(--glass-bg);
    backdrop-filter: blur(15px);
    border: 1px solid var(--glass-border);
    border-radius: 30px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.5), inset 0 0 10px var(--glass-border);
    z-index: 100;
    transition: all 0.3s ease;
  }

  .dock-btn {
    background: transparent;
    border: none;
    color: var(--cyan-dim);
    font-family: var(--display);
    font-size: 11px;
    letter-spacing: 2px;
    padding: 8px 12px;
    cursor: pointer;
    transition: all 0.3s;
    border-radius: 15px;
    text-transform: uppercase;
  }

  .dock-btn:hover {
    color: var(--cyan);
    background: rgba(255,255,255,0.05);
    box-shadow: 0 0 15px var(--cyan-glow);
  }

  .dock-btn.active {
    color: var(--cyan);
    box-shadow: inset 0 0 10px var(--cyan-glow);
    background: rgba(255,255,255,0.1);
  }"""

content = content.replace(wake_css_old, holo_dock_css)

# 7. CSS do Canvas Neural e Anéis para Sexta Feira
synapse_old = """/* ── SYNAPSE CANVAS ── */
  #synapse-canvas {
    width: 300px;
    height: 110px;
    opacity: 0.85;
  }"""

synapse_new = """/* ── SYNAPSE CANVAS ── */
  #synapse-canvas {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 320px;
    height: 320px;
    opacity: 0.85;
    z-index: 1;
    pointer-events: none;
  }
  
  body.theme-friday .ring-outer,
  body.theme-friday .ring-middle,
  body.theme-friday .ring-inner {
    border-radius: 50%;
    border-style: dotted;
    border-width: 3px;
  }"""

content = content.replace(synapse_old, synapse_new)

# 8. HTML: Mover os botões para o Holo-Dock
html_dock = """<div id="holo-dock">
    <button id="wake-btn" class="dock-btn" onclick="toggleWakeWord()" title="Ativar detecção por voz contínua">WAKE WORD</button>
    <button id="temporal-btn" class="dock-btn" onclick="openTemporalPanel()">⏱ TEMPORAL</button>
    <button id="nexus-btn" class="dock-btn" onclick="openNexusPanel()">⬡ NEXUS</button>
    <button id="thinking-btn" class="dock-btn" onclick="toggleThinking()" title="Thinking Visible: OFF">🧠 THINKING</button>
    <button id="personality-btn" class="dock-btn" onclick="openPersonalityPanel()">🎭 MODO</button>
    <button id="memory-btn" class="dock-btn" onclick="openMemoryPanel()">⬡ MEMÓRIA</button>
  </div>"""

# Remove botões soltos
content = re.sub(r'<button id="wake-btn"[^>]*>.*?</button>', '', content, flags=re.DOTALL)
content = re.sub(r'<button id="temporal-btn"[^>]*>.*?</button>', '', content, flags=re.DOTALL)
content = re.sub(r'<button id="nexus-btn"[^>]*>.*?</button>', '', content, flags=re.DOTALL)
content = re.sub(r'<button id="thinking-btn"[^>]*>.*?</button>', '', content, flags=re.DOTALL)
content = re.sub(r'<button id="personality-btn"[^>]*>.*?</button>', '', content, flags=re.DOTALL)
content = re.sub(r'<button id="memory-btn"[^>]*>.*?</button>', '', content, flags=re.DOTALL)

# Injeta o Holo-Dock antes do script
content = content.replace("  <canvas id=\"particle-canvas\"></canvas>", f"  <canvas id=\"particle-canvas\"></canvas>\n  {html_dock}")

# 9. HTML: Centralizar Synapse Canvas
core_old = """<div id="core-panel">
      <!-- JARVIS Rings -->
      <div id="rings-container">
        <div class="ring ring-outer"></div>
        <div class="ring ring-middle"></div>
        <div class="ring ring-inner"></div>
        <div id="core-center">
          <div id="core-logo">J.A.R.V.I.S.<br>v3.1</div>
        </div>
      </div>
      
      <!-- Voice Waveform -->
      <div id="waveform-container">
        <canvas id="waveform-canvas"></canvas>
      </div>

      <!-- Neural Synapse Canvas -->
      <canvas id="synapse-canvas"></canvas>
    </div>"""

core_new = """<div id="core-panel">
      <!-- JARVIS Rings -->
      <div id="rings-container">
        <div class="ring ring-outer"></div>
        <div class="ring ring-middle"></div>
        <div class="ring ring-inner"></div>
        
        <canvas id="synapse-canvas"></canvas>

        <div id="core-center">
          <div id="core-logo">J.A.R.V.I.S.<br>v3.1</div>
        </div>
      </div>
      
      <!-- Voice Waveform -->
      <div id="waveform-container">
        <canvas id="waveform-canvas"></canvas>
      </div>
    </div>"""

content = content.replace(core_old, core_new)

# 10. JS: Atualizar Tema quando Personalidade mudar
js_socket_old = """socket.on('personality_changed', (data) => {
      // data: id, name, emoji, color, accent
      document.documentElement.style.setProperty('--cyan', data.color);
      document.documentElement.style.setProperty('--cyan-glow', data.accent);
      
      addMessage('jarvis', `${data.emoji} Personalidade alterada para ${data.name}. O que deseja fazer?`);
      
      showToast(`Modo alterado para ${data.name}`, 'success');
      if (typeof refreshPersonalityTab === 'function') refreshPersonalityTab();
    });"""

js_socket_new = """socket.on('personality_changed', (data) => {
      // data: id, name, emoji, color, accent
      document.documentElement.style.setProperty('--cyan', data.color);
      document.documentElement.style.setProperty('--cyan-glow', data.accent);
      
      // Update theme friday
      if (data.id === 'sexta-feira') {
          document.body.classList.add('theme-friday');
      } else {
          document.body.classList.remove('theme-friday');
      }
      
      addMessage('jarvis', `${data.emoji} Personalidade alterada para ${data.name}. O que deseja fazer?`);
      
      showToast(`Modo alterado para ${data.name}`, 'success');
      if (typeof refreshPersonalityTab === 'function') refreshPersonalityTab();
    });"""

content = content.replace(js_socket_old, js_socket_new)

# 11. JS: initSynapses reescrito
# Eu vou procurar pela defição original de initSynapses e substituí-la.
init_synapses_pattern = r"function initSynapses\(\) \{.*?\n    \}\n    animate\(\);\n\}"

new_init_synapses = """function initSynapses() {
    const canvas = document.getElementById('synapse-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    
    // Dimensões exatas baseadas no CSS do anel
    canvas.width = 320;
    canvas.height = 320;

    let nodes = [];
    const numNodes = 40;
    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2;
    const baseRadius = 110; // Fica entre o anel do meio e exterior

    for (let i = 0; i < numNodes; i++) {
        nodes.push({
            angle: Math.random() * Math.PI * 2,
            speed: (Math.random() * 0.02 + 0.01) * (Math.random() > 0.5 ? 1 : -1),
            orbitOffset: Math.random() * 30 - 15,
            size: Math.random() * 2 + 1,
            pulse: Math.random() * Math.PI * 2
        });
    }

    function animate() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        
        // Verifica o estado atual de speaking via classe no container
        const isSpeaking = document.getElementById('rings-container').classList.contains('speaking');
        
        // As cores se baseiam na variável de tema lida do CSS!
        const styles = getComputedStyle(document.body);
        const nodeColor = isSpeaking ? styles.getPropertyValue('--orange').trim() : styles.getPropertyValue('--cyan').trim();
        const glowColor = isSpeaking ? styles.getPropertyValue('--orange').trim() : styles.getPropertyValue('--cyan-glow').trim();

        ctx.strokeStyle = glowColor;
        ctx.fillStyle = nodeColor;
        ctx.lineWidth = isSpeaking ? 1.5 : 0.8;

        // Atualiza e desenha os nós
        nodes.forEach(n => {
            // Acelera os neurônios quando a IA fala
            n.angle += isSpeaking ? n.speed * 3 : n.speed;
            n.pulse += 0.1;
            
            const currentRadius = baseRadius + n.orbitOffset + (isSpeaking ? Math.sin(n.pulse) * 10 : 0);
            n.x = centerX + Math.cos(n.angle) * currentRadius;
            n.y = centerY + Math.sin(n.angle) * currentRadius;

            ctx.beginPath();
            ctx.arc(n.x, n.y, n.size + (isSpeaking ? 1 : 0), 0, Math.PI * 2);
            ctx.fill();
        });

        // Desenha as conexões (sinapses) entre nós próximos
        ctx.beginPath();
        for (let i = 0; i < nodes.length; i++) {
            for (let j = i + 1; j < nodes.length; j++) {
                const dx = nodes[i].x - nodes[j].x;
                const dy = nodes[i].y - nodes[j].y;
                const dist = Math.sqrt(dx * dx + dy * dy);

                // Conecta nós próximos
                const connectThreshold = isSpeaking ? 80 : 60;
                if (dist < connectThreshold) {
                    ctx.moveTo(nodes[i].x, nodes[i].y);
                    ctx.lineTo(nodes[j].x, nodes[j].y);
                }
            }
        }
        ctx.globalAlpha = isSpeaking ? 0.8 : 0.3;
        ctx.stroke();
        ctx.globalAlpha = 1.0;

        requestAnimationFrame(animate);
    }
    animate();
}"""

content = re.sub(init_synapses_pattern, new_init_synapses, content, flags=re.DOTALL)

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Patch applied!")
