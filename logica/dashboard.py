"""
Contas do resumo mensal do Dashboard (cartões de Receitas, Despesas e Saldo).

Função pura (sem Streamlit/Sheets), testada em tests/test_resumo_dashboard.py.
Regras mantidas do Dashboard anterior:
  • "Despesas do mês" = só despesas PAGAS (status pendente fica de fora — B-04);
  • o Saldo do mês = receitas − despesas pagas;
  • despesa sem status (lançada antes do campo existir) conta como paga.
Novidade: `a_pagar` = despesas PENDENTES com data no mês, mostradas à parte.
"""

import pandas as pd

from logica.despesas import despesa_esta_pendente


def _do_mes(df, mes: str) -> pd.DataFrame:
    """Linhas do mês `YYYY-MM`, com `valor` numérico (inválido vira 0). Não altera `df`."""
    if df is None or df.empty or "data" not in df.columns or "valor" not in df.columns:
        return pd.DataFrame({"valor": pd.Series(dtype=float)})
    d = df.copy()
    d["valor"] = pd.to_numeric(d["valor"], errors="coerce").fillna(0.0)
    return d[d["data"].astype(str).str.startswith(mes)]


def resumo_mes(df_despesas, df_receitas, mes: str) -> dict:
    """
    `df_despesas` deve trazer TODAS as despesas (inclusive as pendentes).
    Devolve: total_rec, n_rec, total_desp (pagas), n_desp, a_pagar, n_a_pagar,
    saldo (receitas − despesas pagas) e saldo_apos (saldo − a pagar).
    """
    rec = _do_mes(df_receitas, mes)
    desp = _do_mes(df_despesas, mes)

    if "status" in desp.columns:
        # .astype(bool): num mês SEM despesas o apply() devolve uma série vazia de
        # tipo "object", e o pandas passa a tratá-la como lista de COLUNAS (KeyError).
        pendente = desp["status"].apply(despesa_esta_pendente).astype(bool)
    else:
        pendente = pd.Series(False, index=desp.index)
    pagas, pendentes = desp[~pendente], desp[pendente]

    total_rec = float(rec["valor"].sum())
    total_desp = float(pagas["valor"].sum())
    a_pagar = float(pendentes["valor"].sum())
    saldo = total_rec - total_desp
    return {
        "total_rec": total_rec, "n_rec": int(len(rec)),
        "total_desp": total_desp, "n_desp": int(len(pagas)),
        "a_pagar": a_pagar, "n_a_pagar": int(len(pendentes)),
        "saldo": saldo, "saldo_apos": saldo - a_pagar,
    }
