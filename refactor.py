import ast
import re

skill_groups = {
    'intent_engine': ['detect_intent'],
    'system': [
        'execute_open_app', 'execute_search_web', 'execute_open_youtube',
        'execute_system_info', 'execute_manage_files', 'execute_type_text',
        'execute_open_url', 'execute_get_clipboard'
    ],
    'media': [
        'execute_spotify_control', 'execute_protocol_work_time', 'execute_control_music'
    ],
    'communication': [
        'execute_send_whatsapp', 'execute_send_telegram'
    ],
    'productivity': [
        'execute_trello_action', 'execute_asana_action', 'execute_schedule_task'
    ],
    'vision': [
        'execute_analyze_screen', 'execute_analyze_screen_quick',
        'execute_take_screenshot', 'execute_analyze_media', 'execute_pc_agent_task'
    ],
    'information': [
        'execute_get_weather', 'execute_get_news'
    ]
}

imports_header = """import os
import json
import time
import subprocess
import webbrowser
import platform
import base64
import requests
import datetime
from threading import Thread

# Helper para socketio.emit
class DummySocketIO:
    def __init__(self):
        self._emit_fn = None
    def emit(self, *args, **kwargs):
        if self._emit_fn:
            self._emit_fn(*args, **kwargs)
        else:
            print("[SKILL] socketio emit not initialized")
socketio = DummySocketIO()

__all___deps = {}
def setup(deps):
    global __all___deps
    __all___deps.update(deps)
    if 'emit' in deps:
        socketio._emit_fn = deps['emit']

def _get_dep(name, default=None):
    return __all___deps.get(name, default)

"""

# Let's map how globals are accessed by replacing them with _get_dep() dynamically or just setting globals.
imports_header_alt = """import os
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

"""

with open('App.py', 'r', encoding='utf-8') as f:
    code = f.read()

tree = ast.parse(code)
functions = {}
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and (node.name.startswith('execute_') or node.name == 'detect_intent' or node.name == 'INTENT_PROMPT'):
        functions[node.name] = {
            'start': node.lineno - 1,
            'end': node.end_lineno,
            'text': code.splitlines()[node.lineno-1:node.end_lineno]
        }

# INTENT_PROMPT is an Assign, let's extract it manually using regex since ast doesn't group comments.
intent_prompt_match = re.search(r'INTENT_PROMPT\s*=\s*\"\"\"(.*?)\"\"\"', code, re.DOTALL)
intent_prompt_code = ""
if intent_prompt_match:
    intent_prompt_code = intent_prompt_match.group(0) + "\\n"

# Remove the functions from App.py backwards
lines = code.splitlines()

# Create skills files
import os
os.makedirs('skills', exist_ok=True)
with open('skills/__init__.py', 'w', encoding='utf-8') as f:
    f.write("")

for group, func_names in skill_groups.items():
    with open(f'skills/{group}.py', 'w', encoding='utf-8') as f:
        f.write(imports_header_alt)
        if group == 'intent_engine':
            f.write(intent_prompt_code + "\n\n")
        
        for name in func_names:
            if name in functions:
                f.write("\n".join(functions[name]['text']))
                f.write("\n\n")
            else:
                print(f"Warning: {name} not found in App.py")

# Remove from App.py
remove_ranges = []
for name, data in functions.items():
    remove_ranges.append((data['start'], data['end']))

# Remove INTENT_PROMPT from App.py
if intent_prompt_match:
    start_ip = code.count('\\n', 0, intent_prompt_match.start())
    end_ip = code.count('\\n', 0, intent_prompt_match.end())
    remove_ranges.append((start_ip, end_ip+1))

remove_ranges.sort(key=lambda x: x[0], reverse=True)
for start, end in remove_ranges:
    del lines[start:end]

with open('App.py', 'w', encoding='utf-8') as f:
    f.write("\n".join(lines))

print("Extraction completed.")
