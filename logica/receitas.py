"""
Regras de negócio relacionadas a receitas: lançamento, exclusão e
encerramento de recorrência.
"""

from datetime import datetime

import gspread
import pandas as pd

from config import CONTAS, SEM_CONTA
from sheets.client import get_sheet, sheet_to_df, delete_rows_batch, append_linha_por_nome_id_unico
from sheets.loaders import carregar_receitas
from utils.datas import hoje_str
from utils.sessao import usuario_atual


def salvar_receita(desc, valor, data, cat, obs, recorrente=False, recorrencia_fim=None, conta=""):
    ws = get_sheet("receitas")
    append_linha_por_nome_id_unico(ws, {
        "descricao": desc, "valor": valor, "data": data,
        "categoria": cat, "observacao": obs,
        "criado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "recorrente": "sim" if recorrente else "nao",
        "recorrencia_fim": recorrencia_fim.strftime("%Y-%m-%d") if recorrencia_fim else "",
        "lancado_por": usuario_atual(),
        "conta": conta,
    })
    carregar_receitas.clear()


def excluir_receita(rid: int):
    ws = get_sheet("receitas")
    df = sheet_to_df(ws)
    if not df.empty:
        delete_rows_batch(ws, df[df["id"].astype(str) == str(rid)].index.tolist())
    carregar_receitas.clear()


def atualizar_receita(rid: int, desc: str, valor: float, data: str, cat: str, obs: str,
                      conta: str | None = None):
    """Edita descrição, valor, data, categoria, observação e (se informada)
    a conta de uma receita já lançada. Com `conta=None` a conta gravada NÃO é
    tocada. Não mexe em `recorrente`/`recorrencia_fim` — isso continua sendo
    gerenciado só pelo botão "Encerrar recorrência"."""
    ws = get_sheet("receitas")
    df = sheet_to_df(ws)
    cabecalho = ws.row_values(1)
    campos = {"descricao": desc, "valor": valor, "data": data,
              "categoria": cat, "observacao": obs}
    if conta is not None:
        campos["conta"] = conta
    updates = []
    for idx in df[df["id"].astype(str) == str(rid)].index.tolist():
        row_num = idx + 2
        for campo, v in campos.items():
            col = cabecalho.index(campo) + 1
            updates.append({"range": gspread.utils.rowcol_to_a1(row_num, col), "values": [[v]]})
    if updates:
        ws.batch_update(updates, value_input_option="RAW")
    carregar_receitas.clear()


def encerrar_recorrencia_receita(rid: int):
    ws = get_sheet("receitas")
    df = sheet_to_df(ws)
    col_idx = df.columns.get_loc("recorrencia_fim") + 1
    hoje = hoje_str()
    for idx in df[df["id"].astype(str) == str(rid)].index.tolist():
        ws.update_cell(idx + 2, col_idx, hoje)
    carregar_receitas.clear()


def entradas_por_conta(df_rec) -> list:
    """Soma as receitas por conta. Devolve [(conta, total), ...] na ordem:
    contas de `CONTAS` (todas, mesmo com R$ 0,00), depois contas antigas que não
    estão mais na lista, e por último `SEM_CONTA` (só se houver valor/linhas).
    Função pura: recebe o DataFrame de receitas já filtrado pelo período."""
    totais = {c: 0.0 for c in CONTAS}
    sem_conta = 0.0
    tem_sem_conta = False
    if df_rec is not None and not df_rec.empty and "valor" in df_rec.columns:
        valores = pd.to_numeric(df_rec["valor"], errors="coerce").fillna(0.0)
        if "conta" in df_rec.columns:
            contas = df_rec["conta"].fillna("").astype(str).str.strip()
        else:
            contas = pd.Series([""] * len(df_rec), index=df_rec.index)
        for conta, valor in zip(contas, valores):
            if not conta or conta == SEM_CONTA:
                sem_conta += float(valor)
                tem_sem_conta = True
            else:
                totais[conta] = totais.get(conta, 0.0) + float(valor)
    saida = list(totais.items())
    if tem_sem_conta:
        saida.append((SEM_CONTA, sem_conta))
    return saida
