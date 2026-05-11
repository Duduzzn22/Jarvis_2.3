import socketio
import time

sio = socketio.Client()

start_time = None
first_byte_time = None

@sio.event
def connect():
    print('[TESTE] Conectado ao J.A.R.V.I.S.')
    global start_time
    start_time = time.time()
    sio.emit('chat_message_stream', {'text': 'Diga uma frase curta de bom dia.'})
    print('[TESTE] Mensagem enviada. Aguardando stream...')

@sio.on('text_chunk')
def on_text_chunk(data):
    global first_byte_time
    if not first_byte_time:
        first_byte_time = time.time()
        print(f'\\n[TESTE] Time-to-First-Text: {first_byte_time - start_time:.2f}s')
    print(data['text'], end='', flush=True)

@sio.on('audio_chunk')
def on_audio_chunk(data):
    print('\\n[TESTE] Recebeu chunk de áudio! Tamanho Base64:', len(data['chunk_b64']))

@sio.on('stream_end')
def on_stream_end(data):
    print('\\n[TESTE] Stream finalizado. Intenção:', data.get('intent'))
    sio.disconnect()

@sio.event
def disconnect():
    print('[TESTE] Desconectado.')

if __name__ == '__main__':
    sio.connect('http://localhost:5000')
    sio.wait()
