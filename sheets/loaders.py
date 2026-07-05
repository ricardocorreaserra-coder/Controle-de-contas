"""
Funções de carregamento de dados (com @st.cache_data), usadas em todo o app.

IMPORTANTE (cache do Streamlit): assim como em `sheets/client.py`, cada
função abaixo é definida uma única vez neste módulo. Qualquer código que
precise ler dados ou invalidar o cache (`.clear()`) deve IMPORTAR a função
daqui — nunca recriar uma função equivalente em outro arquivo, pois isso
geraria um cache separado e desincronizado do original.
"""

from datetime import datetime

import streamlit as st

from sheets.client import get_sheet, sheet_to_df


@st.cache_data(ttl=300)
def carregar_cartoes():
    ws = get_sheet("cartoes")
    df = sheet_to_df(ws)
    if df.empty:
        default_cards = [
            [1, "Nubank",    5000,  5, 12, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
            [2, "Itaú",      5000, 10, 17, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
            [3, "Bradesco",  5000, 15, 22, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
            [4, "Inter",     5000, 20, 27, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
            [5, "Santander", 5000, 25,  2, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
            [6, "Outro",     5000, 10, 17, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
        ]
        ws.append_rows(default_cards)
        carregar_cartoes.clear()
        df = sheet_to_df(ws)
    return df


@st.cache_data(ttl=300)
def carregar_despesas():
    return sheet_to_df(get_sheet("despesas"))


@st.cache_data(ttl=300)
def carregar_receitas():
    return sheet_to_df(get_sheet("receitas"))


@st.cache_data(ttl=300)
def carregar_parcelas():
    return sheet_to_df(get_sheet("parcelas"))


@st.cache_data(ttl=300)
def carregar_planejamento():
    return sheet_to_df(get_sheet("planejamento"))


@st.cache_data(ttl=300)
def carregar_fechamentos():
    """
    Fechamentos reais de fatura, registrados manualmente por cartão/mês.
    Fonte de verdade usada por logica.cartoes.resolver_vencimento_parcela
    para saber em qual fatura uma compra realmente cai — a data de
    fechamento não é confiável como "dia fixo do mês", pois varia mês a mês.
    """
    return sheet_to_df(get_sheet("fechamentos"))


@st.cache_data(ttl=300)
def carregar_emprestimos():
    """
    Empréstimos — aba isolada de consulta e controle. Nenhuma outra função
    de carregamento (despesas, planejamento, dashboard) lê esta tabela, e
    ela nunca deve ser somada em relatórios de outras abas.
    """
    return sheet_to_df(get_sheet("emprestimos"))


def obter_nomes_cartoes() -> list:
    try:
        df_c = carregar_cartoes()
        if not df_c.empty and "nome" in df_c.columns:
            return df_c["nome"].tolist()
    except Exception:
        pass
    return ["Nubank", "Itaú", "Bradesco", "Inter", "Santander", "Outro"]