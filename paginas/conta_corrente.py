"""Aba: 🏦 Conta Corrente — extrato consolidado de receitas e despesas."""

import pandas as pd
import streamlit as st

from sheets.loaders import carregar_despesas, carregar_receitas
from logica.receitas import excluir_receita
from utils.datas import seletor_mes_ano
from utils.formatacao import fmt_moeda, card_html, converter_data_para_exibicao


def render():
    st.subheader("Conta Corrente")
    st.markdown("##### Filtro de Período")
    mes_cc = seletor_mes_ano("cc")

    df_d = carregar_despesas()
    df_r = carregar_receitas()

    if not df_d.empty and "valor" in df_d.columns:
        df_d["valor"] = pd.to_numeric(df_d["valor"], errors='coerce').fillna(0.0)
    if not df_r.empty and "valor" in df_r.columns:
        df_r["valor"] = pd.to_numeric(df_r["valor"], errors='coerce').fillna(0.0)

    desp_cc = df_d[df_d["data"].astype(str).str.startswith(mes_cc)] if not df_d.empty else pd.DataFrame()
    rec_cc  = df_r[df_r["data"].astype(str).str.startswith(mes_cc)]  if not df_r.empty else pd.DataFrame()

    total_rec_cc  = float(rec_cc["valor"].sum())  if not rec_cc.empty  else 0.0
    total_desp_cc = float(desp_cc["valor"].sum()) if not desp_cc.empty else 0.0
    saldo_cc      = total_rec_cc - total_desp_cc
    saldo_cor_cc  = "green" if saldo_cc >= 0 else "red"

    m1, m2, m3 = st.columns(3)
    with m1: st.markdown(card_html("Total receitas",  fmt_moeda(total_rec_cc),  "green"),      unsafe_allow_html=True)
    with m2: st.markdown(card_html("Total despesas",  fmt_moeda(total_desp_cc), "red"),        unsafe_allow_html=True)
    with m3: st.markdown(card_html("Saldo acumulado", fmt_moeda(saldo_cc),      saldo_cor_cc), unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    movs = []
    if not rec_cc.empty:
        for _, row in rec_cc.iterrows():
            movs.append({"Data": row["data"], "Descrição": row["descricao"], "Tipo": "Receita",
                         "Categoria": row.get("categoria", ""), "Valor": float(row["valor"]),
                         "ID": row["id"], "_tipo": "rec"})
    if not desp_cc.empty:
        for _, row in desp_cc.iterrows():
            movs.append({"Data": row["data"], "Descrição": row["descricao"], "Tipo": "Despesa",
                         "Categoria": row.get("categoria", ""), "Valor": -float(row["valor"]),
                         "ID": row["id"], "_tipo": "dsp"})
    movs.sort(key=lambda x: x["Data"])

    saldo_ac = 0.0
    extrato  = []
    for m in movs:
        saldo_ac += m["Valor"]
        extrato.append({
            "Data": converter_data_para_exibicao(m["Data"]), "Descrição": m["Descrição"],
            "Tipo": m["Tipo"], "Categoria": m["Categoria"],
            "Valor": fmt_moeda(abs(m["Valor"])), "Saldo": fmt_moeda(saldo_ac),
        })

    if not extrato:
        st.info("Nenhum movimento para o período selecionado.")
        return

    df_extrato = pd.DataFrame(extrato)
    event_cc = st.dataframe(df_extrato, use_container_width=True, hide_index=True,
                            on_select="rerun", selection_mode="single-row")

    st.markdown("#### Ações do Lançamento")
    if event_cc.selection.rows:
        idx_sel  = event_cc.selection.rows[0]
        mov_sel  = movs[idx_sel]
        id_sel   = int(mov_sel["ID"])
        tipo_sel = mov_sel["_tipo"]
        desc_sel = mov_sel["Descrição"]
        val_sel  = fmt_moeda(abs(mov_sel["Valor"]))
        if tipo_sel == "rec":
            st.warning(f"⚠️ Receita selecionada: **#{id_sel} — {desc_sel} ({val_sel})**")

            # Item 2 · Confirmação explícita antes de excluir receita
            confirmar_r = st.checkbox(
                f"Confirmo a exclusão da receita #{id_sel}",
                key=f"confirmar_excl_rec_{id_sel}"
            )
            if confirmar_r:
                if st.button("🗑 Excluir receita", type="primary", use_container_width=True, key="btn_excl_rec"):
                    try:
                        excluir_receita(id_sel)
                        st.success(f"Receita #{id_sel} excluída!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao excluir: {e}")
            else:
                st.button("🗑 Excluir receita", type="primary", use_container_width=True,
                          disabled=True, key="btn_excl_rec_dis")
        else:
            st.info(f"ℹ️ O lançamento selecionado é uma **Despesa** (#{id_sel}). Para excluí-la, utilize a aba **☰ Despesas**.")
    else:
        st.info("💡 Clique em um lançamento do extrato acima para opções de exclusão (disponível para Receitas).")
