"""
Testes para utils/formatacao.py — funções puras de formatação e parsing.
Nenhuma dependência de Streamlit ou Google Sheets é necessária aqui.
"""

import pytest

from utils.formatacao import fmt_moeda, parse_valor, converter_data_para_exibicao, card_html


# ── fmt_moeda ──────────────────────────────────────────────────────────────────

class TestFmtMoeda:

    def test_valor_inteiro(self):
        assert fmt_moeda(1234) == "R$ 1.234,00"

    def test_valor_com_centavos(self):
        assert fmt_moeda(1234.5) == "R$ 1.234,50"

    def test_valor_zero(self):
        assert fmt_moeda(0) == "R$ 0,00"

    def test_valor_negativo(self):
        assert fmt_moeda(-1234.5) == "R$ -1.234,50"

    def test_valor_grande_com_milhares_multiplos(self):
        assert fmt_moeda(1234567.89) == "R$ 1.234.567,89"

    def test_arredondamento_para_duas_casas(self):
        assert fmt_moeda(10.005) in ("R$ 10,00", "R$ 10,01")  # depende do arredondamento bancário do Python

    def test_string_numerica_valida(self):
        # fmt_moeda aceita qualquer coisa conversível via float()
        assert fmt_moeda("1500.75") == "R$ 1.500,75"

    def test_valor_invalido_retorna_zero_formatado(self):
        assert fmt_moeda("abc") == "R$ 0,00"

    def test_none_retorna_zero_formatado(self):
        assert fmt_moeda(None) == "R$ 0,00"

    def test_string_vazia_retorna_zero_formatado(self):
        assert fmt_moeda("") == "R$ 0,00"


# ── parse_valor ────────────────────────────────────────────────────────────────

class TestParseValor:

    def test_formato_br_com_milhar_e_decimal(self):
        assert parse_valor("1.234,56") == 1234.56

    def test_formato_us_com_milhar_e_decimal(self):
        assert parse_valor("1,234.56") == 1234.56

    def test_formato_us_sem_milhar(self):
        assert parse_valor("1234.56") == 1234.56

    def test_formato_br_sem_milhar(self):
        assert parse_valor("1234,56") == 1234.56

    def test_apenas_inteiro(self):
        assert parse_valor("500") == 500.0

    def test_valor_negativo_formato_br(self):
        assert parse_valor("-50,00") == -50.0

    def test_prefixo_moeda_e_espacos_sao_ignorados(self):
        assert parse_valor("  R$ 1.234,56  ") == 1234.56

    def test_valor_pequeno_com_centavos(self):
        assert parse_valor("0,01") == 0.01

    def test_milhar_multiplo_formato_br(self):
        assert parse_valor("1.234.567,89") == 1234567.89

    def test_string_vazia_levanta_erro(self):
        with pytest.raises(ValueError):
            parse_valor("")

    def test_string_so_espacos_levanta_erro(self):
        with pytest.raises(ValueError):
            parse_valor("   ")

    def test_none_levanta_erro(self):
        with pytest.raises(ValueError):
            parse_valor(None)

    def test_texto_sem_digitos_levanta_erro(self):
        with pytest.raises(ValueError):
            parse_valor("abc")


# ── converter_data_para_exibicao ────────────────────────────────────────────────

class TestConverterDataParaExibicao:

    def test_formato_iso_com_hifen(self):
        assert converter_data_para_exibicao("2026-07-01") == "01/07/2026"

    def test_formato_iso_com_barra(self):
        assert converter_data_para_exibicao("2026/07/01") == "01/07/2026"

    def test_data_invalida_retorna_valor_original(self):
        assert converter_data_para_exibicao("data-invalida") == "data-invalida"

    def test_string_vazia_retorna_vazia(self):
        assert converter_data_para_exibicao("") == ""

    def test_fim_de_ano(self):
        assert converter_data_para_exibicao("2025-12-31") == "31/12/2025"


# ── card_html ────────────────────────────────────────────────────────────────────

class TestCardHtml:

    def test_estrutura_basica(self):
        html_out = card_html("Total", "R$ 100,00", "green")
        assert 'class="card"' in html_out
        assert 'class="card-label"' in html_out
        assert 'card-value green' in html_out
        assert "Total" in html_out
        assert "R$ 100,00" in html_out

    def test_escapa_html_no_label(self):
        html_out = card_html("<script>alert(1)</script>", "100", "red")
        assert "<script>" not in html_out
        assert "&lt;script&gt;" in html_out

    def test_escapa_html_no_valor(self):
        html_out = card_html("Total", "<img src=x onerror=alert(1)>", "blue")
        assert "<img" not in html_out
        assert "&lt;img" in html_out

    def test_valor_numerico_e_convertido_para_string(self):
        html_out = card_html("Contagem", 42, "orange")
        assert "42" in html_out
