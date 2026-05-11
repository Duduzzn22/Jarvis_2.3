import os
import re

patch_streaming_logic = """
# ─── GERAÇÃO DE RESPOSTA IA (STREAMING) ───────────────────────────────────────
def generate_ai_response_stream(messages: list, context: str = ''):
    \"\"\"Groq com streaming ativado.\"\"\"
    memory_prompt      = build_system_prompt()
    personality_prompt = get_personality_prompt()
    system = personality_prompt + '\\n\\n' + memory_prompt

    if MEM0_AVAILABLE and messages:
        ultima_msg = messages[-1].get('content', '')
        mem0_context = mem0_search(ultima_msg, limit=5)
        if mem0_context:
            system += mem0_context

    if context:
        system += f'\\n\\n## AÇÃO EXECUTADA\\n{context}'

    msgs_base = [{'role': 'system', 'content': system}] + messages

    if GROQ_AVAILABLE and groq_client:
        try:
            stream = groq_client.chat.completions.create(
                model='llama-3.3-70b-versatile',
                messages=msgs_base,
                max_tokens=300,
                temperature=0.7,
                stream=True
            )
            for chunk in stream:
                token = chunk.choices[0].delta.content
                if token:
                    yield token
            return
        except Exception as e:
            print(f'[JARVIS] Groq stream falhou: {e}')

    yield "Desculpe, estou com dificuldades na minha conexão neural."

import websockets
import asyncio

async def _stream_tts_elevenlabs_ws(text_generator, voice_id, emit_callback):
    uri = f"wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-input?model_id=eleven_multilingual_v2"
    
    try:
        async with websockets.connect(uri) as websocket:
            # Envia configuração inicial
            await websocket.send(json.dumps({
                "text": " ",
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.8},
                "xi_api_key": ELEVENLABS_API_KEY
            }))

            async def listen():
                while True:
                    try:
                        message = await websocket.recv()
                        data = json.loads(message)
                        if data.get("audio"):
                            emit_callback(audio_b64=data["audio"])
                        if data.get("isFinal"):
                            break
                    except Exception as e:
                        print("[JARVIS] ElevenLabs WS Error (listen):", e)
                        break

            listen_task = asyncio.create_task(listen())

            buffer = ""
            full_text = ""
            for token in text_generator:
                emit_callback(text_chunk=token)
                buffer += token
                full_text += token
                
                # Descarrega na API quando encontra pontuação ou espaço (otimiza a prosódia do TTS)
                if any(p in buffer for p in [' ', '.', ',', '!', '?', '\\n']):
                    await websocket.send(json.dumps({"text": buffer, "try_trigger_generation": True}))
                    buffer = ""

            if buffer:
                await websocket.send(json.dumps({"text": buffer, "try_trigger_generation": True}))
            
            # Sinaliza fim do stream
            await websocket.send(json.dumps({"text": ""}))
            await listen_task
            return full_text
            
    except Exception as e:
        print(f"[JARVIS] ElevenLabs WebSocket error: {e}")
        # Fallback para emitir os tokens de texto mesmo sem áudio
        full_text = ""
        for token in text_generator:
            emit_callback(text_chunk=token)
            full_text += token
        return full_text

def run_tts_stream(text_generator, voice_id, sid):
    def emit_callback(audio_b64=None, text_chunk=None):
        if audio_b64:
            socketio.emit('audio_chunk', {'chunk_b64': audio_b64}, room=sid)
        if text_chunk:
            socketio.emit('text_chunk', {'text': text_chunk}, room=sid)

    return asyncio.run(_stream_tts_elevenlabs_ws(text_generator, voice_id, emit_callback))


@socketio.on('chat_message_stream')
def on_chat_message_stream(data):
    sid  = request.sid
    text = data.get('text', '').strip()
    if not text: return

    print(f'[JARVIS STREAM] Mensagem: {text}')

    def _process():
        try:
            socketio.emit('status_update', {'step': 'thinking', 'message': 'Analisando...'}, room=sid)
            intent_data = detect_intent(text)

            action_context = None
            if intent_data.get('intent') not in ('conversation', None):
                action_context = dispatch_intent(intent_data, sid)

            Thread(target=extract_facts_via_ai, args=(text,), daemon=True).start()

            history = chat_sessions.get(sid, [])
            history.append({'role': 'user', 'content': text})
            if len(history) > 20:
                history = history[-20:]

            socketio.emit('status_update', {'step': 'speaking', 'message': 'Respondendo...'}, room=sid)
            
            # Stream generator
            generator = generate_ai_response_stream(history, context=action_context or '')

            # Resolving Voice ID
            current_personality = get_current_name()
            voice_id = ELEVENLABS_VOICE_MAP.get(current_personality, ELEVENLABS_VOICE_ID)

            # Consome o generator enviando via WebSockets TTS
            full_resposta = run_tts_stream(generator, voice_id, sid)
            
            # Sinaliza fim
            socketio.emit('stream_end', {'intent': intent_data.get('intent', 'conversation')}, room=sid)

            # Salva no histórico
            history.append({'role': 'assistant', 'content': full_resposta})
            chat_sessions[sid] = history
            log_message('user', text, intent=intent_data.get('intent'))
            log_message('assistant', full_resposta)

            if MEM0_AVAILABLE:
                Thread(target=mem0_add, args=(text, 'user'), daemon=True).start()
                Thread(target=mem0_add, args=(full_resposta, 'assistant'), daemon=True).start()

        except Exception as e:
            print(f'[JARVIS] Erro no stream: {e}')
            socketio.emit('error', {'message': f'Erro no stream: {e}'}, room=sid)

    Thread(target=_process, daemon=True).start()

"""

with open('App.py', 'r', encoding='utf-8') as f:
    code = f.read()

# We insert the patch_streaming_logic right before `def generate_tts_elevenlabs` or at the end of the file before `if __name__ == '__main__':`
# Let's insert it right after the generate_ai_response function
split_token = "def generate_tts_elevenlabs"
if split_token in code:
    parts = code.split(split_token)
    new_code = parts[0] + patch_streaming_logic + "\\n" + split_token + parts[1]
    with open('App.py', 'w', encoding='utf-8') as f:
        f.write(new_code)
    print("Patch applied to App.py")
else:
    print("Could not find the insertion point.")

