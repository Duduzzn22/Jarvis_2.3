"""
J.A.R.V.I.S. — Script de Configuração de Perfil
Módulo 2: Consciência
Execute UMA VEZ antes de iniciar o App.py pela primeira vez.
"""

import os
import sys
import datetime

# Garante que o memory.py seja encontrado na mesma pasta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from memory import (
    is_profile_complete,
    set_profile,
    get_profile,
    add_memory,
    get_profile_field,
)

# ─── CORES NO TERMINAL ────────────────────────────────────────────────────────
CYAN   = '\033[96m'
WHITE  = '\033[97m'
GREEN  = '\033[92m'
YELLOW = '\033[93m'
DIM    = '\033[2m'
RESET  = '\033[0m'
BOLD   = '\033[1m'

def c(text, color):
    return f'{color}{text}{RESET}'

def linha():
    print(c('─' * 56, CYAN))

def header():
    print()
    linha()
    print(c('  J.A.R.V.I.S. — CONFIGURAÇÃO DE PERFIL', BOLD + CYAN))
    print(c('  Módulo 2: Consciência', DIM))
    linha()
    print()

def perguntar(prompt, default='', obrigatorio=False):
    """Pergunta com suporte a valor padrão e campo obrigatório."""
    sufixo = f' [{default}]' if default else ''
    while True:
        resposta = input(c(f'  ▸ {prompt}{sufixo}: ', WHITE)).strip()
        if not resposta and default:
            return default
        if resposta:
            return resposta
        if obrigatorio:
            print(c('  ! Campo obrigatório. Tente novamente.', YELLOW))
        else:
            return ''

def perguntar_opcoes(prompt, opcoes: list, default_idx=0):
    """Pergunta com opções numeradas."""
    print(c(f'  ▸ {prompt}', WHITE))
    for i, op in enumerate(opcoes):
        marcador = c('●', CYAN) if i == default_idx else c('○', DIM)
        print(f'    {marcador} {i+1}. {op}')
    while True:
        resp = input(c(f'  Escolha [1-{len(opcoes)}] (Enter = {default_idx+1}): ', WHITE)).strip()
        if not resp:
            return opcoes[default_idx]
        if resp.isdigit() and 1 <= int(resp) <= len(opcoes):
            return opcoes[int(resp) - 1]
        print(c(f'  ! Digite um número entre 1 e {len(opcoes)}', YELLOW))

# ─── FLUXO DE ONBOARDING ──────────────────────────────────────────────────────

def run_setup(force=False):
    header()

    # Verifica se já foi configurado
    if is_profile_complete() and not force:
        nome = get_profile_field('user_name')
        print(c(f'  Perfil já configurado para: {nome}', GREEN))
        print(c('  Use --reset para reconfigurar.', DIM))
        print()
        resp = input(c('  Deseja reconfigurar mesmo assim? (s/N): ', WHITE)).strip().lower()
        if resp != 's':
            print()
            print(c('  Nenhuma alteração feita. Até logo, Sir.', DIM))
            print()
            return
        print()

    print(c('  Olá, Sir. Vou aprender quem você é.', CYAN))
    print(c('  Isso leva menos de 1 minuto.\n', DIM))

    # ── 1. Nome ──────────────────────────────────────────────────────────────
    linha()
    print(c('  IDENTIDADE', BOLD))
    linha()

    nome = perguntar('Qual é o seu nome?', obrigatorio=True)
    set_profile('user_name', nome.title())
    add_memory('pessoal', f'Usuário se chama {nome.title()}', importance=3)
    print(c(f'  Prazer em conhecê-lo, {nome.title()}, Sir.\n', GREEN))

    # ── 2. Ocupação ──────────────────────────────────────────────────────────
    ocupacao = perguntar('Qual é sua ocupação ou área de trabalho?')
    if ocupacao:
        set_profile('occupation', ocupacao)
        add_memory('trabalho', f'Trabalha como/com {ocupacao}', importance=2)

    # ── 3. Horário de trabalho ───────────────────────────────────────────────
    print()
    horario = perguntar_opcoes(
        'Qual é o seu horário habitual de trabalho?',
        ['Manhã (6h–12h)', 'Tarde (12h–18h)', 'Noite (18h–00h)', 'Madrugada (00h–6h)', 'Variado'],
        default_idx=1
    )
    set_profile('work_hours', horario)
    add_memory('habito', f'Trabalha no período: {horario}', importance=1)

    # ── 4. Sistema operacional ───────────────────────────────────────────────
    print()
    import platform
    so_detectado = platform.system()
    so_map = {'Windows': 0, 'Darwin': 1, 'Linux': 2}
    so_idx = so_map.get(so_detectado, 0)

    so = perguntar_opcoes(
        'Qual sistema operacional você usa?',
        ['Windows', 'macOS', 'Linux'],
        default_idx=so_idx
    )
    set_profile('os', so)
    add_memory('tecnologia', f'Usa {so} como sistema operacional', importance=2)

    # ── 5. Apps favoritos ────────────────────────────────────────────────────
    print()
    linha()
    print(c('  PREFERÊNCIAS DE APPS', BOLD))
    linha()

    browser = perguntar_opcoes(
        'Navegador preferido?',
        ['Chrome', 'Firefox', 'Edge', 'Outro'],
        default_idx=0
    )
    set_profile('browser', browser)
    add_memory('tecnologia', f'Usa {browser} como navegador principal', importance=1)

    musica = perguntar_opcoes(
        'Onde você ouve música?',
        ['Spotify', 'YouTube Music', 'Deezer', 'Não ouço música'],
        default_idx=0
    )
    if musica != 'Não ouço música':
        set_profile('music_app', musica)
        add_memory('preferencia', f'Ouve música no {musica}', importance=1)

    # ── 6. Preferências de comunicação ───────────────────────────────────────
    print()
    linha()
    print(c('  COMUNICAÇÃO', BOLD))
    linha()

    estilo = perguntar_opcoes(
        'Prefere respostas do JARVIS:',
        ['Curtas e diretas', 'Detalhadas quando necessário', 'Sempre detalhadas'],
        default_idx=0
    )
    estilo_map = {
        'Curtas e diretas': 'Prefere respostas curtas e diretas',
        'Detalhadas quando necessário': 'Prefere respostas detalhadas quando o assunto exige',
        'Sempre detalhadas': 'Prefere respostas sempre detalhadas e completas',
    }
    set_profile('response_style', estilo)
    add_memory('preferencia', estilo_map[estilo], importance=2)

    # ── 7. Informação livre ──────────────────────────────────────────────────
    print()
    extra = perguntar(
        'Algo mais que o JARVIS deva saber sobre você? (opcional)'
    )
    if extra:
        add_memory('pessoal', extra, importance=2)
        set_profile('extra_info', extra)

    # ── Confirmação ──────────────────────────────────────────────────────────
    print()
    linha()
    print(c('  PERFIL CONFIGURADO COM SUCESSO', BOLD + GREEN))
    linha()

    perfil = get_profile()
    print()
    print(c('  O que o JARVIS sabe sobre você:', CYAN))
    labels = {
        'user_name':      'Nome',
        'occupation':     'Ocupação',
        'work_hours':     'Horário',
        'os':             'Sistema',
        'browser':        'Navegador',
        'music_app':      'Música',
        'response_style': 'Estilo',
        'extra_info':     'Extra',
    }
    for key, label in labels.items():
        val = perfil.get(key)
        if val:
            print(f'  {c(label + ":", DIM)} {val}')

    print()
    print(c('  Tudo pronto, Sir. Inicie o App.py e o JARVIS já te conhecerá.', GREEN))
    print()
    linha()
    print()


# ─── ENTRY POINT ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    force = '--reset' in sys.argv
    try:
        run_setup(force=force)
    except KeyboardInterrupt:
        print()
        print(c('\n  Configuração cancelada, Sir.', YELLOW))
        print()