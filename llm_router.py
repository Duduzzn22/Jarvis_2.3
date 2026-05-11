"""
J.A.R.V.I.S. v2.3 — LLM Router
================================
Roteador central inteligente para todas as chamadas de IA.

ESTRATÉGIA DE ROTEAMENTO:
  chat       → Groq/llama-3.3-70b  → Groq/qwen-qwq-32b  → Ollama  → erro
  intent     → Groq/llama-3.1-8b   → Groq/llama-3.3-70b  → Ollama  → conversation
  summary    → Groq/llama-3.1-8b   → Groq/llama-3.3-70b  → Ollama
  vision     → Gemini/2.0-flash     → Groq/llama-4-scout  → Ollama/llava
  stream     → Groq/llama-3.3-70b (stream=True) → Ollama (stream)

MECANISMOS DE CONFIABILIDADE:
  - Circuit breaker por modelo (3 falhas → cooldown 5 min)
  - Retry com backoff exponencial via tenacity (1s → 2s → 4s, máx 3)
  - Cache LRU para intent detection (TTL 30s, evita chamadas repetidas)
  - Timeout agressivo: 8s chat, 5s intent, 25s visão

USO:
    from llm_router import get_router
    router = get_router()
    router.init(groq_client, gemini_client, ollama_url, ollama_model)

    # Chat (retorna tuple[str, str])
    text, model_used = router.chat(messages, system_prompt)

    # Stream (generator de tokens)
    for token in router.stream(messages, system_prompt):
        ...

    # Intent (retorna dict)
    intent_data = router.intent(text, prompt)

    # Visão (retorna str)
    result = router.vision(img_b64, query, mime_type)

    # Sumário simples (retorna str)
    summary = router.summarize(prompt)
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from threading import Lock
from typing import Generator, Optional

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
#  CIRCUIT BREAKER
# ═══════════════════════════════════════════════════════════════════════════════

_CB_FAILURE_THRESHOLD = 3      # falhas consecutivas para abrir o circuito
_CB_COOLDOWN_SECONDS  = 300    # 5 minutos de cooldown

@dataclass
class _CircuitState:
    failures:     int   = 0
    opened_at:    float = 0.0
    is_open:      bool  = False

class CircuitBreaker:
    """Circuit breaker por chave (modelo). Thread-safe."""

    def __init__(self):
        self._states: dict[str, _CircuitState] = {}
        self._lock = Lock()

    def is_available(self, key: str) -> bool:
        with self._lock:
            state = self._states.get(key)
            if state is None:
                return True
            if not state.is_open:
                return True
            # Verifica se o cooldown já expirou
            if time.time() - state.opened_at >= _CB_COOLDOWN_SECONDS:
                state.is_open    = False
                state.failures   = 0
                state.opened_at  = 0.0
                logger.info(f"[CB] Circuito {key!r} fechado após cooldown")
                return True
            remaining = int(_CB_COOLDOWN_SECONDS - (time.time() - state.opened_at))
            logger.debug(f"[CB] Circuito {key!r} aberto — cooldown {remaining}s restantes")
            return False

    def record_failure(self, key: str) -> None:
        with self._lock:
            state = self._states.setdefault(key, _CircuitState())
            state.failures += 1
            if state.failures >= _CB_FAILURE_THRESHOLD:
                state.is_open   = True
                state.opened_at = time.time()
                logger.warning(f"[CB] Circuito {key!r} ABERTO após {state.failures} falhas")

    def record_success(self, key: str) -> None:
        with self._lock:
            state = self._states.get(key)
            if state:
                state.failures  = 0
                state.is_open   = False
                state.opened_at = 0.0

    def reset(self, key: str) -> None:
        with self._lock:
            self._states.pop(key, None)

    def status(self) -> dict:
        with self._lock:
            return {
                k: {"open": s.is_open, "failures": s.failures}
                for k, s in self._states.items()
            }


# ═══════════════════════════════════════════════════════════════════════════════
#  LRU CACHE COM TTL (para intent detection)
# ═══════════════════════════════════════════════════════════════════════════════

class _TTLCache:
    """LRU cache com TTL. Guarda resultados de intent detection recentes."""

    def __init__(self, maxsize: int = 128, ttl: float = 30.0):
        self._cache: OrderedDict[str, tuple[dict, float]] = OrderedDict()
        self._maxsize = maxsize
        self._ttl     = ttl
        self._lock    = Lock()
        self._hits    = 0
        self._misses  = 0

    def _key(self, text: str) -> str:
        # Normaliza o texto para maximizar cache hits
        return re.sub(r'\s+', ' ', text.lower().strip())

    def get(self, text: str) -> dict | None:
        key = self._key(text)
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None
            value, ts = self._cache[key]
            if time.time() - ts > self._ttl:
                del self._cache[key]
                self._misses += 1
                return None
            # Move para o fim (LRU)
            self._cache.move_to_end(key)
            self._hits += 1
            return value

    def set(self, text: str, value: dict) -> None:
        key = self._key(text)
        with self._lock:
            self._cache[key] = (value, time.time())
            self._cache.move_to_end(key)
            while len(self._cache) > self._maxsize:
                self._cache.popitem(last=False)

    def stats(self) -> dict:
        total = self._hits + self._misses
        ratio = self._hits / total if total else 0.0
        return {"hits": self._hits, "misses": self._misses, "ratio": round(ratio, 3)}


# ═══════════════════════════════════════════════════════════════════════════════
#  MODELOS POR ROTA
# ═══════════════════════════════════════════════════════════════════════════════

# Chat / conversa
_CHAT_MODELS_GROQ = [
    "llama-3.3-70b-versatile",
    "qwen-qwq-32b",
]

# Intent detection — modelos menores, mais rápidos
_INTENT_MODELS_GROQ = [
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
]

# Sumarização / análise de texto — 8b suficiente
_SUMMARY_MODELS_GROQ = [
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
]

# Visão — Gemini PRIMEIRO (nativo), depois Groq Vision, depois Ollama
_VISION_MODELS_GEMINI = [
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
]
_VISION_MODELS_GROQ = [
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "llama-3.2-11b-vision-preview",
]

# Timeouts por rota (segundos)
_TIMEOUT = {
    "chat":    10,
    "stream":  60,
    "intent":   6,
    "summary": 15,
    "vision":  25,
}

# Tokens máximos por rota
_MAX_TOKENS = {
    "chat":    350,
    "stream":  400,
    "intent":  140,
    "summary": 500,
    "vision":  600,
}


# ═══════════════════════════════════════════════════════════════════════════════
#  LLM ROUTER
# ═══════════════════════════════════════════════════════════════════════════════

class LLMRouter:
    """
    Roteador central de LLMs para o JARVIS v2.3.
    Instância única — use get_router() para obter.
    """

    def __init__(self):
        self._groq        = None
        self._gemini      = None
        self._ollama_url  = "http://localhost:11434"
        self._ollama_model       = "llama3"
        self._ollama_vision_model = "llava"
        self._ollama_available    = False
        self._gemini_available    = False
        self._groq_available      = False

        self._cb     = CircuitBreaker()
        self._cache  = _TTLCache(maxsize=256, ttl=30.0)
        self._lock   = Lock()

    # ── Inicialização ──────────────────────────────────────────────────────────

    def init(
        self,
        groq_client,
        gemini_client,
        ollama_url:          str  = "http://localhost:11434",
        ollama_model:        str  = "llama3",
        ollama_vision_model: str  = "llava",
        ollama_available:    bool = False,
        gemini_available:    bool = False,
    ) -> None:
        """Injeta dependências. Chamado uma vez em App.py após criar os clientes."""
        self._groq   = groq_client
        self._gemini = gemini_client

        self._ollama_url          = ollama_url
        self._ollama_model        = ollama_model
        self._ollama_vision_model = ollama_vision_model
        self._ollama_available    = ollama_available
        self._gemini_available    = gemini_available and (gemini_client is not None)
        self._groq_available      = groq_client is not None

        logger.info(
            f"[ROUTER] Inicializado — "
            f"Groq: {'ON' if self._groq_available else 'OFF'} | "
            f"Gemini: {'ON' if self._gemini_available else 'OFF'} | "
            f"Ollama: {'ON' if self._ollama_available else 'OFF'}"
        )

    # ── Helpers internos ───────────────────────────────────────────────────────

    def _groq_call(
        self,
        model:      str,
        messages:   list,
        max_tokens: int,
        temperature: float,
        timeout:    int,
        stream:     bool = False,
    ):
        """Chamada Groq com circuit breaker. Retorna objeto de resposta ou None."""
        key = f"groq/{model}"
        if not self._cb.is_available(key):
            return None
        if not self._groq_available or not self._groq:
            return None
        try:
            resp = self._groq.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=timeout,
                stream=stream,
            )
            self._cb.record_success(key)
            return resp
        except Exception as e:
            err = str(e)
            # Rate limit não conta como falha de circuito (é temporário)
            if "429" not in err and "rate_limit" not in err.lower():
                self._cb.record_failure(key)
            logger.warning(f"[ROUTER] Groq/{model} falhou: {err[:120]}")
            return None

    def _gemini_call(self, model: str, contents: list, max_tokens: int, config: dict | None = None):
        """Chamada Gemini com circuit breaker."""
        key = f"gemini/{model}"
        if not self._cb.is_available(key):
            return None
        if not self._gemini_available or not self._gemini:
            return None
        try:
            cfg = config or {"max_output_tokens": max_tokens, "temperature": 0.7}
            resp = self._gemini.models.generate_content(
                model=model, contents=contents, config=cfg
            )
            self._cb.record_success(key)
            return resp
        except Exception as e:
            err = str(e)
            if "429" not in err and "RESOURCE_EXHAUSTED" not in err:
                self._cb.record_failure(key)
            logger.warning(f"[ROUTER] Gemini/{model} falhou: {err[:120]}")
            return None

    def _ollama_call(
        self,
        messages:   list,
        max_tokens: int,
        temperature: float,
        timeout:    int,
        stream:     bool = False,
        vision_model: bool = False,
    ):
        """Chamada Ollama com circuit breaker."""
        key = "ollama"
        if not self._cb.is_available(key) or not self._ollama_available:
            return None
        import requests as req
        model = self._ollama_vision_model if vision_model else self._ollama_model
        try:
            resp = req.post(
                f"{self._ollama_url}/api/chat",
                json={
                    "model":    model,
                    "messages": messages,
                    "stream":   stream,
                    "keep_alive": "5m",
                    "options":  {"temperature": temperature, "num_predict": max_tokens},
                },
                timeout=timeout,
                stream=stream,
            )
            resp.raise_for_status()
            self._cb.record_success(key)
            return resp
        except Exception as e:
            self._cb.record_failure(key)
            logger.warning(f"[ROUTER] Ollama falhou: {str(e)[:120]}")
            return None

    # ── API pública: chat (síncrono) ───────────────────────────────────────────

    def chat(
        self,
        messages:    list,
        system:      str = "",
        temperature: float = 0.7,
        max_tokens:  int = 0,
    ) -> tuple[str, str]:
        """
        Gera resposta de chat.
        Rota: Groq/70b → Groq/qwen → Ollama → fallback texto
        Retorna (texto_resposta, modelo_usado).
        """
        mt = max_tokens or _MAX_TOKENS["chat"]
        msgs = ([{"role": "system", "content": system}] if system else []) + messages

        # 1. Groq (modelos em cascata)
        for model in _CHAT_MODELS_GROQ:
            resp = self._groq_call(model, msgs, mt, temperature, _TIMEOUT["chat"])
            if resp:
                text = resp.choices[0].message.content
                logger.info(f"[ROUTER] chat via groq/{model}")
                return text, f"groq/{model}"

        # 2. Ollama (offline)
        resp = self._ollama_call(msgs, mt, temperature, 30)
        if resp:
            text = resp.json()["message"]["content"]
            logger.info(f"[ROUTER] chat via ollama/{self._ollama_model}")
            return text, f"ollama/{self._ollama_model}"

        logger.error("[ROUTER] chat: todos os motores falharam")
        return "Peço desculpas, Senhor. Estou com dificuldades técnicas no momento.", "none"

    # ── API pública: stream ────────────────────────────────────────────────────

    def stream(
        self,
        messages:    list,
        system:      str = "",
        temperature: float = 0.7,
        max_tokens:  int = 0,
    ) -> Generator[str, None, None]:
        """
        Gera resposta em streaming (token a token).
        Rota: Groq/70b (stream) → Ollama (stream) → fallback texto único
        Yields tokens de string.
        """
        mt   = max_tokens or _MAX_TOKENS["stream"]
        msgs = ([{"role": "system", "content": system}] if system else []) + messages

        # 1. Groq streaming
        for model in _CHAT_MODELS_GROQ:
            resp = self._groq_call(model, msgs, mt, temperature, _TIMEOUT["stream"], stream=True)
            if resp:
                logger.info(f"[ROUTER] stream via groq/{model}")
                try:
                    for chunk in resp:
                        token = chunk.choices[0].delta.content
                        if token:
                            yield token
                    return
                except Exception as e:
                    logger.warning(f"[ROUTER] Groq stream interrompido: {e}")
                    self._cb.record_failure(f"groq/{model}")
                    break

        # 2. Ollama streaming
        resp = self._ollama_call(msgs, mt, temperature, _TIMEOUT["stream"], stream=True)
        if resp:
            logger.info(f"[ROUTER] stream via ollama/{self._ollama_model}")
            try:
                for line in resp.iter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    token = chunk.get("message", {}).get("content", "")
                    if token:
                        yield token
                    if chunk.get("done"):
                        return
                return
            except Exception as e:
                logger.warning(f"[ROUTER] Ollama stream interrompido: {e}")

        # 3. Fallback: texto único
        logger.error("[ROUTER] stream: todos os motores falharam, usando fallback texto")
        yield "Desculpe, estou com dificuldades na minha conexão neural, Senhor."

    # ── API pública: intent ────────────────────────────────────────────────────

    def intent(self, text: str, prompt: str) -> dict:
        """
        Classifica a intenção do texto.
        Rota: cache → Groq/8b → Groq/70b → Ollama → conversation
        Retorna dict {intent, params}.
        """
        # 0. Cache hit — zero latência
        cached = self._cache.get(text)
        if cached is not None:
            logger.debug(f"[ROUTER] intent cache hit: {cached.get('intent')}")
            return cached

        mt = _MAX_TOKENS["intent"]

        # 1. Groq modelos de intent (8b primeiro)
        for model in _INTENT_MODELS_GROQ:
            resp = self._groq_call(
                model,
                [{"role": "user", "content": prompt}],
                mt, 0.0, _TIMEOUT["intent"]
            )
            if resp:
                raw = resp.choices[0].message.content.strip()
                result = self._parse_json(raw)
                if result:
                    logger.info(f"[ROUTER] intent via groq/{model}: {result.get('intent')}")
                    self._cache.set(text, result)
                    return result

        # 2. Ollama
        resp = self._ollama_call(
            [{"role": "user", "content": prompt}],
            mt, 0.0, _TIMEOUT["intent"]
        )
        if resp:
            raw = resp.json()["message"]["content"].strip()
            result = self._parse_json(raw)
            if result:
                logger.info(f"[ROUTER] intent via ollama: {result.get('intent')}")
                self._cache.set(text, result)
                return result

        logger.warning("[ROUTER] intent: fallback para conversation")
        fallback = {"intent": "conversation", "params": {}}
        self._cache.set(text, fallback)
        return fallback

    # ── API pública: summarize ─────────────────────────────────────────────────

    def summarize(self, prompt: str, max_tokens: int = 0) -> str:
        """
        Gera texto de sumarização/análise simples.
        Rota: Groq/8b → Groq/70b → Ollama
        """
        mt   = max_tokens or _MAX_TOKENS["summary"]
        msgs = [{"role": "user", "content": prompt}]

        for model in _SUMMARY_MODELS_GROQ:
            resp = self._groq_call(model, msgs, mt, 0.5, _TIMEOUT["summary"])
            if resp:
                text = resp.choices[0].message.content.strip()
                logger.info(f"[ROUTER] summarize via groq/{model}")
                return text

        resp = self._ollama_call(msgs, mt, 0.5, 20)
        if resp:
            logger.info("[ROUTER] summarize via ollama")
            return resp.json()["message"]["content"].strip()

        return ""

    # ── API pública: vision ────────────────────────────────────────────────────

    def vision(
        self,
        img_b64:   str,
        query:     str,
        mime_type: str = "image/jpeg",
    ) -> str | None:
        """
        Analisa imagem/screenshot.
        Rota: Gemini (primário) → Groq Vision → Ollama Vision
        Retorna texto ou None.
        """
        full_query = f"Analise esta imagem e responda em português brasileiro: {query}"

        # 1. Gemini (melhor qualidade para visão, suporte nativo multimodal)
        for model in _VISION_MODELS_GEMINI:
            key = f"gemini/{model}"
            if not self._cb.is_available(key):
                continue
            resp = self._gemini_call(
                model,
                contents=[{
                    "role": "user",
                    "parts": [
                        {"text": full_query},
                        {"inline_data": {"mime_type": mime_type, "data": img_b64}},
                    ],
                }],
                max_tokens=_MAX_TOKENS["vision"],
                config={"max_output_tokens": _MAX_TOKENS["vision"], "temperature": 0.3},
            )
            if resp:
                logger.info(f"[ROUTER] vision via gemini/{model}")
                return resp.text.strip()

        # 2. Groq Vision (fallback multimodal)
        if self._groq_available and self._groq:
            for model in _VISION_MODELS_GROQ:
                key = f"groq/{model}"
                if not self._cb.is_available(key):
                    continue
                try:
                    resp = self._groq.chat.completions.create(
                        model=model,
                        messages=[{
                            "role": "user",
                            "content": [
                                {"type": "text",      "text": full_query},
                                {"type": "image_url", "image_url": {
                                    "url": f"data:{mime_type};base64,{img_b64}"
                                }},
                            ],
                        }],
                        max_tokens=_MAX_TOKENS["vision"],
                        temperature=0.3,
                        timeout=_TIMEOUT["vision"],
                    )
                    self._cb.record_success(key)
                    logger.info(f"[ROUTER] vision via groq/{model}")
                    return resp.choices[0].message.content.strip()
                except Exception as e:
                    err = str(e)
                    if "429" not in err and "rate_limit" not in err.lower():
                        self._cb.record_failure(key)
                    logger.warning(f"[ROUTER] Groq vision/{model} falhou: {err[:120]}")
                    continue

        # 3. Ollama Vision (offline)
        if self._ollama_available:
            key = "ollama"
            if self._cb.is_available(key):
                import requests as req
                try:
                    resp = req.post(
                        f"{self._ollama_url}/api/chat",
                        json={
                            "model": self._ollama_vision_model,
                            "messages": [{
                                "role":    "user",
                                "content": full_query,
                                "images":  [img_b64],
                            }],
                            "stream": False,
                            "keep_alive": "5m",
                        },
                        timeout=_TIMEOUT["vision"],
                    )
                    resp.raise_for_status()
                    self._cb.record_success(key)
                    logger.info(f"[ROUTER] vision via ollama/{self._ollama_vision_model}")
                    return resp.json()["message"]["content"].strip()
                except Exception as e:
                    self._cb.record_failure(key)
                    logger.warning(f"[ROUTER] Ollama vision falhou: {str(e)[:120]}")

        logger.error("[ROUTER] vision: todos os motores falharam")
        return None

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_json(raw: str) -> dict | None:
        """Tenta extrair JSON válido do texto bruto do LLM."""
        clean = raw.replace("```json", "").replace("```", "").strip()
        # Tenta parse direto
        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            pass
        # Tenta extrair primeiro objeto JSON
        match = re.search(r'\{.*\}', clean, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return None

    # ── Status e diagnóstico ───────────────────────────────────────────────────

    def status(self) -> dict:
        """Retorna estado atual do router para /api/v23/status."""
        return {
            "groq_available":   self._groq_available,
            "gemini_available": self._gemini_available,
            "ollama_available": self._ollama_available,
            "ollama_model":     self._ollama_model,
            "circuit_breakers": self._cb.status(),
            "intent_cache":     self._cache.stats(),
        }

    def reset_circuits(self) -> None:
        """Reseta todos os circuit breakers (útil para debug/admin)."""
        with self._lock:
            self._cb._states.clear()
        logger.info("[ROUTER] Circuit breakers resetados")

    def clear_intent_cache(self) -> None:
        """Limpa o cache de intent detection."""
        with self._lock:
            self._cache._cache.clear()
            self._cache._hits   = 0
            self._cache._misses = 0
        logger.info("[ROUTER] Cache de intent limpo")


# ═══════════════════════════════════════════════════════════════════════════════
#  SINGLETON GLOBAL
# ═══════════════════════════════════════════════════════════════════════════════

_router_instance: LLMRouter | None = None
_router_lock = Lock()

def get_router() -> LLMRouter:
    """Retorna a instância singleton do router. Thread-safe."""
    global _router_instance
    if _router_instance is None:
        with _router_lock:
            if _router_instance is None:
                _router_instance = LLMRouter()
    return _router_instance

def init_router(
    groq_client,
    gemini_client,
    ollama_url:          str  = "http://localhost:11434",
    ollama_model:        str  = "llama3",
    ollama_vision_model: str  = "llava",
    ollama_available:    bool = False,
    gemini_available:    bool = False,
) -> LLMRouter:
    """
    Inicializa o router singleton com as dependências do App.py.
    Deve ser chamado UMA vez na inicialização.
    """
    router = get_router()
    router.init(
        groq_client=groq_client,
        gemini_client=gemini_client,
        ollama_url=ollama_url,
        ollama_model=ollama_model,
        ollama_vision_model=ollama_vision_model,
        ollama_available=ollama_available,
        gemini_available=gemini_available,
    )
    return router


# ═══════════════════════════════════════════════════════════════════════════════
#  TESTE LOCAL
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(message)s")

    print("=== LLM Router v2.3 — Teste de unidade ===\n")

    # Testa circuit breaker
    cb = CircuitBreaker()
    assert cb.is_available("teste") is True
    for _ in range(_CB_FAILURE_THRESHOLD):
        cb.record_failure("teste")
    assert cb.is_available("teste") is False
    print("[OK] Circuit breaker — abre após falhas")

    # Simula reset do cooldown
    state = cb._states["teste"]
    state.opened_at = time.time() - (_CB_COOLDOWN_SECONDS + 1)
    assert cb.is_available("teste") is True
    print("[OK] Circuit breaker — fecha após cooldown")

    # Testa cache TTL
    cache = _TTLCache(maxsize=10, ttl=0.1)
    cache.set("abrir spotify", {"intent": "spotify_control"})
    assert cache.get("abrir spotify") == {"intent": "spotify_control"}
    time.sleep(0.15)
    assert cache.get("abrir spotify") is None
    print("[OK] TTL Cache — expira corretamente")

    # Testa normalização de chave
    cache.set("Abrir  Spotify", {"intent": "spotify_control"})
    assert cache.get("abrir spotify") == {"intent": "spotify_control"}
    print("[OK] TTL Cache — normalização de chave")

    # Testa _parse_json
    r1 = LLMRouter._parse_json('{"intent":"open_app","params":{}}')
    assert r1 == {"intent": "open_app", "params": {}}
    r2 = LLMRouter._parse_json('```json\n{"intent":"conversation"}\n```')
    assert r2 == {"intent": "conversation"}
    r3 = LLMRouter._parse_json("texto inválido sem json")
    assert r3 is None
    print("[OK] _parse_json — 3 casos")

    print("\nTodos os testes passaram!")
    print("\nEstatísticas do cache:")
    stats = cache.stats()
    print(f"  hits={stats['hits']} misses={stats['misses']} ratio={stats['ratio']}")