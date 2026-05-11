"""
J.A.R.V.I.S. — NEXUS MODULE
Versão 3.0 — Central de Comando

Responsabilidades:
  1. Nexus Dashboard  — status de todos os subsistemas em tempo real
  2. Plugin Manager   — registro, ativação e desativação de capacidades
  3. Nexus Sync       — export / import de perfil e memórias em JSON
  4. Health Check     — auto-diagnóstico proativo (APIs, TTS, microfone, memória)
  5. Setup Wizard API — endpoints para o onboarding via frontend
"""

import os
import json
import time
import datetime
import platform
import importlib
from pathlib import Path
from threading import Thread
from neural_core import process_input, get_pending_slots

# ─── CONFIGURAÇÃO DE PLUGINS ─────────────────────────────────────────────────

PLUGINS: dict[str, dict] = {
    "spotify": {
        "name": "Spotify",
        "description": "Controle de música via API do Spotify",
        "icon": "🎵",
        "env_keys": ["SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"],
        "enabled": False,
        "status": "unchecked",
    },
    "telegram": {
        "name": "Telegram",
        "description": "Envio de mensagens via bot do Telegram",
        "icon": "✈️",
        "env_keys": ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"],
        "enabled": False,
        "status": "unchecked",
    },
    "trello": {
        "name": "Trello",
        "description": "Gestão de tarefas e boards no Trello",
        "icon": "📋",
        "env_keys": ["TRELLO_API_KEY", "TRELLO_TOKEN"],
        "enabled": False,
        "status": "unchecked",
    },
    "asana": {
        "name": "Asana",
        "description": "Gestão de projetos e tarefas no Asana",
        "icon": "✅",
        "env_keys": ["ASANA_TOKEN"],
        "enabled": False,
        "status": "unchecked",
    },
    "news": {
        "name": "NewsAPI",
        "description": "Manchetes e notícias em tempo real",
        "icon": "📰",
        "env_keys": ["NEWS_API_KEY"],
        "enabled": False,
        "status": "unchecked",
    },
    "mem0": {
        "name": "Mem0",
        "description": "Memória de longo prazo na nuvem",
        "icon": "🧠",
        "env_keys": ["MEM0_API_KEY"],
        "enabled": False,
        "status": "unchecked",
    },
    "livekit": {
        "name": "LiveKit",
        "description": "Reconhecimento de voz avançado em tempo real",
        "icon": "🎙️",
        "env_keys": ["LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"],
        "enabled": False,
        "status": "unchecked",
    },
    "whatsapp": {
        "name": "WhatsApp",
        "description": "Envio de mensagens via WhatsApp Web",
        "icon": "💬",
        "env_keys": [],
        "pip_deps": ["pywhatkit"],
        "enabled": False,
        "status": "unchecked",
    },
    "scheduler": {
        "name": "Agendador",
        "description": "Automações e lembretes programados",
        "icon": "⏰",
        "env_keys": [],
        "enabled": True,
        "status": "active",
    },
    "tts": {
        "name": "Text-to-Speech",
        "description": "Síntese de voz com Edge TTS",
        "icon": "🔊",
        "env_keys": [],
        "pip_deps": ["edge_tts"],
        "enabled": True,
        "status": "unchecked",
    },
    "vad": {
        "name": "Detecção de Voz (VAD)",
        "description": "Reconhecimento automático de fala via Whisper",
        "icon": "🎤",
        "env_keys": [],
        "pip_deps": ["pyaudio"],
        "enabled": True,
        "status": "unchecked",
    },
    "instagram": {
        "name": "Instagram",
        "description": "Postar no feed, stories e enviar DMs",
        "icon": "📸",
        "env_keys": ["INSTAGRAM_USERNAME", "INSTAGRAM_PASSWORD"],
        "pip_deps": ["instagrapi"],
        "enabled": False,
        "status": "unchecked",
    },
    "google_sheets": {
        "name": "Google Sheets",
        "description": "Criar e editar planilhas no Google Sheets",
        "icon": "📊",
        "env_keys": [],
        "pip_deps": ["googleapiclient"],
        "enabled": False,
        "status": "unchecked",
    },
    "google_calendar": {
        "name": "Google Calendar",
        "description": "Gerenciar agenda e eventos",
        "icon": "📅",
        "env_keys": [],
        "pip_deps": ["googleapiclient"],
        "enabled": False,
        "status": "unchecked",
    },
    "google_maps": {
        "name": "Google Maps",
        "description": "Buscar locais e calcular rotas",
        "icon": "🗺️",
        "env_keys": [],
        "enabled": True,
        "status": "active",
    },
}


def refresh_plugins_from_env() -> None:
    """Lê o ambiente atual e atualiza o status de cada plugin."""
    for plugin_id, plugin in PLUGINS.items():
        env_keys = plugin.get("env_keys", [])
        pip_deps = plugin.get("pip_deps", [])

        # Todos env_keys devem estar presentes e não-vazios
        env_ok = all(bool(os.getenv(k)) for k in env_keys) if env_keys else True

        # Todos pip_deps devem ser importáveis
        pip_ok = True
        for dep in pip_deps:
            try:
                importlib.import_module(dep)
            except ImportError:
                pip_ok = False
                break

        if env_ok and pip_ok:
            plugin["enabled"] = True
            plugin["status"] = "active"
        elif plugin["status"] == "unchecked":
            plugin["enabled"] = False
            plugin["status"] = "inactive" if env_keys else "missing_dep"


def get_plugins_summary() -> list[dict]:
    """Retorna lista de plugins com status para o frontend."""
    refresh_plugins_from_env()
    return [
        {
            "id": pid,
            "name": p["name"],
            "description": p["description"],
            "icon": p["icon"],
            "enabled": p["enabled"],
            "status": p["status"],
            "env_keys": p.get("env_keys", []),
        }
        for pid, p in PLUGINS.items()
    ]


def toggle_plugin(plugin_id: str, enabled: bool) -> dict:
    """Ativa ou desativa um plugin manualmente."""
    if plugin_id not in PLUGINS:
        return {"success": False, "message": f"Plugin '{plugin_id}' não encontrado"}
    PLUGINS[plugin_id]["enabled"] = enabled
    PLUGINS[plugin_id]["status"] = "active" if enabled else "disabled"
    return {
        "success": True,
        "plugin_id": plugin_id,
        "enabled": enabled,
        "message": f"Plugin {PLUGINS[plugin_id]['name']} {'ativado' if enabled else 'desativado'}",
    }


# ─── HEALTH CHECK ─────────────────────────────────────────────────────────────

def run_health_check() -> dict:
    """
    Executa diagnóstico completo de todos os subsistemas.
    Retorna um dict com resultado de cada verificação.
    """
    results = {}
    start = time.time()

    # 1. Python e sistema
    results["system"] = {
        "label": "Sistema",
        "status": "ok",
        "detail": f"{platform.system()} {platform.release()} | Python {platform.python_version()}",
    }

    # 2. Cerebras
    cerebras_key = os.getenv("CEREBRAS_API_KEY", "")
    if cerebras_key:
        try:
            from openai import OpenAI as _OpenAI
            _OpenAI(api_key=cerebras_key, base_url="https://api.cerebras.ai/v1")
            results["cerebras"] = {"label": "Cerebras", "status": "ok", "detail": "API key configurada"}
        except Exception as e:
            results["cerebras"] = {"label": "Cerebras", "status": "error", "detail": str(e)[:80]}
    else:
        results["cerebras"] = {"label": "Cerebras", "status": "missing", "detail": "CEREBRAS_API_KEY não configurada"}

    # 3. Groq
    groq_key = os.getenv("GROQ_API_KEY", "")
    if groq_key:
        try:
            from groq import Groq
            Groq(api_key=groq_key)
            results["groq"] = {"label": "Groq", "status": "ok", "detail": "API key configurada"}
        except Exception as e:
            results["groq"] = {"label": "Groq", "status": "error", "detail": str(e)[:80]}
    else:
        results["groq"] = {"label": "Groq", "status": "missing", "detail": "GROQ_API_KEY não configurada"}

    # 4. Edge TTS
    try:
        import edge_tts
        results["tts"] = {"label": "TTS", "status": "ok", "detail": "edge-tts disponível"}
    except ImportError:
        results["tts"] = {"label": "TTS", "status": "error", "detail": "edge-tts não instalado"}

    # 5. Banco de memória
    try:
        from memory import get_memory_summary
        summary = get_memory_summary()
        total = summary.get("total_memories", 0)
        db_path = summary.get("db_path", "?")
        results["memory"] = {
            "label": "Memória",
            "status": "ok",
            "detail": f"{total} memórias salvas | DB: {db_path}",
        }
    except Exception as e:
        results["memory"] = {"label": "Memória", "status": "error", "detail": str(e)[:80]}

    # 6. Módulo de personalidades
    try:
        from personalities import get_all_personalities
        count = len(get_all_personalities())
        results["personalities"] = {
            "label": "Personalidades",
            "status": "ok",
            "detail": f"{count} personalidades carregadas",
        }
    except Exception as e:
        results["personalities"] = {"label": "Personalidades", "status": "error", "detail": str(e)[:80]}

    # 7. Scheduler
    try:
        from scheduler import get_all_tasks
        tasks = get_all_tasks()
        results["scheduler"] = {
            "label": "Agendador",
            "status": "ok",
            "detail": f"{len(tasks)} tarefas agendadas",
        }
    except Exception as e:
        results["scheduler"] = {"label": "Agendador", "status": "error", "detail": str(e)[:80]}

    # 8. Disco
    try:
        import psutil
        usage = psutil.disk_usage(Path.cwd())
        free_gb = usage.free / (1024 ** 3)
        results["disk"] = {
            "label": "Disco",
            "status": "ok" if free_gb > 1 else "warning",
            "detail": f"{free_gb:.1f} GB livres ({100 - usage.percent:.0f}% disponível)",
        }
    except Exception as e:
        results["disk"] = {"label": "Disco", "status": "unknown", "detail": str(e)[:80]}

    # 9. RAM
    try:
        import psutil
        mem = psutil.virtual_memory()
        avail_mb = mem.available / (1024 ** 2)
        results["ram"] = {
            "label": "RAM",
            "status": "ok" if mem.percent < 85 else "warning",
            "detail": f"{avail_mb:.0f} MB livres | {mem.percent:.0f}% em uso",
        }
    except Exception as e:
        results["ram"] = {"label": "RAM", "status": "unknown", "detail": str(e)[:80]}

    elapsed = round((time.time() - start) * 1000)

    # Calcula status geral
    statuses = [r["status"] for r in results.values()]
    if "error" in statuses:
        overall = "degraded"
    elif "missing" in statuses:
        overall = "partial"
    elif "warning" in statuses:
        overall = "warning"
    else:
        overall = "healthy"

    return {
        "overall": overall,
        "checks": results,
        "elapsed_ms": elapsed,
        "timestamp": datetime.datetime.now().isoformat(),
    }


# ─── NEXUS DASHBOARD ──────────────────────────────────────────────────────────

def get_dashboard_status() -> dict:
    """Retorna snapshot de status do sistema para o Nexus Dashboard."""
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.2)
        mem = psutil.virtual_memory()
        ram_pct = mem.percent
    except Exception:
        cpu, ram_pct = 0, 0

    try:
        from memory import get_memory_summary, get_profile_field
        summary = get_memory_summary()
        user_name = get_profile_field("user_name") or "Sir"
        total_memories = summary.get("total_memories", 0)
        log_count = len(summary.get("recent_log", []))
    except Exception:
        user_name = "Sir"
        total_memories = 0
        log_count = 0

    try:
        from personalities import get_current_name, get_personality
        current_personality = get_current_name()
        p = get_personality(current_personality)
        personality_name = p.get("name", "J.A.R.V.I.S.")
        personality_color = p.get("color", "#00d4ff")
    except Exception:
        personality_name = "J.A.R.V.I.S."
        personality_color = "#00d4ff"
        current_personality = "jarvis"

    try:
        from scheduler import get_all_tasks
        scheduled_tasks = len(get_all_tasks())
    except Exception:
        scheduled_tasks = 0

    plugins = get_plugins_summary()
    active_plugins = sum(1 for p in plugins if p["enabled"])

    return {
        "timestamp": datetime.datetime.now().isoformat(),
        "uptime": _get_uptime(),
        "user_name": user_name,
        "cpu_pct": round(cpu),
        "ram_pct": round(ram_pct),
        "total_memories": total_memories,
        "log_count": log_count,
        "personality": {
            "id": current_personality,
            "name": personality_name,
            "color": personality_color,
        },
        "scheduled_tasks": scheduled_tasks,
        "active_plugins": active_plugins,
        "total_plugins": len(plugins),
        "ai_available": {
            "cerebras": bool(os.getenv("CEREBRAS_API_KEY")),
            "groq": bool(os.getenv("GROQ_API_KEY")),
        },
    }


_start_time = time.time()

def _get_uptime() -> str:
    elapsed = int(time.time() - _start_time)
    h = elapsed // 3600
    m = (elapsed % 3600) // 60
    s = elapsed % 60
    if h > 0:
        return f"{h}h {m:02d}m"
    return f"{m}m {s:02d}s"


# ─── NEXUS SYNC ───────────────────────────────────────────────────────────────

def export_profile(output_path: str | None = None) -> dict:
    """
    Exporta todo o perfil e memórias do JARVIS para um arquivo JSON.
    Retorna o dict exportado e o caminho do arquivo gerado.
    """
    try:
        from memory import get_memory_summary, get_profile
        data = get_memory_summary()
        data["exported_at"] = datetime.datetime.now().isoformat()
        data["jarvis_version"] = "3.0"
        data["platform"] = platform.system()

        if output_path is None:
            stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"jarvis_backup_{stamp}.json"

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return {
            "success": True,
            "path": output_path,
            "memories": data.get("total_memories", 0),
            "exported_at": data["exported_at"],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def import_profile(input_path: str) -> dict:
    """
    Importa um backup JSON criado pelo export_profile.
    Sobrescreve perfil e memórias existentes.
    """
    try:
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        from memory import set_profile, add_memory, clear_all_memories

        # Restaura perfil
        profile = data.get("profile", {})
        for key, value in profile.items():
            if value:
                set_profile(key, value)

        # Restaura memórias
        memories = data.get("memories", [])
        if memories:
            clear_all_memories()
            for mem in memories:
                add_memory(
                    mem.get("category", "geral"),
                    mem.get("content", ""),
                    importance=mem.get("importance", 1),
                )

        return {
            "success": True,
            "profile_keys": len(profile),
            "memories_restored": len(memories),
            "source_version": data.get("jarvis_version", "?"),
            "exported_at": data.get("exported_at", "?"),
        }
    except FileNotFoundError:
        return {"success": False, "error": f"Arquivo '{input_path}' não encontrado"}
    except json.JSONDecodeError:
        return {"success": False, "error": "Arquivo JSON inválido"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── SETUP WIZARD STATE ───────────────────────────────────────────────────────

_setup_state: dict = {
    "completed": False,
    "step": 0,
    "total_steps": 6,
}


def get_setup_state() -> dict:
    """Retorna estado atual do wizard de configuração."""
    try:
        from memory import is_profile_complete, get_profile
        completed = is_profile_complete()
        profile = get_profile()
        _setup_state["completed"] = completed
        _setup_state["profile"] = profile
        return _setup_state
    except Exception:
        return _setup_state


def complete_setup_step(step_data: dict) -> dict:
    """
    Processa um passo do wizard de configuração.
    step_data deve conter: step, field, value (e opcionalmente memory_category)
    """
    try:
        from memory import set_profile, add_memory

        step = step_data.get("step", 0)
        field = step_data.get("field")
        value = step_data.get("value")
        category = step_data.get("memory_category", "pessoal")
        memory_text = step_data.get("memory_text")

        if field and value:
            set_profile(field, value)
        if memory_text:
            add_memory(category, memory_text, importance=step_data.get("importance", 2))

        _setup_state["step"] = step + 1
        return {"success": True, "step": step, "next_step": step + 1}
    except Exception as e:
        return {"success": False, "error": str(e)}


def finalize_setup() -> dict:
    """Marca o setup como completo."""
    try:
        from memory import set_profile
        set_profile("setup_completed", "true")
        _setup_state["completed"] = True
        return {"success": True, "message": "Setup finalizado com sucesso"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── INICIALIZAÇÃO ────────────────────────────────────────────────────────────

def init_nexus() -> None:
    """Inicializa o Nexus — deve ser chamado pelo App.py na inicialização."""
    refresh_plugins_from_env()
    print(f"[NEXUS] Central inicializada | {len(PLUGINS)} plugins registrados")
    active = sum(1 for p in PLUGINS.values() if p["enabled"])
    print(f"[NEXUS] Plugins ativos: {active}/{len(PLUGINS)}")


if __name__ == "__main__":
    init_nexus()
    print("\n=== Dashboard ===")
    import pprint
    pprint.pprint(get_dashboard_status())
    print("\n=== Health Check ===")
    pprint.pprint(run_health_check())
    print("\n=== Plugins ===")
    for p in get_plugins_summary():
        icon = "✓" if p["enabled"] else "✗"
        print(f"  {icon} {p['icon']} {p['name']} — {p['status']}")

PATCH_7_NEXUS = """
    \"pc_agent\": {
        \"name\": \"PC Agent\",
        \"description\": \"Agente visual de controle de PC com Gemini Vision\",
        \"icon\": \"🤖\",
        \"env_keys\": [\"GEMINI_API_KEY\"],
        \"pip_deps\": [\"pyautogui\", \"PIL\"],
        \"enabled\": False,
        \"status\": \"unchecked\",
    },
"""
 
if __name__ == '__main__':
    print("Este arquivo documenta as alterações a fazer no App.py e nexus.py.")
    print("Não execute este arquivo diretamente.")
    print("Consulte cada PATCH_N para saber onde inserir cada bloco.")