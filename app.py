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
from utils.sessao import usuario_atual, USUARIO_PADRAO
from paginas import (
    dashboard,
    lancar_despesa,
    lancar_receita,
    lista_despesas,
    cartao_credito,
    conta_corrente,
    planejamento_12_meses,
    emprestimos,
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

# Identificação de quem está usando o app — só aparece no modo multiusuário
# (quando a seção [USUARIOS] existe nos secrets). No modo de senha única,
# usuario_atual() devolve USUARIO_PADRAO e nada é exibido.
_usuario = usuario_atual()
if _usuario != USUARIO_PADRAO:
    col_user, col_sair = st.columns([5, 1])
    col_user.caption(f"👤 Conectado como **{_usuario}**")
    if col_sair.button("Sair", use_container_width=True, key="btn_sair"):
        st.session_state["autenticado"] = False
        st.session_state.pop("usuario", None)
        st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# ABAS
# ══════════════════════════════════════════════════════════════════════════════
tab_dash, tab_lanc, tab_rec, tab_lista, tab_cc, tab_cc_rec, tab_plan, tab_emp = st.tabs([
    "📊 Dashboard", "➖ Lançar Despesa", "➕ Lançar Receita",
    "☰ Despesas", "💳 Cartão de Crédito", "🏦 Conta Corrente",
    "🔮 Planejamento 12 Meses", "🏛️ Empréstimos",
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

with tab_emp:
    emprestimos.render()