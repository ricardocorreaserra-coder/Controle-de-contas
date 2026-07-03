"""Aba: ☰ Despesas — listagem, filtros e exclusão."""

import pandas as pd
import streamlit as st

from config import CAT_DESP, PAGAMENTOS
from sheets.loaders import carregar_despesas
from logica.despesas import excluir_despesa
from utils.datas import seletor_mes_ano
from utils.formatacao import fmt_moeda, card_html, converter_data_para_exibicao


def render():
    st.subheader("Despesas")
    st.markdown("##### Filtros de visualização")
    fmes = seletor_mes_ano("lista")

    f1, f2 = st.columns(2)
    fpag = f1.selectbox("Pagamento", ["Todos"] + PAGAMENTOS, key="fpag_lista")
    fcat = f2.selectbox("Categoria", ["Todas"] + CAT_DESP,  key="fcat_lista")

    df_d = carregar_despesas()
    if df_d.empty:
        st.info("Nenhuma despesa cadastrada.")
        return

    df_d["valor"] = pd.to_numeric(df_d["valor"], errors='coerce').fillna(0.0)
    mask = df_d["data"].astype(str).str.startswith(fmes)
    if fpag != "Todos": mask &= df_d["pagamento"] == fpag
    if fcat != "Todas": mask &= df_d["categoria"] == fcat
    df_filtrado = df_d[mask].copy()

    total = float(df_filtrado["valor"].sum()) if not df_filtrado.empty else 0.0
    cc_v  = float(df_filtrado[df_filtrado["pagamento"] == "Cartão de crédito"]["valor"].sum()) if not df_filtrado.empty else 0.0
    c1, c2, c3 = st.columns(3)
    with c1: st.markdown(card_html("Total",   fmt_moeda(total),        "blue"),  unsafe_allow_html=True)
    with c2: st.markdown(card_html("Crédito", fmt_moeda(cc_v),         "blue"),  unsafe_allow_html=True)
    with c3: st.markdown(card_html("Outros",  fmt_moeda(total - cc_v), "green"), unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    if df_filtrado.empty:
        st.info("Nenhuma despesa no período selecionado.")
        return

    df_show = df_filtrado[["id", "descricao", "valor", "data", "local",
                            "pagamento", "categoria", "n_parcelas", "observacao"]].copy()
    df_show["valor"] = df_show["valor"].apply(fmt_moeda)
    df_show["data"]  = df_show["data"].apply(converter_data_para_exibicao)
    df_show.columns  = ["ID", "Descrição", "Valor", "Data", "Local",
                         "Pagamento", "Categoria", "Parcelas", "Obs"]

    event_d = st.dataframe(df_show, use_container_width=True, hide_index=True,
                           on_select="rerun", selection_mode="single-row")

    st.markdown("#### Ações")
    if event_d.selection.rows:
        idx_sel      = event_d.selection.rows[0]
        id_excluir   = int(df_filtrado.iloc[idx_sel]["id"])
        desc_excluir = df_filtrado.iloc[idx_sel]["descricao"]
        val_excluir  = fmt_moeda(df_filtrado.iloc[idx_sel]["valor"])
        st.warning(f"⚠️ Despesa selecionada: **#{id_excluir} — {desc_excluir} ({val_excluir})**")
        st.caption("Esta ação também excluirá todas as parcelas vinculadas a esta despesa.")

        # Item 2 · Confirmação explícita antes de excluir despesa
        confirmar_d = st.checkbox(
            f"Confirmo a exclusão da despesa #{id_excluir}",
            key=f"confirmar_excl_desp_{id_excluir}"
        )
        if confirmar_d:
            if st.button("🗑 Excluir despesa", type="primary", use_container_width=True, key="btn_excl_desp"):
                try:
                    excluir_despesa(id_excluir)
                    st.success(f"Despesa #{id_excluir} excluída com sucesso!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao excluir: {e}")
        else:
            st.button("🗑 Excluir despesa", type="primary", use_container_width=True,
                      disabled=True, key="btn_excl_desp_dis")
    else:
        st.info("💡 Clique em uma linha na tabela acima para liberar as ações de exclusão.")
