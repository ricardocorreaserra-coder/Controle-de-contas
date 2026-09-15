"""
Regras de negócio relacionadas a receitas: lançamento, exclusão e
encerramento de recorrência.
"""

from datetime import datetime

from sheets.client import get_sheet, sheet_to_df, delete_rows_batch, append_row_id_unico
from sheets.loaders import carregar_receitas
from utils.datas import hoje_str
from utils.sessao import usuario_atual


def salvar_receita(desc, valor, data, cat, obs, recorrente=False, recorrencia_fim=None):
    ws = get_sheet("receitas")
    append_row_id_unico(ws, [desc, valor, data, cat, obs,
                             datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                             "sim" if recorrente else "nao",
                             recorrencia_fim.strftime("%Y-%m-%d") if recorrencia_fim else "",
                             usuario_atual()])
    carregar_receitas.clear()


def excluir_receita(rid: int):
    ws = get_sheet("receitas")
    df = sheet_to_df(ws)
    if not df.empty:
        delete_rows_batch(ws, df[df["id"].astype(str) == str(rid)].index.tolist())
    carregar_receitas.clear()


def encerrar_recorrencia_receita(rid: int):
    ws = get_sheet("receitas")
    df = sheet_to_df(ws)
    col_idx = df.columns.get_loc("recorrencia_fim") + 1
    hoje = hoje_str()
    for idx in df[df["id"].astype(str) == str(rid)].index.tolist():
        ws.update_cell(idx + 2, col_idx, hoje)
    carregar_receitas.clear()
