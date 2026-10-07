"""
Testes para logica/parcelas.py.

valores_parcelas(): divide um valor total em N parcelas garantindo que a
soma bata exatamente com o total (B-03).

_indices_da_compra() e resumo_compra_parcelas(): recebem o DataFrame já
carregado (não tocam o Google Sheets), então são testáveis como funções
puras — cobrem especialmente a desambiguação de lançamentos históricos
com descrição/cartão/total repetidos (ex.: duas assinaturas "Netflix"
parceladas em momentos diferentes).

As demais funções do módulo (salvar_parcela_manual, corrigir_total_parcelas,
alterar_lancamento_parcela, etc.) gravam diretamente na planilha e por isso
ficam fora do escopo destes testes.
"""

import pandas as pd
import pytest

from logica.parcelas import valores_parcelas, _indices_da_compra, resumo_compra_parcelas


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


# ── _indices_da_compra ───────────────────────────────────────────────────────

def _df_parcelas(linhas):
    """Monta um DataFrame de parcelas a partir de uma lista de dicts, com
    as colunas que _indices_da_compra / resumo_compra_parcelas esperam."""
    cols = ["id", "despesa_id", "numero", "total", "valor", "vencimento",
            "status", "descricao", "cartao", "origem_vencimento"]
    return pd.DataFrame(linhas, columns=cols)


class TestIndicesDaCompra:

    def test_parcela_de_despesa_agrupa_pelo_despesa_id(self):
        df = _df_parcelas([
            {"id": 1, "despesa_id": 7, "numero": 1, "total": 3, "valor": 10.0,
             "vencimento": "2026-01-10", "status": "pago", "descricao": "Mercado",
             "cartao": "Nubank", "origem_vencimento": "fechamento"},
            {"id": 2, "despesa_id": 7, "numero": 2, "total": 3, "valor": 10.0,
             "vencimento": "2026-02-10", "status": "pendente", "descricao": "Mercado",
             "cartao": "Nubank", "origem_vencimento": "fechamento"},
            {"id": 3, "despesa_id": 7, "numero": 3, "total": 3, "valor": 10.0,
             "vencimento": "2026-03-10", "status": "pendente", "descricao": "Mercado",
             "cartao": "Nubank", "origem_vencimento": "fechamento"},
            # despesa diferente, não deve entrar no grupo mesmo com descrição parecida
            {"id": 4, "despesa_id": 9, "numero": 1, "total": 1, "valor": 50.0,
             "vencimento": "2026-01-10", "status": "pendente", "descricao": "Mercado",
             "cartao": "Nubank", "origem_vencimento": "fechamento"},
        ])
        resultado = _indices_da_compra(df, idx_ref=1)  # linha do id=2
        assert resultado == [0, 1, 2]

    def test_lancamento_historico_simples_sem_ambiguidade(self):
        df = _df_parcelas([
            {"id": 10, "despesa_id": -1, "numero": 1, "total": 3, "valor": 20.0,
             "vencimento": "2026-01-05", "status": "pago", "descricao": "Geladeira",
             "cartao": "Itaú", "origem_vencimento": "manual"},
            {"id": 11, "despesa_id": -1, "numero": 2, "total": 3, "valor": 20.0,
             "vencimento": "2026-02-05", "status": "pendente", "descricao": "Geladeira",
             "cartao": "Itaú", "origem_vencimento": "manual"},
            {"id": 12, "despesa_id": -1, "numero": 3, "total": 3, "valor": 20.0,
             "vencimento": "2026-03-05", "status": "pendente", "descricao": "Geladeira",
             "cartao": "Itaú", "origem_vencimento": "manual"},
        ])
        resultado = _indices_da_compra(df, idx_ref=0)
        assert resultado == [0, 1, 2]

    def test_duas_compras_historicas_com_mesma_descricao_cartao_e_total(self):
        """
        Caso real que motivou a desambiguação por sequência: duas assinaturas
        'Netflix' no mesmo cartão, ambas parceladas em 3x — os números de
        parcela (1,2,3) se repetem entre as duas compras. A função deve
        isolar apenas o grupo da parcela de referência, usando a sequência
        de ids consecutivos com números também consecutivos.
        """
        df = _df_parcelas([
            # Compra A: ids 10-12, parcelas 1-3
            {"id": 10, "despesa_id": -1, "numero": 1, "total": 3, "valor": 15.0,
             "vencimento": "2026-01-01", "status": "pago", "descricao": "Netflix",
             "cartao": "Nubank", "origem_vencimento": "manual"},
            {"id": 11, "despesa_id": -1, "numero": 2, "total": 3, "valor": 15.0,
             "vencimento": "2026-02-01", "status": "pendente", "descricao": "Netflix",
             "cartao": "Nubank", "origem_vencimento": "manual"},
            {"id": 12, "despesa_id": -1, "numero": 3, "total": 3, "valor": 15.0,
             "vencimento": "2026-03-01", "status": "pendente", "descricao": "Netflix",
             "cartao": "Nubank", "origem_vencimento": "manual"},
            # Compra B: ids 20-22, parcelas 1-3 (mesma descrição/cartão/total)
            {"id": 20, "despesa_id": -1, "numero": 1, "total": 3, "valor": 15.0,
             "vencimento": "2026-06-01", "status": "pendente", "descricao": "Netflix",
             "cartao": "Nubank", "origem_vencimento": "manual"},
            {"id": 21, "despesa_id": -1, "numero": 2, "total": 3, "valor": 15.0,
             "vencimento": "2026-07-01", "status": "pendente", "descricao": "Netflix",
             "cartao": "Nubank", "origem_vencimento": "manual"},
            {"id": 22, "despesa_id": -1, "numero": 3, "total": 3, "valor": 15.0,
             "vencimento": "2026-08-01", "status": "pendente", "descricao": "Netflix",
             "cartao": "Nubank", "origem_vencimento": "manual"},
        ])
        # Pede a compra a partir da parcela do meio da Compra A (id=11, índice 1)
        resultado = _indices_da_compra(df, idx_ref=1)
        assert resultado == [0, 1, 2]  # só a Compra A, nunca mistura com a B

        # E a partir da Compra B também isola corretamente, sem pegar a A
        resultado_b = _indices_da_compra(df, idx_ref=4)  # id=21, índice 4
        assert resultado_b == [3, 4, 5]

    def test_compra_de_parcela_unica(self):
        df = _df_parcelas([
            {"id": 30, "despesa_id": -1, "numero": 1, "total": 1, "valor": 99.0,
             "vencimento": "2026-05-01", "status": "pendente", "descricao": "Fogão",
             "cartao": "Visa", "origem_vencimento": "manual"},
        ])
        assert _indices_da_compra(df, idx_ref=0) == [0]


# ── resumo_compra_parcelas ───────────────────────────────────────────────────

class TestResumoCompraParcelas:

    def test_resumo_lancamento_historico(self):
        df = _df_parcelas([
            {"id": 10, "despesa_id": -1, "numero": 1, "total": 3, "valor": 20.0,
             "vencimento": "2026-01-05", "status": "pago", "descricao": "Geladeira",
             "cartao": "Itaú", "origem_vencimento": "manual"},
            {"id": 11, "despesa_id": -1, "numero": 2, "total": 3, "valor": 20.0,
             "vencimento": "2026-02-05", "status": "pendente", "descricao": "Geladeira",
             "cartao": "Itaú", "origem_vencimento": "manual"},
            {"id": 12, "despesa_id": -1, "numero": 3, "total": 3, "valor": 20.0,
             "vencimento": "2026-03-05", "status": "pendente", "descricao": "Geladeira",
             "cartao": "Itaú", "origem_vencimento": "manual"},
        ])
        resumo = resumo_compra_parcelas(df, pid=11)
        assert resumo == {
            "manual": True, "descricao": "Geladeira", "cartao": "Itaú",
            "total": 3, "n": 3, "pagas": 1, "pendentes": 2,
            "num_min": 1, "num_max": 3,
        }

    def test_resumo_parcela_de_despesa_nao_e_manual(self):
        df = _df_parcelas([
            {"id": 1, "despesa_id": 7, "numero": 1, "total": 2, "valor": 10.0,
             "vencimento": "2026-01-10", "status": "pendente", "descricao": "Mercado",
             "cartao": "Nubank", "origem_vencimento": "fechamento"},
            {"id": 2, "despesa_id": 7, "numero": 2, "total": 2, "valor": 10.0,
             "vencimento": "2026-02-10", "status": "pendente", "descricao": "Mercado",
             "cartao": "Nubank", "origem_vencimento": "fechamento"},
        ])
        resumo = resumo_compra_parcelas(df, pid=1)
        assert resumo["manual"] is False
        assert resumo["n"] == 2

    def test_pid_inexistente_retorna_none(self):
        df = _df_parcelas([
            {"id": 1, "despesa_id": -1, "numero": 1, "total": 1, "valor": 10.0,
             "vencimento": "2026-01-10", "status": "pendente", "descricao": "X",
             "cartao": "Y", "origem_vencimento": "manual"},
        ])
        assert resumo_compra_parcelas(df, pid=999) is None

    def test_funciona_a_partir_de_qualquer_parcela_do_grupo(self):
        """O resumo deve ser idêntico não importa qual parcela da compra é
        usada como ponto de partida."""
        df = _df_parcelas([
            {"id": 10, "despesa_id": -1, "numero": 1, "total": 3, "valor": 20.0,
             "vencimento": "2026-01-05", "status": "pago", "descricao": "Geladeira",
             "cartao": "Itaú", "origem_vencimento": "manual"},
            {"id": 11, "despesa_id": -1, "numero": 2, "total": 3, "valor": 20.0,
             "vencimento": "2026-02-05", "status": "pago", "descricao": "Geladeira",
             "cartao": "Itaú", "origem_vencimento": "manual"},
            {"id": 12, "despesa_id": -1, "numero": 3, "total": 3, "valor": 20.0,
             "vencimento": "2026-03-05", "status": "pendente", "descricao": "Geladeira",
             "cartao": "Itaú", "origem_vencimento": "manual"},
        ])
        assert resumo_compra_parcelas(df, pid=10) == resumo_compra_parcelas(df, pid=12)
