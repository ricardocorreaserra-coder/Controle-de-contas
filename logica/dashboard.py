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

from config import MESES_PT
from logica.despesas import despesa_esta_pendente
from utils.datas import deslocar_mes


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


def janela_meses(selecionado: str, antes: int = 3, depois: int = 2) -> list:
    """['YYYY-MM', ...]: `antes` meses antes do selecionado, ele mesmo e `depois` meses depois."""
    ano, mes = int(selecionado[:4]), int(selecionado[5:7])
    return ["{:04d}-{:02d}".format(*deslocar_mes(ano, mes, d)) for d in range(-antes, depois + 1)]


def linha_do_tempo(selecionado: str, mes_atual: str, df_despesas, planejado: dict) -> list:
    """
    Blocos da linha do tempo do Dashboard (3 meses antes do selecionado, ele e 2 depois).

    O valor de cada bloco depende de ele ser futuro em relação a HOJE (`mes_atual`),
    não de qual está selecionado:
      • mês atual ou passado → despesas PAGAS do mês (mesmo cálculo dos cartões e
        do gráfico "Histórico 6 meses");
      • mês futuro → despesas PLANEJADAS (`planejado[mes]`, vindo do Planejamento);
        sem planejado para o mês, `valor` é None (a tela mostra "—").
    O selecionado só ganha destaque (`selecionado=True`). `df_despesas` deve trazer
    todas as despesas, inclusive as pendentes.
    Devolve [{mes, rotulo, valor, planejado, selecionado}, ...].
    """
    blocos = []
    for mes in janela_meses(selecionado):
        futuro = mes > mes_atual
        if futuro:
            valor = planejado.get(mes)
            valor = None if valor is None else float(valor)
        else:
            valor = resumo_mes(df_despesas, None, mes)["total_desp"]
        ano_s, mes_n = mes[:4], int(mes[5:7])
        rotulo = MESES_PT[mes_n]
        if mes == selecionado or mes_n == 1:   # ano só onde ajuda a se situar
            rotulo += f"/{ano_s[2:]}"
        blocos.append({"mes": mes, "rotulo": rotulo, "valor": valor,
                       "planejado": futuro, "selecionado": mes == selecionado})
    return blocos


def historico_meses(df_despesas, df_receitas, mes_fim: str, n: int = 6) -> pd.DataFrame:
    """
    Receitas × despesas PAGAS dos `n` meses que terminam em `mes_fim` ('YYYY-MM').
    Colunas: "Mês" (ex.: "Out/26"), "Receita", "Despesa" — o formato que o PDF espera.
    Mesma regra dos cartões (`resumo_mes`): despesa pendente fica de fora.
    `df_despesas` deve trazer todas as despesas, inclusive as pendentes.
    """
    linhas = []
    for mes in janela_meses(mes_fim, antes=n - 1, depois=0):
        r = resumo_mes(df_despesas, df_receitas, mes)
        linhas.append({"Mês": f"{MESES_PT[int(mes[5:7])]}/{mes[2:4]}",
                       "Receita": r["total_rec"], "Despesa": r["total_desp"]})
    return pd.DataFrame(linhas, columns=["Mês", "Receita", "Despesa"])


def participacao(df, coluna: str, vazio: str = "Não informado") -> pd.DataFrame:
    """
    Quanto cada valor de `coluna` (ex.: forma de pagamento) pesa no total de `df`.
    Colunas: "Nome", "Valor", "Percentual" (0 a 100), da maior para a menor fatia.
    Texto em branco vira `vazio`. DataFrame vazio (ou sem a coluna) → resultado vazio.
    """
    colunas = ["Nome", "Valor", "Percentual"]
    if df is None or df.empty or coluna not in df.columns or "valor" not in df.columns:
        return pd.DataFrame(columns=colunas)
    d = pd.DataFrame({
        "Nome": df[coluna].fillna("").astype(str).str.strip().replace("", vazio),
        "Valor": pd.to_numeric(df["valor"], errors="coerce").fillna(0.0),
    })
    g = d.groupby("Nome", as_index=False)["Valor"].sum()
    g = g[g["Valor"] > 0].sort_values(["Valor", "Nome"], ascending=[False, True]).reset_index(drop=True)
    total = float(g["Valor"].sum())
    g["Percentual"] = g["Valor"] / total * 100 if total else 0.0
    return g[colunas]

