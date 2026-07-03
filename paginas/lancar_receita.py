"""Aba: Lançar Receita."""

from datetime import date

import streamlit as st

from config import CAT_REC
from logica.receitas import salvar_receita
from utils.formatacao import parse_valor


def render():
    st.subheader("Nova Receita")
    with st.form("form_receita", clear_on_submit=True):
        r1, r2 = st.columns([3, 1])
        rdesc  = r1.text_input("Descrição *")
        rvalor = r2.text_input("Valor (R$) *", placeholder="0,00")

        r3, r4 = st.columns(2)
        rdata = r3.date_input("Data *", value=date.today(), format="DD/MM/YYYY")
        rcat  = r4.selectbox("Categoria", [""] + CAT_REC)

        st.markdown("##### 🔁 Recorrência")
        rrecorrente = st.checkbox("Receita recorrente (mensal)", key="rec_recorrente")
        rrec_fim = None
        if rrecorrente:
            rusar_fim = st.checkbox("Definir data de encerramento da recorrência", key="rec_rec_fim_chk")
            if rusar_fim:
                rrec_fim = st.date_input("Encerrar recorrência em", value=date.today(), format="DD/MM/YYYY", key="rec_rec_fim")

        robs  = st.text_input("Observação (opcional)")

        rsubmit = st.form_submit_button("✔ Salvar receita", type="primary", use_container_width=True)

    if rsubmit:
        erros = []
        if not rdesc.strip():
            erros.append("Preencha a descrição.")
        try:
            rv = parse_valor(rvalor)
            if not (0 < rv <= 1_000_000):
                erros.append("Valor deve estar entre R$ 0,01 e R$ 1.000.000,00.")
        except Exception:
            erros.append("Valor inválido.")
            rv = 0

        if erros:
            for e in erros: st.error(e)
        else:
            if st.session_state.get("salvando_receita"):
                st.warning("Aguarde, salvando...")
            else:
                st.session_state["salvando_receita"] = True
                try:
                    salvar_receita(rdesc.strip(), rv, rdata.strftime("%Y-%m-%d"), rcat, robs.strip(),
                                   recorrente=rrecorrente, recorrencia_fim=rrec_fim)
                    st.success("✅ Receita lançada com sucesso!")
                except Exception as e:
                    st.error(f"Erro ao salvar receita: {e}")
                finally:
                    st.session_state["salvando_receita"] = False
