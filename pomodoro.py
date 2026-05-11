"""
J.A.R.V.I.S. v2.3 — Pomodoro Engine
======================================
Gerencia sessões Pomodoro completas, controladas por voz.

Estados:
  idle → working(25min) → short_break(5min) → working → ... → long_break(15min)

Após 4 pomodoros: long_break de 15 min.

Comandos de voz reconhecidos (detectados em App.py):
  - "iniciar pomodoro" / "começar pomodoro" / "foco"
  - "pausar pomodoro" / "pausar foco"
  - "pular intervalo" / "próximo pomodoro"
  - "parar pomodoro" / "cancelar pomodoro"
  - "status pomodoro" / "quanto tempo falta"
  - "quantos pomodoros" / "meu progresso"

Uso em App.py:
    from pomodoro import PomodoroManager, is_pomodoro_command, handle_pomodoro_command
    pomodoro = PomodoroManager(socketio_instance, tts_fn=generate_tts)
    ...
    if is_pomodoro_command(text):
        response = handle_pomodoro_command(text, pomodoro, sid)
"""

from __future__ import annotations

import time
import threading
import logging
import datetime
from enum import Enum, auto
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ─── Configuração ─────────────────────────────────────────────────────────────

WORK_DURATION        = 25 * 60   # 25 minutos
SHORT_BREAK_DURATION =  5 * 60   # 5 minutos
LONG_BREAK_DURATION  = 15 * 60   # 15 minutos
POMODOROS_BEFORE_LONG = 4        # pomodoros antes do descanso longo

# ─── Estados ──────────────────────────────────────────────────────────────────

class PomodoroState(Enum):
    IDLE        = auto()
    WORKING     = auto()
    SHORT_BREAK = auto()
    LONG_BREAK  = auto()
    PAUSED      = auto()

STATE_LABELS: dict[PomodoroState, str] = {
    PomodoroState.IDLE:        "inativo",
    PomodoroState.WORKING:     "trabalhando",
    PomodoroState.SHORT_BREAK: "pausa curta",
    PomodoroState.LONG_BREAK:  "pausa longa",
    PomodoroState.PAUSED:      "pausado",
}

# ─── Palavras-gatilho ─────────────────────────────────────────────────────────

_TRIGGERS: dict[str, list[str]] = {
    "start": [
        "iniciar pomodoro", "começar pomodoro", "inicia pomodoro",
        "modo foco", "iniciar foco", "começar foco",
        "pomodoro", "foco jarvis", "hora de focar",
    ],
    "pause": [
        "pausar pomodoro", "pausar foco", "pausa pomodoro",
        "pausa no foco",
    ],
    "resume": [
        "continuar pomodoro", "retomar pomodoro", "resume pomodoro",
        "continuar foco", "retomar foco",
    ],
    "skip": [
        "pular intervalo", "próximo pomodoro", "pula intervalo",
        "skip pausa", "próxima sessão",
    ],
    "stop": [
        "parar pomodoro", "cancelar pomodoro", "encerrar pomodoro",
        "para pomodoro", "sair do foco",
    ],
    "status": [
        "status pomodoro", "quanto tempo falta", "status foco",
        "quantos pomodoros", "meu progresso", "tempo restante",
        "como está o pomodoro",
    ],
}

def is_pomodoro_command(text: str) -> bool:
    """Verifica se o texto é um comando Pomodoro."""
    t = text.lower().strip()
    return any(
        trigger in t
        for triggers in _TRIGGERS.values()
        for trigger in triggers
    )

def _classify_command(text: str) -> str | None:
    """Classifica o tipo de comando Pomodoro. Retorna None se não reconhecido.
    A ordem importa: status e stop têm prioridade sobre start."""
    t = text.lower().strip()
    # Verifica na ordem de especificidade (mais específico primeiro)
    for cmd in ["status", "stop", "pause", "resume", "skip", "start"]:
        if any(tr in t for tr in _TRIGGERS[cmd]):
            return cmd
    return None

# ─── Engine ───────────────────────────────────────────────────────────────────

class PomodoroManager:
    """
    Gerenciador de sessões Pomodoro.
    Thread-safe — pode ser usado em contexto multi-thread do Flask.
    """

    def __init__(self, socketio_instance, tts_fn=None):
        self._socketio       = socketio_instance
        self._tts_fn         = tts_fn
        self._lock           = threading.Lock()
        self._timer: threading.Thread | None = None

        # Estado
        self._state          = PomodoroState.IDLE
        self._start_time     = 0.0
        self._pause_time     = 0.0
        self._duration       = 0
        self._elapsed_paused = 0.0

        # Contadores
        self._pomodoros_done = 0
        self._session_start: datetime.datetime | None = None

        # Sessão atual (para o sid que iniciou)
        self._active_sid: str = ""

    # ── Controles ─────────────────────────────────────────────────────────────

    def start(self, sid: str = "") -> str:
        """Inicia uma nova sessão de trabalho."""
        with self._lock:
            if self._state == PomodoroState.WORKING:
                elapsed = self._get_elapsed()
                restante = max(0, WORK_DURATION - elapsed)
                return f"Já há uma sessão em andamento, Senhor. Faltam {self._fmt_time(restante)} para terminar."

            self._state          = PomodoroState.WORKING
            self._start_time     = time.time()
            self._elapsed_paused = 0.0
            self._duration       = WORK_DURATION
            self._active_sid     = sid

            if not self._session_start:
                self._session_start = datetime.datetime.now()

            self._start_timer()
            self._emit_update()

            pomo_num = self._pomodoros_done + 1
            return (
                f"Pomodoro número {pomo_num} iniciado, Senhor. "
                f"Vinte e cinco minutos de foco total. Bom trabalho."
            )

    def pause(self) -> str:
        """Pausa o timer atual."""
        with self._lock:
            if self._state not in (PomodoroState.WORKING, PomodoroState.SHORT_BREAK, PomodoroState.LONG_BREAK):
                return "Não há sessão ativa para pausar, Senhor."
            self._pause_time = time.time()
            prev_state       = self._state
            self._state      = PomodoroState.PAUSED
            self._stop_timer()
            self._emit_update()
            return f"Pomodoro pausado, Senhor. A sessão de {STATE_LABELS[prev_state]} foi suspensa."

    def resume(self) -> str:
        """Retoma a sessão pausada."""
        with self._lock:
            if self._state != PomodoroState.PAUSED:
                return "Não há sessão pausada, Senhor."
            self._elapsed_paused += time.time() - self._pause_time
            # Restaura estado anterior
            self._state = PomodoroState.WORKING
            self._start_timer()
            self._emit_update()
            elapsed  = self._get_elapsed()
            restante = max(0, self._duration - elapsed)
            return f"Retomando, Senhor. Faltam {self._fmt_time(restante)} para o fim da sessão."

    def skip(self) -> str:
        """Pula o intervalo atual e vai direto para a próxima sessão."""
        with self._lock:
            if self._state in (PomodoroState.SHORT_BREAK, PomodoroState.LONG_BREAK):
                self._stop_timer()
                return self._advance_to_work()
            elif self._state == PomodoroState.WORKING:
                self._stop_timer()
                return self._advance_to_break()
            return "Não há sessão ativa, Senhor."

    def stop(self) -> str:
        """Para completamente o Pomodoro."""
        with self._lock:
            self._stop_timer()
            total = self._pomodoros_done
            self._reset()
            self._emit_update()
            if total > 0:
                return (
                    f"Pomodoro encerrado. Você completou {total} "
                    f"{'sessão' if total == 1 else 'sessões'} hoje, Senhor. Excelente trabalho."
                )
            return "Pomodoro encerrado, Senhor."

    def get_status(self) -> str:
        """Retorna status verboso atual para TTS."""
        with self._lock:
            if self._state == PomodoroState.IDLE:
                done = self._pomodoros_done
                if done > 0:
                    return f"Não há sessão ativa no momento. Você completou {done} pomodoros nesta sessão, Senhor."
                return "Não há sessão Pomodoro ativa, Senhor. Diga 'iniciar pomodoro' para começar."

            elapsed  = self._get_elapsed()
            restante = max(0, self._duration - elapsed)
            state_lbl = STATE_LABELS[self._state]

            return (
                f"Status do Pomodoro: {state_lbl}. "
                f"Faltam {self._fmt_time(restante)}. "
                f"Sessões completadas hoje: {self._pomodoros_done}."
            )

    def get_status_dict(self) -> dict:
        """Retorna estado como dicionário para SocketIO e frontend."""
        with self._lock:
            elapsed  = self._get_elapsed() if self._state != PomodoroState.IDLE else 0
            restante = max(0, self._duration - elapsed) if self._duration else 0
            return {
                "state":            self._state.name.lower(),
                "state_label":      STATE_LABELS[self._state],
                "elapsed_seconds":  int(elapsed),
                "remaining_seconds":int(restante),
                "duration_seconds": self._duration,
                "pomodoros_done":   self._pomodoros_done,
                "progress_pct":     int((elapsed / self._duration * 100) if self._duration else 0),
            }

    # ── Internos ──────────────────────────────────────────────────────────────

    def _get_elapsed(self) -> float:
        """Tempo decorrido em segundos, descontando pausas."""
        if self._start_time == 0:
            return 0.0
        if self._state == PomodoroState.PAUSED:
            return (self._pause_time - self._start_time) - self._elapsed_paused
        return (time.time() - self._start_time) - self._elapsed_paused

    def _start_timer(self) -> None:
        """Inicia thread de timer que dispara ao fim da sessão."""
        self._stop_timer()
        elapsed  = self._get_elapsed()
        restante = max(1, self._duration - elapsed)

        def _run():
            time.sleep(restante)
            if self._state in (PomodoroState.WORKING, PomodoroState.SHORT_BREAK, PomodoroState.LONG_BREAK):
                self._on_timer_done()

        self._timer = threading.Thread(target=_run, daemon=True, name="jarvis-pomodoro-timer")
        self._timer.start()

    def _stop_timer(self) -> None:
        """Cancela o timer atual (a thread termina na próxima verificação)."""
        self._timer = None   # A thread verifica self._state antes de chamar _on_timer_done

    def _on_timer_done(self) -> None:
        """Chamado quando o timer da sessão atual expira."""
        with self._lock:
            if self._state == PomodoroState.WORKING:
                texto = self._advance_to_break()
            elif self._state in (PomodoroState.SHORT_BREAK, PomodoroState.LONG_BREAK):
                texto = self._advance_to_work()
            else:
                return

        # Fala o texto e emite evento
        logger.info(f"[POMODORO] Timer expirou: {texto}")
        if self._tts_fn:
            try:
                audio = self._tts_fn(texto)
                self._socketio.emit("jarvis_response", {
                    "text":      texto,
                    "audio_b64": audio,
                    "api_used":  "pomodoro",
                    "intent":    "pomodoro_transition",
                })
            except Exception as e:
                logger.error(f"[POMODORO] Erro ao falar transição: {e}")

    def _advance_to_break(self) -> str:
        """Avança para o próximo intervalo."""
        self._pomodoros_done += 1
        if self._pomodoros_done % POMODOROS_BEFORE_LONG == 0:
            self._state    = PomodoroState.LONG_BREAK
            self._duration = LONG_BREAK_DURATION
            msg = (
                f"Excelente! Você completou {self._pomodoros_done} pomodoros, Senhor. "
                f"Pausa longa de {LONG_BREAK_DURATION // 60} minutos iniciada. Descanse bem."
            )
        else:
            self._state    = PomodoroState.SHORT_BREAK
            self._duration = SHORT_BREAK_DURATION
            msg = (
                f"Pomodoro {self._pomodoros_done} concluído, Senhor! "
                f"Pausa de {SHORT_BREAK_DURATION // 60} minutos. Aproveite."
            )
        self._start_time     = time.time()
        self._elapsed_paused = 0.0
        self._start_timer()
        self._emit_update()
        return msg

    def _advance_to_work(self) -> str:
        """Retorna para sessão de trabalho."""
        self._state          = PomodoroState.WORKING
        self._duration       = WORK_DURATION
        self._start_time     = time.time()
        self._elapsed_paused = 0.0
        self._start_timer()
        self._emit_update()
        pomo_num = self._pomodoros_done + 1
        return (
            f"Pausa encerrada. Iniciando pomodoro {pomo_num}, Senhor. "
            f"Foco total por {WORK_DURATION // 60} minutos."
        )

    def _reset(self) -> None:
        """Reseta o estado completo."""
        self._state          = PomodoroState.IDLE
        self._start_time     = 0.0
        self._elapsed_paused = 0.0
        self._duration       = 0
        self._pomodoros_done = 0
        self._session_start  = None

    def _emit_update(self) -> None:
        """Emite evento de atualização para o frontend."""
        try:
            self._socketio.emit("pomodoro_update", self.get_status_dict())
        except Exception as e:
            logger.debug(f"[POMODORO] Erro ao emitir update: {e}")

    @staticmethod
    def _fmt_time(seconds: float) -> str:
        """Formata segundos em texto legível."""
        s = int(seconds)
        if s <= 0:
            return "zero segundos"
        mins = s // 60
        secs = s % 60
        if mins > 0 and secs > 0:
            return f"{mins} {'minuto' if mins == 1 else 'minutos'} e {secs} segundos"
        elif mins > 0:
            return f"{mins} {'minuto' if mins == 1 else 'minutos'}"
        return f"{secs} segundos"


# ─── Handler de comando ───────────────────────────────────────────────────────

def handle_pomodoro_command(text: str, manager: "PomodoroManager", sid: str = "") -> str:
    """
    Processa um comando Pomodoro e retorna a resposta para TTS.
    Chamado pelo App.py quando is_pomodoro_command() retorna True.
    """
    cmd = _classify_command(text)
    if cmd == "start":
        return manager.start(sid)
    elif cmd == "pause":
        return manager.pause()
    elif cmd == "resume":
        return manager.resume()
    elif cmd == "skip":
        return manager.skip()
    elif cmd == "stop":
        return manager.stop()
    elif cmd == "status":
        return manager.get_status()
    return "Desculpe, Senhor. Não entendi o comando do Pomodoro."


# ─── Singleton global ─────────────────────────────────────────────────────────

_manager: PomodoroManager | None = None

def init_pomodoro(socketio_instance, tts_fn=None) -> PomodoroManager:
    """Inicializa e retorna o gerenciador global de Pomodoro."""
    global _manager
    _manager = PomodoroManager(socketio_instance, tts_fn=tts_fn)
    logger.info("[POMODORO] Engine inicializada")
    return _manager

def get_pomodoro_manager() -> PomodoroManager | None:
    return _manager


# ─── Teste local ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== Pomodoro Engine — Teste ===\n")

    # Testa detecção de comandos
    testes = [
        ("iniciar pomodoro", True),
        ("começar pomodoro", True),
        ("pausar foco", True),
        ("quanto tempo falta", True),
        ("abre o spotify", False),
        ("status pomodoro", True),
        ("parar pomodoro", True),
        ("Boa tarde Jarvis", False),
    ]
    for texto, esperado in testes:
        r = is_pomodoro_command(texto)
        status = "OK" if r == esperado else "FALHOU"
        cmd    = _classify_command(texto)
        print(f"  [{status}] '{texto}' → {r} (cmd: {cmd})")

    print("\nFormatação de tempo:")
    for s in [5, 60, 90, 300, 1500, 0]:
        print(f"  {s}s → '{PomodoroManager._fmt_time(s)}'")