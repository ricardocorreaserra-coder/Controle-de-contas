"""
Testes das funções de I/O de logica/parcelas.py (as que leem/gravam na
planilha): salvar_parcela_manual, excluir_compra_parcelas,
corrigir_total_parcelas, alterar_lancamento_parcela,
atualizar_vencimento_parcela, atualizar_parcela e baixar_fatura_mes.

Como funciona: em vez de falar com o Google Sheets, os testes usam uma
planilha FALSA em memória (FakeWorksheet) que imita só o que o código usa do
gspread (row_values, get_all_records, batch_update, update_cell, append_rows,
col_values, add_cols e a exclusão de linhas em lote). O código real de
logica/parcelas.py e de sheets/client.py roda de verdade em cima dela.

A planilha falsa também ajuda a travar regras do projeto
(nos testes de ordem de colunas, o "id" fica sempre na coluna A, como na
planilha real, pois sheets/client.py assume isso na checagem de colisão):
- leitura sempre com value_render_option="UNFORMATTED_VALUE";
- escrita por NOME de coluna (testamos com colunas em ordem física diferente);
- escritas em lote com uma única chamada a batch_update;
- datas gravadas como texto ISO com value_input_option="RAW".
"""

from datetime import date

import gspread
import pandas as pd
import pytest

import logica.parcelas as parcelas
from config import DIA_VENCIMENTO_PADRAO, EXPECTED_HEADERS


# ─────────────────────────────────────────────────────────────────────────────
# Planilha falsa
# ─────────────────────────────────────────────────────────────────────────────

class FakeSpreadsheet:
    """Só implementa o batch_update com deleteDimension, usado por delete_rows_batch."""

    def __init__(self, ws):
        self.ws = ws
        self.chamadas = []

    def batch_update(self, body):
        self.chamadas.append(body)
        for req in body["requests"]:
            r = req["deleteDimension"]["range"]
            assert r["dimension"] == "ROWS"
            assert r["sheetId"] == self.ws.id
            # startIndex é 0-based contando o cabeçalho; rows guarda só os dados
            del self.ws.rows[r["startIndex"] - 1]


class FakeWorksheet:
    def __init__(self, title, header, rows=None, col_count=None):
        self.title = title
        self.id = 123
        self.header = list(header)
        self.rows = [list(r) for r in (rows or [])]
        self.col_count = col_count if col_count is not None else len(self.header)
        self.spreadsheet = FakeSpreadsheet(self)
        self.batch_calls = []      # [(updates, value_input_option)]
        self.cell_updates = []     # [(row, col, valor)]
        self.cols_added = 0

    # ── leitura ──
    def row_values(self, n):
        assert n == 1
        return list(self.header)

    def col_values(self, n):
        return [self.header[n - 1]] + [
            (r[n - 1] if n - 1 < len(r) else "") for r in self.rows
        ]

    def get_all_records(self, value_render_option=None):
        # Regra 2 do projeto: sempre ler o valor bruto da célula.
        assert value_render_option == "UNFORMATTED_VALUE"
        registros = []
        for r in self.rows:
            r = list(r) + [""] * (len(self.header) - len(r))
            registros.append(dict(zip(self.header, r)))
        return registros

    # ── escrita ──
    def _set(self, row, col, valor):
        if row == 1:
            while len(self.header) < col:
                self.header.append("")
            self.header[col - 1] = valor
            return
        while len(self.rows) < row - 1:
            self.rows.append([""] * len(self.header))
        linha = self.rows[row - 2]
        while len(linha) < col:
            linha.append("")
        linha[col - 1] = valor

    def update_cell(self, row, col, valor):
        self.cell_updates.append((row, col, valor))
        self._set(row, col, valor)

    def batch_update(self, updates, value_input_option=None):
        self.batch_calls.append((updates, value_input_option))
        for u in updates:
            row, col = gspread.utils.a1_to_rowcol(u["range"])
            self._set(row, col, u["values"][0][0])

    def add_cols(self, n):
        self.cols_added += n
        self.col_count += n

    def append_rows(self, payload):
        primeira = len(self.rows) + 2  # linha 1 é o cabeçalho
        for linha in payload:
            assert len(linha) == len(self.header)
            self.rows.append(list(linha))
        ultima = primeira + len(payload) - 1
        return {"updates": {"updatedRange": f"{self.title}!A{primeira}:K{ultima}"}}

    # ── conveniência dos testes ──
    def df(self):
        data = self.get_all_records(value_render_option="UNFORMATTED_VALUE")
        return pd.DataFrame(data)

    def linhas_por_id(self):
        d = self.df()
        return {int(r["id"]): r for _, r in d.iterrows()}


class FakeCache:
    """Substitui o carregar_* decorado com st.cache_data: só conta os .clear()."""

    def __init__(self, retorno=None):
        self.retorno = retorno
        self.limpezas = 0

    def clear(self):
        self.limpezas += 1

    def __call__(self):
        return self.retorno


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures e construtores
# ─────────────────────────────────────────────────────────────────────────────

HEADER_PARCELAS = EXPECTED_HEADERS["parcelas"]


def parcela(id, numero, total=3, despesa_id=-1, valor=100.0, venc="2026-01-10",
            status="pendente", desc="Geladeira", cartao="Nubank",
            origem="manual", data_compra=""):
    return {
        "id": id, "despesa_id": despesa_id, "numero": numero, "total": total,
        "valor": valor, "vencimento": venc, "status": status, "descricao": desc,
        "cartao": cartao, "origem_vencimento": origem, "data_compra": data_compra,
    }


def montar_ws(linhas, header=None, nome="parcelas", col_count=None):
    header = header or HEADER_PARCELAS
    rows = [[l.get(col, "") for col in header] for l in linhas]
    return FakeWorksheet(nome, header, rows, col_count=col_count)


class Ambiente:
    def __init__(self, monkeypatch):
        self.mp = monkeypatch
        self.abas = {}
        self.cache_parcelas = FakeCache()
        self.cache_cartoes = FakeCache(pd.DataFrame())
        monkeypatch.setattr(parcelas, "get_sheet", lambda nome: self.abas[nome])
        monkeypatch.setattr(parcelas, "carregar_parcelas", self.cache_parcelas)
        monkeypatch.setattr(parcelas, "carregar_cartoes", self.cache_cartoes)

    def parcelas(self, linhas, **kw):
        ws = montar_ws(linhas, **kw)
        self.abas["parcelas"] = ws
        return ws

    def despesas(self, linhas):
        header = EXPECTED_HEADERS["despesas"]
        rows = [[l.get(col, "") for col in header] for l in linhas]
        ws = FakeWorksheet("despesas", header, rows)
        self.abas["despesas"] = ws
        return ws

    def cartoes(self, **dias_vencimento):
        """cartoes(Nubank=12, Itaú=17) → DataFrame que carregar_cartoes devolve."""
        self.cache_cartoes.retorno = pd.DataFrame([
            {"id": i + 1, "nome": nome, "dia_vencimento": dia}
            for i, (nome, dia) in enumerate(dias_vencimento.items())
        ])


@pytest.fixture
def amb(monkeypatch):
    return Ambiente(monkeypatch)


def compra_3x(id_inicial=1, **kw):
    """Compra histórica de 3 parcelas com ids consecutivos."""
    base = dict(desc="Geladeira", cartao="Nubank", valor=100.0)
    base.update(kw)
    return [
        parcela(id_inicial + 0, 1, venc="2026-01-10", status="pago", **base),
        parcela(id_inicial + 1, 2, venc="2026-02-10", **base),
        parcela(id_inicial + 2, 3, venc="2026-03-10", **base),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# salvar_parcela_manual
# ─────────────────────────────────────────────────────────────────────────────

class TestSalvarParcelaManual:

    def test_grava_da_parcela_inicial_ate_a_total(self, amb):
        ws = amb.parcelas([])
        amb.cartoes(Nubank=12)
        parcelas.salvar_parcela_manual("Nubank", "Sofá", 250.0, 3, 5, "2026-03-12", "")
        df = ws.df()
        assert list(df["numero"]) == [3, 4, 5]
        assert list(df["vencimento"]) == ["2026-03-12", "2026-04-12", "2026-05-12"]
        assert set(df["total"]) == {5}
        assert set(df["despesa_id"]) == {-1}
        assert set(df["status"]) == {"pendente"}
        assert set(df["origem_vencimento"]) == {"manual"}
        assert set(df["descricao"]) == {"Sofá"}
        assert set(df["cartao"]) == {"Nubank"}

    def test_ids_continuam_depois_dos_existentes(self, amb):
        ws = amb.parcelas(compra_3x(id_inicial=10))
        amb.cartoes(Nubank=10)
        parcelas.salvar_parcela_manual("Nubank", "Sofá", 50.0, 1, 2, "2026-05-10", "")
        assert list(ws.df()["id"]) == [10, 11, 12, 13, 14]

    def test_valor_com_centavos_e_preservado(self, amb):
        ws = amb.parcelas([])
        amb.cartoes(Nubank=10)
        parcelas.salvar_parcela_manual("Nubank", "Café", 12.34, 1, 2, "2026-05-10", "")
        assert list(ws.df()["valor"]) == [12.34, 12.34]

    def test_dia_do_vencimento_vem_do_cartao_e_respeita_fim_de_mes(self, amb):
        ws = amb.parcelas([])
        amb.cartoes(Nubank=31)
        parcelas.salvar_parcela_manual("Nubank", "TV", 100.0, 1, 3, "2027-01-31", "")
        assert list(ws.df()["vencimento"]) == ["2027-01-31", "2027-02-28", "2027-03-31"]

    def test_cartao_desconhecido_usa_dia_padrao(self, amb):
        ws = amb.parcelas([])
        amb.cartoes(Nubank=12)
        parcelas.salvar_parcela_manual("Outro Banco", "TV", 100.0, 1, 2, "2026-05-01", "")
        dias = [int(v[-2:]) for v in ws.df()["vencimento"]]
        assert dias == [DIA_VENCIMENTO_PADRAO] * 2

    def test_sem_cartoes_cadastrados_usa_dia_padrao(self, amb):
        ws = amb.parcelas([])
        parcelas.salvar_parcela_manual("Nubank", "TV", 100.0, 1, 1, "2026-05-01", "")
        assert int(ws.df().iloc[0]["vencimento"][-2:]) == DIA_VENCIMENTO_PADRAO

    def test_data_compra_cria_coluna_que_faltava_e_grava_em_todas(self, amb):
        header_sem = [c for c in HEADER_PARCELAS if c != "data_compra"]
        ws = amb.parcelas([], header=header_sem)
        amb.cartoes(Nubank=10)
        parcelas.salvar_parcela_manual("Nubank", "TV", 100.0, 1, 2, "2026-05-10", "",
                                       data_compra="2026-04-01")
        assert ws.header[-1] == "data_compra"
        assert ws.cols_added == 1
        assert list(ws.df()["data_compra"]) == ["2026-04-01", "2026-04-01"]

    def test_sem_data_compra_nao_cria_coluna(self, amb):
        header_sem = [c for c in HEADER_PARCELAS if c != "data_compra"]
        ws = amb.parcelas([], header=header_sem)
        amb.cartoes(Nubank=10)
        parcelas.salvar_parcela_manual("Nubank", "TV", 100.0, 1, 2, "2026-05-10", "")
        assert "data_compra" not in ws.header
        assert ws.cols_added == 0

    def test_escreve_por_nome_mesmo_com_colunas_em_ordem_fisica_diferente(self, amb):
        header = ["id", "status", "valor", "descricao", "despesa_id", "numero", "total",
                  "vencimento", "cartao", "data_compra", "origem_vencimento"]
        ws = amb.parcelas([], header=header)
        amb.cartoes(Nubank=10)
        parcelas.salvar_parcela_manual("Nubank", "TV", 77.7, 1, 2, "2026-05-10", "",
                                       data_compra="2026-04-01")
        primeira = ws.df().iloc[0]
        assert primeira["status"] == "pendente"
        assert primeira["valor"] == 77.7
        assert primeira["descricao"] == "TV"
        assert primeira["numero"] == 1
        assert primeira["data_compra"] == "2026-04-01"

    def test_limpa_o_cache_de_parcelas(self, amb):
        amb.parcelas([])
        amb.cartoes(Nubank=10)
        parcelas.salvar_parcela_manual("Nubank", "TV", 100.0, 1, 1, "2026-05-10", "")
        assert amb.cache_parcelas.limpezas == 1


# ─────────────────────────────────────────────────────────────────────────────
# excluir_compra_parcelas
# ─────────────────────────────────────────────────────────────────────────────

class TestExcluirCompraParcelas:

    def test_exclui_todas_as_parcelas_da_compra_pagas_e_pendentes(self, amb):
        outra = [parcela(20, 1, total=1, desc="Notebook")]
        ws = amb.parcelas(compra_3x(id_inicial=1) + outra)
        qtd = parcelas.excluir_compra_parcelas(2)
        assert qtd == 3
        assert list(ws.df()["id"]) == [20]

    def test_separa_duas_compras_com_mesma_descricao(self, amb):
        netflix_a = compra_3x(id_inicial=1, desc="Netflix")
        netflix_b = compra_3x(id_inicial=4, desc="Netflix")
        ws = amb.parcelas(netflix_a + netflix_b)
        qtd = parcelas.excluir_compra_parcelas(5)  # parcela 2 da segunda compra
        assert qtd == 3
        assert list(ws.df()["id"]) == [1, 2, 3]

    def test_parcela_de_despesa_nao_pode_ser_excluida_por_aqui(self, amb):
        linhas = [parcela(1, 1, total=2, despesa_id=7), parcela(2, 2, total=2, despesa_id=7)]
        ws = amb.parcelas(linhas)
        with pytest.raises(ValueError, match="veio de uma despesa"):
            parcelas.excluir_compra_parcelas(1)
        assert len(ws.rows) == 2
        assert amb.cache_parcelas.limpezas == 0

    def test_parcela_inexistente_levanta_erro(self, amb):
        ws = amb.parcelas(compra_3x())
        with pytest.raises(ValueError, match="não encontrada"):
            parcelas.excluir_compra_parcelas(999)
        assert len(ws.rows) == 3

    def test_planilha_vazia_levanta_erro(self, amb):
        amb.parcelas([])
        with pytest.raises(ValueError, match="não encontrada"):
            parcelas.excluir_compra_parcelas(1)

    def test_limpa_o_cache(self, amb):
        amb.parcelas(compra_3x())
        parcelas.excluir_compra_parcelas(1)
        assert amb.cache_parcelas.limpezas == 1


# ─────────────────────────────────────────────────────────────────────────────
# corrigir_total_parcelas
# ─────────────────────────────────────────────────────────────────────────────

class TestCorrigirTotalParcelas:

    @pytest.mark.parametrize("novo_total", [0, -1, 49, 100])
    def test_total_fora_de_1_a_48_e_recusado(self, amb, novo_total):
        ws = amb.parcelas(compra_3x())
        antes = [list(r) for r in ws.rows]
        with pytest.raises(ValueError, match="entre 1 e 48"):
            parcelas.corrigir_total_parcelas(1, novo_total)
        assert ws.rows == antes
        assert ws.batch_calls == []

    def test_aumentar_cria_as_parcelas_que_faltam(self, amb):
        linhas = compra_3x(valor=99.9, data_compra="2025-12-20")
        ws = amb.parcelas(linhas)
        removidas, criadas = parcelas.corrigir_total_parcelas(2, 5)
        assert (removidas, criadas) == (0, 2)
        df = ws.df()
        assert list(df["numero"]) == [1, 2, 3, 4, 5]
        assert list(df["vencimento"])[3:] == ["2026-04-10", "2026-05-10"]
        novas = df.iloc[3:]
        assert set(novas["valor"]) == {99.9}
        assert set(novas["status"]) == {"pendente"}
        assert set(novas["despesa_id"]) == {-1}
        assert set(novas["origem_vencimento"]) == {"manual"}
        assert set(novas["descricao"]) == {"Geladeira"}
        assert set(novas["cartao"]) == {"Nubank"}
        assert set(novas["data_compra"]) == {"2025-12-20"}
        assert list(df["id"]) == [1, 2, 3, 4, 5]

    def test_aumentar_atualiza_o_total_de_todas_as_parcelas(self, amb):
        ws = amb.parcelas(compra_3x())
        parcelas.corrigir_total_parcelas(1, 5)
        assert set(ws.df()["total"]) == {5}

    def test_aumentar_respeita_fim_de_mes(self, amb):
        linhas = [parcela(1, 1, total=1, venc="2026-01-31")]
        ws = amb.parcelas(linhas)
        parcelas.corrigir_total_parcelas(1, 3)
        assert list(ws.df()["vencimento"]) == ["2026-01-31", "2026-02-28", "2026-03-31"]

    def test_aumentar_sem_data_compra_deixa_o_campo_vazio(self, amb):
        ws = amb.parcelas(compra_3x())
        parcelas.corrigir_total_parcelas(1, 4)
        assert ws.df().iloc[3]["data_compra"] == ""

    def test_aumentar_compra_que_comecou_depois_da_parcela_1(self, amb):
        linhas = [
            parcela(1, 3, total=5, venc="2026-03-10"),
            parcela(2, 4, total=5, venc="2026-04-10"),
            parcela(3, 5, total=5, venc="2026-05-10"),
        ]
        ws = amb.parcelas(linhas)
        removidas, criadas = parcelas.corrigir_total_parcelas(1, 6)
        assert (removidas, criadas) == (0, 1)
        ultima = ws.df().iloc[-1]
        assert ultima["numero"] == 6
        assert ultima["vencimento"] == "2026-06-10"

    def test_reduzir_remove_as_parcelas_excedentes(self, amb):
        linhas = [
            parcela(1, 1, total=5, venc="2026-01-10", status="pago"),
            parcela(2, 2, total=5, venc="2026-02-10"),
            parcela(3, 3, total=5, venc="2026-03-10"),
            parcela(4, 4, total=5, venc="2026-04-10"),
            parcela(5, 5, total=5, venc="2026-05-10"),
        ]
        ws = amb.parcelas(linhas)
        removidas, criadas = parcelas.corrigir_total_parcelas(2, 3)
        assert (removidas, criadas) == (2, 0)
        df = ws.df()
        assert list(df["numero"]) == [1, 2, 3]
        assert set(df["total"]) == {3}

    def test_reduzir_recusa_se_alguma_removida_estiver_paga(self, amb):
        linhas = [
            parcela(1, 1, total=3, venc="2026-01-10", status="pago"),
            parcela(2, 2, total=3, venc="2026-02-10", status="pago"),
            parcela(3, 3, total=3, venc="2026-03-10"),
        ]
        ws = amb.parcelas(linhas)
        antes = [list(r) for r in ws.rows]
        with pytest.raises(ValueError, match="Estorne"):
            parcelas.corrigir_total_parcelas(1, 1)
        assert ws.rows == antes
        assert ws.batch_calls == []

    def test_total_menor_que_a_primeira_parcela_lancada_e_recusado(self, amb):
        linhas = [
            parcela(1, 3, total=5, venc="2026-03-10"),
            parcela(2, 4, total=5, venc="2026-04-10"),
        ]
        ws = amb.parcelas(linhas)
        with pytest.raises(ValueError, match="primeira parcela lançada"):
            parcelas.corrigir_total_parcelas(1, 2)
        assert len(ws.rows) == 2

    def test_mesmo_total_nao_cria_nem_remove(self, amb):
        ws = amb.parcelas(compra_3x())
        assert parcelas.corrigir_total_parcelas(1, 3) == (0, 0)
        assert len(ws.rows) == 3

    def test_nao_mexe_em_outra_compra_com_a_mesma_descricao(self, amb):
        a = compra_3x(id_inicial=1, desc="Netflix")
        b = compra_3x(id_inicial=4, desc="Netflix")
        ws = amb.parcelas(a + b)
        parcelas.corrigir_total_parcelas(5, 4)  # aumenta só a 2ª compra
        df = ws.df()
        primeira = df[df["id"].isin([1, 2, 3])]
        assert set(primeira["total"]) == {3}
        assert len(df) == 7

    def test_parcela_de_despesa_e_recusada(self, amb):
        ws = amb.parcelas([parcela(1, 1, total=2, despesa_id=7), parcela(2, 2, total=2, despesa_id=7)])
        with pytest.raises(ValueError, match="veio de uma despesa"):
            parcelas.corrigir_total_parcelas(1, 4)
        assert len(ws.rows) == 2

    def test_atualiza_o_total_em_uma_unica_chamada_em_lote(self, amb):
        ws = amb.parcelas(compra_3x())
        parcelas.corrigir_total_parcelas(1, 5)
        assert len(ws.batch_calls) == 1
        updates, opcao = ws.batch_calls[0]
        assert opcao == "RAW"
        assert len(updates) == 3  # as 3 parcelas que já existiam
        assert ws.cell_updates == []

    def test_escreve_o_total_na_coluna_certa_com_ordem_fisica_diferente(self, amb):
        header = ["id", "total", "despesa_id", "numero", "valor", "vencimento", "status",
                  "descricao", "cartao", "origem_vencimento", "data_compra"]
        ws = amb.parcelas(compra_3x(), header=header)
        parcelas.corrigir_total_parcelas(1, 4)
        df = ws.df()
        assert set(df["total"]) == {4}
        assert list(df["numero"]) == [1, 2, 3, 4]
        assert list(df["valor"]) == [100.0] * 4

    def test_limpa_o_cache(self, amb):
        amb.parcelas(compra_3x())
        parcelas.corrigir_total_parcelas(1, 4)
        assert amb.cache_parcelas.limpezas == 1


# ─────────────────────────────────────────────────────────────────────────────
# alterar_lancamento_parcela
# ─────────────────────────────────────────────────────────────────────────────

class TestAlterarLancamentoParcela:

    def test_escopo_parcela_altera_so_o_valor_dela(self, amb):
        ws = amb.parcelas(compra_3x())
        n = parcelas.alterar_lancamento_parcela(2, valor=123.45)
        assert n == 1
        valores = ws.df()["valor"].tolist()
        assert valores == [100.0, 123.45, 100.0]

    def test_valor_e_arredondado_em_centavos(self, amb):
        ws = amb.parcelas(compra_3x())
        parcelas.alterar_lancamento_parcela(2, valor=10.126)
        assert ws.df().iloc[1]["valor"] == 10.13

    def test_escopo_compra_altera_valor_so_das_pendentes(self, amb):
        ws = amb.parcelas(compra_3x())  # parcela 1 paga, 2 e 3 pendentes
        n = parcelas.alterar_lancamento_parcela(2, valor=150.0, escopo="compra")
        assert n == 2
        assert ws.df()["valor"].tolist() == [100.0, 150.0, 150.0]

    def test_escopo_compra_altera_descricao_cartao_e_data_em_todas(self, amb):
        ws = amb.parcelas(compra_3x(), col_count=20)
        n = parcelas.alterar_lancamento_parcela(
            2, descricao="  Geladeira nova  ", cartao="Itaú",
            data_compra="2025-12-01", escopo="compra")
        assert n == 3
        df = ws.df()
        assert set(df["descricao"]) == {"Geladeira nova"}
        assert set(df["cartao"]) == {"Itaú"}
        assert set(df["data_compra"]) == {"2025-12-01"}

    def test_escopo_compra_nao_toca_em_outra_compra_homonima(self, amb):
        a = compra_3x(id_inicial=1, desc="Netflix")
        b = compra_3x(id_inicial=4, desc="Netflix")
        ws = amb.parcelas(a + b)
        parcelas.alterar_lancamento_parcela(5, descricao="Netflix 4K", escopo="compra")
        df = ws.df()
        assert list(df["descricao"]) == ["Netflix"] * 3 + ["Netflix 4K"] * 3

    def test_escopo_parcela_nao_altera_descricao_das_irmas(self, amb):
        ws = amb.parcelas(compra_3x())
        n = parcelas.alterar_lancamento_parcela(2, descricao="Outro nome")
        assert n == 1
        assert ws.df()["descricao"].tolist() == ["Geladeira", "Outro nome", "Geladeira"]

    def test_parcela_de_despesa_ignora_descricao_cartao_e_data(self, amb):
        linhas = [parcela(1, 1, total=2, despesa_id=7), parcela(2, 2, total=2, despesa_id=7)]
        ws = amb.parcelas(linhas)
        n = parcelas.alterar_lancamento_parcela(
            1, descricao="X", cartao="Itaú", data_compra="2025-01-01")
        assert n == 0
        assert ws.batch_calls == []
        assert set(ws.df()["descricao"]) == {"Geladeira"}

    def test_parcela_de_despesa_aceita_alterar_o_valor(self, amb):
        linhas = [parcela(1, 1, total=2, despesa_id=7), parcela(2, 2, total=2, despesa_id=7)]
        ws = amb.parcelas(linhas)
        assert parcelas.alterar_lancamento_parcela(1, valor=80.0) == 1
        assert ws.df()["valor"].tolist() == [80.0, 100.0]

    @pytest.mark.parametrize("valor", [0, -5, 1_000_000.01, 5_000_000])
    def test_valor_fora_da_faixa_e_recusado(self, amb, valor):
        ws = amb.parcelas(compra_3x())
        with pytest.raises(ValueError, match="Valor deve estar entre"):
            parcelas.alterar_lancamento_parcela(2, valor=valor)
        assert ws.batch_calls == []

    def test_valor_no_limite_superior_e_aceito(self, amb):
        amb.parcelas(compra_3x())
        assert parcelas.alterar_lancamento_parcela(2, valor=1_000_000) == 1

    @pytest.mark.parametrize("descricao", ["", "   "])
    def test_descricao_vazia_e_recusada(self, amb, descricao):
        ws = amb.parcelas(compra_3x())
        with pytest.raises(ValueError, match="descrição"):
            parcelas.alterar_lancamento_parcela(2, descricao=descricao)
        assert ws.batch_calls == []

    def test_data_da_compra_posterior_ao_vencimento_e_recusada(self, amb):
        ws = amb.parcelas(compra_3x())  # menor vencimento do escopo parcela (id 2): 2026-02-10
        with pytest.raises(ValueError, match="posterior ao vencimento"):
            parcelas.alterar_lancamento_parcela(2, data_compra="2026-02-11")
        assert ws.batch_calls == []

    def test_data_da_compra_no_escopo_compra_compara_com_a_menor_data(self, amb):
        amb.parcelas(compra_3x())  # menor vencimento da compra: 2026-01-10
        with pytest.raises(ValueError, match="posterior ao vencimento"):
            parcelas.alterar_lancamento_parcela(2, data_compra="2026-01-11", escopo="compra")

    def test_data_da_compra_igual_ao_vencimento_e_aceita(self, amb):
        ws = amb.parcelas(compra_3x(), col_count=20)
        n = parcelas.alterar_lancamento_parcela(2, data_compra="2026-02-10")
        assert n == 1
        assert ws.df().iloc[1]["data_compra"] == "2026-02-10"

    def test_data_da_compra_cria_a_coluna_se_faltar(self, amb):
        header_sem = [c for c in HEADER_PARCELAS if c != "data_compra"]
        ws = amb.parcelas(compra_3x(), header=header_sem)
        parcelas.alterar_lancamento_parcela(2, data_compra="2025-12-01")
        assert "data_compra" in ws.header
        assert ws.df().iloc[1]["data_compra"] == "2025-12-01"

    def test_vencimento_como_numero_serial_do_sheets_e_entendido(self, amb):
        serial = (date(2026, 2, 10) - date(1899, 12, 30)).days
        linhas = compra_3x()
        linhas[1]["vencimento"] = serial
        ws = amb.parcelas(linhas)
        with pytest.raises(ValueError, match="posterior ao vencimento"):
            parcelas.alterar_lancamento_parcela(2, data_compra="2026-02-11")
        assert ws.batch_calls == []

    def test_sem_nada_para_alterar_devolve_zero_sem_gravar(self, amb):
        ws = amb.parcelas(compra_3x())
        assert parcelas.alterar_lancamento_parcela(2) == 0
        assert ws.batch_calls == []
        assert amb.cache_parcelas.limpezas == 0

    def test_parcela_inexistente(self, amb):
        amb.parcelas(compra_3x())
        with pytest.raises(ValueError, match="não encontrada"):
            parcelas.alterar_lancamento_parcela(999, valor=10.0)

    def test_planilha_vazia(self, amb):
        amb.parcelas([])
        with pytest.raises(ValueError, match="Nenhuma parcela"):
            parcelas.alterar_lancamento_parcela(1, valor=10.0)

    def test_grava_tudo_em_uma_unica_chamada_em_lote_raw(self, amb):
        ws = amb.parcelas(compra_3x(), col_count=20)
        parcelas.alterar_lancamento_parcela(
            2, valor=50.0, descricao="Novo", cartao="Itaú", escopo="compra")
        assert len(ws.batch_calls) == 1
        assert ws.batch_calls[0][1] == "RAW"
        assert ws.cell_updates == []

    def test_escreve_por_nome_com_colunas_em_ordem_fisica_diferente(self, amb):
        header = ["id", "status", "valor", "cartao", "descricao", "despesa_id", "numero",
                  "total", "vencimento", "origem_vencimento", "data_compra"]
        ws = amb.parcelas(compra_3x(), header=header)
        parcelas.alterar_lancamento_parcela(2, valor=77.7, descricao="Novo", cartao="Itaú")
        linha = ws.df().iloc[1]
        assert linha["valor"] == 77.7
        assert linha["descricao"] == "Novo"
        assert linha["cartao"] == "Itaú"
        assert linha["status"] == "pendente"
        assert linha["numero"] == 2

    def test_limpa_o_cache(self, amb):
        amb.parcelas(compra_3x())
        parcelas.alterar_lancamento_parcela(2, valor=10.0)
        assert amb.cache_parcelas.limpezas == 1


# ─────────────────────────────────────────────────────────────────────────────
# atualizar_vencimento_parcela
# ─────────────────────────────────────────────────────────────────────────────

class TestAtualizarVencimentoParcela:

    def test_grava_data_como_texto_iso_e_marca_origem_manual(self, amb):
        linhas = compra_3x(origem="fechamento")
        ws = amb.parcelas(linhas)
        parcelas.atualizar_vencimento_parcela(2, date(2026, 2, 15))
        df = ws.df()
        assert df.iloc[1]["vencimento"] == "2026-02-15"
        assert df.iloc[1]["origem_vencimento"] == "manual"

    def test_usa_raw_para_a_data_nao_virar_serial(self, amb):
        ws = amb.parcelas(compra_3x())
        parcelas.atualizar_vencimento_parcela(2, date(2026, 2, 15))
        assert len(ws.batch_calls) == 1
        assert ws.batch_calls[0][1] == "RAW"

    def test_nao_altera_as_outras_parcelas(self, amb):
        linhas = compra_3x(origem="fechamento")
        ws = amb.parcelas(linhas)
        parcelas.atualizar_vencimento_parcela(2, date(2026, 2, 15))
        df = ws.df()
        assert df["vencimento"].tolist() == ["2026-01-10", "2026-02-15", "2026-03-10"]
        assert df["origem_vencimento"].tolist() == ["fechamento", "manual", "fechamento"]

    def test_sem_coluna_origem_grava_so_o_vencimento(self, amb):
        header = [c for c in HEADER_PARCELAS if c != "origem_vencimento"]
        ws = amb.parcelas(compra_3x(), header=header)
        parcelas.atualizar_vencimento_parcela(2, date(2026, 2, 15))
        updates, _ = ws.batch_calls[0]
        assert len(updates) == 1
        assert ws.df().iloc[1]["vencimento"] == "2026-02-15"

    def test_escreve_por_nome_com_colunas_em_ordem_fisica_diferente(self, amb):
        header = ["id", "origem_vencimento", "vencimento", "despesa_id", "numero", "total",
                  "valor", "status", "descricao", "cartao", "data_compra"]
        ws = amb.parcelas(compra_3x(), header=header)
        parcelas.atualizar_vencimento_parcela(3, date(2026, 3, 20))
        linha = ws.df().iloc[2]
        assert linha["vencimento"] == "2026-03-20"
        assert linha["origem_vencimento"] == "manual"
        assert linha["valor"] == 100.0

    def test_parcela_inexistente_nao_grava_nada(self, amb):
        ws = amb.parcelas(compra_3x())
        parcelas.atualizar_vencimento_parcela(999, date(2026, 2, 15))
        assert ws.batch_calls == []

    def test_limpa_o_cache(self, amb):
        amb.parcelas(compra_3x())
        parcelas.atualizar_vencimento_parcela(2, date(2026, 2, 15))
        assert amb.cache_parcelas.limpezas == 1


# ─────────────────────────────────────────────────────────────────────────────
# atualizar_parcela
# ─────────────────────────────────────────────────────────────────────────────

class TestAtualizarParcela:

    def test_marca_como_paga_so_a_parcela_pedida(self, amb):
        ws = amb.parcelas(compra_3x())
        parcelas.atualizar_parcela(2, "pago")
        assert ws.df()["status"].tolist() == ["pago", "pago", "pendente"]

    def test_estorna_para_pendente(self, amb):
        ws = amb.parcelas(compra_3x())
        parcelas.atualizar_parcela(1, "pendente")
        assert ws.df()["status"].tolist() == ["pendente", "pendente", "pendente"]

    def test_funciona_com_colunas_em_ordem_fisica_diferente(self, amb):
        header = ["id", "status", "despesa_id", "numero", "total", "valor", "vencimento",
                  "descricao", "cartao", "origem_vencimento", "data_compra"]
        ws = amb.parcelas(compra_3x(), header=header)
        parcelas.atualizar_parcela(3, "pago")
        df = ws.df()
        assert df["status"].tolist() == ["pago", "pendente", "pago"]
        assert df["valor"].tolist() == [100.0] * 3

    def test_parcela_inexistente_nao_altera_nada(self, amb):
        ws = amb.parcelas(compra_3x())
        antes = [list(r) for r in ws.rows]
        parcelas.atualizar_parcela(999, "pago")
        assert ws.rows == antes

    def test_limpa_o_cache(self, amb):
        amb.parcelas(compra_3x())
        parcelas.atualizar_parcela(2, "pago")
        assert amb.cache_parcelas.limpezas == 1


# ─────────────────────────────────────────────────────────────────────────────
# baixar_fatura_mes
# ─────────────────────────────────────────────────────────────────────────────

def despesa(id, cartao):
    return {"id": id, "descricao": f"Despesa {id}", "valor": 100.0, "cartao": cartao,
            "pagamento": "Cartão de crédito"}


class TestBaixarFaturaMes:

    def _cenario(self, amb):
        """Duas despesas no cartão (Nubank e Itaú) e uma compra histórica no Nubank."""
        amb.despesas([despesa(7, "Nubank"), despesa(8, "Itaú")])
        return amb.parcelas([
            parcela(1, 1, total=2, despesa_id=7, venc="2026-03-10", cartao=""),
            parcela(2, 2, total=2, despesa_id=7, venc="2026-04-10", cartao=""),
            parcela(3, 1, total=1, despesa_id=8, venc="2026-03-17", cartao=""),
            parcela(4, 1, total=1, despesa_id=-1, venc="2026-03-10", cartao="Nubank"),
            parcela(5, 1, total=1, despesa_id=-1, venc="2026-03-05", cartao="Nubank",
                    status="pago"),
        ])

    def test_planilha_de_parcelas_vazia_devolve_zero(self, amb):
        amb.despesas([])
        ws = amb.parcelas([])
        assert parcelas.baixar_fatura_mes("2026-03") == 0
        assert ws.batch_calls == []

    def test_baixa_todos_os_cartoes_do_mes(self, amb):
        ws = self._cenario(amb)
        n = parcelas.baixar_fatura_mes("2026-03")
        assert n == 3
        status = ws.linhas_por_id()
        assert status[1]["status"] == "pago"
        assert status[3]["status"] == "pago"
        assert status[4]["status"] == "pago"

    def test_nao_mexe_em_outros_meses_nem_nas_ja_pagas(self, amb):
        ws = self._cenario(amb)
        parcelas.baixar_fatura_mes("2026-03")
        linhas = ws.linhas_por_id()
        assert linhas[2]["status"] == "pendente"   # abril
        assert linhas[5]["status"] == "pago"        # já estava paga

    def test_todos_equivale_a_nenhum_filtro(self, amb):
        ws = self._cenario(amb)
        assert parcelas.baixar_fatura_mes("2026-03", "Todos") == 3

    def test_filtra_pelo_cartao_da_despesa(self, amb):
        ws = self._cenario(amb)
        n = parcelas.baixar_fatura_mes("2026-03", "Itaú")
        assert n == 1
        linhas = ws.linhas_por_id()
        assert linhas[3]["status"] == "pago"
        assert linhas[1]["status"] == "pendente"
        assert linhas[4]["status"] == "pendente"

    def test_parcela_historica_usa_o_cartao_da_propria_parcela(self, amb):
        ws = self._cenario(amb)
        n = parcelas.baixar_fatura_mes("2026-03", "Nubank")
        assert n == 2  # a da despesa 7 (id 1) e a histórica (id 4)
        linhas = ws.linhas_por_id()
        assert linhas[1]["status"] == "pago"
        assert linhas[4]["status"] == "pago"
        assert linhas[3]["status"] == "pendente"

    def test_cartao_da_despesa_tem_prioridade_sobre_o_da_parcela(self, amb):
        amb.despesas([despesa(7, "Nubank")])
        ws = amb.parcelas([
            parcela(1, 1, total=1, despesa_id=7, venc="2026-03-10", cartao="Itaú"),
        ])
        assert parcelas.baixar_fatura_mes("2026-03", "Itaú") == 0
        assert parcelas.baixar_fatura_mes("2026-03", "Nubank") == 1

    def test_sem_nenhuma_despesa_usa_o_cartao_da_parcela(self, amb):
        amb.despesas([])
        ws = amb.parcelas([
            parcela(1, 1, total=1, despesa_id=-1, venc="2026-03-10", cartao="Nubank"),
            parcela(2, 1, total=1, despesa_id=-1, venc="2026-03-10", cartao="Itaú"),
        ])
        assert parcelas.baixar_fatura_mes("2026-03", "Itaú") == 1
        assert ws.linhas_por_id()[2]["status"] == "pago"
        assert ws.linhas_por_id()[1]["status"] == "pendente"

    def test_vencimento_como_numero_serial_do_sheets_e_considerado(self, amb):
        serial = (date(2026, 3, 10) - date(1899, 12, 30)).days
        amb.despesas([])
        ws = amb.parcelas([
            parcela(1, 1, total=1, venc=serial, cartao="Nubank"),
        ])
        assert parcelas.baixar_fatura_mes("2026-03") == 1
        assert ws.linhas_por_id()[1]["status"] == "pago"

    def test_grava_tudo_em_uma_unica_chamada_em_lote(self, amb):
        ws = self._cenario(amb)
        parcelas.baixar_fatura_mes("2026-03")
        assert len(ws.batch_calls) == 1
        assert len(ws.batch_calls[0][0]) == 3
        assert ws.cell_updates == []

    def test_sem_pendentes_no_mes_devolve_zero_sem_gravar(self, amb):
        ws = self._cenario(amb)
        assert parcelas.baixar_fatura_mes("2027-01") == 0
        assert ws.batch_calls == []
        assert amb.cache_parcelas.limpezas == 0

    def test_nao_corrompe_outras_colunas(self, amb):
        ws = self._cenario(amb)
        antes = ws.df().drop(columns=["status"])
        parcelas.baixar_fatura_mes("2026-03")
        depois = ws.df().drop(columns=["status"])
        pd.testing.assert_frame_equal(antes, depois)

    def test_funciona_com_colunas_em_ordem_fisica_diferente(self, amb):
        amb.despesas([])
        header = ["id", "status", "despesa_id", "numero", "total", "valor", "vencimento",
                  "descricao", "cartao", "origem_vencimento", "data_compra"]
        ws = amb.parcelas([
            parcela(1, 1, total=1, venc="2026-03-10", cartao="Nubank"),
            parcela(2, 1, total=1, venc="2026-04-10", cartao="Nubank"),
        ], header=header)
        assert parcelas.baixar_fatura_mes("2026-03") == 1
        assert ws.df()["status"].tolist() == ["pago", "pendente"]

    def test_limpa_o_cache(self, amb):
        self._cenario(amb)
        parcelas.baixar_fatura_mes("2026-03")
        assert amb.cache_parcelas.limpezas == 1


# ─────────────────────────────────────────────────────────────────────────────
# _garantir_coluna
# ─────────────────────────────────────────────────────────────────────────────

class TestGarantirColuna:

    def test_coluna_existente_nao_faz_nada(self):
        ws = montar_ws([])
        parcelas._garantir_coluna(ws, "status")
        assert ws.cell_updates == []
        assert ws.cols_added == 0

    def test_coluna_nova_vai_para_o_fim(self):
        ws = montar_ws([], col_count=20)
        parcelas._garantir_coluna(ws, "nova_coluna")
        assert ws.header[-1] == "nova_coluna"
        assert len(ws.header) == len(HEADER_PARCELAS) + 1
        assert ws.cols_added == 0  # ainda cabia na planilha

    def test_aumenta_a_planilha_se_nao_houver_espaco(self):
        ws = montar_ws([], col_count=len(HEADER_PARCELAS))
        parcelas._garantir_coluna(ws, "nova_coluna")
        assert ws.cols_added == 1
        assert ws.header[-1] == "nova_coluna"
