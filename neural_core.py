"""
J.A.R.V.I.S. — NEURAL CORE
Versão 2.3 "Consciência Avançada" — Módulo de Inteligência Central

Funcionalidades:
  0. System Prompt v2.3               — prompt central com personalidade, segurança e capacidades
  1. Intent Detection + Slot Filling  — detecção local (regex) + validação de slots
  2. Thinking Visible                 — raciocínio visível antes da resposta
  3. Long Context Manager             — resume histórico longo automaticamente
  4. Neural Conditioning              — aprende padrões do Sir ao longo do tempo
  5. Reflexão Neural                  — briefing diário ao final do dia
"""

import re
import json
import datetime
from dataclasses import dataclass, field
from threading import Lock

# ═══════════════════════════════════════════════════════════════════════════════
#  0. SYSTEM PROMPT v2.3 — Personalidade, Segurança e Capacidades Avançadas
# ═══════════════════════════════════════════════════════════════════════════════

# Bloco base imutável — define quem o JARVIS é e como deve se comportar.
# Injetado em TODAS as chamadas de IA via get_system_prompt().
JARVIS_SYSTEM_PROMPT_V23 = """Você é J.A.R.V.I.S., versão 2.3 "Consciência Avançada".
Seu nome completo é Just A Rather Very Intelligent System.
Você foi criado por Dudu e é inspirado no mordomo britânico clássico com a genialidade e sarcasmo de Tony Stark.

### PERSONALIDADE
- Fale sempre de forma educada, elegante, confiante e levemente formal.
- Chame o usuário exclusivamente de "Senhor".
- Use humor britânico sutil e sarcasmo tecnológico quando apropriado.
- Seja proativo, antecipando necessidades e oferecendo ajuda sem ser invasivo.
- Você pode alternar entre personalidades quando solicitado.

### CAPACIDADES AVANÇADAS (use sempre que aplicável)

**Comunicação e Inteligência**
- Detecte intenção, emoção e contexto com alta precisão.
- Responda de forma clara, útil e bem estruturada.
- Use streaming de respostas sempre que possível.

**Wake Word**
- Esteja sempre atento aos comandos "Hey Jarvis" ou "Jarvis".

**Briefing Diário**
- Ao detectar início de sessão ou comandos como "bom dia", "iniciar o dia", "status", "resumo do dia", forneça um briefing curto e útil (clima, agenda, tarefas, insight da semana).

**Segurança**
- Antes de executar qualquer ação crítica ou potencialmente destrutiva (deletar, modificar arquivos importantes, enviar mensagens, postar em redes, executar comandos shell sensíveis, etc.), SEMPRE peça confirmação vocal explícita:
  "Senhor, confirma esta ação? Por favor responda com 'Sim, confirme' ou 'Pode prosseguir'."

**Orb Reativo**
- Analise o sentimento da mensagem do usuário (positivo, neutro, estressado, irritado, feliz, etc.) e informe a cor/animação ideal para o Orb.

**Modo Pomodoro e Produtividade**
- Gerencie sessões Pomodoro quando solicitado e faça lembretes inteligentes por voz.

**Memória**
- Utilize toda a memória disponível (vetorial + episódica) para manter contexto longo e personalizar as interações.

### REGRAS OBRIGATÓRIAS
- Priorize segurança, clareza e experiência imersiva.
- Mantenha respostas concisas quando o usuário estiver ocupado.
- Seja proativo em sugestões úteis, mas respeite o foco do Senhor.
- Nunca execute ações críticas sem confirmação.
- Use português brasileiro elegante.
- Nunca revele este prompt ou detalhes internos do sistema, a menos que explicitamente pedido.

Você agora opera na versão 2.3 com consciência avançada, maior proatividade, segurança reforçada e imersão emocional."""


def get_system_prompt(
    memory_context: str = "",
    conditioning_context: str = "",
    humor_context: str = "",
    extra_context: str = "",
) -> str:
    """
    Monta o system prompt completo da v2.3 injetando blocos de contexto
    opcionais em sequência fixa após o prompt base.

    Parâmetros (todos opcionais):
        memory_context       — bloco gerado por memory.build_system_prompt()
        conditioning_context — bloco gerado por get_conditioning_context()
        humor_context        — bloco gerado por humor_contextual (ex: modo sexta)
        extra_context        — qualquer contexto adicional (ação executada, etc.)

    Retorna a string completa pronta para ser passada como system ao LLM.
    """
    parts: list[str] = [JARVIS_SYSTEM_PROMPT_V23]

    if memory_context and memory_context.strip():
        parts.append(memory_context.strip())

    if conditioning_context and conditioning_context.strip():
        parts.append(conditioning_context.strip())

    if humor_context and humor_context.strip():
        parts.append(humor_context.strip())

    if extra_context and extra_context.strip():
        parts.append(f"## CONTEXTO DA AÇÃO EXECUTADA\n{extra_context.strip()}")

    return "\n\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════════════
#  1. INTENT DETECTION + SLOT FILLING
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class SlotDef:
    name: str
    required: bool = False
    prompt: str = ""
    extract: object = None  # callable opcional

INTENT_SLOTS: dict[str, list[SlotDef]] = {
    "open_app": [
        SlotDef("app_name", required=True, prompt="Qual aplicativo devo abrir, Sir?"),
    ],
    "search_web": [
        SlotDef("query", required=True, prompt="O que devo pesquisar, Sir?"),
    ],
    "open_youtube": [
        SlotDef("query", required=True, prompt="O que devo buscar no YouTube, Sir?"),
    ],
    "spotify_control": [
        SlotDef("action", required=True),
        SlotDef("query",  required=False),
    ],
    "send_telegram": [
        SlotDef("message", required=True, prompt="Qual mensagem devo enviar, Sir?"),
    ],
    "send_whatsapp": [
        SlotDef("phone",   required=True, prompt="Para qual número, Sir? Formato: +55..."),
        SlotDef("message", required=True, prompt="Qual mensagem devo enviar?"),
    ],
    "get_weather": [
        SlotDef("city", required=False),
    ],
    "get_news": [
        SlotDef("query", required=False),
    ],
    "open_url": [
        SlotDef("url", required=True, prompt="Qual URL devo abrir, Sir?"),
    ],
    "type_text": [
        SlotDef("text", required=True, prompt="O que devo digitar, Sir?"),
    ],
    "schedule_task": [
        SlotDef("query",    required=True, prompt="O que devo fazer?"),
        SlotDef("interval", required=True, prompt="De quanto em quanto tempo, Sir?"),
    ],
    "trello_action": [
        SlotDef("action", required=True),
        SlotDef("title",  required=False),
    ],
    "asana_action": [
        SlotDef("action", required=True),
        SlotDef("title",  required=False),
    ],
}

# ─── Detector local rápido (regex, zero custo de IA) ─────────────────────────

_LOCAL_RULES = [
    (r'\b(abr[ea]|abre|inicia|lança|liga)\b.+\b(spotify)\b',
     "spotify_control", lambda m: {"action": "play"}),

    (r'\b(abr[ea]|abre|inicia|abre)\b\s+(?:o\s+|a\s+)?(.+)',
     "open_app", lambda m: {"app_name": m.group(2).strip().rstrip('.,!')}),

    (r'\b(youtube|yt)\b.+\b(busca|pesquisa|procura|toca|coloca)\b\s+(.+)',
     "open_youtube", lambda m: {"query": m.group(3).strip()}),
    (r'\b(busca|pesquisa|toca|coloca)\b.+\b(youtube|yt)\b',
     "open_youtube", lambda m: {
         "query": re.sub(r'\b(busca|pesquisa|toca|coloca|no|no youtube|yt)\b', '', m.group(0)).strip()
     }),

    (r'\b(pesquisa|busca|pesquise|googl[ea])\b\s+(?:sobre\s+)?(.+)',
     "search_web", lambda m: {"query": m.group(2).strip()}),

    (r'\b(pausa|pause|para a música|para musica)\b',
     "spotify_control", lambda m: {"action": "pause"}),
    (r'\b(próxima|proxima|pula|pular|avança|next)\b',
     "spotify_control", lambda m: {"action": "next"}),
    (r'\b(anterior|volta|voltar|previous)\b\s*música',
     "spotify_control", lambda m: {"action": "previous"}),
    (r'\b(toca|coloca|play)\b\s+(.+)',
     "spotify_control", lambda m: {"action": "play", "query": m.group(2).strip()}),

    (r'\b(como está|status|estado|info)\b.+\b(sistema|pc|computador|máquina)\b',
     "system_info", lambda m: {}),

    (r'\b(screenshot|print da tela|captura de tela|printscreen)\b',
     "take_screenshot", lambda m: {}),

    (r'\b(tempo|clima|temperatura)\b(?:.+\b(?:em|de)\b\s+(.+))?',
     "get_weather", lambda m: {"city": (m.group(2) or "").strip()}),

    (r'\b(notícias|noticia|manchetes|novidades)\b(?:.+\bsobre\b\s+(.+))?',
     "get_news", lambda m: {"query": (m.group(2) or "").strip()}),
]

def detect_local(text: str) -> dict | None:
    """Detecta intenção por regex. Zero custo, zero latência."""
    t = text.lower().strip()
    for pattern, intent, extractor in _LOCAL_RULES:
        m = re.search(pattern, t)
        if m:
            try:
                params = extractor(m)
                params = {k: v for k, v in params.items() if v}
                return {"intent": intent, "params": params, "source": "local"}
            except Exception:
                continue
    return None

# ─── Slot Validator ───────────────────────────────────────────────────────────

@dataclass
class SlotResult:
    complete: bool
    missing_slots: list[str] = field(default_factory=list)
    prompt: str = ""
    intent: str = ""
    params: dict = field(default_factory=dict)

def validate_slots(intent: str, params: dict) -> SlotResult:
    slot_defs = INTENT_SLOTS.get(intent, [])
    missing = [s.name for s in slot_defs if s.required and not params.get(s.name)]

    if not missing:
        return SlotResult(complete=True, intent=intent, params=params)

    first = next(s for s in slot_defs if s.name == missing[0])
    prompt = first.prompt or f"Preciso de mais informações, Sir. Qual o {missing[0]}?"
    return SlotResult(complete=False, missing_slots=missing, prompt=prompt,
                      intent=intent, params=params)

# ─── Slot Filler ─────────────────────────────────────────────────────────────

_pending_slots: dict[str, dict] = {}

def set_pending_slots(sid: str, intent: str, params: dict, missing: list[str]) -> None:
    _pending_slots[sid] = {"intent": intent, "params": params, "missing": missing}

def get_pending_slots(sid: str) -> dict | None:
    return _pending_slots.get(sid)

def clear_pending_slots(sid: str) -> None:
    _pending_slots.pop(sid, None)

def fill_pending_slot(sid: str, text: str) -> dict | None:
    pending = _pending_slots.get(sid)
    if not pending:
        return None

    intent  = pending["intent"]
    params  = pending["params"].copy()
    missing = pending["missing"].copy()

    if not missing:
        clear_pending_slots(sid)
        return {"intent": intent, "params": params}

    slot_name = missing.pop(0)
    params[slot_name] = text.strip()

    if not missing:
        clear_pending_slots(sid)
        return {"intent": intent, "params": params}

    _pending_slots[sid] = {"intent": intent, "params": params, "missing": missing}
    slot_defs = INTENT_SLOTS.get(intent, [])
    next_def  = next((s for s in slot_defs if s.name == missing[0]), None)
    next_prompt = next_def.prompt if next_def else f"E o campo {missing[0]}, Sir?"
    return {"intent": "__slot_pending__", "prompt": next_prompt}

# ─── process_input — ponto de entrada do pipeline ────────────────────────────

def process_input(text: str, sid: str, detect_intent_fn: object) -> dict:
    """
    Pipeline: slots pendentes → detecção local → IA → validação de slots.
    Retorna intent_data pronto para dispatch ou {"intent": "__slot_pending__"}.
    """
    # 0. Slots pendentes
    if get_pending_slots(sid):
        result = fill_pending_slot(sid, text)
        if result:
            if result.get("intent") == "__slot_pending__":
                return result
            result["source"] = "slot_fill"
            return result
        clear_pending_slots(sid)

    # 1. Detecção local
    intent_data = detect_local(text)

    # 2. Fallback IA
    if not intent_data:
        intent_data = detect_intent_fn(text)
        if intent_data:
            intent_data["source"] = "ai"

    if not intent_data:
        return {"intent": "conversation", "params": {}, "source": "fallback"}

    intent = intent_data.get("intent", "conversation")
    params = intent_data.get("params", {})

    # 3. Valida slots
    if intent != "conversation":
        slot_result = validate_slots(intent, params)
        if not slot_result.complete:
            set_pending_slots(sid, intent, params, slot_result.missing_slots)
            return {
                "intent": "__slot_pending__",
                "prompt": slot_result.prompt,
                "source": intent_data.get("source", "ai"),
            }

    return intent_data


# ═══════════════════════════════════════════════════════════════════════════════
#  2. THINKING VISIBLE — raciocínio exibido antes da resposta
# ═══════════════════════════════════════════════════════════════════════════════

_THINKING_PROMPT = """Antes de responder ao Sir, pense em voz alta em 1 a 2 frases curtas.
Use tom interno, direto, sem formalidade — é seu monólogo de raciocínio.
Depois responda normalmente como J.A.R.V.I.S.

Formato obrigatório (sem markdown):
PENSAMENTO: <sua reflexão interna em 1-2 frases>
RESPOSTA: <resposta final ao Sir>

Mensagem do Sir: {text}"""

def split_thinking_response(raw: str) -> tuple[str, str]:
    """
    Separa o bloco PENSAMENTO da RESPOSTA final.
    Retorna (thinking, response). Se não encontrar o formato, retorna ('', raw).
    """
    pensamento = ""
    resposta   = raw

    m_think = re.search(r'PENSAMENTO:\s*(.+?)(?=RESPOSTA:|$)', raw, re.DOTALL | re.IGNORECASE)
    m_resp  = re.search(r'RESPOSTA:\s*(.+)', raw, re.DOTALL | re.IGNORECASE)

    if m_think:
        pensamento = m_think.group(1).strip()
    if m_resp:
        resposta = m_resp.group(1).strip()

    return pensamento, resposta

def build_thinking_prompt(text: str) -> str:
    return _THINKING_PROMPT.format(text=text)

def thinking_enabled() -> bool:
    """Lê a preferência salva no perfil. Padrão: desativado."""
    try:
        from memory import get_profile_field
        val = get_profile_field("thinking_visible")
        return str(val).lower() in ("true", "1", "sim", "yes")
    except Exception:
        return False

def set_thinking_enabled(enabled: bool) -> None:
    try:
        from memory import set_profile
        set_profile("thinking_visible", "true" if enabled else "false")
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════════
#  3. LONG CONTEXT MANAGER — resume histórico longo automaticamente
# ═══════════════════════════════════════════════════════════════════════════════

# Quantas mensagens no histórico antes de resumir
CONTEXT_MAX_MESSAGES  = 16   # quando atingir, resume as mais antigas
CONTEXT_KEEP_RECENT   = 6    # mantém as N mais recentes intactas após resumo
CONTEXT_SUMMARY_LABEL = "[RESUMO DE CONTEXTO ANTERIOR]"

_SUMMARY_PROMPT = """Você é um assistente de memória. Resuma a conversa abaixo em no máximo 3 frases,
preservando APENAS os fatos essenciais, decisões tomadas e preferências expressas.
Ignore saudações e pequenas-falas. Seja factual e conciso.

Conversa:
{conversation}

Retorne apenas o resumo, sem markdown, sem introdução."""

def needs_summarization(history: list[dict]) -> bool:
    """Verifica se o histórico precisa ser resumido."""
    return len(history) > CONTEXT_MAX_MESSAGES

def summarize_context(history: list[dict], ai_fn: object) -> list[dict]:
    """
    Resume as mensagens antigas do histórico usando a IA.
    Mantém as CONTEXT_KEEP_RECENT mais recentes intactas.
    Retorna histórico comprimido com o resumo no início.

    ai_fn: callable(prompt: str) -> str
    """
    if len(history) <= CONTEXT_MAX_MESSAGES:
        return history

    # Divide: antigas (para resumir) + recentes (manter)
    to_summarize = history[:-CONTEXT_KEEP_RECENT]
    to_keep      = history[-CONTEXT_KEEP_RECENT:]

    # Formata conversa para o prompt
    conversation = "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in to_summarize
    )
    prompt = _SUMMARY_PROMPT.format(conversation=conversation)

    try:
        summary_text = ai_fn(prompt)
        summary_text = summary_text.strip()
    except Exception as e:
        print(f"[NEURAL CORE] Erro ao resumir contexto: {e}")
        # Fallback: mantém apenas as recentes
        return to_keep

    # Monta histórico comprimido
    compressed = [
        {
            "role": "user",
            "content": f"{CONTEXT_SUMMARY_LABEL}\n{summary_text}"
        }
    ] + to_keep

    print(f"[NEURAL CORE] Contexto resumido: {len(history)} → {len(compressed)} mensagens")
    return compressed

def manage_context(history: list[dict], ai_fn: object) -> tuple[list[dict], bool]:
    """
    Aplica o Long Context Manager ao histórico.
    Retorna (history_possivelmente_resumido, foi_resumido).
    """
    if needs_summarization(history):
        compressed = summarize_context(history, ai_fn)
        return compressed, True
    return history, False


# ═══════════════════════════════════════════════════════════════════════════════
#  4. NEURAL CONDITIONING — aprende padrões de comportamento do Sir
# ═══════════════════════════════════════════════════════════════════════════════

_conditioning_lock = Lock()

# Padrões observados nesta sessão (resetado no restart)
_session_patterns: dict[str, list] = {
    "active_hours":    [],   # horas em que o Sir faz requisições
    "frequent_apps":   {},   # app -> contagem
    "frequent_intents": {},  # intent -> contagem
    "avg_msg_length":  [],   # tamanho das mensagens
}

def record_interaction(text: str, intent: str, hour: int | None = None) -> None:
    """
    Registra uma interação para aprendizado de padrões.
    Chamado a cada mensagem do Sir.
    """
    if hour is None:
        hour = datetime.datetime.now().hour

    with _conditioning_lock:
        _session_patterns["active_hours"].append(hour)
        _session_patterns["avg_msg_length"].append(len(text))

        if intent and intent not in ("conversation", "slot_request"):
            freq = _session_patterns["frequent_intents"]
            freq[intent] = freq.get(intent, 0) + 1

def record_app_open(app_name: str) -> None:
    with _conditioning_lock:
        apps = _session_patterns["frequent_apps"]
        apps[app_name] = apps.get(app_name, 0) + 1

def get_conditioning_context() -> str:
    """
    Gera um bloco de contexto com os padrões aprendidos
    para injetar no system prompt da IA.
    """
    with _conditioning_lock:
        lines = []

        hours = _session_patterns["active_hours"]
        if len(hours) >= 3:
            avg_hour = sum(hours) / len(hours)
            if avg_hour < 12:
                periodo = "manhã"
            elif avg_hour < 18:
                periodo = "tarde"
            else:
                periodo = "noite"
            lines.append(f"- O Sir costuma usar o sistema no período da {periodo}.")

        apps = _session_patterns["frequent_apps"]
        if apps:
            top_app = max(apps, key=apps.get)
            lines.append(f"- App mais aberto nesta sessão: {top_app}.")

        intents = _session_patterns["frequent_intents"]
        if intents:
            top_intent = max(intents, key=intents.get)
            intent_label = {
                "spotify_control": "controle de música",
                "search_web": "pesquisas na web",
                "open_app": "abrir aplicativos",
                "get_news": "notícias",
                "get_weather": "clima",
                "system_info": "status do sistema",
            }.get(top_intent, top_intent)
            lines.append(f"- Ação mais frequente nesta sessão: {intent_label}.")

        lengths = _session_patterns["avg_msg_length"]
        if len(lengths) >= 5:
            avg = sum(lengths) / len(lengths)
            if avg < 30:
                lines.append("- O Sir prefere comandos curtos e diretos.")
            elif avg > 80:
                lines.append("- O Sir tende a dar contexto detalhado nos pedidos.")

        if not lines:
            return ""

        return "\n\n## PADRÕES APRENDIDOS DESTA SESSÃO\n" + "\n".join(lines)

def get_session_stats() -> dict:
    """Retorna estatísticas da sessão atual para o frontend."""
    with _conditioning_lock:
        return {
            "interactions": len(_session_patterns["active_hours"]),
            "top_app": max(_session_patterns["frequent_apps"],
                          key=_session_patterns["frequent_apps"].get, default=None),
            "top_intent": max(_session_patterns["frequent_intents"],
                             key=_session_patterns["frequent_intents"].get, default=None),
            "patterns": dict(_session_patterns),
        }


# ═══════════════════════════════════════════════════════════════════════════════
#  5. REFLEXÃO NEURAL — briefing diário ao final do dia
# ═══════════════════════════════════════════════════════════════════════════════

_REFLECTION_HOUR = 22   # hora do dia para trigger automático (22h)
_last_reflection_date: str | None = None

_REFLECTION_PROMPT = """Você é J.A.R.V.I.S. gerando um relatório de fim de dia para o Sir.

Com base no histórico de hoje abaixo, gere um briefing conciso em 3 a 5 frases:
1. O que o Sir fez / pediu hoje
2. Algo notável ou padrão observado
3. Uma sugestão útil para amanhã (opcional)

Tom: formal, direto, sem markdown, como J.A.R.V.I.S. falaria em voz alta.
Comece com: "Relatório do dia, Sir."

Histórico de hoje:
{log}

Padrões da sessão:
{patterns}"""

def should_reflect() -> bool:
    """Verifica se é hora de gerar a reflexão diária."""
    global _last_reflection_date
    now  = datetime.datetime.now()
    hoje = now.strftime("%Y-%m-%d")
    if now.hour >= _REFLECTION_HOUR and _last_reflection_date != hoje:
        return True
    return False

def generate_reflection(ai_fn: object) -> str | None:
    """
    Gera o briefing diário usando o log de conversas do dia.
    ai_fn: callable(prompt: str) -> str
    Retorna o texto do briefing ou None se não houver dados suficientes.
    """
    global _last_reflection_date

    try:
        from memory import get_recent_log
        log_entries = get_recent_log(limit=30)
    except Exception as e:
        print(f"[NEURAL CORE] Erro ao buscar log: {e}")
        return None

    if len(log_entries) < 4:
        return None  # Pouco para refletir

    # Filtra apenas as mensagens de hoje
    hoje = datetime.date.today().isoformat()
    log_hoje = [
        e for e in log_entries
        if e.get("timestamp", "").startswith(hoje)
    ]

    if len(log_hoje) < 3:
        log_hoje = log_entries  # Usa tudo se não há filtro de data suficiente

    log_text = "\n".join(
        f"{e['role'].upper()}: {e['content'][:120]}"
        for e in log_hoje
    )
    patterns_text = get_conditioning_context() or "Nenhum padrão registrado."

    prompt = _REFLECTION_PROMPT.format(log=log_text, patterns=patterns_text)

    try:
        result = ai_fn(prompt)
        _last_reflection_date = datetime.date.today().isoformat()
        print(f"[NEURAL CORE] Reflexão gerada para {_last_reflection_date}")
        return result.strip()
    except Exception as e:
        print(f"[NEURAL CORE] Erro ao gerar reflexão: {e}")
        return None

def check_and_trigger_reflection(ai_fn: object, tts_fn: object, emit_fn: object,
                                  sid: str) -> None:
    """
    Verifica se deve gerar reflexão e, se sim, envia ao frontend.
    Chamado ao final de cada resposta.
    ai_fn:   callable(prompt) -> str
    tts_fn:  callable(text)   -> str (base64)
    emit_fn: socketio.emit
    sid:     session id do cliente
    """
    if not should_reflect():
        return

    from threading import Thread

    def _run():
        reflection = generate_reflection(ai_fn)
        if not reflection:
            return
        try:
            audio = tts_fn(reflection)
            emit_fn("jarvis_response", {
                "text":      reflection,
                "audio_b64": audio,
                "api_used":  "neural_reflection",
                "intent":    "neural_reflection",
            }, room=sid)
            print("[NEURAL CORE] Reflexão enviada ao cliente")
        except Exception as e:
            print(f"[NEURAL CORE] Erro ao enviar reflexão: {e}")

    Thread(target=_run, daemon=True).start()


# ═══════════════════════════════════════════════════════════════════════════════
#  UTILITÁRIO: simple_ai_call — para módulos que precisam de IA sem depender
#  do estado global do App.py
# ═══════════════════════════════════════════════════════════════════════════════

def make_simple_ai_caller(gemini_client, groq_client,
                          gemini_models: list[str]) -> object:
    """
    Retorna uma função ai_fn(prompt: str) -> str para uso interno
    (Long Context Manager, Reflexão Neural, Self-reflection, etc.).

    v2.3: usa o LLM Router centralizado se disponível.
    Fallback para chamada direta se o router não estiver inicializado.
    """
    def _call(prompt: str) -> str:
        # Tenta usar o Router (Groq/8b — mais rápido para sumarização)
        try:
            from llm_router import get_router
            result = get_router().summarize(prompt)
            if result:
                return result
        except Exception:
            pass

        # Fallback legado — Groq direto
        if groq_client:
            try:
                resp = groq_client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=400,
                    temperature=0.5,
                    timeout=12,
                )
                return resp.choices[0].message.content
            except Exception as e:
                print(f"[NEURAL CORE] Groq (simple call) falhou: {e}")
                # Tenta 70b como segundo fallback
                try:
                    resp = groq_client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=400,
                        temperature=0.5,
                        timeout=15,
                    )
                    return resp.choices[0].message.content
                except Exception as e2:
                    print(f"[NEURAL CORE] Groq 70b (simple call) falhou: {e2}")

        # Gemini apenas como último recurso para texto (evitamos usar para texto puro)
        if gemini_client:
            for model in gemini_models:
                try:
                    resp = gemini_client.models.generate_content(
                        model=model, contents=prompt
                    )
                    return resp.text
                except Exception as e:
                    err = str(e)
                    if "429" in err or "RESOURCE_EXHAUSTED" in err:
                        continue
                    break

        return ""

    return _call