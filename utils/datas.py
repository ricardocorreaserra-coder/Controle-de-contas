"""
Funções auxiliares de manipulação de datas e meses, incluindo o widget
de seleção de mês/ano usado em várias abas.
"""

import calendar
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import streamlit as st

from config import MESES_PT


MESES_COMPLETOS = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho",
    7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}


def deslocar_mes(ano: int, mes: int, delta: int) -> tuple:
    """(ano, mes) deslocado `delta` meses (negativo = para trás). Ex.: (2026, 1, -1) → (2025, 12)."""
    total = ano * 12 + (mes - 1) + delta
    return total // 12, total % 12 + 1


def fmt_mes_pt(dt: date) -> str:
    return f"{MESES_PT[dt.month]}/{str(dt.year)[2:]}"


def fmt_mes_str_pt(mes_str: str) -> str:
    """Converte 'YYYY-MM' em 'Mmm/AA'."""
    try:
        ano, mes = mes_str.split("-")
        return f"{MESES_PT[int(mes)]}/{ano[2:]}"
    except Exception:
        return mes_str


def add_months(dt: date, months: int) -> date:
    m = dt.month - 1 + months
    year = dt.year + m // 12
    month = m % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


# Horário de Brasília com offset fixo UTC-3 (o Brasil não tem horário de verão
# desde 2019). O servidor do Streamlit Cloud roda em UTC: `date.today()` dele
# vira o dia seguinte entre ~21h e 24h no Brasil. Por isso TODA decisão "que dia
# é hoje?" do app deve usar `hoje_br()` / `agora_br()`, nunca `date.today()`.
_FUSO_BR = timezone(timedelta(hours=-3))


def agora_br() -> datetime:
    """Data e hora atuais em Brasília (UTC-3 fixo)."""
    return datetime.now(_FUSO_BR)


def hoje_br() -> date:
    """Data de hoje em Brasília (UTC-3 fixo)."""
    return agora_br().date()


def hoje_str():
    return hoje_br().strftime("%Y-%m-%d")


def data_iso(v) -> str:
    """
    Normaliza uma data lida da planilha para 'YYYY-MM-DD'. Aceita texto ISO,
    'DD/MM/YYYY' e o número serial do Google Sheets (ex.: 25569 = 01/01/1970),
    que aparece quando a célula foi convertida em data pelo próprio Sheets
    (ex.: editada manualmente direto na interface do Google Sheets).

    Se não reconhecer o formato, devolve o texto original; se vazio, devolve "".
    """
    if v is None:
        return ""
    t = str(v).strip()
    if not t or t.lower() in ("nan", "none", "nat"):
        return ""
    try:
        n = float(t.replace(",", "."))
        if 20000 < n < 80000:  # número serial de data do Sheets
            return (date(1899, 12, 30) + timedelta(days=int(n))).isoformat()
    except ValueError:
        pass
    if len(t) >= 10 and t[4] == "-" and t[7] == "-":
        return t[:10]
    if "/" in t:
        dt = pd.to_datetime(t, dayfirst=True, errors="coerce")
        if not pd.isna(dt):
            return dt.date().isoformat()
    return t


def seletor_mes_ano(key_prefix: str):
    """Renderiza seletores de ano e mês lado a lado de forma amigável."""
    hoje = hoje_br()
    anos = [hoje.year - i for i in range(5)]
    c1, c2 = st.columns(2)
    ano = c1.selectbox("Ano", anos, index=0, key=f"{key_prefix}_ano")
    # O mês padrão vai pelo session_state (e não por index=) para que a barra de
    # período (utils/widgets.py::barra_periodo) possa mudar o valor sem o aviso
    # "widget criado com valor padrão e alterado pela Session State API".
    k_mes = f"{key_prefix}_mes"
    if k_mes not in st.session_state:
        st.session_state[k_mes] = hoje.month
    mes = c2.selectbox("Mês", list(MESES_PT.keys()),
                       format_func=lambda x: MESES_PT[x], key=k_mes)
    return f"{ano}-{mes:02d}"


def proximos_12_meses() -> list:
    """Retorna ['YYYY-MM', ...] para os 12 meses a partir do mês seguinte ao atual."""
    hoje = hoje_br()
    base = date(hoje.year, hoje.month, 1)
    return [add_months(base, i).strftime("%Y-%m") for i in range(1, 13)]


def mes_ativo_recorrencia(mes: str, data_inicio: date, data_fim) -> bool:
    """Verifica se um lançamento recorrente está ativo em determinado mês (YYYY-MM)."""
    if mes < data_inicio.strftime("%Y-%m"):
        return False
    fim_str = str(data_fim).strip() if data_fim not in (None, "") else ""
    if fim_str:
        fim_mes = fim_str[:7]
        if mes > fim_mes:
            return False
    return True
