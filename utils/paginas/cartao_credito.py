"""Aba: 💳 Cartão de Crédito — parcelas, faturas futuras, lançamento manual e configurações."""

import calendar
import re
from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from sheets.loaders import carregar_parcelas, carregar_despesas, carregar_cartoes, obter_nomes_cartoes
from logica.cartoes import salvar_cartao, excluir_cartao, cartao_tem_vinculos, estimar_vencimento_parcela
from logica.parcelas import (
    salvar_parcela_manual, atualizar_parcela, baixar_fatura_mes, atualizar_vencimento_parcela,
    alterar_lancamento_parcela, resumo_compra_parcelas, excluir_compra_parcelas, corrigir_total_parcelas,
)
from logica.fechamentos import (
    fechamentos_ordenados_por_cartao, salvar_fechamento, excluir_fechamento,
    detectar_buracos_fechamentos,
)
from utils.datas import seletor_mes_ano, hoje_str, add_months, fmt_mes_str_pt, data_iso as _data_para_iso
from utils.formatacao import fmt_moeda, card_html, parse_valor, converter_data_para_exibicao
from utils.widgets import campo_valor_moeda, concluir_com_sucesso, exibir_mensagem_pendente


def _preparar_df_parcelas(df_p: pd.DataFrame, df_d: pd.DataFrame) -> pd.DataFrame:
    """Faz o merge de parcelas com despesas para preencher descrição/cartão quando vazios."""
    if df_p.empty:
        return pd.DataFrame()
    df_p_converted = df_p.copy()
    df_p_converted["valor"] = pd.to_numeric(df_p_converted["valor"], errors='coerce').fillna(0.0)
    if "vencimento" in df_p_converted.columns:
        df_p_converted["vencimento"] = df_p_converted["vencimento"].apply(_data_para_iso)
    if not df_d.empty:
        df_d_sub = df_d[["id", "descricao", "cartao"]].rename(
            columns={"id": "despesa_id", "descricao": "desc_dep", "cartao": "cartao_dep"})
        df_p2 = df_p_converted.merge(df_d_sub, on="despesa_id", how="left")
        df_p2["descricao"] = df_p2.apply(
            lambda r: r["desc_dep"] if pd.notna(r.get("desc_dep")) and r["desc_dep"] != "" else r.get("descricao", ""), axis=1)
        df_p2["cartao"] = df_p2.apply(
            lambda r: r["cartao_dep"] if pd.notna(r.get("cartao_dep")) and r["cartao_dep"] != "" else r.get("cartao", ""), axis=1)
    else:
        df_p2 = df_p_converted.copy()
        df_p2["descricao"] = df_p2.get("descricao", "")
        df_p2["cartao"]    = df_p2.get("cartao", "")
    df_p2["descricao"] = df_p2["descricao"].fillna("").astype(str)
    df_p2["cartao"]    = df_p2["cartao"].fillna("").astype(str)
    return df_p2


def _sub_parcelas(df_p, df_p2, hoje):
    st.subheader("Cartão de Crédito — Parcelas")
    msg_alt = st.session_state.pop("_msg_alt_parcela", None)
    if msg_alt:
        st.success(msg_alt)
    if df_p.empty or df_p2.empty:
        st.info("Nenhuma parcela cadastrada.")
        return

    fc1, fc2 = st.columns(2)
    fc_cartao = fc1.selectbox("Cartão", ["Todos"] + obter_nomes_cartoes(), key="fc_cartao")
    fc_status = fc2.selectbox("Status", ["Todos", "Pendente", "Vencido", "Pago"], key="fc_status")

    df_filtrado = df_p2.copy()
    if fc_cartao != "Todos":
        df_filtrado = df_filtrado[df_filtrado["cartao"] == fc_cartao]
    if fc_status != "Todos":
        if fc_status == "Vencido":
            df_filtrado = df_filtrado[(df_filtrado["status"] == "pendente") & (df_filtrado["vencimento"].astype(str) < hoje)]
        elif fc_status == "Pendente":
            df_filtrado = df_filtrado[(df_filtrado["status"] == "pendente") & (df_filtrado["vencimento"].astype(str) >= hoje)]
        else:
            df_filtrado = df_filtrado[df_filtrado["status"] == fc_status.lower()]

    pend  = float(df_p2[df_p2["status"] == "pendente"]["valor"].sum())
    venc  = int(((df_p2["status"] == "pendente") & (df_p2["vencimento"].astype(str) < hoje)).sum())
    pagas = int((df_p2["status"] == "pago").sum())
    cc1, cc2, cc3 = st.columns(3)
    with cc1: st.markdown(card_html("A pagar total", fmt_moeda(pend),       "orange"), unsafe_allow_html=True)
    with cc2: st.markdown(card_html("Vencidas",      f"{venc} parcela(s)",  "red"),    unsafe_allow_html=True)
    with cc3: st.markdown(card_html("Pagas",         f"{pagas} parcela(s)", "green"),  unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    if df_filtrado.empty:
        st.info("Nenhuma parcela para os filtros selecionados.")
        return

    def status_label(row):
        if row["status"] == "pago": return "✅ Pago"
        if str(row["vencimento"]) < hoje: return "❌ Vencido"
        return "⏳ Pendente"
    def origem_label(row):
        # Registros antigos (antes desta funcionalidade existir) não têm
        # origem_vencimento preenchida — tratamos como "estimado" por
        # segurança, já que de fato vieram do cálculo automático antigo.
        origem = str(row.get("origem_vencimento", "")).strip().lower()
        return "✅ Confirmado" if origem == "manual" else "🔧 Estimado"
    df_filtrado = df_filtrado.copy()
    df_filtrado["Status"] = df_filtrado.apply(status_label, axis=1)
    df_filtrado["Origem"] = df_filtrado.apply(origem_label, axis=1)

    cols_show = [c for c in ["id", "descricao", "cartao", "numero", "total", "valor", "data_compra", "vencimento", "Status", "Origem"] if c in df_filtrado.columns]
    df_show = df_filtrado[cols_show].copy()
    df_show["valor"]      = df_show["valor"].apply(fmt_moeda)
    df_show["vencimento"] = df_show["vencimento"].apply(converter_data_para_exibicao)
    if "data_compra" in df_show.columns:
        # Parcelas sem data da compra (lançamentos antigos) ficam em branco
        df_show["data_compra"] = df_show["data_compra"].apply(
            lambda v: converter_data_para_exibicao(_data_para_iso(v)) if _data_para_iso(v) else "")
    df_show.rename(columns={"id": "ID", "descricao": "Despesa/Item", "cartao": "Cartão",
                            "numero": "Parc.", "total": "Total", "valor": "Valor",
                            "data_compra": "Data da Compra",
                            "vencimento": "Vencimento"}, inplace=True)

    event_p = st.dataframe(df_show, use_container_width=True, hide_index=True,
                           on_select="rerun", selection_mode="single-row",
                           key=f"df_parcelas_list_{st.session_state.get('_ver_df_parcelas', 0)}")

    st.markdown("#### Ações da Parcela")
    # Ignora seleção "velha" (posição fora do intervalo após filtro/baixa/exclusão)
    rows_p = [i for i in event_p.selection.rows if 0 <= i < len(df_filtrado)]
    if rows_p:
        idx_sel  = rows_p[0]
        pid_acao = int(df_filtrado.iloc[idx_sel]["id"])
        desc_p   = df_filtrado.iloc[idx_sel]["descricao"]
        val_p    = fmt_moeda(df_filtrado.iloc[idx_sel]["valor"])
        status_p = df_filtrado.iloc[idx_sel]["status"]
        st.info(f"📋 Parcela selecionada: **#{pid_acao} — {desc_p} ({val_p})** | Status: **{status_p.upper()}**")
        ba2, ba3 = st.columns(2)
        # Baixa e estorno de parcela individual não precisam de confirmação
        # pois são reversíveis (estorno disponível)
        if ba2.button("✔ Dar baixa (Marcar como Pago)", type="primary", use_container_width=True, key="btn_pago_p"):
            try:
                atualizar_parcela(pid_acao, "pago")
                st.success(f"Parcela #{pid_acao} marcada como paga!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro: {e}")
        if ba3.button("↩ Estornar (Voltar para Pendente)", use_container_width=True, key="btn_pendente_p"):
            try:
                atualizar_parcela(pid_acao, "pendente")
                st.warning(f"Parcela #{pid_acao} estornada para pendente.")
                st.rerun()
            except Exception as e:
                st.error(f"Erro: {e}")

        st.markdown("###### ✏️ Corrigir vencimento desta parcela")
        st.caption(
            "Use quando o fechamento real da fatura foi diferente da estimativa "
            "automática (ex.: o fechamento daquele mês ainda não estava registrado "
            "na aba 🗓️ Fechamentos quando esta compra foi lançada)."
        )
        venc_dt = pd.to_datetime(_data_para_iso(df_filtrado.iloc[idx_sel]["vencimento"]), errors="coerce")
        venc_atual = date.today() if pd.isna(venc_dt) else venc_dt.date()
        if not (2000 <= venc_atual.year <= 2100):
            st.warning(
                "O vencimento desta parcela está inválido na planilha. "
                "Informe a data correta abaixo e clique em Corrigir."
            )
            venc_atual = date.today()
        cc_v1, cc_v2 = st.columns([2, 1])
        novo_venc = cc_v1.date_input("Novo vencimento", value=venc_atual,
                                     min_value=date(2000, 1, 1), max_value=date(2100, 12, 31),
                                     format="DD/MM/YYYY", key=f"corrigir_venc_data_{pid_acao}")
        cc_v2.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        if cc_v2.button("Corrigir", use_container_width=True, key="btn_corrigir_venc"):
            try:
                atualizar_vencimento_parcela(pid_acao, novo_venc)
                st.success(f"Vencimento da parcela #{pid_acao} corrigido para {novo_venc.strftime('%d/%m/%Y')}.")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao corrigir vencimento: {e}")

        _form_alterar_lancamento(df_filtrado.iloc[idx_sel], pid_acao)
        _form_gerenciar_compra(df_p, pid_acao)
    else:
        st.info("💡 Clique em uma parcela na tabela acima para liberar as ações de pagamento/estorno.")

    st.markdown("---")
    st.markdown("##### 💳 Baixar Fatura Completa do Mês")
    c_fat1, c_fat2 = st.columns([2, 1])
    with c_fat1:
        mes_fat = seletor_mes_ano("fatura_lote")

    cartao_label = fc_cartao if fc_cartao != "Todos" else "todos os cartões"

    # Item 2 · Confirmação explícita antes de baixar fatura em lote
    confirmar_fat = st.checkbox(
        f"Confirmo a baixa de todas as parcelas pendentes de {mes_fat} para {cartao_label}",
        key="confirmar_baixa_fatura"
    )
    with c_fat2:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        btn_baixa_lote = st.button(
            "💳 Baixar fatura completa do mês",
            type="secondary",
            use_container_width=True,
            key="btn_baixa_lote",
            disabled=not confirmar_fat
        )
    if btn_baixa_lote and confirmar_fat:
        try:
            n = baixar_fatura_mes(mes_fat, fc_cartao if fc_cartao != "Todos" else None)
            st.success(f"Sucesso! {n} parcela(s) baixadas para {mes_fat}!")
            st.rerun()
        except Exception as e:
            st.error(f"Erro ao baixar fatura: {e}")


def _form_alterar_lancamento(row, pid_acao):
    """Formulário para alterar os dados de uma parcela (ou da compra inteira)."""
    manual = str(row.get("despesa_id", "")).strip() == "-1"

    with st.expander("✏️ Alterar lançamento", expanded=False):
        if manual:
            st.caption("Lançamento histórico: você pode alterar descrição, cartão, valor e data da compra.")
        else:
            st.caption(
                "Esta parcela veio de uma despesa lançada na aba Despesas. Aqui só o **valor** pode ser "
                "alterado; descrição, cartão e data pertencem à despesa."
            )

        nomes_cartoes = obter_nomes_cartoes()
        cartao_atual  = str(row.get("cartao", ""))
        if cartao_atual and cartao_atual not in nomes_cartoes:
            nomes_cartoes = [cartao_atual] + nomes_cartoes

        compra_atual = pd.to_datetime(_data_para_iso(row.get("data_compra", "")), errors="coerce")
        compra_atual = None if pd.isna(compra_atual) else compra_atual.date()

        with st.form(f"form_alterar_parcela_{pid_acao}"):
            if manual:
                c1, c2 = st.columns(2)
                nova_desc   = c1.text_input("Descrição", value=str(row.get("descricao", "")),
                                            key=f"alt_desc_{pid_acao}")
                novo_cartao = c2.selectbox("Cartão", nomes_cartoes,
                                           index=nomes_cartoes.index(cartao_atual) if cartao_atual in nomes_cartoes else 0,
                                           key=f"alt_cartao_{pid_acao}")
            c3, c4 = st.columns(2)
            novo_valor = c3.number_input("Valor da parcela (R$)", min_value=0.01, max_value=1_000_000.0,
                                         value=max(float(row.get("valor", 0.01) or 0.01), 0.01),
                                         step=0.01, format="%.2f", key=f"alt_valor_{pid_acao}")
            if manual:
                nova_compra = c4.date_input("Data da compra", value=compra_atual,
                                            min_value=date(2000, 1, 1), max_value=date.today(),
                                            format="DD/MM/YYYY", key=f"alt_compra_{pid_acao}")

            escopo_label = st.radio(
                "Aplicar a",
                ["Apenas esta parcela", "Toda a compra"],
                horizontal=True, key=f"alt_escopo_{pid_acao}",
                help="'Toda a compra' altera descrição, cartão e data da compra em todas as parcelas dela "
                     "(pagas e pendentes) e o valor somente nas parcelas pendentes.",
            )
            salvar_alt = st.form_submit_button("💾 Salvar alterações", type="primary", use_container_width=True)

        if salvar_alt:
            escopo = "compra" if escopo_label == "Toda a compra" else "parcela"
            try:
                n = alterar_lancamento_parcela(
                    pid_acao,
                    valor=float(novo_valor),
                    descricao=nova_desc.strip() if manual else None,
                    cartao=novo_cartao if manual else None,
                    data_compra=nova_compra.strftime("%Y-%m-%d") if (manual and nova_compra) else None,
                    escopo=escopo,
                )
                st.session_state["_msg_alt_parcela"] = f"Lançamento alterado com sucesso ({n} parcela(s) atualizada(s))."
                st.rerun()
            except ValueError as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"Erro ao alterar lançamento: {e}")


def _form_gerenciar_compra(df_p, pid_acao):
    """Corrigir a quantidade de parcelas ou excluir a compra inteira (lançamentos históricos)."""
    resumo = resumo_compra_parcelas(df_p, pid_acao)

    with st.expander("🗂️ Corrigir quantidade de parcelas / Excluir compra", expanded=False):
        if resumo is None:
            st.caption("Parcela não encontrada. Recarregue a página.")
            return
        if not resumo["manual"]:
            st.caption(
                "Esta parcela veio de uma despesa lançada na aba Despesas. "
                "Para corrigir o parcelamento ou excluir, altere a despesa lá."
            )
            return

        st.markdown(
            f"**{resumo['descricao']}** — {resumo['cartao']} · {resumo['n']} parcela(s) lançada(s) "
            f"(nº {resumo['num_min']} a {resumo['num_max']}) · "
            f"{resumo['pagas']} paga(s), {resumo['pendentes']} pendente(s)"
        )

        # ── Corrigir quantidade de parcelas ──
        st.markdown("###### Corrigir quantidade de parcelas")
        novo_total = st.number_input("Total de parcelas da compra", min_value=1, max_value=48,
                                     value=int(resumo["total"]), step=1, key=f"gc_total_{pid_acao}")
        if novo_total < resumo["num_max"]:
            st.warning(f"Serão **removidas** as parcelas {novo_total + 1} a {resumo['num_max']}.")
        elif novo_total > resumo["num_max"]:
            st.info(
                f"Serão **criadas** as parcelas {resumo['num_max'] + 1} a {novo_total}, mês a mês depois da última, "
                "com o mesmo valor e o mesmo dia de vencimento."
            )
        if st.button("Aplicar novo total", use_container_width=True, key=f"gc_btn_total_{pid_acao}",
                     disabled=(novo_total == resumo["total"] and novo_total == resumo["num_max"])):
            try:
                removidas, criadas = corrigir_total_parcelas(pid_acao, novo_total)
                st.session_state["_ver_df_parcelas"] = st.session_state.get("_ver_df_parcelas", 0) + 1
                st.session_state["_msg_alt_parcela"] = (
                    f"Total corrigido para {novo_total} parcela(s): {removidas} removida(s), {criadas} criada(s)."
                )
                st.rerun()
            except ValueError as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"Erro ao corrigir o total de parcelas: {e}")

        # ── Excluir compra ──
        st.markdown("---")
        st.markdown("###### Excluir compra")
        aviso_pagas = f" (inclui {resumo['pagas']} já paga(s))" if resumo["pagas"] else ""
        confirmar = st.checkbox(
            f"Confirmo a exclusão de **{resumo['descricao']}** e de suas {resumo['n']} parcela(s){aviso_pagas}",
            key=f"gc_confirma_{pid_acao}",
        )
        if st.button("🗑 Excluir compra", type="primary", use_container_width=True,
                     key=f"gc_btn_excluir_{pid_acao}", disabled=not confirmar):
            try:
                n = excluir_compra_parcelas(pid_acao)
                st.session_state["_ver_df_parcelas"] = st.session_state.get("_ver_df_parcelas", 0) + 1
                st.session_state["_msg_alt_parcela"] = f"Compra '{resumo['descricao']}' excluída ({n} parcela(s))."
                st.rerun()
            except ValueError as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"Erro ao excluir a compra: {e}")


def _sub_faturas_futuras(df_p, df_p2):
    st.subheader("Projeção de Faturas Futuras")
    if df_p.empty or df_p2.empty:
        st.info("Nenhuma parcela pendente para gerar projeção.")
        return

    df_pend = df_p2[df_p2["status"] == "pendente"].copy()
    if df_pend.empty:
        st.success("🎉 Todas as faturas estão totalmente pagas! Sem parcelas pendentes.")
        return

    df_pend["Mês Vencimento"] = df_pend["vencimento"].astype(str).str.slice(0, 7)
    df_fat_group = df_pend.groupby(["Mês Vencimento", "cartao"])["valor"].sum().reset_index()
    df_pivot     = df_fat_group.pivot(index="Mês Vencimento", columns="cartao", values="valor").fillna(0.0)

    st.markdown("##### Valores projetados por Fatura (R$)")
    df_pivot_fmt = df_pivot.copy()
    for col in df_pivot_fmt.columns:
        df_pivot_fmt[col] = df_pivot_fmt[col].apply(fmt_moeda)
    st.dataframe(df_pivot_fmt, use_container_width=True)
    st.markdown("<br>", unsafe_allow_html=True)

    fig_proj = px.bar(df_fat_group, x="Mês Vencimento", y="valor", color="cartao",
                      labels={"valor": "Total da Fatura (R$)", "Mês Vencimento": "Mês da Fatura", "cartao": "Cartão"},
                      title="Distribuição Mensal das Faturas Futuras",
                      template="plotly_white", color_discrete_sequence=px.colors.qualitative.Set2)
    fig_proj.update_layout(barmode="stack", separators=',.')
    st.plotly_chart(fig_proj, use_container_width=True)

    st.markdown("---")
    st.markdown("##### 🔍 Detalhamento de Fatura Específica")
    col_d1, col_d2 = st.columns(2)
    lista_cartoes_det = ["Todos"] + list(df_fat_group["cartao"].unique())
    lista_meses_det   = sorted(list(df_fat_group["Mês Vencimento"].unique()))
    sel_cartao_det = col_d1.selectbox("Selecione o Cartão", lista_cartoes_det, key="sel_cartao_det")
    sel_mes_det    = col_d2.selectbox("Selecione o Mês da Fatura", lista_meses_det, key="sel_mes_det")

    df_detalhe = df_pend[df_pend["Mês Vencimento"] == sel_mes_det].copy()
    if sel_cartao_det != "Todos":
        df_detalhe = df_detalhe[df_detalhe["cartao"] == sel_cartao_det]

    if df_detalhe.empty:
        st.info("Nenhum lançamento pendente encontrado para este filtro.")
    else:
        st.markdown(f"**Total da fatura selecionada: {fmt_moeda(float(df_detalhe['valor'].sum()))}**")
        df_det_show = df_detalhe[["descricao", "cartao", "numero", "total", "valor", "vencimento"]].copy()
        df_det_show["valor"]      = df_det_show["valor"].apply(fmt_moeda)
        df_det_show["vencimento"] = df_det_show["vencimento"].apply(converter_data_para_exibicao)
        df_det_show.columns = ["Descrição/Item", "Cartão", "Parcela", "Total Parc.", "Valor", "Vencimento"]
        st.dataframe(df_det_show, use_container_width=True, hide_index=True)


def _sub_lancar_historico():
    st.subheader("Lançar Parcelas Anteriores / Saldo Devedor")
    exibir_mensagem_pendente()
    st.markdown(
        "Utilize este formulário para lançar compras parceladas feitas antes do início do uso "
        "deste aplicativo que ainda possuem parcelas a vencer no cartão de crédito."
    )

    # Fora do st.form de propósito — ver comentário em paginas/lancar_despesa.py.
    c_valor, _ = st.columns([1, 2])
    with c_valor:
        val_parc_m = campo_valor_moeda("Valor da Parcela (R$) *", base_key="m_val")

    with st.form("form_parcelas_manuais", clear_on_submit=True):
        col_m1, col_m2 = st.columns(2)
        card_m = col_m1.selectbox("Cartão de Crédito", obter_nomes_cartoes(), key="m_card")
        desc_m = col_m2.text_input("Descrição da Compra * (ex: Compra Geladeira)")

        col_m4, col_m5 = st.columns(2)
        parc_init_m  = col_m4.selectbox("Próxima Parcela a vencer *", list(range(1, 49)), index=0, key="m_init")
        parc_total_m = col_m5.selectbox("Total de Parcelas da Compra *", list(range(1, 49)), index=0, key="m_total")

        col_m6, col_m7 = st.columns(2)
        data_compra_m = col_m6.date_input("Data da compra (opcional)", value=None,
                                          min_value=date(2000, 1, 1), max_value=date.today(),
                                          format="DD/MM/YYYY", key="m_data_compra")
        venc_init_m = col_m7.date_input("Vencimento da próxima parcela a vencer *",
                                        value=date.today(), format="DD/MM/YYYY", key="m_date")
        obs_m      = st.text_input("Observação (opcional)", key="m_obs")
        sub_manual = st.form_submit_button("✔ Salvar Parcelas Históricas", type="primary", use_container_width=True)

    if sub_manual:
        erros_m = []
        if not desc_m.strip(): erros_m.append("Preencha a descrição.")
        if parc_init_m > parc_total_m: erros_m.append("A próxima parcela não pode ser maior que o total.")
        if data_compra_m and data_compra_m > venc_init_m:
            erros_m.append("A data da compra não pode ser posterior ao vencimento da próxima parcela.")
        try:
            v_p = parse_valor(val_parc_m)
            if not (0 < v_p <= 1_000_000):
                erros_m.append("Valor deve estar entre R$ 0,01 e R$ 1.000.000,00.")
        except Exception:
            erros_m.append("Valor da parcela inválido.")
            v_p = 0

        if erros_m:
            for e in erros_m: st.error(e)
        else:
            if st.session_state.get("salvando_parcela"):
                st.warning("Aguarde, salvando...")
            else:
                st.session_state["salvando_parcela"] = True
                try:
                    salvar_parcela_manual(card_m, desc_m.strip(), v_p, parc_init_m, parc_total_m,
                                          venc_init_m.strftime("%Y-%m-%d"), obs_m.strip(),
                                          data_compra_m.strftime("%Y-%m-%d") if data_compra_m else None)
                    st.session_state["salvando_parcela"] = False
                    concluir_com_sucesso(f"Parcelas históricas do item '{desc_m}' cadastradas com sucesso!",
                                         campo_valor_base_key="m_val")
                except Exception as e:
                    st.session_state["salvando_parcela"] = False
                    st.error(f"Erro ao salvar parcelas: {e}")
                finally:
                    st.session_state["salvando_parcela"] = False


def _sub_configuracoes():
    st.subheader("Gerenciamento de Cartões")
    exibir_mensagem_pendente()
    st.markdown("##### Cartões Cadastrados")
    df_c = carregar_cartoes()
    if df_c.empty:
        st.info("Nenhum cartão cadastrado no banco de dados.")
    else:
        df_c_show = df_c[["id", "nome", "limite", "dia_fechamento", "dia_vencimento"]].copy()
        df_c_show["limite"] = df_c_show["limite"].apply(fmt_moeda)
        df_c_show.columns   = ["ID", "Nome do Cartão", "Limite de Crédito", "Dia do Fechamento", "Dia do Vencimento"]
        event_c = st.dataframe(df_c_show, use_container_width=True, hide_index=True,
                               on_select="rerun", selection_mode="single-row",
                               key=f"df_cartoes_config_list_{st.session_state.get('_ver_df_cartoes', 0)}")

        # Ignora seleção "velha" (posição fora do intervalo após exclusão/recarga)
        rows_c = [i for i in event_c.selection.rows if 0 <= i < len(df_c)]
        if rows_c:
            idx_sel     = rows_c[0]
            id_cartao   = int(df_c.iloc[idx_sel]["id"])
            nome_cartao = df_c.iloc[idx_sel]["nome"]
            st.warning(f"⚠️ Cartão selecionado: **#{id_cartao} — {nome_cartao}**")

            # Item 3 · Verificar vínculos antes de permitir exclusão
            vinculos = cartao_tem_vinculos(nome_cartao)
            tem_vinculos = vinculos["despesas"] > 0 or vinculos["parcelas_pendentes"] > 0

            if tem_vinculos:
                msgs = []
                if vinculos["despesas"] > 0:
                    msgs.append(f"{vinculos['despesas']} despesa(s) registrada(s)")
                if vinculos["parcelas_pendentes"] > 0:
                    msgs.append(f"{vinculos['parcelas_pendentes']} parcela(s) pendente(s)")
                st.error(
                    f"🚫 Não é possível excluir o cartão **{nome_cartao}** pois ele possui "
                    f"{' e '.join(msgs)} vinculadas. "
                    f"Quite ou exclua os registros antes de remover o cartão."
                )
            else:
                # Item 2 · Confirmação explícita antes de excluir cartão
                confirmar_c = st.checkbox(
                    f"Confirmo a exclusão do cartão {nome_cartao}",
                    key=f"confirmar_excl_cartao_{id_cartao}"
                )
                if confirmar_c:
                    if st.button("🗑 Excluir cartão", type="primary",
                                 use_container_width=True, key="btn_del_card"):
                        try:
                            excluir_cartao(id_cartao)
                            # Troca a key da tabela para limpar a seleção guardada
                            st.session_state["_ver_df_cartoes"] = st.session_state.get("_ver_df_cartoes", 0) + 1
                            st.success(f"Cartão '{nome_cartao}' excluído com sucesso!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao excluir cartão: {e}")
                else:
                    st.button("🗑 Excluir cartão", type="primary",
                              use_container_width=True, disabled=True, key="btn_del_card_dis")
        else:
            st.info("💡 Clique em um cartão na tabela acima para liberar as opções de exclusão.")

    st.markdown("---")
    st.markdown("##### Cadastrar Novo Cartão")

    # Fora do st.form de propósito — ver comentário em paginas/lancar_despesa.py.
    c_valor, _ = st.columns([1, 2])
    with c_valor:
        limite_nc = campo_valor_moeda("Limite de Crédito (R$) *", base_key="nc_limit")

    with st.form("form_cadastro_cartao", clear_on_submit=True):
        col_nc1, col_nc3 = st.columns(2)
        nome_nc       = col_nc1.text_input("Nome do Cartão * (ex: Nubank Platinum)")
        fechamento_nc = col_nc3.selectbox("Dia do Fechamento da Fatura *", list(range(1, 32)), index=4,  key="nc_fech")
        vencimento_nc = st.selectbox("Dia do Vencimento da Fatura *", list(range(1, 32)), index=11, key="nc_venc")
        submit_nc = st.form_submit_button("✔ Cadastrar Novo Cartão", type="primary", use_container_width=True)

    if submit_nc:
        erros_nc = []
        if not nome_nc.strip(): erros_nc.append("Preencha o nome do cartão.")
        try:
            lim = parse_valor(limite_nc)
            if lim < 0: erros_nc.append("Limite não pode ser negativo.")
        except Exception:
            erros_nc.append("Limite de crédito inválido.")
            lim = 0
        if erros_nc:
            for e in erros_nc: st.error(e)
        else:
            try:
                salvar_cartao(nome_nc.strip(), lim, fechamento_nc, vencimento_nc)
                concluir_com_sucesso(f"Novo cartão '{nome_nc}' cadastrado com sucesso!",
                                     campo_valor_base_key="nc_limit")
            except Exception as e:
                st.error(f"Erro ao cadastrar cartão: {e}")


def _sugerir_datas_fechamento(dia_fechamento: int, dia_vencimento: int, mes_referencia: str):
    """
    Sugestão inicial (não vinculante) de fechamento/vencimento para um mês
    de referência, com base no dia fixo cadastrado no cartão. Serve apenas
    para pré-preencher o formulário — o usuário sempre pode ajustar antes
    de registrar o fechamento real.
    """
    ano, mes = map(int, mes_referencia.split("-"))
    max_day_venc = calendar.monthrange(ano, mes)[1]
    data_vencimento_sugerida = date(ano, mes, min(dia_vencimento, max_day_venc))
    if dia_vencimento < dia_fechamento:
        mes_fech_base = add_months(date(ano, mes, 1), -1)
    else:
        mes_fech_base = date(ano, mes, 1)
    max_day_fech = calendar.monthrange(mes_fech_base.year, mes_fech_base.month)[1]
    data_fechamento_sugerida = date(mes_fech_base.year, mes_fech_base.month, min(dia_fechamento, max_day_fech))
    return data_fechamento_sugerida, data_vencimento_sugerida


def _sub_fechamentos():
    st.subheader("Fechamentos Reais de Fatura")
    st.markdown(
        "A data de fechamento de uma fatura pode variar de mês para mês "
        "(fins de semana, feriados, ajustes do banco). Registre aqui o "
        "fechamento e o vencimento **reais** de cada fatura à medida que "
        "eles acontecem — a partir daí, esse registro passa a valer como "
        "fonte de verdade para as parcelas desse mês, no lugar da "
        "estimativa automática baseada no dia fixo cadastrado no cartão."
    )

    df_c = carregar_cartoes()
    if df_c.empty:
        st.info("Cadastre um cartão primeiro, na aba ⚙️ Cartões & Configurações.")
        return

    with st.form("form_fechamento", clear_on_submit=True):
        f1, f2 = st.columns(2)
        cartao_f  = f1.selectbox("Cartão", obter_nomes_cartoes(), key="fech_cartao")
        mes_ref_f = f2.text_input("Mês de referência do vencimento * (AAAA-MM)",
                                   value=date.today().strftime("%Y-%m"), key="fech_mes")

        card_info       = df_c[df_c["nome"] == cartao_f]
        dia_fech_padrao = int(card_info.iloc[0]["dia_fechamento"]) if not card_info.empty else 5
        dia_venc_padrao = int(card_info.iloc[0]["dia_vencimento"]) if not card_info.empty else 12


        sugestao_fech, sugestao_venc = date.today(), date.today()
        if re.match(r"^\d{4}-\d{2}$", mes_ref_f or ""):
            try:
                sugestao_fech, sugestao_venc = _sugerir_datas_fechamento(dia_fech_padrao, dia_venc_padrao, mes_ref_f)
            except Exception:
                pass

        st.caption("Datas pré-preenchidas com base no dia fixo cadastrado no cartão — ajuste para o valor real.")
        f3, f4 = st.columns(2)
        data_fech_f = f3.date_input("Data real do fechamento *", value=sugestao_fech,
                                    format="DD/MM/YYYY", key="fech_data_fechamento")
        data_venc_f = f4.date_input("Data real do vencimento *", value=sugestao_venc,
                                    format="DD/MM/YYYY", key="fech_data_vencimento")
        obs_f = st.text_input("Observação (opcional)", key="fech_obs")

        sub_f = st.form_submit_button("✔ Registrar fechamento", type="primary", use_container_width=True)

    if sub_f:
        erros_f = []
        if not re.match(r"^\d{4}-\d{2}$", mes_ref_f or ""):
            erros_f.append("Mês de referência deve estar no formato AAAA-MM (ex.: 2026-07).")
        if data_venc_f < data_fech_f:
            erros_f.append("O vencimento não pode ser anterior ao fechamento.")
        if erros_f:
            for e in erros_f: st.error(e)
        else:
            try:
                salvar_fechamento(cartao_f, mes_ref_f, data_fech_f, data_venc_f, obs_f.strip())
                st.success(f"Fechamento de {cartao_f} para {mes_ref_f} registrado com sucesso!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao registrar fechamento: {e}")

    st.markdown("---")
    st.markdown("##### Fechamentos Registrados")
    cartao_filtro_f = st.selectbox("Filtrar por cartão", ["Todos"] + obter_nomes_cartoes(), key="fech_filtro_cartao")

    if cartao_filtro_f == "Todos":
        registros = []
        for nome in obter_nomes_cartoes():
            fechs_nome = fechamentos_ordenados_por_cartao(nome)
            for f in fechs_nome:
                registros.append(dict(f, cartao=nome))
            buracos = detectar_buracos_fechamentos(fechs_nome)
            if buracos:
                meses_fmt = ", ".join(fmt_mes_str_pt(m) for m in buracos)
                st.warning(
                    f"⚠️ **{nome}**: faltam fechamentos de {meses_fmt}. "
                    f"Parcelas nesses meses vão usar a estimativa automática "
                    f"até você registrar o fechamento real."
                )
        registros.sort(key=lambda r: r["data_fechamento"])
    else:
        fechs_filtro = fechamentos_ordenados_por_cartao(cartao_filtro_f)
        registros = [dict(f, cartao=cartao_filtro_f) for f in fechs_filtro]
        buracos = detectar_buracos_fechamentos(fechs_filtro)
        if buracos:
            meses_fmt = ", ".join(fmt_mes_str_pt(m) for m in buracos)
            st.warning(
                f"⚠️ Faltam fechamentos de **{meses_fmt}** para {cartao_filtro_f}. "
                f"Parcelas nesses meses vão usar a estimativa automática "
                f"até você registrar o fechamento real."
            )

    if not registros:
        st.info("Nenhum fechamento registrado ainda para este filtro.")
        return

    df_fech_show = pd.DataFrame(registros)
    df_fech_show["data_fechamento"] = df_fech_show["data_fechamento"].apply(lambda d: d.strftime("%d/%m/%Y"))
    df_fech_show["data_vencimento"] = df_fech_show["data_vencimento"].apply(lambda d: d.strftime("%d/%m/%Y"))
    cols = [c for c in ["id", "cartao", "mes_referencia", "data_fechamento", "data_vencimento", "observacao"] if c in df_fech_show.columns]
    df_fech_show = df_fech_show[cols]
    df_fech_show.columns = ["ID", "Cartão", "Mês Ref.", "Fechamento", "Vencimento", "Obs"][:len(cols)]

    event_f = st.dataframe(df_fech_show, use_container_width=True, hide_index=True,
                           on_select="rerun", selection_mode="single-row", key="df_fechamentos_list")
    rows_f = [i for i in event_f.selection.rows if 0 <= i < len(registros)]
    if rows_f:
        idx_sel = rows_f[0]
        id_f    = int(registros[idx_sel]["id"])
        if st.button("🗑 Excluir este fechamento", type="primary", use_container_width=True, key="btn_excl_fech"):
            try:
                excluir_fechamento(id_f)
                st.success(f"Fechamento #{id_f} excluído.")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao excluir: {e}")
    else:
        st.info("💡 Clique em um fechamento na tabela acima para excluí-lo.")


def render():
    sub_cc_list, sub_cc_faturas, sub_cc_fech, sub_cc_lanc, sub_cc_config = st.tabs([
        "📊 Parcelas", "📅 Faturas Futuras", "🗓️ Fechamentos", "➕ Lançar Histórico", "⚙️ Cartões & Configurações"
    ])

    df_p = carregar_parcelas()
    df_d = carregar_despesas()
    hoje = hoje_str()
    df_p2 = _preparar_df_parcelas(df_p, df_d)

    with sub_cc_list:
        _sub_parcelas(df_p, df_p2, hoje)

    with sub_cc_faturas:
        _sub_faturas_futuras(df_p, df_p2)

    with sub_cc_fech:
        _sub_fechamentos()

    with sub_cc_lanc:
        _sub_lancar_historico()

    with sub_cc_config:
        _sub_configuracoes()