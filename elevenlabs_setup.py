"""
J.A.R.V.I.S. — ElevenLabs Multi-Voice Setup
Clona uma ou mais vozes e salva os voice_ids no .env

Uso:
    python elevenlabs_setup.py              # wizard interativo
    python elevenlabs_setup.py --list       # lista vozes clonadas na conta
    python elevenlabs_setup.py --test       # testa todas as vozes salvas no .env
    python elevenlabs_setup.py --delete ID  # deleta uma voz pelo voice_id
"""

import os, sys, json, base64, requests
from pathlib import Path
from dotenv import load_dotenv, set_key

CYAN='\033[96m'; GREEN='\033[92m'; RED='\033[91m'
YELLOW='\033[93m'; BOLD='\033[1m'; DIM='\033[2m'; RESET='\033[0m'

def ok(m):   print(f"  {GREEN}✓{RESET} {m}")
def err(m):  print(f"  {RED}✗{RESET} {m}")
def info(m): print(f"  {CYAN}→{RESET} {m}")
def warn(m): print(f"  {YELLOW}!{RESET} {m}")

PROJECT_DIR     = Path(__file__).parent.resolve()
ELEVENLABS_BASE = 'https://api.elevenlabs.io/v1'

PERSONALITIES = {
    'jarvis':     'ELEVENLABS_VOICE_JARVIS',
    'cientista':  'ELEVENLABS_VOICE_CIENTISTA',
    'guerreiro':  'ELEVENLABS_VOICE_GUERREIRO',
    'zen':        'ELEVENLABS_VOICE_ZEN',
    'sarcastico': 'ELEVENLABS_VOICE_EDITH',
    'ator':       'ELEVENLABS_VOICE_ATOR',
    'detetive':   'ELEVENLABS_VOICE_DETETIVE',
    'ultron':     'ELEVENLABS_VOICE_ULTRON',
}

ENV_FILE = None
for candidate in ['.env', '_env']:
    p = PROJECT_DIR / candidate
    if p.exists():
        load_dotenv(p); ENV_FILE = str(p); break
if not ENV_FILE:
    load_dotenv(); ENV_FILE = str(PROJECT_DIR / '.env')

def get_api_key():
    key = os.getenv('ELEVENLABS_API_KEY', '').strip()
    if not key:
        print(f"\n  {YELLOW}ELEVENLABS_API_KEY não encontrada no .env{RESET}")
        key = input(f"  {CYAN}Cole sua API key do ElevenLabs:{RESET} ").strip()
        if key:
            set_key(ENV_FILE, 'ELEVENLABS_API_KEY', key)
            ok(f"Chave salva em {ENV_FILE}")
    return key

def check_quota(api_key):
    try:
        r = requests.get(f'{ELEVENLABS_BASE}/user/subscription',
                         headers={'xi-api-key': api_key}, timeout=10)
        if r.status_code == 200:
            s = r.json()
            used=s.get('character_count',0); lim=s.get('character_limit',0)
            print(f"  {DIM}Plano: {s.get('tier','?')} | Caracteres: {used:,}/{lim:,} | Restantes: {lim-used:,}{RESET}")
    except Exception: pass

def list_cloned_voices(api_key):
    try:
        r = requests.get(f'{ELEVENLABS_BASE}/voices',
                         headers={'xi-api-key': api_key}, timeout=15)
        if r.status_code == 200:
            return [v for v in r.json().get('voices',[])
                    if v.get('category') in ('cloned','professional')]
    except Exception as e: warn(f"Erro ao listar vozes: {e}")
    return []

def find_voice_by_name(api_key, name):
    for v in list_cloned_voices(api_key):
        if v.get('name') == name: return v['voice_id']
    return None

def clone_voice(api_key, samples, name, description=''):
    files = []
    for path in samples:
        if path.exists():
            files.append(('files', (path.name, open(path,'rb'), 'audio/wav')))
        else:
            warn(f"Arquivo não encontrado: {path.name}")
    if not files:
        raise RuntimeError("Nenhum arquivo WAV válido encontrado.")
    data = {
        'name': name,
        'description': description or f'Voz J.A.R.V.I.S. — {name}',
        'labels': json.dumps({'language':'pt','jarvis':'true'}),
    }
    info(f"Enviando {len(files)} arquivo(s) → '{name}'...")
    r = requests.post(f'{ELEVENLABS_BASE}/voices/add',
                      headers={'xi-api-key': api_key},
                      data=data, files=files, timeout=60)
    for _,(_, f, _) in files: f.close()
    if r.status_code == 200:
        vid = r.json()['voice_id']
        ok(f"Voz criada | voice_id: {vid}"); return vid
    raise RuntimeError(f"ElevenLabs {r.status_code}: {r.text[:300]}")

def delete_voice(api_key, voice_id):
    r = requests.delete(f'{ELEVENLABS_BASE}/voices/{voice_id}',
                        headers={'xi-api-key': api_key}, timeout=10)
    return r.status_code == 200

def test_voice_id(api_key, voice_id, label=''):
    r = requests.post(
        f'{ELEVENLABS_BASE}/text-to-speech/{voice_id}',
        headers={'xi-api-key':api_key,'Content-Type':'application/json','Accept':'audio/mpeg'},
        json={
            'text': 'Senhor, todos os sistemas do J.A.R.V.I.S. estão operacionais. Voz ativa.',
            'model_id': 'eleven_multilingual_v2',
            'voice_settings': {'stability':0.55,'similarity_boost':0.85,
                               'style':0.20,'use_speaker_boost':True},
        }, timeout=30)
    if r.status_code == 200:
        fname = f"test_{label or voice_id[:8]}.mp3"
        (PROJECT_DIR / fname).write_bytes(r.content)
        ok(f"Teste salvo: {fname}"); return True
    warn(f"Teste falhou {r.status_code}: {r.text[:100]}"); return False

def _save_voice(env_key, voice_id, voice_name, api_key):
    current_default = os.getenv('ELEVENLABS_VOICE_ID','')
    if not current_default:
        set_key(ENV_FILE,'ELEVENLABS_VOICE_ID', voice_id)
        ok(f"ELEVENLABS_VOICE_ID={voice_id} (voz padrão)")
    if env_key:
        set_key(ENV_FILE, env_key, voice_id)
        ok(f"{env_key}={voice_id}")
    if current_default and current_default != voice_id:
        resp = input(f"  {CYAN}Tornar essa a voz padrão? (s/N):{RESET} ").strip().lower()
        if resp == 's':
            set_key(ENV_FILE,'ELEVENLABS_VOICE_ID', voice_id)
            ok(f"ELEVENLABS_VOICE_ID atualizado")
    resp = input(f"  {CYAN}Gerar MP3 de teste? (S/n):{RESET} ").strip().lower()
    if resp != 'n':
        test_voice_id(api_key, voice_id, voice_name.lower().replace(' ','_'))

def wizard_clone(api_key):
    print(f"\n  {BOLD}Qual personalidade receberá essa voz?{RESET}")
    pers_list = list(PERSONALITIES.keys())
    for i, p in enumerate(pers_list):
        current = os.getenv(PERSONALITIES[p],'')
        status  = f"{GREEN}✓ configurada{RESET}" if current else f"{DIM}sem voz{RESET}"
        print(f"    {CYAN}{i+1}{RESET}. {p:<14} {status}")
    print(f"    {CYAN}{len(pers_list)+1}{RESET}. Criar voz sem associar personalidade")

    while True:
        choice = input(f"\n  {CYAN}Escolha [1-{len(pers_list)+1}]:{RESET} ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(pers_list)+1:
            idx = int(choice)-1; break
        warn("Opção inválida.")

    if idx < len(pers_list):
        personality = pers_list[idx]
        env_key     = PERSONALITIES[personality]
        voice_name  = f'JARVIS-{personality.title()}'
    else:
        personality = None; env_key = None
        voice_name  = input(f"  {CYAN}Nome para a voz:{RESET} ").strip() or 'JARVIS-Custom'

    existing = find_voice_by_name(api_key, voice_name)
    if existing:
        warn(f"Voz '{voice_name}' já existe (voice_id: {existing})")
        resp = input(f"  {CYAN}Recriar do zero? (s/N):{RESET} ").strip().lower()
        if resp == 's':
            info("Deletando voz antiga..."); delete_voice(api_key, existing)
        else:
            _save_voice(env_key, existing, voice_name, api_key); return

    # Coleta arquivos
    print(f"\n  {BOLD}Arquivos WAV de referência{RESET}")
    samples = []
    default_samples = [PROJECT_DIR/f'borgerth_0{i}.wav' for i in range(1,4)]
    defaults_exist  = [p for p in default_samples if p.exists()]

    if defaults_exist:
        print(f"  Arquivos encontrados na pasta:")
        for p in defaults_exist: print(f"    {DIM}{p.name}{RESET}")
        use = input(f"  {CYAN}Usar esses arquivos? (S/n):{RESET} ").strip().lower()
        if use != 'n': samples = defaults_exist

    if not samples:
        i = 1
        while True:
            fname = input(f"  {CYAN}Arquivo {i} (Enter p/ terminar):{RESET} ").strip()
            if not fname: break
            p = PROJECT_DIR / fname
            if p.exists(): samples.append(p); ok(fname); i+=1
            else: warn(f"'{fname}' não encontrado.")

    if not samples: err("Nenhum arquivo informado."); return

    try:
        voice_id = clone_voice(api_key, samples, voice_name)
    except RuntimeError as e:
        err(str(e)); return

    _save_voice(env_key, voice_id, voice_name, api_key)

def cmd_list(api_key):
    print(f"\n  {BOLD}Vozes clonadas na sua conta:{RESET}\n")
    voices = list_cloned_voices(api_key)
    if not voices: warn("Nenhuma voz clonada."); return
    all_env_keys = list(PERSONALITIES.values()) + ['ELEVENLABS_VOICE_ID']
    for v in voices:
        vid  = v['voice_id']; name = v['name']
        in_env = any(os.getenv(k,'') == vid for k in all_env_keys)
        marker = f"{GREEN}● no .env{RESET}" if in_env else f"{DIM}○{RESET}"
        print(f"  {CYAN}{name:<28}{RESET} {DIM}{vid}{RESET}  {marker}")

def cmd_test(api_key):
    print(f"\n  {BOLD}Testando vozes configuradas:{RESET}\n")
    tested = set()
    default = os.getenv('ELEVENLABS_VOICE_ID','')
    if default and default not in tested:
        info(f"Padrão ({default[:8]}...)"); test_voice_id(api_key,default,'default'); tested.add(default)
    for p, k in PERSONALITIES.items():
        vid = os.getenv(k,'')
        if vid and vid not in tested:
            info(f"{p} ({vid[:8]}...)"); test_voice_id(api_key,vid,p); tested.add(vid)
    if not tested: warn("Nenhuma voz configurada. Rode o setup primeiro.")

def cmd_delete(api_key, voice_id):
    if not voice_id: err("Informe o voice_id: python elevenlabs_setup.py --delete ID"); return
    info(f"Deletando {voice_id}...")
    if delete_voice(api_key, voice_id):
        ok("Voz deletada.")
        for k in list(PERSONALITIES.values()) + ['ELEVENLABS_VOICE_ID']:
            if os.getenv(k,'') == voice_id:
                set_key(ENV_FILE, k, ''); warn(f"{k} removida do .env")
    else: err("Falha ao deletar.")

def print_summary():
    print(f"\n  {BOLD}Vozes configuradas no .env:{RESET}")
    default = os.getenv('ELEVENLABS_VOICE_ID','')
    if default: print(f"  Padrão:  {CYAN}{default}{RESET}")
    for p, k in PERSONALITIES.items():
        v = os.getenv(k,'')
        if v:
            mark = f" {DIM}(= padrão){RESET}" if v==default else ''
            print(f"  {p:<14} {CYAN}{v}{mark}{RESET}")
    print(f"\n  Reinicie o {BOLD}App.py{RESET} para aplicar.\n")

def main():
    args = sys.argv[1:]
    print(f"\n{'═'*54}")
    print(f"{BOLD}{CYAN}  J.A.R.V.I.S. — ELEVENLABS MULTI-VOICE SETUP{RESET}")
    print(f"{'═'*54}\n")
    api_key = get_api_key()
    if not api_key: err("API key necessária."); sys.exit(1)
    check_quota(api_key)

    if '--list'   in args: cmd_list(api_key)
    elif '--test' in args: cmd_test(api_key)
    elif '--delete' in args:
        idx = args.index('--delete')
        vid = args[idx+1] if idx+1 < len(args) else ''
        cmd_delete(api_key, vid)
    else:
        print(f"\n  {BOLD}O que você quer fazer?{RESET}")
        print(f"  {CYAN}1{RESET}. Clonar uma nova voz")
        print(f"  {CYAN}2{RESET}. Ver vozes existentes na conta")
        print(f"  {CYAN}3{RESET}. Testar vozes configuradas")
        print(f"  {CYAN}4{RESET}. Deletar uma voz")
        choice = input(f"\n  {CYAN}Escolha [1-4]:{RESET} ").strip()
        if   choice == '1': wizard_clone(api_key)
        elif choice == '2': cmd_list(api_key)
        elif choice == '3': cmd_test(api_key)
        elif choice == '4':
            cmd_list(api_key)
            vid = input(f"\n  {CYAN}Cole o voice_id para deletar:{RESET} ").strip()
            cmd_delete(api_key, vid)
        else: warn("Opção inválida."); return
        print_summary()

if __name__ == '__main__':
    try: main()
    except KeyboardInterrupt: print(f"\n\n  {YELLOW}Cancelado.{RESET}\n")