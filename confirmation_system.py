"""
J.A.R.V.I.S. v2.3 — Sistema de Confirmação Vocal
==================================================
Gerencia confirmações para ações críticas (deletar arquivos, enviar
mensagens, postar em redes sociais, comandos shell, etc.).

Fluxo:
  1. App.py detecta intenção crítica
  2. Chama request_vocal_confirmation(intent, params, sid)
  3. JARVIS fala: "Senhor, confirma esta ação?"
  4. Usuário responde vocalmente ou por texto
  5. Confirmação é resolvida → ação prossegue ou é cancelada

Compatibilidade retroativa com o sistema antigo de confirmação
já existente no App.py (request_confirmation / CONFIRM_INTENTS).
"""

from __future__ import annotations

import uuid
import logging
from threading import Event
from typing import Any

logger = logging.getLogger(__name__)

# ─── Intenções críticas que sempre pedem confirmação ─────────────────────────

CRITICAL_INTENTS: set[str] = {
    # Comunicação
    "send_telegram",
    "send_whatsapp",
    "instagram_post",
    "instagram_story",
    "instagram_dm",
    # Arquivos
    "manage_files",
    # Sistema
    "pc_agent_task",
    # Tarefas (criação/deleção)
    "trello_action",
    "asana_action",
}

# Ações dentro de intenções que precisam de confirmação adicional
CRITICAL_ACTIONS: dict[str, set[str]] = {
    "manage_files":  {"delete", "remove", "format"},
    "trello_action": {"delete", "archive"},
    "asana_action":  {"delete", "complete"},
    "pc_agent_task": {"*"},   # * = sempre confirma para pc_agent
}

# ─── Mensagens de confirmação por intenção ────────────────────────────────────

_CONFIRM_TEMPLATES: dict[str, str] = {
    "send_telegram":  'Senhor, confirmo: vou enviar a mensagem "{msg}" via Telegram. Pode prosseguir?',
    "send_whatsapp":  'Senhor, confirmo: vou enviar "{msg}" para {phone} via WhatsApp. Pode prosseguir?',
    "instagram_post": "Senhor, vou publicar esta imagem no Instagram. Confirma?",
    "instagram_story":"Senhor, vou publicar nos Stories do Instagram. Confirma?",
    "instagram_dm":   "Senhor, vou enviar uma mensagem direta no Instagram. Confirma?",
    "manage_files":   'Senhor, vou executar "{op}" no arquivo "{path}". Esta ação pode ser irreversível. Confirma?',
    "pc_agent_task":  'Senhor, vou executar no PC: "{task}". Confirma?',
    "trello_action":  'Senhor, vou executar "{action}" no Trello. Confirma?',
    "asana_action":   'Senhor, vou executar "{action}" no Asana. Confirma?',
    "_default":       "Senhor, confirma esta ação? Responda com 'Sim, confirme' ou 'Pode prosseguir'.",
}

def _build_confirm_message(intent: str, params: dict) -> str:
    """Monta a mensagem de confirmação específica para a intenção."""
    template = _CONFIRM_TEMPLATES.get(intent, _CONFIRM_TEMPLATES["_default"])
    try:
        return template.format(
            msg=params.get("message", "")[:80],
            phone=params.get("phone", "destinatário"),
            op=params.get("operation", "operação"),
            path=params.get("file_path", "arquivo"),
            task=params.get("task", "tarefa")[:80],
            action=params.get("action", "ação"),
        )
    except Exception:
        return _CONFIRM_TEMPLATES["_default"]

# ─── Estado das confirmações pendentes ───────────────────────────────────────

_pending: dict[str, Event]  = {}
_results: dict[str, bool]   = {}
_messages: dict[str, str]   = {}   # confirm_id → mensagem de confirmação

# ─── Frases de confirmação / cancelamento ────────────────────────────────────

_CONFIRM_YES: list[str] = [
    "sim confirme", "pode prosseguir", "confirmo", "confirma",
    "pode fazer", "pode executar", "execute", "ok pode",
    "sim", "yes", "afirmativo", "claro pode", "pode",
    "confirmar", "prossiga", "vai em frente",
]

_CONFIRM_NO: list[str] = [
    "não", "cancela", "cancelar", "cancele", "abortar", "aborte",
    "para", "stop", "no", "negativo", "não faça", "desiste",
    "cancelado", "espera", "deixa",
]

def _parse_confirmation(text: str) -> bool | None:
    """Interpreta resposta como confirmação. Retorna True/False/None."""
    t = text.lower().strip()
    if any(p in t for p in _CONFIRM_YES):
        return True
    if any(p in t for p in _CONFIRM_NO):
        return False
    return None

# ─── API pública ──────────────────────────────────────────────────────────────

def needs_confirmation(intent: str, params: dict) -> bool:
    """
    Verifica se a intenção/parâmetros exigem confirmação.
    Substituição drop-in para o check inline do App.py.
    """
    if intent not in CRITICAL_INTENTS:
        return False

    # Verifica se a ação específica é crítica
    critical_actions = CRITICAL_ACTIONS.get(intent)
    if critical_actions is None:
        return True
    if "*" in critical_actions:
        return True

    # manage_files usa 'operation', outros usam 'action'
    action = (params.get("operation") or params.get("action") or "").lower()
    return action in critical_actions

def request_vocal_confirmation(
    intent: str,
    params: dict,
    sid: str,
    socketio_instance,
    timeout: float = 25.0,
) -> bool:
    """
    Solicita confirmação vocal ao usuário.

    1. Monta mensagem de confirmação personalizada
    2. Emite evento 'confirm_action' ao frontend
    3. Aguarda resposta (timeout configurável)
    4. Retorna True (confirmado) ou False (cancelado/timeout)

    Retorna False em caso de timeout ou erro.
    """
    confirm_id   = str(uuid.uuid4())
    confirm_msg  = _build_confirm_message(intent, params)
    ev           = Event()

    _pending[confirm_id]  = ev
    _results[confirm_id]  = False
    _messages[confirm_id] = confirm_msg

    # Emite ao frontend — mostra modal + fala a mensagem
    socketio_instance.emit("confirm_action", {
        "id":      confirm_id,
        "intent":  intent,
        "action":  confirm_msg,
        "detail":  _build_detail(intent, params),
        "timeout": int(timeout),
    }, room=sid)

    logger.info(f"[CONFIRM] Aguardando confirmação [{confirm_id[:8]}] para '{intent}'")

    # Aguarda resposta
    got_response = ev.wait(timeout=timeout)
    result = _results.pop(confirm_id, False)
    _pending.pop(confirm_id, None)
    _messages.pop(confirm_id, None)

    if not got_response:
        logger.warning(f"[CONFIRM] Timeout aguardando confirmação para '{intent}'")
        return False

    logger.info(f"[CONFIRM] Resultado para '{intent}': {'CONFIRMADO' if result else 'CANCELADO'}")
    return result

def resolve_confirmation(confirm_id: str, confirmed: bool) -> None:
    """
    Resolve uma confirmação pendente.
    Chamado pelo evento SocketIO 'confirm_response' (botão da UI)
    ou por process_vocal_confirmation() (resposta por voz/texto).
    """
    ev = _pending.get(confirm_id)
    if not ev:
        logger.warning(f"[CONFIRM] ID desconhecido: {confirm_id}")
        return
    _results[confirm_id] = confirmed
    ev.set()
    logger.debug(f"[CONFIRM] Resolvido [{confirm_id[:8]}]: {confirmed}")

def process_vocal_confirmation(text: str, sid: str) -> bool:
    """
    Tenta interpretar texto como resposta de confirmação para o sid.
    Retorna True se encontrou e resolveu uma confirmação pendente.

    Chamado no pipeline de mensagens do App.py ANTES do processamento normal.
    """
    decision = _parse_confirmation(text)
    if decision is None:
        return False   # Não parece ser uma confirmação

    # Procura confirmação pendente para este sid
    # (não temos acesso direto ao sid por confirm_id — buscamos pelo event set mais recente)
    # Solução: App.py deve manter mapa sid → confirm_id
    # Esta função é um helper — a resolução real usa resolve_confirmation()
    return False

def get_pending_count() -> int:
    """Retorna quantidade de confirmações pendentes (para monitoramento)."""
    return len(_pending)

# ─── Helpers de detalhe ───────────────────────────────────────────────────────

def _build_detail(intent: str, params: dict) -> str:
    """Gera texto de detalhe para o modal de confirmação."""
    details: dict[str, str] = {
        "send_telegram":  f"Mensagem: \"{params.get('message', '')[:60]}\"",
        "send_whatsapp":  f"Para: {params.get('phone','?')} | \"{params.get('message','')[:50]}\"",
        "manage_files":   f"Operação: {params.get('operation','?')} | Caminho: {params.get('file_path','?')}",
        "pc_agent_task":  f"Tarefa: {params.get('task','?')[:80]}",
        "instagram_post": f"Publicação no feed do Instagram",
        "trello_action":  f"Ação: {params.get('action','?')} | Card: {params.get('title','?')}",
        "asana_action":   f"Ação: {params.get('action','?')} | Tarefa: {params.get('title','?')}",
    }
    return details.get(intent, f"Intenção: {intent}")


# ─── Compatibilidade com App.py legado ───────────────────────────────────────
# Mantém a assinatura antiga funcionando sem alterações no App.py

def request_confirmation(intent: str, params: dict, sid: str,
                          socketio_instance=None) -> bool:
    """
    Alias de compatibilidade com o sistema antigo do App.py.
    Se socketio_instance for None, funciona no modo legado (Event direto).
    """
    if socketio_instance is not None:
        return request_vocal_confirmation(intent, params, sid, socketio_instance)

    # Modo legado — replica comportamento original
    return request_vocal_confirmation(intent, params, sid,
                                       socketio_instance or _noop_socketio())

class _noop_socketio:
    """Socketio noop para evitar crash em modo legado."""
    def emit(self, *a, **kw): pass


# ─── Teste local ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== Confirmation System — Teste ===\n")

    # Teste de detecção de necessidade de confirmação
    testes = [
        ("send_telegram", {"message": "Olá!"}, True),
        ("send_whatsapp", {"phone": "+55...", "message": "oi"}, True),
        ("manage_files",  {"operation": "delete", "file_path": "/tmp/x"}, True),
        ("manage_files",  {"operation": "list",   "file_path": "/tmp"}, False),
        ("open_app",      {"app_name": "chrome"}, False),
        ("pc_agent_task", {"task": "clica no botão"}, True),
        ("spotify_control", {"action": "play"}, False),
    ]

    for intent, params, esperado in testes:
        r = needs_confirmation(intent, params)
        status = "OK" if r == esperado else "FALHOU"
        print(f"  [{status}] {intent} → precisa confirmação: {r}")

    print("\nMensagens de confirmação:")
    for intent, params, _ in testes[:4]:
        msg = _build_confirm_message(intent, params)
        print(f"  {intent}:")
        print(f"    '{msg}'")

    print("\nDetecção de confirmação vocal:")
    frases = [
        ("sim pode fazer", True),
        ("pode prosseguir", True),
        ("não cancela", False),
        ("abortar ação", False),
        ("qual o tempo hoje", None),
        ("claro pode", True),
    ]
    for f, esperado in frases:
        r = _parse_confirmation(f)
        status = "OK" if r == esperado else "FALHOU"
        print(f"  [{status}] '{f}' → {r}")