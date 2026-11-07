"""
Controle de Contas - Versão Web (Streamlit + Google Sheets)
Uso: streamlit run app.py

Este arquivo é apenas o ponto de entrada: configura a página, aplica o CSS,
verifica autenticação e monta o menu de navegação (no topo da tela). Toda a lógica
de negócio e acesso a dados vive em `logica/`, `sheets/` e `utils/`; o
conteúdo de cada página vive em `paginas/`.
"""

import streamlit as st

from config import CSS
from auth import verificar_autenticacao
from sheets.client import diagnostico_planilha, texto_aviso_planilhas
from utils.navegacao import registrar_paginas
from utils.sessao import usuario_atual, USUARIO_PADRAO
from utils.widgets import exibir_toasts_pendentes
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
    initial_sidebar_state="collapsed",  # não há mais menu lateral (menu fica no topo)
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
    # Uma linha só (também no celular — regra 22): "Conectado como X   [Sair]".
    with st.container(horizontal=True, vertical_alignment="center"):
        st.caption(f"👤 Conectado como **{_usuario}**")
        if st.button("Sair", key="btn_sair", width="content"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# NAVEGAÇÃO (menu no topo)
# ══════════════════════════════════════════════════════════════════════════════
# Antes disso o app usava st.tabs, que renderiza as 8 páginas a cada
# interação (digitar em um campo já reprocessa Dashboard, Planejamento
# etc. por baixo, mesmo invisíveis). Com st.navigation, só a página
# selecionada roda — as outras 7 ficam paradas até o usuário clicar nelas.
# Cada página tem um url_path próprio (todas as funções se chamam "render",
# então o Streamlit não consegue inferir o endereço sozinho).
_PAGINAS = [
    (dashboard, "Dashboard", "📊", "dashboard"),
    (lancar_despesa, "Despesa", "💸", "lancar-despesa"),
    (lancar_receita, "Receita", "💵", "lancar-receita"),
    (lista_despesas, "Despesas", "📋", "despesas"),
    (cartao_credito, "Cartão", "💳", "cartao"),
    (conta_corrente, "Conta", "🏦", "conta-corrente"),
    (planejamento_12_meses, "Planejar", "🔮", "planejamento"),
    (emprestimos, "Empréstimos", "🏛️", "emprestimos"),
]

# Aviso (só aparece se houver) quando mais de uma planilha tem o nome configurado — ver sheets/client.py.
_diag_planilha = diagnostico_planilha()
if _diag_planilha["ambigua"]:
    st.warning(texto_aviso_planilhas(_diag_planilha, _diag_planilha["nome"]), icon="⚠️")

_objetos_paginas = {
    caminho: st.Page(modulo.render, title=titulo, icon=icone, url_path=caminho,
                     default=(caminho == "dashboard"))
    for modulo, titulo, icone, caminho in _PAGINAS
}
# Permite que as telas levem a outra (botão do estado vazio) — ver utils/navegacao.py.
registrar_paginas(_objetos_paginas)

pagina_atual = st.navigation(list(_objetos_paginas.values()), position="top")
# Avisos flutuantes das movimentações feitas na execução anterior (lançar/alterar/
# excluir) — aparecem em qualquer página, mesmo com a tela rolada.
exibir_toasts_pendentes()

pagina_atual.run()