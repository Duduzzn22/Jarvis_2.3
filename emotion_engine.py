"""
J.A.R.V.I.S. v2.3 — Emotion Engine
====================================
Detecta o sentimento/emoção da mensagem do usuário e emite evento
SocketIO para o frontend reagir no Orb em tempo real.

Pipeline:
  1. Análise rápida por heurísticas (regex + palavras-chave) — zero latência
  2. Fallback opcional via IA leve (transformers DistilBERT) — assíncrono

Emoções mapeadas → cor RGB do Orb + velocidade de animação:
  positivo  → verde        (0,255,136)   speed: 1.0
  animado   → dourado      (255,200,0)   speed: 1.4
  neutro    → azul ciano   (0,212,255)   speed: 1.0   (padrão)
  curioso   → roxo         (160,80,255)  speed: 0.9
  focado    → branco frio  (180,220,255) speed: 0.8
  frustrado → laranja      (255,120,0)   speed: 1.3
  irritado  → vermelho     (255,40,60)   speed: 1.6
  triste    → azul escuro  (0,80,180)    speed: 0.7
  estressado→ âmbar        (255,170,0)   speed: 1.5
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ─── Mapa de emoções → aparência do Orb ──────────────────────────────────────

@dataclass
class OrbState:
    """Estado visual do Orb correspondente a uma emoção."""
    emotion:  str
    color:    tuple[int, int, int]   # RGB
    speed:    float                  # multiplicador de velocidade de rotação
    pulse:    float                  # intensidade de pulso (0.5–2.0)
    label_pt: str                    # rótulo em português para a UI

ORB_STATES: dict[str, OrbState] = {
    "positivo":   OrbState("positivo",   (0,   255, 136), 1.0, 1.1, "Positivo"),
    "animado":    OrbState("animado",    (255, 200,   0), 1.4, 1.5, "Animado"),
    "neutro":     OrbState("neutro",     (0,   212, 255), 1.0, 1.0, "Neutro"),
    "curioso":    OrbState("curioso",    (160,  80, 255), 0.9, 1.0, "Curioso"),
    "focado":     OrbState("focado",     (180, 220, 255), 0.8, 0.8, "Focado"),
    "frustrado":  OrbState("frustrado",  (255, 120,   0), 1.3, 1.4, "Frustrado"),
    "irritado":   OrbState("irritado",   (255,  40,  60), 1.6, 1.8, "Irritado"),
    "triste":     OrbState("triste",     (0,    80, 180), 0.7, 0.7, "Triste"),
    "estressado": OrbState("estressado", (255, 170,   0), 1.5, 1.6, "Estressado"),
}

DEFAULT_EMOTION = "neutro"

# ─── Regras heurísticas por emoção ────────────────────────────────────────────

_RULES: list[tuple[str, list[str]]] = [
    ("irritado", [
        r"\bidiota\b", r"\bburro\b", r"\bmerda\b", r"\bporra\b", r"\bdroga\b",
        r"\braiva\b", r"\bódio\b", r"\bfuncionando\b.{0,20}\bnão\b",
        r"que\s+(lixo|bosta|droga|absurdo)", r"\bhorr[íi]vel\b",
    ]),
    ("frustrado", [
        r"\bfrustrad\w+\b", r"\bnão funciona\b", r"\bpor que não\b",
        r"\bde novo\b.{0,15}\bproblem\w+\b", r"\bcansei\b", r"\bimpossível\b",
        r"\btravad\w+\b", r"\bbugad\w+\b", r"\berro\b.{0,20}\bnovamente\b",
    ]),
    ("estressado", [
        r"\burgente\b", r"\bpreciso agora\b", r"\bcorrendo\b", r"\bprazo\b",
        r"\bentrega\b.{0,15}\bhoje\b", r"\btard[eo]\b.{0,15}\b(demais|muito)\b",
        r"\bstressad\w+\b", r"\bansios\w+\b",
    ]),
    ("animado", [
        r"\bincrível\b", r"\bfantástico\b", r"\bshow\b", r"\bperfeito\b",
        r"\bamazing\b", r"\bgenial\b", r"\bexcelente\b", r"\bmuito bom\b",
        r"[!]{2,}", r"\blegal\b", r"\bsensacional\b", r"\bfoda\b",
    ]),
    ("positivo", [
        r"\bobrigad\w+\b", r"\bvaleu\b", r"\bthank\w*\b", r"\bcerto\b",
        r"\bconseguiu\b", r"\bfuncionou\b", r"\bperfeito\b", r"\bottim\w+\b",
        r"\bbom dia\b", r"\bboa tarde\b", r"\bboa noite\b",
    ]),
    ("curioso", [
        r"\bcom[oo]\b.{0,20}\bfunciona\b", r"\bpor que\b", r"\bexplica\b",
        r"\bme conta\b", r"\bcurioso\b", r"\bgostaria de saber\b",
        r"\bme diz\b", r"\bsabia que\b",
    ]),
    ("triste", [
        r"\btriste\b", r"\bmal\b", r"\bdeprimid\w+\b", r"\bchateado\b",
        r"\bdesiludidd\w+\b", r"\bnão deu certo\b", r"\bperdeu\b",
        r"\bpreocupad\w+\b", r"\bsaudade\b",
    ]),
    ("focado", [
        r"\bprecisos\b", r"\btarefa\b", r"\bpomodoro\b", r"\btrabalhando\b",
        r"\bcodando\b", r"\bprogramando\b", r"\bestudando\b", r"\bfocad\w+\b",
        r"\bprodutiv\w+\b",
    ]),
]

# Pré-compila os padrões para performance
_COMPILED_RULES: list[tuple[str, list[re.Pattern]]] = [
    (emotion, [re.compile(p, re.IGNORECASE) for p in patterns])
    for emotion, patterns in _RULES
]

# ─── Detector heurístico (síncrono, zero latência) ───────────────────────────

def _heuristic_detect(text: str) -> tuple[str, float]:
    """
    Detecta emoção por padrões regex.
    Retorna (emoção, confiança 0.0–1.0).
    Quanto mais padrões batem, maior a confiança.
    """
    scores: dict[str, int] = {}
    for emotion, patterns in _COMPILED_RULES:
        hits = sum(1 for p in patterns if p.search(text))
        if hits > 0:
            scores[emotion] = hits

    if not scores:
        return DEFAULT_EMOTION, 0.5

    best_emotion = max(scores, key=scores.get)
    max_hits     = scores[best_emotion]
    total_patterns = next(
        len(patterns) for e, patterns in _COMPILED_RULES if e == best_emotion
    )
    confidence = min(0.95, 0.5 + (max_hits / total_patterns) * 0.5)
    return best_emotion, confidence

# ─── API pública ──────────────────────────────────────────────────────────────

def detect_emotion(text: str) -> dict:
    """
    Detecta emoção do texto e retorna dados prontos para emitir via SocketIO.

    Retorna dict com:
        emotion   str   — nome da emoção em inglês/código
        label_pt  str   — rótulo em português
        color     list  — [R, G, B]
        speed     float — multiplicador de velocidade do Orb
        pulse     float — intensidade de pulso
        confidence float — confiança da detecção (0.0–1.0)
    """
    emotion, confidence = _heuristic_detect(text)
    state = ORB_STATES.get(emotion, ORB_STATES[DEFAULT_EMOTION])

    result = {
        "emotion":    state.emotion,
        "label_pt":   state.label_pt,
        "color":      list(state.color),
        "speed":      state.speed,
        "pulse":      state.pulse,
        "confidence": round(confidence, 2),
    }
    logger.debug(f"[EMOTION] '{text[:50]}' → {emotion} ({confidence:.0%})")
    return result

def get_orb_state(emotion: str) -> OrbState:
    """Retorna o OrbState para uma emoção. Fallback para neutro."""
    return ORB_STATES.get(emotion, ORB_STATES[DEFAULT_EMOTION])

def get_humor_injection(emotion: str) -> str:
    """
    Retorna um bloco de instrução extra para o system prompt
    baseado na emoção detectada — sutil, não invasivo.
    """
    injections: dict[str, str] = {
        "irritado":   "\n\n## ESTADO EMOCIONAL DO SENHOR\nO Senhor parece irritado. Seja extra paciente, direto e evite piadas. Resolva o problema com eficiência máxima.",
        "frustrado":  "\n\n## ESTADO EMOCIONAL DO SENHOR\nO Senhor parece frustrado. Seja empático, valide o problema e ofereça solução prática imediatamente.",
        "estressado": "\n\n## ESTADO EMOCIONAL DO SENHOR\nO Senhor parece estressado. Seja conciso, priorize a solução e ofereça ajuda proativa.",
        "triste":     "\n\n## ESTADO EMOCIONAL DO SENHOR\nO Senhor parece abatido. Use tom gentil e encorajador, sem exageros.",
        "animado":    "\n\n## ESTADO EMOCIONAL DO SENHOR\nO Senhor está animado. Corresponda à energia com entusiasmo moderado.",
        "positivo":   "",  # Não injeta nada — deixa fluir naturalmente
        "neutro":     "",
        "curioso":    "",
        "focado":     "\n\n## ESTADO EMOCIONAL DO SENHOR\nO Senhor está focado em trabalho. Seja extremamente conciso e útil. Minimize conversas.",
    }
    return injections.get(emotion, "")

# ─── Integração com SocketIO ──────────────────────────────────────────────────

def emit_emotion_event(text: str, socketio_instance, sid: str) -> dict:
    """
    Detecta emoção e emite evento 'emotion_detected' ao frontend.
    Retorna o resultado da detecção.

    Uso em App.py:
        from emotion_engine import emit_emotion_event
        emotion_data = emit_emotion_event(text, socketio, sid)
    """
    try:
        result = detect_emotion(text)
        socketio_instance.emit("emotion_detected", result, room=sid)
        logger.info(f"[EMOTION] Emitido: {result['emotion']} ({result['confidence']:.0%})")
        return result
    except Exception as e:
        logger.error(f"[EMOTION] Erro ao emitir evento: {e}")
        return detect_emotion("")  # retorna neutro como fallback


# ─── Teste local ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    testes = [
        "Isso não está funcionando de jeito nenhum! Que merda.",
        "Incrível! Funcionou perfeitamente! Você é sensacional!",
        "Bom dia Jarvis, como você está hoje?",
        "Preciso entregar isso urgente, prazo é hoje!",
        "Estou triste, as coisas não estão dando certo.",
        "Pode me explicar como funciona esse algoritmo?",
        "Estou codando aqui, foco total no trabalho.",
        "Preciso enviar um email para o cliente.",
    ]
    print("=== Emotion Engine — Teste ===\n")
    for t in testes:
        r = detect_emotion(t)
        bar = "█" * int(r["confidence"] * 20)
        print(f"  '{t[:50]}'")
        print(f"  → {r['emotion']:12s} | conf: {bar:<20} {r['confidence']:.0%}")
        print(f"     RGB: {r['color']}  speed: {r['speed']}  pulse: {r['pulse']}")
        print()