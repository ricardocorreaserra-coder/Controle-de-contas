"""Aba: Lançar Despesa."""

from datetime import date

import streamlit as st

from config import CAT_DESP, PAGAMENTOS, PARCELAS_OPT
from sheets.loaders import obter_nomes_cartoes
from logica.despesas import salvar_despesa
from utils.formatacao import parse_valor


def render():
    st.subheader("Nova Despesa")
    with st.form("form_despesa", clear_on_submit=True):
        c1, c2 = st.columns([3, 1])
        desc  = c1.text_input("Descrição *")
        valor = c2.text_input("Valor (R$) *", placeholder="0,00")

        c3, c4 = st.columns(2)
        data_d = c3.date_input("Data *", value=date.today(), format="DD/MM/YYYY")
        local  = c4.text_input("Local / Estabelecimento")

        c5, c6 = st.columns(2)
        cat = c5.selectbox("Categoria", [""] + CAT_DESP)
        pag = c6.selectbox("Modo de pagamento *", [""] + PAGAMENTOS)

        cartao = None; n_parc = 1
        if pag == "Cartão de crédito":
            st.markdown("##### 💳 Cartão de Crédito")
            cc1, cc2 = st.columns(2)
            cartao = cc1.selectbox("Cartão", obter_nomes_cartoes())
            n_parc = cc2.selectbox("Parcelas", PARCELAS_OPT)

        st.markdown("##### 🔁 Recorrência")
        recorrente = st.checkbox("Despesa recorrente (mensal)", key="desp_recorrente")
        if recorrente and pag == "Cartão de crédito":
            st.warning("Compras no cartão já geram parcelas automáticas. "
                       "Use recorrente para débito, Pix, vale alimentação etc.")
        rec_fim = None
        if recorrente:
            usar_fim = st.checkbox("Definir data de encerramento da recorrência", key="desp_rec_fim_chk")
            if usar_fim:
                rec_fim = st.date_input("Encerrar recorrência em", value=date.today(), format="DD/MM/YYYY", key="desp_rec_fim")

        obs = st.text_input("Observação (opcional)")
        submitted = st.form_submit_button("✔ Salvar despesa", type="primary", use_container_width=True)

    if submitted:
        erros = []
        if not desc.strip():
            erros.append("Preencha a descrição.")
        try:
            v = parse_valor(valor)
            if not (0 < v <= 1_000_000):
                erros.append("Valor deve estar entre R$ 0,01 e R$ 1.000.000,00.")
        except Exception:
            erros.append("Valor inválido.")
            v = 0
        if not pag:
            erros.append("Selecione o modo de pagamento.")

        if erros:
            for e in erros: st.error(e)
        else:
            if st.session_state.get("salvando_despesa"):
                st.warning("Aguarde, salvando...")
            else:
                st.session_state["salvando_despesa"] = True
                try:
                    salvar_despesa(desc.strip(), v, data_d.strftime("%Y-%m-%d"),
                                   local.strip(), pag, cat, cartao, n_parc, obs.strip(),
                                   recorrente=recorrente, recorrencia_fim=rec_fim)
                    st.success("✅ Despesa lançada com sucesso!")
                except Exception as e:
                    st.error(f"Erro ao salvar despesa: {e}")
                finally:
                    st.session_state["salvando_despesa"] = False
