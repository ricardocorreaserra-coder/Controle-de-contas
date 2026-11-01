"""
Navegação entre páginas por código (ex.: o botão do estado vazio que leva a "Lançar despesa").

As páginas são funções (`st.Page(modulo.render, ...)`), então `st.switch_page` precisa do
OBJETO da página, que só o `app.py` tem. O `app.py` registra o mapa `url_path -> página`
a cada execução (`registrar_paginas`) e as telas pedem o destino pelo `url_path` (`ir_para`).
"""

import streamlit as st

_CHAVE = "_paginas_registradas"


def registrar_paginas(mapa: dict) -> None:
    """Chamado só pelo app.py: {url_path: objeto st.Page}."""
    st.session_state[_CHAVE] = dict(mapa)


def pagina_registrada(url_path: str):
    """O objeto da página registrada com esse url_path, ou None."""
    return st.session_state.get(_CHAVE, {}).get(url_path)


def ir_para(url_path: str) -> None:
    """Troca para a página de `url_path` (encerra a execução atual, como st.rerun)."""
    pagina = pagina_registrada(url_path)
    if pagina is None:
        st.warning("Não foi possível abrir essa tela agora. Use o menu do topo.")
        return
    st.switch_page(pagina)
