"""
S-01 · Autenticação por senha simples, com limite de tentativas (B-01)
para dificultar força bruta.
"""

import streamlit as st


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
