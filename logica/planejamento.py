"""
PROJEÇÃO DE 12 MESES (R-01) e persistência de lançamentos manuais de
planejamento.

Cada função `_projetar_*` é responsável por uma única fonte de dados,
tornando o código testável de forma isolada e fácil de estender com
novas fontes.

R-03 · O panorama consolidado é cacheado em `st.session_state` (não em
`st.cache_data`) porque depende da combinação de várias funções já
cacheadas individualmente e precisa de um botão de atualização manual
explícito — ver `get_panorama` / `invalidar_cache_panorama` abaixo.
"""

from datetime import datetime

import pandas as pd
import streamlit as st

from sheets.client import (
    get_sheet, sheet_to_df, delete_rows_batch,
    append_row_id_unico, append_rows_ids_unicos,
)
from sheets.loaders import carregar_despesas, carregar_receitas, carregar_parcelas, carregar_planejamento
from utils.datas import fmt_mes_str_pt, mes_ativo_recorrencia, proximos_12_meses
from utils.sessao import usuario_atual

_COLS_LINHAS = ["mes", "tipo", "origem", "descricao", "valor", "categoria"]


def _projetar_parcelas_cartao(df_p: pd.DataFrame, meses: list) -> list:
    """Fonte 1: parcelas de cartão pendentes com vencimento nos próximos 12 meses."""
    linhas = []
    if df_p.empty:
        return linhas
    meses_set = set(meses)
    df_pend = df_p[df_p["status"] == "pendente"].copy()
    df_pend["valor"] = pd.to_numeric(df_pend["valor"], errors="coerce").fillna(0.0)
    for _, row in df_pend.iterrows():
        mes = str(row["vencimento"])[:7]
        if mes in meses_set:
            linhas.append({
                "mes": mes, "tipo": "despesa", "origem": "Cartão",
                "descricao": str(row.get("descricao", "")),
                "valor": float(row["valor"]), "categoria": "Cartão de crédito",
            })
    return linhas


def _projetar_despesas(df_d: pd.DataFrame, meses: list) -> list:
    """
    Fonte 2: despesas recorrentes (não-cartão) e despesas avulsas com data futura.
    Despesas de cartão são excluídas — já entram via _projetar_parcelas_cartao,
    evitando contagem dupla.
    """
    linhas = []
    if df_d.empty:
        return linhas
    meses_set = set(meses)
    df_d2 = df_d.copy()
    df_d2["valor"] = pd.to_numeric(df_d2["valor"], errors="coerce").fillna(0.0)
    is_recorrente = df_d2.get("recorrente", "").astype(str).str.lower() == "sim"
    nao_cartao    = df_d2["pagamento"] != "Cartão de crédito"

    for _, row in df_d2[is_recorrente & nao_cartao].iterrows():
        try:
            data_ini = datetime.strptime(str(row["data"]), "%Y-%m-%d").date()
        except Exception:
            continue
        for mes in meses:
            if mes_ativo_recorrencia(mes, data_ini, row.get("recorrencia_fim")):
                linhas.append({
                    "mes": mes, "tipo": "despesa", "origem": "Recorrente",
                    "descricao": str(row["descricao"]), "valor": float(row["valor"]),
                    "categoria": str(row.get("categoria", "")),
                })

    avulsas = df_d2[(~is_recorrente) & nao_cartao &
                    (df_d2["data"].astype(str).str.slice(0, 7).isin(meses_set))]
    for _, row in avulsas.iterrows():
        linhas.append({
            "mes": str(row["data"])[:7], "tipo": "despesa", "origem": "Avulsa futura",
            "descricao": str(row["descricao"]), "valor": float(row["valor"]),
            "categoria": str(row.get("categoria", "")),
        })
    return linhas


def _projetar_receitas(df_r: pd.DataFrame, meses: list) -> list:
    """Fonte 3: receitas recorrentes e receitas avulsas com data futura."""
    linhas = []
    if df_r.empty:
        return linhas
    meses_set = set(meses)
    df_r2 = df_r.copy()
    df_r2["valor"] = pd.to_numeric(df_r2["valor"], errors="coerce").fillna(0.0)
    is_recorrente_r = df_r2.get("recorrente", "").astype(str).str.lower() == "sim"

    for _, row in df_r2[is_recorrente_r].iterrows():
        try:
            data_ini = datetime.strptime(str(row["data"]), "%Y-%m-%d").date()
        except Exception:
            continue
        for mes in meses:
            if mes_ativo_recorrencia(mes, data_ini, row.get("recorrencia_fim")):
                linhas.append({
                    "mes": mes, "tipo": "receita", "origem": "Recorrente",
                    "descricao": str(row["descricao"]), "valor": float(row["valor"]),
                    "categoria": str(row.get("categoria", "")),
                })

    avulsas_r = df_r2[(~is_recorrente_r) &
                      (df_r2["data"].astype(str).str.slice(0, 7).isin(meses_set))]
    for _, row in avulsas_r.iterrows():
        linhas.append({
            "mes": str(row["data"])[:7], "tipo": "receita", "origem": "Avulsa futura",
            "descricao": str(row["descricao"]), "valor": float(row["valor"]),
            "categoria": str(row.get("categoria", "")),
        })
    return linhas


def _projetar_planejamento(df_pl: pd.DataFrame, meses: list) -> list:
    """Fonte 4: lançamentos manuais da planilha 'planejamento'."""
    linhas = []
    if df_pl.empty:
        return linhas
    meses_set = set(meses)
    df_pl2 = df_pl.copy()
    df_pl2["valor"] = pd.to_numeric(df_pl2["valor"], errors="coerce").fillna(0.0)
    for _, row in df_pl2[df_pl2["mes"].astype(str).isin(meses_set)].iterrows():
        linhas.append({
            "mes": str(row["mes"]), "tipo": str(row["tipo"]),
            "origem": "Planejamento manual",
            "descricao": str(row["descricao"]), "valor": float(row["valor"]),
            "categoria": str(row.get("categoria", "")),
        })
    return linhas


def _consolidar_resumo(df_linhas: pd.DataFrame, meses: list) -> pd.DataFrame:
    """Agrega df_linhas por mês gerando a tabela resumo (para exibição e exportação)."""
    resumo_rows = []
    for mes in meses:
        sub = df_linhas[df_linhas["mes"] == mes]
        receitas    = float(sub[sub["tipo"] == "receita"]["valor"].sum())
        desp_cartao = float(sub[(sub["tipo"] == "despesa") & (sub["origem"] == "Cartão")]["valor"].sum())
        desp_recor  = float(sub[(sub["tipo"] == "despesa") & (sub["origem"] == "Recorrente")]["valor"].sum())
        desp_outras = float(sub[(sub["tipo"] == "despesa") &
                                (~sub["origem"].isin(["Cartão", "Recorrente"]))]["valor"].sum())
        despesas_tot = desp_cartao + desp_recor + desp_outras
        resumo_rows.append({
            "mes": mes, "Mês": fmt_mes_str_pt(mes),
            "Receitas": receitas, "Cartão": desp_cartao, "Recorrentes": desp_recor,
            "Outras desp.": desp_outras, "Despesas (total)": despesas_tot,
            "Saldo projetado": receitas - despesas_tot,
        })
    return pd.DataFrame(resumo_rows)


def _computar_panorama() -> tuple:
    """
    Orquestra as 4 fontes e retorna (df_linhas, df_resumo).
    Função pura — sem cache próprio; o cache é gerenciado por get_panorama().
    """
    meses = proximos_12_meses()
    linhas = (
        _projetar_parcelas_cartao(carregar_parcelas(), meses)
        + _projetar_despesas(carregar_despesas(), meses)
        + _projetar_receitas(carregar_receitas(), meses)
        + _projetar_planejamento(carregar_planejamento(), meses)
    )
    df_linhas = pd.DataFrame(linhas, columns=_COLS_LINHAS) if linhas else pd.DataFrame(columns=_COLS_LINHAS)
    df_resumo = _consolidar_resumo(df_linhas, meses)
    return df_linhas, df_resumo


# ── Cache de panorama via session_state (R-03) ────────────────────────────────

def get_panorama() -> tuple:
    """
    Retorna (df_linhas, df_resumo) do cache em session_state.
    Recomputa automaticamente se o cache não existir (primeira carga ou após
    invalidação explícita via botão 'Atualizar projeções').
    """
    if "panorama_cache" not in st.session_state:
        df_linhas, df_resumo = _computar_panorama()
        st.session_state["panorama_cache"] = {
            "df_linhas": df_linhas,
            "df_resumo": df_resumo,
            "ts": datetime.now(),
        }
    c = st.session_state["panorama_cache"]
    return c["df_linhas"], c["df_resumo"]


def _ts_panorama() -> str:
    """Retorna a hora da última computação do panorama, ou '—' se não calculado."""
    c = st.session_state.get("panorama_cache")
    return c["ts"].strftime("%H:%M:%S") if c else "—"


def invalidar_cache_panorama():
    """
    Descarta o panorama armazenado em session_state e limpa os caches das
    funções de carregamento, forçando releitura completa do Sheets na próxima
    chamada a get_panorama(). Deve ser chamada após qualquer escrita que
    afete o planejamento.
    """
    st.session_state.pop("panorama_cache", None)
    carregar_parcelas.clear()
    carregar_despesas.clear()
    carregar_receitas.clear()
    carregar_planejamento.clear()


# ── Persistência de lançamentos manuais de planejamento ───────────────────────

def salvar_planejamento(tipo, desc, valor, mes, cat, obs):
    ws = get_sheet("planejamento")
    append_row_id_unico(ws, [tipo, desc, valor, mes, cat, obs,
                             datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                             usuario_atual()])
    carregar_planejamento.clear()


def salvar_planejamento_replicado(tipo, desc, valor, meses, cat, obs):
    ws = get_sheet("planejamento")
    rows = []
    autor = usuario_atual()
    for mes in meses:
        rows.append([tipo, desc, valor, mes, cat, obs,
                     datetime.now().strftime("%Y-%m-%d %H:%M:%S"), autor])
    append_rows_ids_unicos(ws, rows)
    carregar_planejamento.clear()


def excluir_planejamento(pid: int):
    ws = get_sheet("planejamento")
    df = sheet_to_df(ws)
    if not df.empty:
        delete_rows_batch(ws, df[df["id"].astype(str) == str(pid)].index.tolist())
    carregar_planejamento.clear()
