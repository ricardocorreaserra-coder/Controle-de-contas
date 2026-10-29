"""
Testes dos gráficos do Dashboard: histórico de 6 meses (`historico_meses`) e a
participação por forma de pagamento (`participacao`).

Garantia principal: com o histórico terminando no mês atual, os números são
EXATAMENTE os do cálculo antigo da tela (soma por mês, despesa pendente fora).
"""

import pandas as pd
import pytest

from logica.dashboard import historico_meses, participacao


def desp(*linhas):
    return pd.DataFrame([{"data": d, "valor": v, "status": s} for d, v, s in linhas])


def rec(*linhas):
    return pd.DataFrame([{"data": d, "valor": v} for d, v in linhas])


DESP = desp(("2026-05-10", 10.10, "pago"), ("2026-06-10", 20.20, "pago"), ("2026-07-10", 30.30, "pago"),
            ("2026-08-10", 40.40, "pago"), ("2026-09-10", 50.50, "pago"), ("2026-10-10", 60.60, "pago"),
            ("2026-10-28", 999.0, "pendente"), ("2026-04-30", 7.0, "pago"))
REC = rec(("2026-05-01", 100.0), ("2026-06-01", 200.0), ("2026-08-01", 400.0),
          ("2026-10-01", 600.5), ("2026-04-01", 5.0))


class TestHistoricoMeses:
    def test_seis_meses_terminando_no_mes_pedido(self):
        h = historico_meses(DESP, REC, "2026-10")
        assert list(h["Mês"]) == ["Mai/26", "Jun/26", "Jul/26", "Ago/26", "Set/26", "Out/26"]
        assert list(h.columns) == ["Mês", "Receita", "Despesa"]      # formato que o PDF espera

    def test_valores_por_mes_e_pendente_fora(self):
        h = historico_meses(DESP, REC, "2026-10")
        assert list(h["Receita"]) == pytest.approx([100.0, 200.0, 0.0, 400.0, 0.0, 600.5])
        assert list(h["Despesa"]) == pytest.approx([10.10, 20.20, 30.30, 40.40, 50.50, 60.60])  # sem os 999

    def test_mes_fora_da_janela_nao_entra(self):
        h = historico_meses(DESP, REC, "2026-10")
        assert h["Despesa"].sum() == pytest.approx(212.1)            # abril (7,00) não conta

    def test_virada_de_ano(self):
        h = historico_meses(desp(("2025-12-31", 5.0, "pago"), ("2026-01-01", 6.0, "pago")),
                            rec(), "2026-02")
        assert list(h["Mês"]) == ["Set/25", "Out/25", "Nov/25", "Dez/25", "Jan/26", "Fev/26"]
        assert list(h["Despesa"]) == [0.0, 0.0, 0.0, 5.0, 6.0, 0.0]

    def test_mesmo_resultado_do_calculo_antigo_da_tela(self):
        # cálculo que estava inline no dashboard: filtra pendentes e soma por prefixo do mês
        d = DESP.copy()
        d["valor"] = pd.to_numeric(d["valor"])
        d = d[d["status"] != "pendente"]
        for i, mm in enumerate(["2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]):
            antigo_d = float(d[d["data"].astype(str).str.startswith(mm)]["valor"].sum())
            antigo_r = float(REC[REC["data"].astype(str).str.startswith(mm)]["valor"].sum())
            h = historico_meses(DESP, REC, "2026-10")
            assert h.loc[i, "Despesa"] == pytest.approx(antigo_d)
            assert h.loc[i, "Receita"] == pytest.approx(antigo_r)

    def test_n_diferente_de_seis(self):
        assert len(historico_meses(DESP, REC, "2026-10", n=3)) == 3

    def test_sem_dados(self):
        for d, r in [(pd.DataFrame(), pd.DataFrame()), (None, None)]:
            h = historico_meses(d, r, "2026-10")
            assert len(h) == 6 and h["Receita"].sum() == 0 and h["Despesa"].sum() == 0


class TestParticipacao:
    def df(self, *linhas):
        return pd.DataFrame([{"pagamento": p, "valor": v} for p, v in linhas])

    def test_soma_percentual_e_ordem(self):
        r = participacao(self.df(("Pix", 300.0), ("Cartão de crédito", 600.0), ("Pix", 100.0),
                                 ("Dinheiro", 100.0)), "pagamento")
        assert list(r["Nome"]) == ["Cartão de crédito", "Pix", "Dinheiro"]
        assert list(r["Valor"]) == pytest.approx([600.0, 400.0, 100.0])
        assert list(r["Percentual"]) == pytest.approx([54.5454545, 36.3636364, 9.0909091])
        assert r["Percentual"].sum() == pytest.approx(100.0)

    def test_texto_em_branco_vira_nao_informado(self):
        r = participacao(self.df(("", 50.0), (None, 50.0), ("  ", 100.0)), "pagamento")
        assert list(r["Nome"]) == ["Não informado"]
        assert r.loc[0, "Valor"] == 200.0

    def test_empate_ordena_por_nome(self):
        r = participacao(self.df(("Pix", 10.0), ("Dinheiro", 10.0)), "pagamento")
        assert list(r["Nome"]) == ["Dinheiro", "Pix"]

    def test_valor_zero_ou_invalido_nao_vira_linha(self):
        r = participacao(self.df(("Pix", 0.0), ("Dinheiro", "abc"), ("Cartão de crédito", 5.0)), "pagamento")
        assert list(r["Nome"]) == ["Cartão de crédito"]

    def test_vazio_sem_coluna_e_none(self):
        for d in (pd.DataFrame(), None, pd.DataFrame([{"valor": 1.0}])):
            r = participacao(d, "pagamento")
            assert r.empty and list(r.columns) == ["Nome", "Valor", "Percentual"]

    def test_nao_altera_a_entrada(self):
        d = self.df(("Pix", 1.0), ("", 2.0))
        participacao(d, "pagamento")
        assert list(d["pagamento"]) == ["Pix", ""]
