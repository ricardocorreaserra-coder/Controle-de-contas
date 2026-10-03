"""
Regras de negócio relacionadas a parcelas de cartão: divisão de valores,
lançamento manual de parcelas históricas, atualização de status e baixa
de fatura em lote.
"""

import calendar
from datetime import datetime

import gspread
import pandas as pd

from config import DIA_VENCIMENTO_PADRAO
from sheets.client import get_sheet, sheet_to_df, append_linhas_por_nome_ids_unicos, delete_rows_batch
from sheets.loaders import carregar_cartoes, carregar_parcelas
from utils.datas import add_months


def valores_parcelas(valor_total: float, n_parc: int) -> list:
    """
    B-03 · Divide o valor total em n_parc parcelas, garantindo que a soma
    bata exatamente com o valor total (a última parcela absorve o resto
    do arredondamento).
    """
    base = round(valor_total / n_parc, 2)
    valores = [base] * n_parc
    diferenca = round(valor_total - base * n_parc, 2)
    valores[-1] = round(valores[-1] + diferenca, 2)
    return valores


def _garantir_coluna(ws, nome: str):
    """
    Garante que a aba tenha uma coluna com este nome no cabeçalho (linha 1).
    Se não existir, cria no fim — assim a planilha existente é migrada
    automaticamente, sem precisar editar nada à mão.
    """
    cabecalho = ws.row_values(1)
    if nome in cabecalho:
        return
    nova_col = len(cabecalho) + 1
    if nova_col > ws.col_count:
        ws.add_cols(nova_col - ws.col_count)
    ws.update_cell(1, nova_col, nome)


def salvar_parcela_manual(cartao, desc, valor_parcela, num_inicial, num_total, vencimento_inicial, obs,
                          data_compra=None):
    """
    Lança parcelas de compras anteriores ao uso do app. Como a data foi
    digitada diretamente pelo usuário (não calculada), a origem já nasce
    'manual' — não há estimativa envolvida aqui.

    data_compra (opcional, 'YYYY-MM-DD'): data em que a compra foi feita.
    Gravada em todas as parcelas lançadas, na coluna 'data_compra'.
    """
    ws_p = get_sheet("parcelas")
    if data_compra:
        _garantir_coluna(ws_p, "data_compra")
    df_c = carregar_cartoes()
    card_info     = df_c[df_c["nome"] == cartao] if not df_c.empty else pd.DataFrame()
    df_vencimento = int(card_info.iloc[0]["dia_vencimento"]) if not card_info.empty else DIA_VENCIMENTO_PADRAO
    base_date = datetime.strptime(vencimento_inicial, "%Y-%m-%d").date()
    rows = []
    for i in range(num_total - num_inicial + 1):
        venc    = add_months(base_date, i)
        max_day = calendar.monthrange(venc.year, venc.month)[1]
        venc    = venc.replace(day=min(df_vencimento, max_day))
        rows.append({
            "despesa_id": -1, "numero": num_inicial + i, "total": num_total,
            "valor": valor_parcela, "vencimento": venc.strftime("%Y-%m-%d"),
            "status": "pendente", "descricao": desc, "cartao": cartao,
            "origem_vencimento": "manual",
        })
        if data_compra:
            rows[-1]["data_compra"] = data_compra
    append_linhas_por_nome_ids_unicos(ws_p, rows)
    carregar_parcelas.clear()


def _indices_da_compra(df, idx_ref):
    """
    Devolve os índices (do DataFrame) de todas as parcelas que formam a MESMA
    compra da parcela `idx_ref`.

    - Parcela gerada por despesa: todas com o mesmo despesa_id.
    - Lançamento histórico (despesa_id == -1): parcelas com mesma descrição,
      cartão e total. Se houver números de parcela repetidos nesse conjunto
      (duas compras diferentes com a mesma descrição, p.ex. duas "Netflix"),
      separa pela sequência: as parcelas de uma compra são gravadas juntas,
      com ids consecutivos e números 1, 2, 3...
    """
    ref = df.loc[idx_ref]
    if str(ref["despesa_id"]).strip() != "-1":
        return list(df[df["despesa_id"].astype(str) == str(ref["despesa_id"])].index)

    mesma = df[
        (df["despesa_id"].astype(str).str.strip() == "-1")
        & (df["descricao"].astype(str) == str(ref["descricao"]))
        & (df["cartao"].astype(str) == str(ref["cartao"]))
        & (df["total"].astype(str) == str(ref["total"]))
    ]
    numeros = pd.to_numeric(mesma["numero"], errors="coerce")
    if not numeros.duplicated().any():
        return sorted(mesma.index)

    por_id = {}
    for i, r in mesma.iterrows():
        try:
            por_id[int(r["id"])] = (i, int(r["numero"]))
        except (ValueError, TypeError):
            continue
    id_ref, num_ref = int(ref["id"]), int(ref["numero"])
    escolhidos = [idx_ref]
    for passo in (1, -1):
        cur_id, cur_n = id_ref, num_ref
        while (cur_id + passo) in por_id and por_id[cur_id + passo][1] == cur_n + passo:
            cur_id += passo
            cur_n += passo
            escolhidos.append(por_id[cur_id][0])
    return sorted(escolhidos)


def resumo_compra_parcelas(df, pid):
    """Resumo da compra a que a parcela `pid` pertence (para exibir na tela).
    Devolve None se a parcela não existir em `df`."""
    alvo = df[df["id"].astype(str) == str(pid)]
    if alvo.empty:
        return None
    idx_ref = alvo.index[0]
    ref = df.loc[idx_ref]
    g = df.loc[_indices_da_compra(df, idx_ref)]
    nums = pd.to_numeric(g["numero"], errors="coerce")
    return {
        "manual": str(ref["despesa_id"]).strip() == "-1",
        "descricao": str(ref["descricao"]),
        "cartao": str(ref["cartao"]),
        "total": int(pd.to_numeric(ref["total"], errors="coerce")),
        "n": len(g),
        "pagas": int((g["status"] == "pago").sum()),
        "pendentes": int((g["status"] == "pendente").sum()),
        "num_min": int(nums.min()),
        "num_max": int(nums.max()),
    }


def _localizar_compra_manual(ws, pid):
    """Lê a planilha e devolve (df, idx_ref, índices_da_compra) de um lançamento
    histórico. Levanta ValueError se a parcela não existir ou não for histórica."""
    df = sheet_to_df(ws)
    alvo = df[df["id"].astype(str) == str(pid)] if not df.empty else df
    if alvo.empty:
        raise ValueError("Parcela não encontrada (ela pode ter sido excluída).")
    idx_ref = alvo.index[0]
    if str(df.loc[idx_ref, "despesa_id"]).strip() != "-1":
        raise ValueError(
            "Esta parcela veio de uma despesa. Altere ou exclua a despesa na aba Despesas."
        )
    return df, idx_ref, _indices_da_compra(df, idx_ref)


def excluir_compra_parcelas(pid):
    """Exclui TODAS as parcelas (pagas e pendentes) de um lançamento histórico.
    Devolve o nº de parcelas excluídas."""
    ws = get_sheet("parcelas")
    df, idx_ref, idxs = _localizar_compra_manual(ws, pid)
    delete_rows_batch(ws, idxs)
    carregar_parcelas.clear()
    return len(idxs)


def corrigir_total_parcelas(pid, novo_total):
    """
    Corrige a quantidade total de parcelas de um lançamento histórico.

    - Reduzir: remove as parcelas de número maior que o novo total (se alguma
      delas estiver paga, recusa — estorne antes).
    - Aumentar: cria as parcelas que faltam, mês a mês depois da última, com o
      mesmo valor, dia de vencimento, descrição, cartão e data da compra.
    Em ambos os casos o campo 'total' de todas as parcelas da compra é atualizado.
    Devolve (removidas, criadas).
    """
    novo_total = int(novo_total)
    if not (1 <= novo_total <= 48):
        raise ValueError("O total de parcelas deve estar entre 1 e 48.")

    ws = get_sheet("parcelas")
    df, idx_ref, idxs = _localizar_compra_manual(ws, pid)
    g = df.loc[idxs].copy()
    g["_n"] = pd.to_numeric(g["numero"], errors="coerce")
    num_min, num_max = int(g["_n"].min()), int(g["_n"].max())

    if novo_total < num_min:
        raise ValueError(
            f"O total não pode ser menor que a primeira parcela lançada (nº {num_min}). "
            "Para remover a compra toda, use a exclusão."
        )
    remover = g[g["_n"] > novo_total]
    if (remover["status"] == "pago").any():
        raise ValueError(
            "Há parcela(s) paga(s) entre as que seriam removidas. Estorne-as para pendente antes de reduzir o total."
        )
    manter = g[g["_n"] <= novo_total]

    # 1) atualiza o campo 'total' das parcelas que ficam
    cabecalho = ws.row_values(1)
    col_total = cabecalho.index("total") + 1
    updates = [
        {"range": gspread.utils.rowcol_to_a1(i + 2, col_total), "values": [[novo_total]]}
        for i in manter.index
    ]
    if updates:
        ws.batch_update(updates)

    removidas = criadas = 0
    if len(remover):
        # 2a) reduzir: apaga as parcelas excedentes
        delete_rows_batch(ws, list(remover.index))
        removidas = len(remover)
    elif novo_total > num_max:
        # 2b) aumentar: cria as parcelas que faltam
        ultima = g.loc[g["_n"].idxmax()]
        base = datetime.strptime(str(ultima["vencimento"])[:10], "%Y-%m-%d").date()
        data_compra = str(ultima.get("data_compra", "")).strip()
        novas = []
        for k in range(1, novo_total - num_max + 1):
            venc = add_months(base, k)
            venc = venc.replace(day=min(base.day, calendar.monthrange(venc.year, venc.month)[1]))
            linha = {
                "despesa_id": -1, "numero": num_max + k, "total": novo_total,
                "valor": float(ultima["valor"]), "vencimento": venc.strftime("%Y-%m-%d"),
                "status": "pendente", "descricao": str(ultima["descricao"]),
                "cartao": str(ultima["cartao"]), "origem_vencimento": "manual",
            }
            if data_compra and data_compra.lower() != "nan":
                linha["data_compra"] = data_compra
            novas.append(linha)
        append_linhas_por_nome_ids_unicos(ws, novas)
        criadas = len(novas)

    carregar_parcelas.clear()
    return removidas, criadas


def alterar_lancamento_parcela(pid, valor=None, descricao=None, cartao=None,
                               data_compra=None, escopo="parcela"):
    """
    Altera os dados de um lançamento de parcela já gravado.

    - escopo="parcela": altera apenas a parcela `pid`.
    - escopo="compra": altera toda a compra a que a parcela pertence.
        * descricao, cartao e data_compra: todas as parcelas da compra
          (pagas e pendentes), para a compra não se "partir" em duas.
        * valor: apenas as parcelas pendentes (pagas são histórico).

    Descrição, cartão e data da compra só podem ser alterados em lançamentos
    históricos (despesa_id == -1). Em parcelas geradas por uma despesa, esses
    dados pertencem à despesa e são ignorados aqui.

    Argumentos None significam "não alterar". Devolve o nº de parcelas
    afetadas. Levanta ValueError se algum dado for inválido.
    """
    ws = get_sheet("parcelas")
    if data_compra:
        _garantir_coluna(ws, "data_compra")
    df = sheet_to_df(ws)
    if df.empty:
        raise ValueError("Nenhuma parcela encontrada.")

    alvo = df[df["id"].astype(str) == str(pid)]
    if alvo.empty:
        raise ValueError("Parcela não encontrada (ela pode ter sido excluída).")
    ref = alvo.iloc[0]
    idx_ref = alvo.index[0]
    manual = str(ref["despesa_id"]).strip() == "-1"

    # Parcelas que formam a mesma compra
    grupo = df.loc[_indices_da_compra(df, idx_ref)]

    # ── Validações ──
    if valor is not None and not (0 < float(valor) <= 1_000_000):
        raise ValueError("Valor deve estar entre R$ 0,01 e R$ 1.000.000,00.")
    if manual and descricao is not None and not str(descricao).strip():
        raise ValueError("A descrição não pode ficar vazia.")
    if manual and data_compra:
        escopo_idx_v = grupo.index if escopo == "compra" else [idx_ref]
        menor_venc = min(str(df.loc[i, "vencimento"]) for i in escopo_idx_v)
        if str(data_compra) > menor_venc:
            raise ValueError("A data da compra não pode ser posterior ao vencimento da parcela.")

    # ── Quais linhas recebem cada campo ──
    mudancas = {}  # {índice_df: {coluna: valor_novo}}

    def _marcar(idx, coluna, novo):
        mudancas.setdefault(idx, {})[coluna] = novo

    idx_compra = list(grupo.index) if escopo == "compra" else [idx_ref]
    if manual:
        for i in idx_compra:
            if descricao is not None: _marcar(i, "descricao", str(descricao).strip())
            if cartao is not None:    _marcar(i, "cartao", cartao)
            if data_compra:           _marcar(i, "data_compra", str(data_compra))
    if valor is not None:
        if escopo == "compra":
            idx_valor = [i for i in grupo.index if str(df.loc[i, "status"]) == "pendente"]
        else:
            idx_valor = [idx_ref]
        for i in idx_valor:
            _marcar(i, "valor", round(float(valor), 2))

    if not mudancas:
        return 0

    # ── Grava, localizando as colunas pelo NOME no cabeçalho real ──
    cabecalho = ws.row_values(1)
    updates = []
    for i, campos in mudancas.items():
        for coluna, novo in campos.items():
            col_num = cabecalho.index(coluna) + 1
            updates.append({
                "range": gspread.utils.rowcol_to_a1(i + 2, col_num),
                "values": [[novo]],
            })
    ws.batch_update(updates)
    carregar_parcelas.clear()
    return len(mudancas)


def atualizar_vencimento_parcela(pid: int, nova_data):
    """
    Corrige manualmente o vencimento de uma parcela específica — por
    exemplo, quando o fechamento real da fatura acabou sendo diferente da
    estimativa automática e ainda não havia um fechamento registrado no
    momento da compra. A parcela passa a ter origem 'manual'.
    """
    ws = get_sheet("parcelas")
    df = sheet_to_df(ws)
    col_venc = df.columns.get_loc("vencimento") + 1
    tem_origem = "origem_vencimento" in df.columns
    col_origem = df.columns.get_loc("origem_vencimento") + 1 if tem_origem else None
    for idx in df[df["id"].astype(str) == str(pid)].index.tolist():
        ws.update_cell(idx + 2, col_venc, nova_data.strftime("%Y-%m-%d"))
        if col_origem:
            ws.update_cell(idx + 2, col_origem, "manual")
    carregar_parcelas.clear()


def atualizar_parcela(pid: int, status: str):
    ws = get_sheet("parcelas")
    df = sheet_to_df(ws)
    for idx in df[df["id"].astype(str) == str(pid)].index.tolist():
        ws.update_cell(idx + 2, df.columns.get_loc("status") + 1, status)
    carregar_parcelas.clear()


def baixar_fatura_mes(mes: str, cartao_filtro: str = None):
    ws   = get_sheet("parcelas")
    ws_d = get_sheet("despesas")
    df_p = sheet_to_df(ws)
    df_d = sheet_to_df(ws_d)
    if df_p.empty:
        return 0
    df_p_full = df_p.copy()
    if not df_d.empty:
        df_d_sub = df_d[["id", "cartao"]].rename(columns={"id": "despesa_id", "cartao": "cartao_dep"})
        df_p_full = df_p_full.merge(df_d_sub, on="despesa_id", how="left")
        df_p_full["cartao"] = df_p_full.apply(
            lambda r: r["cartao_dep"] if pd.notna(r.get("cartao_dep")) and r["cartao_dep"] != "" else r.get("cartao", ""),
            axis=1
        )
    mask = (df_p_full["vencimento"].astype(str).str.startswith(mes)) & \
           (df_p_full["status"] == "pendente")
    if cartao_filtro and cartao_filtro != "Todos":
        mask = mask & (df_p_full["cartao"] == cartao_filtro)
    idxs = df_p_full[mask].index.tolist()
    if not idxs:
        return 0
    col_idx    = df_p.columns.get_loc("status") + 1
    range_data = [{'range': gspread.utils.rowcol_to_a1(idx + 2, col_idx), 'values': [['pago']]} for idx in idxs]
    ws.batch_update(range_data)
    carregar_parcelas.clear()
    return len(idxs)