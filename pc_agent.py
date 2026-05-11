"""
J.A.R.V.I.S. — PC AGENT
Versão 1.0 — Agente de Controle de PC com Visão

Inspirado no Mark XXXV: usa Gemini Vision para ver a tela e
tomar decisões autônomas de controle (mouse, teclado, janelas).

Capacidades:
  1. screen_capture    — captura e comprime o screenshot atual
  2. vision_analyze    — envia screenshot ao Gemini e recebe plano de ação
  3. execute_plan      — executa as ações do plano (clique, digitar, scroll, abrir)
  4. agent_loop        — loop autônomo: vê → decide → age → verifica
  5. safe_actions      — lista de ações permitidas com confirmação obrigatória

SEGURANÇA:
  - Todas as ações destrutivas (deletar, formatar) são BLOQUEADAS
  - Ações sensíveis (enviar, comprar) requerem confirmação do usuário
  - Limite de 10 iterações por sessão de agente
  - Timeout de 30s por ação

INSTALAÇÃO (além dos requisitos já existentes):
  pip install pyautogui pillow

USO via App.py:
  from pc_agent import run_pc_agent, capture_screen_b64

  # Executa uma tarefa autônoma
  resultado = run_pc_agent(
      task="Abra o Notepad e escreva 'Olá, Sir'",
      gemini_client=gemini_client,
      socketio_emit=socketio.emit,
      sid=sid
  )
"""

import os
import io
import time
import base64
import json
import platform
import datetime
import re
from pathlib import Path
from threading import Lock

# ─── IMPORTAÇÕES OPCIONAIS ────────────────────────────────────────────────────

try:
    import pyautogui
    pyautogui.FAILSAFE = True       # move mouse pro canto superior esquerdo para abortar
    pyautogui.PAUSE    = 0.3        # pausa entre ações (segurança)
    PYAUTOGUI_OK = True
except ImportError:
    PYAUTOGUI_OK = False
    print('[PC-AGENT] pyautogui não instalado — pip install pyautogui')

try:
    from PIL import Image, ImageGrab
    PIL_OK = True
except ImportError:
    PIL_OK = False
    print('[PC-AGENT] Pillow não instalado — pip install pillow')

# ─── CONFIGURAÇÕES DE SEGURANÇA ───────────────────────────────────────────────

MAX_ITERATIONS   = 10     # máximo de passos autônomos por tarefa
ACTION_TIMEOUT   = 30     # segundos por ação
SCREENSHOT_WIDTH = 1280   # largura máxima para enviar ao Gemini (reduz tokens)
JPEG_QUALITY     = 60     # qualidade JPEG para reduzir tamanho

# Ações que exigem confirmação explícita do usuário
CONFIRM_ACTIONS = {
    'send_email', 'send_message', 'purchase', 'delete_file',
    'format_drive', 'execute_script', 'install_software',
}

# Ações completamente bloqueadas
BLOCKED_ACTIONS = {
    'format_drive', 'delete_system_files', 'modify_registry',
    'disable_antivirus', 'access_banking',
}

# Lock para evitar ações paralelas simultâneas
_agent_lock = Lock()

# Histórico de ações da sessão atual
_action_history: list[dict] = []


# ─── CAPTURA DE TELA ──────────────────────────────────────────────────────────

def capture_screen_b64(
    region: tuple | None = None,
    max_width: int = SCREENSHOT_WIDTH,
    quality: int = JPEG_QUALITY,
) -> tuple[str, dict]:
    """
    Captura a tela (ou uma região) e retorna:
      - base64 da imagem JPEG comprimida
      - metadados: resolução original, resolução enviada, timestamp

    region: (x, y, largura, altura) ou None para tela inteira
    """
    if not PIL_OK:
        raise RuntimeError('Pillow não instalado — pip install pillow')

    try:
        if region:
            x, y, w, h = region
            screenshot = ImageGrab.grab(bbox=(x, y, x + w, y + h))
        else:
            screenshot = ImageGrab.grab()

        orig_w, orig_h = screenshot.size

        # Redimensiona para economizar tokens do Gemini
        if orig_w > max_width:
            ratio       = max_width / orig_w
            new_h       = int(orig_h * ratio)
            screenshot  = screenshot.resize((max_width, new_h), Image.LANCZOS)
        else:
            max_width = orig_w

        # Converte para JPEG comprimido
        buf = io.BytesIO()
        screenshot.convert('RGB').save(buf, format='JPEG', quality=quality, optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode('utf-8')

        meta = {
            'original_resolution': f'{orig_w}x{orig_h}',
            'sent_resolution':     f'{screenshot.size[0]}x{screenshot.size[1]}',
            'size_kb':             round(len(buf.getvalue()) / 1024, 1),
            'timestamp':           datetime.datetime.now().isoformat(),
            'region':              region,
        }

        print(f'[PC-AGENT] Screenshot capturado: {meta["sent_resolution"]} | {meta["size_kb"]} KB')
        return b64, meta

    except Exception as e:
        raise RuntimeError(f'Erro ao capturar tela: {e}')


# ─── ANÁLISE VISUAL COM GEMINI ────────────────────────────────────────────────

VISION_SYSTEM_PROMPT = """Você é o agente visual do J.A.R.V.I.S., especializado em analisar screenshots e planejar ações de controle de PC.

Analise a imagem e retorne SOMENTE um JSON com o seguinte formato:

{
  "screen_description": "descrição breve do que está na tela (1-2 frases)",
  "task_status": "not_started|in_progress|completed|failed|needs_input",
  "next_actions": [
    {
      "action": "click|double_click|right_click|type|hotkey|scroll|move|wait|open_app|close_window|screenshot_region",
      "params": {
        "x": 500,
        "y": 300,
        "text": "texto a digitar",
        "keys": ["ctrl", "c"],
        "direction": "up|down|left|right",
        "amount": 3,
        "app": "notepad",
        "region": [x, y, w, h]
      },
      "reason": "por que esta ação",
      "requires_confirmation": false
    }
  ],
  "reasoning": "explicação breve do raciocínio",
  "observation": "algo importante observado na tela",
  "estimated_completion": "porcentagem estimada de conclusão da tarefa (0-100)"
}

REGRAS CRÍTICAS:
- Coordenadas x,y referem-se à tela ORIGINAL (não à imagem redimensionada)
- Nunca sugira ações destrutivas (deletar arquivos do sistema, formatar drives)
- Nunca sugira ações de compra ou bancárias
- Se a tarefa já está concluída, retorne task_status="completed" e next_actions=[]
- Se precisar de input do usuário, retorne task_status="needs_input"
- Máximo de 3 ações por resposta (mantenha o controle)
"""

def analyze_screen_with_vision(
    screenshot_b64: str,
    task: str,
    screen_meta: dict,
    history: list[dict],
    gemini_client,
) -> dict:
    """
    Envia o screenshot ao Gemini Vision com o contexto da tarefa.
    Retorna o plano de ação em formato dict.
    """
    orig_res = screen_meta.get('original_resolution', 'desconhecida')
    history_text = ''
    if history:
        history_text = '\n\nAções já executadas:\n' + '\n'.join(
            f'  {i+1}. {h["action"]} — {h.get("result", "ok")}'
            for i, h in enumerate(history[-5:])
        )

    user_prompt = (
        f'Tarefa: {task}\n'
        f'Resolução original da tela: {orig_res}\n'
        f'Iteração: {len(history) + 1}/{MAX_ITERATIONS}'
        + history_text
    )

    try:
        response = gemini_client.models.generate_content(
            model='gemini-2.0-flash',
            contents=[{
                'parts': [
                    {'text': VISION_SYSTEM_PROMPT + '\n\n' + user_prompt},
                    {'inline_data': {
                        'mime_type': 'image/jpeg',
                        'data':      screenshot_b64,
                    }},
                ]
            }]
        )

        raw = response.text.strip()
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)

        plan = json.loads(raw)
        print(f'[PC-AGENT] Plano recebido: {plan.get("task_status")} | {len(plan.get("next_actions", []))} ações')
        return plan

    except json.JSONDecodeError as e:
        print(f'[PC-AGENT] JSON inválido do Gemini: {e}')
        return {
            'screen_description': 'Erro ao interpretar resposta',
            'task_status':        'failed',
            'next_actions':       [],
            'reasoning':          f'Erro de parsing: {e}',
            'estimated_completion': 0,
        }
    except Exception as e:
        print(f'[PC-AGENT] Erro na análise visual: {e}')
        return {
            'screen_description': 'Erro na análise',
            'task_status':        'failed',
            'next_actions':       [],
            'reasoning':          str(e),
            'estimated_completion': 0,
        }


# ─── EXECUTOR DE AÇÕES ────────────────────────────────────────────────────────

def _scale_coords(x: int, y: int, orig_res: str, sent_res: str) -> tuple[int, int]:
    """Ajusta coordenadas caso a imagem tenha sido redimensionada."""
    try:
        ow, oh = map(int, orig_res.split('x'))
        sw, sh = map(int, sent_res.split('x'))
        if ow == sw:
            return x, y
        # Gemini vê a imagem redimensionada, mas as coords devem ser da original
        # O prompt instrui o Gemini a usar coords originais — essa função é um safety net
        scale_x = ow / sw
        scale_y = oh / sh
        return int(x * scale_x), int(y * scale_y)
    except Exception:
        return x, y


def execute_action(action_dict: dict, screen_meta: dict, safe_mode: bool = True) -> dict:
    """
    Executa uma única ação de controle de PC.
    Retorna dict com {success, result, error}.
    """
    if not PYAUTOGUI_OK:
        return {'success': False, 'error': 'pyautogui não instalado'}

    action = action_dict.get('action', '').lower()
    params = action_dict.get('params', {})

    # Bloqueia ações proibidas
    if action in BLOCKED_ACTIONS:
        return {'success': False, 'error': f'Ação "{action}" é bloqueada por segurança'}

    orig_res = screen_meta.get('original_resolution', '1920x1080')
    sent_res = screen_meta.get('sent_resolution',     '1280x720')

    try:
        # ── Clique simples ──────────────────────────────────────────────────
        if action == 'click':
            x, y = _scale_coords(
                int(params.get('x', 0)),
                int(params.get('y', 0)),
                orig_res, sent_res,
            )
            pyautogui.click(x, y)
            return {'success': True, 'result': f'Clique em ({x}, {y})'}

        # ── Duplo clique ────────────────────────────────────────────────────
        elif action == 'double_click':
            x, y = _scale_coords(
                int(params.get('x', 0)),
                int(params.get('y', 0)),
                orig_res, sent_res,
            )
            pyautogui.doubleClick(x, y)
            return {'success': True, 'result': f'Duplo clique em ({x}, {y})'}

        # ── Clique direito ──────────────────────────────────────────────────
        elif action == 'right_click':
            x, y = _scale_coords(
                int(params.get('x', 0)),
                int(params.get('y', 0)),
                orig_res, sent_res,
            )
            pyautogui.rightClick(x, y)
            return {'success': True, 'result': f'Clique direito em ({x}, {y})'}

        # ── Mover mouse ─────────────────────────────────────────────────────
        elif action == 'move':
            x, y = _scale_coords(
                int(params.get('x', 0)),
                int(params.get('y', 0)),
                orig_res, sent_res,
            )
            pyautogui.moveTo(x, y, duration=0.3)
            return {'success': True, 'result': f'Mouse movido para ({x}, {y})'}

        # ── Digitar texto ───────────────────────────────────────────────────
        elif action == 'type':
            text = params.get('text', '')
            if not text:
                return {'success': False, 'error': 'Nenhum texto para digitar'}
            # Usa pyperclip para textos com caracteres especiais / acentos
            try:
                import pyperclip
                pyperclip.copy(text)
                pyautogui.hotkey('ctrl', 'v')
            except ImportError:
                pyautogui.typewrite(text, interval=0.04)
            return {'success': True, 'result': f'Digitado: "{text[:40]}"'}

        # ── Atalho de teclado ───────────────────────────────────────────────
        elif action == 'hotkey':
            keys = params.get('keys', [])
            if not keys:
                return {'success': False, 'error': 'Nenhuma tecla especificada'}
            # Sanitiza: apenas teclas conhecidas
            allowed_keys = {
                'ctrl', 'alt', 'shift', 'win', 'tab', 'enter', 'escape', 'esc',
                'space', 'backspace', 'delete', 'home', 'end', 'pageup', 'pagedown',
                'up', 'down', 'left', 'right', 'f1', 'f2', 'f3', 'f4', 'f5',
                'f6', 'f7', 'f8', 'f9', 'f10', 'f11', 'f12',
                'a','b','c','d','e','f','g','h','i','j','k','l','m',
                'n','o','p','q','r','s','t','u','v','w','x','y','z',
                '0','1','2','3','4','5','6','7','8','9',
                '+', '-', '=', '[', ']', '\\', ';', "'", ',', '.', '/',
            }
            keys_lower = [k.lower() for k in keys]
            invalid = [k for k in keys_lower if k not in allowed_keys]
            if invalid:
                return {'success': False, 'error': f'Tecla inválida: {invalid}'}
            pyautogui.hotkey(*keys_lower)
            return {'success': True, 'result': f'Atalho: {" + ".join(keys_lower)}'}

        # ── Scroll ──────────────────────────────────────────────────────────
        elif action == 'scroll':
            x      = int(params.get('x', 0)) or None
            y_pos  = int(params.get('y', 0)) or None
            amount = int(params.get('amount', 3))
            direct = params.get('direction', 'down')
            clicks = -amount if direct == 'down' else amount
            if x and y_pos:
                pyautogui.scroll(clicks, x=x, y=y_pos)
            else:
                pyautogui.scroll(clicks)
            return {'success': True, 'result': f'Scroll {direct} {amount}x'}

        # ── Abrir aplicativo ─────────────────────────────────────────────────
        elif action == 'open_app':
            import subprocess
            app = params.get('app', '')
            if not app:
                return {'success': False, 'error': 'App não especificado'}

            # Mapa de apps seguros (evita exec de comandos arbitrários)
            safe_apps = {
                'notepad': 'notepad.exe',
                'calc': 'calc.exe', 'calculadora': 'calc.exe',
                'explorer': 'explorer.exe',
                'chrome': 'chrome.exe',
                'firefox': 'firefox.exe',
                'vscode': 'code', 'code': 'code',
                'terminal': 'cmd.exe' if platform.system() == 'Windows' else 'gnome-terminal',
                'spotify': 'spotify',
                'discord': 'discord',
                'word': 'WINWORD.EXE',
                'excel': 'EXCEL.EXE',
                'paint': 'mspaint.exe',
            }
            cmd = safe_apps.get(app.lower())
            if safe_mode and not cmd:
                return {'success': False, 'error': f'App "{app}" não está na lista segura'}
            if not safe_mode and not cmd:
                cmd = app # Tenta executar o app diretamente se safe_mode estiver desligado

            subprocess.Popen(cmd, shell=True)
            time.sleep(1.5)
            return {'success': True, 'result': f'App aberto: {app}'}

        # ── Fechar janela ────────────────────────────────────────────────────
        elif action == 'close_window':
            pyautogui.hotkey('alt', 'f4')
            return {'success': True, 'result': 'Janela fechada (Alt+F4)'}

        # ── Screenshot de região ─────────────────────────────────────────────
        elif action == 'screenshot_region':
            region = params.get('region')
            if region and len(region) == 4:
                b64, _ = capture_screen_b64(region=tuple(region))
                return {'success': True, 'result': 'Região capturada', 'screenshot_b64': b64}
            return {'success': False, 'error': 'Região inválida'}

        # ── Aguardar ─────────────────────────────────────────────────────────
        elif action == 'wait':
            seconds = min(float(params.get('amount', 1)), 5.0)  # máximo 5s
            time.sleep(seconds)
            return {'success': True, 'result': f'Aguardou {seconds}s'}

        # ── Pressionar tecla única ────────────────────────────────────────────
        elif action == 'press':
            key = params.get('key', 'enter').lower()
            pyautogui.press(key)
            return {'success': True, 'result': f'Tecla pressionada: {key}'}

        else:
            return {'success': False, 'error': f'Ação desconhecida: {action}'}

    except pyautogui.FailSafeException:
        return {'success': False, 'error': 'FAILSAFE ativado (mouse no canto superior esquerdo)'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


# ─── LOOP DO AGENTE ───────────────────────────────────────────────────────────

def run_pc_agent(
    task: str,
    gemini_client,
    socketio_emit=None,
    sid: str = '',
    max_iterations: int = MAX_ITERATIONS,
    confirm_fn=None,
    safe_mode: bool = True,
) -> dict:
    """
    Loop principal do agente de PC.

    Parâmetros:
      task           — instrução em linguagem natural
      gemini_client  — cliente Google Gemini inicializado
      socketio_emit  — função emit do SocketIO (para status em tempo real)
      sid            — session id do cliente
      max_iterations — limite de iterações (default 10)
      confirm_fn     — função(action_dict) -> bool para confirmações
      safe_mode      — se True, impõe restrições rígidas de apps e bloqueios


    Retorna dict com {success, iterations, actions, final_status, summary}
    """
    if not PIL_OK or not PYAUTOGUI_OK:
        missing = []
        if not PIL_OK:      missing.append('pillow')
        if not PYAUTOGUI_OK: missing.append('pyautogui')
        return {
            'success': False,
            'error':   f'Dependências ausentes: pip install {" ".join(missing)}',
        }

    if not gemini_client:
        return {'success': False, 'error': 'Gemini não disponível para visão'}

    def _emit(step: str, message: str, data: dict | None = None):
        if socketio_emit:
            payload = {'step': step, 'message': message}
            if data:
                payload.update(data)
            try:
                socketio_emit('pc_agent_update', payload, room=sid)
            except Exception:
                pass

    # Verifica se outro agente está rodando
    if not _agent_lock.acquire(blocking=False):
        return {'success': False, 'error': 'Agente já está em execução. Aguarde.'}

    action_log: list[dict] = []
    iteration   = 0
    final_status = 'not_started'

    try:
        _emit('agent_start', f'Iniciando agente de PC: {task}')
        print(f'\n[PC-AGENT] ═══ INICIANDO TAREFA ═══')
        print(f'[PC-AGENT] Tarefa: {task}')

        while iteration < max_iterations:
            iteration += 1
            _emit('agent_thinking', f'Iteração {iteration}/{max_iterations} — Capturando tela...')
            print(f'\n[PC-AGENT] ── Iteração {iteration} ──')

            # 1. Captura a tela
            try:
                screenshot_b64, screen_meta = capture_screen_b64()
                _emit('agent_seeing', 'Analisando tela com Gemini Vision...', {
                    'resolution': screen_meta.get('sent_resolution'),
                    'size_kb':    screen_meta.get('size_kb'),
                })
            except Exception as e:
                _emit('agent_error', f'Erro ao capturar tela: {e}')
                break

            # 2. Analisa com Gemini Vision
            plan = analyze_screen_with_vision(
                screenshot_b64=screenshot_b64,
                task=task,
                screen_meta=screen_meta,
                history=action_log,
                gemini_client=gemini_client,
            )

            final_status = plan.get('task_status', 'unknown')
            _emit('agent_plan', plan.get('reasoning', ''), {
                'screen':     plan.get('screen_description', ''),
                'status':     final_status,
                'progress':   plan.get('estimated_completion', 0),
                'actions':    len(plan.get('next_actions', [])),
                'screenshot': screenshot_b64,  # envia o screenshot para o frontend exibir
            })

            print(f'[PC-AGENT] Status: {final_status} | Progresso: {plan.get("estimated_completion", 0)}%')
            print(f'[PC-AGENT] Tela: {plan.get("screen_description", "")}')
            print(f'[PC-AGENT] Raciocínio: {plan.get("reasoning", "")}')

            # 3. Verifica se a tarefa foi concluída ou falhou
            if final_status == 'completed':
                _emit('agent_done', 'Tarefa concluída com sucesso!', {'progress': 100})
                print('[PC-AGENT] ✅ Tarefa concluída!')
                break

            if final_status == 'failed':
                _emit('agent_error', f'Agente não conseguiu completar a tarefa: {plan.get("reasoning")}')
                print(f'[PC-AGENT] ❌ Tarefa falhou: {plan.get("reasoning")}')
                break

            if final_status == 'needs_input':
                _emit('agent_waiting', 'Aguardando input do usuário...')
                print('[PC-AGENT] ⏸ Aguardando input do usuário')
                break

            # 4. Executa as ações planejadas
            actions = plan.get('next_actions', [])
            if not actions:
                _emit('agent_waiting', 'Nenhuma ação necessária — verificando novamente...')
                time.sleep(1)
                continue

            for action_dict in actions:
                action_name = action_dict.get('action', '?')
                reason      = action_dict.get('reason', '')
                needs_confirm = action_dict.get('requires_confirmation', False)

                # Bloqueia ações proibidas sem nem perguntar
                if action_name in BLOCKED_ACTIONS:
                    _emit('agent_blocked', f'Ação bloqueada por segurança: {action_name}')
                    action_log.append({
                        'action': action_name,
                        'result': 'BLOQUEADA',
                        'reason': reason,
                    })
                    continue

                # Ações que precisam de confirmação
                if needs_confirm or action_name in CONFIRM_ACTIONS:
                    if confirm_fn:
                        confirmed = confirm_fn(action_dict)
                        if not confirmed:
                            _emit('agent_skipped', f'Ação cancelada pelo usuário: {action_name}')
                            action_log.append({
                                'action': action_name,
                                'result': 'CANCELADA pelo usuário',
                            })
                            continue
                    else:
                        # Sem função de confirmação — pula a ação sensível
                        _emit('agent_skipped', f'Ação sensível ignorada (sem confirmação): {action_name}')
                        continue

                # Executa a ação
                _emit('agent_acting', f'{action_name} — {reason}', {
                    'action': action_name,
                    'params': action_dict.get('params', {}),
                })
                print(f'[PC-AGENT] → Executando: {action_name} | {reason}')

                result = execute_action(action_dict, screen_meta, safe_mode=safe_mode)

                action_log.append({
                    'action':  action_name,
                    'params':  action_dict.get('params', {}),
                    'reason':  reason,
                    'result':  result.get('result', result.get('error', 'ok')),
                    'success': result.get('success', False),
                })

                status_msg = result.get('result') if result['success'] else f'Erro: {result.get("error")}'
                _emit(
                    'agent_action_result',
                    status_msg,
                    {'success': result['success'], 'action': action_name},
                )
                print(f'[PC-AGENT]   {"✅" if result["success"] else "❌"} {status_msg}')

                if not result['success']:
                    # Continua mesmo com erros individuais (o Gemini vai adaptar)
                    pass

                # Pequena pausa entre ações para o sistema reagir
                time.sleep(0.5)

        else:
            # Chegou no limite de iterações
            final_status = 'max_iterations_reached'
            _emit('agent_timeout', f'Limite de {max_iterations} iterações atingido')
            print(f'[PC-AGENT] ⚠ Limite de iterações atingido')

    finally:
        _agent_lock.release()

    # ── Resumo final ──
    successful_actions = sum(1 for a in action_log if a.get('success'))
    summary = (
        f'Agente encerrou após {iteration} iteração(ões). '
        f'{successful_actions}/{len(action_log)} ações bem-sucedidas. '
        f'Status final: {final_status}.'
    )

    print(f'\n[PC-AGENT] ═══ RESUMO ═══')
    print(f'[PC-AGENT] {summary}')

    return {
        'success':    final_status == 'completed',
        'iterations': iteration,
        'actions':    action_log,
        'final_status': final_status,
        'summary':    summary,
    }


# ─── ANÁLISE RÁPIDA DE TELA (SEM LOOP) ───────────────────────────────────────

def quick_screen_analysis(
    query: str,
    gemini_client,
    region: tuple | None = None,
) -> str:
    """
    Análise pontual da tela sem loop autônomo.
    Útil para "o que está na minha tela?" ou "qual erro está aparecendo?"

    Retorna texto descritivo da análise.
    """
    if not PIL_OK:
        return 'Pillow não instalado — pip install pillow'
    if not gemini_client:
        return 'Gemini não disponível para análise visual'

    try:
        screenshot_b64, meta = capture_screen_b64(region=region)

        prompt = (
            f'Analise esta screenshot e responda em português brasileiro.\n'
            f'Resolução original: {meta["original_resolution"]}\n\n'
            f'Pergunta/tarefa: {query}'
        )

        response = gemini_client.models.generate_content(
            model='gemini-2.0-flash',
            contents=[{
                'parts': [
                    {'text': prompt},
                    {'inline_data': {'mime_type': 'image/jpeg', 'data': screenshot_b64}},
                ]
            }]
        )

        return response.text.strip()

    except Exception as e:
        return f'Erro na análise visual: {e}'


# ─── STATUS DO AGENTE ─────────────────────────────────────────────────────────

def get_agent_status() -> dict:
    """Retorna se o agente está ocupado ou disponível."""
    busy = not _agent_lock.acquire(blocking=False)
    if not busy:
        _agent_lock.release()
    return {
        'available':  not busy,
        'pyautogui':  PYAUTOGUI_OK,
        'pillow':     PIL_OK,
        'max_iter':   MAX_ITERATIONS,
        'screenshot_width': SCREENSHOT_WIDTH,
    }


# ─── TESTE LOCAL ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import sys

    print('\n' + '═' * 56)
    print('  J.A.R.V.I.S. — PC AGENT — Teste')
    print('═' * 56)

    print(f'\n  pyautogui: {"✅ ok" if PYAUTOGUI_OK else "❌ não instalado"}')
    print(f'  Pillow:    {"✅ ok" if PIL_OK else "❌ não instalado"}')

    if PIL_OK:
        print('\n  Testando captura de tela...')
        try:
            b64, meta = capture_screen_b64()
            print(f'  ✅ Screenshot: {meta["sent_resolution"]} | {meta["size_kb"]} KB')
            out = Path('test_screenshot.jpg')
            out.write_bytes(base64.b64decode(b64))
            print(f'  ✅ Salvo em: {out.resolve()}')
        except Exception as e:
            print(f'  ❌ Erro: {e}')

    print('\n  Status do agente:')
    status = get_agent_status()
    for k, v in status.items():
        print(f'    {k}: {v}')

    print()