"""
J.A.R.V.I.S. — INSTAGRAM SKILL
Integração com Instagram via instagrapi
Funcionalidades: post no feed, story, DM
"""

import os
import json
import base64
import tempfile
from pathlib import Path
from threading import Thread

class DummySocketIO:
    def __init__(self):
        self._emit_fn = None
    def emit(self, *args, **kwargs):
        if self._emit_fn:
            self._emit_fn(*args, **kwargs)

socketio = DummySocketIO()

# Globais injetadas
GEMINI_AVAILABLE = False
gemini_client = None
GEMINI_MODELS = []
GROQ_AVAILABLE = False
groq_client = None

_instagram_client = None
_SESSION_FILE = Path(__file__).parent.parent / '.instagram_session.json'

def setup(deps):
    global socketio, GEMINI_AVAILABLE, gemini_client, GEMINI_MODELS
    global GROQ_AVAILABLE, groq_client
    if 'emit' in deps: socketio._emit_fn = deps['emit']
    if 'GEMINI_AVAILABLE' in deps: GEMINI_AVAILABLE = deps['GEMINI_AVAILABLE']
    if 'gemini_client' in deps: gemini_client = deps['gemini_client']
    if 'GEMINI_MODELS' in deps: GEMINI_MODELS = deps['GEMINI_MODELS']
    if 'GROQ_AVAILABLE' in deps: GROQ_AVAILABLE = deps['GROQ_AVAILABLE']
    if 'groq_client' in deps: groq_client = deps['groq_client']


def _get_instagram():
    """Inicializa e retorna cliente Instagram autenticado (lazy init com sessão persistente)."""
    global _instagram_client
    if _instagram_client:
        return _instagram_client

    username = os.getenv('INSTAGRAM_USERNAME', '')
    password = os.getenv('INSTAGRAM_PASSWORD', '')
    if not username or not password:
        return None

    try:
        from instagrapi import Client
        cl = Client()

        # Tenta carregar sessão salva
        if _SESSION_FILE.exists():
            try:
                cl.load_settings(str(_SESSION_FILE))
                cl.login(username, password)
                cl.get_timeline_feed()  # testa se a sessão é válida
                _instagram_client = cl
                print('[JARVIS] Instagram: sessão restaurada')
                return cl
            except Exception:
                print('[JARVIS] Instagram: sessão expirada, fazendo novo login')

        # Login fresco
        cl.login(username, password)
        cl.dump_settings(str(_SESSION_FILE))
        _instagram_client = cl
        print('[JARVIS] Instagram: login bem-sucedido')
        return cl

    except ImportError:
        print('[JARVIS] instagrapi não instalado')
        return None
    except Exception as e:
        print(f'[JARVIS] Instagram erro: {e}')
        return None


def execute_instagram_post(params: dict, sid: str, image_data: bytes = None) -> str:
    """Posta uma foto no feed do Instagram."""
    cl = _get_instagram()
    if not cl:
        socketio.emit('action_result', {'success': False, 'message': 'Instagram não configurado'}, room=sid)
        return 'Instagram não configurado, Senhor. Configure INSTAGRAM_USERNAME e INSTAGRAM_PASSWORD no .env'

    caption = params.get('caption', '') or params.get('message', '')
    image_path = params.get('image_path', '')

    socketio.emit('status_update', {'step': 'executing', 'message': 'Postando no Instagram...'}, room=sid)

    try:
        # Se recebeu imagem como bytes (do upload/chat)
        if image_data:
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
                f.write(image_data)
                temp_path = f.name
            media = cl.photo_upload(temp_path, caption=caption)
            os.unlink(temp_path)
        elif image_path and os.path.exists(image_path):
            media = cl.photo_upload(image_path, caption=caption)
        else:
            return 'Nenhuma imagem fornecida para postar, Senhor. Anexe uma imagem ao chat.'

        socketio.emit('action_result', {'success': True, 'message': 'Foto postada no Instagram!'}, room=sid)
        return f'Foto postada com sucesso no Instagram, Senhor! ID: {media.pk}'

    except Exception as e:
        socketio.emit('action_result', {'success': False, 'message': f'Erro ao postar: {e}'}, room=sid)
        return f'Erro ao postar no Instagram: {e}'


def execute_instagram_story(params: dict, sid: str, image_data: bytes = None) -> str:
    """Posta uma imagem nos stories do Instagram."""
    cl = _get_instagram()
    if not cl:
        socketio.emit('action_result', {'success': False, 'message': 'Instagram não configurado'}, room=sid)
        return 'Instagram não configurado, Senhor. Configure INSTAGRAM_USERNAME e INSTAGRAM_PASSWORD no .env'

    image_path = params.get('image_path', '')

    socketio.emit('status_update', {'step': 'executing', 'message': 'Postando nos stories...'}, room=sid)

    try:
        if image_data:
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
                f.write(image_data)
                temp_path = f.name
            media = cl.photo_upload_to_story(temp_path)
            os.unlink(temp_path)
        elif image_path and os.path.exists(image_path):
            media = cl.photo_upload_to_story(image_path)
        else:
            return 'Nenhuma imagem fornecida para o story, Senhor. Anexe uma imagem ao chat.'

        socketio.emit('action_result', {'success': True, 'message': 'Story postado!'}, room=sid)
        return f'Story postado com sucesso no Instagram, Senhor!'

    except Exception as e:
        socketio.emit('action_result', {'success': False, 'message': f'Erro no story: {e}'}, room=sid)
        return f'Erro ao postar story: {e}'


def execute_instagram_dm(params: dict, sid: str) -> str:
    """Envia uma mensagem direta no Instagram."""
    cl = _get_instagram()
    if not cl:
        socketio.emit('action_result', {'success': False, 'message': 'Instagram não configurado'}, room=sid)
        return 'Instagram não configurado, Senhor.'

    username = params.get('contact', '') or params.get('username', '')
    message = params.get('message', '')

    if not username:
        return 'Por favor, informe o usuário do Instagram para enviar a DM, Senhor.'
    if not message:
        return 'Por favor, informe a mensagem para enviar, Senhor.'

    socketio.emit('status_update', {'step': 'executing', 'message': f'Enviando DM para @{username}...'}, room=sid)

    try:
        # Busca o user_id pelo username
        user_id = cl.user_id_from_username(username.lstrip('@'))
        cl.direct_send(message, [user_id])
        socketio.emit('action_result', {'success': True, 'message': f'DM enviada para @{username}'}, room=sid)
        return f'Mensagem enviada para @{username} no Instagram, Senhor.'

    except Exception as e:
        socketio.emit('action_result', {'success': False, 'message': f'Erro DM: {e}'}, room=sid)
        return f'Erro ao enviar DM: {e}'
