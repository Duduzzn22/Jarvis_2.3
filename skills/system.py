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
import psutil

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

def execute_open_app(params: dict, sid: str) -> str:
    app_name = params.get('app_name', '')
    if not app_name:
        return 'Nenhum aplicativo especificado'
    apps_list  = [a.strip() for a in app_name.split(',') if a.strip()]
    resultados = []
    for app in apps_list:
        cmd = get_app_command(app)
        if not cmd:
            socketio.emit('action_result', {'success': False, 'message': f'{app} não reconhecido'}, room=sid)
            continue

        # ── Instagram: sem app desktop, abre no browser ──────────────────────
        if cmd == '__instagram__':
            try:
                webbrowser.open('https://www.instagram.com')
                socketio.emit('action_result',
                              {'success': True, 'message': 'Instagram aberto no navegador'}, room=sid)
                socketio.emit('open_url', {'url': 'https://www.instagram.com'}, room=sid)
                resultados.append('Instagram')
            except Exception as e:
                socketio.emit('action_result',
                              {'success': False, 'message': f'Erro ao abrir Instagram: {e}'}, room=sid)
            continue

        # ── TikTok: tenta app instalado via URI, fallback para web ───────────
        if cmd == '__tiktok__':
            opened = False
            if platform.system() == 'Windows':
                try:
                    # URI do app TikTok no Windows (Microsoft Store)
                    subprocess.Popen(
                        'start tiktok:', shell=True,
                        creationflags=subprocess.CREATE_NO_WINDOW
                    )
                    opened = True
                except Exception:
                    pass
                if not opened:
                    # Fallback: tenta pelo nome do processo direto
                    try:
                        subprocess.Popen(['TikTok.exe'], shell=False)
                        opened = True
                    except Exception:
                        pass
            elif platform.system() == 'Linux':
                try:
                    subprocess.Popen(['tiktok'], shell=False)
                    opened = True
                except Exception:
                    pass
            if not opened:
                # Último fallback: abre no browser
                webbrowser.open('https://www.tiktok.com')
                socketio.emit('action_result',
                              {'success': True, 'message': 'TikTok aberto no navegador (app não encontrado)'}, room=sid)
            else:
                socketio.emit('action_result',
                              {'success': True, 'message': 'TikTok aberto'}, room=sid)
            resultados.append('TikTok')
            continue

        # ── Apps normais ──────────────────────────────────────────────────────
        try:
            subprocess.Popen(cmd, shell=False)
            socketio.emit('action_result',
                          {'success': True, 'message': f'{app.title()} aberto'}, room=sid)
            resultados.append(app)
            time.sleep(0.3)
        except Exception as e:
            socketio.emit('action_result',
                          {'success': False, 'message': f'Erro ao abrir {app}: {e}'}, room=sid)
    return (f'Aplicativo(s) aberto(s): {", ".join(resultados)}'
            if resultados else 'Não foi possível abrir o aplicativo')

def execute_search_web(params: dict, sid: str) -> str:
    query = params.get('query', '')
    if not query:
        return 'Nenhuma pesquisa especificada'
    url = f'https://www.google.com/search?q={query.replace(" ", "+")}'
    webbrowser.open(url)
    socketio.emit('action_result', {'success': True, 'message': f'Pesquisando: {query}'}, room=sid)
    return f'Pesquisa sobre "{query}" realizada'

def execute_open_youtube(params: dict, sid: str) -> str:
    query = params.get('query', '')
    if not query:
        return 'Nenhuma pesquisa especificada'
    url = f'https://www.youtube.com/results?search_query={query.replace(" ", "+")}'
    webbrowser.open(url)
    socketio.emit('action_result', {'success': True, 'message': f'YouTube: {query}'}, room=sid)
    return f'YouTube aberto com busca por "{query}"'

def execute_system_info(sid: str) -> str:
    cpu  = psutil.cpu_percent(interval=0.5)
    ram  = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    uptime = datetime.datetime.now() - datetime.datetime.fromtimestamp(psutil.boot_time())
    info = (
        f"CPU: {cpu}% | "
        f"RAM: {ram.percent}% ({ram.used // 1024**3}GB de {ram.total // 1024**3}GB) | "
        f"Disco: {disk.percent}% usado | "
        f"Uptime: {str(uptime).split('.')[0]} | "
        f"SO: {platform.system()} {platform.release()}"
    )
    socketio.emit('action_result', {'success': True, 'message': 'Informações coletadas'}, room=sid)
    return info

def execute_manage_files(params: dict, sid: str) -> str:
    operation = params.get('operation', 'list')
    file_path = params.get('file_path', os.path.expanduser('~'))
    try:
        if operation == 'list':
            path = Path(file_path)
            if path.exists() and path.is_dir():
                items = list(path.iterdir())[:20]
                return f'{len(items)} itens em {file_path}: ' + ', '.join(i.name for i in items[:5])
            return f'Caminho não encontrado: {file_path}'
        elif operation == 'open':
            if platform.system() == 'Windows':
                os.startfile(file_path)
            elif platform.system() == 'Darwin':
                subprocess.Popen(['open', file_path])
            else:
                subprocess.Popen(['xdg-open', file_path])
            socketio.emit('action_result', {'success': True, 'message': f'Aberto: {file_path}'}, room=sid)
            return f'Arquivo aberto: {file_path}'
        elif operation == 'create':
            Path(file_path).mkdir(parents=True, exist_ok=True)
            socketio.emit('action_result', {'success': True, 'message': f'Pasta criada: {file_path}'}, room=sid)
            return f'Pasta criada: {file_path}'
    except Exception as e:
        return f'Erro ao gerenciar arquivo: {e}'
    return 'Operação não reconhecida'

def execute_type_text(params: dict, sid: str) -> str:
    """Digita texto via pyautogui."""
    try:
        import pyautogui
        text = params.get('text', '')
        if not text:
            return 'Nenhum texto especificado'
        time.sleep(0.5)
        pyautogui.typewrite(text, interval=0.04)
        socketio.emit('action_result', {'success': True, 'message': f'Digitado: {text[:30]}'}, room=sid)
        return f'Texto digitado: "{text}"'
    except Exception as e:
        return f'Erro ao digitar: {e}'

def execute_open_url(params: dict, sid: str) -> str:
    """Abre uma URL específica no navegador."""
    url = params.get('url', '')
    if not url:
        return 'Nenhuma URL especificada'
    if not url.startswith('http'):
        url = 'https://' + url
    webbrowser.open(url)
    socketio.emit('action_result', {'success': True, 'message': f'Abrindo: {url[:50]}'}, room=sid)
    return f'URL aberta: {url}'

def execute_get_clipboard(params: dict, sid: str) -> str:
    """Lê o conteúdo da área de transferência."""
    try:
        import pyautogui
        import subprocess
        if platform.system() == 'Windows':
            import ctypes
            ctypes.windll.user32.OpenClipboard(0)
            data = ctypes.windll.user32.GetClipboardData(13)
            ctypes.windll.user32.CloseClipboard()
            text = ctypes.c_char_p(data).value
            if text:
                text = text.decode('utf-8', errors='ignore')
        elif platform.system() == 'Darwin':
            text = subprocess.check_output(['pbpaste']).decode('utf-8')
        else:
            text = subprocess.check_output(['xclip', '-selection', 'clipboard', '-o']).decode('utf-8')
        if text:
            text = text.strip()[:500]
            socketio.emit('action_result', {'success': True, 'message': 'Área de transferência lida'}, room=sid)
            return f'Área de transferência contém: "{text}"'
        return 'Área de transferência está vazia'
    except Exception as e:
        return f'Erro ao ler área de transferência: {e}'