"""
J.A.R.V.I.S. v2.3 — Briefing Diário
======================================
Gera o briefing matinal/contextual do JARVIS, consolidando:
  - Saudação contextual (bom dia / boa tarde / boa noite)
  - Data e hora atual
  - Clima da cidade do usuário (via information.py)
  - Tarefas pendentes (Trello / Asana se configurados)
  - Memórias importantes recentes
  - Insight da semana (gerado via IA)
  - Lembretes do dia (scheduler)

Ativado por:
  - Conexão inicial do usuário (emit 'greeting_request')
  - Comando de voz: "bom dia", "status", "resumo do dia", etc.
  - Chamada direta via API

Uso em App.py:
    from briefing import generate_briefing, is_briefing_request
    if is_briefing_request(text):
        result = generate_briefing(deps)
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ─── Utilitários de tempo ─────────────────────────────────────────────────────

def _get_period() -> tuple[str, str]:
    """Retorna (saudação, período) baseado na hora atual."""
    h = datetime.datetime.now().hour
    if 5 <= h < 12:
        return "Bom dia", "manhã"
    elif 12 <= h < 18:
        return "Boa tarde", "tarde"
    else:
        return "Boa noite", "noite"

def _get_weekday_pt() -> str:
    """Retorna o dia da semana em português."""
    dias = [
        "segunda-feira", "terça-feira", "quarta-feira",
        "quinta-feira", "sexta-feira", "sábado", "domingo",
    ]
    return dias[datetime.datetime.now().weekday()]

def _format_date_pt() -> str:
    """Retorna a data formatada em português."""
    meses = [
        "", "janeiro", "fevereiro", "março", "abril", "maio", "junho",
        "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
    ]
    now = datetime.datetime.now()
    return f"{_get_weekday_pt().capitalize()}, {now.day} de {meses[now.month]} de {now.year}"

# ─── Verificação de solicitação de briefing ───────────────────────────────────

_BRIEFING_TRIGGERS: list[str] = [
    "bom dia", "boa tarde", "boa noite",
    "iniciar o dia", "começar o dia",
    "status", "resumo", "resumo do dia",
    "o que tenho hoje", "agenda do dia",
    "atualização", "me atualiza",
    "o que está acontecendo", "what's up",
    "jarvis status", "relatório", "como estão as coisas",
]

def is_briefing_request(text: str) -> bool:
    """Verifica se o texto é um pedido de briefing."""
    t = text.lower().strip()
    return any(trigger in t for trigger in _BRIEFING_TRIGGERS)

# ─── Coleta de dados do briefing ─────────────────────────────────────────────

def _get_user_name(deps: dict) -> str:
    """Obtém o nome do usuário do perfil."""
    try:
        from memory import get_profile_field
        return get_profile_field("user_name", "")
    except Exception:
        return ""

def _get_weather_snippet(deps: dict) -> str:
    """Tenta obter clima resumido. Retorna string vazia se falhar."""
    try:
        from memory import get_profile_field
        city = get_profile_field("city", "") or get_profile_field("cidade", "")
        if not city:
            return ""

        news_api = deps.get("NEWS_API_KEY", "")
        weather_fn = deps.get("execute_get_weather")
        if weather_fn:
            result = weather_fn({"city": city}, "__briefing__")
            if result and len(result) < 200:
                return result
    except Exception as e:
        logger.debug(f"[BRIEFING] Clima indisponível: {e}")
    return ""

def _get_pending_tasks(deps: dict) -> list[str]:
    """Coleta tarefas pendentes do Trello/Asana. Retorna lista de strings."""
    tasks: list[str] = []
    try:
        execute_trello = deps.get("execute_trello_action")
        if execute_trello and deps.get("TRELLO_API_KEY"):
            result = execute_trello({"action": "list"}, "__briefing__")
            if result and isinstance(result, str) and len(result) > 10:
                # Pega apenas as primeiras 3 tarefas
                linhas = [l.strip() for l in result.split("\n") if l.strip()][:3]
                tasks.extend(linhas)
    except Exception as e:
        logger.debug(f"[BRIEFING] Trello indisponível: {e}")

    try:
        execute_asana = deps.get("execute_asana_action")
        if execute_asana and deps.get("ASANA_TOKEN") and not tasks:
            result = execute_asana({"action": "list"}, "__briefing__")
            if result and isinstance(result, str) and len(result) > 10:
                linhas = [l.strip() for l in result.split("\n") if l.strip()][:3]
                tasks.extend(linhas)
    except Exception as e:
        logger.debug(f"[BRIEFING] Asana indisponível: {e}")

    return tasks[:5]  # Máximo 5 tarefas no briefing

def _get_scheduled_reminders(deps: dict) -> list[str]:
    """Obtém lembretes agendados para hoje."""
    reminders: list[str] = []
    try:
        get_all_tasks = deps.get("get_all_tasks")
        if get_all_tasks:
            tasks = get_all_tasks()
            hoje = datetime.date.today().isoformat()
            for t in tasks:
                if t.get("active") and hoje in str(t.get("next_run", "")):
                    reminders.append(t.get("message", "Lembrete agendado"))
    except Exception as e:
        logger.debug(f"[BRIEFING] Scheduler indisponível: {e}")
    return reminders[:3]

def _get_memory_insights(deps: dict) -> list[str]:
    """Obtém memórias importantes recentes (importância ≥ 2)."""
    insights: list[str] = []
    try:
        from memory import get_memories
        mems = get_memories(limit=20)
        importantes = [
            m["content"] for m in mems
            if m.get("importance", 1) >= 2
        ][:3]
        insights.extend(importantes)
    except Exception as e:
        logger.debug(f"[BRIEFING] Memórias indisponíveis: {e}")
    return insights

# ─── Geração do briefing via IA ───────────────────────────────────────────────

_BRIEFING_AI_PROMPT = """Você é J.A.R.V.I.S. gerando o briefing do dia para o Senhor.

Com os dados abaixo, gere um briefing falado em 4 a 6 frases naturais, sem markdown, sem listas, em português brasileiro elegante. Comece diretamente com a saudação. Seja útil, conciso e levemente bem-humorado quando adequado.

DADOS:
{data_block}

REGRAS:
- Se não houver clima, não mencione clima.
- Se não houver tarefas, diga apenas que a agenda está livre.
- Termine com uma oferta de ajuda ou insight motivador.
- NUNCA use markdown, bullet points, asteriscos ou emojis.
- Escreva como se estivesse sendo lido em voz alta.
"""

def _generate_ai_briefing(data_block: str, deps: dict) -> str:
    """Usa IA para gerar o texto final do briefing."""
    prompt = _BRIEFING_AI_PROMPT.format(data_block=data_block)

    try:
        # Tenta Groq primeiro (mais rápido para briefing)
        groq_client = deps.get("groq_client")
        if groq_client and deps.get("GROQ_AVAILABLE"):
            resp = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=250,
                temperature=0.7,
            )
            return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.debug(f"[BRIEFING] Groq falhou: {e}")

    try:
        # Fallback: Gemini
        gemini_client = deps.get("gemini_client")
        gemini_models = deps.get("GEMINI_MODELS", ["gemini-2.0-flash"])
        if gemini_client and deps.get("GEMINI_AVAILABLE"):
            for model in gemini_models:
                try:
                    resp = gemini_client.models.generate_content(
                        model=model, contents=prompt,
                        config={"max_output_tokens": 250, "temperature": 0.7}
                    )
                    return resp.text.strip()
                except Exception:
                    continue
    except Exception as e:
        logger.debug(f"[BRIEFING] Gemini falhou: {e}")

    try:
        # Fallback: Ollama
        import requests as req
        ollama_url   = deps.get("OLLAMA_BASE_URL", "http://localhost:11434")
        ollama_model = deps.get("OLLAMA_MODEL", "llama3")
        if deps.get("OLLAMA_AVAILABLE"):
            resp = req.post(
                f"{ollama_url}/api/chat",
                json={
                    "model":   ollama_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream":  False,
                    "options": {"temperature": 0.7, "num_predict": 250},
                },
                timeout=20,
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"].strip()
    except Exception as e:
        logger.debug(f"[BRIEFING] Ollama falhou: {e}")

    return None  # Todos os motores falharam — usa fallback simples

# ─── Geração do briefing final ────────────────────────────────────────────────

def generate_briefing(deps: dict) -> str:
    """
    Gera o texto completo do briefing diário.

    deps — dicionário de dependências injetado pelo App.py:
        groq_client, GROQ_AVAILABLE, gemini_client, GEMINI_AVAILABLE,
        OLLAMA_AVAILABLE, OLLAMA_BASE_URL, OLLAMA_MODEL, GEMINI_MODELS,
        execute_get_weather, execute_trello_action, execute_asana_action,
        get_all_tasks, TRELLO_API_KEY, ASANA_TOKEN, NEWS_API_KEY

    Retorna string pronta para TTS.
    """
    saudacao, periodo = _get_period()
    data_str     = _format_date_pt()
    hora_str     = datetime.datetime.now().strftime("%H:%M")
    user_name    = _get_user_name(deps)

    # Coleta de dados (tolerante a falhas)
    clima        = _get_weather_snippet(deps)
    tarefas      = _get_pending_tasks(deps)
    lembretes    = _get_scheduled_reminders(deps)
    insights     = _get_memory_insights(deps)

    # Monta bloco de dados para a IA
    linhas: list[str] = [
        f"Saudação: {saudacao}, Senhor{' ' + user_name if user_name else ''}",
        f"Data: {data_str}",
        f"Hora: {hora_str}",
    ]
    if clima:
        linhas.append(f"Clima: {clima}")
    if tarefas:
        linhas.append("Tarefas pendentes:")
        for i, t in enumerate(tarefas, 1):
            linhas.append(f"  {i}. {t}")
    else:
        linhas.append("Tarefas: Agenda livre hoje.")
    if lembretes:
        linhas.append("Lembretes de hoje:")
        for r in lembretes:
            linhas.append(f"  - {r}")
    if insights:
        linhas.append("Memórias relevantes:")
        for m in insights:
            linhas.append(f"  - {m}")

    data_block = "\n".join(linhas)

    # Tenta gerar via IA
    ai_text = _generate_ai_briefing(data_block, deps)
    if ai_text:
        logger.info(f"[BRIEFING] Gerado via IA ({len(ai_text)} chars)")
        return ai_text

    # Fallback simples (sem IA)
    logger.warning("[BRIEFING] Usando fallback simples (sem IA)")
    nome_parte = f", {user_name}" if user_name else ""
    briefing_lines: list[str] = [
        f"{saudacao}{nome_parte}, Senhor. Hoje é {data_str}, são {hora_str}.",
    ]
    if clima:
        briefing_lines.append(clima)
    if tarefas:
        count = len(tarefas)
        briefing_lines.append(
            f"Você tem {count} {'tarefa pendente' if count == 1 else 'tarefas pendentes'} hoje."
        )
    else:
        briefing_lines.append("Sua agenda está livre hoje.")
    if insights:
        briefing_lines.append(f"Lembro que {insights[0].lower()}.")
    briefing_lines.append("Como posso ser útil nesta " + periodo + ", Senhor?")

    return " ".join(briefing_lines)


# ─── Teste local ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    print("=== Briefing Engine — Teste ===\n")

    # Teste com deps mínimas (sem IA)
    deps_mock: dict = {
        "GROQ_AVAILABLE":   False,
        "GEMINI_AVAILABLE": False,
        "OLLAMA_AVAILABLE": False,
    }

    resultado = generate_briefing(deps_mock)
    print("Briefing (fallback):")
    print(f"  {resultado}\n")

    # Teste de trigger detection
    testes = [
        ("bom dia Jarvis", True),
        ("qual a temperatura de São Paulo", False),
        ("status do sistema", True),
        ("me dá um resumo do dia", True),
        ("abre o Spotify", False),
    ]
    print("Detecção de trigger:")
    for texto, esperado in testes:
        r = is_briefing_request(texto)
        status = "OK" if r == esperado else "FALHOU"
        print(f"  [{status}] '{texto}' → {r}")
        