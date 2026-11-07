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

import hmac

import streamlit as st

USUARIO_PADRAO = "—"


def _senhas_iguais(digitada, cadastrada) -> bool:
    """Compara em TEMPO CONSTANTE (não vaza, pelo tempo de resposta, quantas letras acertou)."""
    a = ("" if digitada is None else str(digitada)).encode("utf-8")
    b = ("" if cadastrada is None else str(cadastrada)).encode("utf-8")
    return hmac.compare_digest(a, b)


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

    Segurança: a senha é comparada em tempo constante e a conferência passa por TODAS as
    entradas (sem parar na primeira que bate), então o tempo de resposta não revela quais
    usuários existem. Senha cadastrada vazia NUNCA autentica (secrets mal preenchidos).

    Não usa Streamlit — testável isoladamente.
    """
    if usuarios:
        alvo = (nome_digitado or "").strip().lower()
        achado = None
        for nome_cadastrado, senha_cadastrada in usuarios.items():
            senha_ok = _senhas_iguais(senha_digitada, senha_cadastrada)
            nome_ok = str(nome_cadastrado).strip().lower() == alvo
            if achado is None and nome_ok and senha_ok and str(senha_cadastrada) != "":
                achado = nome_cadastrado
        return achado

    if senha_unica and _senhas_iguais(senha_digitada, senha_unica):
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
