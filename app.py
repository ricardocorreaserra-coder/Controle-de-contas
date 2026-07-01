"""
Controle de Contas - Versão Web (Streamlit + Google Sheets)
Uso: streamlit run app.py
"""

import html as _html
import calendar
import io
import re
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, datetime
import gspread
from google.oauth2.service_account import Credentials

# ── Configuração da página ─────────────────────────────────────────────────────
st.set_page_config(
    page_title="Controle de Contas",
    page_icon=":moneybag:",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Estilos CSS ───────────────────────────────────────────────────────────────
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
    .login-box {
        max-width: 360px; margin: 6rem auto; text-align: center;
        padding: 2rem; background: white; border-radius: 16px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 4px 24px rgba(0,0,0,0.07);
    }
    .plan-banner {
        background: #eff6ff; border: 1px solid #bfdbfe; color: #1e3a8a;
        padding: 0.75rem 1rem; border-radius: 10px; margin-bottom: 1rem;
        font-size: 0.92rem;
    }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# S-01 · AUTENTICAÇÃO POR SENHA
# ══════════════════════════════════════════════════════════════════════════════
def verificar_autenticacao():
    if "autenticado" not in st.session_state:
        st.session_state["autenticado"] = False
    if "tentativas_login" not in st.session_state:
        st.session_state["tentativas_login"] = 0

    if not st.session_state["autenticado"]:
        st.markdown("""
        <div class="login-box">
            <div style="font-size:2.5rem">💰</div>
            <h2 style="margin:0.5rem 0 0.25rem">Controle de Contas</h2>
            <p style="color:#64748b;margin-bottom:1.5rem">Digite a senha para acessar</p>
        </div>
        """, unsafe_allow_html=True)

        # B-01 · Limite simples de tentativas para dificultar força bruta
        bloqueado = st.session_state["tentativas_login"] >= 5

        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if bloqueado:
                st.error("Muitas tentativas incorretas. Recarregue a página para tentar novamente.")
            else:
                senha = st.text_input(
                    "Senha", type="password",
                    label_visibility="collapsed",
                    placeholder="Digite a senha..."
                )
                if st.button("Entrar", use_container_width=True, type="primary"):
                    senha_correta = st.secrets.get("APP_PASSWORD", "")
                    if senha_correta and senha == senha_correta:
                        st.session_state["autenticado"] = True
                        st.session_state["tentativas_login"] = 0
                        st.rerun()
                    elif not senha_correta:
                        st.error("APP_PASSWORD não configurada nos secrets.")
                    else:
                        st.session_state["tentativas_login"] += 1
                        restantes = 5 - st.session_state["tentativas_login"]
                        st.error(f"Senha incorreta. Tentativas restantes: {max(restantes, 0)}.")
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

def fmt_mes_str_pt(mes_str: str) -> str:
    """Converte 'YYYY-MM' em 'Mmm/AA'."""
    try:
        ano, mes = mes_str.split("-")
        return f"{MESES_PT[int(mes)]}/{ano[2:]}"
    except Exception:
        return mes_str

# ── Constantes ─────────────────────────────────────────────────────────────────
PAGAMENTOS   = ["Cartão de crédito", "Débito", "Pix", "Vale alimentação"]
CAT_DESP     = ["Alimentação", "Transporte", "Saúde", "Moradia", "Lazer",
                 "Educação", "Vestuário", "Outros"]
CAT_REC      = ["Salário", "Freelance", "Investimentos", "Aluguel recebido", "Outros"]
PARCELAS_OPT = [1, 2, 3, 4, 5, 6, 10, 12, 18, 24]
DIA_VENCIMENTO_PADRAO = 10  # usado apenas se um cartão referenciado não for encontrado no cadastro

# ── Helpers ────────────────────────────────────────────────────────────────────
def fmt_moeda(v):
    try:
        return "R$ {:,.2f}".format(float(v)).replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"

# B-02 · Parser de valor robusto: aceita tanto "1.234,56" (BR) quanto "1234.56" (US)
def parse_valor(texto: str) -> float:
    if texto is None:
        raise ValueError("valor vazio")
    t = str(texto).strip()
    if not t:
        raise ValueError("valor vazio")
    t = re.sub(r"[^0-9.,-]", "", t)
    if "," in t and "." in t:
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
    elif "," in t:
        t = t.replace(".", "").replace(",", ".")
    return float(t)

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

def proximos_12_meses() -> list:
    """Retorna ['YYYY-MM', ...] para os 12 meses a partir do mês seguinte ao atual."""
    hoje = date.today()
    base = date(hoje.year, hoje.month, 1)
    return [add_months(base, i).strftime("%Y-%m") for i in range(1, 13)]

def mes_ativo_recorrencia(mes: str, data_inicio: date, data_fim) -> bool:
    """Verifica se um lançamento recorrente está ativo em determinado mês (YYYY-MM)."""
    if mes < data_inicio.strftime("%Y-%m"):
        return False
    fim_str = str(data_fim).strip() if data_fim not in (None, "") else ""
    if fim_str:
        fim_mes = fim_str[:7]
        if mes > fim_mes:
            return False
    return True

# ── Google Sheets ──────────────────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

EXPECTED_HEADERS = {
    "despesas": ["id", "descricao", "valor", "data", "local",
                 "pagamento", "categoria", "cartao", "n_parcelas",
                 "observacao", "criado_em", "recorrente", "recorrencia_fim"],
    "parcelas": ["id", "despesa_id", "numero", "total",
                 "valor", "vencimento", "status", "descricao", "cartao"],
    "receitas": ["id", "descricao", "valor", "data",
                 "categoria", "observacao", "criado_em", "recorrente", "recorrencia_fim"],
    "cartoes":  ["id", "nome", "limite", "dia_fechamento", "dia_vencimento", "criado_em"],
    "planejamento": ["id", "tipo", "descricao", "valor", "mes",
                      "categoria", "observacao", "criado_em"],
}

@st.cache_resource(ttl=600)
def get_sheets_client():
    creds_dict = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)

@st.cache_resource(ttl=600)
def get_workbook():
    client = get_sheets_client()
    return client.open(st.secrets["SHEET_NAME"])

def _migrar_headers_se_preciso(ws, nome: str):
    """Garante que a planilha tenha todas as colunas esperadas, sem desalinhar dados existentes."""
    esperados = EXPECTED_HEADERS.get(nome)
    if not esperados:
        return
    atuais = ws.row_values(1)
    if not atuais:
        return
    faltando = [h for h in esperados if h not in atuais]
    if faltando:
        novos_headers = atuais + faltando
        ws.update('A1', [novos_headers])

def get_sheet(name: str):
    wb = get_workbook()
    try:
        ws = wb.worksheet(name)
        _migrar_headers_se_preciso(ws, name)
        return ws
    except gspread.WorksheetNotFound:
        ws = wb.add_worksheet(title=name, rows=1000, cols=20)
        if name in EXPECTED_HEADERS:
            ws.append_row(EXPECTED_HEADERS[name])
        if name == "cartoes":
            default_cards = [
                [1, "Nubank",    5000,  5, 12, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
                [2, "Itaú",      5000, 10, 17, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
                [3, "Bradesco",  5000, 15, 22, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
                [4, "Inter",     5000, 20, 27, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
                [5, "Santander", 5000, 25,  2, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
                [6, "Outro",     5000, 10, 17, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
            ]
            ws.append_rows(default_cards)
        return ws

def sheet_to_df(ws) -> pd.DataFrame:
    data = ws.get_all_records()
    df = pd.DataFrame(data) if data else pd.DataFrame()
    name = ws.title
    if name in EXPECTED_HEADERS:
        for col in EXPECTED_HEADERS[name]:
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
@st.cache_data(ttl=300)
def carregar_cartoes():
    ws = get_sheet("cartoes")
    df = sheet_to_df(ws)
    if df.empty:
        default_cards = [
            [1, "Nubank",    5000,  5, 12, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
            [2, "Itaú",      5000, 10, 17, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
            [3, "Bradesco",  5000, 15, 22, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
            [4, "Inter",     5000, 20, 27, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
            [5, "Santander", 5000, 25,  2, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
            [6, "Outro",     5000, 10, 17, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
        ]
        ws.append_rows(default_cards)
        carregar_cartoes.clear()
        df = sheet_to_df(ws)
    return df

@st.cache_data(ttl=300)
def carregar_despesas():
    return sheet_to_df(get_sheet("despesas"))

@st.cache_data(ttl=300)
def carregar_receitas():
    return sheet_to_df(get_sheet("receitas"))

@st.cache_data(ttl=300)
def carregar_parcelas():
    return sheet_to_df(get_sheet("parcelas"))

@st.cache_data(ttl=300)
def carregar_planejamento():
    return sheet_to_df(get_sheet("planejamento"))

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
    sheet_id = ws.id
    requests = []
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
    ws.spreadsheet.batch_update({"requests": requests})

def calcular_vencimento_parcela(data_compra: date, dia_fechamento: int, dia_vencimento: int, num_parcela: int) -> date:
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
    return date(venc.year, venc.month, min(dia_vencimento, max_day))

def valores_parcelas(valor_total: float, n_parc: int) -> list:
    """
    B-03 · Divide o valor total em n_parc parcelas, garantindo que a soma
    bata exatamente com o valor total (a última parcela absorve o resto
    do arredondamento).
    """
    base = round(valor_total / n_parc, 2)
    valores = [base] * n_parc
    diferenca = round(valor_total - base * n_parc, 2)
    valores[-1] = round(valores[-1] + diferenca, 2)
    return valores

# ── Funções de persistência ────────────────────────────────────────────────────
def salvar_despesa(desc, valor, data, local, pag, cat, cartao, n_parc, obs,
                    recorrente=False, recorrencia_fim=None):
    ws_d = get_sheet("despesas")
    ws_p = get_sheet("parcelas")
    did  = next_id(ws_d)
    ws_d.append_row([did, desc, valor, data, local, pag, cat,
                     cartao or "", n_parc, obs,
                     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                     "sim" if recorrente else "nao",
                     recorrencia_fim.strftime("%Y-%m-%d") if recorrencia_fim else ""])
    if pag == "Cartão de crédito":
        df_c = carregar_cartoes()
        card_info = df_c[df_c["nome"] == cartao] if not df_c.empty else pd.DataFrame()
        if not card_info.empty:
            df_fechamento = int(card_info.iloc[0]["dia_fechamento"])
            df_vencimento = int(card_info.iloc[0]["dia_vencimento"])
        else:
            df_fechamento = DIA_VENCIMENTO_PADRAO
            df_vencimento = DIA_VENCIMENTO_PADRAO
        pid  = next_id(ws_p)
        base = datetime.strptime(data, "%Y-%m-%d").date()
        valores = valores_parcelas(valor, n_parc)  # B-03 · soma exata ao valor total
        rows = []
        for i in range(n_parc):
            venc = calcular_vencimento_parcela(base, df_fechamento, df_vencimento, i + 1)
            rows.append([pid + i, did, i + 1, n_parc, valores[i],
                         venc.strftime("%Y-%m-%d"), "pendente", desc, cartao])
        ws_p.append_rows(rows)
    carregar_despesas.clear()
    carregar_parcelas.clear()

def salvar_parcela_manual(cartao, desc, valor_parcela, num_inicial, num_total, vencimento_inicial, obs):
    ws_p = get_sheet("parcelas")
    pid  = next_id(ws_p)
    df_c = carregar_cartoes()
    card_info     = df_c[df_c["nome"] == cartao] if not df_c.empty else pd.DataFrame()
    df_vencimento = int(card_info.iloc[0]["dia_vencimento"]) if not card_info.empty else DIA_VENCIMENTO_PADRAO
    base_date = datetime.strptime(vencimento_inicial, "%Y-%m-%d").date()
    rows = []
    for i in range(num_total - num_inicial + 1):
        venc    = add_months(base_date, i)
        max_day = calendar.monthrange(venc.year, venc.month)[1]
        venc    = venc.replace(day=min(df_vencimento, max_day))
        rows.append([pid + i, -1, num_inicial + i, num_total, valor_parcela,
                     venc.strftime("%Y-%m-%d"), "pendente", desc, cartao])
    ws_p.append_rows(rows)
    carregar_parcelas.clear()

def salvar_cartao(nome, limite, dia_fechamento, dia_vencimento):
    ws = get_sheet("cartoes")
    ws.append_row([next_id(ws), nome, limite, dia_fechamento, dia_vencimento,
                   datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
    carregar_cartoes.clear()

# Item 3 · Verificar vínculos antes de excluir cartão
def cartao_tem_vinculos(nome_cartao: str) -> dict:
    """
    Retorna dict com contagens de despesas e parcelas pendentes vinculadas ao cartão.
    Usado para bloquear exclusão se houver vínculos ativos.
    """
    df_d = carregar_despesas()
    df_p = carregar_parcelas()

    n_despesas = 0
    n_parcelas_pendentes = 0

    if not df_d.empty and "cartao" in df_d.columns:
        n_despesas = int((df_d["cartao"].astype(str) == nome_cartao).sum())

    if not df_p.empty and "cartao" in df_p.columns:
        mask_p = (df_p["cartao"].astype(str) == nome_cartao) & \
                 (df_p["status"].astype(str) == "pendente")
        n_parcelas_pendentes = int(mask_p.sum())

    return {"despesas": n_despesas, "parcelas_pendentes": n_parcelas_pendentes}

def excluir_cartao(cid: int):
    ws = get_sheet("cartoes")
    df = sheet_to_df(ws)
    if not df.empty:
        delete_rows_batch(ws, df[df["id"].astype(str) == str(cid)].index.tolist())
    carregar_cartoes.clear()

def salvar_receita(desc, valor, data, cat, obs, recorrente=False, recorrencia_fim=None):
    ws = get_sheet("receitas")
    ws.append_row([next_id(ws), desc, valor, data, cat, obs,
                   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                   "sim" if recorrente else "nao",
                   recorrencia_fim.strftime("%Y-%m-%d") if recorrencia_fim else ""])
    carregar_receitas.clear()

def excluir_despesa(did: int):
    ws_d = get_sheet("despesas")
    ws_p = get_sheet("parcelas")
    df_p = sheet_to_df(ws_p)
    if not df_p.empty and "despesa_id" in df_p.columns:
        delete_rows_batch(ws_p, df_p[df_p["despesa_id"].astype(str) == str(did)].index.tolist())
    df_d = sheet_to_df(ws_d)
    if not df_d.empty:
        delete_rows_batch(ws_d, df_d[df_d["id"].astype(str) == str(did)].index.tolist())
    carregar_despesas.clear()
    carregar_parcelas.clear()

def excluir_receita(rid: int):
    ws = get_sheet("receitas")
    df = sheet_to_df(ws)
    if not df.empty:
        delete_rows_batch(ws, df[df["id"].astype(str) == str(rid)].index.tolist())
    carregar_receitas.clear()

def encerrar_recorrencia_despesa(did: int):
    ws = get_sheet("despesas")
    df = sheet_to_df(ws)
    col_idx = df.columns.get_loc("recorrencia_fim") + 1
    hoje = hoje_str()
    for idx in df[df["id"].astype(str) == str(did)].index.tolist():
        ws.update_cell(idx + 2, col_idx, hoje)
    carregar_despesas.clear()

def encerrar_recorrencia_receita(rid: int):
    ws = get_sheet("receitas")
    df = sheet_to_df(ws)
    col_idx = df.columns.get_loc("recorrencia_fim") + 1
    hoje = hoje_str()
    for idx in df[df["id"].astype(str) == str(rid)].index.tolist():
        ws.update_cell(idx + 2, col_idx, hoje)
    carregar_receitas.clear()

def salvar_planejamento(tipo, desc, valor, mes, cat, obs):
    ws = get_sheet("planejamento")
    ws.append_row([next_id(ws), tipo, desc, valor, mes, cat, obs,
                   datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
    carregar_planejamento.clear()

def salvar_planejamento_replicado(tipo, desc, valor, meses, cat, obs):
    ws = get_sheet("planejamento")
    pid = next_id(ws)
    rows = []
    for i, mes in enumerate(meses):
        rows.append([pid + i, tipo, desc, valor, mes, cat, obs,
                     datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
    ws.append_rows(rows)
    carregar_planejamento.clear()

def excluir_planejamento(pid: int):
    ws = get_sheet("planejamento")
    df = sheet_to_df(ws)
    if not df.empty:
        delete_rows_batch(ws, df[df["id"].astype(str) == str(pid)].index.tolist())
    carregar_planejamento.clear()

def atualizar_parcela(pid: int, status: str):
    ws = get_sheet("parcelas")
    df = sheet_to_df(ws)
    for idx in df[df["id"].astype(str) == str(pid)].index.tolist():
        ws.update_cell(idx + 2, df.columns.get_loc("status") + 1, status)
    carregar_parcelas.clear()

def baixar_fatura_mes(mes: str, cartao_filtro: str = None):
    ws   = get_sheet("parcelas")
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
    col_idx    = df_p.columns.get_loc("status") + 1
    range_data = [{'range': gspread.utils.rowcol_to_a1(idx + 2, col_idx), 'values': [['pago']]} for idx in idxs]
    ws.batch_update(range_data)
    carregar_parcelas.clear()
    return len(idxs)

# ══════════════════════════════════════════════════════════════════════════════
# PROJEÇÃO DE 12 MESES — funções auxiliares (R-01)
# Cada função é responsável por uma única fonte de dados, tornando o código
# testável de forma isolada e fácil de estender com novas fontes.
# ══════════════════════════════════════════════════════════════════════════════

_COLS_LINHAS = ["mes", "tipo", "origem", "descricao", "valor", "categoria"]

def _projetar_parcelas_cartao(df_p: pd.DataFrame, meses: list) -> list:
    """Fonte 1: parcelas de cartão pendentes com vencimento nos próximos 12 meses."""
    linhas = []
    if df_p.empty:
        return linhas
    meses_set = set(meses)
    df_pend = df_p[df_p["status"] == "pendente"].copy()
    df_pend["valor"] = pd.to_numeric(df_pend["valor"], errors="coerce").fillna(0.0)
    for _, row in df_pend.iterrows():
        mes = str(row["vencimento"])[:7]
        if mes in meses_set:
            linhas.append({
                "mes": mes, "tipo": "despesa", "origem": "Cartão",
                "descricao": str(row.get("descricao", "")),
                "valor": float(row["valor"]), "categoria": "Cartão de crédito",
            })
    return linhas


def _projetar_despesas(df_d: pd.DataFrame, meses: list) -> list:
    """
    Fonte 2: despesas recorrentes (não-cartão) e despesas avulsas com data futura.
    Despesas de cartão são excluídas — já entram via _projetar_parcelas_cartao,
    evitando contagem dupla.
    """
    linhas = []
    if df_d.empty:
        return linhas
    meses_set = set(meses)
    df_d2 = df_d.copy()
    df_d2["valor"] = pd.to_numeric(df_d2["valor"], errors="coerce").fillna(0.0)
    is_recorrente = df_d2.get("recorrente", "").astype(str).str.lower() == "sim"
    nao_cartao    = df_d2["pagamento"] != "Cartão de crédito"

    for _, row in df_d2[is_recorrente & nao_cartao].iterrows():
        try:
            data_ini = datetime.strptime(str(row["data"]), "%Y-%m-%d").date()
        except Exception:
            continue
        for mes in meses:
            if mes_ativo_recorrencia(mes, data_ini, row.get("recorrencia_fim")):
                linhas.append({
                    "mes": mes, "tipo": "despesa", "origem": "Recorrente",
                    "descricao": str(row["descricao"]), "valor": float(row["valor"]),
                    "categoria": str(row.get("categoria", "")),
                })

    avulsas = df_d2[(~is_recorrente) & nao_cartao &
                    (df_d2["data"].astype(str).str.slice(0, 7).isin(meses_set))]
    for _, row in avulsas.iterrows():
        linhas.append({
            "mes": str(row["data"])[:7], "tipo": "despesa", "origem": "Avulsa futura",
            "descricao": str(row["descricao"]), "valor": float(row["valor"]),
            "categoria": str(row.get("categoria", "")),
        })
    return linhas


def _projetar_receitas(df_r: pd.DataFrame, meses: list) -> list:
    """Fonte 3: receitas recorrentes e receitas avulsas com data futura."""
    linhas = []
    if df_r.empty:
        return linhas
    meses_set = set(meses)
    df_r2 = df_r.copy()
    df_r2["valor"] = pd.to_numeric(df_r2["valor"], errors="coerce").fillna(0.0)
    is_recorrente_r = df_r2.get("recorrente", "").astype(str).str.lower() == "sim"

    for _, row in df_r2[is_recorrente_r].iterrows():
        try:
            data_ini = datetime.strptime(str(row["data"]), "%Y-%m-%d").date()
        except Exception:
            continue
        for mes in meses:
            if mes_ativo_recorrencia(mes, data_ini, row.get("recorrencia_fim")):
                linhas.append({
                    "mes": mes, "tipo": "receita", "origem": "Recorrente",
                    "descricao": str(row["descricao"]), "valor": float(row["valor"]),
                    "categoria": str(row.get("categoria", "")),
                })

    avulsas_r = df_r2[(~is_recorrente_r) &
                      (df_r2["data"].astype(str).str.slice(0, 7).isin(meses_set))]
    for _, row in avulsas_r.iterrows():
        linhas.append({
            "mes": str(row["data"])[:7], "tipo": "receita", "origem": "Avulsa futura",
            "descricao": str(row["descricao"]), "valor": float(row["valor"]),
            "categoria": str(row.get("categoria", "")),
        })
    return linhas


def _projetar_planejamento(df_pl: pd.DataFrame, meses: list) -> list:
    """Fonte 4: lançamentos manuais da planilha 'planejamento'."""
    linhas = []
    if df_pl.empty:
        return linhas
    meses_set = set(meses)
    df_pl2 = df_pl.copy()
    df_pl2["valor"] = pd.to_numeric(df_pl2["valor"], errors="coerce").fillna(0.0)
    for _, row in df_pl2[df_pl2["mes"].astype(str).isin(meses_set)].iterrows():
        linhas.append({
            "mes": str(row["mes"]), "tipo": str(row["tipo"]),
            "origem": "Planejamento manual",
            "descricao": str(row["descricao"]), "valor": float(row["valor"]),
            "categoria": str(row.get("categoria", "")),
        })
    return linhas


def _consolidar_resumo(df_linhas: pd.DataFrame, meses: list) -> pd.DataFrame:
    """Agrega df_linhas por mês gerando a tabela resumo (para exibição e exportação)."""
    resumo_rows = []
    for mes in meses:
        sub = df_linhas[df_linhas["mes"] == mes]
        receitas    = float(sub[sub["tipo"] == "receita"]["valor"].sum())
        desp_cartao = float(sub[(sub["tipo"] == "despesa") & (sub["origem"] == "Cartão")]["valor"].sum())
        desp_recor  = float(sub[(sub["tipo"] == "despesa") & (sub["origem"] == "Recorrente")]["valor"].sum())
        desp_outras = float(sub[(sub["tipo"] == "despesa") &
                                (~sub["origem"].isin(["Cartão", "Recorrente"]))]["valor"].sum())
        despesas_tot = desp_cartao + desp_recor + desp_outras
        resumo_rows.append({
            "mes": mes, "Mês": fmt_mes_str_pt(mes),
            "Receitas": receitas, "Cartão": desp_cartao, "Recorrentes": desp_recor,
            "Outras desp.": desp_outras, "Despesas (total)": despesas_tot,
            "Saldo projetado": receitas - despesas_tot,
        })
    return pd.DataFrame(resumo_rows)


def _computar_panorama() -> tuple:
    """
    Orquestra as 4 fontes e retorna (df_linhas, df_resumo).
    Função pura — sem cache próprio; o cache é gerenciado por get_panorama().
    """
    meses = proximos_12_meses()
    linhas = (
        _projetar_parcelas_cartao(carregar_parcelas(), meses)
        + _projetar_despesas(carregar_despesas(), meses)
        + _projetar_receitas(carregar_receitas(), meses)
        + _projetar_planejamento(carregar_planejamento(), meses)
    )
    df_linhas = pd.DataFrame(linhas, columns=_COLS_LINHAS) if linhas else pd.DataFrame(columns=_COLS_LINHAS)
    df_resumo = _consolidar_resumo(df_linhas, meses)
    return df_linhas, df_resumo


# ── Cache de panorama via session_state (R-03) ────────────────────────────────

def get_panorama() -> tuple:
    """
    Retorna (df_linhas, df_resumo) do cache em session_state.
    Recomputa automaticamente se o cache não existir (primeira carga ou após
    invalidação explícita via botão 'Atualizar projeções').
    """
    if "panorama_cache" not in st.session_state:
        df_linhas, df_resumo = _computar_panorama()
        st.session_state["panorama_cache"] = {
            "df_linhas": df_linhas,
            "df_resumo": df_resumo,
            "ts": datetime.now(),
        }
    c = st.session_state["panorama_cache"]
    return c["df_linhas"], c["df_resumo"]


def _ts_panorama() -> str:
    """Retorna a hora da última computação do panorama, ou '—' se não calculado."""
    c = st.session_state.get("panorama_cache")
    return c["ts"].strftime("%H:%M:%S") if c else "—"


def invalidar_cache_panorama():
    """
    Descarta o panorama armazenado em session_state e limpa os caches das
    funções de carregamento, forçando releitura completa do Sheets na próxima
    chamada a get_panorama(). Deve ser chamada após qualquer escrita que
    afete o planejamento.
    """
    st.session_state.pop("panorama_cache", None)
    carregar_parcelas.clear()
    carregar_despesas.clear()
    carregar_receitas.clear()
    carregar_planejamento.clear()


# ── Exportação (R-02) ─────────────────────────────────────────────────────────

def _df_resumo_export(df_resumo: pd.DataFrame) -> pd.DataFrame:
    """Prepara o df_resumo para exportação (sem a coluna interna 'mes')."""
    return df_resumo[["Mês", "Receitas", "Cartão", "Recorrentes",
                       "Outras desp.", "Despesas (total)", "Saldo projetado"]].copy()


def _df_detalhes_export(df_linhas: pd.DataFrame) -> pd.DataFrame:
    """Prepara df_linhas para exportação com cabeçalhos amigáveis."""
    det = df_linhas[["mes", "tipo", "origem", "descricao", "categoria", "valor"]].copy()
    det.columns = ["Mês", "Tipo", "Origem", "Descrição", "Categoria", "Valor (R$)"]
    det["Mês"] = det["Mês"].apply(fmt_mes_str_pt)
    return det


def gerar_excel_panorama(df_linhas: pd.DataFrame, df_resumo: pd.DataFrame) -> bytes:
    """
    Gera um arquivo Excel (.xlsx) com duas abas:
      - 'Resumo'   → tabela agregada por mês
      - 'Detalhes' → todos os lançamentos linha a linha
    """
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        _df_resumo_export(df_resumo).to_excel(writer, sheet_name="Resumo", index=False)
        _df_detalhes_export(df_linhas).to_excel(writer, sheet_name="Detalhes", index=False)
    buf.seek(0)
    return buf.getvalue()


def gerar_csv_panorama(df_linhas: pd.DataFrame, df_resumo: pd.DataFrame) -> bytes:
    """
    Gera um CSV com BOM UTF-8 (compatível com Excel ao abrir diretamente),
    com seções de Resumo e Detalhes separadas por linha em branco.
    """
    buf = io.StringIO()
    buf.write("# RESUMO MENSAL\n")
    _df_resumo_export(df_resumo).to_csv(buf, index=False)
    buf.write("\n# DETALHES\n")
    _df_detalhes_export(df_linhas).to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8-sig")

# ══════════════════════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="main-header"><span style="font-size:1.6rem">💰</span>'
            '<span style="font-size:1.3rem;font-weight:700">Controle de Contas</span></div>',
            unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# ABAS
# ══════════════════════════════════════════════════════════════════════════════
tab_dash, tab_lanc, tab_rec, tab_lista, tab_cc, tab_cc_rec, tab_plan = st.tabs([
    "📊 Dashboard", "➖ Lançar Despesa", "➕ Lançar Receita",
    "☰ Despesas", "💳 Cartão de Crédito", "🏦 Conta Corrente",
    "🔮 Planejamento 12 Meses",
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
    with c1: st.markdown(card_html("Receitas do mês", fmt_moeda(total_rec),  "green"),   unsafe_allow_html=True)
    with c2: st.markdown(card_html("Despesas do mês", fmt_moeda(total_desp), "red"),     unsafe_allow_html=True)
    with c3: st.markdown(card_html("Saldo do mês",    fmt_moeda(saldo),      saldo_cor), unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.subheader("Histórico 6 meses")
        hist = []
        for i in range(5, -1, -1):
            d   = date.today()
            mm  = add_months(d, -i).strftime("%Y-%m")
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

# ══════════════════════════════════════════════════════════════════════════════
# LISTA DE DESPESAS
# ══════════════════════════════════════════════════════════════════════════════
with tab_lista:
    st.subheader("Despesas")
    st.markdown("##### Filtros de visualização")
    fmes = seletor_mes_ano("lista")

    f1, f2 = st.columns(2)
    fpag = f1.selectbox("Pagamento", ["Todos"] + PAGAMENTOS, key="fpag_lista")
    fcat = f2.selectbox("Categoria", ["Todas"] + CAT_DESP,  key="fcat_lista")

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
        with c1: st.markdown(card_html("Total",   fmt_moeda(total),        "blue"),  unsafe_allow_html=True)
        with c2: st.markdown(card_html("Crédito", fmt_moeda(cc_v),         "blue"),  unsafe_allow_html=True)
        with c3: st.markdown(card_html("Outros",  fmt_moeda(total - cc_v), "green"), unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        if not df_filtrado.empty:
            df_show = df_filtrado[["id", "descricao", "valor", "data", "local",
                                    "pagamento", "categoria", "n_parcelas", "observacao"]].copy()
            df_show["valor"] = df_show["valor"].apply(fmt_moeda)
            df_show["data"]  = df_show["data"].apply(converter_data_para_exibicao)
            df_show.columns  = ["ID", "Descrição", "Valor", "Data", "Local",
                                 "Pagamento", "Categoria", "Parcelas", "Obs"]

            event_d = st.dataframe(df_show, use_container_width=True, hide_index=True,
                                   on_select="rerun", selection_mode="single-row")

            st.markdown("#### Ações")
            if event_d.selection.rows:
                idx_sel      = event_d.selection.rows[0]
                id_excluir   = int(df_filtrado.iloc[idx_sel]["id"])
                desc_excluir = df_filtrado.iloc[idx_sel]["descricao"]
                val_excluir  = fmt_moeda(df_filtrado.iloc[idx_sel]["valor"])
                st.warning(f"⚠️ Despesa selecionada: **#{id_excluir} — {desc_excluir} ({val_excluir})**")
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
        else:
            st.info("Nenhuma despesa no período selecionado.")

# ══════════════════════════════════════════════════════════════════════════════
# CARTÃO DE CRÉDITO
# ══════════════════════════════════════════════════════════════════════════════
with tab_cc:
    sub_cc_list, sub_cc_faturas, sub_cc_lanc, sub_cc_config = st.tabs([
        "📊 Parcelas", "📅 Faturas Futuras", "➕ Lançar Histórico", "⚙️ Cartões & Configurações"
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

    # ── Parcelas ──
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

            pend  = float(df_p2[df_p2["status"] == "pendente"]["valor"].sum())
            venc  = int(((df_p2["status"] == "pendente") & (df_p2["vencimento"].astype(str) < hoje)).sum())
            pagas = int((df_p2["status"] == "pago").sum())
            cc1, cc2, cc3 = st.columns(3)
            with cc1: st.markdown(card_html("A pagar total", fmt_moeda(pend),       "orange"), unsafe_allow_html=True)
            with cc2: st.markdown(card_html("Vencidas",      f"{venc} parcela(s)",  "red"),    unsafe_allow_html=True)
            with cc3: st.markdown(card_html("Pagas",         f"{pagas} parcela(s)", "green"),  unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)

            if not df_filtrado.empty:
                def status_label(row):
                    if row["status"] == "pago": return "✅ Pago"
                    if str(row["vencimento"]) < hoje: return "❌ Vencido"
                    return "⏳ Pendente"
                df_filtrado = df_filtrado.copy()
                df_filtrado["Status"] = df_filtrado.apply(status_label, axis=1)

                cols_show = [c for c in ["id", "descricao", "cartao", "numero", "total", "valor", "vencimento", "Status"] if c in df_filtrado.columns]
                df_show = df_filtrado[cols_show].copy()
                df_show["valor"]      = df_show["valor"].apply(fmt_moeda)
                df_show["vencimento"] = df_show["vencimento"].apply(converter_data_para_exibicao)
                df_show.rename(columns={"id": "ID", "descricao": "Despesa/Item", "cartao": "Cartão",
                                        "numero": "Parc.", "total": "Total", "valor": "Valor",
                                        "vencimento": "Vencimento"}, inplace=True)

                event_p = st.dataframe(df_show, use_container_width=True, hide_index=True,
                                       on_select="rerun", selection_mode="single-row", key="df_parcelas_list")

                st.markdown("#### Ações da Parcela")
                if event_p.selection.rows:
                    idx_sel  = event_p.selection.rows[0]
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
            else:
                st.info("Nenhuma parcela para os filtros selecionados.")

    # ── Faturas Futuras ──
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

    # ── Lançar Histórico ──
    with sub_cc_lanc:
        st.subheader("Lançar Parcelas Anteriores / Saldo Devedor")
        st.markdown(
            "Utilize este formulário para lançar compras parceladas feitas antes do início do uso "
            "deste aplicativo que ainda possuem parcelas a vencer no cartão de crédito."
        )
        with st.form("form_parcelas_manuais", clear_on_submit=True):
            col_m1, col_m2 = st.columns(2)
            card_m = col_m1.selectbox("Cartão de Crédito", obter_nomes_cartoes(), key="m_card")
            desc_m = col_m2.text_input("Descrição da Compra * (ex: Compra Geladeira)")

            col_m3, col_m4, col_m5 = st.columns(3)
            val_parc_m   = col_m3.text_input("Valor da Parcela (R$) *", placeholder="0,00", key="m_val")
            parc_init_m  = col_m4.selectbox("Próxima Parcela a vencer *", list(range(1, 49)), index=0, key="m_init")
            parc_total_m = col_m5.selectbox("Total de Parcelas da Compra *", list(range(1, 49)), index=11, key="m_total")

            venc_init_m = st.columns(1)[0].date_input("Vencimento da próxima parcela a vencer *",
                                                       value=date.today(), format="DD/MM/YYYY", key="m_date")
            obs_m      = st.text_input("Observação (opcional)", key="m_obs")
            sub_manual = st.form_submit_button("✔ Salvar Parcelas Históricas", type="primary", use_container_width=True)

        if sub_manual:
            erros_m = []
            if not desc_m.strip(): erros_m.append("Preencha a descrição.")
            if parc_init_m > parc_total_m: erros_m.append("A próxima parcela não pode ser maior que o total.")
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
                                              venc_init_m.strftime("%Y-%m-%d"), obs_m.strip())
                        st.success(f"Parcelas históricas do item '{desc_m}' cadastradas com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar parcelas: {e}")
                    finally:
                        st.session_state["salvando_parcela"] = False

    # ── Configurações ──
    with sub_cc_config:
        st.subheader("Gerenciamento de Cartões")
        st.markdown("##### Cartões Cadastrados")
        df_c = carregar_cartoes()
        if df_c.empty:
            st.info("Nenhum cartão cadastrado no banco de dados.")
        else:
            df_c_show = df_c[["id", "nome", "limite", "dia_fechamento", "dia_vencimento"]].copy()
            df_c_show["limite"] = df_c_show["limite"].apply(fmt_moeda)
            df_c_show.columns   = ["ID", "Nome do Cartão", "Limite de Crédito", "Dia do Fechamento", "Dia do Vencimento"]
            event_c = st.dataframe(df_c_show, use_container_width=True, hide_index=True,
                                   on_select="rerun", selection_mode="single-row", key="df_cartoes_config_list")

            if event_c.selection.rows:
                idx_sel     = event_c.selection.rows[0]
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
        with st.form("form_cadastro_cartao", clear_on_submit=True):
            col_nc1, col_nc2 = st.columns(2)
            nome_nc   = col_nc1.text_input("Nome do Cartão * (ex: Nubank Platinum)")
            limite_nc = col_nc2.text_input("Limite de Crédito (R$) *", placeholder="0,00", key="nc_limit")
            col_nc3, col_nc4 = st.columns(2)
            fechamento_nc = col_nc3.selectbox("Dia do Fechamento da Fatura *", list(range(1, 32)), index=4,  key="nc_fech")
            vencimento_nc = col_nc4.selectbox("Dia do Vencimento da Fatura *", list(range(1, 32)), index=11, key="nc_venc")
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
    with m1: st.markdown(card_html("Total receitas",  fmt_moeda(total_rec_cc),  "green"),      unsafe_allow_html=True)
    with m2: st.markdown(card_html("Total despesas",  fmt_moeda(total_desp_cc), "red"),        unsafe_allow_html=True)
    with m3: st.markdown(card_html("Saldo acumulado", fmt_moeda(saldo_cc),      saldo_cor_cc), unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    movs = []
    if not rec_cc.empty:
        for _, row in rec_cc.iterrows():
            movs.append({"Data": row["data"], "Descrição": row["descricao"], "Tipo": "Receita",
                         "Categoria": row.get("categoria", ""), "Valor": float(row["valor"]),
                         "ID": row["id"], "_tipo": "rec"})
    if not desp_cc.empty:
        for _, row in desp_cc.iterrows():
            movs.append({"Data": row["data"], "Descrição": row["descricao"], "Tipo": "Despesa",
                         "Categoria": row.get("categoria", ""), "Valor": -float(row["valor"]),
                         "ID": row["id"], "_tipo": "dsp"})
    movs.sort(key=lambda x: x["Data"])

    saldo_ac = 0.0
    extrato  = []
    for m in movs:
        saldo_ac += m["Valor"]
        extrato.append({
            "Data": converter_data_para_exibicao(m["Data"]), "Descrição": m["Descrição"],
            "Tipo": m["Tipo"], "Categoria": m["Categoria"],
            "Valor": fmt_moeda(abs(m["Valor"])), "Saldo": fmt_moeda(saldo_ac),
        })

    if extrato:
        df_extrato = pd.DataFrame(extrato)
        event_cc = st.dataframe(df_extrato, use_container_width=True, hide_index=True,
                                on_select="rerun", selection_mode="single-row")

        st.markdown("#### Ações do Lançamento")
        if event_cc.selection.rows:
            idx_sel  = event_cc.selection.rows[0]
            mov_sel  = movs[idx_sel]
            id_sel   = int(mov_sel["ID"])
            tipo_sel = mov_sel["_tipo"]
            desc_sel = mov_sel["Descrição"]
            val_sel  = fmt_moeda(abs(mov_sel["Valor"]))
            if tipo_sel == "rec":
                st.warning(f"⚠️ Receita selecionada: **#{id_sel} — {desc_sel} ({val_sel})**")

                # Item 2 · Confirmação explícita antes de excluir receita
                confirmar_r = st.checkbox(
                    f"Confirmo a exclusão da receita #{id_sel}",
                    key=f"confirmar_excl_rec_{id_sel}"
                )
                if confirmar_r:
                    if st.button("🗑 Excluir receita", type="primary", use_container_width=True, key="btn_excl_rec"):
                        try:
                            excluir_receita(id_sel)
                            st.success(f"Receita #{id_sel} excluída!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao excluir: {e}")
                else:
                    st.button("🗑 Excluir receita", type="primary", use_container_width=True,
                              disabled=True, key="btn_excl_rec_dis")
            else:
                st.info(f"ℹ️ O lançamento selecionado é uma **Despesa** (#{id_sel}). Para excluí-la, utilize a aba **☰ Despesas**.")
        else:
            st.info("💡 Clique em um lançamento do extrato acima para opções de exclusão (disponível para Receitas).")
    else:
        st.info("Nenhum movimento para o período selecionado.")

# ══════════════════════════════════════════════════════════════════════════════
# PLANEJAMENTO 12 MESES
# ══════════════════════════════════════════════════════════════════════════════
with tab_plan:
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

    # ── Panorama ──
    with sub_plan_panorama:
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
        else:
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

    # ── Lançamentos Futuros (planejamento manual) ──
    with sub_plan_futuros:
        st.subheader("Lançar item de Planejamento")
        st.caption("Use para itens pontuais que não são recorrentes nem parcelas "
                   "(ex.: IPTU em março, 13º salário em dezembro).")

        with st.form("form_planejamento", clear_on_submit=True):
            p1, p2 = st.columns([1, 3])
            tipo_pl = p1.selectbox("Tipo", ["Despesa", "Receita"])
            desc_pl = p2.text_input("Descrição *")

            p3, p4 = st.columns(2)
            valor_pl = p3.text_input("Valor (R$) *", placeholder="0,00", key="pl_valor")
            cat_opcoes = CAT_DESP if tipo_pl == "Despesa" else CAT_REC
            cat_pl = p4.selectbox("Categoria", [""] + cat_opcoes, key="pl_cat")

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
                        st.success(f"Lançamento '{desc_pl}' replicado para os 12 meses!")
                    else:
                        salvar_planejamento(tipo_db, desc_pl.strip(), v_pl, mes_pl, cat_pl, obs_pl.strip())
                        st.success(f"Lançamento '{desc_pl}' adicionado ao planejamento de {fmt_mes_str_pt(mes_pl)}!")
                    invalidar_cache_panorama()
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao salvar planejamento: {e}")

        st.markdown("---")
        st.markdown("##### Itens de Planejamento Cadastrados")
        df_pl_list = carregar_planejamento()
        if df_pl_list.empty:
            st.info("Nenhum item de planejamento cadastrado.")
        else:
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

    # ── Recorrentes ──
    with sub_plan_recorrentes:
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
        with st.form("form_receita_recorrente_rapida", clear_on_submit=True):
            qr1, qr2 = st.columns([3, 1])
            qdesc = qr1.text_input("Descrição * (ex: Salário)")
            qvalor = qr2.text_input("Valor (R$) *", placeholder="0,00", key="qr_valor")
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
                    st.success(f"Receita recorrente '{qdesc}' cadastrada!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao cadastrar: {e}")
