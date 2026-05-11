"""
J.A.R.V.I.S. — Motor de Memória Persistente
Módulo 2: Consciência
Usa SQLite para persistir histórico, fatos e perfil do usuário entre sessões.
"""

import sqlite3
import json
import os
import datetime
from pathlib import Path
from threading import Lock

# Temporal Lobe — importado de forma lazy para evitar circular import
_temporal_lobe = None
def _get_temporal():
    global _temporal_lobe
    if _temporal_lobe is None:
        try:
            import temporal_lobe as _tl
            _temporal_lobe = _tl
        except ImportError:
            pass
    return _temporal_lobe

# Caminho do banco — fica na mesma pasta do script principal
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'jarvis.db')
SOUL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'SOUL.md')

_db_lock = Lock()


# ─── INICIALIZAÇÃO DO BANCO ──────────────────────────────────────────────────

def init_db():
    """Cria as tabelas se não existirem. Seguro chamar múltiplas vezes."""
    with _db_lock:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        # Perfil do usuário (uma única linha)
        c.execute('''
            CREATE TABLE IF NOT EXISTS user_profile (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')

        # Fatos que o JARVIS aprendeu sobre o usuário
        c.execute('''
            CREATE TABLE IF NOT EXISTS memories (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                category   TEXT NOT NULL,
                content    TEXT NOT NULL,
                importance INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                last_seen  TEXT NOT NULL
            )
        ''')

        # Histórico de conversas (para contexto de longo prazo)
        c.execute('''
            CREATE TABLE IF NOT EXISTS conversation_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                role       TEXT NOT NULL,
                content    TEXT NOT NULL,
                intent     TEXT,
                timestamp  TEXT NOT NULL
            )
        ''')

        conn.commit()
        conn.close()
    print('[JARVIS] Banco de memória inicializado:', DB_PATH)


# ─── PERFIL DO USUÁRIO ───────────────────────────────────────────────────────

def get_profile() -> dict:
    """Retorna todos os campos do perfil do usuário."""
    with _db_lock:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT key, value FROM user_profile')
        rows = c.fetchall()
        conn.close()
    return {row[0]: row[1] for row in rows}


def set_profile(key: str, value: str):
    """Define ou atualiza um campo do perfil."""
    now = datetime.datetime.now().isoformat()
    with _db_lock:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''
            INSERT INTO user_profile (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
        ''', (key, value, now))
        conn.commit()
        conn.close()


def get_profile_field(key: str, default: str = '') -> str:
    """Retorna um campo específico do perfil."""
    profile = get_profile()
    return profile.get(key, default)


def is_profile_complete() -> bool:
    """Verifica se o perfil mínimo foi preenchido (nome do usuário)."""
    return bool(get_profile_field('user_name'))


# ─── MEMÓRIAS / FATOS APRENDIDOS ─────────────────────────────────────────────

def add_memory(category: str, content: str, importance: int = 1):
    """
    Adiciona um fato à memória do JARVIS.
    Categorias sugeridas: preferencia, habito, trabalho, pessoal, tecnologia
    Importância: 1 (normal), 2 (importante), 3 (crítico)
    """
    now = datetime.datetime.now().isoformat()

    # Verifica se já existe fato similar (evita duplicatas)
    with _db_lock:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        # Busca por conteúdo parecido na mesma categoria
        c.execute('''
            SELECT id FROM memories
            WHERE category = ? AND content LIKE ?
        ''', (category, f'%{content[:30]}%'))

        existing = c.fetchone()

        if existing:
            # Atualiza o last_seen e importância se for mais relevante
            c.execute('''
                UPDATE memories SET last_seen = ?, importance = MAX(importance, ?)
                WHERE id = ?
            ''', (now, importance, existing[0]))
        else:
            c.execute('''
                INSERT INTO memories (category, content, importance, created_at, last_seen)
                VALUES (?, ?, ?, ?, ?)
            ''', (category, content, importance, now, now))

        conn.commit()
        conn.close()


def get_memories(category: str = None, limit: int = 10) -> list:
    """
    Retorna memórias salvas, ordenadas por importância e recência.
    Se category for None, retorna de todas as categorias.
    """
    with _db_lock:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        if category:
            c.execute('''
                SELECT category, content, importance, created_at
                FROM memories
                WHERE category = ?
                ORDER BY importance DESC, last_seen DESC
                LIMIT ?
            ''', (category, limit))
        else:
            c.execute('''
                SELECT category, content, importance, created_at
                FROM memories
                ORDER BY importance DESC, last_seen DESC
                LIMIT ?
            ''', (limit,))

        rows = c.fetchall()
        conn.close()

    return [
        {'category': r[0], 'content': r[1], 'importance': r[2], 'created_at': r[3]}
        for r in rows
    ]


def get_all_memories() -> list:
    """Retorna todas as memórias (para exibir no painel da interface)."""
    return get_memories(limit=50)


def delete_memory(memory_id: int):
    """Remove uma memória específica pelo ID."""
    with _db_lock:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('DELETE FROM memories WHERE id = ?', (memory_id,))
        conn.commit()
        conn.close()


def clear_all_memories():
    """Apaga todas as memórias (mantém o perfil)."""
    with _db_lock:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('DELETE FROM memories')
        c.execute('DELETE FROM conversation_log')
        conn.commit()
        conn.close()


# ─── HISTÓRICO DE CONVERSAS ──────────────────────────────────────────────────

def log_message(role: str, content: str, intent: str = None):
    """Registra uma mensagem no log permanente de conversas."""
    now = datetime.datetime.now().isoformat()
    with _db_lock:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''
            INSERT INTO conversation_log (role, content, intent, timestamp)
            VALUES (?, ?, ?, ?)
        ''', (role, content, intent, now))

        # Mantém apenas as últimas 500 mensagens no log permanente
        c.execute('''
            DELETE FROM conversation_log WHERE id NOT IN (
                SELECT id FROM conversation_log ORDER BY id DESC LIMIT 500
            )
        ''')

        conn.commit()
        conn.close()


def get_recent_log(limit: int = 10) -> list:
    """Retorna as últimas N mensagens do log permanente."""
    with _db_lock:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''
            SELECT role, content, intent, timestamp
            FROM conversation_log
            ORDER BY id DESC
            LIMIT ?
        ''', (limit,))
        rows = c.fetchall()
        conn.close()

    # Retorna em ordem cronológica (mais antigas primeiro)
    return [
        {'role': r[0], 'content': r[1], 'intent': r[2], 'timestamp': r[3]}
        for r in reversed(rows)
    ]


# ─── GERAÇÃO DO SYSTEM PROMPT COM MEMÓRIA ────────────────────────────────────

# ─── Cache em memória para evitar I/O de disco a cada mensagem ───────────────
_soul_cache: str | None = None
_system_prompt_cache: dict = {'prompt': '', 'ts': 0.0}
_SYSTEM_PROMPT_TTL = 30  # segundos — recarrega memória a cada 30s no máx

def _load_soul() -> str:
    global _soul_cache
    if _soul_cache is None:
        try:
            with open(SOUL_PATH, 'r', encoding='utf-8') as f:
                _soul_cache = f.read()
        except FileNotFoundError:
            _soul_cache = "Você é J.A.R.V.I.S., assistente pessoal. Responda sempre em português brasileiro, de forma formal e elegante, chamando o usuário de Senhor."
    return _soul_cache

def build_system_prompt() -> str:
    """
    Constrói o system prompt completo combinando:
    1. SOUL.md (personalidade) — cacheado em memória
    2. Perfil do usuário
    3. Memórias relevantes
    4. Data/hora atual
    Cache de 30s para evitar SQLite + disk I/O a cada mensagem.
    """
    import time as _time
    now_ts = _time.monotonic()

    # Retorna cache se ainda válido
    if _system_prompt_cache['prompt'] and (now_ts - _system_prompt_cache['ts']) < _SYSTEM_PROMPT_TTL:
        return _system_prompt_cache['prompt']

    soul = _load_soul()

    # Data/hora atual
    agora = datetime.datetime.now()
    data_hora = agora.strftime('%A, %d de %B de %Y às %H:%M')

    # Perfil do usuário
    profile = get_profile()
    user_name = profile.get('user_name', '')
    user_prefs = profile.get('preferences', '')
    work_hours = profile.get('work_hours', '')

    profile_block = '\n\n## PERFIL DO USUÁRIO (USE SEMPRE)\n'
    if user_name:
        profile_block += f'- Nome: {user_name} (chame de "Senhor", ou "{user_name}")\n'
    else:
        profile_block += '- Nome: desconhecido (pergunte educadamente em algum momento)\n'
    if user_prefs:
        profile_block += f'- Preferências: {user_prefs}\n'
    if work_hours:
        profile_block += f'- Horário de trabalho: {work_hours}\n'

    # Memórias relevantes — com Temporal Decay
    tl = _get_temporal()
    memories = get_memories(limit=20)
    if tl and memories:
        mem_block = tl.apply_temporal_decay_to_prompt(memories)
    elif memories:
        mem_block = '\n\n## O QUE VOCÊ JÁ SABE SOBRE O SENHOR\n'
        for m in memories:
            mem_block += f'- [{m["category"].upper()}] {m["content"]}\n'
    else:
        mem_block = ''

    # Contexto geo-temporal
    if tl:
        time_block = tl.build_temporal_system_prompt_extras()
    else:
        time_block = f'\n\n## CONTEXTO ATUAL\nData e hora: {data_hora}'

    result = soul + profile_block + mem_block + time_block

    # Salva cache
    _system_prompt_cache['prompt'] = result
    _system_prompt_cache['ts'] = now_ts

    return result


# ─── EXTRAÇÃO AUTOMÁTICA DE FATOS ────────────────────────────────────────────

def extract_facts_from_message(text: str):
    """
    Tenta extrair fatos simples de uma mensagem do usuário usando regras básicas.
    A extração avançada via IA é feita no App.py após a resposta do modelo.
    """
    text_lower = text.lower()

    # Detecta nome
    for prefix in ['me chamo ', 'meu nome é ', 'sou o ', 'sou a ', 'pode me chamar de ']:
        if prefix in text_lower:
            idx = text_lower.index(prefix) + len(prefix)
            name = text[idx:].split()[0].strip('.,!?')
            if 2 < len(name) < 30:
                set_profile('user_name', name.title())
                add_memory('pessoal', f'Usuário se chama {name.title()}', importance=3)
                return

    # Detecta preferências de apps
    for app in ['spotify', 'chrome', 'firefox', 'vscode', 'discord', 'steam']:
        if f'uso {app}' in text_lower or f'prefiro {app}' in text_lower:
            add_memory('tecnologia', f'Prefere usar {app}', importance=2)


# ─── UTILITÁRIOS ─────────────────────────────────────────────────────────────

def get_memory_summary() -> dict:
    """Retorna um resumo do estado atual da memória (para a API e frontend)."""
    profile = get_profile()
    memories = get_all_memories()
    recent_log = get_recent_log(5)

    return {
        'profile': profile,
        'memories': memories,
        'recent_log': recent_log,
        'total_memories': len(memories),
        'db_path': DB_PATH,
    }


# ─── INICIALIZAÇÃO AUTOMÁTICA ─────────────────────────────────────────────────

# Cria o banco ao importar o módulo
init_db()

if __name__ == '__main__':
    # Teste rápido
    print('=== Teste do motor de memória ===')
    set_profile('user_name', 'Tony')
    set_profile('preferences', 'Gosta de jazz e trabalha com tecnologia')
    add_memory('trabalho', 'Trabalha como desenvolvedor', importance=2)
    add_memory('preferencia', 'Prefere respostas curtas', importance=2)
    add_memory('tecnologia', 'Usa Windows 11 com VSCode', importance=1)

    print('\nPerfil:', get_profile())
    print('\nMemórias:', get_memories())
    print('\nSystem prompt gerado:')
    print(build_system_prompt()[:500], '...')