"""Aba: Lançar Despesa."""


import streamlit as st

from config import CAT_DESP, PAGAMENTOS
from sheets.loaders import obter_nomes_cartoes
from logica.despesas import salvar_despesa
from utils.datas import hoje_br
from utils.formatacao import parse_valor, fmt_moeda
from utils.widgets import campo_valor_moeda, concluir_com_sucesso, exibir_mensagem_pendente


def render():
    st.subheader("Nova Despesa")
    exibir_mensagem_pendente()

    # Fora do st.form de propósito: o campo de valor precisa reagir ao
    # perder o foco (on_change) para aplicar a máscara de centavos, algo
    # que widgets dentro de formulários só fazem na submissão do form
    # inteiro — ver utils/widgets.py::campo_valor_moeda.
    c_valor, _ = st.columns([1, 3])
    with c_valor:
        valor = campo_valor_moeda("Valor (R$) *", base_key="desp_valor")

    # SEM st.form de propósito: dentro de um formulário o Streamlit só atualiza
    # a tela no envio. Com "Modo de pagamento" dentro dele, os campos do cartão
    # (e os de status/recorrência) não apareciam ao escolher a opção — só depois
    # de Salvar, que então gravava com os valores padrão (1º cartão, 1 parcela).
    # Fora do form, cada escolha atualiza a tela na hora.
    #
    # Para "limpar a tela" depois de salvar (o que o clear_on_submit fazia), as
    # chaves dos campos levam um contador; ao salvar o contador sobe e todos os
    # campos voltam ao estado inicial.
    n = st.session_state.get("desp_form_n", 0)
    k = lambda nome: f"desp_{nome}_{n}"

    desc = st.text_input("Descrição *", key=k("desc"))

    c3, c4 = st.columns(2)
    data_d = c3.date_input("Data *", value=hoje_br(), format="DD/MM/YYYY", key=k("data"),
                           help="Se marcar como pendente mais abaixo, use aqui a data de vencimento prevista.")
    local  = c4.text_input("Local / Estabelecimento", key=k("local"))

    c5, c6 = st.columns(2)
    cat = c5.selectbox("Categoria", [""] + CAT_DESP, key=k("cat"))
    pag = c6.selectbox("Modo de pagamento *", [""] + PAGAMENTOS, key=k("pag"))

    cartao = None; n_parc = 1
    if pag == "Cartão de crédito":
        st.markdown("##### 💳 Cartão de Crédito")
        cc1, cc2 = st.columns(2)
        cartao = cc1.selectbox("Cartão", obter_nomes_cartoes(), key=k("cartao"))
        n_parc = cc2.number_input("Parcelas", min_value=1, max_value=60, value=1, step=1,
                                  key=k("parcelas"))

    pendente = False
    if pag and pag != "Cartão de crédito":
        st.markdown("##### 📌 Status")
        pendente = st.checkbox(
            "Despesa pendente (ainda não debitou — ex.: conta de luz programada)",
            key=k("pendente"),
            help="Fica fora do saldo do Dashboard até a data chegar (baixa automática) "
                 "ou você marcar como paga manualmente."
        )

    st.markdown("##### 🔁 Recorrência")
    recorrente = st.checkbox("Despesa recorrente (mensal)", key=k("recorrente"))
    if recorrente and pag == "Cartão de crédito":
        st.warning("Compras no cartão já geram parcelas automáticas. "
                   "Use recorrente para débito, Pix, vale alimentação etc.")
    rec_fim = None
    if recorrente:
        usar_fim = st.checkbox("Definir data de encerramento da recorrência", key=k("rec_fim_chk"))
        if usar_fim:
            rec_fim = st.date_input("Encerrar recorrência em", value=hoje_br(),
                                    format="DD/MM/YYYY", key=k("rec_fim"))

    obs = st.text_input("Observação (opcional)", key=k("obs"))
    submitted = st.button("✔ Salvar despesa", type="primary", use_container_width=True,
                          key=k("salvar"))

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
        if pag == "Cartão de crédito" and not cartao:
            erros.append("Selecione o cartão.")

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
                                   recorrente=recorrente, recorrencia_fim=rec_fim,
                                   pendente=pendente)
                    st.session_state["desp_form_n"] = n + 1   # campos voltam ao estado inicial
                    if pag == "Cartão de crédito":
                        detalhe = f"{fmt_moeda(v)} no cartão {cartao} em {n_parc}x"
                    else:
                        detalhe = f"{fmt_moeda(v)} ({pag}{', pendente' if pendente else ''})"
                    concluir_com_sucesso(f"Despesa lançada: {desc.strip()} — {detalhe}",
                                         campo_valor_base_key="desp_valor")
                except Exception as e:
                    st.error(f"Erro ao salvar despesa: {e}")
                finally:
                    st.session_state["salvando_despesa"] = False