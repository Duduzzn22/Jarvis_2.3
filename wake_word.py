"""
J.A.R.V.I.S. v2.3 — Wake Word Engine
======================================
Detecta "Hey Jarvis" / "Jarvis" em tempo real usando:
  - Primário:  faster-whisper (Whisper tiny — ~75 MB, offline)
  - Fallback:  keyword matching simples em texto transcrito pelo Groq

Roda em thread dedicada separada do Flask.
Ao detectar a wake word, emite evento SocketIO para todos os clientes.

Uso em App.py:
    from wake_word import WakeWordEngine
    wwe = WakeWordEngine(socketio_instance, tts_fn=generate_tts)
    wwe.start()   # na inicialização
    wwe.stop()    # no shutdown

Requisitos (opcionais — fallback automático se ausentes):
    pip install faster-whisper sounddevice numpy
"""

from __future__ import annotations

import logging
import threading
import time
import queue
from typing import Callable

logger = logging.getLogger(__name__)

# ─── Palavras-chave da wake word ─────────────────────────────────────────────

_WAKE_PHRASES: list[str] = [
    "hey jarvis", "ei jarvis", "jarvis",
    "oi jarvis", "olá jarvis",
    "hey jarvis", "jarvis acorda",
]

# Frases que NÃO são wake word (evita falso positivo)
_FALSE_POSITIVE_BLOCKLIST: list[str] = [
    "como jarvis", "tipo jarvis", "igual jarvis",
]

# ─── Configurações ────────────────────────────────────────────────────────────

SAMPLE_RATE       = 16000   # Hz — Whisper tiny espera 16kHz
CHUNK_DURATION    = 1.5     # segundos por chunk de análise
CHUNK_SAMPLES     = int(SAMPLE_RATE * CHUNK_DURATION)
SILENCE_THRESHOLD = 0.005   # RMS mínimo para processar (evita chunks silenciosos)
COOLDOWN_SECONDS  = 3.0     # segundos de silêncio após detectar wake word

# ─── Motor principal ──────────────────────────────────────────────────────────

class WakeWordEngine:
    """
    Engine de wake word offline.
    Thread-safe — pode ser iniciada/parada a qualquer momento.
    """

    def __init__(
        self,
        socketio_instance,
        tts_fn: Callable[[str], str | None] | None = None,
        on_wake: Callable[[], None] | None = None,
    ):
        """
        socketio_instance — instância do Flask-SocketIO
        tts_fn            — função generate_tts(text) → base64 (opcional)
        on_wake           — callback adicional chamado na detecção (opcional)
        """
        self._socketio   = socketio_instance
        self._tts_fn     = tts_fn
        self._on_wake    = on_wake
        self._running    = False
        self._thread: threading.Thread | None = None
        self._audio_q: queue.Queue = queue.Queue(maxsize=30)
        self._last_trigger = 0.0
        self._available  = False   # True se faster-whisper + sounddevice OK

        # Tenta carregar modelo
        self._model      = None
        self._load_model()

    # ── Carregamento do modelo ──────────────────────────────────────────────

    def _load_model(self) -> None:
        """Carrega faster-whisper tiny. Silencioso se não instalado."""
        try:
            from faster_whisper import WhisperModel  # type: ignore
            logger.info("[WAKE WORD] Carregando Whisper tiny (offline)…")
            # cpu_threads=2 é suficiente para tiny em tempo real
            self._model    = WhisperModel(
                "tiny", device="cpu", compute_type="int8", cpu_threads=2
            )
            self._available = True
            logger.info("[WAKE WORD] Whisper tiny carregado — Wake Word ATIVO")
        except ImportError:
            logger.warning(
                "[WAKE WORD] faster-whisper não instalado — "
                "Wake Word INATIVO (fallback: palma dupla disponível)\n"
                "  Para ativar: pip install faster-whisper sounddevice numpy"
            )
        except Exception as e:
            logger.error(f"[WAKE WORD] Erro ao carregar Whisper: {e}")

    # ── Controle de ciclo de vida ───────────────────────────────────────────

    def start(self) -> bool:
        """Inicia a thread de escuta. Retorna True se iniciada com sucesso."""
        if not self._available:
            logger.info("[WAKE WORD] Motor indisponível — não iniciado.")
            return False
        if self._running:
            return True

        try:
            import sounddevice as _sd  # type: ignore
            _sd  # valida import
        except ImportError:
            logger.warning("[WAKE WORD] sounddevice não instalado — Wake Word INATIVO")
            return False

        self._running = True
        self._thread  = threading.Thread(
            target=self._listen_loop, daemon=True, name="jarvis-wake-word"
        )
        self._thread.start()
        logger.info("[WAKE WORD] Thread de escuta iniciada")
        return True

    def stop(self) -> None:
        """Para a thread de escuta."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        logger.info("[WAKE WORD] Engine parada")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_available(self) -> bool:
        return self._available

    # ── Loop de escuta ──────────────────────────────────────────────────────

    def _listen_loop(self) -> None:
        """Loop principal — captura áudio e processa em chunks."""
        try:
            import sounddevice as sd  # type: ignore
            import numpy as np        # type: ignore
        except ImportError:
            logger.error("[WAKE WORD] numpy/sounddevice não disponíveis — parando")
            self._running = False
            return

        logger.info(f"[WAKE WORD] Escutando microfone @ {SAMPLE_RATE}Hz")

        def _audio_callback(indata, frames, time_info, status):
            if status:
                logger.debug(f"[WAKE WORD] Audio status: {status}")
            self._audio_q.put(indata.copy())

        try:
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=int(SAMPLE_RATE * 0.25),   # chunks de 250ms
                callback=_audio_callback,
            ):
                buffer = []
                buf_samples = 0

                while self._running:
                    try:
                        chunk = self._audio_q.get(timeout=0.5)
                        buffer.append(chunk)
                        buf_samples += len(chunk)

                        # Acumula CHUNK_DURATION de áudio antes de transcrever
                        if buf_samples >= CHUNK_SAMPLES:
                            import numpy as np
                            audio_np = np.concatenate(buffer, axis=0).flatten()
                            buffer    = []
                            buf_samples = 0

                            # Descarta chunks silenciosos
                            rms = float(np.sqrt(np.mean(audio_np ** 2)))
                            if rms < SILENCE_THRESHOLD:
                                continue

                            # Processa em background para não bloquear a captura
                            threading.Thread(
                                target=self._process_chunk,
                                args=(audio_np,),
                                daemon=True,
                            ).start()

                    except queue.Empty:
                        continue
                    except Exception as e:
                        logger.error(f"[WAKE WORD] Erro no loop de áudio: {e}")
                        time.sleep(0.5)

        except Exception as e:
            logger.error(f"[WAKE WORD] Erro ao abrir stream de áudio: {e}")
            self._running = False

    # ── Processamento de chunk ──────────────────────────────────────────────

    def _process_chunk(self, audio_np) -> None:
        """Transcreve chunk com Whisper e verifica wake word."""
        now = time.time()

        # Cooldown — ignora se acabou de disparar
        if now - self._last_trigger < COOLDOWN_SECONDS:
            return

        try:
            # Transcrição offline com Whisper tiny
            segments, _ = self._model.transcribe(
                audio_np,
                language="pt",
                beam_size=1,        # mais rápido, menos preciso — ok para wake word
                without_timestamps=True,
                condition_on_previous_text=False,
            )
            text = " ".join(seg.text for seg in segments).strip().lower()

            if text:
                logger.debug(f"[WAKE WORD] Transcrito: '{text}'")
                if self._is_wake_word(text):
                    self._on_wake_detected(text)

        except Exception as e:
            logger.error(f"[WAKE WORD] Erro na transcrição: {e}")

    def _is_wake_word(self, text: str) -> bool:
        """Verifica se o texto contém a wake word (com proteção contra falsos positivos)."""
        t = text.lower().strip()

        # Bloqueia falsos positivos conhecidos
        if any(fp in t for fp in _FALSE_POSITIVE_BLOCKLIST):
            return False

        return any(phrase in t for phrase in _WAKE_PHRASES)

    # ── Disparo da wake word ────────────────────────────────────────────────

    def _on_wake_detected(self, text: str) -> None:
        """Chamado quando a wake word é detectada."""
        self._last_trigger = time.time()
        logger.info(f"[WAKE WORD] DETECTADA: '{text}'")

        # Emite para todos os clientes SocketIO conectados
        try:
            self._socketio.emit("wake_word_detected", {
                "text":      text,
                "timestamp": self._last_trigger,
            })
        except Exception as e:
            logger.error(f"[WAKE WORD] Erro ao emitir socket: {e}")

        # Callback adicional (ex: acionar saudação)
        if self._on_wake:
            try:
                self._on_wake()
            except Exception as e:
                logger.error(f"[WAKE WORD] Erro no callback on_wake: {e}")

    # ── Status público ──────────────────────────────────────────────────────

    def get_status(self) -> dict:
        return {
            "available": self._available,
            "running":   self._running,
            "wake_phrases": _WAKE_PHRASES,
            "model":     "whisper-tiny" if self._available else None,
            "fallback":  "clap_detection",
        }


# ─── Singleton global (instanciado pelo App.py) ───────────────────────────────

_engine: WakeWordEngine | None = None

def init_wake_word(socketio_instance, tts_fn=None, on_wake=None) -> WakeWordEngine:
    """
    Inicializa e retorna o engine global de wake word.
    Deve ser chamado uma única vez em App.py após criar o socketio.
    """
    global _engine
    _engine = WakeWordEngine(
        socketio_instance=socketio_instance,
        tts_fn=tts_fn,
        on_wake=on_wake,
    )
    _engine.start()
    return _engine

def get_wake_word_status() -> dict:
    """Retorna status do engine para a rota /api/wake_word/status."""
    if _engine is None:
        return {"available": False, "running": False, "reason": "not_initialized"}
    return _engine.get_status()

def stop_wake_word() -> None:
    """Para o engine (chamado no shutdown)."""
    if _engine:
        _engine.stop()


# ─── Teste local ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.DEBUG)

    print("=== Wake Word Engine — Teste ===")
    print("Testando detecção de frases...\n")

    engine = WakeWordEngine.__new__(WakeWordEngine)
    engine._socketio     = None
    engine._tts_fn       = None
    engine._on_wake      = None
    engine._running      = False
    engine._last_trigger = 0.0
    engine._model        = None
    engine._available    = False
    engine._audio_q      = queue.Queue()

    frases_teste = [
        ("hey jarvis, abre o spotify", True),
        ("jarvis acorda", True),
        ("olá jarvis", True),
        ("como jarvis faria isso?", False),    # falso positivo bloqueado
        ("Boa tarde, abre o chrome", False),
        ("oi jarvis, que horas são?", True),
    ]

    for frase, esperado in frases_teste:
        resultado = engine._is_wake_word(frase.lower())
        status = "OK" if resultado == esperado else "FALHOU"
        print(f"  [{status}] '{frase}' → {resultado} (esperado: {esperado})")

    print("\nStatus do engine:")
    print(engine.get_status())