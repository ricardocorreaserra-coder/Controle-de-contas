"""Segurança de infraestrutura: permissões mínimas do Google e .devcontainer sem atalhos inseguros."""
import json
import logging
import re
from pathlib import Path

import gspread
import pytest
import requests

import config
from sheets.client import _abrir_planilha, _erro_de_escopo

RAIZ = Path(__file__).resolve().parent.parent
DRIVE_COMPLETO = "https://www.googleapis.com/auth/drive"


def api_error(status, mensagem):
    r = requests.Response()
    r.status_code = status
    r._content = json.dumps({"error": {"code": status, "message": mensagem, "status": "X"}}).encode()
    r.headers["Content-Type"] = "application/json"
    return gspread.exceptions.APIError(r)


ESCOPO = api_error(403, "Request had insufficient authentication scopes.")
SEM_ACESSO = api_error(403, "The caller does not have permission")
NAO_ACHADO = api_error(404, "Requested entity was not found.")
SERVIDOR = api_error(500, "Internal error encountered.")


class TestEscoposDoGoogle:
    def test_nao_pede_o_drive_completo(self):
        assert DRIVE_COMPLETO not in config.SCOPES

    def test_pede_so_planilhas_e_metadados_do_drive(self):
        assert set(config.SCOPES) == {"https://www.googleapis.com/auth/spreadsheets",
                                      "https://www.googleapis.com/auth/drive.metadata.readonly"}

    def test_nenhum_escopo_do_drive_permite_escrever_ou_apagar(self):
        for escopo in config.SCOPES:
            if "/drive" in escopo:
                assert escopo.endswith(".readonly")

    def test_plano_b_e_o_escopo_antigo(self):
        assert DRIVE_COMPLETO in config.SCOPES_AMPLOS
        assert "https://www.googleapis.com/auth/spreadsheets" in config.SCOPES_AMPLOS

    def test_o_app_so_usa_o_drive_para_achar_a_planilha_pelo_nome(self):
        """Se alguém adicionar compartilhar/exportar/apagar arquivo, o escopo mínimo deixa de bastar.

        `list_spreadsheet_files` fica de fora de propósito: é a MESMA consulta de metadados que o
        `gspread.open` já faz (id, nome, datas), coberta por drive.metadata.readonly.
        """
        proibidos = re.compile(r"\.(share|export|list_permissions|insert_permission|remove_permission|"
                               r"del_spreadsheet|transfer_ownership|accept_ownership|import_csv|"
                               r"get_file_drive_metadata)\(|\b(client|gc|gspread_client)\.(create|copy)\(")
        achados = []
        for pasta in ("sheets", "logica", "paginas", "utils"):
            for arq in sorted((RAIZ / pasta).rglob("*.py")):
                for n, linha in enumerate(arq.read_text(encoding="utf-8").splitlines(), 1):
                    if proibidos.search(linha):
                        achados.append(f"{arq.relative_to(RAIZ)}:{n}")
        assert not achados, ("Usa recurso do Google Drive: revise config.SCOPES antes. " + ", ".join(achados))


class TestErroDeEscopo:
    def test_403_de_escopo(self):
        assert _erro_de_escopo(ESCOPO) is True

    @pytest.mark.parametrize("erro", [SEM_ACESSO, NAO_ACHADO, SERVIDOR])
    def test_outros_erros_nao_disparam_o_plano_b(self, erro):
        assert _erro_de_escopo(erro) is False

    def test_excecao_qualquer(self):
        assert _erro_de_escopo(RuntimeError("scope insufficient")) is False   # só APIError 403 conta


class _Cliente:
    def __init__(self, resultado):
        self.resultado, self.chamadas = resultado, []

    def open(self, nome):
        self.chamadas.append(nome)
        if isinstance(self.resultado, BaseException):
            raise self.resultado
        return self.resultado


class TestAbrirPlanilha:
    def test_usa_o_cliente_minimo_e_nao_cria_o_amplo(self):
        minimo = _Cliente("PLANILHA")
        criou_amplo = []
        r = _abrir_planilha("Controle", minimo, lambda: criou_amplo.append(1))
        assert r == "PLANILHA" and minimo.chamadas == ["Controle"] and not criou_amplo

    def test_escopo_recusado_cai_no_plano_b_uma_vez(self, caplog):
        minimo, amplo = _Cliente(ESCOPO), _Cliente("PLANILHA-AMPLA")
        with caplog.at_level(logging.WARNING, logger="controle_contas"):
            r = _abrir_planilha("Controle", minimo, lambda: amplo)
        assert r == "PLANILHA-AMPLA" and minimo.chamadas == ["Controle"] and amplo.chamadas == ["Controle"]
        assert any("escopo" in x.getMessage().lower() for x in caplog.records)   # avisa no log

    @pytest.mark.parametrize("erro", [SEM_ACESSO, NAO_ACHADO, SERVIDOR])
    def test_outros_erros_do_google_sobem_sem_plano_b(self, erro):
        amplo_usado = []
        with pytest.raises(gspread.exceptions.APIError):
            _abrir_planilha("Controle", _Cliente(erro), lambda: amplo_usado.append(1))
        assert not amplo_usado

    def test_planilha_nao_encontrada_sobe_sem_plano_b(self):
        amplo_usado = []
        with pytest.raises(gspread.SpreadsheetNotFound):
            _abrir_planilha("Controle", _Cliente(gspread.SpreadsheetNotFound(NAO_ACHADO.response)),
                            lambda: amplo_usado.append(1))
        assert not amplo_usado

    def test_se_o_plano_b_tambem_falhar_o_erro_sobe_sem_repetir(self):
        amplo = _Cliente(SEM_ACESSO)
        with pytest.raises(gspread.exceptions.APIError):
            _abrir_planilha("Controle", _Cliente(ESCOPO), lambda: amplo)
        assert amplo.chamadas == ["Controle"]


class TestDevcontainerSeguro:
    ARQUIVO = RAIZ / ".devcontainer" / "devcontainer.json"

    def test_nao_desliga_xsrf_nem_cors(self):
        texto = self.ARQUIVO.read_text(encoding="utf-8")
        assert "enableXsrfProtection" not in texto
        assert "enableCORS" not in texto

    def test_nao_inicia_o_app_sozinho(self):
        assert "postAttachCommand" not in self.ARQUIVO.read_text(encoding="utf-8")

    def test_continua_sendo_um_json_valido(self):
        sem_comentarios = re.sub(r"^\s*//.*$", "", self.ARQUIVO.read_text(encoding="utf-8"), flags=re.M)
        dados = json.loads(sem_comentarios)
        assert dados["forwardPorts"] == [8501] and "image" in dados


class TestLigacaoDoGetWorkbook:
    """O get_workbook de verdade, com os clientes do Google trocados por falsos."""

    @pytest.fixture
    def preparar(self, monkeypatch):
        import streamlit as st
        import sheets.client as cl
        monkeypatch.setattr(st, "secrets", {"SHEET_NAME": "Controle"})
        cl.get_workbook.clear()
        yield cl
        cl.get_workbook.clear()

    def test_com_o_minimo_funcionando_nao_cria_o_cliente_amplo(self, preparar, monkeypatch):
        cl = preparar
        criou_amplo = []
        monkeypatch.setattr(cl, "get_sheets_client", lambda: _Cliente("PLANILHA"))
        monkeypatch.setattr(cl, "get_sheets_client_amplo", lambda: criou_amplo.append(1))
        assert cl.get_workbook() == "PLANILHA" and not criou_amplo

    def test_google_recusa_o_minimo_e_o_app_continua_no_ar(self, preparar, monkeypatch):
        cl = preparar
        monkeypatch.setattr(cl, "get_sheets_client", lambda: _Cliente(ESCOPO))
        monkeypatch.setattr(cl, "get_sheets_client_amplo", lambda: _Cliente("PLANILHA-AMPLA"))
        assert cl.get_workbook() == "PLANILHA-AMPLA"

    def test_usa_o_nome_da_planilha_dos_secrets(self, preparar, monkeypatch):
        cl = preparar
        c = _Cliente("P")
        monkeypatch.setattr(cl, "get_sheets_client", lambda: c)
        cl.get_workbook()
        assert c.chamadas == ["Controle"]
