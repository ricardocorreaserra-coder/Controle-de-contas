"""Aba: Dashboard — visão geral do mês selecionado."""

from datetime import date

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from sheets.loaders import carregar_despesas, carregar_receitas
from utils.datas import seletor_mes_ano, add_months, fmt_mes_pt
from utils.formatacao import fmt_moeda, card_html


def render():
    st.markdown("##### Filtro de Período")
    mes_dash = seletor_mes_ano("dash")

    df_d = carregar_despesas()
    df_r = carregar_receitas()

    if not df_d.empty and "valor" in df_d.columns:
        df_d["valor"] = pd.to_numeric(df_d["valor"], errors='coerce').fillna(0.0)
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
        fig1.update_layout(barmode="group", height=300, template="plotly_white", separators=',.',
                           margin=dict(t=10, b=10, l=10, r=10),
                           legend=dict(orientation="h", y=-0.2))
        st.plotly_chart(fig1, use_container_width=True)

    with col2:
        st.subheader("Despesas por categoria")
        if not desp_mes.empty and "categoria" in desp_mes.columns:
            grp = desp_mes.groupby("categoria")["valor"].sum().reset_index()
            grp.columns = ["Categoria", "Valor"]
            fig2 = px.pie(grp, values="Valor", names="Categoria", hole=0.4, height=300,
                          color_discrete_sequence=px.colors.qualitative.Set2)
            fig2.update_traces(textinfo='percent+label', hovertemplate='<b>%{label}</b><br>Valor: R$ %{value:,.2f}<extra></extra>')
            fig2.update_layout(template="plotly_white", separators=',.', margin=dict(t=10, b=10, l=10, r=10))
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Sem dados para o período.")

    with col3:
        st.subheader("Por pagamento")
        if not desp_mes.empty and "pagamento" in desp_mes.columns:
            grp2 = desp_mes.groupby("pagamento")["valor"].sum().reset_index()
            grp2.columns = ["Pagamento", "Valor"]
            fig3 = px.pie(grp2, values="Valor", names="Pagamento", hole=0.4, height=300,
                          color_discrete_sequence=px.colors.qualitative.Pastel)
            fig3.update_traces(textinfo='percent+label', hovertemplate='<b>%{label}</b><br>Valor: R$ %{value:,.2f}<extra></extra>')
            fig3.update_layout(template="plotly_white", separators=',.', margin=dict(t=10, b=10, l=10, r=10))
            st.plotly_chart(fig3, use_container_width=True)
        else:
            st.info("Sem dados para o período.")
