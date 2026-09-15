"""
Empréstimos — aba isolada de CONSULTA E CONTROLE.

IMPORTANTE: nada aqui participa de nenhuma soma de despesas, do Dashboard
ou do Planejamento 12 Meses. A tabela `emprestimos` é lida exclusivamente
por este módulo e por `paginas/emprestimos.py`.

REGRAS DE NEGÓCIO (adaptadas a pedido do usuário):
  1) `valor_total_devido` NUNCA é digitado manualmente — é sempre o
     produto de `valor_parcela` × `parcelas_restantes`. Ver
     `calcular_valor_total_devido`.
  2) A baixa das parcelas é AUTOMÁTICA, baseada na data de vencimento
     informada no cadastro (`proxima_data_vencimento`): toda vez que a
     aba é aberta, `sincronizar_baixas_automaticas` compara essa data com
     a data de hoje e dá baixa em todas as parcelas cujo vencimento já
     passou — sem precisar de nenhum clique manual. Ver
     `processar_baixas_automaticas`.
"""

from datetime import date, datetime

from sheets.client import get_sheet, sheet_to_df, delete_rows_batch, append_row_id_unico
from sheets.loaders import carregar_emprestimos
from utils.datas import add_months
from utils.sessao import usuario_atual


# ── Funções puras ────────────────────────────────────────────────────────────

def calcular_valor_total_devido(valor_parcela: float, parcelas_restantes: int) -> float:
    """
    O valor total do débito é sempre o produto do valor da parcela pela
    quantidade de parcelas restantes — nunca um valor digitado
    manualmente. Isso garante que os dois números nunca fiquem
    inconsistentes entre si.
    """
    parcelas = max(0, int(parcelas_restantes))
    return round(float(valor_parcela) * parcelas, 2)


def processar_baixas_automaticas(parcelas_restantes: int, valor_parcela: float,
                                  proxima_data_vencimento: date, hoje: date) -> dict:
    """
    Dá baixa automaticamente em todas as parcelas cujo vencimento já
    passou (ou é hoje), uma de cada vez, avançando a data de vencimento em
    um mês a cada baixa aplicada — até a próxima parcela vencer no futuro
    ou as parcelas acabarem.

    Isso cobre o caso de o app ficar dias ou meses sem ser aberto: todas
    as parcelas que já venceram nesse intervalo são baixadas de uma vez,
    não só a mais recente.

    Retorna um dict com:
      - parcelas_restantes (int, já atualizado)
      - valor_total_devido (float, recalculado via calcular_valor_total_devido)
      - proxima_data_vencimento (date, avançada a cada baixa aplicada)
      - parcelas_baixadas (int — 0 se nenhuma baixa foi necessária)
    """
    parcelas = max(0, int(parcelas_restantes))
    vencimento = proxima_data_vencimento
    baixas = 0
    while parcelas > 0 and vencimento <= hoje:
        parcelas -= 1
        vencimento = add_months(vencimento, 1)
        baixas += 1
    return {
        "parcelas_restantes": parcelas,
        "valor_total_devido": calcular_valor_total_devido(valor_parcela, parcelas),
        "proxima_data_vencimento": vencimento,
        "parcelas_baixadas": baixas,
    }


# ── Persistência (Google Sheets) ────────────────────────────────────────────

def salvar_emprestimo(descricao: str, banco: str, valor_parcela: float,
                       parcelas_restantes: int, proxima_data_vencimento: date):
    ws = get_sheet("emprestimos")
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    valor_total = calcular_valor_total_devido(valor_parcela, parcelas_restantes)
    append_row_id_unico(ws, [
        descricao, banco, valor_parcela, parcelas_restantes,
        proxima_data_vencimento.strftime("%Y-%m-%d"), valor_total, agora, agora,
        usuario_atual(),
    ])
    carregar_emprestimos.clear()


def atualizar_emprestimo(eid: int, descricao: str, banco: str, valor_parcela: float,
                          parcelas_restantes: int, proxima_data_vencimento: date):
    """Edição manual completa — útil para corrigir um cadastro feito com
    valores errados, já que a baixa em si é automática e não há mais um
    botão de 'registrar pagamento' para compensar erros de digitação."""
    ws = get_sheet("emprestimos")
    df = sheet_to_df(ws)
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    valor_total = calcular_valor_total_devido(valor_parcela, parcelas_restantes)
    for idx in df[df["id"].astype(str) == str(eid)].index.tolist():
        row_num = idx + 2
        ws.update_cell(row_num, df.columns.get_loc("descricao") + 1, descricao)
        ws.update_cell(row_num, df.columns.get_loc("banco") + 1, banco)
        ws.update_cell(row_num, df.columns.get_loc("valor_parcela") + 1, valor_parcela)
        ws.update_cell(row_num, df.columns.get_loc("parcelas_restantes") + 1, parcelas_restantes)
        ws.update_cell(row_num, df.columns.get_loc("proxima_data_vencimento") + 1,
                       proxima_data_vencimento.strftime("%Y-%m-%d"))
        ws.update_cell(row_num, df.columns.get_loc("valor_total_devido") + 1, valor_total)
        ws.update_cell(row_num, df.columns.get_loc("atualizado_em") + 1, agora)
    carregar_emprestimos.clear()


def excluir_emprestimo(eid: int):
    ws = get_sheet("emprestimos")
    df = sheet_to_df(ws)
    if not df.empty:
        delete_rows_batch(ws, df[df["id"].astype(str) == str(eid)].index.tolist())
    carregar_emprestimos.clear()


def sincronizar_baixas_automaticas() -> list:
    """
    Percorre todos os empréstimos com parcelas pendentes e aplica
    `processar_baixas_automaticas` a cada um, comparando com a data de
    hoje. Persiste na planilha qualquer mudança detectada.

    Deve ser chamada uma vez no topo de `paginas/emprestimos.py::render()`
    — assim, toda vez que a aba é aberta, o estado reflete automaticamente
    quaisquer parcelas vencidas desde a última visita, sem nenhum clique
    manual.

    Retorna a lista de empréstimos que tiveram baixa aplicada nesta
    chamada (lista vazia se nada mudou), para exibir uma mensagem
    informativa na tela.
    """
    ws = get_sheet("emprestimos")
    df = sheet_to_df(ws)
    if df.empty:
        return []

    hoje = date.today()
    atualizados = []

    for idx, row in df.iterrows():
        parcelas_atuais = int(float(row["parcelas_restantes"])) if str(row["parcelas_restantes"]).strip() else 0
        if parcelas_atuais <= 0:
            continue
        valor_parcela = float(row["valor_parcela"]) if str(row["valor_parcela"]).strip() else 0.0
        try:
            venc_atual = datetime.strptime(str(row["proxima_data_vencimento"]), "%Y-%m-%d").date()
        except Exception:
            continue  # sem data válida cadastrada — não há como calcular baixa automática

        resultado = processar_baixas_automaticas(parcelas_atuais, valor_parcela, venc_atual, hoje)
        if resultado["parcelas_baixadas"] > 0:
            row_num = idx + 2
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ws.update_cell(row_num, df.columns.get_loc("parcelas_restantes") + 1, resultado["parcelas_restantes"])
            ws.update_cell(row_num, df.columns.get_loc("valor_total_devido") + 1, resultado["valor_total_devido"])
            ws.update_cell(row_num, df.columns.get_loc("proxima_data_vencimento") + 1,
                           resultado["proxima_data_vencimento"].strftime("%Y-%m-%d"))
            ws.update_cell(row_num, df.columns.get_loc("atualizado_em") + 1, agora)
            atualizados.append({
                "descricao": row["descricao"],
                "banco": row["banco"],
                "parcelas_baixadas": resultado["parcelas_baixadas"],
                "parcelas_restantes": resultado["parcelas_restantes"],
            })

    if atualizados:
        carregar_emprestimos.clear()
    return atualizados
