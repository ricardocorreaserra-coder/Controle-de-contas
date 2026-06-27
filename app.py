"""
Controle de Contas - Versão Web (Streamlit + Google Sheets)
Uso: streamlit run app.py
"""

import html as _html
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
    page_icon=":moneybag:",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Estilos CSS Atualizados ───────────────────────────────────────────────────
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
        border-radius: 12px; padding: 1.25rem 1.5rem;
        text-align: center; 
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05), 0 2px 4px -1px rgba(0,0,0,0.03);
        transition: transform 0.2s, box-shadow 0.2s;
    }
    .card:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 15px -3px rgba(0,0,0,0.05), 0 4px 6px -2px rgba(0,0,0,0.03);
    }
    .card-label { font-size: 0.85rem; color: #64748b; margin-bottom: 6px; font-weight: 500; }
    .card-value { font-size: 1.5rem; font-weight: 700; }
    .green  { color: #16a34a; }
    .red    { color: #dc2626; }
    .blue   { color: #2563eb; }
    .orange { color: #d97706; }
    .stTabs [data-baseweb="tab"] { font-size: 0.95rem; }
    div[data-testid="stSuccess"] { border-radius: 8px; }
    div[data-testid="stWarning"] { border-radius: 8px; }
    /* Tela de login */
    .login-box {
        max-width: 360px; margin: 6rem auto; text-align: center;
        padding: 2rem; background: white; border-radius: 16px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 4px 24px rgba(0,0,0,0.07);
    }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# S-01 · AUTENTICAÇÃO POR SENHA
# ══════════════════════════════════════════════════════════════════════════════
def verificar_autenticacao():
    if "autenticado" not in st.session_state:
        st.session_state["autenticado"] = False

    if not st.session_state["autenticado"]:
        st.markdown("""
        <div class="login-box">
            <div style="font-size:2.5rem">💰</div>
            <h2 style="margin:0.5rem 0 0.25rem">Controle de Contas</h2>
            <p style="color:#64748b;margin-bottom:1.5rem">Digite a senha para acessar</p>
        </div>
        """, unsafe_allow_html=True)

        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            senha = st.text_input(
                "Senha",
                type="password",
                label_visibility="collapsed",
                placeholder="Digite a senha..."
            )
            if st.button("Entrar", use_container_width=True, type="primary"):
                senha_correta = st.secrets.get("APP_PASSWORD", "")
                if senha_correta and senha == senha_correta:
                    st.session_state["autenticado"] = True
                    st.rerun()
                elif not senha_correta:
                    st.error("APP_PASSWORD não configurada nos secrets.")
                else:
                    st.error("Senha incorreta.")
        st.stop()

verificar_autenticacao()

# ── Meses em português ────────────────────────────────────────────────────────
MESES_PT = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr",
    5: "Mai", 6: "Jun", 7: "Jul", 8: "Ago",
    9: "Set", 10: "Out", 11: "Nov", 12: "Dez"
}

def fmt_mes_pt(dt: date) -> str:
    return f"{MESES_PT[dt.month]}/{str(dt.year)[2:]}"

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

def converter_data_para_exibicao(dt_str):
    try:
        return datetime.strptime(str(dt_str), "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        try:
            return datetime.strptime(str(dt_str), "%Y/%m/%d").strftime("%d/%m/%Y")
        except Exception:
            return dt_str

# S-02 · card_html com sanitização via html.escape
def card_html(label, value, color_class):
    label_safe = _html.escape(str(label))
    value_safe = _html.escape(str(value))
    return f"""
    <div class="card">
        <div class="card-label">{label_safe}</div>
        <div class="card-value {color_class}">{value_safe}</div>
    </div>
    """

def seletor_mes_ano(key_prefix: str):
    """Renderiza seletores de ano e mês lado a lado de forma amigável."""
    hoje = date.today()
    anos = [hoje.year - i for i in range(5)]
    c1, c2 = st.columns(2)
    ano = c1.selectbox("Ano", anos, index=0, key=f"{key_prefix}_ano")
    mes = c2.selectbox("Mês", list(MESES_PT.keys()), 
                       format_func=lambda x: MESES_PT[x], 
                       index=hoje.month - 1, key=f"{key_prefix}_mes")
    return f"{ano}-{mes:02d}"

# ── Google Sheets ──────────────────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

@st.cache_resource(ttl=600)
def get_sheets_client():
    """Conecta ao Google Sheets via credenciais nos secrets."""
    creds_dict = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)

@st.cache_resource(ttl=600)
def get_workbook():
    client = get_sheets_client()
    return client.open(st.secrets["SHEET_NAME"])

def get_sheet(name: str):
    wb = get_workbook()
    try:
        ws = wb.worksheet(name)
        if name == "parcelas":
            headers = ws.row_values(1)
            if "descricao" not in headers or "cartao" not in headers:
                new_headers = ["id", "despesa_id", "numero", "total",
                               "valor", "vencimento", "status", "descricao", "cartao"]
                ws.update('A1:I1', [new_headers])
        return ws
    except gspread.WorksheetNotFound:
        ws = wb.add_worksheet(title=name, rows=1000, cols=20)
        headers = {
            "despesas": ["id", "descricao", "valor", "data", "local",
                         "pagamento", "categoria", "cartao", "n_parcelas",
                         "observacao", "criado_em"],
            "parcelas": ["id", "despesa_id", "numero", "total",
                         "valor", "vencimento", "status", "descricao", "cartao"],
            "receitas": ["id", "descricao", "valor", "data",
                         "categoria", "observacao", "criado_em"],
            "cartoes": ["id", "nome", "limite", "dia_fechamento", "dia_vencimento", "criado_em"]
        }
        if name in headers:
            ws.append_row(headers[name])
        if name == "cartoes":
            default_cards = [
                [1, "Nubank", 5000, 5, 12, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
                [2, "Itaú", 5000, 10, 17, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
                [3, "Bradesco", 5000, 15, 22, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
                [4, "Inter", 5000, 20, 27, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
                [5, "Santander", 5000, 25, 2, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
                [6, "Outro", 5000, 10, 17, datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
            ]
            ws.append_rows(default_cards)
        return ws

def sheet_to_df(ws) -> pd.DataFrame:
    data = ws.get_all_records()
    df = pd.DataFrame(data) if data else pd.DataFrame()
    name = ws.title
    expected_headers = {
        "despesas": ["id", "descricao", "valor", "data", "local",
                     "pagamento", "categoria", "cartao", "n_parcelas",
                     "observacao", "criado_em"],
        "parcelas": ["id", "despesa_id", "numero", "total",
                     "valor", "vencimento", "status", "descricao", "cartao"],
        "receitas": ["id", "descricao", "valor", "data",
                     "categoria", "observacao", "criado_em"],
        "cartoes": ["id", "nome", "limite", "dia_fechamento", "dia_vencimento", "criado_em"]
    }
    if name in expected_headers:
        for col in expected_headers[name]:
            if col not in df.columns:
                df[col] = ""
    return df

def next_id(ws) -> int:
    df = sheet_to_df(ws)
    if df.empty or "id" not in df.columns or df["id"].astype(str).str.strip().eq("").all():
        return 1
    ids = pd.to_numeric(df["id"], errors='coerce').fillna(0).astype(int)
    return int(ids.max()) + 1

# ── Lógica de dados ────────────────────────────────────────────────────────────
@st.cache_data(ttl=30)
def carregar_cartoes():
    ws = get_sheet("cartoes")
    df = sheet_to_df(ws)
    if df.empty:
        default_cards = [
            [1, "Nubank", 5000, 5, 12, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
            [2, "Itaú", 5000, 10, 17, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
            [3, "Bradesco", 5000, 15, 22, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
            [4, "Inter", 5000, 20, 27, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
            [5, "Santander", 5000, 25, 2, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
            [6, "Outro", 5000, 10, 17, datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
        ]
        ws.append_rows(default_cards)
        st.cache_data.clear()
        df = sheet_to_df(ws)
    return df

def obter_nomes_cartoes() -> list:
    try:
        df_c = carregar_cartoes()
        if not df_c.empty and "nome" in df_c.columns:
            return df_c["nome"].tolist()
    except Exception:
        pass
    return ["Nubank", "Itaú", "Bradesco", "Inter", "Santander", "Outro"]

def delete_rows_batch(ws, indices):
    """Deleta várias linhas do Google Sheets em uma única requisição em lote."""
    if not indices:
        return
    sorted_indices = sorted(indices, reverse=True)
    requests = []
    sheet_id = ws.id
    for idx in sorted_indices:
        row_num = idx + 1
        requests.append({
            "deleteDimension": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "ROWS",
                    "startIndex": row_num,
                    "endIndex": row_num + 1
                }
            }
        })
    body = {"requests": requests}
    ws.spreadsheet.batch_update(body)

def calcular_vencimento_parcela(data_compra: date, dia_fechamento: int, dia_vencimento: int, num_parcela: int) -> date:
    """Calcula o vencimento da parcela baseado no dia de fechamento e vencimento do cartão."""
    try:
        fechamento_mes_compra = date(data_compra.year, data_compra.month, dia_fechamento)
    except ValueError:
        last_day = calendar.monthrange(data_compra.year, data_compra.month)[1]
        fechamento_mes_compra = date(data_compra.year, data_compra.month, last_day)

    meses_adicionais = 1 if data_compra > fechamento_mes_compra else 0
    total_meses = meses_adicionais + (num_parcela - 1)

    if dia_vencimento < dia_fechamento:
        total_meses += 1

    venc = add_months(data_compra, total_meses)
    max_day = calendar.monthrange(venc.year, venc.month)[1]
    dia_ajustado = min(dia_vencimento, max_day)
    return date(venc.year, venc.month, dia_ajustado)

# ── Funções de persistência com tratamento de erro (S-06 antecipado) ───────────
def salvar_despesa(desc, valor, data, local, pag, cat, cartao, n_parc, dia_venc, obs):
    ws_d = get_sheet("despesas")
    ws_p = get_sheet("parcelas")
    did  = next_id(ws_d)
    ws_d.append_row([did, desc, valor, data, local, pag, cat,
                     cartao or "", n_parc, obs,
                     datetime.now().strftime("%Y-%m-%d %H:%M:%S")])

    if pag == "Cartão de crédito":
        df_c = carregar_cartoes()
        card_info = df_c[df_c["nome"] == cartao] if not df_c.empty else pd.DataFrame()
        if not card_info.empty:
            df_fechamento = int(card_info.iloc[0]["dia_fechamento"])
            df_vencimento = int(card_info.iloc[0]["dia_vencimento"])
        else:
            df_fechamento = 10
            df_vencimento = dia_venc

        pid   = next_id(ws_p)
        base  = datetime.strptime(data, "%Y-%m-%d").date()
        vp    = round(valor / n_parc, 2)
        rows  = []
        for i in range(n_parc):
            venc = calcular_vencimento_parcela(base, df_fechamento, df_vencimento, i + 1)
            rows.append([pid + i, did, i + 1, n_parc, vp,
                         venc.strftime("%Y-%m-%d"), "pendente", desc, cartao])
        ws_p.append_rows(rows)
    st.cache_data.clear()

def salvar_parcela_manual(cartao, desc, valor_parcela, num_inicial, num_total, vencimento_inicial, obs):
    ws_p = get_sheet("parcelas")
    pid = next_id(ws_p)

    df_c = carregar_cartoes()
    card_info = df_c[df_c["nome"] == cartao] if not df_c.empty else pd.DataFrame()
    if not card_info.empty:
        df_vencimento = int(card_info.iloc[0]["dia_vencimento"])
    else:
        df_vencimento = 17

    base_date = datetime.strptime(vencimento_inicial, "%Y-%m-%d").date()
    rows = []
    num_a_gerar = num_total - num_inicial + 1
    for i in range(num_a_gerar):
        num_parcela = num_inicial + i
        venc = add_months(base_date, i)
        max_day = calendar.monthrange(venc.year, venc.month)[1]
        dia_ajustado = min(df_vencimento, max_day)
        venc = venc.replace(day=dia_ajustado)
        rows.append([
            pid + i,
            -1,
            num_parcela,
            num_total,
            valor_parcela,
            venc.strftime("%Y-%m-%d"),
            "pendente",
            desc,
            cartao
        ])
    ws_p.append_rows(rows)
    st.cache_data.clear()

def salvar_cartao(nome, limite, dia_fechamento, dia_vencimento):
    ws = get_sheet("cartoes")
    cid = next_id(ws)
    ws.append_row([cid, nome, limite, dia_fechamento, dia_vencimento,
                   datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
    st.cache_data.clear()

def excluir_cartao(cid: int):
    ws = get_sheet("cartoes")
    df = sheet_to_df(ws)
    if not df.empty:
        idx_list = df[df["id"].astype(str) == str(cid)].index.tolist()
        delete_rows_batch(ws, idx_list)
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
    df_p = sheet_to_df(ws_p)
    if not df_p.empty and "despesa_id" in df_p.columns:
        ids_excluir = df_p[df_p["despesa_id"].astype(str) == str(did)].index.tolist()
        delete_rows_batch(ws_p, ids_excluir)
    df_d = sheet_to_df(ws_d)
    if not df_d.empty:
        idx_list = df_d[df_d["id"].astype(str) == str(did)].index.tolist()
        delete_rows_batch(ws_d, idx_list)
    st.cache_data.clear()

def excluir_receita(rid: int):
    ws = get_sheet("receitas")
    df = sheet_to_df(ws)
    if not df.empty:
        idx_list = df[df["id"].astype(str) == str(rid)].index.tolist()
        delete_rows_batch(ws, idx_list)
    st.cache_data.clear()

def atualizar_parcela(pid: int, status: str):
    ws = get_sheet("parcelas")
    df = sheet_to_df(ws)
    idx_list = df[df["id"].astype(str) == str(pid)].index.tolist()
    for idx in idx_list:
        ws.update_cell(idx + 2, df.columns.get_loc("status") + 1, status)
    st.cache_data.clear()

def baixar_fatura_mes(mes: str, cartao_filtro: str = None):
    """Marca todas as parcelas pendentes da fatura do mês como pagas em lote."""
    ws = get_sheet("parcelas")
    ws_d = get_sheet("despesas")
    df_p = sheet_to_df(ws)
    df_d = sheet_to_df(ws_d)
    if df_p.empty:
        return 0

    df_p_full = df_p.copy()
    if not df_d.empty:
        df_d_sub = df_d[["id", "cartao"]].rename(columns={"id": "despesa_id", "cartao": "cartao_dep"})
        df_p_full = df_p_full.merge(df_d_sub, on="despesa_id", how="left")
        df_p_full["cartao"] = df_p_full.apply(
            lambda r: r["cartao_dep"] if pd.notna(r.get("cartao_dep")) and r["cartao_dep"] != "" else r.get("cartao", ""),
            axis=1
        )

    mask = (df_p_full["vencimento"].astype(str).str.startswith(mes)) & \
           (df_p_full["status"] == "pendente")

    if cartao_filtro and cartao_filtro != "Todos":
        mask = mask & (df_p_full["cartao"] == cartao_filtro)

    idxs = df_p_full[mask].index.tolist()
    if not idxs:
        return 0

    col_idx = df_p.columns.get_loc("status") + 1
    range_data = []
    for idx in idxs:
        row_num = idx + 2
        range_data.append({
            'range': f'{gspread.utils.rowcol_to_a1(row_num, col_idx)}',
            'values': [['pago']]
        })
    ws.batch_update(range_data)
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
    st.markdown("##### Filtro de Período")
    mes_dash = seletor_mes_ano("dash")

    df_d = carregar_despesas()
    df_r = carregar_receitas()

    if not df_d.empty and "valor" in df_d.columns:
        df_d["valor"] = pd.to_numeric(df_d["valor"], errors='coerce').fillna(0.0)
    if not df_r.empty and "valor" in df_r.columns:
        df_r["valor"] = pd.to_numeric(df_r["valor"], errors='coerce').fillna(0.0)

    desp_mes = df_d[df_d["data"].astype(str).str.startswith(mes_dash)] if not df_d.empty else pd.DataFrame()
    rec_mes  = df_r[df_r["data"].astype(str).str.startswith(mes_dash)]  if not df_r.empty else pd.DataFrame()

    total_rec  = float(rec_mes["valor"].sum())  if not rec_mes.empty  else 0.0
    total_desp = float(desp_mes["valor"].sum()) if not desp_mes.empty else 0.0
    saldo      = total_rec - total_desp
    saldo_cor  = "green" if saldo >= 0 else "red"

    c1, c2, c3 = st.columns(3)
    with c1: st.markdown(card_html("Receitas do mês", fmt_moeda(total_rec), "green"),  unsafe_allow_html=True)
    with c2: st.markdown(card_html("Despesas do mês", fmt_moeda(total_desp), "red"),    unsafe_allow_html=True)
    with c3: st.markdown(card_html("Saldo do mês", fmt_moeda(saldo), saldo_cor),        unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader("Histórico 6 meses")
        hist = []
        for i in range(5, -1, -1):
            d  = date.today()
            mm = add_months(d, -i).strftime("%Y-%m")
            lbl = fmt_mes_pt(add_months(d, -i))
            r_val = float(df_r[df_r["data"].astype(str).str.startswith(mm)]["valor"].sum()) if not df_r.empty else 0.0
            e_val = float(df_d[df_d["data"].astype(str).str.startswith(mm)]["valor"].sum()) if not df_d.empty else 0.0
            hist.append({"Mês": lbl, "Receita": r_val, "Despesa": e_val})
        df_hist = pd.DataFrame(hist)
        fig1 = go.Figure()
        fig1.add_bar(x=df_hist["Mês"], y=df_hist["Receita"], name="Receita", marker_color="#16a34a",
                     hovertemplate='Receita: R$ %{y:,.2f}<extra></extra>')
        fig1.add_bar(x=df_hist["Mês"], y=df_hist["Despesa"], name="Despesa", marker_color="#dc2626",
                     hovertemplate='Despesa: R$ %{y:,.2f}<extra></extra>')
        fig1.update_layout(barmode="group", height=300, template="plotly_white", separators=',.',
                           margin=dict(t=10, b=10, l=10, r=10),
                           legend=dict(orientation="h", y=-0.2))
        st.plotly_chart(fig1, use_container_width=True)

    with col2:
        st.subheader("Despesas por categoria")
        if not desp_mes.empty and "categoria" in desp_mes.columns:
            grp = desp_mes.groupby("categoria")["valor"].sum().reset_index()
            grp.columns = ["Categoria", "Valor"]
            fig2 = px.pie(grp, values="Valor", names="Categoria", hole=0.4, height=300,
                          color_discrete_sequence=px.colors.qualitative.Set2)
            fig2.update_traces(textinfo='percent+label', hovertemplate='<b>%{label}</b><br>Valor: R$ %{value:,.2f}<extra></extra>')
            fig2.update_layout(template="plotly_white", separators=',.', margin=dict(t=10, b=10, l=10, r=10))
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Sem dados para o período.")

    with col3:
        st.subheader("Por pagamento")
        if not desp_mes.empty and "pagamento" in desp_mes.columns:
            grp2 = desp_mes.groupby("pagamento")["valor"].sum().reset_index()
            grp2.columns = ["Pagamento", "Valor"]
            fig3 = px.pie(grp2, values="Valor", names="Pagamento", hole=0.4, height=300,
                          color_discrete_sequence=px.colors.qualitative.Pastel)
            fig3.update_traces(textinfo='percent+label', hovertemplate='<b>%{label}</b><br>Valor: R$ %{value:,.2f}<extra></extra>')
            fig3.update_layout(template="plotly_white", separators=',.', margin=dict(t=10, b=10, l=10, r=10))
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
        data_d = c3.date_input("Data *", value=date.today(), format="DD/MM/YYYY")
        local  = c4.text_input("Local / Estabelecimento")

        c5, c6 = st.columns(2)
        cat = c5.selectbox("Categoria", [""] + CAT_DESP)
        pag = c6.selectbox("Modo de pagamento *", [""] + PAGAMENTOS)

        cartao = None; n_parc = 1; dia_venc = 10
        if pag == "Cartão de crédito":
            st.markdown("##### 💳 Cartão de Crédito")
            cc1, cc2 = st.columns(2)
            cartao   = cc1.selectbox("Cartão", obter_nomes_cartoes())
            n_parc   = cc2.selectbox("Parcelas", PARCELAS_OPT)

        obs = st.text_input("Observação (opcional)")
        submitted = st.form_submit_button("✔ Salvar despesa", type="primary", use_container_width=True)

    if submitted:
        erros = []
        if not desc.strip():
            erros.append("Preencha a descrição.")
        # S-03 · Validação de limites de valor
        try:
            v = float(valor.replace(".", "").replace(",", "."))
            if not (0 < v <= 1_000_000):
                erros.append("Valor deve estar entre R$ 0,01 e R$ 1.000.000,00.")
        except Exception:
            erros.append("Valor inválido.")
            v = 0
        if not pag:
            erros.append("Selecione o modo de pagamento.")

        if erros:
            for e in erros:
                st.error(e)
        else:
            # S-05 · Debounce para evitar duplo clique
            if st.session_state.get("salvando_despesa"):
                st.warning("Aguarde, salvando...")
            else:
                st.session_state["salvando_despesa"] = True
                try:
                    salvar_despesa(desc.strip(), v, data_d.strftime("%Y-%m-%d"),
                                   local.strip(), pag, cat, cartao, n_parc, dia_venc, obs.strip())
                    st.success("✅ Despesa lançada com sucesso!")
                except Exception as e:
                    st.error(f"Erro ao salvar despesa: {e}")
                finally:
                    st.session_state["salvando_despesa"] = False

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
        rdata = r3.date_input("Data *", value=date.today(), format="DD/MM/YYYY")
        rcat  = r4.selectbox("Categoria", [""] + CAT_REC)
        robs  = st.text_input("Observação (opcional)")

        rsubmit = st.form_submit_button("✔ Salvar receita", type="primary", use_container_width=True)

    if rsubmit:
        erros = []
        if not rdesc.strip():
            erros.append("Preencha a descrição.")
        # S-03 · Validação de limites de valor
        try:
            rv = float(rvalor.replace(".", "").replace(",", "."))
            if not (0 < rv <= 1_000_000):
                erros.append("Valor deve estar entre R$ 0,01 e R$ 1.000.000,00.")
        except Exception:
            erros.append("Valor inválido.")
            rv = 0

        if erros:
            for e in erros:
                st.error(e)
        else:
            # S-05 · Debounce para evitar duplo clique
            if st.session_state.get("salvando_receita"):
                st.warning("Aguarde, salvando...")
            else:
                st.session_state["salvando_receita"] = True
                try:
                    salvar_receita(rdesc.strip(), rv, rdata.strftime("%Y-%m-%d"), rcat, robs.strip())
                    st.success("✅ Receita lançada com sucesso!")
                except Exception as e:
                    st.error(f"Erro ao salvar receita: {e}")
                finally:
                    st.session_state["salvando_receita"] = False

# ══════════════════════════════════════════════════════════════════════════════
# LISTA DE DESPESAS
# ══════════════════════════════════════════════════════════════════════════════
with tab_lista:
    st.subheader("Despesas")
    st.markdown("##### Filtros de visualização")
    fmes = seletor_mes_ano("lista")

    f1, f2 = st.columns(2)
    fpag  = f1.selectbox("Pagamento", ["Todos"] + PAGAMENTOS, key="fpag_lista")
    fcat  = f2.selectbox("Categoria", ["Todas"] + CAT_DESP,  key="fcat_lista")

    df_d = carregar_despesas()
    if df_d.empty:
        st.info("Nenhuma despesa cadastrada.")
    else:
        df_d["valor"] = pd.to_numeric(df_d["valor"], errors='coerce').fillna(0.0)
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
            df_show["data"] = df_show["data"].apply(converter_data_para_exibicao)
            df_show.columns = ["ID", "Descrição", "Valor", "Data", "Local",
                                "Pagamento", "Categoria", "Parcelas", "Obs"]

            event_d = st.dataframe(
                df_show,
                use_container_width=True,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row"
            )

            st.markdown("#### Ações")
            selected_rows_d = event_d.selection.rows
            if selected_rows_d:
                idx_sel = selected_rows_d[0]
                id_excluir = int(df_filtrado.iloc[idx_sel]["id"])
                desc_excluir = df_filtrado.iloc[idx_sel]["descricao"]
                val_excluir = fmt_moeda(df_filtrado.iloc[idx_sel]["valor"])
                st.warning(f"⚠️ Despesa selecionada: **#{id_excluir} - {desc_excluir} ({val_excluir})**")
                if st.button("🗑 Excluir despesa selecionada", type="primary", use_container_width=True):
                    try:
                        excluir_despesa(id_excluir)
                        st.success(f"Despesa #{id_excluir} excluída com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao excluir: {e}")
            else:
                st.info("💡 Clique em uma linha na tabela acima para liberar as ações de exclusão.")
        else:
            st.info("Nenhuma despesa no período selecionado.")

# ══════════════════════════════════════════════════════════════════════════════
# CARTÃO DE CRÉDITO
# ══════════════════════════════════════════════════════════════════════════════
with tab_cc:
    sub_cc_list, sub_cc_faturas, sub_cc_lanc, sub_cc_config = st.tabs([
        "📊 Parcelas",
        "📅 Faturas Futuras",
        "➕ Lançar Histórico",
        "⚙️ Cartões & Configurações"
    ])

    df_p = carregar_parcelas()
    df_d = carregar_despesas()
    hoje = hoje_str()

    df_p2 = pd.DataFrame()
    if not df_p.empty:
        df_p_converted = df_p.copy()
        df_p_converted["valor"] = pd.to_numeric(df_p_converted["valor"], errors='coerce').fillna(0.0)

        if not df_d.empty:
            df_d_sub = df_d[["id", "descricao", "cartao"]].rename(
                columns={"id": "despesa_id", "descricao": "desc_dep", "cartao": "cartao_dep"}
            )
            df_p2 = df_p_converted.merge(df_d_sub, on="despesa_id", how="left")
            df_p2["descricao"] = df_p2.apply(
                lambda r: r["desc_dep"] if pd.notna(r.get("desc_dep")) and r["desc_dep"] != "" else r.get("descricao", ""),
                axis=1
            )
            df_p2["cartao"] = df_p2.apply(
                lambda r: r["cartao_dep"] if pd.notna(r.get("cartao_dep")) and r["cartao_dep"] != "" else r.get("cartao", ""),
                axis=1
            )
        else:
            df_p2 = df_p_converted.copy()
            df_p2["descricao"] = df_p2.get("descricao", "")
            df_p2["cartao"] = df_p2.get("cartao", "")

        df_p2["descricao"] = df_p2["descricao"].fillna("").astype(str)
        df_p2["cartao"] = df_p2["cartao"].fillna("").astype(str)

    with sub_cc_list:
        st.subheader("Cartão de Crédito — Parcelas")

        if df_p.empty or df_p2.empty:
            st.info("Nenhuma parcela cadastrada.")
        else:
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

            pend = float(df_p2[df_p2["status"] == "pendente"]["valor"].sum())
            venc = int(((df_p2["status"] == "pendente") & (df_p2["vencimento"].astype(str) < hoje)).sum())
            pagas = int((df_p2["status"] == "pago").sum())

            cc1, cc2, cc3 = st.columns(3)
            with cc1: st.markdown(card_html("A pagar total", fmt_moeda(pend), "orange"), unsafe_allow_html=True)
            with cc2: st.markdown(card_html("Vencidas", f"{venc} parcela(s)", "red"), unsafe_allow_html=True)
            with cc3: st.markdown(card_html("Pagas", f"{pagas} parcela(s)", "green"), unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)

            if not df_filtrado.empty:
                def status_label(row):
                    if row["status"] == "pago": return "✅ Pago"
                    if str(row["vencimento"]) < hoje: return "❌ Vencido"
                    return "⏳ Pendente"
                df_filtrado["Status"] = df_filtrado.apply(status_label, axis=1)

                cols_show = ["id", "descricao", "cartao", "numero", "total", "valor", "vencimento", "Status"]
                cols_show = [c for c in cols_show if c in df_filtrado.columns]
                df_show = df_filtrado[cols_show].copy()
                df_show["valor"] = df_show["valor"].apply(fmt_moeda)
                df_show["vencimento"] = df_show["vencimento"].apply(converter_data_para_exibicao)
                df_show.rename(columns={"id": "ID", "descricao": "Despesa/Item", "cartao": "Cartão",
                                         "numero": "Parc.", "total": "Total", "valor": "Valor",
                                         "vencimento": "Vencimento"}, inplace=True)

                event_p = st.dataframe(
                    df_show,
                    use_container_width=True,
                    hide_index=True,
                    on_select="rerun",
                    selection_mode="single-row",
                    key="df_parcelas_list"
                )

                st.markdown("#### Ações da Parcela")
                selected_rows_p = event_p.selection.rows
                if selected_rows_p:
                    idx_sel = selected_rows_p[0]
                    pid_acao = int(df_filtrado.iloc[idx_sel]["id"])
                    desc_p = df_filtrado.iloc[idx_sel]["descricao"]
                    val_p = fmt_moeda(df_filtrado.iloc[idx_sel]["valor"])
                    status_p = df_filtrado.iloc[idx_sel]["status"]

                    st.info(f"📋 Parcela selecionada: **#{pid_acao} - {desc_p} ({val_p})** | Status: **{status_p.upper()}**")

                    ba2, ba3 = st.columns(2)
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
                else:
                    st.info("💡 Clique em uma parcela na tabela acima para liberar as ações de pagamento/estorno.")

                st.markdown("---")
                st.markdown("##### 💳 Baixar Fatura Completa do Mês")
                c_fat1, c_fat2 = st.columns([2, 1])
                with c_fat1:
                    mes_fat = seletor_mes_ano("fatura_lote")
                with c_fat2:
                    st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                    btn_baixa_lote = st.button("💳 Baixar fatura completa do mês", type="secondary", use_container_width=True, key="btn_baixa_lote")

                if btn_baixa_lote:
                    try:
                        n = baixar_fatura_mes(mes_fat, fc_cartao if fc_cartao != "Todos" else None)
                        st.success(f"Sucesso! {n} parcela(s) baixadas para o mês {mes_fat}!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao baixar fatura: {e}")
            else:
                st.info("Nenhuma parcela para os filtros selecionados.")

    with sub_cc_faturas:
        st.subheader("Projeção de Faturas Futuras")

        if df_p.empty or df_p2.empty:
            st.info("Nenhuma parcela pendente para gerar projeção.")
        else:
            df_pend = df_p2[df_p2["status"] == "pendente"].copy()
            if df_pend.empty:
                st.success("🎉 Todas as faturas estão totalmente pagas! Sem parcelas pendentes.")
            else:
                df_pend["Mês Vencimento"] = df_pend["vencimento"].astype(str).str.slice(0, 7)
                df_fat_group = df_pend.groupby(["Mês Vencimento", "cartao"])["valor"].sum().reset_index()
                df_pivot = df_fat_group.pivot(index="Mês Vencimento", columns="cartao", values="valor").fillna(0.0)

                st.markdown("##### Valores projetados por Fatura (R$)")
                df_pivot_fmt = df_pivot.copy()
                for col in df_pivot_fmt.columns:
                    df_pivot_fmt[col] = df_pivot_fmt[col].apply(fmt_moeda)
                st.dataframe(df_pivot_fmt, use_container_width=True)

                st.markdown("<br>", unsafe_allow_html=True)
                fig_proj = px.bar(
                    df_fat_group,
                    x="Mês Vencimento",
                    y="valor",
                    color="cartao",
                    labels={"valor": "Total da Fatura (R$)", "Mês Vencimento": "Mês da Fatura", "cartao": "Cartão"},
                    title="Distribuição Mensal das Faturas Futuras",
                    template="plotly_white",
                    color_discrete_sequence=px.colors.qualitative.Set2
                )
                fig_proj.update_layout(barmode="stack", separators=',.')
                st.plotly_chart(fig_proj, use_container_width=True)

                st.markdown("---")
                st.markdown("##### 🔍 Detalhamento de Fatura Específica")
                col_d1, col_d2 = st.columns(2)
                lista_cartoes_det = ["Todos"] + list(df_fat_group["cartao"].unique())
                lista_meses_det = sorted(list(df_fat_group["Mês Vencimento"].unique()))
                sel_cartao_det = col_d1.selectbox("Selecione o Cartão", lista_cartoes_det, key="sel_cartao_det")
                sel_mes_det = col_d2.selectbox("Selecione o Mês da Fatura", lista_meses_det, key="sel_mes_det")

                df_detalhe = df_pend[df_pend["Mês Vencimento"] == sel_mes_det].copy()
                if sel_cartao_det != "Todos":
                    df_detalhe = df_detalhe[df_detalhe["cartao"] == sel_cartao_det]

                if df_detalhe.empty:
                    st.info("Nenhum lançamento pendente encontrado para este filtro.")
                else:
                    total_fatura_det = float(df_detalhe["valor"].sum())
                    st.markdown(f"**Total da fatura selecionada: {fmt_moeda(total_fatura_det)}**")
                    df_det_show = df_detalhe[["descricao", "cartao", "numero", "total", "valor", "vencimento"]].copy()
                    df_det_show["valor"] = df_det_show["valor"].apply(fmt_moeda)
                    df_det_show["vencimento"] = df_det_show["vencimento"].apply(converter_data_para_exibicao)
                    df_det_show.columns = ["Descrição/Item", "Cartão", "Parcela", "Total Parc.", "Valor", "Vencimento"]
                    st.dataframe(df_det_show, use_container_width=True, hide_index=True)

    with sub_cc_lanc:
        st.subheader("Lançar Parcelas Anteriores / Saldo Devedor")
        st.markdown(
            "Utilize este formulário para lançar compras parceladas que foram feitas em meses anteriores "
            "ao início do uso deste aplicativo e que ainda possuem parcelas a vencer no cartão de crédito."
        )

        with st.form("form_parcelas_manuais", clear_on_submit=True):
            col_m1, col_m2 = st.columns(2)
            card_m = col_m1.selectbox("Cartão de Crédito", obter_nomes_cartoes(), key="m_card")
            desc_m = col_m2.text_input("Descrição da Compra * (ex: Compra Geladeira)")

            col_m3, col_m4, col_m5 = st.columns(3)
            val_parc_m = col_m3.text_input("Valor da Parcela (R$) *", placeholder="0,00", key="m_val")
            parc_init_m = col_m4.selectbox("Próxima Parcela a vencer *", list(range(1, 49)), index=0, key="m_init")
            parc_total_m = col_m5.selectbox("Total de Parcelas da Compra *", list(range(1, 49)), index=11, key="m_total")

            col_m6 = st.columns(1)[0]
            venc_init_m = col_m6.date_input("Vencimento da próxima parcela a vencer *", value=date.today(), format="DD/MM/YYYY", key="m_date")

            obs_m = st.text_input("Observação (opcional)", key="m_obs")
            sub_manual = st.form_submit_button("✔ Salvar Parcelas Históricas", type="primary", use_container_width=True)

        if sub_manual:
            erros_m = []
            if not desc_m.strip():
                erros_m.append("Preencha a descrição.")
            if parc_init_m > parc_total_m:
                erros_m.append("A próxima parcela a vencer não pode ser maior que o total de parcelas.")
            # S-03 · Validação de limites de valor
            try:
                v_p = float(val_parc_m.replace(".", "").replace(",", "."))
                if not (0 < v_p <= 1_000_000):
                    erros_m.append("Valor da parcela deve estar entre R$ 0,01 e R$ 1.000.000,00.")
            except Exception:
                erros_m.append("Valor da parcela inválido.")
                v_p = 0

            if erros_m:
                for e in erros_m:
                    st.error(e)
            else:
                # S-05 · Debounce para evitar duplo clique
                if st.session_state.get("salvando_parcela"):
                    st.warning("Aguarde, salvando...")
                else:
                    st.session_state["salvando_parcela"] = True
                    try:
                        salvar_parcela_manual(card_m, desc_m.strip(), v_p, parc_init_m, parc_total_m,
                                              venc_init_m.strftime("%Y-%m-%d"), obs_m.strip())
                        st.success(f"Parcelas históricas do item '{desc_m}' cadastradas com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar parcelas: {e}")
                    finally:
                        st.session_state["salvando_parcela"] = False

    with sub_cc_config:
        st.subheader("Gerenciamento de Cartões")

        st.markdown("##### Cartões Cadastrados")
        df_c = carregar_cartoes()
        if df_c.empty:
            st.info("Nenhum cartão cadastrado no banco de dados.")
        else:
            df_c_show = df_c[["id", "nome", "limite", "dia_fechamento", "dia_vencimento"]].copy()
            df_c_show["limite"] = df_c_show["limite"].apply(fmt_moeda)
            df_c_show.columns = ["ID", "Nome do Cartão", "Limite de Crédito", "Dia do Fechamento", "Dia do Vencimento"]

            event_c = st.dataframe(
                df_c_show,
                use_container_width=True,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
                key="df_cartoes_config_list"
            )

            selected_rows_c = event_c.selection.rows
            if selected_rows_c:
                idx_sel = selected_rows_c[0]
                id_cartao = int(df_c.iloc[idx_sel]["id"])
                nome_cartao = df_c.iloc[idx_sel]["nome"]
                st.warning(f"⚠️ Cartão selecionado para exclusão: **#{id_cartao} - {nome_cartao}**")
                if st.button("🗑 Excluir cartão selecionado", type="primary", use_container_width=True, key="btn_del_card"):
                    try:
                        excluir_cartao(id_cartao)
                        st.success(f"Cartão '{nome_cartao}' excluído com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao excluir cartão: {e}")
            else:
                st.info("💡 Clique em um cartão na tabela acima para liberar as opções de exclusão.")

        st.markdown("---")
        st.markdown("##### Cadastrar Novo Cartão")
        with st.form("form_cadastro_cartao", clear_on_submit=True):
            col_nc1, col_nc2 = st.columns(2)
            nome_nc = col_nc1.text_input("Nome do Cartão * (ex: Nubank Platinum)")
            limite_nc = col_nc2.text_input("Limite de Crédito (R$) *", placeholder="0,00", key="nc_limit")

            col_nc3, col_nc4 = st.columns(2)
            fechamento_nc = col_nc3.selectbox("Dia do Fechamento da Fatura *", list(range(1, 32)), index=4, key="nc_fech")
            vencimento_nc = col_nc4.selectbox("Dia do Vencimento da Fatura *", list(range(1, 32)), index=11, key="nc_venc")

            submit_nc = st.form_submit_button("✔ Cadastrar Novo Cartão", type="primary", use_container_width=True)

        if submit_nc:
            erros_nc = []
            if not nome_nc.strip():
                erros_nc.append("Preencha o nome do cartão.")
            try:
                lim = float(limite_nc.replace(".", "").replace(",", "."))
                if lim < 0:
                    erros_nc.append("Limite não pode ser negativo.")
            except Exception:
                erros_nc.append("Limite de crédito inválido.")
                lim = 0

            if erros_nc:
                for e in erros_nc:
                    st.error(e)
            else:
                try:
                    salvar_cartao(nome_nc.strip(), lim, fechamento_nc, vencimento_nc)
                    st.success(f"Novo cartão '{nome_nc}' cadastrado com sucesso!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao cadastrar cartão: {e}")

# ══════════════════════════════════════════════════════════════════════════════
# CONTA CORRENTE
# ══════════════════════════════════════════════════════════════════════════════
with tab_cc_rec:
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
    with m1: st.markdown(card_html("Total receitas", fmt_moeda(total_rec_cc), "green"), unsafe_allow_html=True)
    with m2: st.markdown(card_html("Total despesas", fmt_moeda(total_desp_cc), "red"), unsafe_allow_html=True)
    with m3: st.markdown(card_html("Saldo acumulado", fmt_moeda(saldo_cc), saldo_cor_cc), unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

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
            "Data": converter_data_para_exibicao(m["Data"]), "Descrição": m["Descrição"], "Tipo": m["Tipo"],
            "Categoria": m["Categoria"],
            "Valor": fmt_moeda(abs(m["Valor"])),
            "Saldo": fmt_moeda(saldo_ac),
        })

    if extrato:
        df_extrato = pd.DataFrame(extrato)

        event_cc = st.dataframe(
            df_extrato,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row"
        )

        st.markdown("#### Ações do Lançamento")
        selected_rows_cc = event_cc.selection.rows
        if selected_rows_cc:
            idx_sel = selected_rows_cc[0]
            mov_sel = movs[idx_sel]
            id_sel = int(mov_sel["ID"])
            tipo_sel = mov_sel["_tipo"]
            desc_sel = mov_sel["Descrição"]
            val_sel = fmt_moeda(abs(mov_sel["Valor"]))

            if tipo_sel == "rec":
                st.warning(f"⚠️ Receita selecionada: **#{id_sel} - {desc_sel} ({val_sel})**")
                if st.button("🗑 Excluir receita selecionada", type="primary", use_container_width=True):
                    try:
                        excluir_receita(id_sel)
                        st.success(f"Receita #{id_sel} excluída!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao excluir: {e}")
            else:
                st.info(f"ℹ️ O lançamento selecionado é uma **Despesa** (#{id_sel}). Para excluí-la, utilize a aba **☰ Despesas**.")
        else:
            st.info("💡 Clique em um lançamento do extrato acima para opções de exclusão (disponível para Receitas).")
    else:
        st.info("Nenhum movimento para o período selecionado.")
