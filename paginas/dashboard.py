"""Aba: Dashboard — visão geral do mês selecionado."""

from datetime import date

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from sheets.loaders import carregar_despesas, carregar_receitas
from logica.despesas import despesa_esta_pendente
from utils.datas import seletor_mes_ano, add_months, fmt_mes_pt
from utils.formatacao import fmt_moeda, card_html


def _rosquinha(grp: pd.DataFrame, coluna_nomes: str, cores):
    """
    Rosquinha (pizza com furo) usada nos gráficos por categoria e por pagamento.

    Rótulo da fatia: só o PERCENTUAL. O nome da categoria fica na legenda
    (abaixo do gráfico) e no hover. Antes cada fatia mostrava "nome + %", e
    nas fatias pequenas esse texto longo era jogado para fora da rosquinha e
    cortado na borda do gráfico ("ducação", "porte"). `automargin=True` deixa o
    Plotly abrir a margem sozinho se algum rótulo ainda ficar para fora.
    NÃO passar `template=` aqui — o padrão do Streamlit já segue o tema.
    """
    fig = px.pie(grp, values="Valor", names=coluna_nomes, hole=0.4, height=300,
                 color_discrete_sequence=cores)
    fig.update_traces(
        textinfo="percent", textposition="auto",
        insidetextorientation="horizontal", automargin=True,
        hovertemplate="<b>%{label}</b><br>Valor: R$ %{value:,.2f}<extra></extra>",
    )
    fig.update_layout(separators=",.", margin=dict(t=10, b=10, l=10, r=10),
                      legend=dict(orientation="h", y=-0.15))
    return fig


def render():
    st.markdown("##### Filtro de Período")
    mes_dash = seletor_mes_ano("dash")

    df_d = carregar_despesas()
    df_r = carregar_receitas()

    if not df_d.empty and "valor" in df_d.columns:
        df_d["valor"] = pd.to_numeric(df_d["valor"], errors='coerce').fillna(0.0)
    if not df_d.empty and "status" in df_d.columns:
        # B-04 · despesas pendentes (ex.: conta de luz ainda não debitada)
        # ficam fora do Dashboard até serem baixadas — ver logica/despesas.py.
        df_d = df_d[~df_d["status"].apply(despesa_esta_pendente)]
    if not df_r.empty and "valor" in df_r.columns:
        df_r["valor"] = pd.to_numeric(df_r["valor"], errors='coerce').fillna(0.0)

    desp_mes = df_d[df_d["data"].astype(str).str.startswith(mes_dash)] if not df_d.empty else pd.DataFrame()
    rec_mes  = df_r[df_r["data"].astype(str).str.startswith(mes_dash)]  if not df_r.empty else pd.DataFrame()

    total_rec  = float(rec_mes["valor"].sum())  if not rec_mes.empty  else 0.0
    total_desp = float(desp_mes["valor"].sum()) if not desp_mes.empty else 0.0
    saldo      = total_rec - total_desp
    saldo_cor  = "green" if saldo >= 0 else "red"

    c1, c2, c3 = st.columns(3)
    with c1: st.markdown(card_html("Receitas do mês", fmt_moeda(total_rec),  "green"),   unsafe_allow_html=True)
    with c2: st.markdown(card_html("Despesas do mês", fmt_moeda(total_desp), "red"),     unsafe_allow_html=True)
    with c3: st.markdown(card_html("Saldo do mês",    fmt_moeda(saldo),      saldo_cor), unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.subheader("Histórico 6 meses")
        hist = []
        for i in range(5, -1, -1):
            d   = date.today()
            mm  = add_months(d, -i).strftime("%Y-%m")
            lbl = fmt_mes_pt(add_months(d, -i))
            r_val = float(df_r[df_r["data"].astype(str).str.startswith(mm)]["valor"].sum()) if not df_r.empty else 0.0
            e_val = float(df_d[df_d["data"].astype(str).str.startswith(mm)]["valor"].sum()) if not df_d.empty else 0.0
            hist.append({"Mês": lbl, "Receita": r_val, "Despesa": e_val})
        df_hist = pd.DataFrame(hist)
        fig1 = go.Figure()
        fig1.add_bar(x=df_hist["Mês"], y=df_hist["Receita"], name="Receita", marker_color="#16a34a",
                     hovertemplate='Receita: R$ %{y:,.2f}<extra></extra>')
        fig1.add_bar(x=df_hist["Mês"], y=df_hist["Despesa"], name="Despesa", marker_color="#dc2626",
                     hovertemplate='Despesa: R$ %{y:,.2f}<extra></extra>')
        fig1.update_layout(barmode="group", height=300, separators=',.',
                           margin=dict(t=10, b=10, l=10, r=10),
                           legend=dict(orientation="h", y=-0.2))
        st.plotly_chart(fig1, use_container_width=True)

    with col2:
        st.subheader("Despesas por categoria")
        if not desp_mes.empty and "categoria" in desp_mes.columns:
            grp = desp_mes.groupby("categoria")["valor"].sum().reset_index()
            grp.columns = ["Categoria", "Valor"]
            fig2 = _rosquinha(grp, "Categoria", px.colors.qualitative.Set2)
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Sem dados para o período.")

    with col3:
        st.subheader("Por pagamento")
        if not desp_mes.empty and "pagamento" in desp_mes.columns:
            grp2 = desp_mes.groupby("pagamento")["valor"].sum().reset_index()
            grp2.columns = ["Pagamento", "Valor"]
            fig3 = _rosquinha(grp2, "Pagamento", px.colors.qualitative.Pastel)
            st.plotly_chart(fig3, use_container_width=True)
        else:
            st.info("Sem dados para o período.")
