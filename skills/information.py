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

def execute_get_weather(params: dict, sid: str) -> str:
    """Obtém clima via Open-Meteo (sem API key) com fallback wttr.in texto."""
    import requests as req
    city = params.get('city', '') or 'Rio de Janeiro'

    # Tentativa 1: Open-Meteo — sem API key, mais confiável
    try:
        geo = req.get(
            'https://geocoding-api.open-meteo.com/v1/search',
            params={'name': city, 'count': 1, 'language': 'pt', 'format': 'json'},
            timeout=5,
        )
        geo_data = geo.json().get('results', [])
        if geo_data:
            lat  = geo_data[0]['latitude']
            lon  = geo_data[0]['longitude']
            nome = geo_data[0].get('name', city)
            pais = geo_data[0].get('country', '')
            clima = req.get(
                'https://api.open-meteo.com/v1/forecast',
                params={
                    'latitude': lat, 'longitude': lon,
                    'current': 'temperature_2m,apparent_temperature,weathercode,windspeed_10m,relativehumidity_2m',
                    'timezone': 'auto',
                },
                timeout=5,
            )
            c     = clima.json().get('current', {})
            temp  = c.get('temperature_2m', '?')
            feels = c.get('apparent_temperature', '?')
            wind  = c.get('windspeed_10m', '?')
            humid = c.get('relativehumidity_2m', '?')
            code  = c.get('weathercode', 0)
            wmo   = {
                0:'céu limpo', 1:'predominantemente limpo', 2:'parcialmente nublado',
                3:'nublado', 45:'névoa', 51:'chuvisco leve', 61:'chuva leve',
                63:'chuva moderada', 65:'chuva intensa', 80:'pancadas de chuva',
                95:'trovoada',
            }
            desc   = wmo.get(code, 'condição variável')
            result = (f'Clima em {nome}, {pais}: {desc}. '
                      f'Temperatura: {temp}°C, sensação de {feels}°C. '
                      f'Umidade: {humid}%, vento: {wind} km/h.')
            socketio.emit('action_result', {'success': True, 'message': f'{temp}°C em {nome}'}, room=sid)
            return result
    except Exception as e:
        print(f'[JARVIS] Open-Meteo falhou: {e}')

    # Tentativa 2: wttr.in formato texto simples (mais leve que JSON)
    try:
        resp = req.get(
            f'https://wttr.in/{city}?format=3',
            timeout=5, headers={'User-Agent': 'curl/7.68.0'},
        )
        if resp.status_code == 200 and resp.text.strip():
            texto = resp.text.strip()
            socketio.emit('action_result', {'success': True, 'message': texto[:50]}, room=sid)
            return f'Clima: {texto}'
    except Exception as e:
        print(f'[JARVIS] wttr.in falhou: {e}')

    socketio.emit('action_result', {'success': False, 'message': 'Clima indisponível'}, room=sid)
    return f'Não foi possível obter o clima para "{city}", Senhor. Tente novamente em instantes.'

def execute_get_news(params: dict, sid: str) -> str:
    """
    Busca notícias via NewsAPI.
    Fallback gratuito via RSS do G1 caso NEWS_API_KEY não esteja configurada.
    """
    import requests as req

    query  = params.get('query', '').strip()
    count  = min(int(params.get('count', 3)), 5)
    topics = [query] if query else NEWS_TOPICS

    socketio.emit('action_result', {'success': True, 'message': f'Buscando notícias: {", ".join(topics)}'}, room=sid)

    # ── Tentativa 1: NewsAPI ──
    if NEWS_API_KEY:
        try:
            q = ' OR '.join(topics)
            resp = req.get(
                'https://newsapi.org/v2/everything',
                params={
                    'q': q,
                    'language': 'pt',
                    'sortBy': 'publishedAt',
                    'pageSize': count,
                    'apiKey': NEWS_API_KEY,
                },
                timeout=10
            )
            articles = resp.json().get('articles', [])
            if articles:
                resumo = []
                for i, a in enumerate(articles[:count], 1):
                    titulo = a.get('title', 'Sem título').split(' - ')[0]
                    fonte  = a.get('source', {}).get('name', 'Fonte desconhecida')
                    resumo.append(f'{i}. {titulo} ({fonte})')
                socketio.emit('news_update', {'articles': articles[:count], 'topics': topics}, room=sid)
                return f'Notícias sobre {", ".join(topics)}: ' + ' | '.join(resumo)
        except Exception as e:
            print(f'[JARVIS] NewsAPI erro: {e}')

    # ── Fallback: RSS G1 gratuito ──
    try:
        import xml.etree.ElementTree as ET
        rss_feeds = {
            'tecnologia': 'https://g1.globo.com/rss/g1/tecnologia/',
            'brasil':     'https://g1.globo.com/rss/g1/',
            'economia':   'https://g1.globo.com/rss/g1/economia/',
            'esportes':   'https://g1.globo.com/rss/g1/esportes/',
            'mundo':      'https://g1.globo.com/rss/g1/mundo/',
        }
        feed_url = None
        for topic in topics:
            for key, url in rss_feeds.items():
                if key in topic.lower():
                    feed_url = url
                    break
            if feed_url:
                break
        feed_url = feed_url or rss_feeds['brasil']

        resp = req.get(feed_url, timeout=10, headers={'User-Agent': 'JARVIS/3.0'})
        root  = ET.fromstring(resp.content)
        items = root.findall('.//item')[:count]

        if items:
            resumo = [f'{i+1}. {item.findtext("title", "Sem título").strip()}' for i, item in enumerate(items)]
            socketio.emit('action_result', {'success': True, 'message': f'{len(items)} notícias encontradas'}, room=sid)
            return 'Principais notícias: ' + ' | '.join(resumo)

    except Exception as e:
        print(f'[JARVIS] RSS fallback erro: {e}')

    return 'Não foi possível buscar notícias no momento, Senhor. Verifique sua conexão ou configure a NEWS_API_KEY no .env.'

