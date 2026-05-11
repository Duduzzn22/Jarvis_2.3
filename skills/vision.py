"""
J.A.R.V.I.S. v2.3 — Vision Skills
=====================================
Análise visual de telas, imagens e mídia.

MUDANÇAS v2.3:
  - Gemini é o PRIMÁRIO para visão (melhor qualidade, suporte nativo multimodal)
  - Groq Vision como fallback (llama-4-scout)
  - Ollama Vision como último fallback offline
  - Todo roteamento via LLM Router centralizado
  - Gemini NUNCA é chamado para texto puro (apenas visão)
  - PC Agent preservado integralmente
"""

import os
import base64
import datetime
import logging
import uuid
from pathlib import Path
from threading import Event

logger = logging.getLogger(__name__)


# ─── DummySocketIO ────────────────────────────────────────────────────────────

class DummySocketIO:
    def __init__(self):
        self._emit_fn = None
    def emit(self, *args, **kwargs):
        if self._emit_fn:
            self._emit_fn(*args, **kwargs)

socketio = DummySocketIO()

# ─── Globais injetadas ────────────────────────────────────────────────────────
OLLAMA_AVAILABLE      = False
OLLAMA_BASE_URL       = 'http://localhost:11434'
OLLAMA_VISION_MODEL   = 'llava'
CEREBRAS_AVAILABLE    = False
cerebras_client       = None
GROQ_AVAILABLE        = False
groq_client           = None
GEMINI_AVAILABLE      = False
gemini_client         = None
GEMINI_MODELS         = []
TELEGRAM_BOT_TOKEN    = ''
TELEGRAM_CHAT_ID      = ''
TRELLO_API_KEY        = ''
TRELLO_TOKEN          = ''
TRELLO_BOARD_ID       = ''
ASANA_TOKEN           = ''
ASANA_PROJECT_ID      = ''
NEWS_API_KEY          = ''
NEWS_TOPICS           = []
PC_AGENT_AVAILABLE    = False
get_app_command       = None
get_spotify           = None
run_pc_agent          = None
quick_screen_analysis = None
capture_screen_b64_fn = None
get_all_tasks         = None
add_task              = None
PC_AGENT_SAFE_MODE    = True

_confirm_results  = {}
_pending_confirms = {}


def setup(deps: dict) -> None:
    global socketio, OLLAMA_AVAILABLE, OLLAMA_BASE_URL, OLLAMA_VISION_MODEL
    global CEREBRAS_AVAILABLE, cerebras_client, GROQ_AVAILABLE, groq_client
    global GEMINI_AVAILABLE, gemini_client, GEMINI_MODELS
    global TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    global TRELLO_API_KEY, TRELLO_TOKEN, TRELLO_BOARD_ID
    global ASANA_TOKEN, ASANA_PROJECT_ID
    global NEWS_API_KEY, NEWS_TOPICS
    global PC_AGENT_AVAILABLE, get_app_command, get_spotify
    global run_pc_agent, quick_screen_analysis, capture_screen_b64_fn
    global get_all_tasks, add_task, PC_AGENT_SAFE_MODE

    if 'emit'                 in deps: socketio._emit_fn    = deps['emit']
    if 'OLLAMA_AVAILABLE'     in deps: OLLAMA_AVAILABLE     = deps['OLLAMA_AVAILABLE']
    if 'OLLAMA_BASE_URL'      in deps: OLLAMA_BASE_URL      = deps['OLLAMA_BASE_URL']
    if 'OLLAMA_VISION_MODEL'  in deps: OLLAMA_VISION_MODEL  = deps['OLLAMA_VISION_MODEL']
    if 'GROQ_AVAILABLE'       in deps: GROQ_AVAILABLE       = deps['GROQ_AVAILABLE']
    if 'groq_client'          in deps: groq_client          = deps['groq_client']
    if 'GEMINI_AVAILABLE'     in deps: GEMINI_AVAILABLE     = deps['GEMINI_AVAILABLE']
    if 'gemini_client'        in deps: gemini_client        = deps['gemini_client']
    if 'GEMINI_MODELS'        in deps: GEMINI_MODELS        = deps['GEMINI_MODELS']
    if 'TELEGRAM_BOT_TOKEN'   in deps: TELEGRAM_BOT_TOKEN   = deps['TELEGRAM_BOT_TOKEN']
    if 'TELEGRAM_CHAT_ID'     in deps: TELEGRAM_CHAT_ID     = deps['TELEGRAM_CHAT_ID']
    if 'PC_AGENT_AVAILABLE'   in deps: PC_AGENT_AVAILABLE   = deps['PC_AGENT_AVAILABLE']
    if 'get_app_command'      in deps: get_app_command      = deps['get_app_command']
    if 'get_spotify'          in deps: get_spotify          = deps['get_spotify']
    if 'run_pc_agent'         in deps: run_pc_agent         = deps['run_pc_agent']
    if 'quick_screen_analysis'in deps: quick_screen_analysis = deps['quick_screen_analysis']
    if 'capture_screen_b64'   in deps: capture_screen_b64_fn = deps['capture_screen_b64']
    if 'get_all_tasks'        in deps: get_all_tasks        = deps['get_all_tasks']
    if 'add_task'             in deps: add_task             = deps['add_task']
    if 'PC_AGENT_SAFE_MODE'   in deps: PC_AGENT_SAFE_MODE   = deps['PC_AGENT_SAFE_MODE']
    # Compatibilidade com nomes antigos
    if 'TRELLO_API_KEY'    in deps: TRELLO_API_KEY    = deps['TRELLO_API_KEY']
    if 'TRELLO_TOKEN'      in deps: TRELLO_TOKEN      = deps['TRELLO_TOKEN']
    if 'TRELLO_BOARD_ID'   in deps: TRELLO_BOARD_ID   = deps['TRELLO_BOARD_ID']
    if 'ASANA_TOKEN'       in deps: ASANA_TOKEN       = deps['ASANA_TOKEN']
    if 'ASANA_PROJECT_ID'  in deps: ASANA_PROJECT_ID  = deps['ASANA_PROJECT_ID']
    if 'NEWS_API_KEY'      in deps: NEWS_API_KEY      = deps['NEWS_API_KEY']
    if 'NEWS_TOPICS'       in deps: NEWS_TOPICS       = deps['NEWS_TOPICS']
    if 'CEREBRAS_AVAILABLE'in deps: pass  # não usado mais
    if 'cerebras_client'   in deps: pass


# ─── Captura de tela ──────────────────────────────────────────────────────────

def _capture_screen_jpeg_b64(max_width: int = 1280, quality: int = 72) -> tuple[str, float]:
    """
    Captura a tela e retorna (jpeg_b64, size_kb).
    JPEG comprimido — muito mais rápido que PNG.
    """
    import PIL.ImageGrab as ImageGrab
    from PIL import Image
    import io

    screenshot = ImageGrab.grab()
    orig_w, orig_h = screenshot.size
    if orig_w > max_width:
        ratio      = max_width / orig_w
        screenshot = screenshot.resize(
            (max_width, int(orig_h * ratio)), Image.LANCZOS
        )
    buf = io.BytesIO()
    screenshot.convert('RGB').save(buf, format='JPEG', quality=quality, optimize=True)
    b64     = base64.b64encode(buf.getvalue()).decode('utf-8')
    size_kb = round(len(buf.getvalue()) / 1024, 1)
    logger.info(f"[VISION] Screenshot JPEG: {screenshot.size[0]}x{screenshot.size[1]} | {size_kb} KB")
    return b64, size_kb

# Alias PNG para compatibilidade com pc_agent
def _capture_screen_png_b64() -> str:
    b64, _ = _capture_screen_jpeg_b64(max_width=1280, quality=75)
    return b64


# ─── Análise de tela via Router ───────────────────────────────────────────────

def _analyze_screen_with_router(img_b64: str, query: str) -> str | None:
    """Usa LLM Router para análise de visão (Gemini → Groq → Ollama)."""
    try:
        from llm_router import get_router
        return get_router().vision(img_b64, query)
    except ImportError:
        logger.warning("[VISION] llm_router não disponível — usando fallback legado")
        return _legacy_vision(img_b64, query)


def _legacy_vision(img_b64: str, query: str) -> str | None:
    """Fallback legado de visão (compatibilidade sem router)."""
    full_q = f"Analise esta captura de tela e responda em português brasileiro: {query}"

    # Gemini
    if GEMINI_AVAILABLE and gemini_client:
        for model in ('gemini-2.0-flash', 'gemini-1.5-flash'):
            try:
                resp = gemini_client.models.generate_content(
                    model=model,
                    contents=[{"role": "user", "parts": [
                        {"text": full_q},
                        {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}},
                    ]}]
                )
                return resp.text.strip()
            except Exception as e:
                err = str(e)
                if '429' in err or 'quota' in err.lower():
                    continue
                break

    # Groq Vision
    if GROQ_AVAILABLE and groq_client:
        for model in ('meta-llama/llama-4-scout-17b-16e-instruct', 'llama-3.2-11b-vision-preview'):
            try:
                resp = groq_client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": [
                        {"type": "text", "text": full_q},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                    ]}],
                    max_tokens=600, temperature=0.3, timeout=25,
                )
                return resp.choices[0].message.content.strip()
            except Exception:
                continue

    return None


# ─── Executores de visão ──────────────────────────────────────────────────────

def execute_analyze_screen(params: dict, sid: str) -> str:
    """Captura e analisa tela completa."""
    try:
        socketio.emit('status_update', {'step': 'thinking', 'message': 'Capturando tela...'}, room=sid)
        img_b64, size_kb = _capture_screen_jpeg_b64()
        socketio.emit('status_update', {'step': 'thinking', 'message': f'Analisando ({size_kb} KB)...'}, room=sid)

        query     = params.get('query', 'Descreva o que está acontecendo nesta tela em detalhes.')
        resultado = _analyze_screen_with_router(img_b64, query)

        if resultado:
            socketio.emit('action_result', {'success': True, 'message': 'Tela analisada'}, room=sid)
            return resultado

        return (
            'Não foi possível analisar a tela, Senhor. '
            'Verifique se Gemini ou Groq estão configurados no .env.'
        )

    except ImportError:
        return 'Pillow não instalado — execute: pip install pillow'
    except Exception as e:
        logger.error(f"[VISION] execute_analyze_screen: {e}")
        return f'Erro ao analisar tela: {e}'


def execute_analyze_screen_quick(params: dict, sid: str) -> str:
    """Análise rápida de tela (resolução menor, mais veloz)."""
    query = params.get('query', 'O que está na minha tela agora?')
    socketio.emit('status_update', {'step': 'thinking', 'message': 'Capturando e analisando...'}, room=sid)

    try:
        img_b64, size_kb = _capture_screen_jpeg_b64(max_width=1024, quality=65)
    except ImportError:
        return 'Pillow não instalado — execute: pip install pillow'
    except Exception as e:
        return f'Erro ao capturar tela: {e}'

    resultado = _analyze_screen_with_router(img_b64, query)
    if resultado:
        socketio.emit('action_result', {'success': True, 'message': 'Tela analisada'}, room=sid)
        return resultado

    return (
        'Não consegui analisar a tela, Senhor. '
        'Verifique as credenciais do Gemini no .env.'
    )


def execute_take_screenshot(params: dict, sid: str) -> str:
    """Salva screenshot na área de trabalho."""
    try:
        import PIL.ImageGrab as ImageGrab
        desktop  = Path.home() / 'Desktop'
        desktop.mkdir(exist_ok=True)
        filename = f'jarvis_screenshot_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.png'
        filepath = desktop / filename
        ImageGrab.grab().save(str(filepath))
        socketio.emit('action_result', {'success': True, 'message': f'Screenshot: {filename}'}, room=sid)
        return f'Screenshot salvo na área de trabalho: {filename}'
    except Exception as e:
        return f'Erro ao capturar tela: {e}'


def execute_analyze_media(
    params:     dict,
    sid:        str,
    image_data: bytes | None = None,
    mime_type:  str = 'image/jpeg',
) -> str:
    """
    Analisa imagem enviada pelo usuário.
    Aceita: bytes diretos, arquivo local ou URL.
    Rota via LLM Router: Gemini (primário) → Groq Vision → Ollama Vision.
    """
    import io
    import requests as req

    query     = params.get('query', 'Descreva esta imagem em detalhes em português brasileiro.')
    file_path = params.get('file_path', '')
    url       = params.get('url', '')

    socketio.emit('status_update', {'step': 'thinking', 'message': 'Analisando imagem...'}, room=sid)

    try:
        if image_data:
            img_b64 = base64.b64encode(image_data).decode('utf-8')
        elif file_path and os.path.exists(file_path):
            ext       = Path(file_path).suffix.lower()
            mime_type = {
                '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                '.png': 'image/png',  '.gif': 'image/gif',
                '.webp': 'image/webp', '.bmp': 'image/bmp',
            }.get(ext, 'image/jpeg')
            with open(file_path, 'rb') as f:
                img_b64 = base64.b64encode(f.read()).decode('utf-8')
        elif url:
            response  = req.get(url, timeout=10)
            mime_type = response.headers.get('content-type', 'image/jpeg').split(';')[0]
            img_b64   = base64.b64encode(response.content).decode('utf-8')
        else:
            return 'Nenhuma imagem fornecida para análise'

        # Usa o Router (Gemini primeiro para imagens — é o melhor)
        try:
            from llm_router import get_router
            resultado = get_router().vision(img_b64, query, mime_type)
        except ImportError:
            resultado = _legacy_vision(img_b64, query)

        if resultado:
            socketio.emit('action_result', {'success': True, 'message': 'Imagem analisada'}, room=sid)
            return resultado

        return 'Não foi possível analisar a imagem no momento, Senhor.'

    except Exception as e:
        logger.error(f"[VISION] execute_analyze_media: {e}")
        return f'Erro ao analisar imagem: {e}'


def execute_pc_agent_task(params: dict, sid: str) -> str:
    """
    Executa tarefa autônoma no PC usando visão + controle.
    PC Agent é o modo mais avançado — vê a tela, planeja e age em loop.
    Gemini é o motor de visão preferencial para o PC Agent (mais preciso).
    """
    if not PC_AGENT_AVAILABLE:
        return 'PC Agent não disponível, Senhor. Execute: pip install pyautogui pillow'

    task = params.get('task', '') or params.get('query', '')
    if not task:
        return 'Nenhuma tarefa especificada para o agente de PC, Senhor.'

    from pc_agent import get_agent_status
    status_info = get_agent_status()
    if not status_info.get('available'):
        return 'O agente de PC já está executando uma tarefa, Senhor. Aguarde.'

    socketio.emit('status_update', {
        'step':    'pc_agent',
        'message': f'Agente de PC: {task[:60]}...',
    }, room=sid)

    def _confirm_fn(action_dict: dict) -> bool:
        action     = action_dict.get('action', '')
        reason     = action_dict.get('reason', '')
        confirm_id = str(uuid.uuid4())
        ev         = Event()
        _confirm_results[confirm_id]  = False
        _pending_confirms[confirm_id] = ev
        socketio.emit('confirm_action', {
            'id':     confirm_id,
            'intent': 'pc_agent_action',
            'action': f'Ação do PC Agent: {action}',
            'detail': reason,
        }, room=sid)
        confirmed = ev.wait(timeout=20)
        result    = _confirm_results.pop(confirm_id, False)
        _pending_confirms.pop(confirm_id, None)
        return result if confirmed else False

    # Passa gemini_client para o PC Agent (é o melhor para visão de tela)
    result = run_pc_agent(
        task          = task,
        gemini_client = gemini_client,
        socketio_emit = socketio.emit,
        sid           = sid,
        max_iterations = 10,
        confirm_fn    = _confirm_fn,
        safe_mode     = PC_AGENT_SAFE_MODE,
    )

    if result.get('success'):
        n_actions = len(result.get('actions', []))
        iters     = result.get('iterations', 0)
        socketio.emit('action_result', {
            'success': True, 'message': f'Tarefa concluída em {iters} etapa(s)',
        }, room=sid)
        return (
            f'Tarefa concluída com sucesso, Senhor. '
            f'Executei {n_actions} ação(ões) em {iters} etapa(s). '
            f'{result.get("summary", "")}'
        )

    final      = result.get('final_status', 'failed')
    status_map = {
        'failed':                 'não foi possível completar a tarefa',
        'needs_input':            'aguardo seu input para continuar',
        'max_iterations_reached': 'atingi o limite de etapas sem concluir',
    }
    motivo = status_map.get(final, final)
    socketio.emit('action_result', {'success': False, 'message': f'Agente: {motivo}'}, room=sid)
    return f'Senhor, {motivo}. {result.get("summary", "")}'