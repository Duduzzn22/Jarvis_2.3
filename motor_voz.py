"""
J.A.R.V.I.S. — Motor de Voz com Clonagem
Engine: F5-TTS (clonagem zero-shot, Python 3.12+)

Usa os 3 arquivos borgerth_0x.wav como referência para clonagem.
Se F5-TTS falhar, App.py cai no edge-tts automaticamente.

INSTALAÇÃO:
    pip install f5-tts soundfile

TESTE:
    python motor_voz.py "Senhor, sistemas online."
"""

import os
import base64
import tempfile
import hashlib
from pathlib import Path

_BASE_DIR = Path(__file__).parent

VOZES_REFERENCIA = [
    str(_BASE_DIR / "borgerth_01.wav"),
    str(_BASE_DIR / "borgerth_02.wav"),
    str(_BASE_DIR / "borgerth_03.wav"),
]

_cache: dict = {}

# ─── F5-TTS ───────────────────────────────────────────────────────────────────

_f5_model  = None
_f5_loaded = False
_f5_error  = None


def _carregar_f5():
    global _f5_model, _f5_loaded, _f5_error

    if _f5_loaded:
        return True
    if _f5_error:
        return False

    try:
        print("[JARVIS-VOZ] Carregando F5-TTS... (1ª vez baixa ~3 GB de modelo)")
        from f5_tts.api import F5TTS
        _f5_model  = F5TTS()
        _f5_loaded = True
        print("[JARVIS-VOZ] ✅ F5-TTS carregado!")
        return True
    except Exception as e:
        _f5_error = str(e)
        print(f"[JARVIS-VOZ] ⚠ F5-TTS indisponível: {e}")
        return False


def gerar_fala_jarvis(texto: str, usar_cache: bool = True):
    """
    Gera fala clonada usando F5-TTS e retorna base64 WAV.
    Retorna None se falhar → App.py usa edge-tts como fallback.
    """
    if not texto or not texto.strip():
        return None

    chave = hashlib.md5(texto.encode()).hexdigest()
    if usar_cache and chave in _cache:
        print("[JARVIS-VOZ] ✅ Cache hit")
        return _cache[chave]

    ref = next((r for r in VOZES_REFERENCIA if Path(r).exists()), None)
    if ref is None:
        print(
            "[JARVIS-VOZ] ⚠ Nenhum WAV de referência encontrado!\n"
            f"  Esperados em: {_BASE_DIR}\n"
            "  Arquivos: borgerth_01.wav / borgerth_02.wav / borgerth_03.wav"
        )
        return None

    if not _carregar_f5():
        return None

    label = f"'{texto[:55]}...'" if len(texto) > 55 else f"'{texto}'"
    print(f"[JARVIS-VOZ] Sintetizando: {label}")

    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp = f.name

        _f5_model.infer(
            ref_file=ref,
            ref_text="",      # F5-TTS transcreve o áudio de referência automaticamente
            gen_text=texto,
            file_wave=tmp,
            remove_silence=True,
            speed=1.0,
        )

        with open(tmp, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        os.unlink(tmp)

        if usar_cache:
            _cache[chave] = b64
            if len(_cache) > 50:
                _cache.pop(next(iter(_cache)))

        print("[JARVIS-VOZ] ✅ Áudio gerado com sucesso")
        return b64

    except Exception as e:
        print(f"[JARVIS-VOZ] ❌ Erro na síntese: {e}")
        return None


# ─── TESTE LOCAL ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    texto = (
        sys.argv[1] if len(sys.argv) > 1
        else "Senhor, os sistemas estão online e a armadura está pronta para testes."
    )

    print(f"\n🎙 Teste de síntese de voz — F5-TTS")
    print(f"   Texto : {texto}")
    print(f"   Pasta : {_BASE_DIR}")
    print(f"   Referências:")
    for r in VOZES_REFERENCIA:
        status = "✅" if Path(r).exists() else "❌ NÃO ENCONTRADO"
        print(f"     {status}  {Path(r).name}")
    print()

    audio_b64 = gerar_fala_jarvis(texto, usar_cache=False)

    if audio_b64:
        output = Path("teste_voz_output.wav")
        output.write_bytes(base64.b64decode(audio_b64))
        print(f"\n✅ Salvo em: {output.resolve()}")
        print("   Abra o arquivo para ouvir a voz clonada!")
    else:
        print("\n❌ Falha na síntese.")
        print("   Verifique: pip install f5-tts soundfile")
