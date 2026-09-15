"""
Testes para as funções puras de logica/emprestimos.py:

- calcular_valor_total_devido(): valor total é sempre parcela × restantes.
- processar_baixas_automaticas(): avança o estado do empréstimo baixando
  automaticamente todas as parcelas cujo vencimento já passou.

Nenhuma das duas toca em Sheets/Streamlit — testáveis isoladamente.
"""

from datetime import date

from logica.emprestimos import calcular_valor_total_devido, processar_baixas_automaticas


class TestCalcularValorTotalDevido:

    def test_produto_simples(self):
        assert calcular_valor_total_devido(100.0, 5) == 500.0

    def test_com_centavos(self):
        assert calcular_valor_total_devido(66.67, 3) == 200.01

    def test_zero_parcelas_restantes_zera_o_total(self):
        assert calcular_valor_total_devido(100.0, 0) == 0.0

    def test_parcelas_negativas_tratadas_como_zero(self):
        assert calcular_valor_total_devido(100.0, -3) == 0.0

    def test_aceita_valor_parcela_como_string_numerica(self):
        assert calcular_valor_total_devido("50.5", 4) == 202.0


class TestProcessarBaixasAutomaticas:

    def test_vencimento_no_futuro_nao_da_baixa(self):
        resultado = processar_baixas_automaticas(
            parcelas_restantes=10, valor_parcela=100.0,
            proxima_data_vencimento=date(2026, 8, 10), hoje=date(2026, 7, 1)
        )
        assert resultado["parcelas_baixadas"] == 0
        assert resultado["parcelas_restantes"] == 10
        assert resultado["proxima_data_vencimento"] == date(2026, 8, 10)
        assert resultado["valor_total_devido"] == 1000.0

    def test_vencimento_exatamente_hoje_da_uma_baixa(self):
        resultado = processar_baixas_automaticas(
            parcelas_restantes=5, valor_parcela=200.0,
            proxima_data_vencimento=date(2026, 7, 5), hoje=date(2026, 7, 5)
        )
        assert resultado["parcelas_baixadas"] == 1
        assert resultado["parcelas_restantes"] == 4
        assert resultado["proxima_data_vencimento"] == date(2026, 8, 5)
        assert resultado["valor_total_devido"] == 800.0

    def test_varios_meses_atrasados_baixam_todos_de_uma_vez(self):
        resultado = processar_baixas_automaticas(
            parcelas_restantes=10, valor_parcela=100.0,
            proxima_data_vencimento=date(2026, 1, 10), hoje=date(2026, 4, 15)
        )
        assert resultado["parcelas_baixadas"] == 4
        assert resultado["parcelas_restantes"] == 6
        assert resultado["proxima_data_vencimento"] == date(2026, 5, 10)
        assert resultado["valor_total_devido"] == 600.0

    def test_para_de_baixar_quando_parcelas_se_esgotam(self):
        resultado = processar_baixas_automaticas(
            parcelas_restantes=3, valor_parcela=50.0,
            proxima_data_vencimento=date(2026, 1, 10), hoje=date(2026, 12, 31)
        )
        assert resultado["parcelas_baixadas"] == 3
        assert resultado["parcelas_restantes"] == 0
        assert resultado["valor_total_devido"] == 0.0

    def test_ja_quitado_nao_faz_nada(self):
        resultado = processar_baixas_automaticas(
            parcelas_restantes=0, valor_parcela=100.0,
            proxima_data_vencimento=date(2026, 1, 1), hoje=date(2026, 12, 31)
        )
        assert resultado["parcelas_baixadas"] == 0
        assert resultado["parcelas_restantes"] == 0
        assert resultado["valor_total_devido"] == 0.0

    def test_penultimo_dia_antes_do_vencimento_nao_baixa(self):
        resultado = processar_baixas_automaticas(
            parcelas_restantes=2, valor_parcela=100.0,
            proxima_data_vencimento=date(2026, 7, 10), hoje=date(2026, 7, 9)
        )
        assert resultado["parcelas_baixadas"] == 0
        assert resultado["parcelas_restantes"] == 2

    def test_virada_de_ano_no_avanco_do_vencimento(self):
        resultado = processar_baixas_automaticas(
            parcelas_restantes=5, valor_parcela=100.0,
            proxima_data_vencimento=date(2026, 12, 20), hoje=date(2027, 1, 5)
        )
        assert resultado["parcelas_baixadas"] == 1
        assert resultado["proxima_data_vencimento"] == date(2027, 1, 20)
        assert resultado["parcelas_restantes"] == 4
