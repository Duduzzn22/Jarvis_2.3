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

def execute_spotify_control(params: dict, sid: str) -> str:
    """Controla o Spotify via API real."""
    sp = get_spotify()
    if not sp:
        # Fallback para teclas de mídia se Spotify não estiver configurado
        socketio.emit('action_result', {'success': False, 'message': 'Spotify não configurado — usando teclas de mídia'}, room=sid)
        return execute_control_music(params, sid)

    action = params.get('action', 'play').lower()
    query  = params.get('query', '')
    volume = params.get('volume', None)

    try:
        # Obtém dispositivos disponíveis
        devices  = sp.devices()
        all_devs = devices.get('devices', [])

        # Nenhum dispositivo — abre o Spotify e aguarda até 15s
        if not all_devs:
            subprocess.Popen('start spotify:', shell=True)
            for _ in range(15):
                time.sleep(1)
                all_devs = sp.devices().get('devices', [])
                if all_devs:
                    break

        if not all_devs:
            socketio.emit('action_result', {
                'success': False,
                'message': 'Spotify não encontrado — abra o app manualmente'
            }, room=sid)
            return 'Nenhum dispositivo Spotify disponível, Senhor. Abra o Spotify e tente novamente.'

        # Prefere dispositivo ativo, senão pega o primeiro
        active    = next((d for d in all_devs if d['is_active']), all_devs[0])
        device_id = active['id']

        # Transfere com force_play=True se não estiver ativo
        if not active['is_active']:
            sp.transfer_playback(device_id, force_play=True)
            time.sleep(2)

        if action == 'play' and query:
            # Busca e toca música/artista/playlist por nome
            results = sp.search(q=query, limit=1, type='track,artist,playlist')
            tracks = results.get('tracks', {}).get('items', [])
            artists = results.get('artists', {}).get('items', [])
            playlists = results.get('playlists', {}).get('items', [])

            if tracks:
                track = tracks[0]
                sp.start_playback(device_id=device_id, uris=[track['uri']])
                name   = track['name']
                artist = track['artists'][0]['name']
                socketio.emit('action_result', {'success': True, 'message': f'Tocando: {name} — {artist}'}, room=sid)
                return f'Tocando "{name}" de {artist} no Spotify'
            elif playlists:
                pl = playlists[0]
                sp.start_playback(device_id=device_id, context_uri=pl['uri'])
                socketio.emit('action_result', {'success': True, 'message': f'Playlist: {pl["name"]}'}, room=sid)
                return f'Tocando playlist "{pl["name"]}" no Spotify'
            else:
                return f'Nenhum resultado encontrado para "{query}" no Spotify'

        elif action in ('play', 'resume', 'open', 'abrir', 'iniciar'):
            current = sp.current_playback()
            if current and current.get('item'):
                sp.start_playback(device_id=device_id)
                name = current['item']['name']
                socketio.emit('action_result', {'success': True, 'message': f'Spotify: play — {name}'}, room=sid)
                return f'Reproduzindo "{name}" no Spotify'
            else:
                try:
                    import random
                    saved = sp.current_user_saved_tracks(limit=50)
                    items = saved.get('items', [])
                    if items:
                        uris = [i['track']['uri'] for i in items if i.get('track')]
                        random.shuffle(uris)
                        sp.start_playback(device_id=device_id, uris=uris[:50])
                        socketio.emit('action_result', {'success': True, 'message': 'Tocando músicas curtidas'}, room=sid)
                        return 'Tocando suas músicas curtidas no Spotify, Senhor.'
                except Exception:
                    pass
                sp.start_playback(device_id=device_id)
                socketio.emit('action_result', {'success': True, 'message': 'Spotify: play'}, room=sid)
                return 'Spotify iniciado, Senhor.'

        elif action in ('pause', 'pausar'):
            sp.pause_playback(device_id=device_id)
            socketio.emit('action_result', {'success': True, 'message': 'Spotify: pausado'}, room=sid)
            return 'Spotify pausado'

        elif action in ('next', 'proxima', 'próxima', 'pular'):
            sp.next_track(device_id=device_id)
            time.sleep(0.5)
            current = sp.current_playback()
            name = current['item']['name'] if current and current.get('item') else 'próxima'
            socketio.emit('action_result', {'success': True, 'message': f'Próxima: {name}'}, room=sid)
            return f'Avançando para "{name}"'

        elif action in ('previous', 'anterior', 'voltar'):
            sp.previous_track(device_id=device_id)
            socketio.emit('action_result', {'success': True, 'message': 'Spotify: faixa anterior'}, room=sid)
            return 'Voltando para a faixa anterior'

        elif action in ('volume_up', 'aumentar'):
            current = sp.current_playback()
            vol = min(100, (current['device']['volume_percent'] + 20) if current else 80)
            sp.volume(vol, device_id=device_id)
            socketio.emit('action_result', {'success': True, 'message': f'Volume: {vol}%'}, room=sid)
            return f'Volume do Spotify: {vol}%'

        elif action in ('volume_down', 'diminuir'):
            current = sp.current_playback()
            vol = max(0, (current['device']['volume_percent'] - 20) if current else 40)
            sp.volume(vol, device_id=device_id)
            socketio.emit('action_result', {'success': True, 'message': f'Volume: {vol}%'}, room=sid)
            return f'Volume do Spotify: {vol}%'

        elif action == 'volume' and volume is not None:
            vol = max(0, min(100, int(volume)))
            sp.volume(vol, device_id=device_id)
            socketio.emit('action_result', {'success': True, 'message': f'Volume: {vol}%'}, room=sid)
            return f'Volume do Spotify definido para {vol}%'

        elif action in ('mute', 'silenciar'):
            sp.volume(0, device_id=device_id)
            socketio.emit('action_result', {'success': True, 'message': 'Spotify: mudo'}, room=sid)
            return 'Spotify silenciado'

        elif action in ('current', 'atual', 'tocando', 'what'):
            current = sp.current_playback()
            if current and current.get('item'):
                name   = current['item']['name']
                artist = current['item']['artists'][0]['name']
                return f'Tocando agora: "{name}" de {artist}'
            return 'Nenhuma música tocando no momento'

        else:
            return f'Ação Spotify não reconhecida: {action}'

    except Exception as e:
        print(f'[JARVIS] Erro Spotify: {e}')
        socketio.emit('action_result', {'success': False, 'message': f'Erro Spotify: {str(e)[:50]}'}, room=sid)
        return f'Erro ao controlar Spotify: {str(e)[:80]}'

def execute_protocol_work_time(params: dict, sid: str) -> str:
    """
    Protocolo especial 'Hora do Papai Trabalhar':
    Toca Back in Black do AC/DC no Spotify.
    CORRIGIDO v4: força play mesmo com dispositivo inativo.
    """
    sp = get_spotify()
    if sp:
        try:
            devices   = sp.devices()
            all_devs  = devices.get('devices', [])

            # ── Se Spotify não está aberto: abre e aguarda até 15s ──
            if not all_devs:
                print('[JARVIS] Nenhum dispositivo — abrindo Spotify...')
                subprocess.Popen('start spotify:', shell=True)
                for _ in range(15):
                    time.sleep(1)
                    all_devs = sp.devices().get('devices', [])
                    if all_devs:
                        break

            if not all_devs:
                socketio.emit('action_result', {
                    'success': False,
                    'message': 'Spotify não encontrado — abra o app manualmente'
                }, room=sid)
                return 'Nenhum dispositivo Spotify disponível, Senhor.'

            # ── Pega dispositivo ativo ou o primeiro disponível ──
            active    = next((d for d in all_devs if d['is_active']), all_devs[0])
            device_id = active['id']

            # ── CORREÇÃO PRINCIPAL: force_play=True garante o play ──
            if not active['is_active']:
                print(f'[JARVIS] Transferindo playback para {active["name"]}...')
                sp.transfer_playback(device_id, force_play=True)
                time.sleep(2)

            # ── Busca Back in Black ──
            results = sp.search(q='Back in Black artist:AC/DC', limit=1, type='track')
            tracks  = results.get('tracks', {}).get('items', [])

            if not tracks:
                return 'Back in Black não encontrada no Spotify, Senhor.'

            track = tracks[0]

            # ── Inicia a música ──
            sp.start_playback(device_id=device_id, uris=[track['uri']])
            time.sleep(1)

            # ── Segunda tentativa de play caso ainda esteja pausado ──
            playback = sp.current_playback()
            if playback and not playback.get('is_playing'):
                print('[JARVIS] Ainda pausado — forçando play...')
                sp.start_playback(device_id=device_id, uris=[track['uri']])
                time.sleep(0.5)

            # ── Volume audível ──
            sp.volume(80, device_id=device_id)

            socketio.emit('action_result', {
                'success': True,
                'message': f'PROTOCOLO ATIVADO — {track["name"]} tocando'
            }, room=sid)
            print(f'[JARVIS] Protocolo: tocando {track["name"]}')
            return f'PROTOCOLO_WORK_TIME | Tocando "{track["name"]}" de AC/DC'

        except Exception as e:
            print(f'[JARVIS] Spotify API falhou no protocolo: {e}')
            socketio.emit('action_result', {
                'success': False,
                'message': f'Erro Spotify: {str(e)[:60]}'
            }, room=sid)

    # ─── Fallback: URI desktop + playpause ───
    try:
        os.startfile('spotify:search:Back%20in%20Black%20ACDC')
        time.sleep(4)
        import pyautogui
        pyautogui.press('playpause')
        socketio.emit('action_result', {
            'success': True,
            'message': 'PROTOCOLO ATIVADO — Spotify aberto'
        }, room=sid)
        return 'PROTOCOLO_WORK_TIME | Spotify aberto com play forçado'
    except Exception as e:
        print(f'[JARVIS] Fallback falhou: {e}')

    # ─── Fallback final: Spotify Web ───
    webbrowser.open('https://open.spotify.com/search/Back%20in%20Black%20ACDC')
    return 'PROTOCOLO_WORK_TIME | Spotify Web aberto'

def execute_control_music(params: dict, sid: str) -> str:
    """Fallback: controla música via teclas de mídia do sistema."""
    try:
        import pyautogui
        action = params.get('action', 'play')
        action_map = {
            'play':       lambda: pyautogui.press('playpause'),
            'pause':      lambda: pyautogui.press('playpause'),
            'next':       lambda: pyautogui.press('nexttrack'),
            'anterior':   lambda: pyautogui.press('prevtrack'),
            'previous':   lambda: pyautogui.press('prevtrack'),
            'volume_up':  lambda: pyautogui.press('volumeup'),
            'aumentar':   lambda: [pyautogui.press('volumeup') for _ in range(3)],
            'volume_down':lambda: pyautogui.press('volumedown'),
            'diminuir':   lambda: [pyautogui.press('volumedown') for _ in range(3)],
            'mute':       lambda: pyautogui.press('volumemute'),
            'silenciar':  lambda: pyautogui.press('volumemute'),
        }
        fn = action_map.get(action.lower())
        if fn:
            fn()
            socketio.emit('action_result', {'success': True, 'message': f'Música: {action}'}, room=sid)
            return f'Controle de música: {action}'
        return f'Ação de música não reconhecida: {action}'
    except ImportError:
        return 'pyautogui não instalado'
    except Exception as e:
        return f'Erro ao controlar música: {e}'

