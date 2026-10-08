"""
Testes para logica/despesas.py — foco em despesa_esta_pendente(), a função
pura que decide se uma despesa conta como "ainda não paga" (B-04). As
demais funções do módulo gravam diretamente na planilha e por isso ficam
fora do escopo destes testes.
"""

from logica.despesas import despesa_esta_pendente


class TestDespesaEstaPendente:

    def test_status_pendente(self):
        assert despesa_esta_pendente("pendente") is True

    def test_status_pendente_maiusculo(self):
        assert despesa_esta_pendente("PENDENTE") is True

    def test_status_pendente_com_espacos(self):
        assert despesa_esta_pendente("  pendente  ") is True

    def test_status_pago_nao_e_pendente(self):
        assert despesa_esta_pendente("pago") is False

    def test_status_vazio_nao_e_pendente(self):
        # Despesas lançadas antes deste campo existir têm status em
        # branco — devem contar como já pagas (comportamento histórico).
        assert despesa_esta_pendente("") is False

    def test_status_none_nao_e_pendente(self):
        assert despesa_esta_pendente(None) is False

    def test_status_nan_nao_e_pendente(self):
        assert despesa_esta_pendente(float("nan")) is False

    def test_texto_qualquer_nao_e_pendente(self):
        assert despesa_esta_pendente("qualquer coisa") is False
