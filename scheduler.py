"""
J.A.R.V.I.S. — Motor de Automações Agendadas
Módulo 7: Vozes Únicas
Agenda tarefas por voz que o JARVIS executa automaticamente.
"""

import schedule
import threading
import datetime
import time
import json
import os
import re
from pathlib import Path

# Arquivo de persistência de tarefas agendadas
TASKS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'jarvis_tasks.json')

_tasks = {}          # {task_id: task_dict}
_scheduler_running = False
_socketio_ref = None  # Referência ao socketio injetada pelo App.py
_tts_func = None      # Referência ao generate_tts


def init_scheduler(socketio_instance, tts_function):
    """Inicializa o scheduler com referências do App.py."""
    global _socketio_ref, _tts_func
    _socketio_ref = socketio_instance
    _tts_func     = tts_function
    _load_tasks()
    _start_scheduler_thread()
    print('[JARVIS] Scheduler inicializado')


# ─── PERSISTÊNCIA ─────────────────────────────────────────────────────────────

def _save_tasks():
    with open(TASKS_FILE, 'w', encoding='utf-8') as f:
        # Salva apenas tarefas serializáveis (exclui callables)
        serializable = {
            k: {kk: vv for kk, vv in v.items() if kk != 'job'}
            for k, v in _tasks.items()
        }
        json.dump(serializable, f, ensure_ascii=False, indent=2)


def _load_tasks():
    """Recarrega tarefas salvas e as reagenda."""
    if not os.path.exists(TASKS_FILE):
        return
    try:
        with open(TASKS_FILE, 'r', encoding='utf-8') as f:
            saved = json.load(f)
        for task_id, task in saved.items():
            if task.get('active', True):
                _schedule_task(task_id, task)
        print(f'[JARVIS] {len(saved)} tarefas recarregadas')
    except Exception as e:
        print(f'[JARVIS] Erro ao carregar tarefas: {e}')


# ─── EXECUÇÃO DE TAREFAS ──────────────────────────────────────────────────────

def _execute_task(task_id: str):
    """Executa uma tarefa agendada — fala a mensagem via TTS."""
    task = _tasks.get(task_id)
    if not task or not task.get('active'):
        return

    message = task.get('message', 'Lembrete do J.A.R.V.I.S.')
    print(f'[JARVIS] Executando tarefa: {message}')

    if _tts_func:
        try:
            audio_b64 = _tts_func(message)
            if _socketio_ref:
                # Broadcast para todos os clientes conectados
                _socketio_ref.emit('jarvis_response', {
                    'text':      message,
                    'audio_b64': audio_b64,
                    'api_used':  'scheduler',
                    'intent':    'scheduled_task',
                })
        except Exception as e:
            print(f'[JARVIS] Erro ao executar tarefa: {e}')

    # Se for tarefa única (não recorrente), cancela após execução
    if task.get('type') == 'once':
        cancel_task(task_id)


# ─── AGENDAMENTO ──────────────────────────────────────────────────────────────

def _schedule_task(task_id: str, task: dict):
    """Registra uma tarefa no schedule e na memória interna."""
    task_type = task.get('type', 'once')
    time_str  = task.get('time', '')
    weekday   = task.get('weekday', '')

    try:
        fn = lambda tid=task_id: _execute_task(tid)

        if task_type == 'once':
            # Agenda para uma hora específica hoje
            job = schedule.every().day.at(time_str).do(fn).tag(task_id)

        elif task_type == 'daily':
            job = schedule.every().day.at(time_str).do(fn).tag(task_id)

        elif task_type == 'hourly':
            job = schedule.every().hour.do(fn).tag(task_id)

        elif task_type == 'weekday' and weekday:
            day_map = {
                'segunda': schedule.every().monday,
                'terca':   schedule.every().tuesday,
                'quarta':  schedule.every().wednesday,
                'quinta':  schedule.every().thursday,
                'sexta':   schedule.every().friday,
                'sabado':  schedule.every().saturday,
                'domingo': schedule.every().sunday,
            }
            day_scheduler = day_map.get(weekday.lower())
            if day_scheduler:
                job = day_scheduler.at(time_str).do(fn).tag(task_id)
            else:
                return False
        else:
            return False

        task['job_tag'] = task_id
        _tasks[task_id] = task
        return True

    except Exception as e:
        print(f'[JARVIS] Erro ao agendar tarefa: {e}')
        return False


def add_task(message: str, time_str: str, task_type: str = 'once',
             weekday: str = '', task_id: str = None) -> dict:
    """
    Adiciona uma nova tarefa agendada.

    Parâmetros:
    - message:   O que o JARVIS vai falar
    - time_str:  Horário no formato HH:MM
    - task_type: 'once', 'daily', 'hourly', 'weekday'
    - weekday:   segunda|terca|quarta|quinta|sexta|sabado|domingo
    - task_id:   ID único (gerado automaticamente se não fornecido)
    """
    import uuid
    if not task_id:
        task_id = str(uuid.uuid4())[:8]

    task = {
        'id':       task_id,
        'message':  message,
        'time':     time_str,
        'type':     task_type,
        'weekday':  weekday,
        'active':   True,
        'created':  datetime.datetime.now().isoformat(),
    }

    success = _schedule_task(task_id, task)
    if success:
        _save_tasks()
        print(f'[JARVIS] Tarefa agendada: {message} às {time_str} ({task_type})')
        return task
    return {}


def cancel_task(task_id: str) -> bool:
    """Cancela e remove uma tarefa agendada."""
    schedule.clear(task_id)
    if task_id in _tasks:
        _tasks[task_id]['active'] = False
        _tasks.pop(task_id, None)
        _save_tasks()
        return True
    return False


def get_all_tasks() -> list:
    """Retorna todas as tarefas ativas."""
    return [
        {k: v for k, v in task.items() if k != 'job'}
        for task in _tasks.values()
        if task.get('active')
    ]


def clear_all_tasks():
    """Cancela todas as tarefas."""
    schedule.clear()
    _tasks.clear()
    if os.path.exists(TASKS_FILE):
        os.remove(TASKS_FILE)


# ─── THREAD DO SCHEDULER ──────────────────────────────────────────────────────

def _scheduler_loop():
    """Loop que verifica e executa tarefas pendentes."""
    global _scheduler_running
    _scheduler_running = True
    while _scheduler_running:
        try:
            schedule.run_pending()
        except Exception as e:
            print(f'[JARVIS] Scheduler erro: {e}')
        time.sleep(10)  # Verifica a cada 10 segundos


def _start_scheduler_thread():
    t = threading.Thread(target=_scheduler_loop, daemon=True)
    t.start()


def stop_scheduler():
    global _scheduler_running
    _scheduler_running = False


# ─── PARSER DE LINGUAGEM NATURAL ─────────────────────────────────────────────

def parse_schedule_command(text: str) -> dict | None:
    """
    Tenta extrair dados de agendamento de texto em linguagem natural.
    Retorna dict com {message, time, type, weekday} ou None.
    """
    text_lower = text.lower().strip()

    # Extrai horário no formato HH:MM ou HH:MMh
    time_patterns = [
        r'(\d{1,2})[h:](\d{2})',   # 15:30 ou 15h30
        r'(\d{1,2})h',              # 15h
        r'às (\d{1,2}):(\d{2})',    # às 15:30
        r'às (\d{1,2})h',           # às 15h
    ]

    time_str = None
    for pattern in time_patterns:
        match = re.search(pattern, text_lower)
        if match:
            groups = match.groups()
            hour   = int(groups[0])
            minute = int(groups[1]) if len(groups) > 1 and groups[1] else 0
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                time_str = f'{hour:02d}:{minute:02d}'
            break

    if not time_str:
        return None

    # Detecta tipo de recorrência
    task_type = 'once'
    weekday   = ''

    if any(w in text_lower for w in ['todo dia', 'todos os dias', 'diariamente', 'cada dia']):
        task_type = 'daily'
    elif any(w in text_lower for w in ['toda segunda', 'todo segunda']):
        task_type, weekday = 'weekday', 'segunda'
    elif any(w in text_lower for w in ['toda terça', 'todo terça', 'toda terca']):
        task_type, weekday = 'weekday', 'terca'
    elif any(w in text_lower for w in ['toda quarta', 'todo quarta']):
        task_type, weekday = 'weekday', 'quarta'
    elif any(w in text_lower for w in ['toda quinta', 'todo quinta']):
        task_type, weekday = 'weekday', 'quinta'
    elif any(w in text_lower for w in ['toda sexta', 'todo sexta']):
        task_type, weekday = 'weekday', 'sexta'
    elif any(w in text_lower for w in ['todo sábado', 'todo sabado']):
        task_type, weekday = 'weekday', 'sabado'
    elif any(w in text_lower for w in ['todo domingo']):
        task_type, weekday = 'weekday', 'domingo'

    # Extrai a mensagem do lembrete
    # Remove o padrão de agendamento para pegar o conteúdo
    clean = re.sub(r'(lembre-me|me lembre|lembre|agende|todo dia|todos os dias|toda \w+|todo \w+|às|as|de|para|que|às \d+[h:]\d*|\d+[h:]\d+)', '', text_lower)
    clean = clean.strip(' .,!?')

    if not clean:
        clean = f'Lembrete agendado para às {time_str}'

    # Formata a mensagem como o JARVIS falaria
    message = f'Sir, é hora de: {clean}. Este é seu lembrete das {time_str}.'

    return {
        'message':  message,
        'time':     time_str,
        'type':     task_type,
        'weekday':  weekday,
    }


if __name__ == '__main__':
    print("=== Teste do Scheduler ===")
    tests = [
        "lembre-me às 15h de fazer café",
        "todo dia às 09:00 me diga bom dia",
        "toda segunda às 8h reunião de equipe",
        "me lembre às 22h30 de dormir",
    ]
    for t in tests:
        result = parse_schedule_command(t)
        print(f"\nTexto: {t}")
        print(f"Resultado: {result}")