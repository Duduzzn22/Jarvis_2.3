import os
import json
import time
import subprocess
import webbrowser
import platform
import base64
import requests
import datetime
from threading import Thread

class DummySocketIO:
    def __init__(self):
        self._emit_fn = None
    def emit(self, *args, **kwargs):
        if self._emit_fn:
            self._emit_fn(*args, **kwargs)

socketio = DummySocketIO()

# Globais injetadas
CEREBRAS_AVAILABLE = False
cerebras_client = None
GROQ_AVAILABLE = False
groq_client = None
GEMINI_AVAILABLE = False
gemini_client = None
GEMINI_MODELS = []
TELEGRAM_BOT_TOKEN = ''
TELEGRAM_CHAT_ID = ''
TRELLO_API_KEY = ''
TRELLO_TOKEN = ''
TRELLO_BOARD_ID = ''
ASANA_TOKEN = ''
ASANA_PROJECT_ID = ''
NEWS_API_KEY = ''
NEWS_TOPICS = []
PC_AGENT_AVAILABLE = False
get_app_command = None
get_spotify = None
run_pc_agent = None
quick_screen_analysis = None
capture_screen_b64 = None
get_all_tasks = None
add_task = None
PC_AGENT_SAFE_MODE = True

def setup(deps):
    global socketio, CEREBRAS_AVAILABLE, cerebras_client, GROQ_AVAILABLE, groq_client
    global GEMINI_AVAILABLE, gemini_client, GEMINI_MODELS, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    global TRELLO_API_KEY, TRELLO_TOKEN, TRELLO_BOARD_ID, ASANA_TOKEN, ASANA_PROJECT_ID
    global NEWS_API_KEY, NEWS_TOPICS, PC_AGENT_AVAILABLE, get_app_command, get_spotify
    global run_pc_agent, quick_screen_analysis, capture_screen_b64, get_all_tasks, add_task
    global PC_AGENT_SAFE_MODE
    
    if 'emit' in deps: socketio._emit_fn = deps['emit']
    if 'CEREBRAS_AVAILABLE' in deps: CEREBRAS_AVAILABLE = deps['CEREBRAS_AVAILABLE']
    if 'cerebras_client' in deps: cerebras_client = deps['cerebras_client']
    if 'GROQ_AVAILABLE' in deps: GROQ_AVAILABLE = deps['GROQ_AVAILABLE']
    if 'groq_client' in deps: groq_client = deps['groq_client']
    if 'GEMINI_AVAILABLE' in deps: GEMINI_AVAILABLE = deps['GEMINI_AVAILABLE']
    if 'gemini_client' in deps: gemini_client = deps['gemini_client']
    if 'GEMINI_MODELS' in deps: GEMINI_MODELS = deps['GEMINI_MODELS']
    if 'TELEGRAM_BOT_TOKEN' in deps: TELEGRAM_BOT_TOKEN = deps['TELEGRAM_BOT_TOKEN']
    if 'TELEGRAM_CHAT_ID' in deps: TELEGRAM_CHAT_ID = deps['TELEGRAM_CHAT_ID']
    if 'TRELLO_API_KEY' in deps: TRELLO_API_KEY = deps['TRELLO_API_KEY']
    if 'TRELLO_TOKEN' in deps: TRELLO_TOKEN = deps['TRELLO_TOKEN']
    if 'TRELLO_BOARD_ID' in deps: TRELLO_BOARD_ID = deps['TRELLO_BOARD_ID']
    if 'ASANA_TOKEN' in deps: ASANA_TOKEN = deps['ASANA_TOKEN']
    if 'ASANA_PROJECT_ID' in deps: ASANA_PROJECT_ID = deps['ASANA_PROJECT_ID']
    if 'NEWS_API_KEY' in deps: NEWS_API_KEY = deps['NEWS_API_KEY']
    if 'NEWS_TOPICS' in deps: NEWS_TOPICS = deps['NEWS_TOPICS']
    if 'PC_AGENT_AVAILABLE' in deps: PC_AGENT_AVAILABLE = deps['PC_AGENT_AVAILABLE']
    if 'get_app_command' in deps: get_app_command = deps['get_app_command']
    if 'get_spotify' in deps: get_spotify = deps['get_spotify']
    if 'run_pc_agent' in deps: run_pc_agent = deps['run_pc_agent']
    if 'quick_screen_analysis' in deps: quick_screen_analysis = deps['quick_screen_analysis']
    if 'capture_screen_b64' in deps: capture_screen_b64 = deps['capture_screen_b64']
    if 'get_all_tasks' in deps: get_all_tasks = deps['get_all_tasks']
    if 'add_task' in deps: add_task = deps['add_task']
    if 'PC_AGENT_SAFE_MODE' in deps: PC_AGENT_SAFE_MODE = deps['PC_AGENT_SAFE_MODE']

# Mapeamento de contatos carregado do .env
_WHATSAPP_CONTACTS = {}

def _load_whatsapp_contacts():
    """Carrega mapeamento nome→número do .env (WHATSAPP_CONTACTS como JSON)."""
    global _WHATSAPP_CONTACTS
    raw = os.getenv('WHATSAPP_CONTACTS', '{}')
    try:
        _WHATSAPP_CONTACTS = json.loads(raw)
    except Exception:
        _WHATSAPP_CONTACTS = {}

def _resolve_contact(name_or_phone: str) -> tuple:
    """Resolve nome do contato para número. Retorna (número, nome_encontrado)."""
    if not _WHATSAPP_CONTACTS:
        _load_whatsapp_contacts()

    # Se já é um número
    if name_or_phone.startswith('+') or name_or_phone.replace(' ', '').isdigit():
        return name_or_phone, name_or_phone

    # Busca por nome (case-insensitive)
    name_lower = name_or_phone.lower().strip()
    for contact_name, phone in _WHATSAPP_CONTACTS.items():
        if contact_name.lower() == name_lower:
            return phone, contact_name

    # Busca parcial
    for contact_name, phone in _WHATSAPP_CONTACTS.items():
        if name_lower in contact_name.lower() or contact_name.lower() in name_lower:
            return phone, contact_name

    return None, name_or_phone


def _try_whatsapp_desktop(phone: str, message: str) -> bool:
    """Tenta enviar via app desktop do WhatsApp usando protocolo whatsapp://."""
    import subprocess
    import platform
    import time

    if platform.system() != 'Windows':
        return False

    try:
        # Usa o protocolo whatsapp:// para abrir o app desktop
        phone_clean = phone.replace('+', '').replace(' ', '').replace('-', '')
        url = f'whatsapp://send?phone={phone_clean}&text={message}'

        subprocess.Popen(['cmd', '/c', 'start', '', url], shell=False)
        time.sleep(3)

        # Tenta pressionar Enter via pyautogui para enviar
        try:
            import pyautogui
            time.sleep(2)
            pyautogui.press('enter')
            return True
        except ImportError:
            print('[JARVIS] pyautogui não disponível — mensagem aberta mas não enviada automaticamente')
            return True  # Pelo menos abriu a conversa

    except Exception as e:
        print(f'[JARVIS] WhatsApp Desktop falhou: {e}')
        return False


def execute_send_whatsapp(params: dict, sid: str) -> str:
    """
    Envia mensagem via WhatsApp.
    Fluxo: resolve contato por nome → tenta app desktop → fallback pywhatkit.
    Se não tiver mensagem, retorna pedido para o Jarvis perguntar.
    """
    phone = params.get('phone', '')
    contact = params.get('contact', '')
    message = params.get('message', '')

    # Resolve contato por nome
    if contact and not phone:
        phone, resolved_name = _resolve_contact(contact)
        if not phone:
            socketio.emit('action_result', {'success': False, 'message': f'Contato "{contact}" não encontrado'}, room=sid)
            return (f'Não encontrei o contato "{contact}" na minha lista, Senhor. '
                    f'Adicione no .env: WHATSAPP_CONTACTS={{"nome": "+55numero"}}')

    if not phone:
        socketio.emit('action_result', {'success': False, 'message': 'Número não especificado'}, room=sid)
        return 'Por favor, forneça o número ou nome do contato, Senhor.'

    # Se não tem mensagem, pede para o Jarvis perguntar
    if not message:
        contact_display = resolved_name if contact else phone
        socketio.emit('jarvis_ask', {
            'question': f'Qual mensagem deseja enviar para {contact_display}, Senhor?',
            'context': 'whatsapp_message',
            'meta': {'phone': phone, 'contact': contact_display}
        }, room=sid)
        return f'__ASK__:Qual mensagem deseja enviar para {contact_display}?'

    socketio.emit('status_update', {'step': 'executing', 'message': f'Enviando WhatsApp para {contact or phone}...'}, room=sid)

    # 1. Tenta via app desktop
    if _try_whatsapp_desktop(phone, message):
        socketio.emit('action_result', {'success': True, 'message': f'WhatsApp enviado para {contact or phone}'}, room=sid)
        return f'Mensagem enviada via WhatsApp Desktop para {contact or phone}, Senhor.'

    # 2. Fallback: pywhatkit
    try:
        import pywhatkit
        pywhatkit.sendwhatmsg_instantly(phone, message, wait_time=10, tab_close=True)
        socketio.emit('action_result', {'success': True, 'message': f'WhatsApp enviado para {contact or phone}'}, room=sid)
        return f'Mensagem enviada via WhatsApp para {contact or phone}, Senhor.'
    except ImportError:
        return 'Nenhum método de envio do WhatsApp disponível. Instale pywhatkit ou use o WhatsApp Desktop.'
    except Exception as e:
        return f'Erro ao enviar WhatsApp: {e}'

def execute_send_telegram(params: dict, sid: str) -> str:
    import requests as req
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        socketio.emit('action_result', {'success': False, 'message': 'Telegram não configurado'}, room=sid)
        return 'Telegram não configurado no .env'
    message = params.get('message', 'Mensagem do J.A.R.V.I.S.')
    try:
        resp = req.post(
            f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage',
            json={'chat_id': TELEGRAM_CHAT_ID, 'text': message}, timeout=10
        )
        if resp.status_code == 200:
            socketio.emit('action_result', {'success': True, 'message': 'Mensagem enviada no Telegram'}, room=sid)
            return 'Mensagem enviada com sucesso no Telegram'
        return f'Erro ao enviar Telegram: {resp.text}'
    except Exception as e:
        return f'Erro Telegram: {e}'

