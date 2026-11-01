"""Etapa 5 do redesenho: limite usado por cartão (soma das parcelas PENDENTES)."""
import numpy as np
import pandas as pd
import pytest

from logica.cartoes import LIMITE_ALERTA, resumo_limites_cartoes


def _cartoes(*linhas):
    return pd.DataFrame(linhas, columns=["id", "nome", "limite", "dia_fechamento", "dia_vencimento"])


def _parcelas(*linhas):
    return pd.DataFrame(linhas, columns=["cartao", "status", "valor"])


def _por_nome(resumo):
    return {c["nome"]: c for c in resumo["cartoes"]}


class TestSomaDePendentes:
    def test_soma_so_pendentes_do_proprio_cartao(self):
        df_c = _cartoes([1, "Nubank", 1000, 5, 12], [2, "Itaú", 500, 10, 17])
        df_p = _parcelas(["Nubank", "pendente", 100.10], ["Nubank", "pendente", 200.20],
                         ["Nubank", "pago", 999], ["Itaú", "pendente", 50])
        r = _por_nome(resumo_limites_cartoes(df_c, df_p))
        assert r["Nubank"]["usado"] == 300.30
        assert r["Nubank"]["n_parcelas"] == 2
        assert r["Itaú"]["usado"] == 50

    def test_disponivel_e_percentual(self):
        df_c = _cartoes([1, "Nubank", 1000, 5, 12])
        r = _por_nome(resumo_limites_cartoes(df_c, _parcelas(["Nubank", "pendente", 250])))["Nubank"]
        assert r["disponivel"] == 750
        assert r["percentual"] == pytest.approx(0.25)
        assert r["alerta"] is False and r["estourado"] is False

    def test_sem_parcelas_usado_zero_e_disponivel_igual_ao_limite(self):
        r = _por_nome(resumo_limites_cartoes(_cartoes([1, "Nubank", 1000, 5, 12]), pd.DataFrame()))["Nubank"]
        assert r["usado"] == 0 and r["disponivel"] == 1000 and r["percentual"] == 0

    def test_status_com_espaco_e_maiuscula_conta_como_pendente(self):
        df_c = _cartoes([1, "Nubank", 1000, 5, 12])
        df_p = _parcelas(["Nubank", " Pendente ", 10], ["Nubank", "PENDENTE", 5])
        assert _por_nome(resumo_limites_cartoes(df_c, df_p))["Nubank"]["usado"] == 15

    def test_status_vazio_nao_conta(self):
        df_c = _cartoes([1, "Nubank", 1000, 5, 12])
        df_p = _parcelas(["Nubank", "", 10], ["Nubank", None, 5], ["Nubank", np.nan, 1])
        assert _por_nome(resumo_limites_cartoes(df_c, df_p))["Nubank"]["usado"] == 0

    def test_valor_invalido_vira_zero_sem_quebrar(self):
        df_c = _cartoes([1, "Nubank", 1000, 5, 12])
        df_p = _parcelas(["Nubank", "pendente", "abc"], ["Nubank", "pendente", None], ["Nubank", "pendente", 7.5])
        assert _por_nome(resumo_limites_cartoes(df_c, df_p))["Nubank"]["usado"] == 7.5

    def test_centavos_sem_erro_de_ponto_flutuante(self):
        df_c = _cartoes([1, "Nubank", 1000, 5, 12])
        df_p = _parcelas(*[["Nubank", "pendente", 0.1]] * 3)
        assert _por_nome(resumo_limites_cartoes(df_c, df_p))["Nubank"]["usado"] == 0.3

    def test_nome_do_cartao_com_espaco_extra_casa(self):
        df_c = _cartoes([1, "Nubank ", 1000, 5, 12])
        df_p = _parcelas([" Nubank", "pendente", 40])
        assert _por_nome(resumo_limites_cartoes(df_c, df_p))["Nubank"]["usado"] == 40


class TestAlertaELimite:
    def test_alerta_a_partir_de_80_por_cento(self):
        assert LIMITE_ALERTA == 0.80
        df_c = _cartoes([1, "A", 1000, 5, 12], [2, "B", 1000, 5, 12])
        df_p = _parcelas(["A", "pendente", 800], ["B", "pendente", 799.99])
        r = _por_nome(resumo_limites_cartoes(df_c, df_p))
        assert r["A"]["alerta"] is True
        assert r["B"]["alerta"] is False

    def test_estourado_nao_tem_disponivel_negativo(self):
        r = _por_nome(resumo_limites_cartoes(_cartoes([1, "A", 1000, 5, 12]),
                                             _parcelas(["A", "pendente", 1300])))["A"]
        assert r["estourado"] is True and r["alerta"] is True
        assert r["disponivel"] == 0
        assert r["percentual"] == pytest.approx(1.3)

    def test_exatamente_no_limite_nao_e_estourado(self):
        r = _por_nome(resumo_limites_cartoes(_cartoes([1, "A", 1000, 5, 12]),
                                             _parcelas(["A", "pendente", 1000])))["A"]
        assert r["estourado"] is False and r["alerta"] is True and r["disponivel"] == 0

    @pytest.mark.parametrize("limite", [0, None, "", "abc", -50, np.nan])
    def test_sem_limite_valido_nao_tem_barra_nem_disponivel(self, limite):
        r = _por_nome(resumo_limites_cartoes(_cartoes([1, "A", limite, 5, 12]),
                                             _parcelas(["A", "pendente", 100])))["A"]
        assert r["tem_limite"] is False
        assert r["disponivel"] is None and r["percentual"] is None
        assert r["alerta"] is False and r["estourado"] is False
        assert r["usado"] == 100


class TestDatasECadastro:
    def test_dias_de_fechamento_e_vencimento(self):
        r = _por_nome(resumo_limites_cartoes(_cartoes([1, "A", 100, 5, "12"], [2, "B", 100, "", 40]), None))
        assert (r["A"]["dia_fechamento"], r["A"]["dia_vencimento"]) == (5, 12)
        assert (r["B"]["dia_fechamento"], r["B"]["dia_vencimento"]) == (None, None)

    def test_ordem_dos_cartoes_segue_a_planilha(self):
        df_c = _cartoes([1, "Z", 1, 1, 1], [2, "A", 1, 1, 1])
        assert [c["nome"] for c in resumo_limites_cartoes(df_c, None)["cartoes"]] == ["Z", "A"]

    def test_sem_cartoes_devolve_lista_vazia(self):
        for vazio in (None, pd.DataFrame(), pd.DataFrame(columns=["id", "nome"])):
            assert resumo_limites_cartoes(vazio, None)["cartoes"] == []

    def test_nome_vazio_e_repetido_sao_ignorados(self):
        df_c = _cartoes([1, "", 100, 1, 1], [2, "A", 100, 1, 1], [3, "A", 100, 1, 1])
        assert [c["nome"] for c in resumo_limites_cartoes(df_c, None)["cartoes"]] == ["A"]


class TestParcelasSemCartaoCadastrado:
    def test_parcelas_de_cartao_inexistente_ficam_a_parte(self):
        df_c = _cartoes([1, "Nubank", 1000, 5, 12])
        df_p = _parcelas(["Nubank", "pendente", 10], ["Antigo", "pendente", 30],
                         ["", "pendente", 5], ["Antigo", "pago", 99])
        r = resumo_limites_cartoes(df_c, df_p)
        assert r["sem_cartao_n"] == 2 and r["sem_cartao_valor"] == 35
        assert _por_nome(r)["Nubank"]["usado"] == 10

    def test_tabelas_sem_as_colunas_esperadas_nao_quebram(self):
        r = resumo_limites_cartoes(_cartoes([1, "A", 100, 1, 1]), pd.DataFrame({"x": [1]}))
        assert r["cartoes"][0]["usado"] == 0 and r["sem_cartao_n"] == 0

    def test_nao_altera_os_dataframes_recebidos(self):
        df_c = _cartoes([1, "A", 100, 1, 1])
        df_p = _parcelas(["A", "pendente", 10])
        c0, p0 = df_c.copy(), df_p.copy()
        resumo_limites_cartoes(df_c, df_p)
        pd.testing.assert_frame_equal(df_c, c0)
        pd.testing.assert_frame_equal(df_p, p0)
