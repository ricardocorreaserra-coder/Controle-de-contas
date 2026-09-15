"""
Identificação do usuário logado.

Suporta acesso multiusuário: cada pessoa tem sua própria senha, definida
em `st.secrets` sob a seção [USUARIOS]. Isso permite revogar o acesso de
uma pessoa sem trocar a senha de todo mundo, e registrar quem lançou cada
despesa/receita (ver coluna `lancado_por`).

Compatibilidade: se [USUARIOS] não existir nos secrets, o app continua
aceitando a senha única antiga (APP_PASSWORD) e registra os lançamentos
como feitos por "—". Nenhuma configuração existente quebra.
"""

import streamlit as st

USUARIO_PADRAO = "—"


def autenticar_credenciais(nome_digitado: str, senha_digitada: str,
                            usuarios: dict, senha_unica: str = "") -> str:
    """
    Função pura de autenticação. Retorna o NOME do usuário autenticado, ou
    None se as credenciais não conferirem.

    Regras, nesta ordem:
      1) Se `usuarios` tiver entradas, o par nome+senha precisa bater com
         uma delas (comparação do nome é case-insensitive e ignora espaços
         nas pontas; a senha é comparada exatamente).
      2) Senão, cai no modo antigo: só a senha importa e precisa bater com
         `senha_unica`; o usuário retornado é USUARIO_PADRAO.

    Não usa Streamlit — testável isoladamente.
    """
    if usuarios:
        alvo = (nome_digitado or "").strip().lower()
        for nome_cadastrado, senha_cadastrada in usuarios.items():
            if nome_cadastrado.strip().lower() == alvo and senha_digitada == senha_cadastrada:
                return nome_cadastrado
        return None

    if senha_unica and senha_digitada == senha_unica:
        return USUARIO_PADRAO
    return None


def _ler_usuarios_dos_secrets() -> dict:
    """Lê a seção [USUARIOS] dos secrets. Devolve {} se não existir."""
    try:
        usuarios = st.secrets.get("USUARIOS", {})
        return dict(usuarios) if usuarios else {}
    except Exception:
        return {}


def usuario_atual() -> str:
    """
    Nome de quem está logado nesta sessão — usado para preencher a coluna
    `lancado_por` dos registros. Retorna USUARIO_PADRAO se o app estiver
    no modo de senha única (sem [USUARIOS] configurado).
    """
    return st.session_state.get("usuario", USUARIO_PADRAO)
