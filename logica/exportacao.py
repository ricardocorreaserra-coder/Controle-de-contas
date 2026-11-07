"""
R-02 · Exportação do panorama de planejamento em Excel e CSV.
"""

import io
import re

import pandas as pd

from utils.datas import fmt_mes_str_pt


# Texto que o Excel/LibreOffice interpretaria como FÓRMULA ao abrir o arquivo (injeção de
# fórmula): começa com = + - @ (ou tab/enter). Ex.: uma descrição "=HYPERLINK(...)".
_GATILHOS_FORMULA = ("=", "+", "-", "@", "\t", "\r", "\n")
# ...exceto quando é só um número/valor: "-12,50", "+3%", "-R$ 9.719,98".
_PARECE_NUMERO = re.compile(r"^[+-]?\s*(R\$\s*)?[\d.,]+\s*%?$")


def neutralizar_formula(valor):
    """
    Se `valor` é texto que viraria fórmula numa planilha, devolve o texto com um apóstrofo na
    frente (fica visível como texto, e não executa). Números, datas e texto comum voltam iguais.
    """
    if not isinstance(valor, str) or not valor.strip():
        return valor
    if valor.lstrip()[0] in _GATILHOS_FORMULA and not _PARECE_NUMERO.match(valor.strip()):
        return "'" + valor
    return valor


def _seguro(df: pd.DataFrame) -> pd.DataFrame:
    """Cópia do DataFrame com todo texto neutralizado contra injeção de fórmula."""
    return df.map(neutralizar_formula)


def _df_resumo_export(df_resumo: pd.DataFrame) -> pd.DataFrame:
    """Prepara o df_resumo para exportação (sem a coluna interna 'mes')."""
    return _seguro(df_resumo[["Mês", "Receitas", "Cartão", "Recorrentes",
                              "Outras desp.", "Despesas (total)", "Saldo projetado"]].copy())


def _df_detalhes_export(df_linhas: pd.DataFrame) -> pd.DataFrame:
    """Prepara df_linhas para exportação com cabeçalhos amigáveis."""
    det = df_linhas[["mes", "tipo", "origem", "descricao", "categoria", "valor"]].copy()
    det.columns = ["Mês", "Tipo", "Origem", "Descrição", "Categoria", "Valor (R$)"]
    det["Mês"] = det["Mês"].apply(fmt_mes_str_pt)
    return _seguro(det)


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
