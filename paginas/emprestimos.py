"""
Aba: 🏛️ Empréstimos — cadastro e controle de empréstimos/financiamentos.

ISOLAMENTO INTENCIONAL: esta aba é só para consulta e controle. Os valores
aqui lançados NÃO entram em nenhuma soma de despesas, no Dashboard nem no
Planejamento 12 Meses — a tabela `emprestimos` é lida exclusivamente por
este arquivo e por `logica/emprestimos.py`.
"""

import pandas as pd
import streamlit as st

from sheets.loaders import carregar_emprestimos
from logica.emprestimos import (
    salvar_emprestimo, excluir_emprestimo, registrar_pagamento_parcela,
)
from utils.formatacao import fmt_moeda, card_html, parse_valor
from utils.widgets import campo_valor_moeda, concluir_com_sucesso, exibir_mensagem_pendente


def _preparar_df(df_e: pd.DataFrame) -> pd.DataFrame:
    df = df_e.copy()
    df["valor_parcela"]       = pd.to_numeric(df["valor_parcela"], errors="coerce").fillna(0.0)
    df["valor_total_devido"]  = pd.to_numeric(df["valor_total_devido"], errors="coerce").fillna(0.0)
    df["parcelas_restantes"]  = pd.to_numeric(df["parcelas_restantes"], errors="coerce").fillna(0).astype(int)
    return df


def _sub_cadastro():
    st.subheader("Novo Empréstimo")
    exibir_mensagem_pendente()

    # Fora do st.form de propósito — mesma razão de todos os outros campos
    # de valor do app: precisam reagir ao perder o foco para aplicar a
    # máscara de centavos, o que widgets dentro de formulários só fazem
    # ao enviar o formulário inteiro. Ver utils/widgets.py::campo_valor_moeda.
    cv1, cv2 = st.columns(2)
    with cv1:
        valor_parcela_txt = campo_valor_moeda("Valor da Parcela (R$) *", base_key="emp_valor_parcela")
    with cv2:
        valor_total_txt = campo_valor_moeda("Valor Total do Débito (R$) *", base_key="emp_valor_total")

    with st.form("form_emprestimo", clear_on_submit=True):
        e1, e2 = st.columns(2)
        descricao = e1.text_input("Descrição * (ex: Empréstimo pessoal, Financiamento veículo)")
        banco     = e2.text_input("Banco *")

        parcelas_restantes = st.number_input(
            "Quantidade de parcelas restantes *", min_value=0, max_value=600, step=1, value=1
        )

        submitted = st.form_submit_button("✔ Salvar Empréstimo", type="primary", use_container_width=True)

    if submitted:
        erros = []
        if not descricao.strip(): erros.append("Preencha a descrição.")
        if not banco.strip(): erros.append("Preencha o banco.")
        try:
            valor_parcela = parse_valor(valor_parcela_txt)
            if not (0 < valor_parcela <= 1_000_000):
                erros.append("Valor da parcela deve estar entre R$ 0,01 e R$ 1.000.000,00.")
        except Exception:
            erros.append("Valor da parcela inválido.")
            valor_parcela = 0
        try:
            valor_total = parse_valor(valor_total_txt)
            if not (0 < valor_total <= 10_000_000):
                erros.append("Valor total do débito deve estar entre R$ 0,01 e R$ 10.000.000,00.")
        except Exception:
            erros.append("Valor total do débito inválido.")
            valor_total = 0

        if erros:
            for e in erros: st.error(e)
        else:
            try:
                salvar_emprestimo(descricao.strip(), banco.strip(), valor_parcela,
                                  int(parcelas_restantes), valor_total)
                concluir_com_sucesso(
                    f"✅ Empréstimo '{descricao}' cadastrado com sucesso!",
                    campo_valor_base_key=["emp_valor_parcela", "emp_valor_total"],
                )
            except Exception as e:
                st.error(f"Erro ao salvar empréstimo: {e}")


def _sub_lista():
    st.subheader("Meus Empréstimos")
    df_e = carregar_emprestimos()
    if df_e.empty:
        st.info("Nenhum empréstimo cadastrado ainda.")
        return

    df = _preparar_df(df_e)

    total_devido = float(df["valor_total_devido"].sum())
    ativos       = int((df["parcelas_restantes"] > 0).sum())
    quitados     = int((df["parcelas_restantes"] <= 0).sum())

    c1, c2, c3 = st.columns(3)
    with c1: st.markdown(card_html("Total devido (todos)", fmt_moeda(total_devido), "orange"), unsafe_allow_html=True)
    with c2: st.markdown(card_html("Empréstimos ativos",   f"{ativos}",              "blue"),   unsafe_allow_html=True)
    with c3: st.markdown(card_html("Quitados",             f"{quitados}",            "green"),  unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    df_show = df[["id", "descricao", "banco", "valor_parcela", "parcelas_restantes", "valor_total_devido"]].copy()
    df_show["valor_parcela"]      = df_show["valor_parcela"].apply(fmt_moeda)
    df_show["valor_total_devido"] = df_show["valor_total_devido"].apply(fmt_moeda)
    df_show.columns = ["ID", "Descrição", "Banco", "Valor Parcela", "Parcelas Restantes", "Valor Total Devido"]

    event = st.dataframe(df_show, use_container_width=True, hide_index=True,
                         on_select="rerun", selection_mode="single-row", key="df_emprestimos_list")

    st.markdown("#### Ações")
    if not event.selection.rows:
        st.info("💡 Clique em um empréstimo na tabela acima para registrar pagamento ou excluir.")
        return

    idx_sel  = event.selection.rows[0]
    eid      = int(df.iloc[idx_sel]["id"])
    desc_sel = df.iloc[idx_sel]["descricao"]
    banco_sel = df.iloc[idx_sel]["banco"]
    parcelas_sel = int(df.iloc[idx_sel]["parcelas_restantes"])
    valor_total_sel = float(df.iloc[idx_sel]["valor_total_devido"])
    valor_parcela_sel = float(df.iloc[idx_sel]["valor_parcela"])

    st.info(
        f"📋 Selecionado: **#{eid} — {desc_sel} ({banco_sel})** | "
        f"Parcelas restantes: **{parcelas_sel}** | Devido: **{fmt_moeda(valor_total_sel)}**"
    )

    if parcelas_sel <= 0:
        st.success("🎉 Este empréstimo já está quitado!")
    else:
        st.caption(
            f"Ao confirmar, o total devido é abatido em {fmt_moeda(valor_parcela_sel)} "
            f"(valor da parcela) e o contador de parcelas restantes diminui em 1."
        )
        if st.button("✔ Registrar pagamento de 1 parcela", type="primary",
                     use_container_width=True, key="btn_pagar_parcela_emp"):
            try:
                registrar_pagamento_parcela(eid)
                st.success(f"Parcela registrada! Restam {max(0, parcelas_sel - 1)} parcela(s).")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao registrar pagamento: {e}")

    st.markdown("---")
    confirmar_excl = st.checkbox(
        f"Confirmo a exclusão do empréstimo #{eid} — {desc_sel}",
        key=f"confirmar_excl_emp_{eid}"
    )
    if confirmar_excl:
        if st.button("🗑 Excluir empréstimo", type="primary",
                     use_container_width=True, key="btn_excl_emp"):
            try:
                excluir_emprestimo(eid)
                st.success(f"Empréstimo #{eid} excluído.")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao excluir: {e}")
    else:
        st.button("🗑 Excluir empréstimo", type="primary",
                  use_container_width=True, disabled=True, key="btn_excl_emp_dis")


def render():
    st.markdown(
        '<div class="plan-banner">🏛️ Esta aba é apenas para <b>consulta e controle</b> — '
        'os valores lançados aqui não entram em nenhuma soma de despesas, no Dashboard '
        'ou no Planejamento 12 Meses.</div>',
        unsafe_allow_html=True
    )

    sub_cadastro, sub_lista = st.tabs(["➕ Novo Empréstimo", "📋 Meus Empréstimos"])

    with sub_cadastro:
        _sub_cadastro()

    with sub_lista:
        _sub_lista()