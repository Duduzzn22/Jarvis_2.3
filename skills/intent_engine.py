"""
J.A.R.V.I.S. v2.3 — Intent Engine
====================================
Detecta a intenção da mensagem do usuário.

MUDANÇAS v2.3:
  - Usa LLM Router centralizado (Groq/8b como primário — 3x mais rápido)
  - Gemini REMOVIDO do pipeline de intent (desnecessário e lento para classificação)
  - Cache LRU 30s embutido no Router (zero latência para intents repetidas)
  - Detecções locais expandidas (mais casos cobertos sem chamar IA)
"""

import re
import json
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)


# ─── DummySocketIO (compatibilidade com arquitetura de skills) ────────────────

class DummySocketIO:
    def __init__(self):
        self._emit_fn = None
    def emit(self, *args, **kwargs):
        if self._emit_fn:
            self._emit_fn(*args, **kwargs)

socketio = DummySocketIO()

# ─── Globais injetadas via setup() ───────────────────────────────────────────
# Mantidas por compatibilidade — o Router é buscado dinamicamente
OLLAMA_AVAILABLE   = False
OLLAMA_BASE_URL    = 'http://localhost:11434'
OLLAMA_MODEL       = 'llama3'
CEREBRAS_AVAILABLE = False
cerebras_client    = None
GROQ_AVAILABLE     = False
groq_client        = None
GEMINI_AVAILABLE   = False
gemini_client      = None
GEMINI_MODELS      = []
TELEGRAM_BOT_TOKEN = ''
TELEGRAM_CHAT_ID   = ''
TRELLO_API_KEY     = ''
TRELLO_TOKEN       = ''
TRELLO_BOARD_ID    = ''
ASANA_TOKEN        = ''
ASANA_PROJECT_ID   = ''
NEWS_API_KEY       = ''
NEWS_TOPICS        = []
PC_AGENT_AVAILABLE = False
get_app_command    = None
get_spotify        = None
run_pc_agent       = None
quick_screen_analysis  = None
capture_screen_b64     = None
get_all_tasks      = None
add_task           = None
PC_AGENT_SAFE_MODE = True


def setup(deps: dict) -> None:
    global socketio, OLLAMA_AVAILABLE, OLLAMA_BASE_URL, OLLAMA_MODEL
    global CEREBRAS_AVAILABLE, cerebras_client, GROQ_AVAILABLE, groq_client
    global GEMINI_AVAILABLE, gemini_client, GEMINI_MODELS
    global TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    global TRELLO_API_KEY, TRELLO_TOKEN, TRELLO_BOARD_ID
    global ASANA_TOKEN, ASANA_PROJECT_ID
    global NEWS_API_KEY, NEWS_TOPICS
    global PC_AGENT_AVAILABLE, get_app_command, get_spotify
    global run_pc_agent, quick_screen_analysis, capture_screen_b64
    global get_all_tasks, add_task, PC_AGENT_SAFE_MODE

    if 'emit'              in deps: socketio._emit_fn  = deps['emit']
    if 'OLLAMA_AVAILABLE'  in deps: OLLAMA_AVAILABLE   = deps['OLLAMA_AVAILABLE']
    if 'OLLAMA_BASE_URL'   in deps: OLLAMA_BASE_URL    = deps['OLLAMA_BASE_URL']
    if 'OLLAMA_MODEL'      in deps: OLLAMA_MODEL       = deps['OLLAMA_MODEL']
    if 'GROQ_AVAILABLE'    in deps: GROQ_AVAILABLE     = deps['GROQ_AVAILABLE']
    if 'groq_client'       in deps: groq_client        = deps['groq_client']
    if 'GEMINI_AVAILABLE'  in deps: GEMINI_AVAILABLE   = deps['GEMINI_AVAILABLE']
    if 'gemini_client'     in deps: gemini_client      = deps['gemini_client']
    if 'GEMINI_MODELS'     in deps: GEMINI_MODELS      = deps['GEMINI_MODELS']
    if 'TELEGRAM_BOT_TOKEN'in deps: TELEGRAM_BOT_TOKEN = deps['TELEGRAM_BOT_TOKEN']
    if 'TELEGRAM_CHAT_ID'  in deps: TELEGRAM_CHAT_ID   = deps['TELEGRAM_CHAT_ID']
    if 'TRELLO_API_KEY'    in deps: TRELLO_API_KEY     = deps['TRELLO_API_KEY']
    if 'TRELLO_TOKEN'      in deps: TRELLO_TOKEN       = deps['TRELLO_TOKEN']
    if 'TRELLO_BOARD_ID'   in deps: TRELLO_BOARD_ID    = deps['TRELLO_BOARD_ID']
    if 'ASANA_TOKEN'       in deps: ASANA_TOKEN        = deps['ASANA_TOKEN']
    if 'ASANA_PROJECT_ID'  in deps: ASANA_PROJECT_ID   = deps['ASANA_PROJECT_ID']
    if 'NEWS_API_KEY'      in deps: NEWS_API_KEY       = deps['NEWS_API_KEY']
    if 'NEWS_TOPICS'       in deps: NEWS_TOPICS        = deps['NEWS_TOPICS']
    if 'PC_AGENT_AVAILABLE'in deps: PC_AGENT_AVAILABLE = deps['PC_AGENT_AVAILABLE']
    if 'get_app_command'   in deps: get_app_command    = deps['get_app_command']
    if 'get_spotify'       in deps: get_spotify        = deps['get_spotify']
    if 'run_pc_agent'      in deps: run_pc_agent       = deps['run_pc_agent']
    if 'quick_screen_analysis' in deps: quick_screen_analysis = deps['quick_screen_analysis']
    if 'capture_screen_b64'    in deps: capture_screen_b64    = deps['capture_screen_b64']
    if 'get_all_tasks'     in deps: get_all_tasks      = deps['get_all_tasks']
    if 'add_task'          in deps: add_task           = deps['add_task']
    if 'PC_AGENT_SAFE_MODE'in deps: PC_AGENT_SAFE_MODE = deps['PC_AGENT_SAFE_MODE']


# ─── Prompt de intenção ───────────────────────────────────────────────────────

INTENT_PROMPT = """Analise o texto abaixo e retorne APENAS um JSON com a intenção detectada.

Texto: "{text}"

INTENÇÕES ESPECIAIS:
- "protocol_work_time": SE o texto contiver "hora do papai trabalhar", "protocolo papai",
  "protocolo trabalho", "papai vai trabalhar", "hora de trabalhar papai".
- "get_news": SE pedir notícias, manchetes, novidades. Extraia tópico em "query".
- "trello_action": SE mencionar Trello (criar card, listar, mover, ver board).
- "asana_action": SE mencionar Asana (criar tarefa, listar, completar).
- "pc_agent_task": SE pedir para EXECUTAR algo no PC com múltiplos passos. Campo "task".
- "analyze_screen_quick": SE pedir para DESCREVER o que está na tela. Campo "query".
- "instagram_post": SE pedir para postar imagem no Instagram/feed. Campo "caption".
- "instagram_story": SE pedir para postar nos stories do Instagram.
- "instagram_dm": SE pedir DM no Instagram. Campos "contact" e "message".
- "send_whatsapp": SE pedir mensagem no WhatsApp. Campos "contact", "phone", "message".
  Se NÃO houver mensagem explícita, deixe "message" vazio.
- "google_sheets": SE pedir planilha/excel/sheets. Campos "action", "title", "description".
- "google_calendar": SE pedir agenda/evento/reunião. Campos "action", "title", "date", "time".
- "google_maps": SE pedir mapa/rota/como chegar. Campos "action", "query", "origin".

Para "trello_action" e "asana_action":
- "action": create|list|complete|move|delete
- "title", "description", "due_date" (YYYY-MM-DD), "priority" (high|medium|low), "list_name"

Retorne SOMENTE este JSON, sem markdown:
{{
  "intent": "open_app|search_web|open_youtube|send_whatsapp|send_telegram|spotify_control|control_music|manage_files|system_info|analyze_screen|get_weather|open_url|type_text|take_screenshot|get_clipboard|get_news|trello_action|asana_action|protocol_work_time|pc_agent_task|analyze_screen_quick|instagram_post|instagram_story|instagram_dm|google_sheets|google_calendar|google_maps|conversation",
  "params": {{
    "app_name": "",
    "query": "",
    "task": "",
    "contact": "",
    "phone": "",
    "message": "",
    "caption": "",
    "action": "",
    "volume": 50,
    "file_path": "",
    "operation": "",
    "url": "",
    "text": "",
    "city": "",
    "title": "",
    "description": "",
    "date": "",
    "time": "",
    "due_date": "",
    "priority": "",
    "list_name": "",
    "origin": "",
    "count": 3
  }}
}}"""


# ─── Detecção local rápida (zero custo de IA) ─────────────────────────────────

# Keywords que NUNCA são conversa pura
_ACTION_KWS = frozenset((
    'abre', 'abrir', 'toca', 'pause', 'busca', 'pesquisa', 'spotify',
    'youtube', 'notícia', 'clima', 'tempo', 'whatsapp', 'telegram',
    'trello', 'screenshot', 'tela', 'arquivo', 'url', 'site',
    'papai', 'instagram', 'insta', 'story', 'stories', 'poste',
    'posta', 'post', 'planilha', 'excel', 'sheets', 'agenda',
    'calendar', 'calendário', 'evento', 'compromisso', 'reunião',
    'maps', 'mapa', 'rota', 'caminho', 'mande', 'envie', 'envia',
    'mensagem', 'msg', 'asana', 'abra', 'inicia', 'lança',
))


def _is_pure_conversation(text: str) -> bool:
    """Heurística: se curto e sem keywords de ação, é conversa."""
    t = text.strip().lower()
    if len(t) < 15 and not any(kw in t for kw in _ACTION_KWS):
        return True
    return False


def _detect_local(text: str) -> dict | None:
    """
    Detecta intenções comuns sem chamar IA.
    Retorna dict ou None se não reconheceu.
    """
    t = text.lower().strip()

    # Protocolo trabalho
    if any(kw in t for kw in (
        'hora do papai trabalhar', 'protocolo papai',
        'protocolo trabalho', 'papai vai trabalhar', 'hora de trabalhar papai',
    )):
        return {"intent": "protocol_work_time", "params": {}}

    # Instagram stories
    if any(kw in t for kw in ('instagram', 'insta')):
        if any(kw in t for kw in ('story', 'stories', 'storie')):
            return {"intent": "instagram_story", "params": {}}
        if any(kw in t for kw in ('post', 'posta', 'poste', 'publica', 'feed')):
            caption = ''
            for sep in ('legenda', 'caption', 'com a legenda', 'escrito'):
                if sep in t:
                    caption = text[t.index(sep) + len(sep):].strip().strip('"\'')
                    break
            return {"intent": "instagram_post", "params": {"caption": caption}}

    # Google Maps
    for prefix in ('rota para', 'caminho para', 'como chegar em',
                   'como chegar ao', 'como chegar à', 'como chegar na',
                   'como chegar no', 'como ir para', 'como ir ao', 'como ir à'):
        if prefix in t:
            query = text[t.index(prefix) + len(prefix):].strip()
            if query:
                return {"intent": "google_maps", "params": {"action": "route", "query": query}}

    # Google Sheets
    if any(kw in t for kw in (
        'crie uma planilha', 'criar planilha', 'cria uma planilha',
        'abra o excel', 'planilha sobre', 'planilha de',
    )):
        return {"intent": "google_sheets", "params": {
            "action": "create", "title": "Planilha Jarvis", "description": text
        }}

    # Google Calendar — listar
    if any(kw in t for kw in (
        'minha agenda', 'meus compromissos', 'meus eventos',
        'próximos eventos', 'agenda de hoje', 'agenda de amanhã',
    )):
        return {"intent": "google_calendar", "params": {"action": "list"}}

    # Screenshot
    if any(kw in t for kw in ('screenshot', 'print da tela', 'captura de tela', 'printscreen')):
        return {"intent": "take_screenshot", "params": {}}

    # Spotify — controles rápidos
    if 'próxima' in t or 'pula música' in t or 'next track' in t:
        return {"intent": "spotify_control", "params": {"action": "next"}}
    if 'música anterior' in t or 'volta música' in t:
        return {"intent": "spotify_control", "params": {"action": "previous"}}
    if t in ('pause', 'pausa', 'pausa a música', 'pause a música'):
        return {"intent": "spotify_control", "params": {"action": "pause"}}

    return None


# ─── detect_intent — ponto de entrada ────────────────────────────────────────

def detect_intent(text: str) -> dict:
    """
    Pipeline de detecção de intenção v2.3.

    1. Detecção local instantânea (0 ms)
    2. Heurística de conversa pura (0 ms)
    3. LLM Router → Groq/8b → Groq/70b → Ollama (cache embutido)
    """
    # 1. Detecções locais determinísticas
    local = _detect_local(text)
    if local:
        logger.info(f"[INTENT] Local: {local['intent']}")
        return local

    # 2. Conversa pura — economiza chamada de IA
    if _is_pure_conversation(text):
        logger.info("[INTENT] Conversa pura (local)")
        return {"intent": "conversation", "params": {}, "source": "local"}

    # 3. LLM Router (Groq/8b → Groq/70b → Ollama, com cache)
    try:
        from llm_router import get_router
        router = get_router()
        prompt = INTENT_PROMPT.format(text=text)
        result = router.intent(text, prompt)
        return result
    except ImportError:
        # Fallback legacy se router não estiver disponível
        logger.warning("[INTENT] llm_router não disponível — usando fallback legado")
        return _legacy_intent(text)


def _legacy_intent(text: str) -> dict:
    """Fallback para quando o router não está disponível (compatibilidade)."""
    prompt = INTENT_PROMPT.format(text=text)

    if GROQ_AVAILABLE and groq_client:
        for model in ('llama-3.1-8b-instant', 'llama-3.3-70b-versatile'):
            try:
                resp = groq_client.chat.completions.create(
                    model=model,
                    messages=[{'role': 'user', 'content': prompt}],
                    max_tokens=140, temperature=0.0, timeout=6,
                )
                raw = resp.choices[0].message.content.strip()
                raw = raw.replace('```json', '').replace('```', '').strip()
                result = json.loads(raw)
                logger.info(f"[INTENT] Legacy groq/{model}: {result.get('intent')}")
                return result
            except Exception:
                continue

    return {"intent": "conversation", "params": {}}