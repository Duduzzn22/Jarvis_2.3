"""
J.A.R.V.I.S. — GOOGLE WORKSPACE SKILL v2.0
Integração com Google Sheets, Calendar, Maps
Novas features:
  - Sheets: create, read, write, append_entry, update_cell, update_formula
  - NLP parser: extrai valor/categoria/coluna de comandos de voz
  - Memória de planilha ativa por sessão
  - Browser search: abre Chrome com resultados em tempo real
  - Respostas de voz sem URL (curtas e diretas)
"""

import re
import json
import datetime
import webbrowser
from pathlib import Path
from urllib.parse import quote_plus

# ─── ESTADO GLOBAL ────────────────────────────────────────────────────────────
# Memória de planilha ativa por sessão: {sid: {id, title, url}}
_active_sheets: dict = {}

class DummySocketIO:
    def __init__(self):
        self._emit_fn = None
    def emit(self, *args, **kwargs):
        if self._emit_fn:
            self._emit_fn(*args, **kwargs)

socketio = DummySocketIO()

# Globais injetadas via setup()
GEMINI_AVAILABLE = False
gemini_client    = None
GEMINI_MODELS    = []
GROQ_AVAILABLE   = False
groq_client      = None

_CREDS_FILE = Path(__file__).parent.parent / 'google_credentials.json'
_TOKEN_FILE = Path(__file__).parent.parent / 'google_token.json'

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/drive.file',
]

# ─── SETUP ────────────────────────────────────────────────────────────────────

def setup(deps):
    global socketio, GEMINI_AVAILABLE, gemini_client, GEMINI_MODELS
    global GROQ_AVAILABLE, groq_client
    if 'emit'             in deps: socketio._emit_fn  = deps['emit']
    if 'GEMINI_AVAILABLE' in deps: GEMINI_AVAILABLE   = deps['GEMINI_AVAILABLE']
    if 'gemini_client'    in deps: gemini_client      = deps['gemini_client']
    if 'GEMINI_MODELS'    in deps: GEMINI_MODELS      = deps['GEMINI_MODELS']
    if 'GROQ_AVAILABLE'   in deps: GROQ_AVAILABLE     = deps['GROQ_AVAILABLE']
    if 'groq_client'      in deps: groq_client        = deps['groq_client']


# ─── AUTH ─────────────────────────────────────────────────────────────────────

def _get_google_creds():
    """Obtém credenciais Google OAuth 2.0 com refresh automático."""
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request

        creds = None
        if _TOKEN_FILE.exists():
            creds = Credentials.from_authorized_user_file(str(_TOKEN_FILE), SCOPES)

        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                _TOKEN_FILE.write_text(creds.to_json())
                return creds
            except Exception as refresh_err:
                print(f'[JARVIS] Google token expirado e nao renovavel: {refresh_err}')
                _TOKEN_FILE.unlink(missing_ok=True)
                creds = None

        if creds and creds.valid:
            return creds

        if not _CREDS_FILE.exists():
            print('[JARVIS] google_credentials.json nao encontrado')
            return None

        print('[JARVIS] Iniciando fluxo OAuth Google — browser abrira em instantes...')
        try:
            flow  = InstalledAppFlow.from_client_secrets_file(str(_CREDS_FILE), SCOPES)
            creds = flow.run_local_server(port=8090, open_browser=True)
            _TOKEN_FILE.write_text(creds.to_json())
            print('[JARVIS] Google autenticado com sucesso! Token salvo.')
            return creds
        except Exception as oauth_err:
            err_str = str(oauth_err).lower()
            if 'access_denied' in err_str or '403' in err_str:
                print('[JARVIS] ERRO 403 — adicione seu email em: '
                      'console.cloud.google.com > Tela de consentimento OAuth > Usuarios de teste')
            else:
                print(f'[JARVIS] Erro no fluxo OAuth: {oauth_err}')
            return None

    except Exception as e:
        print(f'[JARVIS] Google Auth erro: {e}')
        return None


def _get_sheets_service():
    creds = _get_google_creds()
    if not creds:
        return None
    from googleapiclient.discovery import build
    return build('sheets', 'v4', credentials=creds)


def _get_calendar_service():
    creds = _get_google_creds()
    if not creds:
        return None
    from googleapiclient.discovery import build
    return build('calendar', 'v3', credentials=creds)


def _auth_error_msg(sid: str) -> str:
    if _TOKEN_FILE.exists():
        msg = ('Sua sessao Google expirou, Senhor. '
               'Reinicie o Jarvis para renovar a autenticacao.')
    else:
        msg = ('Autenticacao Google necessaria, Senhor. '
               'Reinicie o Jarvis — o browser abrira para autorizacao.')
    socketio.emit('action_result',
                  {'success': False, 'message': 'Google: requer autenticacao'}, room=sid)
    return msg


# =============================================================================
#  GOOGLE SHEETS — NLP PARSER
# =============================================================================

def _parse_entry_from_voice(text: str) -> dict:
    """
    Extrai dados de inserção via regex a partir de texto transcrito.
    Exemplos:
      "adicione R$ 37 de cartao na coluna Valor"
      "insira 150 reais de mercado"
      "coloca 50 de uber no transporte"
    """
    t     = text.lower().strip()
    value = None

    for pat in (
        r'r\$\s*([\d]+(?:[.,]\d{1,2})?)',
        r'([\d]+(?:[.,]\d{1,2})?)\s*reais',
        r'([\d]+(?:[.,]\d{1,2})?)\s+de\s+',
    ):
        m = re.search(pat, t)
        if m:
            try:
                value = float(m.group(1).replace(',', '.'))
                break
            except ValueError:
                pass

    if value is None:
        return {}

    col_map = {
        'valor': 'Valor', 'valores': 'Valor',
        'descricao': 'Descricao', 'descricao': 'Descricao',
        'categoria': 'Categoria', 'data': 'Data',
        'despesa': 'Despesas', 'despesas': 'Despesas',
        'receita': 'Receitas', 'receitas': 'Receitas',
    }
    column = 'Valor'

    col_m = re.search(r'(?:na coluna|no campo|em|na)\s+([a-z\w]+)', t)
    if col_m:
        col_raw = col_m.group(1).strip()
        column  = col_map.get(col_raw, col_raw.title())

    desc_m = re.search(
        r'(?:de|do|da|para|referente a)\s+([a-z\w\s]+?)(?:\s+(?:na|no|em|coluna|campo)|$)', t
    )
    description = desc_m.group(1).strip().title() if desc_m else 'Lancamento'

    value_str = f"R$ {value:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

    return {
        'value':       value,
        'value_str':   value_str,
        'description': description,
        'column':      column,
        'date':        datetime.date.today().strftime('%d/%m/%Y'),
    }


def _ai_parse_entry(text: str) -> dict:
    """Usa Groq para extrair dados quando regex nao consegue."""
    prompt = (
        f'Analise este comando de voz para insercao em planilha: "{text}"\n'
        f'Retorne APENAS JSON: {{"value": 37.00, "description": "Cartao", '
        f'"column": "Valor", "date": "{datetime.date.today().isoformat()}"}}\n'
        f'Se nao houver dados suficientes retorne null'
    )
    if GROQ_AVAILABLE and groq_client:
        try:
            resp = groq_client.chat.completions.create(
                model='llama-3.1-8b-instant',
                messages=[{'role': 'user', 'content': prompt}],
                max_tokens=80, temperature=0.0, timeout=5,
            )
            raw = resp.choices[0].message.content.strip().replace('```json','').replace('```','')
            if raw.lower().strip() == 'null':
                return {}
            data = json.loads(raw)
            data['value_str'] = (f"R$ {data['value']:,.2f}"
                                 .replace(',','X').replace('.', ',').replace('X','.'))
            data['date'] = datetime.date.today().strftime('%d/%m/%Y')
            return data
        except Exception as e:
            print(f'[JARVIS] AI parse entry falhou: {e}')
    return {}


# =============================================================================
#  GOOGLE SHEETS — DISPATCHER PRINCIPAL
# =============================================================================

def execute_google_sheets(params: dict, sid: str) -> str:
    """
    Dispatcher para todas as acoes do Google Sheets.
    Acoes: create | read | append_entry | update_cell | update_formula |
           list_sheets | set_active | open_active | write | append
    """
    if not _CREDS_FILE.exists():
        socketio.emit('action_result',
                      {'success': False, 'message': 'google_credentials.json ausente'}, room=sid)
        return ('Arquivo google_credentials.json nao encontrado, Senhor. '
                'Baixe no Google Cloud Console e coloque na pasta raiz do Jarvis.')

    service = _get_sheets_service()
    if not service:
        return _auth_error_msg(sid)

    action = params.get('action', 'create')
    socketio.emit('status_update',
                  {'step': 'executing', 'message': f'Google Sheets: {action}...'}, room=sid)

    try:
        if action == 'create':
            return _sheets_create(service, params, sid)

        if action == 'open_active':
            return _sheets_open_active(sid)

        if action == 'list_sheets':
            return _sheets_list(sid)

        if action == 'set_active':
            return _sheets_set_active(params, sid)

        # Acoes que precisam de spreadsheet_id
        sheet_id = _resolve_sheet_id(params, sid)
        if not sheet_id:
            return ('Qual planilha devo editar, Senhor? '
                    'Diga "abrir planilha ativa" para usar a ultima criada.')

        if action == 'read':
            return _sheets_read(service, sheet_id,
                                params.get('range', 'Dados!A1:Z100'), sid)

        if action in ('write', 'append'):
            return _sheets_write(service, sheet_id,
                                 params.get('range', 'Dados!A1'),
                                 params.get('data', []), sid)

        if action == 'append_entry':
            return _sheets_append_entry(service, sheet_id, params, sid)

        if action == 'update_cell':
            return _sheets_update_cell(service, sheet_id, params, sid)

        if action == 'update_formula':
            return _sheets_update_formula(service, sheet_id, params, sid)

        return f'Acao "{action}" nao reconhecida para Google Sheets, Senhor.'

    except Exception as e:
        print(f'[JARVIS] Sheets erro: {e}')
        socketio.emit('action_result',
                      {'success': False, 'message': f'Erro Sheets: {e}'}, room=sid)
        return f'Erro no Google Sheets: {e}'


def _resolve_sheet_id(params: dict, sid: str):
    sid_id = params.get('spreadsheet_id', '')
    if sid_id:
        return sid_id
    active = _active_sheets.get(sid)
    if active:
        return active['id']
    return None


# ─── CREATE ───────────────────────────────────────────────────────────────────

def _sheets_create(service, params: dict, sid: str) -> str:
    title       = params.get('title', 'Planilha Jarvis')
    description = params.get('description', '')
    data        = params.get('data', [])

    result         = service.spreadsheets().create(body={
        'properties': {'title': title},
        'sheets': [{'properties': {'title': 'Dados'}}]
    }).execute()
    spreadsheet_id = result['spreadsheetId']
    url            = f'https://docs.google.com/spreadsheets/d/{spreadsheet_id}'

    if description and not data:
        data = _generate_sheet_structure(description)

    if data:
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range='Dados!A1',
            valueInputOption='USER_ENTERED',
            body={'values': data}
        ).execute()

    # Salva como planilha ativa da sessao
    _active_sheets[sid] = {'id': spreadsheet_id, 'title': title, 'url': url}
    print(f'[JARVIS] Planilha ativa: {title} ({spreadsheet_id})')

    try:
        webbrowser.open(url)
    except Exception as e:
        print(f'[JARVIS] Nao foi possivel abrir o browser: {e}')

    socketio.emit('action_result', {
        'success': True, 'message': f'Planilha "{title}" criada!',
        'url': url, 'action': 'open_url'
    }, room=sid)
    socketio.emit('open_url', {'url': url}, room=sid)

    # Resposta de voz: SEM o link
    return f'Planilha "{title}" criada com sucesso, Senhor. Abrindo planilha.'


# ─── OPEN / LIST / SET ACTIVE ─────────────────────────────────────────────────

def _sheets_open_active(sid: str) -> str:
    active = _active_sheets.get(sid)
    if not active:
        return ('Nao ha planilha ativa nesta sessao, Senhor. '
                'Crie uma nova ou diga o nome da planilha que deseja abrir.')
    try:
        webbrowser.open(active['url'])
    except Exception as e:
        print(f'[JARVIS] Nao foi possivel abrir o browser: {e}')
    socketio.emit('open_url', {'url': active['url']}, room=sid)
    return f'Abrindo planilha {active["title"]}.'


def _sheets_list(sid: str) -> str:
    active = _active_sheets.get(sid)
    if not active:
        return 'Nenhuma planilha ativa nesta sessao, Senhor.'
    return f'Planilha ativa: {active["title"]}.'


def _sheets_set_active(params: dict, sid: str) -> str:
    sheet_id = params.get('spreadsheet_id', '')
    title    = params.get('title', 'Planilha')
    if not sheet_id:
        return 'Preciso do ID ou URL da planilha para defini-la como ativa, Senhor.'
    url = f'https://docs.google.com/spreadsheets/d/{sheet_id}'
    _active_sheets[sid] = {'id': sheet_id, 'title': title, 'url': url}
    return f'Planilha "{title}" definida como ativa, Senhor.'


# ─── READ ─────────────────────────────────────────────────────────────────────

def _sheets_read(service, spreadsheet_id: str, sheet_range: str, sid: str) -> str:
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=sheet_range
    ).execute()
    values = result.get('values', [])
    if not values:
        return 'A planilha esta vazia, Senhor.'
    formatted = '\n'.join([' | '.join(row) for row in values[:20]])
    socketio.emit('action_result', {'success': True, 'message': 'Dados lidos'}, room=sid)
    return f'Dados da planilha:\n{formatted}'


# ─── WRITE / APPEND ───────────────────────────────────────────────────────────

def _sheets_write(service, spreadsheet_id: str, sheet_range: str,
                  data: list, sid: str) -> str:
    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=sheet_range,
        valueInputOption='USER_ENTERED',
        insertDataOption='INSERT_ROWS',
        body={'values': data}
    ).execute()
    socketio.emit('action_result', {'success': True, 'message': 'Dados adicionados'}, room=sid)
    return 'Dados adicionados a planilha, Senhor.'


# ─── APPEND ENTRY (NLP) ───────────────────────────────────────────────────────

def _sheets_append_entry(service, spreadsheet_id: str, params: dict, sid: str) -> str:
    """
    Insere uma linha extraida via NLP de comando de voz.
    Tenta regex primeiro, depois IA como fallback.
    """
    raw_text = params.get('raw_text', '')
    entry    = params.get('entry') or {}

    if not entry and raw_text:
        entry = _parse_entry_from_voice(raw_text)

    if not entry and raw_text:
        entry = _ai_parse_entry(raw_text)

    if not entry:
        value = params.get('value')
        if value is not None:
            v = float(value)
            entry = {
                'value':       v,
                'value_str':   f"R$ {v:,.2f}".replace(',','X').replace('.', ',').replace('X','.'),
                'description': params.get('description', 'Lancamento'),
                'column':      params.get('column', 'Valor'),
                'date':        datetime.date.today().strftime('%d/%m/%Y'),
            }

    if not entry:
        return ('Nao consegui extrair os dados para insercao, Senhor. '
                'Tente: "adicione R$ 50 de mercado na coluna Valor".')

    # Descobre cabecalho para mapear colunas
    try:
        header_resp = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range='Dados!A1:Z1'
        ).execute()
        headers = header_resp.get('values', [[]])[0] if header_resp.get('values') else []
    except Exception:
        headers = []

    if headers:
        row       = [''] * len(headers)
        col_lower = {h.lower(): i for i, h in enumerate(headers)}
        field_map = {
            entry.get('column', 'valor').lower(): entry['value_str'],
            'descricao':  entry['description'],
            'descricao':  entry['description'],
            'data':       entry['date'],
            'categoria':  entry['description'],
            'item':       entry['description'],
        }
        for col_name, val in field_map.items():
            idx = col_lower.get(col_name)
            if idx is not None:
                row[idx] = val
        if all(c == '' for c in row):
            row = [entry['date'], entry['description'], entry['value_str']]
    else:
        row = [entry['date'], entry['description'], entry['value_str']]

    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range='Dados!A:A',
        valueInputOption='USER_ENTERED',
        insertDataOption='INSERT_ROWS',
        body={'values': [row]}
    ).execute()

    active     = _active_sheets.get(sid, {})
    sheet_name = active.get('title', 'planilha')
    socketio.emit('action_result', {
        'success': True,
        'message': f'{entry["description"]} — {entry["value_str"]} adicionado'
    }, room=sid)
    return (f'{entry["value_str"]} de {entry["description"]} '
            f'adicionado na {sheet_name}, Senhor.')


# ─── UPDATE CELL ──────────────────────────────────────────────────────────────

def _sheets_update_cell(service, spreadsheet_id: str, params: dict, sid: str) -> str:
    """
    Atualiza uma celula especifica.
    params: {cell: 'B5', value: '250', sheet_name: 'Dados'}
    """
    cell       = params.get('cell', 'A1')
    value      = params.get('value', '')
    sheet_name = params.get('sheet_name', 'Dados')

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f'{sheet_name}!{cell}',
        valueInputOption='USER_ENTERED',
        body={'values': [[value]]}
    ).execute()
    socketio.emit('action_result',
                  {'success': True, 'message': f'Celula {cell} atualizada'}, room=sid)
    return f'Celula {cell} atualizada para "{value}", Senhor.'


# ─── UPDATE FORMULA ───────────────────────────────────────────────────────────

def _sheets_update_formula(service, spreadsheet_id: str, params: dict, sid: str) -> str:
    """
    Aplica ou atualiza uma formula em uma celula.
    params: {cell: 'D2', formula: '=SUM(C2:C100)', description: 'total de gastos'}
    """
    cell        = params.get('cell', 'A1')
    formula     = params.get('formula', '')
    description = params.get('description', 'formula')
    sheet_name  = params.get('sheet_name', 'Dados')

    if not formula:
        formula = _ai_generate_formula(description, cell)

    if not formula:
        return f'Nao consegui gerar a formula para "{description}", Senhor.'

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f'{sheet_name}!{cell}',
        valueInputOption='USER_ENTERED',
        body={'values': [[formula]]}
    ).execute()
    socketio.emit('action_result',
                  {'success': True, 'message': f'Formula aplicada em {cell}'}, room=sid)
    return f'Formula aplicada em {cell}. Pronto, Senhor.'


def _ai_generate_formula(description: str, cell: str) -> str:
    """Usa Groq para gerar formula Google Sheets a partir de descricao em linguagem natural."""
    prompt = (f'Gere apenas a formula do Google Sheets para: "{description}" na celula {cell}. '
              f'Retorne SOMENTE a formula (ex: =SUM(C2:C100)), sem explicacao.')
    if GROQ_AVAILABLE and groq_client:
        try:
            resp = groq_client.chat.completions.create(
                model='llama-3.1-8b-instant',
                messages=[{'role': 'user', 'content': prompt}],
                max_tokens=60, temperature=0.0, timeout=5,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            print(f'[JARVIS] AI generate formula falhou: {e}')
    return ''


# ─── GENERATE STRUCTURE ───────────────────────────────────────────────────────

def _generate_sheet_structure(description: str) -> list:
    """Usa IA para gerar estrutura de planilha baseada na descricao."""
    prompt = (
        f'Gere uma estrutura de planilha Google Sheets para: "{description}"\n'
        f'Retorne APENAS um JSON com lista de listas. Primeira linha = cabecalho. 3-5 linhas de exemplo.\n'
        f'Exemplo: [["Data","Descricao","Valor","Categoria"],["01/05/2026","Aluguel","1500","Fixo"]]\n'
        f'Retorne SOMENTE o JSON, sem texto adicional.'
    )
    try:
        if GROQ_AVAILABLE and groq_client:
            resp = groq_client.chat.completions.create(
                model='llama-3.3-70b-versatile',
                messages=[{'role': 'user', 'content': prompt}],
                max_tokens=500, temperature=0.3,
            )
            raw = resp.choices[0].message.content.strip().replace('```json','').replace('```','').strip()
            return json.loads(raw)

        if GEMINI_AVAILABLE and gemini_client:
            for model in GEMINI_MODELS:
                try:
                    response = gemini_client.models.generate_content(model=model, contents=prompt)
                    raw = response.text.strip().replace('```json','').replace('```','').strip()
                    return json.loads(raw)
                except Exception:
                    continue

    except Exception as e:
        print(f'[JARVIS] Erro gerando estrutura de planilha: {e}')

    return [['Data', 'Descricao', 'Valor', 'Categoria', 'Observacoes']]


# =============================================================================
#  BROWSER SEARCH — Pesquisa em tempo real no Chrome
# =============================================================================

_SEARCH_DOMAINS = {
    'jogo':        'https://www.google.com/search?q={query}&tbm=nws',
    'placar':      'https://www.google.com/search?q={query}',
    'flamengo':    'https://www.google.com/search?q={query}',
    'vasco':       'https://www.google.com/search?q={query}',
    'futebol':     'https://www.google.com/search?q={query}',
    'campeonato':  'https://www.google.com/search?q={query}',
    'transmissao': 'https://www.google.com/search?q={query}',
    'transmissão': 'https://www.google.com/search?q={query}',
    'onde passa':  'https://www.google.com/search?q={query}',
    'clima':       'https://www.google.com/search?q=previsão+do+tempo+{query}',
    'tempo':       'https://www.google.com/search?q=previsão+do+tempo+{query}',
    'temperatura': 'https://www.google.com/search?q=temperatura+agora+{query}',
    'previsao':    'https://www.google.com/search?q=previsão+do+tempo+{query}',
    'previsão':    'https://www.google.com/search?q=previsão+do+tempo+{query}',
    'noticia':     'https://news.google.com/search?q={query}&hl=pt-BR',
    'notícia':     'https://news.google.com/search?q={query}&hl=pt-BR',
    'dolar':       'https://www.google.com/search?q=cotacao+dolar+hoje',
    'dólar':       'https://www.google.com/search?q=cotacao+dolar+hoje',
    'cotacao':     'https://www.google.com/search?q={query}',
    'cotação':     'https://www.google.com/search?q={query}',
    'transito':    'https://www.google.com/maps/search/{query}',
    'trânsito':    'https://www.google.com/maps/search/{query}',
}


def execute_browser_search(params: dict, sid: str) -> str:
    """
    Abre o browser padrao com a busca em tempo real.
    Detecta o tipo de query e escolhe a URL mais relevante.
    """
    query    = params.get('query', '').strip()
    category = params.get('category', '').lower()

    if not query:
        return 'O que devo pesquisar, Senhor?'

    socketio.emit('status_update',
                  {'step': 'executing', 'message': 'Abrindo navegador...'}, room=sid)

    url_template = None
    q_lower      = query.lower()
    for keyword, template in _SEARCH_DOMAINS.items():
        if keyword in q_lower or keyword in category:
            url_template = template
            break

    if not url_template:
        url_template = 'https://www.google.com/search?q={query}'

    encoded = quote_plus(query)
    url     = url_template.replace('{query}', encoded)

    try:
        webbrowser.open(url)
        print(f'[JARVIS] Browser aberto: {url}')
    except Exception as e:
        print(f'[JARVIS] Erro ao abrir browser: {e}')
        return f'Nao consegui abrir o navegador, Senhor. Erro: {e}'

    socketio.emit('action_result',
                  {'success': True, 'message': f'Pesquisando: {query}'}, room=sid)
    return f'Pesquisando no navegador, Senhor.'


# =============================================================================
#  GOOGLE CALENDAR
# =============================================================================

def execute_google_calendar(params: dict, sid: str) -> str:
    service = _get_calendar_service()
    if not service:
        socketio.emit('action_result',
                      {'success': False, 'message': 'Google Calendar nao configurado'}, room=sid)
        return 'Google Calendar nao configurado, Senhor. Coloque o google_credentials.json na pasta do Jarvis.'

    action = params.get('action', 'create')
    socketio.emit('status_update',
                  {'step': 'executing', 'message': f'Google Calendar: {action}...'}, room=sid)
    try:
        if action == 'create':
            return _calendar_create_event(service, params, sid)
        elif action == 'list':
            return _calendar_list_events(service, params, sid)
        elif action == 'delete':
            return _calendar_delete_event(service, params, sid)
        else:
            return f'Acao "{action}" nao reconhecida para Google Calendar.'
    except Exception as e:
        socketio.emit('action_result',
                      {'success': False, 'message': f'Erro Calendar: {e}'}, room=sid)
        return f'Erro no Google Calendar: {e}'


def _calendar_create_event(service, params, sid):
    title       = params.get('title', 'Evento Jarvis')
    description = params.get('description', '')
    date        = params.get('date', '')
    time_str    = params.get('time', '')
    duration    = int(params.get('duration', 60))
    now         = datetime.datetime.now()

    if date:
        try:
            if 'amanha' in date.lower() or 'amanha' in date.lower():
                start_date = now + datetime.timedelta(days=1)
            elif 'hoje' in date.lower():
                start_date = now
            else:
                start_date = datetime.datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            start_date = now + datetime.timedelta(days=1)
    else:
        start_date = now + datetime.timedelta(days=1)

    if time_str:
        try:
            parts  = time_str.replace('h', ':').replace('H', ':').split(':')
            hour   = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
            start_date = start_date.replace(hour=hour, minute=minute, second=0)
        except (ValueError, IndexError):
            start_date = start_date.replace(hour=10, minute=0, second=0)
    else:
        start_date = start_date.replace(hour=10, minute=0, second=0)

    end_date = start_date + datetime.timedelta(minutes=duration)
    result   = service.events().insert(calendarId='primary', body={
        'summary':     title,
        'description': description,
        'start': {'dateTime': start_date.isoformat(), 'timeZone': 'America/Sao_Paulo'},
        'end':   {'dateTime': end_date.isoformat(),   'timeZone': 'America/Sao_Paulo'},
    }).execute()
    url = result.get('htmlLink', '')
    socketio.emit('action_result',
                  {'success': True, 'message': f'Evento "{title}" criado!', 'url': url}, room=sid)
    return (f'Evento "{title}" criado no Google Calendar, Senhor. '
            f'Data: {start_date.strftime("%d/%m/%Y as %H:%M")}.')


def _calendar_list_events(service, params, sid):
    count = int(params.get('count', 5))
    now   = datetime.datetime.utcnow().isoformat() + 'Z'
    events_result = service.events().list(
        calendarId='primary', timeMin=now, maxResults=count,
        singleEvents=True, orderBy='startTime'
    ).execute()
    events = events_result.get('items', [])
    if not events:
        return 'Sua agenda esta livre, Senhor.'
    lines = []
    for e in events:
        start = e['start'].get('dateTime', e['start'].get('date', ''))
        try:
            dt        = datetime.datetime.fromisoformat(start.replace('Z', '+00:00'))
            formatted = dt.strftime('%d/%m %H:%M')
        except Exception:
            formatted = start
        lines.append(f'• {formatted} — {e.get("summary", "Sem titulo")}')
    socketio.emit('action_result',
                  {'success': True, 'message': f'{len(events)} eventos encontrados'}, room=sid)
    return f'Seus proximos {len(events)} eventos, Senhor:\n' + '\n'.join(lines)


def _calendar_delete_event(service, params, sid):
    title = params.get('title', '')
    if not title:
        return 'Qual evento devo deletar, Senhor?'
    now   = datetime.datetime.utcnow().isoformat() + 'Z'
    events_result = service.events().list(
        calendarId='primary', timeMin=now, maxResults=20,
        singleEvents=True, orderBy='startTime', q=title
    ).execute()
    events = events_result.get('items', [])
    if not events:
        return f'Nao encontrei nenhum evento com "{title}", Senhor.'
    event = events[0]
    service.events().delete(calendarId='primary', eventId=event['id']).execute()
    socketio.emit('action_result',
                  {'success': True, 'message': f'Evento "{event["summary"]}" deletado'}, room=sid)
    return f'Evento "{event["summary"]}" deletado do calendario, Senhor.'


# =============================================================================
#  GOOGLE MAPS
# =============================================================================

def execute_google_maps(params: dict, sid: str) -> str:
    action = params.get('action', 'search')
    query  = params.get('query', '') or params.get('destination', '')
    origin = params.get('origin', '')
    socketio.emit('status_update', {'step': 'executing', 'message': 'Google Maps...'}, room=sid)
    try:
        if action in ('route', 'directions'):
            if not query:
                return 'Para onde deseja ir, Senhor?'
            base = 'https://www.google.com/maps/dir/'
            url  = f'{base}{origin}/{query}' if origin else f'{base}/{query}'
            webbrowser.open(url)
            socketio.emit('action_result',
                          {'success': True, 'message': f'Rota para {query}'}, room=sid)
            return f'Abrindo rota para {query} no Maps, Senhor.'
        else:
            if not query:
                return 'O que deseja buscar no Maps, Senhor?'
            url = f'https://www.google.com/maps/search/{quote_plus(query)}'
            webbrowser.open(url)
            socketio.emit('action_result',
                          {'success': True, 'message': f'Buscando: {query}'}, room=sid)
            return f'Abrindo "{query}" no Google Maps, Senhor.'
    except Exception as e:
        socketio.emit('action_result',
                      {'success': False, 'message': f'Erro Maps: {e}'}, room=sid)
        return f'Erro ao abrir Google Maps: {e}'


# =============================================================================
#  STATUS HELPERS
# =============================================================================

def is_google_authenticated() -> bool:
    try:
        from google.oauth2.credentials import Credentials
        if not _TOKEN_FILE.exists():
            return False
        creds = Credentials.from_authorized_user_file(str(_TOKEN_FILE), SCOPES)
        return creds and creds.valid
    except Exception:
        return False


def has_credentials_file() -> bool:
    return _CREDS_FILE.exists()


def get_active_sheet(sid: str) -> dict:
    """Retorna a planilha ativa da sessao, se houver."""
    return _active_sheets.get(sid, {})