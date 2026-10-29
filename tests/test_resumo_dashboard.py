"""
Testes do resumo do mês do Dashboard (logica/dashboard.py), do deslocamento de
meses da barra de período (utils/datas.py) e do cartão com ícone
(utils/formatacao.py::kpi_card_html).

Garantia principal: os números dos cartões continuam EXATAMENTE os do Dashboard
anterior (despesa pendente fora; sem status = pago) e a parte "a pagar" é nova.
"""

import pandas as pd
import pytest

from logica.dashboard import resumo_mes
from utils.datas import MESES_COMPLETOS, deslocar_mes
from utils.formatacao import kpi_card_html


def desp(*linhas):
    return pd.DataFrame([{"data": d, "valor": v, "status": s} for d, v, s in linhas])


def rec(*linhas):
    return pd.DataFrame([{"data": d, "valor": v} for d, v in linhas])


class TestResumoMes:
    def test_totais_basicos_com_centavos(self):
        r = resumo_mes(desp(("2026-10-01", 10.55, "pago"), ("2026-10-09", 4.45, "pago")),
                       rec(("2026-10-05", 1000.10), ("2026-10-06", 0.05)), "2026-10")
        assert r["total_rec"] == pytest.approx(1000.15)
        assert r["total_desp"] == pytest.approx(15.0)
        assert r["saldo"] == pytest.approx(985.15)
        assert (r["n_rec"], r["n_desp"], r["n_a_pagar"]) == (2, 2, 0)

    def test_so_conta_o_mes_pedido(self):
        r = resumo_mes(desp(("2026-09-30", 50.0, "pago"), ("2026-10-01", 7.0, "pago"),
                            ("2026-11-01", 90.0, "pago")),
                       rec(("2026-09-01", 100.0), ("2026-10-02", 300.0)), "2026-10")
        assert (r["total_rec"], r["total_desp"]) == (300.0, 7.0)

    def test_pendente_fica_fora_de_despesas_e_do_saldo_mas_vai_para_a_pagar(self):
        r = resumo_mes(desp(("2026-10-01", 100.0, "pago"), ("2026-10-20", 250.0, "pendente")),
                       rec(("2026-10-02", 1000.0)), "2026-10")
        assert r["total_desp"] == 100.0          # igual ao Dashboard anterior
        assert r["saldo"] == 900.0               # idem
        assert (r["a_pagar"], r["n_a_pagar"]) == (250.0, 1)
        assert r["saldo_apos"] == 650.0

    def test_status_vazio_ou_estranho_conta_como_pago(self):
        # regra do projeto: só o texto exato "pendente" é pendente
        r = resumo_mes(desp(("2026-10-01", 10.0, ""), ("2026-10-02", 20.0, None),
                            ("2026-10-03", 30.0, "xyz"), ("2026-10-04", 5.0, "PENDENTE ")),
                       rec(), "2026-10")
        assert r["total_desp"] == 60.0
        assert r["a_pagar"] == 5.0

    def test_planilha_antiga_sem_coluna_status(self):
        d = pd.DataFrame([{"data": "2026-10-01", "valor": 12.5}])
        r = resumo_mes(d, rec(), "2026-10")
        assert (r["total_desp"], r["a_pagar"]) == (12.5, 0.0)

    def test_vazio_e_none(self):
        for d, rc in [(pd.DataFrame(), pd.DataFrame()), (None, None)]:
            r = resumo_mes(d, rc, "2026-10")
            assert r == {"total_rec": 0.0, "n_rec": 0, "total_desp": 0.0, "n_desp": 0,
                         "a_pagar": 0.0, "n_a_pagar": 0, "saldo": 0.0, "saldo_apos": 0.0}

    def test_valor_invalido_vira_zero_e_nao_altera_a_entrada(self):
        d = desp(("2026-10-01", "abc", "pago"), ("2026-10-02", 8.0, "pago"))
        r = resumo_mes(d, rec(), "2026-10")
        assert r["total_desp"] == 8.0
        assert d.loc[0, "valor"] == "abc"        # DataFrame original intacto

    def test_data_como_texto_e_numero_misturados(self):
        d = pd.DataFrame([{"data": "2026-10-01", "valor": 1.5, "status": "pago"},
                          {"data": 20261001, "valor": 9.0, "status": "pago"}])
        assert resumo_mes(d, rec(), "2026-10")["total_desp"] == 1.5

    def test_mes_sem_nenhuma_despesa_com_coluna_status(self):
        # defeito real achado na simulação: mês vazio + coluna status => KeyError 'valor'
        r = resumo_mes(desp(("2026-10-01", 10.0, "pago")), rec(("2026-10-02", 5.0)), "2026-08")
        assert (r["total_desp"], r["a_pagar"], r["total_rec"], r["saldo"]) == (0.0, 0.0, 0.0, 0.0)

    def test_mes_so_com_pendentes_ou_so_com_pagas(self):
        so_pend = resumo_mes(desp(("2026-10-20", 40.0, "pendente")), rec(), "2026-10")
        assert (so_pend["total_desp"], so_pend["a_pagar"], so_pend["n_desp"]) == (0.0, 40.0, 0)
        so_pagas = resumo_mes(desp(("2026-10-01", 40.0, "pago")), rec(), "2026-10")
        assert (so_pagas["total_desp"], so_pagas["a_pagar"], so_pagas["n_a_pagar"]) == (40.0, 0.0, 0)

    def test_saldo_negativo(self):
        r = resumo_mes(desp(("2026-10-01", 300.0, "pago")), rec(("2026-10-02", 100.0)), "2026-10")
        assert r["saldo"] == -200.0


class TestDeslocarMes:
    @pytest.mark.parametrize("ano,mes,delta,esperado", [
        (2026, 10, 1, (2026, 11)), (2026, 10, -1, (2026, 9)),
        (2026, 12, 1, (2027, 1)), (2026, 1, -1, (2025, 12)),
        (2026, 3, -15, (2024, 12)), (2026, 3, 0, (2026, 3)), (2026, 1, 12, (2027, 1)),
    ])
    def test_deslocamentos(self, ano, mes, delta, esperado):
        assert deslocar_mes(ano, mes, delta) == esperado

    def test_nomes_completos_dos_12_meses(self):
        assert list(MESES_COMPLETOS) == list(range(1, 13))
        assert MESES_COMPLETOS[3] == "Março" and MESES_COMPLETOS[10] == "Outubro"


class TestKpiCard:
    def test_mostra_icone_rotulo_valor_e_linhas(self):
        h = kpi_card_html("💸", "Despesas do mês", "R$ 1,00", "red", [("A pagar", "R$ 2,00")])
        assert "💸 Despesas do mês" in h and "R$ 1,00" in h and "card-value red" in h
        assert "A pagar" in h and "R$ 2,00" in h

    def test_sem_linhas_extras_nao_desenha_divisoria(self):
        assert "border-top" not in kpi_card_html("💵", "Receitas", "R$ 0,00", "green")

    def test_escapa_html(self):
        h = kpi_card_html("x", "<b>rotulo</b>", "<i>1</i>", "red", [("<u>a</u>", "<s>b</s>")])
        for cru in ("<b>rotulo", "<i>1", "<u>a", "<s>b"):
            assert cru not in h

    def test_so_cores_translucidas_ou_herdadas(self):
        # regra 8 (tema claro/escuro): nada de cor de fundo/texto fixa clara
        h = kpi_card_html("x", "r", "v", "blue", [("a", "b")])
        for proibida in ("background: white", "#fff", "#e2e8f0", "#64748b"):
            assert proibida not in h
