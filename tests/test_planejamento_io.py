"""
Testes das funções de I/O de logica/planejamento.py que gravam na planilha
`planejamento`: salvar_planejamento, salvar_planejamento_replicado,
atualizar_planejamento (usada pela tela "✏️ Editar item de planejamento") e
excluir_planejamento.

Mesma ideia de tests/test_parcelas_io.py e tests/test_emprestimos_io.py: uma
planilha FALSA em memória imita o que o código usa do gspread, e o código real
roda de verdade em cima dela. (A planilha falsa é repetida aqui de propósito,
para este arquivo funcionar sozinho.)
"""

import gspread
import pandas as pd
import pytest

import logica.planejamento as plan
from config import EXPECTED_HEADERS

HEADER = EXPECTED_HEADERS["planejamento"]


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
        self.id = 555
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
        return {"updates": {"updatedRange": f"{self.title}!A{n}:I{n}"}}

    def append_rows(self, payload):
        primeira = len(self.rows) + 2
        for linha in payload:
            assert len(linha) == len(self.header)
            self.rows.append(list(linha))
        ultima = primeira + len(payload) - 1
        return {"updates": {"updatedRange": f"{self.title}!A{primeira}:I{ultima}"}}

    def df(self):
        return pd.DataFrame(self.get_all_records(value_render_option="UNFORMATTED_VALUE"))


class FakeCache:
    def __init__(self):
        self.limpezas = 0

    def clear(self):
        self.limpezas += 1


def item(id, tipo="despesa", desc="IPTU", valor=1234.56, mes="2027-01",
         cat="Moradia", obs="cota única", criado_em="2026-09-01 08:00:00",
         lancado_por="Ricardo"):
    return {"id": id, "tipo": tipo, "descricao": desc, "valor": valor, "mes": mes,
            "categoria": cat, "observacao": obs, "criado_em": criado_em,
            "lancado_por": lancado_por}


@pytest.fixture
def ws(monkeypatch):
    planilha = FakeWorksheet("planejamento", HEADER)
    cache = FakeCache()
    planilha.cache = cache
    monkeypatch.setattr(plan, "get_sheet", lambda nome: planilha)
    monkeypatch.setattr(plan, "carregar_planejamento", cache)
    monkeypatch.setattr(plan, "usuario_atual", lambda: "Jociara")
    return planilha


def carregar(ws, *itens):
    ws.rows = [[i[c] for c in ws.header] for i in itens]


# ─────────────────────────────────────────────────────────────────────────────
# salvar_planejamento / salvar_planejamento_replicado
# ─────────────────────────────────────────────────────────────────────────────

class TestSalvarPlanejamento:

    def test_grava_cada_valor_na_coluna_certa(self, ws):
        plan.salvar_planejamento("receita", "13º salário", 4321.09, "2026-12", "Salário", "metade")
        linha = ws.df().iloc[0]
        assert linha["id"] == 1
        assert linha["tipo"] == "receita"
        assert linha["descricao"] == "13º salário"
        assert linha["valor"] == 4321.09
        assert linha["mes"] == "2026-12"
        assert linha["categoria"] == "Salário"
        assert linha["observacao"] == "metade"
        assert linha["lancado_por"] == "Jociara"

    def test_id_continua_depois_dos_existentes(self, ws):
        carregar(ws, item(7), item(8))
        plan.salvar_planejamento("despesa", "X", 10.0, "2027-01", "", "")
        assert list(ws.df()["id"]) == [7, 8, 9]

    def test_limpa_o_cache(self, ws):
        plan.salvar_planejamento("despesa", "X", 10.0, "2027-01", "", "")
        assert ws.cache.limpezas == 1

    def test_replicado_cria_uma_linha_por_mes_com_ids_diferentes(self, ws):
        meses = ["2026-11", "2026-12", "2027-01"]
        plan.salvar_planejamento_replicado("despesa", "Internet", 99.9, meses, "Moradia", "")
        df = ws.df()
        assert list(df["mes"]) == meses
        assert list(df["id"]) == [1, 2, 3]
        assert set(df["valor"]) == {99.9}
        assert set(df["lancado_por"]) == {"Jociara"}
        assert ws.cache.limpezas == 1


# ─────────────────────────────────────────────────────────────────────────────
# atualizar_planejamento
# ─────────────────────────────────────────────────────────────────────────────

class TestAtualizarPlanejamento:

    def test_atualiza_todos_os_campos_editaveis(self, ws):
        carregar(ws, item(1))
        plan.atualizar_planejamento(1, "IPTU 2027", 999.99, "2027-03", "Saúde", "parcelado")
        linha = ws.df().iloc[0]
        assert linha["descricao"] == "IPTU 2027"
        assert linha["valor"] == 999.99
        assert linha["mes"] == "2027-03"
        assert linha["categoria"] == "Saúde"
        assert linha["observacao"] == "parcelado"

    def test_valor_com_centavos_e_preservado(self, ws):
        carregar(ws, item(1))
        plan.atualizar_planejamento(1, "X", 1234.56, "2027-01", "", "")
        assert ws.df().iloc[0]["valor"] == 1234.56

    def test_nao_altera_tipo_criado_em_nem_lancado_por(self, ws):
        carregar(ws, item(1, tipo="receita", lancado_por="Ricardo", criado_em="2026-09-01 08:00:00"))
        plan.atualizar_planejamento(1, "X", 10.0, "2027-03", "", "")
        linha = ws.df().iloc[0]
        assert linha["tipo"] == "receita"
        assert linha["criado_em"] == "2026-09-01 08:00:00"
        assert linha["lancado_por"] == "Ricardo"
        assert linha["id"] == 1

    def test_nao_mexe_nos_outros_itens(self, ws):
        carregar(ws, item(1), item(2, desc="Seguro", valor=500.0, mes="2027-05"))
        plan.atualizar_planejamento(1, "IPTU 2027", 1.0, "2027-03", "", "")
        outro = ws.df().iloc[1]
        assert outro["descricao"] == "Seguro"
        assert outro["valor"] == 500.0
        assert outro["mes"] == "2027-05"

    def test_mes_e_gravado_como_texto_com_raw_em_uma_unica_chamada(self, ws):
        carregar(ws, item(1))
        plan.atualizar_planejamento(1, "X", 10.0, "2027-03", "", "")
        assert len(ws.batch_calls) == 1
        updates, opcao = ws.batch_calls[0]
        assert opcao == "RAW"
        assert len(updates) == 5
        assert ws.rows[0][HEADER.index("mes")] == "2027-03"

    def test_escreve_por_nome_com_colunas_em_ordem_fisica_diferente(self, ws):
        header = ["id", "observacao", "valor", "tipo", "mes", "descricao",
                  "categoria", "criado_em", "lancado_por"]
        ws.header = header
        carregar(ws, item(1, tipo="despesa", valor=10.0, desc="A", mes="2027-01", obs="o"))
        plan.atualizar_planejamento(1, "B", 20.5, "2027-02", "Lazer", "nova")
        linha = ws.df().iloc[0]
        assert (linha["descricao"], linha["valor"], linha["mes"]) == ("B", 20.5, "2027-02")
        assert (linha["categoria"], linha["observacao"]) == ("Lazer", "nova")
        assert linha["tipo"] == "despesa"

    def test_id_inexistente_nao_grava_nada(self, ws):
        carregar(ws, item(1))
        plan.atualizar_planejamento(999, "X", 10.0, "2027-03", "", "")
        assert ws.batch_calls == []
        assert ws.df().iloc[0]["descricao"] == "IPTU"

    def test_planilha_vazia_nao_da_erro(self, ws):
        plan.atualizar_planejamento(1, "X", 10.0, "2027-03", "", "")
        assert ws.batch_calls == []

    def test_limpa_o_cache(self, ws):
        carregar(ws, item(1))
        plan.atualizar_planejamento(1, "X", 10.0, "2027-03", "", "")
        assert ws.cache.limpezas == 1


# ─────────────────────────────────────────────────────────────────────────────
# excluir_planejamento
# ─────────────────────────────────────────────────────────────────────────────

class TestExcluirPlanejamento:

    def test_exclui_so_o_item_pedido(self, ws):
        carregar(ws, item(1), item(2), item(3))
        plan.excluir_planejamento(2)
        assert list(ws.df()["id"]) == [1, 3]

    def test_planilha_vazia_nao_da_erro(self, ws):
        plan.excluir_planejamento(1)
        assert ws.rows == []

    def test_limpa_o_cache(self, ws):
        carregar(ws, item(1))
        plan.excluir_planejamento(1)
        assert ws.cache.limpezas == 1
