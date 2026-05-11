import sys

patch = """
from skills.intent_engine import detect_intent
from skills.system import *
from skills.media import *
from skills.communication import *
from skills.productivity import *
from skills.vision import *
from skills.information import *

import skills.intent_engine as _ie
import skills.system as _sys
import skills.media as _med
import skills.communication as _com
import skills.productivity as _prod
import skills.vision as _vis
import skills.information as _inf

def _init_skills():
    deps = {
        'emit': socketio.emit,
        'CEREBRAS_AVAILABLE': CEREBRAS_AVAILABLE,
        'cerebras_client': cerebras_client,
        'GROQ_AVAILABLE': GROQ_AVAILABLE,
        'groq_client': groq_client,
        'GEMINI_AVAILABLE': GEMINI_AVAILABLE,
        'gemini_client': gemini_client,
        'GEMINI_MODELS': GEMINI_MODELS,
        'TELEGRAM_BOT_TOKEN': TELEGRAM_BOT_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID,
        'TRELLO_API_KEY': TRELLO_API_KEY,
        'TRELLO_TOKEN': TRELLO_TOKEN,
        'TRELLO_BOARD_ID': TRELLO_BOARD_ID,
        'ASANA_TOKEN': ASANA_TOKEN,
        'ASANA_PROJECT_ID': ASANA_PROJECT_ID,
        'NEWS_API_KEY': NEWS_API_KEY,
        'NEWS_TOPICS': NEWS_TOPICS,
        'PC_AGENT_AVAILABLE': PC_AGENT_AVAILABLE,
        'get_app_command': get_app_command,
        'get_spotify': get_spotify,
        'run_pc_agent': run_pc_agent,
        'quick_screen_analysis': quick_screen_analysis,
        'capture_screen_b64': capture_screen_b64,
        'get_all_tasks': get_all_tasks,
        'add_task': add_task,
        'PC_AGENT_SAFE_MODE': os.getenv('PC_AGENT_SAFE_MODE', 'True').lower() in ('true', '1', 'yes')
    }
    _ie.setup(deps)
    _sys.setup(deps)
    _med.setup(deps)
    _com.setup(deps)
    _prod.setup(deps)
    _vis.setup(deps)
    _inf.setup(deps)

_init_skills()

"""

with open('App.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# find def get_app_command end
insert_idx = -1
for i, line in enumerate(lines):
    if line.startswith("def get_app_command"):
        # The function has a few lines. Wait for the empty line or the end of the function.
        # def get_app_command(app_name: str):
        #     name_lower = app_name.lower().strip()
        #     if platform.system() == 'Windows':
        #         return APPS_WINDOWS.get(name_lower)
        #     return APPS_LINUX.get(name_lower)
        insert_idx = i + 5
        break

if insert_idx != -1:
    lines.insert(insert_idx, patch)
    with open('App.py', 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print("Patch applied.")
else:
    print("Could not find insertion point.")
