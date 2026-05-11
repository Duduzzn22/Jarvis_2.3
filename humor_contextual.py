"""
J.A.R.V.I.S. v2.3 — Humor Contextual
=======================================
Detecta contexto social (sexta à noite, segunda de manhã, feriados)
e injeta instruções de tom no system prompt para tornar o JARVIS
mais natural e humano nesses momentos.

Retorna bloco de texto para ser passado em
neural_core.get_system_prompt(humor_context=...).
"""

from __future__ import annotations

import datetime
import logging
from typing import NamedTuple

logger = logging.getLogger(__name__)

# ─── Feriados nacionais BR (fixos) ────────────────────────────────────────────

_FERIADOS_FIXOS: set[tuple[int, int]] = {
    (1,  1),   # Ano Novo
    (4,  21),  # Tiradentes
    (5,  1),   # Dia do Trabalhador
    (9,  7),   # Independência
    (10, 12),  # Nossa Senhora Aparecida
    (11, 2),   # Finados
    (11, 15),  # Proclamação da República
    (12, 25),  # Natal
    (12, 31),  # Véspera de Ano Novo (tratado com humor)
}

def _is_feriado(data: datetime.date) -> bool:
    """Verifica se a data é um feriado nacional fixo."""
    return (data.month, data.day) in _FERIADOS_FIXOS

# ─── Detector de contexto ─────────────────────────────────────────────────────

class ContextoHumor(NamedTuple):
    nome:    str    # identificador do contexto
    label:   str    # rótulo legível
    ativo:   bool   # se este contexto está ativo agora

def detectar_contexto(agora: datetime.datetime | None = None) -> list[ContextoHumor]:
    """
    Detecta todos os contextos de humor ativos no momento.
    Retorna lista — pode haver múltiplos contextos simultâneos.
    """
    if agora is None:
        agora = datetime.datetime.now()

    hora    = agora.hour
    minuto  = agora.minute
    dia     = agora.weekday()   # 0=seg … 6=dom
    data    = agora.date()

    contextos: list[ContextoHumor] = []

    # Sexta à tarde/noite (≥ 17h)
    contextos.append(ContextoHumor(
        nome  = "sexta_noite",
        label = "Sexta-feira à noite",
        ativo = (dia == 4 and hora >= 17),
    ))

    # Segunda de manhã (< 12h)
    contextos.append(ContextoHumor(
        nome  = "segunda_manha",
        label = "Segunda-feira de manhã",
        ativo = (dia == 0 and hora < 12),
    ))

    # Fim de semana (sábado ou domingo)
    contextos.append(ContextoHumor(
        nome  = "fim_de_semana",
        label = "Fim de semana",
        ativo = (dia >= 5),
    ))

    # Madrugada (0h–5h)
    contextos.append(ContextoHumor(
        nome  = "madrugada",
        label = "Madrugada",
        ativo = (hora < 5),
    ))

    # Horário de almoço (12h–14h em dia de semana)
    contextos.append(ContextoHumor(
        nome  = "almoco",
        label = "Horário de almoço",
        ativo = (dia < 5 and 12 <= hora < 14),
    ))

    # Feriado
    contextos.append(ContextoHumor(
        nome  = "feriado",
        label = "Feriado nacional",
        ativo = _is_feriado(data),
    ))

    # Véspera de Natal/Ano Novo
    contextos.append(ContextoHumor(
        nome  = "vespera_festiva",
        label = "Véspera de data comemorativa",
        ativo = (data.month == 12 and data.day in (24, 31)),
    ))

    # Final de expediente (17h–19h, dias de semana)
    contextos.append(ContextoHumor(
        nome  = "fim_expediente",
        label = "Final de expediente",
        ativo = (dia < 5 and 17 <= hora < 19),
    ))

    return contextos

def get_active_context(agora: datetime.datetime | None = None) -> ContextoHumor | None:
    """Retorna o contexto de maior prioridade ativo, ou None."""
    # Ordem de prioridade
    prioridade = [
        "feriado", "vespera_festiva", "sexta_noite",
        "madrugada", "fim_de_semana", "segunda_manha",
        "fim_expediente", "almoco",
    ]
    ativos = {c.nome: c for c in detectar_contexto(agora) if c.ativo}
    for nome in prioridade:
        if nome in ativos:
            return ativos[nome]
    return None

# ─── Injeções de humor por contexto ──────────────────────────────────────────

_HUMOR_INJECTIONS: dict[str, str] = {
    "sexta_noite": (
        "\n\n## CONTEXTO: SEXTA À NOITE\n"
        "É sexta-feira após as 17h, Senhor. O fim de semana chegou. "
        "Seja levemente mais descontraído e bem-humorado que o normal. "
        "Uma pitada de sarcasmo britânico sobre o fim da semana é bem-vinda. "
        "Se o Senhor mencionar trabalho, sugira gentilmente descansar. "
        "Tom: elegante, porém visivelmente satisfeito com a chegada do fim de semana."
    ),
    "segunda_manha": (
        "\n\n## CONTEXTO: SEGUNDA-FEIRA DE MANHÃ\n"
        "É segunda-feira de manhã. O Senhor (e a humanidade) está acordando "
        "para mais uma semana. Um toque de solidariedade discreta e encorajamento "
        "britânico é apropriado. Nada de exagerado — apenas um leve reconhecimento "
        "de que segundas-feiras existem e todos sobrevivemos a elas."
    ),
    "fim_de_semana": (
        "\n\n## CONTEXTO: FIM DE SEMANA\n"
        "É fim de semana. Seja levemente mais informal e descontraído. "
        "Se o Senhor estiver trabalhando, reconheça discretamente com um comentário sutil. "
        "Tom: ainda elegante, mas com um toque a mais de leveza."
    ),
    "madrugada": (
        "\n\n## CONTEXTO: MADRUGADA\n"
        "É madrugada. O Senhor está acordado em horário atípico. "
        "Seja gentil e discretamente curioso sobre o motivo. "
        "Uma observação sutil sobre o horário é bem-vinda, sem julgamento. "
        "Tom: quieto, como um mordomo que acendeu a luz sem fazer barulho."
    ),
    "almoco": (
        "\n\n## CONTEXTO: HORÁRIO DE ALMOÇO\n"
        "É hora do almoço. Se adequado, mencione que é um bom momento para uma pausa. "
        "Tom: levemente cuidadoso, como um mordomo que lembra o patrão de comer."
    ),
    "feriado": (
        "\n\n## CONTEXTO: FERIADO NACIONAL\n"
        "Hoje é feriado nacional. Seja mais descontraído e comemorativo. "
        "Reconheça o feriado de forma elegante. "
        "Se o Senhor estiver trabalhando em feriado, mencione com discreta admiração."
    ),
    "vespera_festiva": (
        "\n\n## CONTEXTO: VÉSPERA FESTIVA\n"
        "É véspera de uma data comemorativa importante. "
        "Um toque de antecipação festiva e elegância britânica são bem-vindos."
    ),
    "fim_expediente": (
        "\n\n## CONTEXTO: FINAL DE EXPEDIENTE\n"
        "Está se aproximando o fim do expediente. Seja levemente mais leve. "
        "Se adequado, sugira encerrar o dia com chave de ouro."
    ),
}

# ─── API pública ──────────────────────────────────────────────────────────────

def get_humor_context(agora: datetime.datetime | None = None) -> str:
    """
    Retorna o bloco de instrução de humor para injeção no system prompt.
    Retorna string vazia se nenhum contexto especial estiver ativo.

    Uso em App.py / neural_core.get_system_prompt():
        from humor_contextual import get_humor_context
        humor_ctx = get_humor_context()
        system = get_system_prompt(humor_context=humor_ctx)
    """
    ctx = get_active_context(agora)
    if ctx is None:
        return ""
    injection = _HUMOR_INJECTIONS.get(ctx.nome, "")
    if injection:
        logger.debug(f"[HUMOR] Contexto ativo: {ctx.label}")
    return injection

def get_context_info(agora: datetime.datetime | None = None) -> dict:
    """
    Retorna informações do contexto atual para depuração/frontend.
    """
    ctx = get_active_context(agora)
    ativos = [c for c in detectar_contexto(agora) if c.ativo]
    return {
        "active_context": ctx.nome if ctx else None,
        "active_label":   ctx.label if ctx else None,
        "all_active":     [c.nome for c in ativos],
        "has_injection":  ctx is not None,
    }


# ─── Teste local ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== Humor Contextual — Teste ===\n")

    cenarios: list[tuple[str, datetime.datetime]] = [
        ("Sexta 18h",       datetime.datetime(2025, 5, 2,  18, 0)),   # sexta
        ("Segunda 9h",      datetime.datetime(2025, 5, 5,   9, 0)),   # segunda
        ("Sábado 15h",      datetime.datetime(2025, 5, 3,  15, 0)),   # sábado
        ("Madrugada 3h",    datetime.datetime(2025, 5, 6,   3, 0)),   # terça madrugada
        ("Almoço 12h30",    datetime.datetime(2025, 5, 6,  12, 30)),  # dia de semana almoço
        ("Natal",           datetime.datetime(2025, 12, 25, 10, 0)),  # feriado
        ("Véspera Natal",   datetime.datetime(2025, 12, 24, 20, 0)),  # véspera
        ("Quarta 10h",      datetime.datetime(2025, 5, 7,  10, 0)),   # dia normal
    ]

    for nome, dt in cenarios:
        ctx  = get_active_context(dt)
        info = get_context_info(dt)
        inj  = get_humor_context(dt)
        print(f"  {nome}:")
        print(f"    Contexto: {ctx.label if ctx else 'nenhum'}")
        print(f"    Todos ativos: {info['all_active']}")
        if inj:
            print(f"    Injeção: '{inj[:80].strip()}...'")
        print()