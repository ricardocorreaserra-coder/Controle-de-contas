"""Ajustes pequenos do Dashboard: 'Demais' na rosquinha, grade de cartões e contraste."""
import pandas as pd
import pytest

from logica.dashboard import LIMITE_DEMAIS_PCT, agrupar_pequenas
from utils.formatacao import (
    _CSS_LINHA_DO_TEMPO, kpi_card_html, kpi_grid_html, linha_do_tempo_html,
)


def _df(*pares):
    return pd.DataFrame(pares, columns=["Categoria", "Valor"])


def _por_nome(r):
    return {l["Categoria"]: l for _, l in r.iterrows()}


class TestAgruparPequenas:
    def test_limite_padrao_e_3_por_cento(self):
        assert LIMITE_DEMAIS_PCT == 3.0

    def test_junta_as_pequenas_em_demais_por_ultimo(self):
        r = agrupar_pequenas(_df(("Outros", 520), ("Alimentação", 200), ("Lazer", 20), ("Pets", 10), ("Seguros", 5), ("Saúde", 245)))
        assert list(r["Categoria"]) == ["Outros", "Saúde", "Alimentação", "Demais"]
        assert _por_nome(r)["Demais"]["Valor"] == 35

    def test_total_nunca_muda(self):
        df = _df(("A", 700), ("B", 250.55), ("C", 20.10), ("D", 15.35), ("E", 14))
        assert agrupar_pequenas(df)["Valor"].sum() == pytest.approx(df["Valor"].sum())

    def test_detalhe_lista_as_categorias_agrupadas(self):
        r = _por_nome(agrupar_pequenas(_df(("A", 900), ("Pets", 20), ("Seguros", 10))))
        assert r["Demais"]["Detalhe"] == "Inclui: Pets, Seguros"
        assert r["A"]["Detalhe"] == ""

    def test_detalhe_resume_quando_sao_muitas(self):
        pares = [("Grande", 1000)] + [(f"c{i:02d}", 1) for i in range(12)]
        detalhe = _por_nome(agrupar_pequenas(_df(*pares)))["Demais"]["Detalhe"]
        assert detalhe.endswith("e mais 4") and detalhe.count(",") == 7

    def test_uma_unica_pequena_nao_vira_demais(self):
        r = agrupar_pequenas(_df(("A", 900), ("B", 70), ("C", 30)))   # C tem exatamente 3%: não é pequena
        assert "Demais" not in set(r["Categoria"])
        r = agrupar_pequenas(_df(("A", 990), ("B", 10)))              # só B é pequena
        assert list(r["Categoria"]) == ["A", "B"]

    def test_exatamente_3_por_cento_nao_e_pequena(self):
        r = agrupar_pequenas(_df(("A", 94), ("B", 3), ("C", 3)))
        assert "Demais" not in set(r["Categoria"])

    def test_todas_pequenas_nao_agrupa(self):
        r = agrupar_pequenas(_df(*[(f"c{i}", 1) for i in range(40)]))
        assert len(r) == 40 and "Demais" not in set(r["Categoria"])

    def test_nome_demais_ja_existente_nao_se_mistura(self):
        r = agrupar_pequenas(_df(("Demais", 900), ("x", 5), ("y", 5)))
        assert set(r["Categoria"]) == {"Demais", "Demais categorias"}

    def test_soma_categorias_repetidas_e_trata_branco(self):
        r = _por_nome(agrupar_pequenas(_df(("A", 400), ("A", 500), ("", 50), (None, 50))))
        assert r["A"]["Valor"] == 900 and r["Sem categoria"]["Valor"] == 100

    def test_ignora_valor_zero_negativo_e_invalido(self):
        r = agrupar_pequenas(_df(("A", 100), ("B", 0), ("C", -5), ("D", "abc"), ("E", None)))
        assert list(r["Categoria"]) == ["A"]

    @pytest.mark.parametrize("entrada", [None, pd.DataFrame(), pd.DataFrame({"x": [1]})])
    def test_entrada_vazia_ou_sem_colunas(self, entrada):
        r = agrupar_pequenas(entrada)
        assert r.empty and list(r.columns) == ["Categoria", "Valor", "Detalhe"]

    def test_nao_altera_o_dataframe_recebido(self):
        df = _df(("A", 900), ("B", 5), ("C", 5))
        antes = df.copy()
        agrupar_pequenas(df)
        pd.testing.assert_frame_equal(df, antes)

    def test_nomes_de_colunas_personalizados(self):
        df = pd.DataFrame([("A", 900), ("B", 5), ("C", 5)], columns=["Nome", "V"])
        r = agrupar_pequenas(df, "Nome", "V", rotulo="Outras")
        assert list(r.columns) == ["Nome", "V", "Detalhe"] and "Outras" in set(r["Nome"])


class TestGradeDosCartoes:
    def test_junta_os_cartoes_numa_grade(self):
        c = [kpi_card_html("x", f"r{i}", "v", "blue") for i in range(3)]
        h = kpi_grid_html(c)
        assert h.count('class="card"') == 3 and 'class="kpi-grid"' in h

    def test_tres_colunas_mesma_altura_e_empilha_no_celular(self):
        h = kpi_grid_html([])
        assert "repeat(3" in h and "align-items:stretch" in h
        assert "max-width:640px" in h and "grid-template-columns:1fr" in h

    def test_sem_linhas_em_branco_que_quebrariam_o_html_do_markdown(self):
        assert "\n\n" not in kpi_grid_html([kpi_card_html("x", "r", "v", "red", [("a", 1)])])


class TestContrasteDoMesSelecionado:
    def test_vermelho_claro_so_no_tema_escuro(self):
        assert "light-dark(#dc2626,#f87171)" in _CSS_LINHA_DO_TEMPO

    def test_ha_cor_de_reserva_para_navegador_sem_light_dark(self):
        # a declaração simples vem ANTES; navegador antigo ignora só a segunda
        css = _CSS_LINHA_DO_TEMPO
        assert css.index("color:#dc2626;color:light-dark") >= 0

    def test_html_da_linha_do_tempo_inclui_o_css(self):
        assert "light-dark(" in linha_do_tempo_html([])
