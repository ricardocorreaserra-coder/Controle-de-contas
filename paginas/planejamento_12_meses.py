"""Aba: 🔮 Planejamento 12 Meses — panorama, lançamentos futuros e recorrentes."""

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import CAT_DESP, CAT_REC
from sheets.loaders import carregar_despesas, carregar_receitas, carregar_planejamento
from logica.despesas import encerrar_recorrencia_despesa
from logica.receitas import salvar_receita, encerrar_recorrencia_receita
from logica.planejamento import (
    get_panorama, invalidar_cache_panorama, _ts_panorama,
    salvar_planejamento, salvar_planejamento_replicado, excluir_planejamento,
)
from logica.exportacao import gerar_excel_panorama, gerar_csv_panorama
from utils.datas import proximos_12_meses, fmt_mes_str_pt
from utils.formatacao import fmt_moeda, parse_valor, converter_data_para_exibicao
from utils.widgets import campo_valor_moeda, concluir_com_sucesso, exibir_mensagem_pendente


def _sub_panorama(meses_futuros):
    # R-03 · Barra de controle: timestamp + botão de atualização manual
    ctrl_col1, ctrl_col2 = st.columns([3, 1])
    ctrl_col1.caption(f"🕐 Projeções calculadas às {_ts_panorama()} "
                      f"(cache persiste enquanto a sessão estiver aberta).")
    if ctrl_col2.button("🔄 Atualizar projeções", key="btn_atualizar_panorama",
                        use_container_width=True):
        invalidar_cache_panorama()
        st.rerun()

    # R-03 · Carrega do cache (recomputa apenas se o cache foi invalidado)
    df_linhas, df_resumo = get_panorama()

    sem_dados = df_resumo.empty or (
        df_resumo["Receitas"].eq(0).all() and df_resumo["Despesas (total)"].eq(0).all()
    )
    if sem_dados:
        st.info("Nenhuma projeção disponível ainda. Cadastre despesas/receitas recorrentes, "
                "parcelas de cartão ou lançamentos no Planejamento para ver o panorama aqui.")
        return

    st.markdown("##### Resumo mês a mês")
    df_resumo_show = df_resumo[["Mês", "Receitas", "Cartão", "Recorrentes",
                                 "Outras desp.", "Despesas (total)", "Saldo projetado"]].copy()
    for col in ["Receitas", "Cartão", "Recorrentes", "Outras desp.", "Despesas (total)", "Saldo projetado"]:
        df_resumo_show[col] = df_resumo_show[col].apply(fmt_moeda)
    st.dataframe(df_resumo_show, use_container_width=True, hide_index=True)

    st.caption("Saldo projetado considera fluxo de caixa por vencimento (cartão) e por data de "
               "competência (recorrentes/avulsas/planejamento manual).")

    fig_plan = go.Figure()
    fig_plan.add_bar(x=df_resumo["Mês"], y=df_resumo["Cartão"], name="Cartão", marker_color="#d97706")
    fig_plan.add_bar(x=df_resumo["Mês"], y=df_resumo["Recorrentes"], name="Recorrentes", marker_color="#dc2626")
    fig_plan.add_bar(x=df_resumo["Mês"], y=df_resumo["Outras desp."], name="Outras despesas", marker_color="#7c3aed")
    fig_plan.add_trace(go.Scatter(x=df_resumo["Mês"], y=df_resumo["Receitas"], name="Receitas",
                                  mode="lines+markers", line=dict(color="#16a34a", width=3)))
    fig_plan.update_layout(barmode="stack", template="plotly_white", separators=',.',
                           height=350, legend=dict(orientation="h", y=-0.2),
                           margin=dict(t=10, b=10, l=10, r=10))
    st.plotly_chart(fig_plan, use_container_width=True)

    st.markdown("---")
    st.markdown("##### 🔍 Detalhamento por mês")
    mes_det_sel = st.selectbox("Selecione o mês", meses_futuros,
                               format_func=fmt_mes_str_pt, key="plan_mes_det")
    df_mes_det = df_linhas[df_linhas["mes"] == mes_det_sel].copy()
    if df_mes_det.empty:
        st.info("Nenhum lançamento projetado para este mês.")
    else:
        df_mes_det["valor"] = df_mes_det["valor"].apply(fmt_moeda)
        df_mes_det = df_mes_det[["tipo", "origem", "descricao", "categoria", "valor"]]
        df_mes_det.columns = ["Tipo", "Origem", "Descrição", "Categoria", "Valor"]
        st.dataframe(df_mes_det, use_container_width=True, hide_index=True)

    # R-02 · Exportação
    st.markdown("---")
    st.markdown("##### ⬇️ Exportar projeção")
    nome_arquivo = f"planejamento_{date.today().strftime('%Y%m%d')}"
    exp_col1, exp_col2 = st.columns(2)
    with exp_col1:
        try:
            excel_bytes = gerar_excel_panorama(df_linhas, df_resumo)
            st.download_button(
                label="📥 Baixar Excel (.xlsx)",
                data=excel_bytes,
                file_name=f"{nome_arquivo}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key="btn_export_xlsx",
            )
        except Exception as e:
            st.error(f"Erro ao gerar Excel: {e}")
    with exp_col2:
        try:
            csv_bytes = gerar_csv_panorama(df_linhas, df_resumo)
            st.download_button(
                label="📄 Baixar CSV (.csv)",
                data=csv_bytes,
                file_name=f"{nome_arquivo}.csv",
                mime="text/csv",
                use_container_width=True,
                key="btn_export_csv",
            )
        except Exception as e:
            st.error(f"Erro ao gerar CSV: {e}")


def _sub_lancamentos_futuros(meses_futuros):
    st.subheader("Lançar item de Planejamento")
    exibir_mensagem_pendente()
    st.caption("Use para itens pontuais que não são recorrentes nem parcelas "
               "(ex.: IPTU em março, 13º salário em dezembro).")

    # Fora do st.form de propósito — ver comentário em paginas/lancar_despesa.py.
    c_valor, _ = st.columns([1, 3])
    with c_valor:
        valor_pl = campo_valor_moeda("Valor (R$) *", base_key="pl_valor")

    with st.form("form_planejamento", clear_on_submit=True):
        p1, p2 = st.columns([1, 3])
        tipo_pl = p1.selectbox("Tipo", ["Despesa", "Receita"])
        desc_pl = p2.text_input("Descrição *")

        cat_opcoes = CAT_DESP if tipo_pl == "Despesa" else CAT_REC
        cat_pl = st.selectbox("Categoria", [""] + cat_opcoes, key="pl_cat")

        mes_pl = st.selectbox("Mês de competência *", meses_futuros,
                              format_func=fmt_mes_str_pt, key="pl_mes")
        replicar_pl = st.checkbox("Replicar este lançamento para os 12 meses", key="pl_replicar")
        obs_pl = st.text_input("Observação (opcional)", key="pl_obs")

        sub_pl = st.form_submit_button("✔ Salvar Planejamento", type="primary", use_container_width=True)

    if sub_pl:
        erros_pl = []
        if not desc_pl.strip(): erros_pl.append("Preencha a descrição.")
        try:
            v_pl = parse_valor(valor_pl)
            if not (0 < v_pl <= 1_000_000):
                erros_pl.append("Valor deve estar entre R$ 0,01 e R$ 1.000.000,00.")
        except Exception:
            erros_pl.append("Valor inválido.")
            v_pl = 0

        if erros_pl:
            for e in erros_pl: st.error(e)
        else:
            try:
                tipo_db = "despesa" if tipo_pl == "Despesa" else "receita"
                if replicar_pl:
                    salvar_planejamento_replicado(tipo_db, desc_pl.strip(), v_pl, meses_futuros, cat_pl, obs_pl.strip())
                    msg = f"Lançamento '{desc_pl}' replicado para os 12 meses!"
                else:
                    salvar_planejamento(tipo_db, desc_pl.strip(), v_pl, mes_pl, cat_pl, obs_pl.strip())
                    msg = f"Lançamento '{desc_pl}' adicionado ao planejamento de {fmt_mes_str_pt(mes_pl)}!"
                invalidar_cache_panorama()
                concluir_com_sucesso(msg, campo_valor_base_key="pl_valor")
            except Exception as e:
                st.error(f"Erro ao salvar planejamento: {e}")

    st.markdown("---")
    st.markdown("##### Itens de Planejamento Cadastrados")
    df_pl_list = carregar_planejamento()
    if df_pl_list.empty:
        st.info("Nenhum item de planejamento cadastrado.")
        return

    df_pl_list = df_pl_list.copy()
    df_pl_list["valor"] = pd.to_numeric(df_pl_list["valor"], errors='coerce').fillna(0.0)
    df_pl_show = df_pl_list[["id", "tipo", "descricao", "valor", "mes", "categoria", "observacao"]].copy()
    df_pl_show["valor"] = df_pl_show["valor"].apply(fmt_moeda)
    df_pl_show["mes"]   = df_pl_show["mes"].apply(fmt_mes_str_pt)
    df_pl_show.columns  = ["ID", "Tipo", "Descrição", "Valor", "Mês", "Categoria", "Obs"]

    event_pl = st.dataframe(df_pl_show, use_container_width=True, hide_index=True,
                            on_select="rerun", selection_mode="single-row", key="df_planejamento_list")
    if event_pl.selection.rows:
        idx_sel = event_pl.selection.rows[0]
        id_pl   = int(df_pl_list.iloc[idx_sel]["id"])
        desc_pl_sel = df_pl_list.iloc[idx_sel]["descricao"]
        confirmar_pl = st.checkbox(f"Confirmo a exclusão do item de planejamento #{id_pl} — {desc_pl_sel}",
                                   key=f"confirmar_excl_pl_{id_pl}")
        if confirmar_pl:
            if st.button("🗑 Excluir item de planejamento", type="primary",
                         use_container_width=True, key="btn_excl_pl"):
                try:
                    excluir_planejamento(id_pl)
                    invalidar_cache_panorama()
                    st.success(f"Item #{id_pl} excluído!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao excluir: {e}")
        else:
            st.button("🗑 Excluir item de planejamento", type="primary",
                      use_container_width=True, disabled=True, key="btn_excl_pl_dis")
    else:
        st.info("💡 Clique em um item na tabela acima para liberar a exclusão.")


def _sub_recorrentes():
    st.subheader("Despesas e Receitas Recorrentes")

    df_d_rec = carregar_despesas()
    df_r_rec = carregar_receitas()

    st.markdown("##### Despesas recorrentes")
    if df_d_rec.empty or "recorrente" not in df_d_rec.columns:
        st.info("Nenhuma despesa recorrente cadastrada.")
    else:
        df_d_rec_f = df_d_rec[df_d_rec["recorrente"].astype(str).str.lower() == "sim"].copy()
        if df_d_rec_f.empty:
            st.info("Nenhuma despesa recorrente cadastrada.")
        else:
            df_d_rec_f["valor"] = pd.to_numeric(df_d_rec_f["valor"], errors='coerce').fillna(0.0)
            df_d_rec_show = df_d_rec_f[["id", "descricao", "valor", "data", "pagamento",
                                        "categoria", "recorrencia_fim"]].copy()
            df_d_rec_show["valor"] = df_d_rec_show["valor"].apply(fmt_moeda)
            df_d_rec_show["data"]  = df_d_rec_show["data"].apply(converter_data_para_exibicao)
            df_d_rec_show["recorrencia_fim"] = df_d_rec_show["recorrencia_fim"].apply(
                lambda x: converter_data_para_exibicao(x) if str(x).strip() else "— ativa —")
            df_d_rec_show.columns = ["ID", "Descrição", "Valor", "Início", "Pagamento", "Categoria", "Fim da Recorrência"]

            event_dr = st.dataframe(df_d_rec_show, use_container_width=True, hide_index=True,
                                    on_select="rerun", selection_mode="single-row", key="df_desp_recorrentes")
            if event_dr.selection.rows:
                idx_sel = event_dr.selection.rows[0]
                id_dr   = int(df_d_rec_f.iloc[idx_sel]["id"])
                desc_dr = df_d_rec_f.iloc[idx_sel]["descricao"]
                if st.button("⏹ Encerrar recorrência (hoje)", key="btn_encerrar_dr", use_container_width=True):
                    try:
                        encerrar_recorrencia_despesa(id_dr)
                        invalidar_cache_panorama()
                        st.success(f"Recorrência de '{desc_dr}' encerrada a partir de hoje.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro: {e}")

    st.markdown("---")
    st.markdown("##### Receitas recorrentes")
    if df_r_rec.empty or "recorrente" not in df_r_rec.columns:
        st.info("Nenhuma receita recorrente cadastrada.")
    else:
        df_r_rec_f = df_r_rec[df_r_rec["recorrente"].astype(str).str.lower() == "sim"].copy()
        if df_r_rec_f.empty:
            st.info("Nenhuma receita recorrente cadastrada.")
        else:
            df_r_rec_f["valor"] = pd.to_numeric(df_r_rec_f["valor"], errors='coerce').fillna(0.0)
            df_r_rec_show = df_r_rec_f[["id", "descricao", "valor", "data", "categoria", "recorrencia_fim"]].copy()
            df_r_rec_show["valor"] = df_r_rec_show["valor"].apply(fmt_moeda)
            df_r_rec_show["data"]  = df_r_rec_show["data"].apply(converter_data_para_exibicao)
            df_r_rec_show["recorrencia_fim"] = df_r_rec_show["recorrencia_fim"].apply(
                lambda x: converter_data_para_exibicao(x) if str(x).strip() else "— ativa —")
            df_r_rec_show.columns = ["ID", "Descrição", "Valor", "Início", "Categoria", "Fim da Recorrência"]

            event_rr = st.dataframe(df_r_rec_show, use_container_width=True, hide_index=True,
                                    on_select="rerun", selection_mode="single-row", key="df_rec_recorrentes")
            if event_rr.selection.rows:
                idx_sel = event_rr.selection.rows[0]
                id_rr   = int(df_r_rec_f.iloc[idx_sel]["id"])
                desc_rr = df_r_rec_f.iloc[idx_sel]["descricao"]
                if st.button("⏹ Encerrar recorrência (hoje)", key="btn_encerrar_rr", use_container_width=True):
                    try:
                        encerrar_recorrencia_receita(id_rr)
                        invalidar_cache_panorama()
                        st.success(f"Recorrência de '{desc_rr}' encerrada a partir de hoje.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro: {e}")

    st.markdown("---")
    st.markdown("##### Cadastro rápido de receita recorrente")
    exibir_mensagem_pendente()

    # Fora do st.form de propósito — ver comentário em paginas/lancar_despesa.py.
    c_valor, _ = st.columns([1, 3])
    with c_valor:
        qvalor = campo_valor_moeda("Valor (R$) *", base_key="qr_valor")

    with st.form("form_receita_recorrente_rapida", clear_on_submit=True):
        qdesc = st.text_input("Descrição * (ex: Salário)")
        qr3, qr4 = st.columns(2)
        qdata = qr3.date_input("Início *", value=date.today(), format="DD/MM/YYYY", key="qr_data")
        qcat  = qr4.selectbox("Categoria", [""] + CAT_REC, key="qr_cat")
        qsubmit = st.form_submit_button("✔ Cadastrar receita recorrente", type="primary", use_container_width=True)

    if qsubmit:
        erros_qr = []
        if not qdesc.strip(): erros_qr.append("Preencha a descrição.")
        try:
            qv = parse_valor(qvalor)
            if not (0 < qv <= 1_000_000):
                erros_qr.append("Valor deve estar entre R$ 0,01 e R$ 1.000.000,00.")
        except Exception:
            erros_qr.append("Valor inválido.")
            qv = 0
        if erros_qr:
            for e in erros_qr: st.error(e)
        else:
            try:
                salvar_receita(qdesc.strip(), qv, qdata.strftime("%Y-%m-%d"), qcat, "",
                               recorrente=True, recorrencia_fim=None)
                invalidar_cache_panorama()
                concluir_com_sucesso(f"Receita recorrente '{qdesc}' cadastrada!", campo_valor_base_key="qr_valor")
            except Exception as e:
                st.error(f"Erro ao cadastrar: {e}")


def render():
    meses_futuros = proximos_12_meses()
    primeiro_mes_lbl = fmt_mes_str_pt(meses_futuros[0])
    st.markdown(
        f'<div class="plan-banner">📅 Visão de <b>planejamento</b>: próximos 12 meses a partir de '
        f'{primeiro_mes_lbl}. Diferente do Dashboard, que mostra o mês corrente/passado.</div>',
        unsafe_allow_html=True
    )

    sub_plan_panorama, sub_plan_futuros, sub_plan_recorrentes = st.tabs([
        "📈 Panorama 12 Meses", "🗓️ Lançamentos Futuros", "🔁 Recorrentes"
    ])

    with sub_plan_panorama:
        _sub_panorama(meses_futuros)

    with sub_plan_futuros:
        _sub_lancamentos_futuros(meses_futuros)

    with sub_plan_recorrentes:
        _sub_recorrentes()