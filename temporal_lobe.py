"""
J.A.R.V.I.S. — TEMPORAL LOBE
Versão 3.0 — Módulo de Memória Temporal

Funcionalidades:
  1. Memory Timeline      — memórias indexadas por data, JARVIS sabe "o que aconteceu semana passada"
  2. Lembrete Proativo    — detecta compromissos na fala e avisa no momento certo
  3. Episodic Memory      — guarda episódios completos com contexto emocional
  4. Geo-Temporal Context — adapta respostas ao fuso, dia da semana, feriados, período do dia
  5. Temporal Decay       — memórias antigas perdem peso automaticamente
"""

import re
import json
import sqlite3
import datetime
import os
from pathlib import Path
from threading import Lock, Thread

# ─── BANCO ────────────────────────────────────────────────────────────────────

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'jarvis.db')
_lock   = Lock()

def _conn():
    return sqlite3.connect(DB_PATH)

def init_temporal_tables():
    """Cria as tabelas extras do Temporal Lobe (idempotente)."""
    with _lock:
        conn = _conn()
        c = conn.cursor()

        # Reminders — compromissos detectados automaticamente
        c.execute('''
            CREATE TABLE IF NOT EXISTS reminders (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                content     TEXT    NOT NULL,
                remind_at   TEXT    NOT NULL,
                created_at  TEXT    NOT NULL,
                fired       INTEGER DEFAULT 0,
                source_text TEXT
            )
        ''')

        # Episodic memory — episódios completos com contexto
        c.execute('''
            CREATE TABLE IF NOT EXISTS episodes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                summary     TEXT    NOT NULL,
                mood        TEXT    DEFAULT 'neutral',
                intent      TEXT,
                created_at  TEXT    NOT NULL,
                date_label  TEXT    NOT NULL
            )
        ''')

        # Adiciona coluna created_at na tabela memories se não existir
        try:
            c.execute('ALTER TABLE memories ADD COLUMN created_at_ts REAL DEFAULT 0')
        except Exception:
            pass  # já existe

        conn.commit()
        conn.close()
    print('[TEMPORAL LOBE] Tabelas inicializadas')


# ═══════════════════════════════════════════════════════════════════════════════
#  1. MEMORY TIMELINE
# ═══════════════════════════════════════════════════════════════════════════════

def get_memories_by_period(period: str) -> list[dict]:
    """
    Retorna memórias e log de um período específico.
    period: 'hoje' | 'ontem' | 'semana' | 'mes' | 'YYYY-MM-DD'
    """
    now   = datetime.datetime.now()
    today = now.date()

    if period == 'hoje':
        since = datetime.datetime.combine(today, datetime.time.min)
        label = 'hoje'
    elif period == 'ontem':
        since = datetime.datetime.combine(today - datetime.timedelta(days=1), datetime.time.min)
        until = datetime.datetime.combine(today, datetime.time.min)
        label = 'ontem'
    elif period == 'semana':
        since = datetime.datetime.combine(today - datetime.timedelta(days=7), datetime.time.min)
        label = 'nos últimos 7 dias'
    elif period == 'mes':
        since = datetime.datetime.combine(today - datetime.timedelta(days=30), datetime.time.min)
        label = 'nos últimos 30 dias'
    else:
        # Tenta interpretar como data YYYY-MM-DD
        try:
            d = datetime.date.fromisoformat(period)
            since = datetime.datetime.combine(d, datetime.time.min)
            until = datetime.datetime.combine(d + datetime.timedelta(days=1), datetime.time.min)
            label = period
        except ValueError:
            return []

    since_str = since.isoformat()
    until_str = until.isoformat() if period == 'ontem' else now.isoformat()

    with _lock:
        conn = _conn()
        c = conn.cursor()

        # Busca no conversation_log
        c.execute('''
            SELECT role, content, intent, timestamp
            FROM conversation_log
            WHERE timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp ASC
            LIMIT 50
        ''', (since_str, until_str))
        log_rows = c.fetchall()

        # Busca memórias criadas no período
        c.execute('''
            SELECT category, content, importance, created_at
            FROM memories
            WHERE created_at >= ? AND created_at <= ?
            ORDER BY importance DESC
            LIMIT 20
        ''', (since_str, until_str))
        mem_rows = c.fetchall()

        # Busca episódios do período
        c.execute('''
            SELECT summary, mood, created_at
            FROM episodes
            WHERE created_at >= ? AND created_at <= ?
            ORDER BY created_at DESC
            LIMIT 10
        ''', (since_str, until_str))
        ep_rows = c.fetchall()

        conn.close()

    return {
        'period_label': label,
        'log': [{'role': r[0], 'content': r[1], 'intent': r[2], 'timestamp': r[3]}
                for r in log_rows],
        'memories': [{'category': r[0], 'content': r[1], 'importance': r[2], 'created_at': r[3]}
                     for r in mem_rows],
        'episodes': [{'summary': r[0], 'mood': r[1], 'created_at': r[2]}
                     for r in ep_rows],
    }

def get_timeline_summary(period: str, ai_fn) -> str:
    """
    Gera um resumo em linguagem natural do que aconteceu em um período.
    ai_fn: callable(prompt) -> str
    """
    data = get_memories_by_period(period)
    if not data:
        return f"Não encontrei registros para o período '{period}', Sir."

    log   = data.get('log', [])
    mems  = data.get('memories', [])
    eps   = data.get('episodes', [])
    label = data.get('period_label', period)

    if not log and not mems and not eps:
        return f"Não há registros de atividade para {label}, Sir."

    # Monta contexto para a IA
    parts = []
    if log:
        convo = "\n".join(f"{e['role'].upper()}: {e['content'][:100]}" for e in log[:20])
        parts.append(f"Conversas:\n{convo}")
    if mems:
        m_txt = "\n".join(f"- [{m['category']}] {m['content']}" for m in mems)
        parts.append(f"Memórias aprendidas:\n{m_txt}")
    if eps:
        e_txt = "\n".join(f"- {e['summary']}" for e in eps)
        parts.append(f"Episódios:\n{e_txt}")

    context = "\n\n".join(parts)

    prompt = f"""Você é J.A.R.V.I.S. Resuma o que aconteceu {label} com base nos dados abaixo.
Seja conciso, 2 a 4 frases, tom formal de mordomo britânico.
Comece com "Relatório de {label}, Sir."

{context}"""

    try:
        return ai_fn(prompt).strip()
    except Exception:
        return f"Encontrei {len(log)} interações e {len(mems)} memórias para {label}, Sir."

def detect_timeline_query(text: str) -> str | None:
    """
    Detecta se o Sir está perguntando sobre um período passado.
    Retorna o período ('hoje', 'ontem', 'semana', 'mes') ou None.
    """
    t = text.lower()
    if any(w in t for w in ['hoje', 'today']):
        return 'hoje'
    if any(w in t for w in ['ontem', 'yesterday']):
        return 'ontem'
    if any(w in t for w in ['semana passada', 'última semana', 'últimos 7 dias', 'essa semana']):
        return 'semana'
    if any(w in t for w in ['mês passado', 'último mês', 'últimos 30 dias', 'esse mês']):
        return 'mes'
    return None

def is_timeline_query(text: str) -> bool:
    """True se o texto parece ser uma pergunta sobre o passado temporal."""
    t = text.lower()
    temporal_words = ['ontem', 'semana passada', 'mês passado', 'última semana',
                      'último mês', 'o que fiz', 'o que aconteceu', 'me lembra',
                      'o que conversamos', 'o que você aprendeu']
    return any(w in t for w in temporal_words)


# ═══════════════════════════════════════════════════════════════════════════════
#  2. LEMBRETE PROATIVO
# ═══════════════════════════════════════════════════════════════════════════════

# Padrões para detectar compromissos no texto
_REMINDER_PATTERNS = [
    # "reunião amanhã às 15h"
    (r'\b(reunião|meeting|consulta|dentista|médico|apresentação|entrega|prazo|deadline)\b.{0,40}\b(amanhã|hoje|segunda|terça|quarta|quinta|sexta|sábado|domingo)\b.{0,20}\b(\d{1,2})[h:]?(\d{0,2})\b',
     'evento_hora'),
    # "lembra de ligar às 14h"
    (r'\b(lembra|lembre|não esqueç|me avisa|me lembra)\b.{0,60}\b(\d{1,2})[h:](\d{0,2})',
     'lembrete_hora'),
    # "tenho que enviar o relatório amanhã"
    (r'\b(tenho que|preciso|devo|não posso esquecer de)\b.{0,60}\b(amanhã|hoje|segunda|terça|quarta|quinta|sexta)',
     'tarefa_dia'),
]

_WEEKDAY_MAP = {
    'segunda': 0, 'terça': 1, 'quarta': 2, 'quinta': 3,
    'sexta': 4, 'sábado': 5, 'domingo': 6,
}

def _parse_reminder_time(text: str) -> datetime.datetime | None:
    """Tenta extrair data/hora de um texto."""
    now  = datetime.datetime.now()
    text = text.lower()

    # Hora explícita
    hour_match = re.search(r'\b(\d{1,2})[h:](\d{0,2})', text)
    hour = int(hour_match.group(1)) if hour_match else None
    minute = int(hour_match.group(2)) if hour_match and hour_match.group(2) else 0

    # Dia
    target_date = now.date()
    if 'amanhã' in text:
        target_date = now.date() + datetime.timedelta(days=1)
    elif 'hoje' in text:
        target_date = now.date()
    else:
        for day_name, weekday in _WEEKDAY_MAP.items():
            if day_name in text:
                days_ahead = (weekday - now.weekday()) % 7
                if days_ahead == 0:
                    days_ahead = 7
                target_date = now.date() + datetime.timedelta(days=days_ahead)
                break

    if hour is not None:
        return datetime.datetime.combine(target_date, datetime.time(hour, minute))

    # Sem hora → lembra no início do dia
    return datetime.datetime.combine(target_date, datetime.time(8, 0))

def detect_and_save_reminder(text: str, source_text: str = '') -> dict | None:
    """
    Detecta compromisso no texto e salva como lembrete.
    Retorna o lembrete criado ou None.
    """
    for pattern, kind in _REMINDER_PATTERNS:
        m = re.search(pattern, text.lower())
        if m:
            remind_at = _parse_reminder_time(text)
            if not remind_at:
                continue

            # Evita criar lembrete para hora já passada
            if remind_at < datetime.datetime.now():
                remind_at += datetime.timedelta(days=1)

            now_str = datetime.datetime.now().isoformat()
            with _lock:
                conn = _conn()
                c = conn.cursor()
                c.execute('''
                    INSERT INTO reminders (content, remind_at, created_at, source_text)
                    VALUES (?, ?, ?, ?)
                ''', (text[:200], remind_at.isoformat(), now_str, source_text[:500]))
                rid = c.lastrowid
                conn.commit()
                conn.close()

            print(f'[TEMPORAL] Lembrete #{rid} criado: {remind_at.strftime("%d/%m %H:%M")} — {text[:60]}')
            return {
                'id':         rid,
                'content':    text[:200],
                'remind_at':  remind_at.isoformat(),
                'remind_fmt': remind_at.strftime('%d/%m às %H:%M'),
            }
    return None

def get_pending_reminders() -> list[dict]:
    """Retorna lembretes que devem disparar agora (±2min)."""
    now     = datetime.datetime.now()
    window  = datetime.timedelta(minutes=2)
    since   = (now - window).isoformat()
    until   = (now + window).isoformat()

    with _lock:
        conn = _conn()
        c = conn.cursor()
        c.execute('''
            SELECT id, content, remind_at
            FROM reminders
            WHERE fired = 0 AND remind_at >= ? AND remind_at <= ?
            ORDER BY remind_at ASC
        ''', (since, until))
        rows = c.fetchall()
        conn.close()

    return [{'id': r[0], 'content': r[1], 'remind_at': r[2]} for r in rows]

def mark_reminder_fired(reminder_id: int) -> None:
    with _lock:
        conn = _conn()
        c = conn.cursor()
        c.execute('UPDATE reminders SET fired = 1 WHERE id = ?', (reminder_id,))
        conn.commit()
        conn.close()

def get_all_reminders() -> list[dict]:
    """Lista todos os lembretes pendentes (para o frontend)."""
    now_str = datetime.datetime.now().isoformat()
    with _lock:
        conn = _conn()
        c = conn.cursor()
        c.execute('''
            SELECT id, content, remind_at, fired, created_at
            FROM reminders
            WHERE fired = 0 AND remind_at >= ?
            ORDER BY remind_at ASC
            LIMIT 20
        ''', (now_str,))
        rows = c.fetchall()
        conn.close()
    return [
        {'id': r[0], 'content': r[1], 'remind_at': r[2],
         'fired': bool(r[3]), 'created_at': r[4]}
        for r in rows
    ]

def add_reminder(content: str, remind_at: str) -> dict:
    """Cria um lembrete manual a partir de conteúdo e data/hora ISO."""
    if not content or not remind_at:
        raise ValueError('content e remind_at são obrigatórios')

    try:
        parsed_at = datetime.datetime.fromisoformat(remind_at)
    except ValueError as exc:
        raise ValueError('remind_at deve estar em formato ISO') from exc

    now_str = datetime.datetime.now().isoformat()
    with _lock:
        conn = _conn()
        c = conn.cursor()
        c.execute('''
            INSERT INTO reminders (content, remind_at, created_at, source_text)
            VALUES (?, ?, ?, ?)
        ''', (content[:200], parsed_at.isoformat(), now_str, 'manual'))
        rid = c.lastrowid
        conn.commit()
        conn.close()

    return {
        'id': rid,
        'content': content[:200],
        'remind_at': parsed_at.isoformat(),
        'created_at': now_str,
        'fired': False,
    }

def delete_reminder(reminder_id: int) -> None:
    with _lock:
        conn = _conn()
        c = conn.cursor()
        c.execute('DELETE FROM reminders WHERE id = ?', (reminder_id,))
        conn.commit()
        conn.close()

def start_reminder_watcher(tts_fn, emit_fn) -> None:
    """
    Inicia thread que verifica lembretes a cada 60s e dispara TTS + socket.
    """
    def _watch():
        while True:
            try:
                due = get_pending_reminders()
                for r in due:
                    mark_reminder_fired(r['id'])
                    msg = f"Lembrete, Sir: {r['content'][:120]}"
                    audio = tts_fn(msg)
                    emit_fn('jarvis_reminder', {
                        'text':      msg,
                        'audio_b64': audio,
                        'reminder':  r,
                    })
                    print(f'[TEMPORAL] Lembrete disparado: {r["content"][:60]}')
            except Exception as e:
                print(f'[TEMPORAL] Erro no watcher: {e}')
            import time as _time
            _time.sleep(60)

    Thread(target=_watch, daemon=True).start()
    print('[TEMPORAL] Reminder watcher iniciado')


# ═══════════════════════════════════════════════════════════════════════════════
#  3. EPISODIC MEMORY
# ═══════════════════════════════════════════════════════════════════════════════

_MOOD_KEYWORDS = {
    'positivo':  ['ótimo', 'excelente', 'perfeito', 'feliz', 'animado', 'consegui',
                  'funcionou', 'aprovado', 'concluído', 'sucesso', 'ótima', 'adorei'],
    'negativo':  ['erro', 'problema', 'travou', 'bug', 'falhou', 'frustrado',
                  'difícil', 'ruim', 'pior', 'quebrou', 'não funciona', 'deu errado'],
    'neutro':    [],
}

def _detect_mood(text: str) -> str:
    t = text.lower()
    for mood, words in _MOOD_KEYWORDS.items():
        if any(w in t for w in words):
            return mood
    return 'neutro'

def save_episode(user_text: str, jarvis_text: str, intent: str = '') -> None:
    """
    Salva um episódio de conversa com contexto emocional.
    Chamado no final de cada interação relevante.
    """
    # Só salva episódios com conteúdo substancial
    if len(user_text) < 20:
        return
    # Ignora interações puramente de sistema
    if intent in ('slot_request', 'set_personality', 'protocol_work_time'):
        return

    now      = datetime.datetime.now()
    mood     = _detect_mood(user_text + ' ' + jarvis_text)
    # Resumo curto do episódio
    summary  = f"Sir: {user_text[:80].strip()}"
    if jarvis_text:
        summary += f" → JARVIS: {jarvis_text[:80].strip()}"

    date_label = now.strftime('%d/%m/%Y')

    with _lock:
        conn = _conn()
        c = conn.cursor()
        c.execute('''
            INSERT INTO episodes (summary, mood, intent, created_at, date_label)
            VALUES (?, ?, ?, ?, ?)
        ''', (summary, mood, intent or 'conversation', now.isoformat(), date_label))

        # Mantém apenas os últimos 200 episódios
        c.execute('''
            DELETE FROM episodes WHERE id NOT IN (
                SELECT id FROM episodes ORDER BY id DESC LIMIT 200
            )
        ''')
        conn.commit()
        conn.close()

def get_recent_episodes(limit: int = 10, mood: str = None) -> list[dict]:
    with _lock:
        conn = _conn()
        c = conn.cursor()
        if mood:
            c.execute('''
                SELECT id, summary, mood, intent, created_at, date_label
                FROM episodes WHERE mood = ?
                ORDER BY id DESC LIMIT ?
            ''', (mood, limit))
        else:
            c.execute('''
                SELECT id, summary, mood, intent, created_at, date_label
                FROM episodes
                ORDER BY id DESC LIMIT ?
            ''', (limit,))
        rows = c.fetchall()
        conn.close()
    return [
        {'id': r[0], 'summary': r[1], 'mood': r[2],
         'intent': r[3], 'created_at': r[4], 'date_label': r[5]}
        for r in rows
    ]

def get_episode_context(limit: int = 5) -> str:
    """
    Retorna um bloco de contexto episódico para o system prompt.
    Inclui os episódios mais recentes relevantes.
    """
    episodes = get_recent_episodes(limit=limit)
    if not episodes:
        return ''

    lines = [f"- [{e['date_label']} | {e['mood']}] {e['summary']}"
             for e in episodes]
    return '\n\n## EPISÓDIOS RECENTES\n' + '\n'.join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
#  4. GEO-TEMPORAL CONTEXT
# ═══════════════════════════════════════════════════════════════════════════════

_FERIADOS_BR = {
    '01-01': 'Ano Novo',
    '04-21': 'Tiradentes',
    '05-01': 'Dia do Trabalho',
    '09-07': 'Independência do Brasil',
    '10-12': 'Nossa Senhora Aparecida',
    '11-02': 'Finados',
    '11-15': 'Proclamação da República',
    '12-25': 'Natal',
}

def get_geo_temporal_context(timezone_offset: int = -3) -> dict:
    """
    Retorna contexto temporal completo: hora, dia, período, feriado, etc.
    timezone_offset: offset UTC em horas (padrão -3 = BRT)
    """
    utc_now  = datetime.datetime.utcnow()
    local_now = utc_now + datetime.timedelta(hours=timezone_offset)

    hour     = local_now.hour
    weekday  = local_now.weekday()   # 0=seg, 6=dom
    month_day = local_now.strftime('%m-%d')

    # Período do dia
    if 5 <= hour < 12:
        period = 'manhã'
        greeting = 'Bom dia'
    elif 12 <= hour < 18:
        period = 'tarde'
        greeting = 'Boa tarde'
    elif 18 <= hour < 22:
        period = 'noite'
        greeting = 'Boa noite'
    else:
        period = 'madrugada'
        greeting = 'Boa madrugada'

    weekday_names = ['segunda-feira', 'terça-feira', 'quarta-feira',
                     'quinta-feira', 'sexta-feira', 'sábado', 'domingo']
    day_name = weekday_names[weekday]

    is_weekend  = weekday >= 5
    feriado     = _FERIADOS_BR.get(month_day)
    is_holiday  = feriado is not None

    # Sugestão contextual
    suggestions = []
    if is_weekend:
        suggestions.append('É fim de semana — o Sir pode preferir um ritmo mais relaxado.')
    if is_holiday:
        suggestions.append(f'Hoje é feriado: {feriado}.')
    if hour >= 22 or hour < 6:
        suggestions.append('É madrugada — respostas mais breves são recomendadas.')
    if 8 <= hour <= 10 and not is_weekend:
        suggestions.append('Horário de início de trabalho — o Sir pode querer um briefing do dia.')

    return {
        'local_time':   local_now.strftime('%H:%M'),
        'date':         local_now.strftime('%d/%m/%Y'),
        'weekday':      day_name,
        'period':       period,
        'greeting':     greeting,
        'is_weekend':   is_weekend,
        'is_holiday':   is_holiday,
        'holiday_name': feriado,
        'hour':         hour,
        'suggestions':  suggestions,
        'tz_offset':    timezone_offset,
    }

def get_geo_temporal_prompt_block(tz_offset: int = -3) -> str:
    """Gera bloco de contexto geo-temporal para o system prompt."""
    ctx = get_geo_temporal_context(tz_offset)
    lines = [
        f'- Hora local: {ctx["local_time"]} ({ctx["date"]}, {ctx["weekday"]})',
        f'- Período: {ctx["period"]}',
    ]
    if ctx['is_holiday']:
        lines.append(f'- Hoje é feriado: {ctx["holiday_name"]}')
    if ctx['is_weekend']:
        lines.append('- É fim de semana')
    for s in ctx['suggestions']:
        lines.append(f'- Nota: {s}')

    return '\n\n## CONTEXTO TEMPORAL\n' + '\n'.join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
#  5. TEMPORAL DECAY — memórias antigas perdem peso
# ═══════════════════════════════════════════════════════════════════════════════

# Meia-vida em dias por importância
_HALF_LIFE_DAYS = {
    1: 7,    # importância 1 → meia-vida 7 dias
    2: 30,   # importância 2 → meia-vida 30 dias
    3: 180,  # importância 3 → meia-vida 180 dias
}

def _decay_weight(importance: int, created_at_str: str) -> float:
    """
    Calcula peso [0.0 – 1.0] de uma memória baseado na idade e importância.
    Usa decaimento exponencial: w = e^(-λt) onde λ = ln2 / half_life
    """
    import math
    try:
        created = datetime.datetime.fromisoformat(created_at_str)
    except Exception:
        return 1.0

    age_days  = (datetime.datetime.now() - created).total_seconds() / 86400
    half_life = _HALF_LIFE_DAYS.get(importance, 14)
    lam       = 0.693 / half_life   # ln(2) / half_life
    weight    = math.exp(-lam * age_days)
    return max(0.05, weight)  # mínimo 5% — memória nunca some completamente

def get_memories_with_decay(limit: int = 10) -> list[dict]:
    """
    Retorna memórias ordenadas pelo score de decaimento × importância.
    Memórias recentes e importantes ficam no topo.
    """
    with _lock:
        conn = _conn()
        c = conn.cursor()
        c.execute('''
            SELECT id, category, content, importance, created_at, last_seen
            FROM memories
            ORDER BY importance DESC, last_seen DESC
            LIMIT 100
        ''')
        rows = c.fetchall()
        conn.close()

    results = []
    for r in rows:
        mem_id, category, content, importance, created_at, last_seen = r
        # Usa last_seen para decaimento (mais justo do que created_at)
        w = _decay_weight(importance, last_seen or created_at)
        score = importance * w
        results.append({
            'id':         mem_id,
            'category':   category,
            'content':    content,
            'importance': importance,
            'created_at': created_at,
            'decay_weight': round(w, 3),
            'score':      round(score, 3),
        })

    # Ordena pelo score composto
    results.sort(key=lambda x: x['score'], reverse=True)
    return results[:limit]

def apply_temporal_decay_to_prompt(memories_raw: list[dict]) -> str:
    """
    Recebe lista de memórias do banco e retorna bloco de texto
    para o system prompt, priorizando pelo score de decaimento.
    """
    if not memories_raw:
        return ''

    # Recalcula com decay para ordenação
    scored = []
    for m in memories_raw:
        w = _decay_weight(m.get('importance', 1), m.get('created_at', ''))
        scored.append((w * m.get('importance', 1), m))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [m for _, m in scored[:8]]

    lines = [f'- [{m["category"].upper()}] {m["content"]}' for m in top]
    return '\n\n## O QUE VOCÊ JÁ SABE SOBRE O Sir (ordenado por relevância recente)\n' + '\n'.join(lines)

def run_decay_cleanup(min_score: float = 0.03) -> int:
    """
    Remove memórias com score de decaimento abaixo do mínimo.
    Retorna quantas foram removidas.
    """
    with _lock:
        conn = _conn()
        c = conn.cursor()
        c.execute('SELECT id, importance, last_seen, created_at FROM memories')
        rows = c.fetchall()

        to_delete = []
        for row in rows:
            mem_id, importance, last_seen, created_at = row
            ref = last_seen or created_at
            w   = _decay_weight(importance, ref)
            if w * importance < min_score:
                to_delete.append(mem_id)

        if to_delete:
            placeholders = ','.join('?' * len(to_delete))
            c.execute(f'DELETE FROM memories WHERE id IN ({placeholders})', to_delete)
            conn.commit()

        conn.close()

    if to_delete:
        print(f'[TEMPORAL] Decay cleanup: {len(to_delete)} memórias expiradas removidas')
    return len(to_delete)


# ═══════════════════════════════════════════════════════════════════════════════
#  INTEGRAÇÃO COM build_system_prompt — versão temporal enriquecida
# ═══════════════════════════════════════════════════════════════════════════════

def build_temporal_system_prompt_extras(tz_offset: int = -3) -> str:
    """
    Retorna os blocos extras do Temporal Lobe para injetar no system prompt:
    - Contexto geo-temporal
    - Memórias com decay
    - Episódios recentes
    """
    blocks = []

    # 1. Contexto geo-temporal
    blocks.append(get_geo_temporal_prompt_block(tz_offset))

    # 2. Episódios recentes
    episode_block = get_episode_context(limit=4)
    if episode_block:
        blocks.append(episode_block)

    return '\n'.join(blocks)


# ═══════════════════════════════════════════════════════════════════════════════
#  INICIALIZAÇÃO
# ═══════════════════════════════════════════════════════════════════════════════

def init_temporal_lobe(tts_fn=None, emit_fn=None) -> None:
    """
    Inicializa o Temporal Lobe: tabelas + reminder watcher + decay scheduler.
    Chamar uma vez no startup do App.py.
    """
    init_temporal_tables()

    # Watcher de lembretes (precisa de tts_fn e emit_fn)
    if tts_fn and emit_fn:
        start_reminder_watcher(tts_fn, emit_fn)

    # Cleanup de decay uma vez por hora
    def _decay_loop():
        import time as _time
        while True:
            _time.sleep(3600)
            run_decay_cleanup()

    Thread(target=_decay_loop, daemon=True).start()
    print('[TEMPORAL LOBE] Inicializado')


if __name__ == '__main__':
    init_temporal_tables()
    print('=== Temporal Lobe — Teste ===')

    ctx = get_geo_temporal_context()
    print(f'\nContexto: {ctx["greeting"]}, {ctx["weekday"]}, {ctx["period"]}')
    if ctx['is_holiday']:
        print(f'Feriado: {ctx["holiday_name"]}')

    save_episode('Preciso terminar o relatório amanhã', 'Entendido, Sir.', 'conversation')
    print(f'\nEpisódios: {get_recent_episodes(limit=3)}')

    r = detect_and_save_reminder('reunião amanhã às 14h com o cliente', 'reunião amanhã às 14h')
    if r:
        print(f'\nLembrete criado: {r["remind_fmt"]}')

    print('\nTimeline hoje:', get_memories_by_period('hoje'))
    print('\nDecay test:', get_memories_with_decay(limit=3))
