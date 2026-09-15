"""
Regras de negócio relacionadas a despesas: lançamento (com geração
automática de parcelas quando pago no cartão), exclusão e encerramento
de recorrência.
"""

from datetime import datetime

import pandas as pd

from config import DIA_VENCIMENTO_PADRAO
from sheets.client import (
    get_sheet, sheet_to_df, delete_rows_batch,
    append_row_id_unico, append_rows_ids_unicos,
)
from sheets.loaders import carregar_cartoes, carregar_despesas, carregar_parcelas
from logica.cartoes import resolver_vencimento_parcela
from logica.fechamentos import fechamentos_ordenados_por_cartao
from logica.parcelas import valores_parcelas
from utils.datas import hoje_str
from utils.sessao import usuario_atual


def salvar_despesa(desc, valor, data, local, pag, cat, cartao, n_parc, obs,
                    recorrente=False, recorrencia_fim=None):
    ws_d = get_sheet("despesas")
    ws_p = get_sheet("parcelas")
    # append_row_id_unico devolve o id realmente gravado — pode diferir do
    # calculado se outra pessoa gravou ao mesmo tempo. É esse id que precisa
    # ser usado para vincular as parcelas abaixo.
    did = append_row_id_unico(ws_d, [
        desc, valor, data, local, pag, cat,
        cartao or "", n_parc, obs,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sim" if recorrente else "nao",
        recorrencia_fim.strftime("%Y-%m-%d") if recorrencia_fim else "",
        usuario_atual(),
    ])
    if pag == "Cartão de crédito":
        df_c = carregar_cartoes()
        card_info = df_c[df_c["nome"] == cartao] if not df_c.empty else pd.DataFrame()
        if not card_info.empty:
            df_fechamento = int(card_info.iloc[0]["dia_fechamento"])
            df_vencimento = int(card_info.iloc[0]["dia_vencimento"])
        else:
            df_fechamento = DIA_VENCIMENTO_PADRAO
            df_vencimento = DIA_VENCIMENTO_PADRAO
        base = datetime.strptime(data, "%Y-%m-%d").date()
        valores = valores_parcelas(valor, n_parc)  # B-03 · soma exata ao valor total
        # Prioriza fechamentos reais já registrados manualmente para este
        # cartão; só recai na estimativa automática (dia fixo do mês) para
        # os meses ainda não confirmados — ver logica/fechamentos.py.
        fechamentos = fechamentos_ordenados_por_cartao(cartao)
        rows = []
        for i in range(n_parc):
            venc, origem = resolver_vencimento_parcela(
                base, df_fechamento, df_vencimento, i + 1, fechamentos
            )
            rows.append([did, i + 1, n_parc, valores[i],
                         venc.strftime("%Y-%m-%d"), "pendente", desc, cartao, origem])
        append_rows_ids_unicos(ws_p, rows)
    carregar_despesas.clear()
    carregar_parcelas.clear()


def excluir_despesa(did: int):
    ws_d = get_sheet("despesas")
    ws_p = get_sheet("parcelas")
    df_p = sheet_to_df(ws_p)
    if not df_p.empty and "despesa_id" in df_p.columns:
        delete_rows_batch(ws_p, df_p[df_p["despesa_id"].astype(str) == str(did)].index.tolist())
    df_d = sheet_to_df(ws_d)
    if not df_d.empty:
        delete_rows_batch(ws_d, df_d[df_d["id"].astype(str) == str(did)].index.tolist())
    carregar_despesas.clear()
    carregar_parcelas.clear()


def encerrar_recorrencia_despesa(did: int):
    ws = get_sheet("despesas")
    df = sheet_to_df(ws)
    col_idx = df.columns.get_loc("recorrencia_fim") + 1
    hoje = hoje_str()
    for idx in df[df["id"].astype(str) == str(did)].index.tolist():
        ws.update_cell(idx + 2, col_idx, hoje)
    carregar_despesas.clear()
