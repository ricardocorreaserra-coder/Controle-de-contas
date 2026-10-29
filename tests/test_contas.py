"""
Testes das CONTAS de entrada das receitas (Santander, Itaú, Mercado Pago...):
campo `conta` gravado/alterado por NOME de coluna e a soma de entradas por
conta (`entradas_por_conta`), usada no quadro da tela Conta Corrente.

Planilha falsa em memória (repetida de propósito, como nos outros testes de I/O,
para este arquivo funcionar sozinho).
"""

import gspread
import pandas as pd
import pytest

import logica.receitas as rec
from config import CONTAS, EXPECTED_HEADERS, SEM_CONTA

HEADER = EXPECTED_HEADERS["receitas"]


class FakeSpreadsheet:
    def __init__(self, ws):
        self.ws = ws

    def batch_update(self, body):
        for req in body["requests"]:
            r = req["deleteDimension"]["range"]
            del self.ws.rows[r["startIndex"] - 1]


class FakeWorksheet:
    def __init__(self, header, rows=None):
        self.title = "receitas"
        self.id = 777
        self.header = list(header)
        self.rows = [list(r) for r in (rows or [])]
        self.col_count = len(self.header)
        self.spreadsheet = FakeSpreadsheet(self)

    def row_values(self, n):
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
        assert value_input_option == "RAW"
        for u in updates:
            row, col = gspread.utils.a1_to_rowcol(u["range"])
            self._set(row, col, u["values"][0][0])

    def append_row(self, linha):
        assert len(linha) == len(self.header)
        self.rows.append(list(linha))
        n = len(self.rows) + 1
        return {"updates": {"updatedRange": f"receitas!A{n}:K{n}"}}

    def registros(self):
        return self.get_all_records(value_render_option="UNFORMATTED_VALUE")


class FakeCache:
    def __init__(self):
        self.limpezas = 0

    def clear(self):
        self.limpezas += 1


def _monta(monkeypatch, header):
    planilha = FakeWorksheet(header)
    cache = FakeCache()
    planilha.cache = cache
    monkeypatch.setattr(rec, "get_sheet", lambda nome: planilha)
    monkeypatch.setattr(rec, "carregar_receitas", cache)
    monkeypatch.setattr(rec, "usuario_atual", lambda: "Sara")
    return planilha


@pytest.fixture
def ws(monkeypatch):
    return _monta(monkeypatch, HEADER)


@pytest.fixture
def ws_ordem_trocada(monkeypatch):
    # `id` continua na coluna A (regra 12), mas as demais colunas mudam de lugar.
    return _monta(monkeypatch, ["id", "conta", "valor", "lancado_por", "data", "descricao",
                                "categoria", "observacao", "criado_em", "recorrente",
                                "recorrencia_fim"])


# ── Configuração ──────────────────────────────────────────────────────────────

class TestConfiguracao:
    def test_coluna_conta_e_a_ultima(self):
        # Regra 1: coluna nova sempre no FINAL.
        assert HEADER[-1] == "conta"
        assert HEADER.count("conta") == 1

    def test_lista_de_contas_pedida(self):
        assert CONTAS == ["Santander Rio", "Santander Rio Bonito", "Itaú",
                          "Mercado Pago Sara", "Mercado Pago Ricardo"]

    def test_sem_conta_nao_e_uma_das_contas(self):
        assert SEM_CONTA not in CONTAS


# ── Gravação ──────────────────────────────────────────────────────────────────

class TestSalvarReceitaComConta:
    def test_grava_a_conta(self, ws):
        rec.salvar_receita("Salário", 5000.55, "2026-10-05", "Salário", "", conta="Itaú")
        (linha,) = ws.registros()
        assert linha["conta"] == "Itaú"
        assert linha["valor"] == 5000.55
        assert linha["lancado_por"] == "Sara"
        assert ws.cache.limpezas == 1

    def test_grava_por_nome_mesmo_com_colunas_em_outra_ordem(self, ws_ordem_trocada):
        rec.salvar_receita("Freela", 123.45, "2026-10-07", "Freelance", "ok",
                           conta="Mercado Pago Ricardo")
        (linha,) = ws_ordem_trocada.registros()
        assert linha["conta"] == "Mercado Pago Ricardo"
        assert linha["descricao"] == "Freela"
        assert linha["valor"] == 123.45
        assert linha["data"] == "2026-10-07"
        assert linha["id"] == 1

    def test_sem_informar_conta_grava_vazio(self, ws):
        # chamadas antigas (sem o argumento) continuam funcionando
        rec.salvar_receita("Antiga", 10.0, "2026-10-01", "Outros", "")
        assert ws.registros()[0]["conta"] == ""


class TestAtualizarReceitaComConta:
    def _semear(self, ws):
        rec.salvar_receita("Salário", 1000.0, "2026-10-05", "Salário", "", conta="Itaú")
        rec.salvar_receita("Aluguel", 2000.0, "2026-10-06", "Outros", "", conta="Itaú")

    def test_altera_a_conta(self, ws):
        self._semear(ws)
        rec.atualizar_receita(1, "Salário", 1000.0, "2026-10-05", "Salário", "",
                              conta="Santander Rio")
        r1, r2 = ws.registros()
        assert r1["conta"] == "Santander Rio"
        assert r2["conta"] == "Itaú"            # outra receita intacta

    def test_conta_none_nao_mexe_na_conta(self, ws):
        self._semear(ws)
        rec.atualizar_receita(1, "Novo nome", 999.99, "2026-10-09", "Outros", "x")
        r1, _ = ws.registros()
        assert r1["conta"] == "Itaú"
        assert r1["descricao"] == "Novo nome"
        assert r1["valor"] == 999.99

    def test_conta_vazia_limpa_a_conta(self, ws):
        self._semear(ws)
        rec.atualizar_receita(2, "Aluguel", 2000.0, "2026-10-06", "Outros", "", conta="")
        assert ws.registros()[1]["conta"] == ""

    def test_edicao_por_nome_com_colunas_em_outra_ordem(self, ws_ordem_trocada):
        rec.salvar_receita("A", 10.5, "2026-10-01", "Outros", "", conta="Itaú")
        rec.atualizar_receita(1, "A2", 20.25, "2026-10-02", "Salário", "obs",
                              conta="Mercado Pago Sara")
        (linha,) = ws_ordem_trocada.registros()
        assert (linha["descricao"], linha["valor"], linha["data"], linha["conta"]) == \
            ("A2", 20.25, "2026-10-02", "Mercado Pago Sara")


# ── Soma por conta ────────────────────────────────────────────────────────────

def df(*itens):
    return pd.DataFrame([{"valor": v, "conta": c} for v, c in itens])


class TestEntradasPorConta:
    def test_soma_por_conta_e_mostra_todas_as_contas(self):
        r = dict(rec.entradas_por_conta(df((1000.5, "Itaú"), (200.25, "Itaú"),
                                           (50.0, "Santander Rio"))))
        assert r["Itaú"] == pytest.approx(1200.75)
        assert r["Santander Rio"] == 50.0
        assert r["Mercado Pago Sara"] == 0.0     # sem entrada no período, mas aparece
        for c in CONTAS:
            assert c in r

    def test_ordem_das_contas_segue_a_lista(self):
        nomes = [c for c, _ in rec.entradas_por_conta(df((1.0, "Itaú")))]
        assert nomes == CONTAS

    def test_sem_conta_vai_para_o_fim_e_so_aparece_se_existir(self):
        sem = rec.entradas_por_conta(df((10.0, "Itaú")))
        assert SEM_CONTA not in [c for c, _ in sem]
        com = rec.entradas_por_conta(df((10.0, "Itaú"), (7.5, ""), (2.5, None)))
        assert com[-1] == (SEM_CONTA, 10.0)

    def test_conta_antiga_fora_da_lista_nao_some(self):
        # regra 11: conta renomeada/removida do config continua nos lançamentos
        r = rec.entradas_por_conta(df((30.0, "Banco Velho"), (5.0, "Itaú")))
        nomes = [c for c, _ in r]
        assert "Banco Velho" in nomes
        assert nomes.index("Banco Velho") == len(CONTAS)   # logo depois das contas atuais
        assert dict(r)["Banco Velho"] == 30.0

    def test_espacos_e_texto_sem_conta_literal(self):
        r = dict(rec.entradas_por_conta(df((10.0, "  Itaú "), (4.0, SEM_CONTA))))
        assert r["Itaú"] == 10.0
        assert r[SEM_CONTA] == 4.0

    def test_total_das_contas_bate_com_o_total_das_receitas(self):
        d = df((1234.56, "Itaú"), (0.01, "Santander Rio"), (99.99, ""), (10.0, "Outro"))
        assert sum(v for _, v in rec.entradas_por_conta(d)) == pytest.approx(1344.56)

    def test_valor_nao_numerico_vira_zero(self):
        r = dict(rec.entradas_por_conta(df(("abc", "Itaú"), (5.0, "Itaú"))))
        assert r["Itaú"] == 5.0

    def test_dataframe_vazio_ou_sem_coluna_conta(self):
        assert [v for _, v in rec.entradas_por_conta(pd.DataFrame())] == [0.0] * len(CONTAS)
        assert [v for _, v in rec.entradas_por_conta(None)] == [0.0] * len(CONTAS)
        # planilha antiga, sem a coluna `conta`: tudo cai em "Sem conta"
        r = rec.entradas_por_conta(pd.DataFrame([{"valor": 12.5}]))
        assert r[-1] == (SEM_CONTA, 12.5)
