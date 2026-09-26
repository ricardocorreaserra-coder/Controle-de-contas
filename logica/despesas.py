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
    append_linha_por_nome_id_unico, append_linhas_por_nome_ids_unicos,
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
    # append_linha_por_nome_id_unico devolve o id realmente gravado — pode
    # diferir do calculado se outra pessoa gravou ao mesmo tempo. É esse id
    # que precisa ser usado para vincular as parcelas abaixo. A escrita é
    # por NOME de coluna (não por posição), para nunca depender da ordem
    # física real das colunas na planilha.
    did = append_linha_por_nome_id_unico(ws_d, {
        "descricao": desc, "valor": valor, "data": data, "local": local,
        "pagamento": pag, "categoria": cat, "cartao": cartao or "",
        "n_parcelas": n_parc, "observacao": obs,
        "criado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "recorrente": "sim" if recorrente else "nao",
        "recorrencia_fim": recorrencia_fim.strftime("%Y-%m-%d") if recorrencia_fim else "",
        "lancado_por": usuario_atual(),
    })
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
            rows.append({
                "despesa_id": did, "numero": i + 1, "total": n_parc,
                "valor": valores[i], "vencimento": venc.strftime("%Y-%m-%d"),
                "status": "pendente", "descricao": desc, "cartao": cartao,
                "origem_vencimento": origem,
            })
        append_linhas_por_nome_ids_unicos(ws_p, rows)
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


def atualizar_despesa(did: int, desc: str, valor: float, data: str, local: str, cat: str, obs: str):
    """
    Edita os campos "seguros" de uma despesa já lançada — descrição, valor,
    data, local, categoria e observação. NÃO mexe em `pagamento`, `cartao`,
    `n_parcelas` nem `recorrente`: mudar a forma de pagamento depois que as
    parcelas de cartão já foram geradas exigiria reconstruir tudo, então
    quem precisar disso deve excluir e relançar a despesa.

    Se a despesa for no cartão de crédito e o valor for alterado aqui, o
    total das parcelas já geradas NÃO é recalculado automaticamente — a
    tela avisa isso antes de salvar (ver paginas/lista_despesas.py).
    """
    ws = get_sheet("despesas")
    df = sheet_to_df(ws)
    for idx in df[df["id"].astype(str) == str(did)].index.tolist():
        row_num = idx + 2
        ws.update_cell(row_num, df.columns.get_loc("descricao") + 1, desc)
        ws.update_cell(row_num, df.columns.get_loc("valor") + 1, valor)
        ws.update_cell(row_num, df.columns.get_loc("data") + 1, data)
        ws.update_cell(row_num, df.columns.get_loc("local") + 1, local)
        ws.update_cell(row_num, df.columns.get_loc("categoria") + 1, cat)
        ws.update_cell(row_num, df.columns.get_loc("observacao") + 1, obs)
    carregar_despesas.clear()


def encerrar_recorrencia_despesa(did: int):
    ws = get_sheet("despesas")
    df = sheet_to_df(ws)
    col_idx = df.columns.get_loc("recorrencia_fim") + 1
    hoje = hoje_str()
    for idx in df[df["id"].astype(str) == str(did)].index.tolist():
        ws.update_cell(idx + 2, col_idx, hoje)
    carregar_despesas.clear()
