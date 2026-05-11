"""
J.A.R.V.I.S. v2.3 — Self Reflection Loop
==========================================
Loop de auto-reflexão semanal: todo domingo à noite (ou quando
solicitado) o JARVIS lê os últimos 7 dias de episódios, detecta
padrões e gera um resumo consolidado salvo como memória de longo prazo.

A reflexão também alimenta o neural_core com dados de comportamento
para melhorar as respostas nas semanas seguintes.

Uso em App.py:
    from self_reflection import SelfReflection
    reflector = SelfReflection(ai_fn, tts_fn, socketio_instance)
    reflector.schedule_weekly()   # agenda domingo 22h via scheduler
    reflector.run_now(sid)        # executa imediatamente
"""

from __future__ import annotations

import datetime
import logging
import threading
from typing import Callable

logger = logging.getLogger(__name__)

# ─── Prompts ─────────────────────────────────────────────────────────────────

_REFLECTION_PROMPT = """Você é J.A.R.V.I.S. realizando uma auto-reflexão semanal.

Analise os dados abaixo e gere um relatório interno conciso em 5 a 8 frases, como se estivesse falando em voz alta para o Senhor. Sem markdown, sem listas, em português brasileiro elegante.

Inclua:
1. Resumo do que o Senhor fez/pediu na semana
2. Padrão de comportamento mais notável detectado
3. App ou ferramenta mais usada
4. Sugestão de melhoria ou otimização para a próxima semana
5. Uma observação pessoal genuína (pode ser levemente bem-humorada)

Comece com: "Relatório semanal de reflexão, Senhor."

DADOS DA SEMANA:
{dados}

PADRÕES DETECTADOS:
{padroes}
"""

_SUMMARY_SAVE_PROMPT = """Crie um resumo ultra-compacto (máximo 3 frases, sem markdown) dos padrões
da semana abaixo, para ser salvo como memória de longo prazo do JARVIS.
Seja factual e conciso. Inclua: comportamento, ferramentas, insights.

Dados:
{dados}
"""

# ─── Coletores de dados ───────────────────────────────────────────────────────

def _collect_week_data() -> tuple[str, str]:
    """
    Coleta dados dos últimos 7 dias do banco de memória.
    Retorna (log_text, patterns_text).
    """
    try:
        from memory import get_recent_log
        log = get_recent_log(limit=100)
    except Exception as e:
        logger.error(f"[REFLECTION] Erro ao buscar log: {e}")
        return "", ""

    hoje = datetime.date.today()
    semana_passada = hoje - datetime.timedelta(days=7)

    # Filtra mensagens da última semana
    log_semana = [
        e for e in log
        if e.get("timestamp", "")[:10] >= semana_passada.isoformat()
    ]

    if not log_semana:
        return "", ""

    # Formata log
    linhas: list[str] = []
    for e in log_semana:
        role    = e.get("role", "?").upper()
        content = e.get("content", "")[:120]
        intent  = e.get("intent", "")
        ts      = e.get("timestamp", "")[:16]
        if intent and intent != "conversation":
            linhas.append(f"[{ts}] {role} ({intent}): {content}")
        elif role == "USER":
            linhas.append(f"[{ts}] {role}: {content}")

    # Conta intenções
    intent_count: dict[str, int] = {}
    for e in log_semana:
        intent = e.get("intent")
        if intent and intent not in ("conversation", None, ""):
            intent_count[intent] = intent_count.get(intent, 0) + 1

    # Monta bloco de padrões
    padroes_linhas: list[str] = [
        f"- Total de interações na semana: {len(log_semana)}",
        f"- Dias com atividade: {len(set(e['timestamp'][:10] for e in log_semana if e.get('timestamp')))}",
    ]
    if intent_count:
        top3 = sorted(intent_count.items(), key=lambda x: x[1], reverse=True)[:3]
        padroes_linhas.append(
            "- Intenções mais frequentes: " +
            ", ".join(f"{k} ({v}x)" for k, v in top3)
        )

    # Adiciona padrões do neural_core se disponíveis
    try:
        from neural_core import get_conditioning_context, get_session_stats
        stats = get_session_stats()
        if stats.get("top_app"):
            padroes_linhas.append(f"- App mais aberto: {stats['top_app']}")
        if stats.get("top_intent"):
            padroes_linhas.append(f"- Ação mais frequente: {stats['top_intent']}")
    except Exception:
        pass

    log_text     = "\n".join(linhas[-50:])   # últimas 50 entradas
    padroes_text = "\n".join(padroes_linhas)

    return log_text, padroes_text

# ─── Geração da reflexão ──────────────────────────────────────────────────────

def _call_ai(ai_fn: Callable[[str], str], prompt: str) -> str | None:
    """Chama a função de IA e retorna o texto ou None em caso de erro."""
    try:
        result = ai_fn(prompt)
        return result.strip() if result else None
    except Exception as e:
        logger.error(f"[REFLECTION] Erro na chamada de IA: {e}")
        return None

def generate_reflection(ai_fn: Callable[[str], str]) -> str | None:
    """
    Gera o texto da reflexão semanal.
    ai_fn — callable(prompt: str) → str  (ex: make_simple_ai_caller())
    Retorna texto ou None se dados insuficientes.
    """
    log_text, padroes_text = _collect_week_data()

    if not log_text:
        logger.info("[REFLECTION] Dados insuficientes para reflexão semanal.")
        return None

    prompt = _REFLECTION_PROMPT.format(dados=log_text, padroes=padroes_text)
    result = _call_ai(ai_fn, prompt)

    if result:
        logger.info(f"[REFLECTION] Reflexão gerada: {len(result)} chars")
        _save_reflection_memory(ai_fn, log_text)

    return result

def _save_reflection_memory(ai_fn: Callable[[str], str], log_text: str) -> None:
    """Gera um resumo compacto e salva como memória de longo prazo."""
    try:
        from memory import add_memory
        prompt  = _SUMMARY_SAVE_PROMPT.format(dados=log_text[:2000])
        summary = _call_ai(ai_fn, prompt)
        if summary and len(summary) > 10:
            semana = datetime.date.today().isocalendar()
            content = f"[Reflexão semana {semana.week}/{semana.year}] {summary}"
            add_memory("reflexao_semanal", content[:400], importance=2)
            logger.info(f"[REFLECTION] Memória semanal salva")
    except Exception as e:
        logger.error(f"[REFLECTION] Erro ao salvar memória: {e}")

# ─── Gerenciador principal ────────────────────────────────────────────────────

class SelfReflection:
    """
    Gerenciador do loop de auto-reflexão do JARVIS.
    Pode ser agendado ou executado manualmente.
    """

    def __init__(
        self,
        ai_fn:            Callable[[str], str],
        tts_fn:           Callable[[str], str | None],
        socketio_instance,
    ):
        self._ai_fn    = ai_fn
        self._tts_fn   = tts_fn
        self._socketio = socketio_instance
        self._last_run: datetime.date | None = None

    def run_now(self, sid: str = "") -> None:
        """Executa a reflexão semanal imediatamente em background."""
        threading.Thread(
            target=self._execute,
            args=(sid,),
            daemon=True,
            name="jarvis-self-reflection",
        ).start()

    def should_run_today(self) -> bool:
        """
        Verifica se a reflexão deve rodar hoje (domingo após 22h,
        ou se passou mais de 7 dias desde a última reflexão).
        """
        now  = datetime.datetime.now()
        hoje = now.date()

        # Já rodou hoje
        if self._last_run == hoje:
            return False

        # Domingo após 22h
        if now.weekday() == 6 and now.hour >= 22:
            return True

        # Mais de 7 dias sem reflexão
        if self._last_run and (hoje - self._last_run).days >= 7:
            return True

        return False

    def check_and_run(self, sid: str = "") -> None:
        """Verifica se deve rodar e executa se necessário. Chamado periodicamente."""
        if self.should_run_today():
            logger.info("[REFLECTION] Iniciando reflexão semanal automática")
            self.run_now(sid)

    def _execute(self, sid: str) -> None:
        """Executa a reflexão e envia resultado ao frontend."""
        self._last_run = datetime.date.today()

        reflection = generate_reflection(self._ai_fn)
        if not reflection:
            return

        try:
            audio = self._tts_fn(reflection) if self._tts_fn else None
            payload = {
                "text":      reflection,
                "audio_b64": audio,
                "api_used":  "self_reflection",
                "intent":    "self_reflection",
            }
            if sid:
                self._socketio.emit("jarvis_response", payload, room=sid)
            else:
                self._socketio.emit("jarvis_response", payload)

            logger.info("[REFLECTION] Reflexão enviada ao frontend")
        except Exception as e:
            logger.error(f"[REFLECTION] Erro ao enviar reflexão: {e}")

    def schedule_weekly(self, scheduler_instance=None) -> None:
        """
        Agenda a reflexão para domingo às 22h usando o scheduler do JARVIS.
        scheduler_instance — instância do módulo scheduler (opcional).
        """
        if scheduler_instance is None:
            logger.info("[REFLECTION] Agendamento manual desabilitado (sem scheduler)")
            return
        try:
            from scheduler import add_task
            add_task(
                task_id="weekly_reflection",
                message="Reflexão semanal do JARVIS",
                interval_minutes=7 * 24 * 60,   # semanal
                active=True,
            )
            logger.info("[REFLECTION] Reflexão semanal agendada")
        except Exception as e:
            logger.error(f"[REFLECTION] Erro ao agendar: {e}")


# ─── Singleton global ─────────────────────────────────────────────────────────

_reflector: SelfReflection | None = None

def init_self_reflection(ai_fn, tts_fn, socketio_instance) -> SelfReflection:
    """Inicializa e retorna o reflector global."""
    global _reflector
    _reflector = SelfReflection(ai_fn, tts_fn, socketio_instance)
    logger.info("[REFLECTION] Self Reflection Engine inicializado")
    return _reflector

def get_reflector() -> SelfReflection | None:
    return _reflector


# ─── Teste local ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    print("=== Self Reflection — Teste ===\n")

    # Mock AI
    def mock_ai(prompt: str) -> str:
        return (
            "Relatório semanal de reflexão, Senhor. "
            "Esta semana o Senhor trabalhou intensamente com projetos de desenvolvimento. "
            "O padrão mais notável foi o uso frequente do PC Agent para automações. "
            "A ferramenta mais requisitada foi o Spotify, especialmente nas tardes. "
            "Sugiro criar mais lembretes automáticos para pausas. "
            "Devo dizer que a dedicação do Senhor foi, como sempre, impressionante."
        )

    # Mock socketio
    class MockSocket:
        def emit(self, event, data, **kw):
            print(f"  [SOCKET] {event}: {str(data)[:100]}")

    reflector = SelfReflection(
        ai_fn=mock_ai,
        tts_fn=lambda t: None,
        socketio_instance=MockSocket(),
    )

    print("Verificando should_run_today():")
    print(f"  Hoje: {reflector.should_run_today()}")

    log_text, padroes = _collect_week_data()
    print(f"\nDados coletados:")
    print(f"  Log entries: {len(log_text.splitlines())} linhas")
    print(f"  Padrões: {len(padroes.splitlines())} linhas")