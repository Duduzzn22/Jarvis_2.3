"""
J.A.R.V.I.S. v2.3 — System Prompt Central
==========================================
Arquivo de referência e utilitários para o prompt principal.

O prompt em si vive em neural_core.JARVIS_SYSTEM_PROMPT_V23 e é
montado via neural_core.get_system_prompt().

Este módulo fornece:
  - get_briefing_trigger_words()  — lista de palavras que disparam briefing
  - get_critical_action_keywords() — palavras que exigem confirmação
  - get_confirmation_phrases()    — frases aceitas como confirmação vocal
  - VERSION_INFO                  — metadados da versão
"""

from __future__ import annotations

# ─── Metadados da versão ──────────────────────────────────────────────────────

VERSION_INFO: dict = {
    "version":    "2.3",
    "codename":   "Consciência Avançada",
    "build_date": "2025",
    "features": [
        "wake_word",
        "vocal_confirmation",
        "daily_briefing",
        "emotion_orb",
        "token_streaming",
        "pomodoro",
        "contextual_humor",
        "weekly_summarization",
        "self_reflection",
    ],
}

# ─── Palavras-gatilho para briefing diário ────────────────────────────────────

_BRIEFING_TRIGGERS: list[str] = [
    "bom dia", "boa tarde", "boa noite",
    "iniciar o dia", "começar o dia",
    "status", "resumo", "resumo do dia",
    "o que tenho hoje", "agenda do dia",
    "atualização", "me atualiza",
    "o que está acontecendo", "what's up jarvis",
    "jarvis status",
]

def get_briefing_trigger_words() -> list[str]:
    """Retorna lista de expressões que devem acionar o briefing automático."""
    return list(_BRIEFING_TRIGGERS)

def is_briefing_request(text: str) -> bool:
    """Verifica se o texto é um pedido de briefing."""
    t = text.lower().strip()
    return any(trigger in t for trigger in _BRIEFING_TRIGGERS)

# ─── Ações críticas que exigem confirmação vocal ─────────────────────────────

_CRITICAL_KEYWORDS: list[str] = [
    # Arquivos
    "deletar", "delete", "apagar", "remover", "excluir",
    "formatar", "format", "limpar disco",
    # Comunicação
    "enviar", "postar", "publicar", "mandar", "compartilhar",
    "send", "post", "publish",
    # Sistema
    "desligar", "reiniciar", "shutdown", "reboot",
    "executar script", "rodar script", "run script",
    # Financeiro
    "pagar", "transferir", "comprar",
]

def get_critical_action_keywords() -> list[str]:
    """Retorna lista de palavras que devem acionar confirmação antes da ação."""
    return list(_CRITICAL_KEYWORDS)

def is_critical_action(text: str) -> bool:
    """Verifica se o texto contém uma ação que exige confirmação vocal."""
    t = text.lower()
    return any(kw in t for kw in _CRITICAL_KEYWORDS)

# ─── Frases de confirmação aceitas vocalmente ─────────────────────────────────

_CONFIRM_YES: list[str] = [
    "sim confirme", "pode prosseguir", "confirmo", "confirma",
    "pode fazer", "pode executar", "execute", "ok pode",
    "sim", "yes", "afirmativo", "claro", "pode",
]

_CONFIRM_NO: list[str] = [
    "não", "cancela", "cancelar", "cancele", "abortar", "aborte",
    "para", "stop", "no", "negativo", "não faça", "desiste",
]

def get_confirmation_phrases() -> dict[str, list[str]]:
    """Retorna dicionários de frases de confirmação e cancelamento."""
    return {"yes": list(_CONFIRM_YES), "no": list(_CONFIRM_NO)}

def parse_vocal_confirmation(text: str) -> bool | None:
    """
    Interpreta texto como confirmação vocal.
    Retorna True (confirmado), False (negado) ou None (inconclusivo).
    """
    t = text.lower().strip()
    if any(phrase in t for phrase in _CONFIRM_YES):
        return True
    if any(phrase in t for phrase in _CONFIRM_NO):
        return False
    return None

# ─── Frases de saudação do briefing por período do dia ───────────────────────

def get_greeting_for_hour(hour: int) -> tuple[str, str]:
    """
    Retorna (saudação, período) de acordo com a hora do dia.
    Ex: get_greeting_for_hour(9) → ('Bom dia', 'manhã')
    """
    if 5 <= hour < 12:
        return "Bom dia", "manhã"
    elif 12 <= hour < 18:
        return "Boa tarde", "tarde"
    else:
        return "Boa noite", "noite"