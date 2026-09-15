"""
Regras de negócio relacionadas a parcelas de cartão: divisão de valores,
lançamento manual de parcelas históricas, atualização de status e baixa
de fatura em lote.
"""

import calendar
from datetime import datetime

import gspread
import pandas as pd

from config import DIA_VENCIMENTO_PADRAO
from sheets.client import get_sheet, sheet_to_df, append_rows_ids_unicos
from sheets.loaders import carregar_cartoes, carregar_parcelas
from utils.datas import add_months


def valores_parcelas(valor_total: float, n_parc: int) -> list:
    """
    B-03 · Divide o valor total em n_parc parcelas, garantindo que a soma
    bata exatamente com o valor total (a última parcela absorve o resto
    do arredondamento).
    """
    base = round(valor_total / n_parc, 2)
    valores = [base] * n_parc
    diferenca = round(valor_total - base * n_parc, 2)
    valores[-1] = round(valores[-1] + diferenca, 2)
    return valores


def salvar_parcela_manual(cartao, desc, valor_parcela, num_inicial, num_total, vencimento_inicial, obs):
    """
    Lança parcelas de compras anteriores ao uso do app. Como a data foi
    digitada diretamente pelo usuário (não calculada), a origem já nasce
    'manual' — não há estimativa envolvida aqui.
    """
    ws_p = get_sheet("parcelas")
    df_c = carregar_cartoes()
    card_info     = df_c[df_c["nome"] == cartao] if not df_c.empty else pd.DataFrame()
    df_vencimento = int(card_info.iloc[0]["dia_vencimento"]) if not card_info.empty else DIA_VENCIMENTO_PADRAO
    base_date = datetime.strptime(vencimento_inicial, "%Y-%m-%d").date()
    rows = []
    for i in range(num_total - num_inicial + 1):
        venc    = add_months(base_date, i)
        max_day = calendar.monthrange(venc.year, venc.month)[1]
        venc    = venc.replace(day=min(df_vencimento, max_day))
        rows.append([-1, num_inicial + i, num_total, valor_parcela,
                     venc.strftime("%Y-%m-%d"), "pendente", desc, cartao, "manual"])
    append_rows_ids_unicos(ws_p, rows)
    carregar_parcelas.clear()


def atualizar_vencimento_parcela(pid: int, nova_data):
    """
    Corrige manualmente o vencimento de uma parcela específica — por
    exemplo, quando o fechamento real da fatura acabou sendo diferente da
    estimativa automática e ainda não havia um fechamento registrado no
    momento da compra. A parcela passa a ter origem 'manual'.
    """
    ws = get_sheet("parcelas")
    df = sheet_to_df(ws)
    col_venc = df.columns.get_loc("vencimento") + 1
    tem_origem = "origem_vencimento" in df.columns
    col_origem = df.columns.get_loc("origem_vencimento") + 1 if tem_origem else None
    for idx in df[df["id"].astype(str) == str(pid)].index.tolist():
        ws.update_cell(idx + 2, col_venc, nova_data.strftime("%Y-%m-%d"))
        if col_origem:
            ws.update_cell(idx + 2, col_origem, "manual")
    carregar_parcelas.clear()


def atualizar_parcela(pid: int, status: str):
    ws = get_sheet("parcelas")
    df = sheet_to_df(ws)
    for idx in df[df["id"].astype(str) == str(pid)].index.tolist():
        ws.update_cell(idx + 2, df.columns.get_loc("status") + 1, status)
    carregar_parcelas.clear()


def baixar_fatura_mes(mes: str, cartao_filtro: str = None):
    ws   = get_sheet("parcelas")
    ws_d = get_sheet("despesas")
    df_p = sheet_to_df(ws)
    df_d = sheet_to_df(ws_d)
    if df_p.empty:
        return 0
    df_p_full = df_p.copy()
    if not df_d.empty:
        df_d_sub = df_d[["id", "cartao"]].rename(columns={"id": "despesa_id", "cartao": "cartao_dep"})
        df_p_full = df_p_full.merge(df_d_sub, on="despesa_id", how="left")
        df_p_full["cartao"] = df_p_full.apply(
            lambda r: r["cartao_dep"] if pd.notna(r.get("cartao_dep")) and r["cartao_dep"] != "" else r.get("cartao", ""),
            axis=1
        )
    mask = (df_p_full["vencimento"].astype(str).str.startswith(mes)) & \
           (df_p_full["status"] == "pendente")
    if cartao_filtro and cartao_filtro != "Todos":
        mask = mask & (df_p_full["cartao"] == cartao_filtro)
    idxs = df_p_full[mask].index.tolist()
    if not idxs:
        return 0
    col_idx    = df_p.columns.get_loc("status") + 1
    range_data = [{'range': gspread.utils.rowcol_to_a1(idx + 2, col_idx), 'values': [['pago']]} for idx in idxs]
    ws.batch_update(range_data)
    carregar_parcelas.clear()
    return len(idxs)
