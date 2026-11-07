"""
Camada de acesso ao Google Sheets: autenticação, obtenção de planilhas
e conversão para DataFrame.

IMPORTANTE (cache do Streamlit): as funções decoradas com @st.cache_resource
e @st.cache_data DEVEM ser definidas apenas UMA VEZ, aqui e nos módulos de
`sheets/loaders.py`. O cache do Streamlit é associado ao objeto de função em
si (não ao arquivo/local de importação), então todo o resto do projeto deve
sempre IMPORTAR estas funções — nunca redefini-las ou recriar uma cópia do
decorator em outro lugar. Isso garante que `.clear()` chamado a partir de
qualquer módulo realmente invalide o mesmo cache compartilhado.
"""

import logging

import pandas as pd
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

from config import SCOPES, SCOPES_AMPLOS, EXPECTED_HEADERS

_LOG = logging.getLogger("controle_contas")


@st.cache_resource(ttl=600)
def get_sheets_client():
    """Cliente com as permissões MÍNIMAS (config.SCOPES)."""
    creds_dict = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)


@st.cache_resource(ttl=600)
def get_sheets_client_amplo():
    """Cliente com o escopo antigo (config.SCOPES_AMPLOS). Só é criado se o Google recusar o mínimo."""
    creds_dict = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES_AMPLOS)
    return gspread.authorize(creds)


def _erro_de_escopo(exc: BaseException) -> bool:
    """True se o Google recusou por FALTA DE PERMISSÃO DO TOKEN (escopo), e não por outro motivo."""
    codigo = getattr(exc, "code", None)
    if codigo is None:
        codigo = getattr(getattr(exc, "response", None), "status_code", None)
    texto = str(exc).lower()
    return codigo == 403 and ("scope" in texto or "insufficient" in texto)


def _abrir_planilha(nome, cliente_minimo, obter_cliente_amplo):
    """
    Abre a planilha pelo nome com o cliente de permissões mínimas. Se o Google recusar por
    escopo insuficiente, tenta UMA vez com o cliente amplo (o app nunca fica fora do ar por
    causa da redução de permissões) e registra um aviso no log. Qualquer outro erro sobe igual.
    """
    try:
        return cliente_minimo.open(nome)
    except gspread.exceptions.APIError as e:
        if not _erro_de_escopo(e):
            raise
        _LOG.warning("O Google recusou o escopo mínimo ao abrir a planilha; usando o escopo amplo "
                     "(drive). Detalhe: %r", e)
        return obter_cliente_amplo().open(nome)


@st.cache_resource(ttl=600)
def get_workbook():
    return _abrir_planilha(st.secrets["SHEET_NAME"], get_sheets_client(), get_sheets_client_amplo)


# ── Diagnóstico: mais de uma planilha com o mesmo nome? ─────────────────────────────────
# O app abre a planilha pelo NOME (SHEET_NAME). Se a conta de serviço enxergar duas com o
# mesmo nome, o Google devolve uma delas e a escolha pode mudar sozinha. Isto só OLHA (lê
# metadados dos arquivos) e avisa; não altera nada e não escolhe por você.

def _data_br(rfc3339) -> str:
    """'2026-06-13T14:22:10.123Z' -> '13/06/2026' ('?' se não der para ler)."""
    t = str(rfc3339 or "")[:10]
    try:
        ano, mes, dia = t.split("-")
        return f"{int(dia):02d}/{int(mes):02d}/{int(ano):04d}"
    except ValueError:
        return "?"


def analisar_planilhas_homonimas(arquivos, nome, id_em_uso="") -> dict:
    """
    `arquivos`: lista de dicts do Drive (id, name, createdTime, modifiedTime).
    Considera só as de nome IGUAL a `nome` (a mesma regra do `gspread.open`).
    Devolve {"ambigua": bool, "itens": [{"id", "criada", "alterada", "em_uso"}...]},
    com a mais recentemente alterada primeiro.
    """
    iguais = [a for a in (arquivos or []) if isinstance(a, dict) and a.get("name") == nome and a.get("id")]
    iguais.sort(key=lambda a: str(a.get("modifiedTime") or ""), reverse=True)
    itens = [{
        "id": str(a["id"]),
        "criada": _data_br(a.get("createdTime")),
        "alterada": _data_br(a.get("modifiedTime")),
        "em_uso": str(a["id"]) == str(id_em_uso),
    } for a in iguais]
    return {"ambigua": len(itens) > 1, "itens": itens}


def _md_texto(texto) -> str:
    """Escapa o texto para o markdown do Streamlit."""
    t = str(texto)
    for ch in ("\\", "$", "*", "_", "`", "[", "]", "~", ":", "<", ">"):
        t = t.replace(ch, "\\" + ch)
    return t


def texto_aviso_planilhas(diag: dict, nome: str) -> str:
    """Texto (markdown) do aviso mostrado no app quando há planilhas com o mesmo nome."""
    linhas = [
        f"**Atenção:** há {len(diag['itens'])} planilhas chamadas “{_md_texto(nome)}” compartilhadas com o app. "
        "Ele usa **uma só** e a escolha pode mudar sozinha, o que faria os dados parecerem sumir. "
        "Abra cada uma abaixo e **renomeie ou deixe de compartilhar** as que não são a certa."
    ]
    for it in diag["itens"]:
        marca = " ← **em uso agora**" if it["em_uso"] else ""
        linhas.append(
            f"- [Abrir planilha](https://docs.google.com/spreadsheets/d/{it['id']}) · "
            f"criada em {it['criada']} · última alteração em {it['alterada']}{marca}"
        )
    return "\n".join(linhas)


def _listar_planilhas(nome):
    """Lista as planilhas de nome `nome`; mesmo plano B do `_abrir_planilha` se o escopo for recusado
    (senão o diagnóstico ficaria calado justamente quando a permissão reduzida não valeu)."""
    try:
        return get_sheets_client().list_spreadsheet_files(title=nome)
    except gspread.exceptions.APIError as e:
        if not _erro_de_escopo(e):
            raise
        return get_sheets_client_amplo().list_spreadsheet_files(title=nome)


@st.cache_data(ttl=600)
def diagnostico_planilha() -> dict:
    """
    Resultado cacheado por 10 min. NUNCA levanta erro (o diagnóstico não pode derrubar o app):
    se algo falhar, devolve "sem aviso" e registra no log.
    """
    vazio = {"ambigua": False, "itens": [], "nome": ""}
    try:
        nome = st.secrets["SHEET_NAME"]
        arquivos = _listar_planilhas(nome)
        resultado = analisar_planilhas_homonimas(arquivos, nome, get_workbook().id)
        resultado["nome"] = nome
        return resultado
    except Exception as e:
        _LOG.warning("Diagnóstico de planilhas não pôde ser feito: %r", e)
        return vazio


def _migrar_headers_se_preciso(ws, nome: str):
    """Garante que a planilha tenha todas as colunas esperadas, sem desalinhar dados existentes."""
    esperados = EXPECTED_HEADERS.get(nome)
    if not esperados:
        return
    atuais = ws.row_values(1)
    if not atuais:
        return
    faltando = [h for h in esperados if h not in atuais]
    if faltando:
        novos_headers = atuais + faltando
        ws.update('A1', [novos_headers])


def get_sheet(name: str):
    from datetime import datetime  # import local para evitar custo em quem só lê planilhas existentes
    wb = get_workbook()
    try:
        ws = wb.worksheet(name)
        _migrar_headers_se_preciso(ws, name)
        return ws
    except gspread.WorksheetNotFound:
        ws = wb.add_worksheet(title=name, rows=1000, cols=20)
        if name in EXPECTED_HEADERS:
            ws.append_row(EXPECTED_HEADERS[name])
        if name == "cartoes":
            default_cards = [
                [1, "Nubank",    5000,  5, 12, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
                [2, "Itaú",      5000, 10, 17, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
                [3, "Bradesco",  5000, 15, 22, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
                [4, "Inter",     5000, 20, 27, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
                [5, "Santander", 5000, 25,  2, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
                [6, "Outro",     5000, 10, 17, datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
            ]
            ws.append_rows(default_cards)
        return ws


def sheet_to_df(ws) -> pd.DataFrame:
    # value_render_option="UNFORMATTED_VALUE": pede ao Sheets o número BRUTO
    # da célula, não o texto formatado pela interface (que segue o locale
    # pt-BR da planilha, ex. 1.5 exibido como "1,5"). Sem isso, o gspread
    # tenta converter esse texto formatado em número usando uma lógica que
    # assume o padrão americano (vírgula = separador de milhar) e acaba
    # apagando a vírgula decimal brasileira: "1,5" -> "15" -> 15 (em vez de
    # 1.5). Bug descoberto em produção: uma despesa de R$ 1,50 foi salva
    # corretamente, mas ao ser recarregada aparecia como R$ 15,00 — porque
    # nenhum valor testado antes tinha centavos (todos eram "redondos", sem
    # vírgula nenhuma para o gspread confundir).
    data = ws.get_all_records(value_render_option="UNFORMATTED_VALUE")
    df = pd.DataFrame(data) if data else pd.DataFrame()
    name = ws.title
    if name in EXPECTED_HEADERS:
        for col in EXPECTED_HEADERS[name]:
            if col not in df.columns:
                df[col] = ""
    return df


def next_id(ws) -> int:
    df = sheet_to_df(ws)
    if df.empty or "id" not in df.columns or df["id"].astype(str).str.strip().eq("").all():
        return 1
    ids = pd.to_numeric(df["id"], errors='coerce').fillna(0).astype(int)
    return int(ids.max()) + 1


# ── Escrita com ID único (proteção contra uso simultâneo) ─────────────────────
#
# PROBLEMA: `next_id` lê o maior ID e soma 1. Se duas pessoas salvarem quase
# ao mesmo tempo (acesso compartilhado por casal/família), ambas leem o mesmo
# "último ID" e gravam linhas com o MESMO id — o que faz uma exclusão apagar
# os dois registros de uma vez.
#
# SOLUÇÃO: depois de gravar, conferir se o ID escolhido acabou duplicado. Em
# caso de empate, quem gravou na linha mais abaixo cede e regrava o próprio
# ID. As duas funções de decisão (`numero_linha_do_range` e
# `resolver_colisao_id`) são puras e testadas isoladamente.

def numero_linha_do_range(updated_range) -> int:
    """
    Extrai o número da primeira linha de um range devolvido pela API do
    Sheets (ex.: "despesas!A6:I6" -> 6). Devolve None se não conseguir
    interpretar — nesse caso quem chama simplesmente não faz a checagem
    de colisão, mantendo o comportamento antigo.
    """
    if not updated_range:
        return None
    texto = str(updated_range).split("!")[-1]
    inicio = texto.split(":")[0]
    digitos = "".join(ch for ch in inicio if ch.isdigit())
    return int(digitos) if digitos else None


def resolver_colisao_id(ids_coluna: list, meu_id: int, minha_linha: int) -> int:
    """
    Decide se a linha `minha_linha` precisa trocar de ID.

    `ids_coluna` é a coluna A inteira, como devolvida por `ws.col_values(1)`
    (inclui o cabeçalho na posição 0, então a linha N está no índice N-1).

    Devolve None quando não há colisão (ou quando esta linha é a primeira
    ocorrência do ID e portanto tem direito de mantê-lo). Devolve um ID novo,
    maior que todos os existentes, quando esta linha precisa ceder.
    """
    linhas_com_meu_id = [
        pos + 1 for pos, valor in enumerate(ids_coluna)
        if str(valor).strip() == str(meu_id)
    ]
    if len(linhas_com_meu_id) <= 1 or minha_linha == min(linhas_com_meu_id):
        return None
    numericos = [
        int(v) for v in ids_coluna
        if str(v).strip().lstrip("-").isdigit()
    ]
    return (max(numericos) + 1) if numericos else 1


def _corrigir_id_se_colidiu(ws, id_gravado: int, linha: int) -> int:
    """Relê a coluna de IDs e regrava o ID desta linha se ele colidiu.
    Devolve o ID final (o original ou o corrigido)."""
    if linha is None:
        return id_gravado
    try:
        novo = resolver_colisao_id(ws.col_values(1), id_gravado, linha)
    except Exception:
        return id_gravado
    if novo is None:
        return id_gravado
    ws.update_cell(linha, 1, novo)
    return novo


# ── Escrita por NOME de coluna (imune à ordem física da planilha) ─────────────
#
# PROBLEMA (descoberto em produção): `_migrar_headers_se_preciso` só ACRESCENTA
# colunas que faltam ao FINAL da planilha — nunca reordena. Se uma coluna nova
# foi pensada para ficar "no meio" da lista em EXPECTED_HEADERS (como aconteceu
# com `proxima_data_vencimento` em `emprestimos`), a ordem FÍSICA real da
# planilha diverge silenciosamente da ordem declarada no código. Uma escrita
# posicional (`ws.append_row([...])`) nesse cenário grava cada valor na coluna
# errada, corrompendo os dados sem lançar nenhum erro.
#
# As funções abaixo são o único jeito de gravar linhas neste projeto: leem a
# ordem REAL das colunas direto da planilha (`ws.row_values(1)`) e montam a
# linha a gravar de acordo com ela, não com a ordem do config.py.

def montar_linha_por_nome(cabecalho: list, valores: dict, id_valor) -> list:
    """
    Função pura: dado o cabeçalho real de uma planilha (`ws.row_values(1)`),
    um dict {nome_da_coluna: valor} e o id a usar, devolve a linha pronta
    para `ws.append_row`, na ORDEM FÍSICA REAL das colunas — não na ordem
    em que os campos foram declarados no código.

    A coluna chamada "id" recebe `id_valor`; qualquer outra coluna do
    cabeçalho ausente em `valores` recebe string vazia (nunca lança erro
    por campo faltando, para tolerar colunas que a tela atual não usa).
    """
    return [id_valor if col == "id" else valores.get(col, "") for col in cabecalho]


def append_linha_por_nome_id_unico(ws, valores: dict) -> int:
    """
    Monta e grava uma linha respeitando a ordem REAL das colunas já
    existentes na planilha, a partir de um dict {nome_da_coluna: valor}
    (sem incluir "id" — ele é gerado automaticamente). Colunas existentes
    na planilha mas ausentes em `valores` são gravadas como string vazia.

    Também aplica a mesma proteção contra ID duplicado (ver
    `resolver_colisao_id`). Devolve o id efetivamente gravado.
    """
    cabecalho = ws.row_values(1)
    id_inicial = next_id(ws)
    linha = montar_linha_por_nome(cabecalho, valores, id_inicial)
    resposta = ws.append_row(linha)
    linha_num = numero_linha_do_range((resposta or {}).get("updates", {}).get("updatedRange"))
    return _corrigir_id_se_colidiu(ws, id_inicial, linha_num)


def append_linhas_por_nome_ids_unicos(ws, lista_valores: list) -> list:
    """Versão em lote de `append_linha_por_nome_id_unico`: recebe uma lista
    de dicts {nome_da_coluna: valor} (sem "id") e devolve a lista de ids
    efetivamente gravados, na mesma ordem."""
    if not lista_valores:
        return []
    cabecalho = ws.row_values(1)
    id_base = next_id(ws)
    payload = []
    for i, valores in enumerate(lista_valores):
        payload.append(montar_linha_por_nome(cabecalho, valores, id_base + i))
    resposta = ws.append_rows(payload)
    primeira_linha = numero_linha_do_range((resposta or {}).get("updates", {}).get("updatedRange"))
    if primeira_linha is None:
        return [id_base + i for i in range(len(payload))]
    return [
        _corrigir_id_se_colidiu(ws, id_base + i, primeira_linha + i)
        for i in range(len(payload))
    ]


def delete_rows_batch(ws, indices):
    """Deleta várias linhas do Google Sheets em uma única requisição em lote."""
    if not indices:
        return
    sorted_indices = sorted(indices, reverse=True)
    sheet_id = ws.id
    requests = []
    for idx in sorted_indices:
        row_num = idx + 1
        requests.append({
            "deleteDimension": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "ROWS",
                    "startIndex": row_num,
                    "endIndex": row_num + 1
                }
            }
        })
    ws.spreadsheet.batch_update({"requests": requests})
