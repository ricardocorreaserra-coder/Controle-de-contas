"""
S-01 · Autenticação, com limite de tentativas (B-01) para dificultar
força bruta.

Suporta dois modos, escolhidos automaticamente conforme os secrets:

  • MULTIUSUÁRIO — se existir a seção [USUARIOS] nos secrets, a tela pede
    usuário + senha e cada pessoa tem sua própria credencial. Permite
    revogar o acesso de uma pessoa sem afetar as demais, e registrar quem
    lançou cada despesa/receita.

  • SENHA ÚNICA (modo antigo) — se [USUARIOS] não existir, pede só a
    senha e usa APP_PASSWORD, exatamente como antes. Nenhuma configuração
    existente quebra ao atualizar.

A lógica de conferência das credenciais fica em utils/sessao.py
(`autenticar_credenciais`), que é pura e testável isoladamente.
"""

import time

import streamlit as st

from utils.sessao import autenticar_credenciais, _ler_usuarios_dos_secrets


def verificar_autenticacao():
    if "autenticado" not in st.session_state:
        st.session_state["autenticado"] = False
    if "tentativas_login" not in st.session_state:
        st.session_state["tentativas_login"] = 0

    if st.session_state["autenticado"]:
        return

    usuarios = _ler_usuarios_dos_secrets()
    senha_unica = st.secrets.get("APP_PASSWORD", "")
    modo_multiusuario = bool(usuarios)

    instrucao = ("Entre com seu usuário e senha" if modo_multiusuario
                 else "Digite a senha para acessar")

    # B-01 · Limite simples de tentativas para dificultar força bruta
    bloqueado = st.session_state["tentativas_login"] >= 5

    # Layout: UM único cartão com borda (st.container(border=True)) contendo
    # título, instrução e campos, centralizado na página. Antes o título ficava
    # numa caixa HTML que fechava ANTES dos campos, que apareciam soltos fora
    # dela, e o <h2> ganhava espaçamento extra do Streamlit (vão grande entre
    # título e instrução). Aqui o título usa <div> (sem espaçamento embutido) e
    # nenhuma cor fixa — a borda e o texto seguem o tema claro/escuro.
    st.markdown('<div style="height:3rem"></div>', unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2, st.container(border=True):
        st.markdown(f"""
        <div style="text-align:center;padding:0.5rem 0 1rem">
            <div style="font-size:2.5rem;line-height:1.2">💰</div>
            <div style="font-size:1.75rem;font-weight:700;margin:0.25rem 0">Controle de Contas</div>
            <div style="opacity:0.7">{instrucao}</div>
        </div>
        """, unsafe_allow_html=True)

        if bloqueado:
            st.error("Muitas tentativas incorretas. Recarregue a página para tentar novamente.")
            st.stop()

        nome = ""
        if modo_multiusuario:
            nome = st.text_input(
                "Usuário", label_visibility="collapsed", placeholder="Usuário..."
            )
        senha = st.text_input(
            "Senha", type="password",
            label_visibility="collapsed",
            placeholder="Digite a senha..."
        )

        if st.button("Entrar", use_container_width=True, type="primary"):
            if not modo_multiusuario and not senha_unica:
                st.error("APP_PASSWORD não configurada nos secrets.")
                st.stop()

            usuario_ok = autenticar_credenciais(nome, senha, usuarios, senha_unica)
            if usuario_ok:
                st.session_state["autenticado"] = True
                st.session_state["usuario"] = usuario_ok
                st.session_state["tentativas_login"] = 0
                st.rerun()
            else:
                # B-01 · Atraso proposital a cada tentativa falha. Isso não
                # depende do contador em session_state (que um F5 zera) —
                # desacelera qualquer tentativa automatizada de força bruta
                # mesmo que a pessoa recarregue a página entre uma tentativa
                # e outra.
                time.sleep(2)
                st.session_state["tentativas_login"] += 1
                restantes = 5 - st.session_state["tentativas_login"]
                erro = ("Usuário ou senha incorretos." if modo_multiusuario
                        else "Senha incorreta.")
                st.error(f"{erro} Tentativas restantes: {max(restantes, 0)}.")
    st.stop()
