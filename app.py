"""
Controle de Contas - Versão Web (Streamlit + Google Sheets)
Uso: streamlit run app.py

Este arquivo é apenas o ponto de entrada: configura a página, aplica o CSS,
verifica autenticação e monta as abas. Toda a lógica de negócio e acesso a
dados vive em `logica/`, `sheets/` e `utils/`; o conteúdo de cada aba vive
em `paginas/`.
"""

import streamlit as st

from config import CSS
from auth import verificar_autenticacao
from paginas import (
    dashboard,
    lancar_despesa,
    lancar_receita,
    lista_despesas,
    cartao_credito,
    conta_corrente,
    planejamento_12_meses,
)

# ── Configuração da página ─────────────────────────────────────────────────────
st.set_page_config(
    page_title="Controle de Contas",
    page_icon=":moneybag:",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Estilos CSS ───────────────────────────────────────────────────────────────
st.markdown(CSS, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# AUTENTICAÇÃO
# ══════════════════════════════════════════════════════════════════════════════
verificar_autenticacao()

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

with tab_dash:
    dashboard.render()

with tab_lanc:
    lancar_despesa.render()

with tab_rec:
    lancar_receita.render()

with tab_lista:
    lista_despesas.render()

with tab_cc:
    cartao_credito.render()

with tab_cc_rec:
    conta_corrente.render()

with tab_plan:
    planejamento_12_meses.render()
