"""Diagnóstico: aviso quando há mais de uma planilha com o nome configurado (SHEET_NAME)."""
import json
import logging

import gspread
import pytest
import requests
import streamlit as st

import sheets.client as cl
from sheets.client import _data_br, _md_texto, analisar_planilhas_homonimas, texto_aviso_planilhas

NOME = "Controle de Contas"


def _api_error(status, mensagem):
    r = requests.Response()
    r.status_code = status
    r._content = json.dumps({"error": {"code": status, "message": mensagem, "status": "X"}}).encode()
    r.headers["Content-Type"] = "application/json"
    return gspread.exceptions.APIError(r)


ESCOPO = _api_error(403, "Request had insufficient authentication scopes.")
SEM_ACESSO = _api_error(403, "The caller does not have permission")


def arq(id_, nome=NOME, criada="2026-06-13T14:22:10.123Z", alterada="2026-11-01T09:00:00.000Z"):
    return {"id": id_, "name": nome, "createdTime": criada, "modifiedTime": alterada}


class TestDataBr:
    def test_formata(self):
        assert _data_br("2026-06-13T14:22:10.123Z") == "13/06/2026"

    @pytest.mark.parametrize("v", [None, "", "abc", "2026-13", "x-y-z"])
    def test_invalida(self, v):
        assert _data_br(v) == "?"


class TestAnalisar:
    def test_uma_planilha_nao_e_ambigua(self):
        r = analisar_planilhas_homonimas([arq("A")], NOME, "A")
        assert r["ambigua"] is False and len(r["itens"]) == 1 and r["itens"][0]["em_uso"] is True

    def test_duas_com_o_mesmo_nome_sao_ambiguas(self):
        r = analisar_planilhas_homonimas([arq("A"), arq("B")], NOME, "A")
        assert r["ambigua"] is True and len(r["itens"]) == 2

    def test_marca_so_a_que_esta_em_uso(self):
        r = analisar_planilhas_homonimas([arq("A"), arq("B"), arq("C")], NOME, "B")
        assert [i["id"] for i in r["itens"] if i["em_uso"]] == ["B"]

    def test_ordena_pela_alteracao_mais_recente(self):
        r = analisar_planilhas_homonimas([arq("velha", alterada="2026-01-01T00:00:00Z"),
                                          arq("nova", alterada="2026-11-01T00:00:00Z")], NOME)
        assert [i["id"] for i in r["itens"]] == ["nova", "velha"]

    def test_nome_parecido_nao_conta(self):
        outros = [arq("A"), arq("B", nome="Controle de Contas (cópia)"), arq("C", nome="controle de contas"),
                  arq("D", nome="Outra")]
        assert analisar_planilhas_homonimas(outros, NOME, "A")["ambigua"] is False

    def test_datas_em_formato_brasileiro(self):
        i = analisar_planilhas_homonimas([arq("A", criada="2026-06-13T10:00:00Z", alterada="2026-11-01T10:00:00Z")], NOME)["itens"][0]
        assert (i["criada"], i["alterada"]) == ("13/06/2026", "01/11/2026")

    @pytest.mark.parametrize("entrada", [None, [], [{}], [{"name": NOME}], ["texto", 5, None]])
    def test_entradas_estranhas_nao_quebram(self, entrada):
        r = analisar_planilhas_homonimas(entrada, NOME)
        assert r["ambigua"] is False and r["itens"] == []

    def test_sem_data_nao_quebra_a_ordenacao(self):
        r = analisar_planilhas_homonimas([{"id": "A", "name": NOME}, arq("B")], NOME)
        assert len(r["itens"]) == 2 and r["itens"][0]["id"] == "B"


class TestTextoDoAviso:
    def _diag(self, nome=NOME):
        return analisar_planilhas_homonimas([arq("ID_NOVA", alterada="2026-11-01T00:00:00Z"),
                                             arq("ID_VELHA", criada="2026-01-02T00:00:00Z", alterada="2026-01-05T00:00:00Z")],
                                            nome, "ID_NOVA")

    def test_tem_link_para_abrir_cada_planilha(self):
        t = texto_aviso_planilhas(self._diag(), NOME)
        assert "https://docs.google.com/spreadsheets/d/ID_NOVA" in t
        assert "https://docs.google.com/spreadsheets/d/ID_VELHA" in t

    def test_marca_a_que_esta_em_uso_uma_vez(self):
        t = texto_aviso_planilhas(self._diag(), NOME)
        assert t.count("em uso agora") == 1
        linha_nova = [l for l in t.splitlines() if "ID_NOVA" in l][0]
        assert "em uso agora" in linha_nova

    def test_mostra_quantidade_nome_e_datas(self):
        t = texto_aviso_planilhas(self._diag(), NOME)
        assert "2 planilhas" in t and "Controle de Contas" in t
        assert "criada em 02/01/2026" in t and "última alteração em 05/01/2026" in t

    def test_nome_com_markdown_e_escapado(self):
        t = texto_aviso_planilhas(self._diag("Meu *negrito* [link](http://x) $1 $2"), "Meu *negrito* [link](http://x) $1 $2")
        primeira = t.splitlines()[0]
        assert "\\*negrito\\*" in primeira and "\\[link\\]" in primeira and "\\$1" in primeira

    def test_md_texto(self):
        assert _md_texto("a_b*c") == "a\\_b\\*c"


class _ClienteFalso:
    def __init__(self, arquivos=None, erro=None):
        self.arquivos, self.erro, self.pediu = arquivos, erro, []

    def list_spreadsheet_files(self, title=None, folder_id=None):
        self.pediu.append(title)
        if self.erro:
            raise self.erro
        return self.arquivos


class _Planilha:
    id = "ID_NOVA"


@pytest.fixture
def ambiente(monkeypatch):
    monkeypatch.setattr(st, "secrets", {"SHEET_NAME": NOME})
    cl.diagnostico_planilha.clear()
    yield monkeypatch
    cl.diagnostico_planilha.clear()


class TestDiagnosticoPlanilha:
    def test_detecta_duas_planilhas(self, ambiente):
        c = _ClienteFalso([arq("ID_NOVA"), arq("ID_VELHA", alterada="2026-01-01T00:00:00Z")])
        ambiente.setattr(cl, "get_sheets_client", lambda: c)
        ambiente.setattr(cl, "get_workbook", lambda: _Planilha())
        r = cl.diagnostico_planilha()
        assert r["ambigua"] is True and r["nome"] == NOME and c.pediu == [NOME]
        assert [i["id"] for i in r["itens"] if i["em_uso"]] == ["ID_NOVA"]

    def test_uma_planilha_so_nao_avisa(self, ambiente):
        ambiente.setattr(cl, "get_sheets_client", lambda: _ClienteFalso([arq("ID_NOVA")]))
        ambiente.setattr(cl, "get_workbook", lambda: _Planilha())
        assert cl.diagnostico_planilha()["ambigua"] is False

    def test_falha_do_google_nunca_derruba_o_app(self, ambiente, caplog):
        ambiente.setattr(cl, "get_sheets_client", lambda: _ClienteFalso(erro=RuntimeError("403 secreto")))
        ambiente.setattr(cl, "get_workbook", lambda: _Planilha())
        with caplog.at_level(logging.WARNING, logger="controle_contas"):
            r = cl.diagnostico_planilha()
        assert r["ambigua"] is False and r["itens"] == []
        assert any("Diagnóstico" in x.getMessage() for x in caplog.records)

    def test_falha_ao_abrir_a_planilha_tambem_nao_derruba(self, ambiente):
        ambiente.setattr(cl, "get_sheets_client", lambda: _ClienteFalso([arq("A"), arq("B")]))
        def quebra(): raise RuntimeError("sem planilha")
        ambiente.setattr(cl, "get_workbook", quebra)
        assert cl.diagnostico_planilha()["ambigua"] is False

    def test_se_o_google_recusar_o_escopo_minimo_o_diagnostico_usa_o_plano_b(self, ambiente):
        amplo = _ClienteFalso([arq("ID_NOVA"), arq("ID_VELHA")])
        ambiente.setattr(cl, "get_sheets_client", lambda: _ClienteFalso(erro=ESCOPO))
        ambiente.setattr(cl, "get_sheets_client_amplo", lambda: amplo)
        ambiente.setattr(cl, "get_workbook", lambda: _Planilha())
        assert cl.diagnostico_planilha()["ambigua"] is True and amplo.pediu == [NOME]

    def test_outro_erro_do_google_nao_usa_o_plano_b(self, ambiente):
        usou_amplo = []
        ambiente.setattr(cl, "get_sheets_client", lambda: _ClienteFalso(erro=SEM_ACESSO))
        ambiente.setattr(cl, "get_sheets_client_amplo", lambda: usou_amplo.append(1))
        ambiente.setattr(cl, "get_workbook", lambda: _Planilha())
        assert cl.diagnostico_planilha()["ambigua"] is False and not usou_amplo

    def test_sem_sheet_name_nos_secrets_nao_derruba(self, monkeypatch):
        monkeypatch.setattr(st, "secrets", {})
        cl.diagnostico_planilha.clear()
        assert cl.diagnostico_planilha()["ambigua"] is False
        cl.diagnostico_planilha.clear()
