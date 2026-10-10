"""
Aba: 🏛️ Empréstimos — cadastro e controle de empréstimos/financiamentos.

ISOLAMENTO INTENCIONAL: esta aba é só para consulta e controle. Os valores
aqui lançados NÃO entram em nenhuma soma de despesas, no Dashboard nem no
Planejamento 12 Meses — a tabela `emprestimos` é lida exclusivamente por
este arquivo e por `logica/emprestimos.py`.

REGRAS DE NEGÓCIO:
  - O valor total do débito é sempre CALCULADO (valor da parcela × parcelas
    restantes) — não existe mais campo para digitá-lo manualmente.
  - A baixa das parcelas é AUTOMÁTICA: toda vez que esta aba é aberta,
    `sincronizar_baixas_automaticas()` compara a data de vencimento de
    cada empréstimo com a data de hoje e dá baixa em tudo que já venceu.
"""

from datetime import date
from functools import partial

import pandas as pd
import streamlit as st

from sheets.loaders import carregar_emprestimos
from logica.emprestimos import (
    salvar_emprestimo, atualizar_emprestimo, excluir_emprestimo,
    sincronizar_baixas_automaticas, calcular_valor_total_devido,
)
from logica.relatorios import gerar_pdf, Secao
from utils.datas import data_iso
from utils.formatacao import fmt_moeda, card_html, parse_valor, converter_data_para_exibicao
from utils.widgets import (
    campo_valor_moeda, concluir_com_sucesso, exibir_mensagem_pendente, limpar_campo_valor,
    botao_pdf,
)

# Mensagem de sucesso da EDIÇÃO. Fica numa chave própria (e não na genérica de
# `concluir_com_sucesso`) porque esta é consumida pela sub-aba de cadastro,
# que é desenhada antes — a mensagem apareceria na aba errada.
_CHAVE_MSG_EDICAO = "_msg_emprestimo_editado"


def _preparar_df(df_e: pd.DataFrame) -> pd.DataFrame:
    df = df_e.copy()
    df["valor_parcela"]      = pd.to_numeric(df["valor_parcela"], errors="coerce").fillna(0.0)
    df["valor_total_devido"] = pd.to_numeric(df["valor_total_devido"], errors="coerce").fillna(0.0)
    df["parcelas_restantes"] = pd.to_numeric(df["parcelas_restantes"], errors="coerce").fillna(0).astype(int)
    return df


def _sub_cadastro():
    st.subheader("Novo Empréstimo")
    exibir_mensagem_pendente()

    st.caption(
        "O valor total do débito é calculado automaticamente "
        "(valor da parcela × parcelas restantes) — não precisa informar."
    )

    # Fora do st.form de propósito — precisa reagir ao perder o foco para
    # aplicar a máscara de centavos. Ver utils/widgets.py::campo_valor_moeda.
    cv1, _ = st.columns(2)
    with cv1:
        valor_parcela_txt = campo_valor_moeda("Valor da Parcela (R$) *", base_key="emp_valor_parcela")

    with st.form("form_emprestimo", clear_on_submit=True):
        e1, e2 = st.columns(2)
        descricao = e1.text_input("Descrição * (ex: Empréstimo pessoal, Financiamento veículo)")
        banco     = e2.text_input("Banco *")

        e3, e4 = st.columns(2)
        parcelas_restantes = e3.number_input(
            "Quantidade de parcelas restantes *", min_value=1, max_value=600, step=1, value=1
        )
        proxima_data_vencimento = e4.date_input(
            "Data de vencimento da próxima parcela *", value=date.today(), format="DD/MM/YYYY"
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

        if erros:
            for e in erros: st.error(e)
        else:
            try:
                salvar_emprestimo(descricao.strip(), banco.strip(), valor_parcela,
                                  int(parcelas_restantes), proxima_data_vencimento)
                valor_total_preview = calcular_valor_total_devido(valor_parcela, parcelas_restantes)
                concluir_com_sucesso(
                    f"✅ Empréstimo '{descricao}' cadastrado com sucesso! "
                    f"Valor total do débito: {fmt_moeda(valor_total_preview)}.",
                    campo_valor_base_key="emp_valor_parcela",
                )
            except Exception as e:
                st.error(f"Erro ao salvar empréstimo: {e}")


def _bloco_edicao(eid: int, registro) -> None:
    """Expander "✏️ Editar empréstimo" do empréstimo selecionado na tabela."""
    with st.expander("✏️ Editar empréstimo", expanded=False):
        st.caption(
            "Use para corrigir um cadastro feito com valores errados. O **valor total "
            "devido** é recalculado sozinho (parcela × parcelas restantes). Se a data "
            "de vencimento informada já tiver passado, o app dá baixa automática nas "
            "parcelas vencidas logo após salvar."
        )

        # Fora do st.form de propósito — ver comentário em _sub_cadastro.
        ce1, _ = st.columns(2)
        with ce1:
            valor_edit_txt = campo_valor_moeda(
                "Valor da Parcela (R$) *", base_key=f"emp_edit_valor_{eid}",
                value=fmt_moeda(registro["valor_parcela"]).replace("R$ ", ""),
            )

        try:
            data_atual = date.fromisoformat(data_iso(registro["proxima_data_vencimento"]))
        except Exception:
            data_atual = date.today()

        with st.form(f"form_editar_emprestimo_{eid}"):
            ee1, ee2 = st.columns(2)
            desc_edit  = ee1.text_input("Descrição *", value=str(registro["descricao"]))
            banco_edit = ee2.text_input("Banco *", value=str(registro["banco"]))

            ee3, ee4 = st.columns(2)
            parcelas_edit = ee3.number_input(
                "Quantidade de parcelas restantes *", min_value=0, max_value=600, step=1,
                value=min(max(int(registro["parcelas_restantes"]), 0), 600),
                help="0 = empréstimo quitado.",
            )
            venc_edit = ee4.date_input(
                "Data de vencimento da próxima parcela *", value=data_atual, format="DD/MM/YYYY"
            )
            salvar_edicao = st.form_submit_button(
                "💾 Salvar alterações", type="primary", use_container_width=True
            )

        if salvar_edicao:
            erros = []
            if not desc_edit.strip():  erros.append("Preencha a descrição.")
            if not banco_edit.strip(): erros.append("Preencha o banco.")
            try:
                valor_edit = parse_valor(valor_edit_txt)
                if not (0 < valor_edit <= 1_000_000):
                    erros.append("Valor da parcela deve estar entre R$ 0,01 e R$ 1.000.000,00.")
            except Exception:
                erros.append("Valor da parcela inválido.")
                valor_edit = 0

            if erros:
                for e in erros: st.error(e)
            else:
                try:
                    atualizar_emprestimo(eid, desc_edit.strip(), banco_edit.strip(),
                                         float(valor_edit), int(parcelas_edit), venc_edit)
                    limpar_campo_valor(f"emp_edit_valor_{eid}")
                    st.session_state[_CHAVE_MSG_EDICAO] = f"✅ Empréstimo #{eid} atualizado com sucesso!"
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao atualizar: {e}")


def _sub_lista():
    st.subheader("Meus Empréstimos")
    msg_edicao = st.session_state.pop(_CHAVE_MSG_EDICAO, None)
    if msg_edicao:
        st.success(msg_edicao)
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

    df_show = df[["id", "descricao", "banco", "valor_parcela", "parcelas_restantes",
                  "proxima_data_vencimento", "valor_total_devido"]].copy()
    df_show["valor_parcela"]      = df_show["valor_parcela"].apply(fmt_moeda)
    df_show["valor_total_devido"] = df_show["valor_total_devido"].apply(fmt_moeda)
    df_show["proxima_data_vencimento"] = df_show["proxima_data_vencimento"].apply(converter_data_para_exibicao)
    df_show.columns = ["ID", "Descrição", "Banco", "Valor Parcela", "Parcelas Restantes",
                        "Próximo Vencimento", "Valor Total Devido"]

    botao_pdf(
        "Imprimir empréstimos (PDF)",
        partial(gerar_pdf, "Empréstimos", f"Posição em {date.today().strftime('%d/%m/%Y')}",
                kpis=[("Total devido (todos)", fmt_moeda(total_devido), "laranja"),
                      ("Empréstimos ativos", str(ativos), "azul"),
                      ("Quitados", str(quitados), "verde")],
                secoes=[Secao("", df_show.copy())]),
        f"emprestimos_{date.today().strftime('%Y%m%d')}.pdf", key="pdf_emprestimos",
    )

    event = st.dataframe(df_show, use_container_width=True, hide_index=True,
                         on_select="rerun", selection_mode="single-row", key="df_emprestimos_list")

    st.markdown("#### Ações")
    rows_emp = [i for i in event.selection.rows if 0 <= i < len(df)]
    if not rows_emp:
        st.info("💡 Clique em um empréstimo na tabela acima para editar ou excluir.")
        return

    idx_sel  = rows_emp[0]
    eid      = int(df.iloc[idx_sel]["id"])
    desc_sel = df.iloc[idx_sel]["descricao"]
    banco_sel = df.iloc[idx_sel]["banco"]
    parcelas_sel = int(df.iloc[idx_sel]["parcelas_restantes"])
    valor_total_sel = float(df.iloc[idx_sel]["valor_total_devido"])

    st.info(
        f"📋 Selecionado: **#{eid} — {desc_sel} ({banco_sel})** | "
        f"Parcelas restantes: **{parcelas_sel}** | Devido: **{fmt_moeda(valor_total_sel)}**"
    )

    _bloco_edicao(eid, df.iloc[idx_sel])

    if parcelas_sel <= 0:
        st.success("🎉 Este empréstimo já está quitado!")
    else:
        st.caption(
            "A baixa das parcelas é automática: toda vez que esta aba é aberta, o app "
            "confere a data de vencimento e atualiza sozinho parcelas restantes e valor devido."
        )

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
    # Baixa automática: roda toda vez que a aba é aberta, ANTES de exibir
    # qualquer coisa, para que os números já apareçam atualizados.
    atualizados = sincronizar_baixas_automaticas()
    for item in atualizados:
        st.info(
            f"🔄 **{item['descricao']}** ({item['banco']}): {item['parcelas_baixadas']} "
            f"parcela(s) baixada(s) automaticamente. Restam {item['parcelas_restantes']}."
        )

    st.markdown(
        '<div class="plan-banner">🏛️ Esta aba é apenas para <b>consulta e controle</b> — '
        'os valores lançados aqui não entram em nenhuma soma de despesas, no Dashboard '
        'ou no Planejamento 12 Meses. O valor total do débito é sempre calculado '
        '(parcela × parcelas restantes) e as baixas acontecem automaticamente com base '
        'na data de vencimento.</div>',
        unsafe_allow_html=True
    )

    sub_cadastro, sub_lista = st.tabs(["➕ Novo Empréstimo", "📋 Meus Empréstimos"])

    with sub_cadastro:
        _sub_cadastro()

    with sub_lista:
        _sub_lista()
