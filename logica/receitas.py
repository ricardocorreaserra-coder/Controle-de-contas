"""
Regras de negócio relacionadas a receitas: lançamento, exclusão e
encerramento de recorrência.
"""

from datetime import datetime

from sheets.client import get_sheet, sheet_to_df, delete_rows_batch, append_linha_por_nome_id_unico
from sheets.loaders import carregar_receitas
from utils.datas import hoje_str
from utils.sessao import usuario_atual


def salvar_receita(desc, valor, data, cat, obs, recorrente=False, recorrencia_fim=None):
    ws = get_sheet("receitas")
    append_linha_por_nome_id_unico(ws, {
        "descricao": desc, "valor": valor, "data": data,
        "categoria": cat, "observacao": obs,
        "criado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "recorrente": "sim" if recorrente else "nao",
        "recorrencia_fim": recorrencia_fim.strftime("%Y-%m-%d") if recorrencia_fim else "",
        "lancado_por": usuario_atual(),
    })
    carregar_receitas.clear()


def excluir_receita(rid: int):
    ws = get_sheet("receitas")
    df = sheet_to_df(ws)
    if not df.empty:
        delete_rows_batch(ws, df[df["id"].astype(str) == str(rid)].index.tolist())
    carregar_receitas.clear()


def atualizar_receita(rid: int, desc: str, valor: float, data: str, cat: str, obs: str):
    """Edita descrição, valor, data, categoria e observação de uma receita
    já lançada. Não mexe em `recorrente`/`recorrencia_fim` — isso continua
    sendo gerenciado só pelo botão "Encerrar recorrência"."""
    ws = get_sheet("receitas")
    df = sheet_to_df(ws)
    for idx in df[df["id"].astype(str) == str(rid)].index.tolist():
        row_num = idx + 2
        ws.update_cell(row_num, df.columns.get_loc("descricao") + 1, desc)
        ws.update_cell(row_num, df.columns.get_loc("valor") + 1, valor)
        ws.update_cell(row_num, df.columns.get_loc("data") + 1, data)
        ws.update_cell(row_num, df.columns.get_loc("categoria") + 1, cat)
        ws.update_cell(row_num, df.columns.get_loc("observacao") + 1, obs)
    carregar_receitas.clear()


def encerrar_recorrencia_receita(rid: int):
    ws = get_sheet("receitas")
    df = sheet_to_df(ws)
    col_idx = df.columns.get_loc("recorrencia_fim") + 1
    hoje = hoje_str()
    for idx in df[df["id"].astype(str) == str(rid)].index.tolist():
        ws.update_cell(idx + 2, col_idx, hoje)
    carregar_receitas.clear()
