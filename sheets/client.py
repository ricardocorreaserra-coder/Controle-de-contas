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
    data = ws.get_all_records()
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
