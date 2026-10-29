"""
Widgets reutilizáveis de Streamlit. Diferente de utils/formatacao.py
(funções puras, sem Streamlit), este módulo depende de `streamlit` e
concentra padrões de UI usados em várias páginas — hoje, especialmente,
o campo de valor monetário com máscara de centavos.
"""

import streamlit as st

from utils.datas import MESES_COMPLETOS, deslocar_mes, hoje_br, seletor_mes_ano
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


# ── Avisos de confirmação das movimentações (lançar / alterar / excluir) ──────
#
# Toda gravação termina com `st.rerun()`. Um `st.success()` chamado ANTES do
# rerun nunca chega a ser exibido (o rerun interrompe o envio da tela). Por isso
# o aviso é AGENDADO em session_state e exibido na execução seguinte, de dois
# jeitos ao mesmo tempo:
#
#   1. Aviso flutuante (`st.toast`), mostrado por `exibir_toasts_pendentes()`
#      UMA vez em app.py: aparece no canto da tela, em qualquer página ou aba, e
#      mesmo que a pessoa esteja com a tela rolada lá embaixo (onde ficam os
#      botões de editar/excluir).
#   2. Quadro de confirmação (`st.success`/`st.warning`) no topo da aba onde a
#      ação foi feita, mostrado por `exibir_mensagem_pendente(chave)`, que fica
#      na tela até a próxima interação.
#
# `chave` identifica ONDE o quadro aparece. Telas com abas (st.tabs) executam o
# corpo de todas as abas a cada rodada; com a chave genérica, a mensagem é
# consumida pela primeira aba que a lê — que pode não ser a aba da ação. Nessas
# telas, cada aba usa a sua própria chave.

CHAVE_AVISO = "_msg_sucesso_pendente"
_FILA_TOASTS = "_toasts_pendentes"

# tipo -> (ícone, função de exibição do quadro)
_TIPOS_AVISO = {
    "sucesso":  ("✅", "success"),
    "excluido": ("🗑️", "success"),
    "aviso":    ("⚠️", "warning"),
}


def avisar(mensagem: str, chave: str = CHAVE_AVISO, tipo: str = "sucesso"):
    """Agenda a confirmação de uma movimentação para a PRÓXIMA execução do
    script. Não faz rerun: o chamador faz `st.rerun()` em seguida (ou usa
    `concluir_com_sucesso`).

    `tipo`: "sucesso" (lançou/alterou), "excluido" (excluiu) ou "aviso"
    (ex.: estorno, ou ação que não encontrou nada para fazer).
    """
    if tipo not in _TIPOS_AVISO:
        tipo = "sucesso"
    st.session_state[chave] = (tipo, mensagem)
    st.session_state.setdefault(_FILA_TOASTS, []).append((tipo, mensagem))


def concluir_com_sucesso(mensagem: str, campo_valor_base_key=None,
                         chave: str = CHAVE_AVISO, tipo: str = "sucesso"):
    """
    Agenda a confirmação (ver `avisar`) e, opcionalmente, a limpeza de um ou
    mais campos de valor monetário criados fora de um st.form via
    `campo_valor_moeda`. Termina chamando st.rerun().

    `campo_valor_base_key` aceita None, uma string única, ou uma lista de
    strings — útil em telas com mais de um campo de valor (ex.: a tela de
    Empréstimos, que tem "Valor da Parcela" e "Valor Total do Débito").
    """
    avisar(mensagem, chave=chave, tipo=tipo)
    if campo_valor_base_key:
        chaves = [campo_valor_base_key] if isinstance(campo_valor_base_key, str) else campo_valor_base_key
        for k in chaves:
            limpar_campo_valor(k)
    st.rerun()


def exibir_mensagem_pendente(chave: str = CHAVE_AVISO):
    """Mostra (e descarta) o quadro de confirmação agendado em `chave`.
    Chame uma vez, no topo da aba/função onde a ação acontece."""
    item = st.session_state.pop(chave, None)
    if not item:
        return
    # Compatibilidade: texto simples (formato antigo) conta como sucesso.
    tipo, msg = ("sucesso", item) if isinstance(item, str) else item
    icone, exibir = _TIPOS_AVISO.get(tipo, _TIPOS_AVISO["sucesso"])
    getattr(st, exibir)(msg, icon=icone)


def exibir_toasts_pendentes():
    """Mostra os avisos flutuantes agendados por `avisar`. Chamada UMA vez por
    execução, em app.py, antes de desenhar a página."""
    for tipo, msg in st.session_state.pop(_FILA_TOASTS, []):
        icone, _ = _TIPOS_AVISO.get(tipo, _TIPOS_AVISO["sucesso"])
        st.toast(msg, icon=icone, duration="long")


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


def barra_periodo(key_prefix: str) -> str:
    """
    Barra de período: [‹] [Outubro 2026 ▾] [›] [Este mês]. Devolve 'YYYY-MM'.

    Reaproveita `seletor_mes_ano` (os mesmos selects de Ano e Mês, mesmas keys
    `<prefixo>_ano` / `<prefixo>_mes`) dentro do menu que abre ao clicar no mês,
    para pular direto para outro mês/ano. As setas e o "Este mês" só mexem nessas
    keys (num callback, antes de a tela ser redesenhada). O intervalo é o mesmo
    do seletor antigo: do ano atual − 4 até dezembro do ano atual.
    `st.container(horizontal=True)` mantém os botões na MESMA linha no celular
    (colunas empilham em tela estreita).
    """
    hoje = hoje_br()
    k_ano, k_mes = f"{key_prefix}_ano", f"{key_prefix}_mes"
    ano_min, ano_max = hoje.year - 4, hoje.year
    ano = st.session_state.get(k_ano, hoje.year)
    mes = st.session_state.get(k_mes, hoje.month)

    def _ir(a, m):
        st.session_state[k_ano], st.session_state[k_mes] = a, m

    def _mover(delta):
        a, m = deslocar_mes(st.session_state.get(k_ano, hoje.year),
                            st.session_state.get(k_mes, hoje.month), delta)
        if ano_min <= a <= ano_max:
            _ir(a, m)

    pode_voltar = ano_min <= deslocar_mes(ano, mes, -1)[0]
    pode_avancar = deslocar_mes(ano, mes, 1)[0] <= ano_max
    com_mes_atual = (ano, mes) == (hoje.year, hoje.month)

    with st.container(horizontal=True, vertical_alignment="center"):
        st.button("‹", key=f"{key_prefix}_mes_ant", on_click=_mover, args=(-1,),
                  disabled=not pode_voltar, help="Mês anterior")
        with st.popover(f"{MESES_COMPLETOS[mes]} {ano}", help="Escolher outro mês ou ano"):
            periodo = seletor_mes_ano(key_prefix)
        st.button("›", key=f"{key_prefix}_mes_prox", on_click=_mover, args=(1,),
                  disabled=not pode_avancar, help="Próximo mês")
        st.button("Este mês", key=f"{key_prefix}_mes_hoje", on_click=_ir,
                  args=(hoje.year, hoje.month), disabled=com_mes_atual)
    return periodo

