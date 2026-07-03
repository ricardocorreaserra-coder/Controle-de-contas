"""
R-02 · Exportação do panorama de planejamento em Excel e CSV.
"""

import io

import pandas as pd

from utils.datas import fmt_mes_str_pt


def _df_resumo_export(df_resumo: pd.DataFrame) -> pd.DataFrame:
    """Prepara o df_resumo para exportação (sem a coluna interna 'mes')."""
    return df_resumo[["Mês", "Receitas", "Cartão", "Recorrentes",
                       "Outras desp.", "Despesas (total)", "Saldo projetado"]].copy()


def _df_detalhes_export(df_linhas: pd.DataFrame) -> pd.DataFrame:
    """Prepara df_linhas para exportação com cabeçalhos amigáveis."""
    det = df_linhas[["mes", "tipo", "origem", "descricao", "categoria", "valor"]].copy()
    det.columns = ["Mês", "Tipo", "Origem", "Descrição", "Categoria", "Valor (R$)"]
    det["Mês"] = det["Mês"].apply(fmt_mes_str_pt)
    return det


def gerar_excel_panorama(df_linhas: pd.DataFrame, df_resumo: pd.DataFrame) -> bytes:
    """
    Gera um arquivo Excel (.xlsx) com duas abas:
      - 'Resumo'   → tabela agregada por mês
      - 'Detalhes' → todos os lançamentos linha a linha
    """
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        _df_resumo_export(df_resumo).to_excel(writer, sheet_name="Resumo", index=False)
        _df_detalhes_export(df_linhas).to_excel(writer, sheet_name="Detalhes", index=False)
    buf.seek(0)
    return buf.getvalue()


def gerar_csv_panorama(df_linhas: pd.DataFrame, df_resumo: pd.DataFrame) -> bytes:
    """
    Gera um CSV com BOM UTF-8 (compatível com Excel ao abrir diretamente),
    com seções de Resumo e Detalhes separadas por linha em branco.
    """
    buf = io.StringIO()
    buf.write("# RESUMO MENSAL\n")
    _df_resumo_export(df_resumo).to_csv(buf, index=False)
    buf.write("\n# DETALHES\n")
    _df_detalhes_export(df_linhas).to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8-sig")
