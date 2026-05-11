"""
J.A.R.V.I.S. — Verificador e Instalador de Dependências
Execute este script UMA VEZ antes de tudo.
Ele identifica o que está faltando e instala automaticamente.
"""

import sys
import os
import subprocess
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.resolve()

CYAN   = '\033[96m'
GREEN  = '\033[92m'
RED    = '\033[91m'
YELLOW = '\033[93m'
RESET  = '\033[0m'
BOLD   = '\033[1m'
DIM    = '\033[2m'

def ok(msg):   print(f"  {GREEN}✓{RESET} {msg}")
def err(msg):  print(f"  {RED}✗{RESET} {msg}")
def warn(msg): print(f"  {YELLOW}!{RESET} {msg}")
def info(msg): print(f"  {CYAN}→{RESET} {msg}")

# ─── DEPENDÊNCIAS NECESSÁRIAS ─────────────────────────────────────────────────

# (nome_de_import, pacote_pip, obrigatório)
DEPENDENCIES = [
    ("flask",           "flask",              True),
    ("flask_socketio",  "flask-socketio",     True),
    ("dotenv",          "python-dotenv",      True),
    ("psutil",          "psutil",             True),
    ("google.genai",    "google-genai",       True),
    ("groq",            "groq",               True),
    ("edge_tts",        "edge-tts",           True),
    ("pyautogui",       "pyautogui",          True),
    ("PIL",             "pillow",             True),
    ("requests",        "requests",           True),
    ("speech_recognition", "SpeechRecognition", True),
    ("pyaudio",         "pyaudio",            True),
    ("schedule",        "schedule",           True),
    ("keyboard",        "keyboard",           False),  # opcional — fallback F8
]

def check_import(module_name: str) -> bool:
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False

def pip_install(package: str) -> bool:
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", package, "--quiet"],
        capture_output=True, text=True
    )
    return result.returncode == 0

# ─── VERIFICAÇÃO DE ARQUIVOS LOCAIS ───────────────────────────────────────────

LOCAL_MODULES = ["memory.py", "personalities.py", "scheduler.py", "App.py", "index.html"]
OPTIONAL_FILES = ["SOUL.md", ".env", "_env"]

def check_files():
    print(f"\n{BOLD}{CYAN}[1/3] Arquivos do projeto{RESET}")
    all_ok = True
    for fname in LOCAL_MODULES:
        path = PROJECT_DIR / fname
        if path.exists():
            ok(fname)
        else:
            err(f"{fname}  ← NÃO ENCONTRADO em {PROJECT_DIR}")
            all_ok = False

    print()
    for fname in OPTIONAL_FILES:
        path = PROJECT_DIR / fname
        if path.exists():
            ok(f"{fname}  (opcional)")
        else:
            warn(f"{fname}  (opcional — não encontrado)")

    if not (PROJECT_DIR / ".env").exists() and not (PROJECT_DIR / "_env").exists():
        print()
        warn("Nenhum arquivo .env encontrado!")
        warn("Crie um arquivo .env com suas chaves de API:")
        print(f"  {DIM}GEMINI_API_KEY=sua_chave_aqui")
        print(f"  GROQ_API_KEY=sua_chave_aqui{RESET}")

    return all_ok

# ─── VERIFICAÇÃO E INSTALAÇÃO DE PACOTES ──────────────────────────────────────

def check_and_install():
    print(f"\n{BOLD}{CYAN}[2/3] Dependências Python{RESET}")

    missing = []
    for module, package, required in DEPENDENCIES:
        if check_import(module):
            ok(f"{package}")
        else:
            label = "obrigatório" if required else "opcional"
            warn(f"{package}  ← FALTANDO ({label})")
            if required:
                missing.append((module, package))

    if not missing:
        print(f"\n  {GREEN}Todas as dependências obrigatórias estão instaladas!{RESET}")
        return True

    print(f"\n  {YELLOW}Encontradas {len(missing)} dependências faltando.{RESET}")
    resp = input(f"  {BOLD}Instalar automaticamente agora? (S/n): {RESET}").strip().lower()
    if resp in ('n', 'nao', 'não'):
        print()
        print("  Para instalar manualmente, execute:")
        pkgs = " ".join(p for _, p in missing)
        print(f"  {DIM}pip install {pkgs}{RESET}")
        return False

    print()
    failed = []
    for module, package in missing:
        info(f"Instalando {package}...")
        if pip_install(package):
            ok(f"{package} instalado!")
        else:
            # Tenta alternativa para pyaudio no Windows
            if package == "pyaudio" and sys.platform == "win32":
                info("Tentando instalação alternativa do pyaudio...")
                r = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "pipwin", "--quiet"],
                    capture_output=True
                )
                r2 = subprocess.run(
                    [sys.executable, "-m", "pipwin", "install", "pyaudio"],
                    capture_output=True
                )
                if r2.returncode == 0:
                    ok("pyaudio instalado via pipwin!")
                    continue
            err(f"Falha ao instalar {package}")
            failed.append(package)

    if failed:
        print()
        warn(f"Não foi possível instalar automaticamente: {', '.join(failed)}")
        warn("Tente instalar manualmente:")
        print(f"  {DIM}pip install {' '.join(failed)}{RESET}")
        return False

    return True

# ─── TESTE DO MICROFONE ───────────────────────────────────────────────────────

def check_microphone():
    print(f"\n{BOLD}{CYAN}[3/3] Microfone{RESET}")

    try:
        import speech_recognition as sr
        mics = sr.Microphone.list_microphone_names()
        if not mics:
            err("Nenhum microfone encontrado!")
            warn("Conecte um microfone e tente novamente.")
            return False

        ok(f"{len(mics)} microfone(s) encontrado(s):")
        for i, name in enumerate(mics[:5]):
            print(f"    {DIM}[{i}] {name}{RESET}")
        if len(mics) > 5:
            print(f"    {DIM}... e mais {len(mics)-5}{RESET}")

        # Teste rápido de captura
        print()
        info("Testando captura de áudio por 3 segundos...")
        info("Fale algo após o beep...")
        try:
            import winsound
            winsound.Beep(800, 200)
        except:
            pass

        r = sr.Recognizer()
        r.energy_threshold = 400
        r.dynamic_energy_threshold = True
        with sr.Microphone() as source:
            try:
                audio = r.listen(source, timeout=3, phrase_time_limit=3)
                try:
                    text = r.recognize_google(audio, language='pt-BR')
                    ok(f"Microfone OK! Ouvido: '{text}'")
                except sr.UnknownValueError:
                    ok("Microfone OK! (áudio capturado, fala não reconhecida)")
                except sr.RequestError:
                    warn("Microfone OK, mas sem internet para reconhecimento.")
            except sr.WaitTimeoutError:
                warn("Nenhuma fala detectada em 3s — mas microfone está aberto.")
                warn("Isso é normal se você não falou nada.")
        return True

    except Exception as e:
        err(f"Erro ao testar microfone: {e}")
        if "Access is denied" in str(e) or "Permission" in str(e):
            warn("Windows bloqueou o acesso ao microfone!")
            warn("Acesse: Configurações → Privacidade → Microfone")
            warn("E ative: 'Permitir que apps de desktop acessem o microfone'")
        return False

# ─── TESTE DO APP.PY ──────────────────────────────────────────────────────────

def test_app_import():
    print(f"\n{BOLD}{CYAN}[BÔNUS] Testando importação do App.py{RESET}")
    app_path = PROJECT_DIR / "App.py"
    if not app_path.exists():
        warn("App.py não encontrado — pulando teste.")
        return

    result = subprocess.run(
        [sys.executable, "-c",
         f"import sys; sys.path.insert(0,r'{PROJECT_DIR}'); "
         "import importlib.util; "
         f"spec = importlib.util.spec_from_file_location('App', r'{app_path}'); "
         # Só verifica imports, não executa o servidor
         ],
        capture_output=True, text=True, timeout=15,
        cwd=str(PROJECT_DIR)
    )

    # Verifica se há erros de import conhecidos no App.py
    info("Verificando imports do App.py...")
    check_result = subprocess.run(
        [sys.executable, "-c",
         "import ast, sys\n"
         f"code = open(r'{app_path}', encoding='utf-8').read()\n"
         "tree = ast.parse(code)\n"
         "imports = []\n"
         "for node in ast.walk(tree):\n"
         "    if isinstance(node, ast.Import):\n"
         "        for alias in node.names: imports.append(alias.name.split('.')[0])\n"
         "    elif isinstance(node, ast.ImportFrom):\n"
         "        if node.module: imports.append(node.module.split('.')[0])\n"
         "imports = sorted(set(imports))\n"
         "failed = []\n"
         "for m in imports:\n"
         "    try: __import__(m)\n"
         "    except ImportError: failed.append(m)\n"
         "if failed:\n"
         "    print('FALTANDO:' + ','.join(failed))\n"
         "else:\n"
         "    print('OK')\n"
        ],
        capture_output=True, text=True, timeout=15,
        cwd=str(PROJECT_DIR)
    )

    output = check_result.stdout.strip()
    if output == "OK":
        ok("Todos os imports do App.py estão disponíveis!")
    elif output.startswith("FALTANDO:"):
        missing = output.replace("FALTANDO:", "").split(",")
        # Filtra módulos locais (são arquivos .py do projeto)
        local = {"memory", "personalities", "scheduler", "motor_voz", "profile_setup"}
        real_missing = [m for m in missing if m not in local and m not in sys.stdlib_module_names]
        if real_missing:
            err(f"Imports não resolvidos no App.py: {', '.join(real_missing)}")
        else:
            ok("App.py OK — todos os imports externos estão disponíveis.")
    else:
        warn(f"Resultado inesperado: {output}")

# ─── RESUMO FINAL ─────────────────────────────────────────────────────────────

def print_summary():
    print(f"\n{'═'*52}")
    print(f"{BOLD}{CYAN}  PRÓXIMOS PASSOS{RESET}")
    print(f"{'═'*52}")
    print(f"""
  1. {BOLD}Configure o .env{RESET} (se ainda não fez):
     {DIM}GEMINI_API_KEY=sua_chave
     GROQ_API_KEY=sua_chave{RESET}

  2. {BOLD}Teste o servidor manualmente:{RESET}
     {DIM}python App.py{RESET}
     → Deve aparecer: "Acesse: http://localhost:5000"

  3. {BOLD}Se o servidor subiu, teste o wake word:{RESET}
     {DIM}python wake_word.py{RESET}
     → Fale: "hora de acordar" ou "hey jarvis"

  4. {BOLD}Para iniciar automaticamente com Windows:{RESET}
     {DIM}execute instalar_servicos.bat como Administrador{RESET}
""")
    print(f"{'═'*52}\n")

# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'═'*52}")
    print(f"{BOLD}{CYAN}  J.A.R.V.I.S. — DIAGNÓSTICO COMPLETO{RESET}")
    print(f"  Pasta: {PROJECT_DIR}")
    print(f"  Python: {sys.version.split()[0]}")
    print(f"{'═'*52}")

    files_ok = check_files()
    deps_ok  = check_and_install()
    mic_ok   = check_microphone()

    if deps_ok:
        test_app_import()

    print_summary()

    status = all([files_ok, deps_ok, mic_ok])
    if status:
        print(f"  {GREEN}{BOLD}Sistema pronto! Execute: python App.py{RESET}\n")
    else:
        print(f"  {YELLOW}{BOLD}Resolva os itens marcados com ✗ antes de continuar.{RESET}\n")

    input("  Pressione ENTER para sair...")

if __name__ == "__main__":
    main()