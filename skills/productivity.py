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
from scheduler import parse_schedule_command

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

def execute_trello_action(params: dict, sid: str) -> str:
    """Gerencia cards no Trello via API REST."""
    import requests as req

    if not TRELLO_API_KEY or not TRELLO_TOKEN:
        socketio.emit('action_result', {'success': False, 'message': 'Trello não configurado'}, room=sid)
        return 'Trello não configurado, Senhor. Adicione TRELLO_API_KEY e TRELLO_TOKEN no .env.'

    action      = params.get('action', 'list').lower()
    title       = params.get('title', '')
    description = params.get('description', '')
    due_date    = params.get('due_date', '')
    list_name   = params.get('list_name', 'A fazer')

    auth = {'key': TRELLO_API_KEY, 'token': TRELLO_TOKEN}
    base = 'https://api.trello.com/1'

    try:
        if action == 'list':
            if not TRELLO_BOARD_ID:
                resp  = req.get(f'{base}/members/me/boards', params=auth, timeout=10)
                nomes = [b['name'] for b in resp.json()[:5]]
                return f'Seus boards no Trello: {", ".join(nomes)}. Configure TRELLO_BOARD_ID no .env para listar cards.'

            resp  = req.get(f'{base}/boards/{TRELLO_BOARD_ID}/cards', params=auth, timeout=10)
            cards = resp.json()
            if not cards:
                return 'Nenhum card encontrado no board, Senhor.'
            resumo = [f'{i+1}. {c["name"]}' for i, c in enumerate(cards[:5])]
            socketio.emit('action_result', {'success': True, 'message': f'{len(cards)} cards encontrados'}, room=sid)
            return f'{len(cards)} cards no Trello: ' + ' | '.join(resumo)

        elif action == 'create':
            if not title:
                return 'Por favor, especifique o título do card, Senhor.'
            if not TRELLO_BOARD_ID:
                return 'TRELLO_BOARD_ID não configurado, Senhor.'

            resp   = req.get(f'{base}/boards/{TRELLO_BOARD_ID}/lists', params=auth, timeout=10)
            listas = resp.json()
            list_id = next((l['id'] for l in listas if list_name.lower() in l['name'].lower()), None)
            if not list_id and listas:
                list_id = listas[0]['id']
            if not list_id:
                return 'Não foi possível encontrar a lista no Trello, Senhor.'

            card_data = {**auth, 'name': title, 'idList': list_id}
            if description:
                card_data['desc'] = description
            if due_date:
                card_data['due'] = f'{due_date}T23:59:00.000Z'

            resp = req.post(f'{base}/cards', params=card_data, timeout=10)
            if resp.status_code == 200:
                socketio.emit('action_result', {'success': True, 'message': f'Card criado: {title}'}, room=sid)
                return f'Card "{title}" criado no Trello na lista "{list_name}", Senhor.'
            return f'Erro ao criar card: {resp.text}'

        elif action in ('complete', 'delete'):
            if not title or not TRELLO_BOARD_ID:
                return 'Especifique o nome do card e configure TRELLO_BOARD_ID, Senhor.'
            resp  = req.get(f'{base}/boards/{TRELLO_BOARD_ID}/cards', params=auth, timeout=10)
            card  = next((c for c in resp.json() if title.lower() in c['name'].lower()), None)
            if not card:
                return f'Card "{title}" não encontrado, Senhor.'
            req.put(f'{base}/cards/{card["id"]}', params={**auth, 'closed': 'true'}, timeout=10)
            socketio.emit('action_result', {'success': True, 'message': f'Card arquivado: {title}'}, room=sid)
            return f'Card "{title}" marcado como concluído no Trello, Senhor.'

        return f'Ação Trello não reconhecida: {action}'

    except Exception as e:
        print(f'[JARVIS] Erro Trello: {e}')
        socketio.emit('action_result', {'success': False, 'message': f'Erro Trello: {str(e)[:50]}'}, room=sid)
        return f'Erro ao acessar o Trello: {str(e)[:80]}'

def execute_asana_action(params: dict, sid: str) -> str:
    """Gerencia tarefas no Asana via API REST."""
    import requests as req

    if not ASANA_TOKEN:
        socketio.emit('action_result', {'success': False, 'message': 'Asana não configurado'}, room=sid)
        return 'Asana não configurado, Senhor. Adicione ASANA_TOKEN no .env.'

    action      = params.get('action', 'list').lower()
    title       = params.get('title', '')
    description = params.get('description', '')
    due_date    = params.get('due_date', '')

    headers = {
        'Authorization': f'Bearer {ASANA_TOKEN}',
        'Content-Type':  'application/json',
        'Accept':        'application/json',
    }
    base = 'https://app.asana.com/api/1.0'

    try:
        if action == 'list':
            if not ASANA_PROJECT_ID:
                resp  = req.get(f'{base}/projects', headers=headers, timeout=10)
                nomes = [p['name'] for p in resp.json().get('data', [])[:5]]
                return f'Seus projetos no Asana: {", ".join(nomes)}. Configure ASANA_PROJECT_ID no .env.'

            resp  = req.get(
                f'{base}/tasks',
                headers=headers,
                params={'project': ASANA_PROJECT_ID, 'completed_since': 'now', 'limit': 10},
                timeout=10
            )
            tasks = resp.json().get('data', [])
            if not tasks:
                return 'Nenhuma tarefa pendente no Asana, Senhor.'
            resumo = [f'{i+1}. {t["name"]}' for i, t in enumerate(tasks[:5])]
            socketio.emit('action_result', {'success': True, 'message': f'{len(tasks)} tarefas encontradas'}, room=sid)
            return f'{len(tasks)} tarefas no Asana: ' + ' | '.join(resumo)

        elif action == 'create':
            if not title:
                return 'Por favor, especifique o título da tarefa, Senhor.'
            task_data: dict = {'name': title}
            if description:
                task_data['notes'] = description
            if due_date:
                task_data['due_on'] = due_date
            if ASANA_PROJECT_ID:
                task_data['projects'] = [ASANA_PROJECT_ID]

            resp = req.post(f'{base}/tasks', headers=headers, json={'data': task_data}, timeout=10)
            if resp.status_code in (200, 201):
                prazo = f' com prazo em {due_date}' if due_date else ''
                socketio.emit('action_result', {'success': True, 'message': f'Tarefa criada: {title}'}, room=sid)
                return f'Tarefa "{title}" criada no Asana{prazo}, Senhor.'
            return f'Erro ao criar tarefa: {resp.text}'

        elif action == 'complete':
            if not title or not ASANA_PROJECT_ID:
                return 'Especifique o nome da tarefa e configure ASANA_PROJECT_ID, Senhor.'
            resp  = req.get(f'{base}/tasks', headers=headers,
                            params={'project': ASANA_PROJECT_ID, 'limit': 50}, timeout=10)
            task  = next((t for t in resp.json().get('data', []) if title.lower() in t['name'].lower()), None)
            if not task:
                return f'Tarefa "{title}" não encontrada no Asana, Senhor.'
            req.put(f'{base}/tasks/{task["gid"]}', headers=headers,
                    json={'data': {'completed': True}}, timeout=10)
            socketio.emit('action_result', {'success': True, 'message': f'Tarefa concluída: {title}'}, room=sid)
            return f'Tarefa "{title}" marcada como concluída no Asana, Senhor.'

        return f'Ação Asana não reconhecida: {action}'

    except Exception as e:
        print(f'[JARVIS] Erro Asana: {e}')
        socketio.emit('action_result', {'success': False, 'message': f'Erro Asana: {str(e)[:50]}'}, room=sid)
        return f'Erro ao acessar o Asana: {str(e)[:80]}'

def execute_schedule_task(params: dict, sid: str) -> str:
    text = params.get('query', '')
    parsed = parse_schedule_command(text)
    if not parsed:
        return 'Não consegui identificar o horário do lembrete, Senhor. Diga por exemplo: lembre-me às 15h de fazer algo.'
    task = add_task(
        message   = parsed['message'],
        time_str  = parsed['time'],
        task_type = parsed['type'],
        weekday   = parsed['weekday'],
    )
    if task:
        tipo_map = {'once': 'hoje', 'daily': 'todos os dias', 'hourly': 'a cada hora', 'weekday': f'toda {parsed["weekday"]}'}
        tipo_str = tipo_map.get(parsed['type'], parsed['type'])
        socketio.emit('action_result', {'success': True, 'message': f'Lembrete às {parsed["time"]}'}, room=sid)
        return f'Lembrete agendado para às {parsed["time"]} {tipo_str}, Senhor.'
    return 'Não foi possível criar o lembrete, Senhor.'

