"""
Empréstimos — aba isolada de CONSULTA E CONTROLE.

IMPORTANTE: nada aqui participa de nenhuma soma de despesas, do Dashboard
ou do Planejamento 12 Meses. Não há nenhuma função neste módulo chamada a
partir de `logica/despesas.py`, `logica/planejamento.py` ou
`paginas/dashboard.py` — e não deve haver. Esta é uma tabela própria
(`emprestimos`), com sua própria página (`paginas/emprestimos.py`),
totalmente desacoplada do resto do fluxo financeiro do app.
"""

from datetime import datetime

from sheets.client import get_sheet, sheet_to_df, next_id, delete_rows_batch
from sheets.loaders import carregar_emprestimos


# ── Função pura ────────────────────────────────────────────────────────────────

def calcular_novo_estado_apos_pagamento(parcelas_restantes: int, valor_total_devido: float,
                                         valor_parcela: float) -> tuple:
    """
    Calcula o novo estado de um empréstimo depois de registrar o pagamento
    de uma parcela: uma parcela a menos, e o valor da parcela abatido do
    total devido.

    Nunca deixa nenhum dos dois valores ficar negativo — se as parcelas já
    estiverem zeradas, ou se o valor da parcela for maior que o saldo
    restante (ex.: arredondamento na última parcela), o resultado fica em
    zero em vez de negativo.

    Retorna (nova_parcelas_restantes: int, novo_valor_total_devido: float).
    """
    nova_parcelas = max(0, int(parcelas_restantes) - 1)
    novo_valor = max(0.0, round(float(valor_total_devido) - float(valor_parcela), 2))
    return nova_parcelas, novo_valor


# ── Persistência (Google Sheets) ────────────────────────────────────────────

def salvar_emprestimo(descricao: str, banco: str, valor_parcela: float,
                       parcelas_restantes: int, valor_total_devido: float):
    ws = get_sheet("emprestimos")
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ws.append_row([next_id(ws), descricao, banco, valor_parcela,
                   parcelas_restantes, valor_total_devido, agora, agora])
    carregar_emprestimos.clear()


def atualizar_emprestimo(eid: int, descricao: str, banco: str, valor_parcela: float,
                          parcelas_restantes: int, valor_total_devido: float):
    """Edição manual completa — útil se o empréstimo for renegociado e os
    valores precisarem ser corrigidos diretamente, fora do fluxo normal de
    'registrar pagamento'."""
    ws = get_sheet("emprestimos")
    df = sheet_to_df(ws)
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for idx in df[df["id"].astype(str) == str(eid)].index.tolist():
        row_num = idx + 2
        ws.update_cell(row_num, df.columns.get_loc("descricao") + 1, descricao)
        ws.update_cell(row_num, df.columns.get_loc("banco") + 1, banco)
        ws.update_cell(row_num, df.columns.get_loc("valor_parcela") + 1, valor_parcela)
        ws.update_cell(row_num, df.columns.get_loc("parcelas_restantes") + 1, parcelas_restantes)
        ws.update_cell(row_num, df.columns.get_loc("valor_total_devido") + 1, valor_total_devido)
        ws.update_cell(row_num, df.columns.get_loc("atualizado_em") + 1, agora)
    carregar_emprestimos.clear()


def registrar_pagamento_parcela(eid: int):
    """
    Registra o pagamento de uma parcela: busca o estado atual do
    empréstimo na planilha, aplica `calcular_novo_estado_apos_pagamento`
    e grava o resultado de volta.
    """
    ws = get_sheet("emprestimos")
    df = sheet_to_df(ws)
    linhas = df[df["id"].astype(str) == str(eid)]
    if linhas.empty:
        return
    row = linhas.iloc[0]
    parcelas_atuais = int(float(row["parcelas_restantes"])) if str(row["parcelas_restantes"]).strip() else 0
    valor_devido_atual = float(row["valor_total_devido"]) if str(row["valor_total_devido"]).strip() else 0.0
    valor_parcela = float(row["valor_parcela"]) if str(row["valor_parcela"]).strip() else 0.0

    nova_parcelas, novo_valor = calcular_novo_estado_apos_pagamento(
        parcelas_atuais, valor_devido_atual, valor_parcela
    )

    idx = linhas.index[0]
    row_num = idx + 2
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ws.update_cell(row_num, df.columns.get_loc("parcelas_restantes") + 1, nova_parcelas)
    ws.update_cell(row_num, df.columns.get_loc("valor_total_devido") + 1, novo_valor)
    ws.update_cell(row_num, df.columns.get_loc("atualizado_em") + 1, agora)
    carregar_emprestimos.clear()


def excluir_emprestimo(eid: int):
    ws = get_sheet("emprestimos")
    df = sheet_to_df(ws)
    if not df.empty:
        delete_rows_batch(ws, df[df["id"].astype(str) == str(eid)].index.tolist())
    carregar_emprestimos.clear()