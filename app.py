"""
Controle de Contas - Versão Web (Streamlit + Google Sheets)
Uso: streamlit run app.py
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, datetime
import calendar
import gspread
from google.oauth2.service_account import Credentials
import json

# ── Configuração da página ─────────────────────────────────────────────────────
st.set_page_config(
    page_title="Controle de Contas",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Estilos CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #2563eb, #1e40af);
        color: white; padding: 1rem 1.5rem; border-radius: 10px;
        margin-bottom: 1.5rem;
        display: flex; align-items: center; gap: 0.5rem;
    }
    .card {
        background: white; border: 1px solid #e2e8f0;
        border-radius: 10px; padding: 1rem 1.5rem;
        text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,.06);
    }
    .card-label { font-size: 0.8rem; color: #64748b; margin-bottom: 4px; }
    .card-value { font-size: 1.4rem; font-weight: 700; }
    .green  { color: #16a34a; }
    .red    { color: #dc2626; }
    .blue   { color: #2563eb; }
    .orange { color: #d97706; }
    .stTabs [data-baseweb="tab"] { font-size: 0.95rem; }
    div[data-testid="stSuccess"] { border-radius: 8px; }
    div[data-testid="stWarning"] { border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

# ── Constantes ─────────────────────────────────────────────────────────────────
PAGAMENTOS   = ["Cartão de crédito", "Débito", "Pix", "Vale alimentação"]
CAT_DESP     = ["Alimentação", "Transporte", "Saúde", "Moradia", "Lazer",
                 "Educação", "Vestuário", "Outros"]
CAT_REC      = ["Salário", "Freelance", "Investimentos", "Aluguel recebido", "Outros"]
CARTOES      = ["Nubank", "Itaú", "Bradesco", "Inter", "Santander", "Outro"]
DIAS_VENC    = [1, 5, 7, 10, 15, 20, 25, 28]
PARCELAS_OPT = [1, 2, 3, 4, 5, 6, 10, 12, 18, 24]

# ── Helpers ────────────────────────────────────────────────────────────────────
def fmt_moeda(v):
    try:
        return "R$ {:,.2f}".format(float(v)).replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"

def add_months(dt: date, months: int) -> date:
    m = dt.month - 1 + months
    year = dt.year + m // 12
    month = m % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)

def hoje_str():
    return date.today().strftime("%Y-%m-%d")

def mes_atual():
    return date.today().strftime("%Y-%m")

def card_html(label, value, color_class):
    return f"""
    <div class="card">
        <div class="card-label">{label}</div>
        <div class="card-value {color_class}">{value}</div>
    </div>
    """

# ── Google Sheets ──────────────────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

@st.cache_resource
def get_sheets_client():
    """Conecta ao Google Sheets via credenciais nos secrets."""
    creds_dict = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)

@st.cache_resource
def get_workbook():
    client = get_sheets_client()
    return client.open(st.secrets["SHEET_NAME"])

def get_sheet(name: str):
    wb = get_workbook()
    try:
        return wb.worksheet(name)
    except gspread.WorksheetNotFound:
        ws = wb.add_worksheet(title=name, rows=1000, cols=20)
        # Cabeçalhos por aba
        headers = {
            "despesas": ["id", "descricao", "valor", "data", "local",
                         "pagamento", "categoria", "cartao", "n_parcelas",
                         "observacao", "criado_em"],
            "parcelas": ["id", "despesa_id", "numero", "total",
                         "valor", "vencimento", "status"],
            "receitas": ["id", "descricao", "valor", "data",
                         "categoria", "observacao", "criado_em"],
        }
        if name in headers:
            ws.append_row(headers[name])
        return ws

def sheet_to_df(ws) -> pd.DataFrame:
    data = ws.get_all_records()
    return pd.DataFrame(data) if data else pd.DataFrame()

def next_id(ws) -> int:
    df = sheet_to_df(ws)
    if df.empty or "id" not in df.columns or df["id"].astype(str).str.strip().eq("").all():
        return 1
    return int(df["id"].max()) + 1

# ── Lógica de dados ────────────────────────────────────────────────────────────
def salvar_despesa(desc, valor, data, local, pag, cat, cartao, n_parc, dia_venc, obs):
    ws_d = get_sheet("despesas")
    ws_p = get_sheet("parcelas")
    did  = next_id(ws_d)
    ws_d.append_row([did, desc, valor, data, local, pag, cat,
                     cartao or "", n_parc, obs,
                     datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
    if pag == "Cartão de crédito" and n_parc > 1:
        pid   = next_id(ws_p)
        base  = datetime.strptime(data, "%Y-%m-%d").date()
        vp    = round(valor / n_parc, 2)
        rows  = []
        for i in range(n_parc):
            venc = add_months(base, i + 1)
            mx   = calendar.monthrange(venc.year, venc.month)[1]
            venc = venc.replace(day=min(dia_venc, mx))
            rows.append([pid + i, did, i + 1, n_parc, vp,
                         venc.strftime("%Y-%m-%d"), "pendente"])
        ws_p.append_rows(rows)
    st.cache_data.clear()

def salvar_receita(desc, valor, data, cat, obs):
    ws = get_sheet("receitas")
    rid = next_id(ws)
    ws.append_row([rid, desc, valor, data, cat, obs,
                   datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
    st.cache_data.clear()

def excluir_despesa(did: int):
    ws_d = get_sheet("despesas")
    ws_p = get_sheet("parcelas")
    # Excluir parcelas
    df_p = sheet_to_df(ws_p)
    if not df_p.empty and "despesa_id" in df_p.columns:
        ids_excluir = df_p[df_p["despesa_id"].astype(str) == str(did)].index.tolist()
        for idx in sorted(ids_excluir, reverse=True):
            ws_p.delete_rows(idx + 2)
    # Excluir despesa
    df_d = sheet_to_df(ws_d)
    if not df_d.empty:
        idx_list = df_d[df_d["id"].astype(str) == str(did)].index.tolist()
        for idx in sorted(idx_list, reverse=True):
            ws_d.delete_rows(idx + 2)
    st.cache_data.clear()

def excluir_receita(rid: int):
    ws = get_sheet("receitas")
    df = sheet_to_df(ws)
    if not df.empty:
        idx_list = df[df["id"].astype(str) == str(rid)].index.tolist()
        for idx in sorted(idx_list, reverse=True):
            ws.delete_rows(idx + 2)
    st.cache_data.clear()

def atualizar_parcela(pid: int, status: str):
    ws = get_sheet("parcelas")
    df = sheet_to_df(ws)
    idx_list = df[df["id"].astype(str) == str(pid)].index.tolist()
    for idx in idx_list:
        ws.update_cell(idx + 2, df.columns.get_loc("status") + 1, status)
    st.cache_data.clear()

def baixar_fatura_mes(mes: str, cartao_filtro: str = None):
    ws = get_sheet("parcelas")
    ws_d = get_sheet("despesas")
    df_p = sheet_to_df(ws)
    df_d = sheet_to_df(ws_d)
    if df_p.empty:
        return 0
    mask = (df_p["vencimento"].astype(str).str.startswith(mes)) & \
           (df_p["status"] == "pendente")
    if cartao_filtro and cartao_filtro != "Todos":
        ids_cartao = df_d[df_d["cartao"] == cartao_filtro]["id"].astype(str).tolist()
        mask = mask & df_p["despesa_id"].astype(str).isin(ids_cartao)
    idxs = df_p[mask].index.tolist()
    for idx in idxs:
        ws.update_cell(idx + 2, df_p.columns.get_loc("status") + 1, "pago")
    st.cache_data.clear()
    return len(idxs)

@st.cache_data(ttl=30)
def carregar_despesas():
    return sheet_to_df(get_sheet("despesas"))

@st.cache_data(ttl=30)
def carregar_receitas():
    return sheet_to_df(get_sheet("receitas"))

@st.cache_data(ttl=30)
def carregar_parcelas():
    return sheet_to_df(get_sheet("parcelas"))

# ══════════════════════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="main-header"><span style="font-size:1.6rem">💰</span>'
            '<span style="font-size:1.3rem;font-weight:700">Controle de Contas</span></div>',
            unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# ABAS
# ══════════════════════════════════════════════════════════════════════════════
tab_dash, tab_lanc, tab_rec, tab_lista, tab_cc, tab_cc_rec = st.tabs([
    "📊 Dashboard",
    "➖ Lançar Despesa",
    "➕ Lançar Receita",
    "☰ Despesas",
    "💳 Cartão de Crédito",
    "🏦 Conta Corrente",
])

# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
with tab_dash:
    mes_dash = st.text_input("Mês (AAAA-MM)", value=mes_atual(), key="mes_dash")

    df_d = carregar_despesas()
    df_r = carregar_receitas()

    # Filtrar pelo mês
    desp_mes = df_d[df_d["data"].astype(str).str.startswith(mes_dash)] if not df_d.empty else pd.DataFrame()
    rec_mes  = df_r[df_r["data"].astype(str).str.startswith(mes_dash)]  if not df_r.empty else pd.DataFrame()

    total_rec  = float(rec_mes["valor"].sum())  if not rec_mes.empty  else 0.0
    total_desp = float(desp_mes["valor"].sum()) if not desp_mes.empty else 0.0
    saldo      = total_rec - total_desp
    saldo_cor  = "green" if saldo >= 0 else "red"

    # Cards resumo
    c1, c2, c3 = st.columns(3)
    with c1: st.markdown(card_html("Receitas do mês", fmt_moeda(total_rec), "green"),  unsafe_allow_html=True)
    with c2: st.markdown(card_html("Despesas do mês", fmt_moeda(total_desp), "red"),    unsafe_allow_html=True)
    with c3: st.markdown(card_html("Saldo do mês", fmt_moeda(saldo), saldo_cor),        unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Gráficos
    col1, col2, col3 = st.columns(3)

    # ── Histórico 6 meses ──
    with col1:
        st.subheader("Histórico 6 meses")
        hist = []
        for i in range(5, -1, -1):
            d  = date.today()
            mm = add_months(d, -i).strftime("%Y-%m")
            lbl = add_months(d, -i).strftime("%b/%y")
            r_val = float(df_r[df_r["data"].astype(str).str.startswith(mm)]["valor"].sum()) if not df_r.empty else 0.0
            e_val = float(df_d[df_d["data"].astype(str).str.startswith(mm)]["valor"].sum()) if not df_d.empty else 0.0
            hist.append({"Mês": lbl, "Receita": r_val, "Despesa": e_val})
        df_hist = pd.DataFrame(hist)
        fig1 = go.Figure()
        fig1.add_bar(x=df_hist["Mês"], y=df_hist["Receita"], name="Receita", marker_color="#16a34a")
        fig1.add_bar(x=df_hist["Mês"], y=df_hist["Despesa"], name="Despesa", marker_color="#dc2626")
        fig1.update_layout(barmode="group", height=300, margin=dict(t=10, b=10, l=10, r=10),
                           legend=dict(orientation="h", y=-0.2))
        st.plotly_chart(fig1, use_container_width=True)

    # ── Pizza categorias despesa ──
    with col2:
        st.subheader("Despesas por categoria")
        if not desp_mes.empty and "categoria" in desp_mes.columns:
            grp = desp_mes.groupby("categoria")["valor"].sum().reset_index()
            grp.columns = ["Categoria", "Valor"]
            fig2 = px.pie(grp, values="Valor", names="Categoria", height=300,
                          color_discrete_sequence=px.colors.qualitative.Set2)
            fig2.update_layout(margin=dict(t=10, b=10, l=10, r=10))
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Sem dados para o período.")

    # ── Pizza pagamento ──
    with col3:
        st.subheader("Por pagamento")
        if not desp_mes.empty and "pagamento" in desp_mes.columns:
            grp2 = desp_mes.groupby("pagamento")["valor"].sum().reset_index()
            grp2.columns = ["Pagamento", "Valor"]
            fig3 = px.pie(grp2, values="Valor", names="Pagamento", height=300,
                          color_discrete_sequence=px.colors.qualitative.Pastel)
            fig3.update_layout(margin=dict(t=10, b=10, l=10, r=10))
            st.plotly_chart(fig3, use_container_width=True)
        else:
            st.info("Sem dados para o período.")

# ══════════════════════════════════════════════════════════════════════════════
# LANÇAR DESPESA
# ══════════════════════════════════════════════════════════════════════════════
with tab_lanc:
    st.subheader("Nova Despesa")
    with st.form("form_despesa", clear_on_submit=True):
        c1, c2 = st.columns([3, 1])
        desc  = c1.text_input("Descrição *")
        valor = c2.text_input("Valor (R$) *", placeholder="0,00")

        c3, c4 = st.columns(2)
        data_d = c3.date_input("Data *", value=date.today())
        local  = c4.text_input("Local / Estabelecimento")

        c5, c6 = st.columns(2)
        cat = c5.selectbox("Categoria", [""] + CAT_DESP)
        pag = c6.selectbox("Modo de pagamento *", [""] + PAGAMENTOS)

        cartao = None; n_parc = 1; dia_venc = 10
        if pag == "Cartão de crédito":
            st.markdown("##### 💳 Cartão de Crédito")
            cc1, cc2, cc3 = st.columns(3)
            cartao   = cc1.selectbox("Cartão", CARTOES)
            n_parc   = cc2.selectbox("Parcelas", PARCELAS_OPT)
            dia_venc = cc3.selectbox("Dia vencimento fatura", DIAS_VENC, index=4)

        obs = st.text_input("Observação (opcional)")
        submitted = st.form_submit_button("✔ Salvar despesa", type="primary", use_container_width=True)

    if submitted:
        erros = []
        if not desc.strip(): erros.append("Preencha a descrição.")
        try:
            v = float(valor.replace(",", "."))
            assert v > 0
        except Exception:
            erros.append("Valor inválido.")
            v = 0
        if not pag: erros.append("Selecione o modo de pagamento.")
        if erros:
            for e in erros: st.error(e)
        else:
            salvar_despesa(desc.strip(), v, data_d.strftime("%Y-%m-%d"),
                           local.strip(), pag, cat, cartao, n_parc, dia_venc, obs.strip())
            st.success("Despesa lançada com sucesso!")

# ══════════════════════════════════════════════════════════════════════════════
# LANÇAR RECEITA
# ══════════════════════════════════════════════════════════════════════════════
with tab_rec:
    st.subheader("Nova Receita")
    with st.form("form_receita", clear_on_submit=True):
        r1, r2 = st.columns([3, 1])
        rdesc  = r1.text_input("Descrição *")
        rvalor = r2.text_input("Valor (R$) *", placeholder="0,00")

        r3, r4 = st.columns(2)
        rdata = r3.date_input("Data *", value=date.today())
        rcat  = r4.selectbox("Categoria", [""] + CAT_REC)
        robs  = st.text_input("Observação (opcional)")

        rsubmit = st.form_submit_button("✔ Salvar receita", type="primary", use_container_width=True)

    if rsubmit:
        erros = []
        if not rdesc.strip(): erros.append("Preencha a descrição.")
        try:
            rv = float(rvalor.replace(",", "."))
            assert rv > 0
        except Exception:
            erros.append("Valor inválido.")
            rv = 0
        if erros:
            for e in erros: st.error(e)
        else:
            salvar_receita(rdesc.strip(), rv, rdata.strftime("%Y-%m-%d"), rcat, robs.strip())
            st.success("Receita lançada com sucesso!")

# ══════════════════════════════════════════════════════════════════════════════
# LISTA DE DESPESAS
# ══════════════════════════════════════════════════════════════════════════════
with tab_lista:
    st.subheader("Despesas")
    f1, f2, f3 = st.columns(3)
    fmes  = f1.text_input("Mês (AAAA-MM)", value=mes_atual(), key="fmes_lista")
    fpag  = f2.selectbox("Pagamento", ["Todos"] + PAGAMENTOS, key="fpag_lista")
    fcat  = f3.selectbox("Categoria", ["Todas"] + CAT_DESP,  key="fcat_lista")

    df_d = carregar_despesas()
    if df_d.empty:
        st.info("Nenhuma despesa cadastrada.")
    else:
        mask = df_d["data"].astype(str).str.startswith(fmes)
        if fpag != "Todos": mask &= df_d["pagamento"] == fpag
        if fcat != "Todas": mask &= df_d["categoria"] == fcat
        df_filtrado = df_d[mask].copy()

        total = float(df_filtrado["valor"].sum()) if not df_filtrado.empty else 0.0
        cc_v  = float(df_filtrado[df_filtrado["pagamento"] == "Cartão de crédito"]["valor"].sum()) if not df_filtrado.empty else 0.0
        c1, c2, c3 = st.columns(3)
        with c1: st.markdown(card_html("Total", fmt_moeda(total), "blue"), unsafe_allow_html=True)
        with c2: st.markdown(card_html("Crédito", fmt_moeda(cc_v), "blue"), unsafe_allow_html=True)
        with c3: st.markdown(card_html("Outros", fmt_moeda(total - cc_v), "green"), unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        if not df_filtrado.empty:
            df_show = df_filtrado[["id", "descricao", "valor", "data", "local",
                                    "pagamento", "categoria", "n_parcelas", "observacao"]].copy()
            df_show["valor"] = df_show["valor"].apply(fmt_moeda)
            df_show.columns = ["ID", "Descrição", "Valor", "Data", "Local",
                                "Pagamento", "Categoria", "Parcelas", "Obs"]
            st.dataframe(df_show, use_container_width=True, hide_index=True)

            st.markdown("#### Excluir despesa")
            id_excluir = st.number_input("ID da despesa para excluir", min_value=1, step=1, key="id_excluir_d")
            if st.button("🗑 Excluir despesa", type="secondary", key="btn_excluir_d"):
                excluir_despesa(int(id_excluir))
                st.success(f"Despesa #{id_excluir} excluída!")
                st.rerun()
        else:
            st.info("Nenhuma despesa no período selecionado.")

# ══════════════════════════════════════════════════════════════════════════════
# CARTÃO DE CRÉDITO
# ══════════════════════════════════════════════════════════════════════════════
with tab_cc:
    st.subheader("Cartão de Crédito — Parcelas")
    fc1, fc2 = st.columns(2)
    fc_cartao = fc1.selectbox("Cartão", ["Todos"] + CARTOES, key="fc_cartao")
    fc_status = fc2.selectbox("Status", ["Todos", "Pendente", "Vencido", "Pago"], key="fc_status")

    df_p = carregar_parcelas()
    df_d = carregar_despesas()

    if df_p.empty:
        st.info("Nenhuma parcela cadastrada.")
    else:
        hoje = hoje_str()
        df_p2 = df_p.copy()
        # Adicionar nome e cartão via join
        if not df_d.empty:
            df_p2 = df_p2.merge(
                df_d[["id", "descricao", "cartao"]].rename(columns={"id": "despesa_id"}),
                on="despesa_id", how="left")

        # Filtros
        if fc_cartao != "Todos" and "cartao" in df_p2.columns:
            df_p2 = df_p2[df_p2["cartao"] == fc_cartao]
        if fc_status != "Todos":
            if fc_status == "Vencido":
                df_p2 = df_p2[(df_p2["status"] == "pendente") & (df_p2["vencimento"].astype(str) < hoje)]
            elif fc_status == "Pendente":
                df_p2 = df_p2[(df_p2["status"] == "pendente") & (df_p2["vencimento"].astype(str) >= hoje)]
            else:
                df_p2 = df_p2[df_p2["status"] == fc_status.lower()]

        # Cards resumo
        df_all = df_p.copy()
        pend = float(df_all[df_all["status"] == "pendente"]["valor"].sum())
        venc = int(((df_all["status"] == "pendente") & (df_all["vencimento"].astype(str) < hoje)).sum())
        pagas = int((df_all["status"] == "pago").sum())
        cc1, cc2, cc3 = st.columns(3)
        with cc1: st.markdown(card_html("A pagar", fmt_moeda(pend), "orange"), unsafe_allow_html=True)
        with cc2: st.markdown(card_html("Vencidas", f"{venc} parcela(s)", "red"), unsafe_allow_html=True)
        with cc3: st.markdown(card_html("Pagas", f"{pagas} parcela(s)", "green"), unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        if not df_p2.empty:
            def status_label(row):
                if row["status"] == "pago": return "✅ Pago"
                if str(row["vencimento"]) < hoje: return "❌ Vencido"
                return "⏳ Pendente"
            df_p2["Status"] = df_p2.apply(status_label, axis=1)

            cols_show = ["id", "descricao", "cartao", "numero", "total", "valor", "vencimento", "Status"]
            cols_show = [c for c in cols_show if c in df_p2.columns]
            df_show = df_p2[cols_show].copy()
            df_show["valor"] = df_show["valor"].apply(fmt_moeda)
            df_show.rename(columns={"id": "ID", "descricao": "Despesa", "cartao": "Cartão",
                                     "numero": "Parc.", "total": "Total", "valor": "Valor",
                                     "vencimento": "Vencimento"}, inplace=True)
            st.dataframe(df_show, use_container_width=True, hide_index=True)

            st.markdown("#### Ações")
            ba1, ba2, ba3 = st.columns(3)
            pid_acao = ba1.number_input("ID da parcela", min_value=1, step=1, key="pid_acao")
            if ba2.button("✔ Dar baixa", type="primary"):
                atualizar_parcela(int(pid_acao), "pago")
                st.success(f"Parcela #{pid_acao} marcada como paga!")
                st.rerun()
            if ba3.button("↩ Estornar"):
                atualizar_parcela(int(pid_acao), "pendente")
                st.warning(f"Parcela #{pid_acao} estornada para pendente.")
                st.rerun()

            st.markdown("---")
            mes_fat = st.text_input("Mês para baixar fatura (AAAA-MM)", value=mes_atual(), key="mes_fatura")
            if st.button("💳 Baixar fatura completa do mês"):
                n = baixar_fatura_mes(mes_fat, fc_cartao if fc_cartao != "Todos" else None)
                st.success(f"{n} parcela(s) baixadas para {mes_fat}!")
                st.rerun()
        else:
            st.info("Nenhuma parcela para os filtros selecionados.")

# ══════════════════════════════════════════════════════════════════════════════
# CONTA CORRENTE
# ══════════════════════════════════════════════════════════════════════════════
with tab_cc_rec:
    st.subheader("Conta Corrente")
    mes_cc = st.text_input("Mês (AAAA-MM)", value=mes_atual(), key="mes_cc_rec")

    df_d = carregar_despesas()
    df_r = carregar_receitas()

    desp_cc = df_d[df_d["data"].astype(str).str.startswith(mes_cc)] if not df_d.empty else pd.DataFrame()
    rec_cc  = df_r[df_r["data"].astype(str).str.startswith(mes_cc)]  if not df_r.empty else pd.DataFrame()

    total_rec_cc  = float(rec_cc["valor"].sum())  if not rec_cc.empty  else 0.0
    total_desp_cc = float(desp_cc["valor"].sum()) if not desp_cc.empty else 0.0
    saldo_cc      = total_rec_cc - total_desp_cc
    saldo_cor_cc  = "green" if saldo_cc >= 0 else "red"

    m1, m2, m3 = st.columns(3)
    with m1: st.markdown(card_html("Total receitas", fmt_moeda(total_rec_cc), "green"), unsafe_allow_html=True)
    with m2: st.markdown(card_html("Total despesas", fmt_moeda(total_desp_cc), "red"), unsafe_allow_html=True)
    with m3: st.markdown(card_html("Saldo acumulado", fmt_moeda(saldo_cc), saldo_cor_cc), unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    # Montar extrato
    movs = []
    if not rec_cc.empty:
        for _, row in rec_cc.iterrows():
            movs.append({
                "Data": row["data"], "Descrição": row["descricao"],
                "Tipo": "Receita", "Categoria": row.get("categoria", ""),
                "Valor": float(row["valor"]), "ID": row["id"], "_tipo": "rec"
            })
    if not desp_cc.empty:
        for _, row in desp_cc.iterrows():
            movs.append({
                "Data": row["data"], "Descrição": row["descricao"],
                "Tipo": "Despesa", "Categoria": row.get("categoria", ""),
                "Valor": -float(row["valor"]), "ID": row["id"], "_tipo": "dsp"
            })
    movs.sort(key=lambda x: x["Data"])

    saldo_ac = 0.0
    extrato = []
    for m in movs:
        saldo_ac += m["Valor"]
        extrato.append({
            "Data": m["Data"], "Descrição": m["Descrição"], "Tipo": m["Tipo"],
            "Categoria": m["Categoria"],
            "Valor": fmt_moeda(abs(m["Valor"])),
            "Saldo": fmt_moeda(saldo_ac),
        })

    if extrato:
        st.dataframe(pd.DataFrame(extrato), use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum movimento para o período selecionado.")

    # Excluir receita
    st.markdown("#### Excluir receita")
    rid_excluir = st.number_input("ID da receita para excluir", min_value=1, step=1, key="rid_excluir")
    if st.button("🗑 Excluir receita", type="secondary"):
        excluir_receita(int(rid_excluir))
        st.success(f"Receita #{rid_excluir} excluída!")
        st.rerun()
