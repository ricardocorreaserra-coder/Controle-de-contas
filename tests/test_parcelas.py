"""
Testes para logica/parcelas.py — foco em valores_parcelas(), que divide um
valor total em N parcelas garantindo que a soma bata exatamente com o
total (B-03). As demais funções do módulo dependem do Google Sheets.
"""

import pytest

from logica.parcelas import valores_parcelas


class TestValoresParcelas:

    def test_divisao_exata(self):
        assert valores_parcelas(100.0, 4) == [25.0, 25.0, 25.0, 25.0]

    def test_divisao_com_dizima_ajusta_ultima_parcela(self):
        resultado = valores_parcelas(100.0, 3)
        assert resultado == [33.33, 33.33, 33.34]

    def test_soma_bate_com_total_mesmo_com_arredondamento(self):
        resultado = valores_parcelas(10.0, 3)
        assert round(sum(resultado), 2) == 10.0
        assert resultado == [3.33, 3.33, 3.34]

    def test_uma_unica_parcela_devolve_o_valor_total(self):
        assert valores_parcelas(150.0, 1) == [150.0]

    def test_valor_pequeno_com_centavos(self):
        resultado = valores_parcelas(0.03, 3)
        assert round(sum(resultado), 2) == 0.03

    def test_quantidade_de_parcelas_corresponde_ao_pedido(self):
        resultado = valores_parcelas(999.99, 7)
        assert len(resultado) == 7

    @pytest.mark.parametrize("valor_total,n_parc", [
        (100.0, 3),
        (1000.0, 6),
        (1234.56, 5),
        (0.10, 3),
        (999999.99, 24),
        (50.0, 2),
        (1.0, 3),
    ])
    def test_soma_das_parcelas_sempre_bate_com_o_total(self, valor_total, n_parc):
        resultado = valores_parcelas(valor_total, n_parc)
        assert len(resultado) == n_parc
        assert round(sum(resultado), 2) == round(valor_total, 2)

    def test_apenas_a_ultima_parcela_absorve_a_diferenca(self):
        resultado = valores_parcelas(100.0, 3)
        # as duas primeiras parcelas devem ser iguais entre si
        assert resultado[0] == resultado[1]
        # e a diferença de arredondamento só aparece na última
        assert resultado[2] != resultado[0]
