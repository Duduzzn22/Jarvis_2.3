import socketio
import time

sio = socketio.Client()

@sio.event
def connect():
    print('[TESTE] Conectado ao J.A.R.V.I.S. Testando modo sexta-feira...')
    # Enviar comando para ativar a Sexta-Feira
    # Se o front antigo for usado, era 'user_message'. Para o nosso front novo é 'chat_message_stream'
    # Como o trigger acontece na intent, mas a mudança de personalidade é processada antes:
    sio.emit('user_message', {'text': 'ativar modo sexta-feira'})
    print('[TESTE] Comando enviado!')

@sio.on('personality_changed')
def on_personality_changed(data):
    print(f"\\n[SUCESSO] Personalidade alterada! Dados recebidos: {data}")

@sio.on('jarvis_response')
def on_jarvis_response(data):
    print(f"\\n[RESPOSTA DE ÁUDIO PRONTA]")
    print(f"Texto: {data.get('text')}")
    print(f"Áudio B64 recebido (Tamanho): {len(data.get('audio_b64', ''))}")
    sio.disconnect()

@sio.event
def disconnect():
    print('[TESTE] Desconectado.')

if __name__ == '__main__':
    sio.connect('http://localhost:5000')
    sio.wait()
