"""
Widgets reutilizáveis de Streamlit. Diferente de utils/formatacao.py
(funções puras, sem Streamlit), este módulo depende de `streamlit` e
concentra padrões de UI usados em várias páginas — hoje, especialmente,
o campo de valor monetário com máscara de centavos.
"""

import streamlit as st

from utils.formatacao import formatar_input_moeda


def _on_blur_valor_moeda(key: str):
    """Streamlit dispara o on_change de um text_input ao perder o foco ou
    apertar Enter — não a cada tecla digitada. É esse o momento certo
    para reformatar o valor."""
    st.session_state[key] = formatar_input_moeda(st.session_state.get(key, ""))


def campo_valor_moeda(label: str, base_key: str, placeholder: str = "0,00") -> str:
    """
    Campo de texto para valores em R$ que se auto-formata ao perder o
    foco, preenchendo as casas decimais a partir da direita — digitar
    "150" vira "1,50"; digitar "15000" vira "150,00" (mesma máscara usada
    em apps bancários).

    IMPORTANTE: deve ficar FORA de um `st.form(...)`. Widgets dentro de
    formulários só disparam on_change quando o formulário inteiro é
    enviado, não ao perder o foco individualmente — o que impediria a
    reformatação de acontecer antes mesmo de o usuário terminar de
    preencher o resto do formulário.

    `base_key` é combinada com um contador guardado em session_state
    (ver `limpar_campo_valor`) para permitir esvaziar o campo depois de
    um envio bem-sucedido: incrementar o contador troca a key do widget e
    o Streamlit o recria do zero, vazio — sem precisar (e sem poder)
    sobrescrever diretamente o valor de um widget que já foi instanciado
    nesta mesma execução do script.

    Retorna o texto atualmente no campo.
    """
    versao = st.session_state.get(f"_v__{base_key}", 0)
    key = f"{base_key}__{versao}"
    return st.text_input(
        label, key=key, placeholder=placeholder,
        on_change=_on_blur_valor_moeda, args=(key,),
    )


def limpar_campo_valor(base_key: str):
    """Chame após salvar com sucesso — faz o próximo render usar uma key
    nova para o campo de valor identificado por `base_key`, esvaziando-o
    (não é possível apenas sobrescrever o valor de um widget que já foi
    instanciado na execução atual)."""
    st.session_state[f"_v__{base_key}"] = st.session_state.get(f"_v__{base_key}", 0) + 1


def concluir_com_sucesso(mensagem: str, campo_valor_base_key=None):
    """
    Agenda a exibição de uma mensagem de sucesso para a PRÓXIMA execução
    do script e, opcionalmente, agenda a limpeza de um ou mais campos de
    valor monetário criados fora de um st.form via `campo_valor_moeda`.
    Termina chamando st.rerun().

    `campo_valor_base_key` aceita None, uma string única, ou uma lista de
    strings — útil em telas com mais de um campo de valor (ex.: a tela de
    Empréstimos, que tem "Valor da Parcela" e "Valor Total do Débito").

    Por que agendar em vez de só chamar st.success() direto: como esta
    função sempre termina com st.rerun(), qualquer st.success() chamado
    ANTES dele na mesma execução nunca chegaria a ser exibido — o rerun
    interrompe o envio da tela para o navegador. Guardando a mensagem em
    session_state, ela é exibida (por `exibir_mensagem_pendente`) já na
    execução seguinte, junto com o(s) campo(s) de valor mostrando-se vazios.
    """
    st.session_state["_msg_sucesso_pendente"] = mensagem
    if campo_valor_base_key:
        chaves = [campo_valor_base_key] if isinstance(campo_valor_base_key, str) else campo_valor_base_key
        for chave in chaves:
            limpar_campo_valor(chave)
    st.rerun()


def exibir_mensagem_pendente():
    """Chame uma vez, no topo da função de uma página — exibe (e
    descarta) qualquer mensagem de sucesso agendada por
    `concluir_com_sucesso`."""
    msg = st.session_state.pop("_msg_sucesso_pendente", None)
    if msg:
        st.success(msg)