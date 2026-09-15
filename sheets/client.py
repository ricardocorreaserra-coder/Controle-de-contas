"""
Camada de acesso ao Google Sheets: autenticação, obtenção de planilhas
e conversão para DataFrame.

IMPORTANTE (cache do Streamlit): as funções decoradas com @st.cache_resource
e @st.cache_data DEVEM ser definidas apenas UMA VEZ, aqui e nos módulos de
`sheets/loaders.py`. O cache do Streamlit é associado ao objeto de função em
si (não ao arquivo/local de importação), então todo o resto do projeto deve
sempre IMPORTAR estas funções — nunca redefini-las ou recriar uma cópia do
decorator em outro lugar. Isso garante que `.clear()` chamado a partir de
qualquer módulo realmente invalide o mesmo cache compartilhado.
"""

import pandas as pd
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

from config import SCOPES, EXPECTED_HEADERS


@st.cache_resource(ttl=600)
def get_sheets_client():
    creds_dict = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)


@st.cache_resource(ttl=600)
def get_workbook():
    client = get_sheets_client()
    return client.open(st.secrets["SHEET_NAME"])


def _migrar_headers_se_preciso(ws, nome: str):
    """Garante que a planilha tenha todas as colunas esperadas, sem desalinhar dados existentes."""
    esperados = EXPECTED_HEADERS.get(nome)
    if not esperados:
        return
    atuais = ws.row_values(1)
    if not atuais:
        return
    faltando = [h for h in esperados if h not in atuais]
    if faltando:
        novos_headers = atuais + faltando
        ws.update('A1', [novos_headers])


def get_sheet(name: str):
    from datetime import datetime  # import local para evitar custo em quem só lê planilhas existentes
    wb = get_workbook()
    try:
        ws = wb.worksheet(name)
        _migrar_headers_se_preciso(ws, name)
        return ws
    except gspread.WorksheetNotFound:
        ws = wb.add_worksheet(title=name, rows=1000, cols=20)
        if name in EXPECTED_HEADERS:
            ws.append_row(EXPECTED_HEADERS[name])
        if name == "cartoes":
            default_cards = [
                [1, "Nubank",    5000,  5, 12, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
                [2, "Itaú",      5000, 10, 17, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
                [3, "Bradesco",  5000, 15, 22, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
                [4, "Inter",     5000, 20, 27, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
                [5, "Santander", 5000, 25,  2, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
                [6, "Outro",     5000, 10, 17, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
            ]
            ws.append_rows(default_cards)
        return ws


def sheet_to_df(ws) -> pd.DataFrame:
    # B-04 · value_render_option="UNFORMATTED_VALUE": sem isso, o gspread
    # busca os valores como exibidos na tela (ex.: "66,35", no formato BR
    # da planilha) e depois tenta reconverter para número assumindo padrão
    # americano — remove a vírgula pensando ser separador de milhar, e
    # "66,35" vira 6635. Com UNFORMATTED_VALUE, a API devolve o número puro
    # (66.35) direto, sem depender de locale nem da conversão do gspread.
    data = ws.get_all_records(value_render_option="UNFORMATTED_VALUE")
    df = pd.DataFrame(data) if data else pd.DataFrame()
    name = ws.title
    if name in EXPECTED_HEADERS:
        for col in EXPECTED_HEADERS[name]:
            if col not in df.columns:
                df[col] = ""
    return df


def next_id(ws) -> int:
    df = sheet_to_df(ws)
    if df.empty or "id" not in df.columns or df["id"].astype(str).str.strip().eq("").all():
        return 1
    ids = pd.to_numeric(df["id"], errors='coerce').fillna(0).astype(int)
    return int(ids.max()) + 1


# ── Escrita com ID único (proteção contra uso simultâneo) ─────────────────────
#
# PROBLEMA: `next_id` lê o maior ID e soma 1. Se duas pessoas salvarem quase
# ao mesmo tempo (acesso compartilhado por casal/família), ambas leem o mesmo
# "último ID" e gravam linhas com o MESMO id — o que faz uma exclusão apagar
# os dois registros de uma vez.
#
# SOLUÇÃO: depois de gravar, conferir se o ID escolhido acabou duplicado. Em
# caso de empate, quem gravou na linha mais abaixo cede e regrava o próprio
# ID. As duas funções de decisão (`numero_linha_do_range` e
# `resolver_colisao_id`) são puras e testadas isoladamente.

def numero_linha_do_range(updated_range) -> int:
    """
    Extrai o número da primeira linha de um range devolvido pela API do
    Sheets (ex.: "despesas!A6:I6" -> 6). Devolve None se não conseguir
    interpretar — nesse caso quem chama simplesmente não faz a checagem
    de colisão, mantendo o comportamento antigo.
    """
    if not updated_range:
        return None
    texto = str(updated_range).split("!")[-1]
    inicio = texto.split(":")[0]
    digitos = "".join(ch for ch in inicio if ch.isdigit())
    return int(digitos) if digitos else None


def resolver_colisao_id(ids_coluna: list, meu_id: int, minha_linha: int) -> int:
    """
    Decide se a linha `minha_linha` precisa trocar de ID.

    `ids_coluna` é a coluna A inteira, como devolvida por `ws.col_values(1)`
    (inclui o cabeçalho na posição 0, então a linha N está no índice N-1).

    Devolve None quando não há colisão (ou quando esta linha é a primeira
    ocorrência do ID e portanto tem direito de mantê-lo). Devolve um ID novo,
    maior que todos os existentes, quando esta linha precisa ceder.
    """
    linhas_com_meu_id = [
        pos + 1 for pos, valor in enumerate(ids_coluna)
        if str(valor).strip() == str(meu_id)
    ]
    if len(linhas_com_meu_id) <= 1 or minha_linha == min(linhas_com_meu_id):
        return None
    numericos = [
        int(v) for v in ids_coluna
        if str(v).strip().lstrip("-").isdigit()
    ]
    return (max(numericos) + 1) if numericos else 1


def _corrigir_id_se_colidiu(ws, id_gravado: int, linha: int) -> int:
    """Relê a coluna de IDs e regrava o ID desta linha se ele colidiu.
    Devolve o ID final (o original ou o corrigido)."""
    if linha is None:
        return id_gravado
    try:
        novo = resolver_colisao_id(ws.col_values(1), id_gravado, linha)
    except Exception:
        return id_gravado
    if novo is None:
        return id_gravado
    ws.update_cell(linha, 1, novo)
    return novo


def append_row_id_unico(ws, valores_sem_id: list) -> int:
    """
    Acrescenta uma linha cujo primeiro campo é o `id`, garantindo que esse
    id não fique duplicado mesmo se outra pessoa gravar ao mesmo tempo.
    Devolve o ID efetivamente gravado (pode diferir do inicial se houve
    colisão) — importante para vincular registros filhos, como as parcelas
    de uma despesa.
    """
    id_inicial = next_id(ws)
    resposta = ws.append_row([id_inicial] + list(valores_sem_id))
    linha = numero_linha_do_range(
        (resposta or {}).get("updates", {}).get("updatedRange")
    )
    return _corrigir_id_se_colidiu(ws, id_inicial, linha)


def append_rows_ids_unicos(ws, linhas_sem_id: list) -> list:
    """
    Versão em lote de `append_row_id_unico`: recebe as linhas SEM o id e
    atribui ids sequenciais a partir do próximo disponível, conferindo
    colisão linha a linha depois da escrita. Devolve a lista de ids
    efetivamente gravados, na mesma ordem.
    """
    if not linhas_sem_id:
        return []
    id_base = next_id(ws)
    payload = [[id_base + i] + list(valores) for i, valores in enumerate(linhas_sem_id)]
    resposta = ws.append_rows(payload)
    primeira_linha = numero_linha_do_range(
        (resposta or {}).get("updates", {}).get("updatedRange")
    )
    if primeira_linha is None:
        return [linha[0] for linha in payload]
    return [
        _corrigir_id_se_colidiu(ws, id_base + i, primeira_linha + i)
        for i in range(len(payload))
    ]


def delete_rows_batch(ws, indices):
    """Deleta várias linhas do Google Sheets em uma única requisição em lote."""
    if not indices:
        return
    sorted_indices = sorted(indices, reverse=True)
    sheet_id = ws.id
    requests = []
    for idx in sorted_indices:
        row_num = idx + 1
        requests.append({
            "deleteDimension": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "ROWS",
                    "startIndex": row_num,
                    "endIndex": row_num + 1
                }
            }
        })
    ws.spreadsheet.batch_update({"requests": requests})