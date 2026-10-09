"""
Testes das funções de I/O de logica/emprestimos.py (as que leem/gravam na
planilha): salvar_emprestimo, atualizar_emprestimo, excluir_emprestimo e
sincronizar_baixas_automaticas.

Mesma ideia de tests/test_parcelas_io.py: uma planilha FALSA em memória imita
o que o código usa do gspread, e o código real de logica/emprestimos.py e de
sheets/client.py roda de verdade em cima dela. (A planilha falsa é repetida
aqui de propósito, para este arquivo funcionar sozinho.)

Os cabeçalhos de teste deixam `proxima_data_vencimento` no FIM, que é a ordem
física real da planilha de empréstimos (a migração só acrescenta colunas ao
final) — por isso a escrita por NOME de coluna é exercitada de verdade.
"""

from datetime import date

import gspread
import pandas as pd
import pytest

import logica.emprestimos as emp

# Ordem FÍSICA realista: proxima_data_vencimento foi acrescentada depois.
HEADER = ["id", "descricao", "banco", "valor_parcela", "parcelas_restantes",
          "valor_total_devido", "criado_em", "atualizado_em", "lancado_por",
          "proxima_data_vencimento"]

HOJE = date(2026, 10, 8)


# ─────────────────────────────────────────────────────────────────────────────
# Planilha falsa
# ─────────────────────────────────────────────────────────────────────────────

class FakeSpreadsheet:
    def __init__(self, ws):
        self.ws = ws

    def batch_update(self, body):
        for req in body["requests"]:
            r = req["deleteDimension"]["range"]
            assert r["dimension"] == "ROWS" and r["sheetId"] == self.ws.id
            del self.ws.rows[r["startIndex"] - 1]


class FakeWorksheet:
    def __init__(self, title, header, rows=None):
        self.title = title
        self.id = 321
        self.header = list(header)
        self.rows = [list(r) for r in (rows or [])]
        self.col_count = len(self.header)
        self.spreadsheet = FakeSpreadsheet(self)
        self.batch_calls = []

    def row_values(self, n):
        assert n == 1
        return list(self.header)

    def col_values(self, n):
        return [self.header[n - 1]] + [
            (r[n - 1] if n - 1 < len(r) else "") for r in self.rows
        ]

    def get_all_records(self, value_render_option=None):
        assert value_render_option == "UNFORMATTED_VALUE"  # regra 2 do projeto
        out = []
        for r in self.rows:
            r = list(r) + [""] * (len(self.header) - len(r))
            out.append(dict(zip(self.header, r)))
        return out

    def _set(self, row, col, valor):
        linha = self.rows[row - 2]
        while len(linha) < col:
            linha.append("")
        linha[col - 1] = valor

    def update_cell(self, row, col, valor):
        self._set(row, col, valor)

    def batch_update(self, updates, value_input_option=None):
        self.batch_calls.append((updates, value_input_option))
        for u in updates:
            row, col = gspread.utils.a1_to_rowcol(u["range"])
            self._set(row, col, u["values"][0][0])

    def append_row(self, linha):
        assert len(linha) == len(self.header)
        self.rows.append(list(linha))
        n = len(self.rows) + 1
        return {"updates": {"updatedRange": f"{self.title}!A{n}:J{n}"}}

    def df(self):
        return pd.DataFrame(self.get_all_records(value_render_option="UNFORMATTED_VALUE"))


class FakeCache:
    def __init__(self):
        self.limpezas = 0

    def clear(self):
        self.limpezas += 1


def emprestimo(id, desc="Financiamento carro", banco="Itaú", parcela=1000.0,
               restantes=10, venc="2026-11-05", lancado_por="Ricardo"):
    return {
        "id": id, "descricao": desc, "banco": banco, "valor_parcela": parcela,
        "parcelas_restantes": restantes,
        "valor_total_devido": round(parcela * restantes, 2),
        "criado_em": "2026-01-01 10:00:00", "atualizado_em": "2026-01-01 10:00:00",
        "lancado_por": lancado_por, "proxima_data_vencimento": venc,
    }


@pytest.fixture
def ws(monkeypatch):
    """Planilha de empréstimos falsa, já ligada ao módulo logica.emprestimos."""
    planilha = FakeWorksheet("emprestimos", HEADER)
    cache = FakeCache()
    planilha.cache = cache

    class DataFixa(date):
        @classmethod
        def today(cls):
            return HOJE

    monkeypatch.setattr(emp, "get_sheet", lambda nome: planilha)
    monkeypatch.setattr(emp, "carregar_emprestimos", cache)
    monkeypatch.setattr(emp, "usuario_atual", lambda: "Jociara")
    monkeypatch.setattr(emp, "date", DataFixa)
    return planilha


def carregar(ws, *itens):
    ws.rows = [[i[c] for c in HEADER] for i in itens]


# ─────────────────────────────────────────────────────────────────────────────
# salvar_emprestimo
# ─────────────────────────────────────────────────────────────────────────────

class TestSalvarEmprestimo:

    def test_grava_cada_valor_na_coluna_certa(self, ws):
        emp.salvar_emprestimo("Empréstimo pessoal", "Nubank", 250.50, 12, date(2026, 11, 10))
        linha = ws.df().iloc[0]
        assert linha["id"] == 1
        assert linha["descricao"] == "Empréstimo pessoal"
        assert linha["banco"] == "Nubank"
        assert linha["valor_parcela"] == 250.50
        assert linha["parcelas_restantes"] == 12
        assert linha["proxima_data_vencimento"] == "2026-11-10"
        assert linha["lancado_por"] == "Jociara"

    def test_valor_total_e_calculado(self, ws):
        emp.salvar_emprestimo("X", "Y", 66.67, 3, date(2026, 11, 10))
        assert ws.df().iloc[0]["valor_total_devido"] == 200.01

    def test_id_continua_depois_dos_existentes(self, ws):
        carregar(ws, emprestimo(4), emprestimo(5))
        emp.salvar_emprestimo("X", "Y", 10.0, 2, date(2026, 11, 10))
        assert list(ws.df()["id"]) == [4, 5, 6]

    def test_limpa_o_cache(self, ws):
        emp.salvar_emprestimo("X", "Y", 10.0, 2, date(2026, 11, 10))
        assert ws.cache.limpezas == 1


# ─────────────────────────────────────────────────────────────────────────────
# atualizar_emprestimo (usada pela tela "✏️ Editar empréstimo")
# ─────────────────────────────────────────────────────────────────────────────

class TestAtualizarEmprestimo:

    def test_atualiza_todos_os_campos_editaveis(self, ws):
        carregar(ws, emprestimo(1))
        emp.atualizar_emprestimo(1, "Carro novo", "Bradesco", 1500.0, 8, date(2026, 12, 20))
        linha = ws.df().iloc[0]
        assert linha["descricao"] == "Carro novo"
        assert linha["banco"] == "Bradesco"
        assert linha["valor_parcela"] == 1500.0
        assert linha["parcelas_restantes"] == 8
        assert linha["proxima_data_vencimento"] == "2026-12-20"

    def test_recalcula_o_valor_total_devido(self, ws):
        carregar(ws, emprestimo(1, parcela=1000.0, restantes=10))
        emp.atualizar_emprestimo(1, "X", "Y", 333.33, 3, date(2026, 12, 20))
        assert ws.df().iloc[0]["valor_total_devido"] == 999.99

    def test_valor_com_centavos_e_preservado(self, ws):
        carregar(ws, emprestimo(1))
        emp.atualizar_emprestimo(1, "X", "Y", 1234.56, 10, date(2026, 12, 20))
        assert ws.df().iloc[0]["valor_parcela"] == 1234.56

    def test_zero_parcelas_quita_e_zera_o_total(self, ws):
        carregar(ws, emprestimo(1))
        emp.atualizar_emprestimo(1, "X", "Y", 1000.0, 0, date(2026, 12, 20))
        linha = ws.df().iloc[0]
        assert linha["parcelas_restantes"] == 0
        assert linha["valor_total_devido"] == 0.0

    def test_atualiza_atualizado_em_e_preserva_criado_em_e_lancado_por(self, ws):
        carregar(ws, emprestimo(1, lancado_por="Ricardo"))
        emp.atualizar_emprestimo(1, "X", "Y", 10.0, 2, date(2026, 12, 20))
        linha = ws.df().iloc[0]
        assert linha["atualizado_em"] != "2026-01-01 10:00:00"
        assert linha["criado_em"] == "2026-01-01 10:00:00"
        assert linha["lancado_por"] == "Ricardo"

    def test_nao_mexe_nos_outros_emprestimos(self, ws):
        carregar(ws, emprestimo(1), emprestimo(2, desc="Casa", banco="Caixa", parcela=2000.0))
        emp.atualizar_emprestimo(1, "Carro novo", "Bradesco", 1.0, 1, date(2026, 12, 20))
        outro = ws.df().iloc[1]
        assert outro["descricao"] == "Casa"
        assert outro["banco"] == "Caixa"
        assert outro["valor_parcela"] == 2000.0
        assert outro["parcelas_restantes"] == 10

    def test_grava_tudo_numa_unica_chamada_em_lote_raw(self, ws):
        carregar(ws, emprestimo(1))
        emp.atualizar_emprestimo(1, "X", "Y", 10.0, 2, date(2026, 12, 20))
        assert len(ws.batch_calls) == 1
        updates, opcao = ws.batch_calls[0]
        assert opcao == "RAW"
        assert len(updates) == 7  # 6 campos + atualizado_em

    def test_data_e_gravada_como_texto_iso(self, ws):
        carregar(ws, emprestimo(1))
        emp.atualizar_emprestimo(1, "X", "Y", 10.0, 2, date(2027, 1, 5))
        assert ws.rows[0][HEADER.index("proxima_data_vencimento")] == "2027-01-05"

    def test_id_inexistente_nao_grava_nada(self, ws):
        carregar(ws, emprestimo(1))
        emp.atualizar_emprestimo(999, "X", "Y", 10.0, 2, date(2026, 12, 20))
        assert ws.batch_calls == []
        assert ws.df().iloc[0]["descricao"] == "Financiamento carro"

    def test_limpa_o_cache(self, ws):
        carregar(ws, emprestimo(1))
        emp.atualizar_emprestimo(1, "X", "Y", 10.0, 2, date(2026, 12, 20))
        assert ws.cache.limpezas == 1


# ─────────────────────────────────────────────────────────────────────────────
# excluir_emprestimo
# ─────────────────────────────────────────────────────────────────────────────

class TestExcluirEmprestimo:

    def test_exclui_so_o_emprestimo_pedido(self, ws):
        carregar(ws, emprestimo(1), emprestimo(2), emprestimo(3))
        emp.excluir_emprestimo(2)
        assert list(ws.df()["id"]) == [1, 3]

    def test_planilha_vazia_nao_da_erro(self, ws):
        emp.excluir_emprestimo(1)
        assert ws.rows == []

    def test_limpa_o_cache(self, ws):
        carregar(ws, emprestimo(1))
        emp.excluir_emprestimo(1)
        assert ws.cache.limpezas == 1


# ─────────────────────────────────────────────────────────────────────────────
# sincronizar_baixas_automaticas  (hoje travado em 08/10/2026)
# ─────────────────────────────────────────────────────────────────────────────

class TestSincronizarBaixasAutomaticas:

    def test_sem_emprestimos_devolve_lista_vazia(self, ws):
        assert emp.sincronizar_baixas_automaticas() == []

    def test_vencimento_futuro_nao_baixa_nada(self, ws):
        carregar(ws, emprestimo(1, restantes=10, venc="2026-11-05"))
        assert emp.sincronizar_baixas_automaticas() == []
        assert ws.batch_calls == []
        assert ws.cache.limpezas == 0

    def test_baixa_a_parcela_que_venceu_e_avanca_a_data(self, ws):
        carregar(ws, emprestimo(1, parcela=100.0, restantes=10, venc="2026-10-05"))
        res = emp.sincronizar_baixas_automaticas()
        assert len(res) == 1 and res[0]["parcelas_baixadas"] == 1
        assert res[0]["parcelas_restantes"] == 9
        linha = ws.df().iloc[0]
        assert linha["parcelas_restantes"] == 9
        assert linha["valor_total_devido"] == 900.0
        assert linha["proxima_data_vencimento"] == "2026-11-05"

    def test_vencimento_hoje_tambem_baixa(self, ws):
        carregar(ws, emprestimo(1, restantes=3, venc="2026-10-08"))
        assert emp.sincronizar_baixas_automaticas()[0]["parcelas_baixadas"] == 1

    def test_baixa_varias_parcelas_atrasadas_de_uma_vez(self, ws):
        carregar(ws, emprestimo(1, parcela=100.0, restantes=10, venc="2026-07-20"))
        res = emp.sincronizar_baixas_automaticas()
        # 20/07, 20/08 e 20/09 já venceram; 20/10 ainda não (hoje é 08/10).
        assert res[0]["parcelas_baixadas"] == 3
        linha = ws.df().iloc[0]
        assert linha["proxima_data_vencimento"] == "2026-10-20"
        assert linha["parcelas_restantes"] == 7

    def test_para_quando_as_parcelas_acabam(self, ws):
        carregar(ws, emprestimo(1, parcela=100.0, restantes=2, venc="2026-01-10"))
        res = emp.sincronizar_baixas_automaticas()
        assert res[0]["parcelas_restantes"] == 0
        assert ws.df().iloc[0]["valor_total_devido"] == 0.0

    def test_ignora_emprestimo_ja_quitado(self, ws):
        carregar(ws, emprestimo(1, restantes=0, venc="2025-01-10"))
        assert emp.sincronizar_baixas_automaticas() == []
        assert ws.batch_calls == []

    def test_ignora_data_invalida_sem_quebrar(self, ws):
        carregar(ws, emprestimo(1, venc="não é data"), emprestimo(2, restantes=5, venc="2026-10-01"))
        res = emp.sincronizar_baixas_automaticas()
        assert [r["parcelas_baixadas"] for r in res] == [1]

    def test_varios_emprestimos_numa_unica_chamada_em_lote(self, ws):
        carregar(ws, emprestimo(1, venc="2026-10-01"), emprestimo(2, venc="2026-10-02"),
                 emprestimo(3, venc="2026-12-01"))
        res = emp.sincronizar_baixas_automaticas()
        assert len(res) == 2
        assert len(ws.batch_calls) == 1
        assert len(ws.batch_calls[0][0]) == 8  # 4 campos × 2 empréstimos
        assert ws.batch_calls[0][1] == "RAW"
        assert ws.cache.limpezas == 1

    def test_escreve_nas_colunas_certas_com_data_no_fim_da_planilha(self, ws):
        carregar(ws, emprestimo(1, parcela=100.0, restantes=10, venc="2026-10-05"))
        emp.sincronizar_baixas_automaticas()
        linha = ws.df().iloc[0]
        assert linha["descricao"] == "Financiamento carro"
        assert linha["banco"] == "Itaú"
        assert linha["valor_parcela"] == 100.0
        assert linha["lancado_por"] == "Ricardo"

    def test_editar_com_data_passada_dispara_a_baixa_na_sequencia(self, ws):
        """Documenta o aviso da tela de edição: ao salvar uma data que já
        passou, a baixa automática age assim que a aba é aberta de novo."""
        carregar(ws, emprestimo(1, parcela=100.0, restantes=10, venc="2026-11-05"))
        emp.atualizar_emprestimo(1, "Carro", "Itaú", 100.0, 10, date(2026, 9, 5))
        res = emp.sincronizar_baixas_automaticas()
        assert res[0]["parcelas_baixadas"] == 2  # 05/09 e 05/10
        linha = ws.df().iloc[0]
        assert linha["parcelas_restantes"] == 8
        assert linha["proxima_data_vencimento"] == "2026-11-05"
