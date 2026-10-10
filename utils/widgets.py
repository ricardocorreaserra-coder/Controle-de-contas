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


def campo_valor_moeda(label: str, base_key: str, placeholder: str = "0,00", value: str = None) -> str:
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

    `value`, se informado, pré-preenche o campo — usado em telas de EDIÇÃO,
    para já mostrar o valor atual do registro (formatado, ex.: "1.234,56",
    sem o "R$"). Só tem efeito na primeira vez que essa key é criada; não
    sobrescreve o que o usuário já digitou em execuções seguintes.

    Retorna o texto atualmente no campo.
    """
    versao = st.session_state.get(f"_v__{base_key}", 0)
    key = f"{base_key}__{versao}"
    if value is not None and key not in st.session_state:
        st.session_state[key] = value
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


def opcoes_categoria(categorias, cat_atual):
    """
    Opções do selectbox de categoria nas telas de EDIÇÃO + índice da atual.

    Se a categoria já gravada no lançamento não estiver (mais) na lista —
    por ter sido renomeada/removida do config.py —, ela é acrescentada ao
    final das opções. Sem isso, o selectbox cairia em "vazio" e salvar a
    edição APAGARIA a categoria sem a pessoa perceber.
    """
    if cat_atual is None or cat_atual != cat_atual:   # None ou NaN
        cat_atual = ""
    atual = str(cat_atual).strip()
    opcoes = [""] + list(categorias)
    if atual and atual not in opcoes:
        opcoes.append(atual)
    return opcoes, opcoes.index(atual) if atual in opcoes else 0


def botao_pdf(rotulo: str, gerar, nome_arquivo: str, key: str) -> None:
    """
    Botão "🖨️ ..." que baixa um PDF da tela para IMPRESSÃO.

    `gerar` é um callable (normalmente um functools.partial de uma função de
    logica/relatorios.py, já com os dados da tela) que aceita `emitido_por=`
    e devolve os bytes do PDF. O PDF só é gerado quando a pessoa CLICA
    (o Streamlit chama o callable nesse momento), então não pesa no uso
    normal do app, e `on_click="ignore"` evita recarregar a página no clique.

    Passe sempre CÓPIAS dos DataFrames no partial (`df.copy()`): o callable
    roda depois, e a tela pode ter alterado a variável original nesse meio tempo.
    """
    from functools import partial

    usuario = str(st.session_state.get("usuario", "") or "")
    st.download_button(
        f"🖨️ {rotulo}",
        data=partial(gerar, emitido_por=usuario),
        file_name=nome_arquivo,
        mime="application/pdf",
        key=key,
        on_click="ignore",
        use_container_width=True,
    )
