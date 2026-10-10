"""Aba: ☰ Despesas — listagem, filtros, edição e exclusão."""

from datetime import datetime
from functools import partial

import pandas as pd
import streamlit as st

from config import CAT_DESP, PAGAMENTOS
from sheets.loaders import carregar_despesas
from logica.despesas import (
    excluir_despesa, atualizar_despesa, despesa_esta_pendente,
    sincronizar_baixas_automaticas_despesas, marcar_despesa_paga,
)
from logica.relatorios import gerar_pdf, Secao
from utils.datas import seletor_mes_ano, fmt_mes_str_pt
from utils.formatacao import fmt_moeda, card_html, converter_data_para_exibicao, parse_valor
from utils.widgets import (
    campo_valor_moeda, concluir_com_sucesso, exibir_mensagem_pendente, opcoes_categoria, botao_pdf,
)


def render():
    st.subheader("Despesas")
    exibir_mensagem_pendente()

    baixadas = sincronizar_baixas_automaticas_despesas()
    if baixadas:
        nomes = ", ".join(f"{b['descricao']} ({fmt_moeda(b['valor'])})" for b in baixadas)
        st.success(f"✅ Baixa automática: {nomes}")

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

    if "status" in df_d.columns:
        pendentes_mes = df_d[
            df_d["data"].astype(str).str.startswith(fmes)
            & df_d["status"].apply(despesa_esta_pendente)
        ]
        if not pendentes_mes.empty:
            st.markdown("##### 📌 Contas a pagar este mês")
            for _, p in pendentes_mes.sort_values("data").iterrows():
                pc1, pc2 = st.columns([5, 1])
                venc_fmt = converter_data_para_exibicao(p["data"])
                pc1.write(f"**{p['descricao']}** — {fmt_moeda(p['valor'])} — vence {venc_fmt}")
                if pc2.button("Marcar paga", key=f"pagar_{int(p['id'])}"):
                    marcar_despesa_paga(int(p["id"]))
                    st.rerun()
            st.markdown("<br>", unsafe_allow_html=True)

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

    colunas = ["id", "descricao", "valor", "data", "local",
               "pagamento", "categoria", "n_parcelas", "observacao"]
    if "lancado_por" in df_filtrado.columns:
        colunas.append("lancado_por")
    if "status" in df_filtrado.columns:
        colunas.append("status")
    df_show = df_filtrado[colunas].copy()
    df_show["valor"] = df_show["valor"].apply(fmt_moeda)
    df_show["data"]  = df_show["data"].apply(converter_data_para_exibicao)
    if "status" in df_show.columns:
        df_show["status"] = df_show["status"].apply(
            lambda s: "📌 Pendente" if despesa_esta_pendente(s) else "✅ Pago"
        )
    nomes = ["ID", "Descrição", "Valor", "Data", "Local",
             "Pagamento", "Categoria", "Parcelas", "Obs"]
    if "lancado_por" in df_filtrado.columns:
        nomes.append("Lançado por")
    if "status" in df_filtrado.columns:
        nomes.append("Status")
    df_show.columns = nomes

    botao_pdf(
        "Imprimir despesas (PDF)",
        partial(gerar_pdf, "Despesas",
                f"Período: {fmt_mes_str_pt(fmes)}  |  Pagamento: {fpag}  |  Categoria: {fcat}",
                kpis=[("Total", fmt_moeda(total), "azul"), ("Crédito", fmt_moeda(cc_v), "azul"),
                      ("Outros", fmt_moeda(total - cc_v), "verde")],
                secoes=[Secao("", df_show.copy())]),
        f"despesas_{fmes}.pdf", key="pdf_despesas",
    )

    event_d = st.dataframe(df_show, use_container_width=True, hide_index=True,
                           on_select="rerun", selection_mode="single-row")

    st.markdown("#### Ações")
    rows_d = [i for i in event_d.selection.rows if 0 <= i < len(df_filtrado)]
    if rows_d:
        idx_sel      = rows_d[0]
        id_excluir   = int(df_filtrado.iloc[idx_sel]["id"])
        desc_excluir = df_filtrado.iloc[idx_sel]["descricao"]
        val_excluir  = fmt_moeda(df_filtrado.iloc[idx_sel]["valor"])
        st.warning(f"⚠️ Despesa selecionada: **#{id_excluir} — {desc_excluir} ({val_excluir})**")

        # ── Edição ───────────────────────────────────────────────────────
        registro = df_filtrado.iloc[idx_sel]
        with st.expander("✏️ Editar despesa", expanded=False):
            if registro["pagamento"] == "Cartão de crédito":
                st.caption(
                    "⚠️ Esta despesa é do cartão de crédito. Descrição, data, local, "
                    "categoria e observação podem ser editados livremente. Se você "
                    "mudar o **valor**, as parcelas já geradas na aba 💳 Cartão de "
                    "Crédito **não são recalculadas automaticamente** — ajuste-as lá "
                    "manualmente se precisar."
                )

            # Fora do st.form de propósito — ver comentário em paginas/lancar_despesa.py.
            ce1, _ = st.columns(2)
            with ce1:
                valor_edit_txt = campo_valor_moeda(
                    "Valor (R$)", base_key=f"edit_desp_valor_{id_excluir}",
                    value=fmt_moeda(registro["valor"]).replace("R$ ", ""),
                )

            with st.form(f"form_editar_despesa_{id_excluir}"):
                ee1, ee2 = st.columns(2)
                desc_edit = ee1.text_input("Descrição", value=str(registro["descricao"]))
                local_edit = ee2.text_input("Local / Estabelecimento", value=str(registro["local"]))

                ee3, ee4 = st.columns(2)
                try:
                    data_atual = datetime.strptime(str(registro["data"]), "%Y-%m-%d").date()
                except Exception:
                    data_atual = datetime.today().date()
                data_edit = ee3.date_input("Data", value=data_atual, format="DD/MM/YYYY")
                cat_opcoes, idx_cat = opcoes_categoria(CAT_DESP, registro["categoria"])
                cat_edit = ee4.selectbox("Categoria", cat_opcoes, index=idx_cat)

                obs_edit = st.text_input("Observação", value=str(registro.get("observacao", "")))
                salvar_edicao = st.form_submit_button("💾 Salvar alterações", type="primary",
                                                       use_container_width=True)

            if salvar_edicao:
                erros_edit = []
                if not desc_edit.strip():
                    erros_edit.append("Preencha a descrição.")
                try:
                    v_edit = parse_valor(valor_edit_txt)
                    if not (0 < v_edit <= 1_000_000):
                        erros_edit.append("Valor deve estar entre R$ 0,01 e R$ 1.000.000,00.")
                except Exception:
                    erros_edit.append("Valor inválido.")
                    v_edit = 0

                if erros_edit:
                    for e in erros_edit: st.error(e)
                else:
                    try:
                        atualizar_despesa(id_excluir, desc_edit.strip(), v_edit,
                                          data_edit.strftime("%Y-%m-%d"), local_edit.strip(),
                                          cat_edit, obs_edit.strip())
                        concluir_com_sucesso(f"✅ Despesa #{id_excluir} atualizada com sucesso!")
                    except Exception as e:
                        st.error(f"Erro ao atualizar: {e}")

        # ── Exclusão ─────────────────────────────────────────────────────
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
