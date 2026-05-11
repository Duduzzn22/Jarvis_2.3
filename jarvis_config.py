"""Configuration helpers for the J.A.R.V.I.S. Flask app."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv


def load_environment(candidates: tuple[str, ...] = ('.env', '_env', '.env.example')) -> str | None:
    """Load the first available dotenv file and return its path."""
    for candidate in candidates:
        if os.path.exists(candidate):
            load_dotenv(candidate)
            return candidate

    load_dotenv()
    return None


def env_float(name: str, default: str) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return float(default)


def env_bool(name: str, default: bool = False) -> bool:
    fallback = 'true' if default else 'false'
    return os.getenv(name, fallback).lower() in ('true', '1', 'yes')


def env_list(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(',') if item.strip()]


@dataclass(frozen=True)
class JarvisSettings:
    secret_key: str = field(default_factory=lambda: os.getenv('SECRET_KEY', 'jarvis-secret-2026'))

    gemini_api_key: str = field(default_factory=lambda: os.getenv('GEMINI_API_KEY', ''))
    groq_api_key: str = field(default_factory=lambda: os.getenv('GROQ_API_KEY', ''))
    telegram_bot_token: str = field(default_factory=lambda: os.getenv('TELEGRAM_BOT_TOKEN', ''))
    telegram_chat_id: str = field(default_factory=lambda: os.getenv('TELEGRAM_CHAT_ID', ''))

    trello_api_key: str = field(default_factory=lambda: os.getenv('TRELLO_API_KEY', ''))
    trello_token: str = field(default_factory=lambda: os.getenv('TRELLO_TOKEN', ''))
    trello_board_id: str = field(default_factory=lambda: os.getenv('TRELLO_BOARD_ID', ''))

    asana_token: str = field(default_factory=lambda: os.getenv('ASANA_TOKEN', ''))
    asana_project_id: str = field(default_factory=lambda: os.getenv('ASANA_PROJECT_ID', ''))

    news_api_key: str = field(default_factory=lambda: os.getenv('NEWS_API_KEY', ''))
    news_topics: list[str] = field(default_factory=lambda: env_list('NEWS_TOPICS', 'tecnologia,brasil'))

    motor_voz: str = field(default_factory=lambda: os.getenv('MOTOR_VOZ', 'elevenlabs'))
    elevenlabs_api_key: str = field(default_factory=lambda: os.getenv('ELEVENLABS_API_KEY', ''))
    elevenlabs_voice_id: str = field(default_factory=lambda: os.getenv('ELEVENLABS_VOICE_ID', ''))
    elevenlabs_model: str = field(default_factory=lambda: os.getenv('ELEVENLABS_MODEL', 'eleven_turbo_v2_5'))
    elevenlabs_stability: float = field(default_factory=lambda: env_float('ELEVENLABS_STABILITY', '0.75'))
    elevenlabs_similarity_boost: float = field(default_factory=lambda: env_float('ELEVENLABS_SIMILARITY', '0.80'))
    elevenlabs_style: float = field(default_factory=lambda: env_float('ELEVENLABS_STYLE', '0.05'))
    elevenlabs_speed: float = field(default_factory=lambda: env_float('ELEVENLABS_SPEED', '0.92'))
    elevenlabs_voice_map: dict[str, str] = field(default_factory=lambda: {
        'jarvis': os.getenv('ELEVENLABS_VOICE_JARVIS', ''),
        'cientista': os.getenv('ELEVENLABS_VOICE_CIENTISTA', ''),
        'guerreiro': os.getenv('ELEVENLABS_VOICE_GUERREIRO', ''),
        'zen': os.getenv('ELEVENLABS_VOICE_ZEN', ''),
        'sarcastico': os.getenv('ELEVENLABS_VOICE_EDITH', ''),
        'ator': os.getenv('ELEVENLABS_VOICE_ATOR', ''),
        'detetive': os.getenv('ELEVENLABS_VOICE_DETETIVE', ''),
        'sexta-feira': os.getenv('ELEVENLABS_VOICE_SEXTA_FEIRA', ''),
        'ultron': os.getenv('ELEVENLABS_VOICE_ULTRON', ''),
    })

    livekit_url: str = field(default_factory=lambda: os.getenv('LIVEKIT_URL', ''))
    livekit_api_key: str = field(default_factory=lambda: os.getenv('LIVEKIT_API_KEY', ''))
    livekit_api_secret: str = field(default_factory=lambda: os.getenv('LIVEKIT_API_SECRET', ''))

    mem0_api_key: str = field(default_factory=lambda: os.getenv('MEM0_API_KEY', ''))
    mem0_user_id: str = field(default_factory=lambda: os.getenv('MEM0_USER_ID', 'jarvis_user'))

    ollama_base_url: str = field(default_factory=lambda: os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434'))
    ollama_model: str = field(default_factory=lambda: os.getenv('OLLAMA_MODEL', 'llama3'))
    ollama_vision_model: str = field(default_factory=lambda: os.getenv('OLLAMA_VISION_MODEL', 'llava'))
    pc_agent_safe_mode: bool = field(default_factory=lambda: env_bool('PC_AGENT_SAFE_MODE', True))


def load_settings() -> JarvisSettings:
    return JarvisSettings()
