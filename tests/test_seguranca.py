"""Segurança: senha em tempo constante, exportações sem fórmula e erros sem texto técnico."""
import hmac
import io
import logging
import re
from pathlib import Path

import openpyxl
import pandas as pd
import pytest

import utils.sessao as sessao
import utils.widgets as widgets
from logica import parcelas
from logica.exportacao import gerar_csv_panorama, gerar_excel_panorama, neutralizar_formula
from utils.erros import ErroDeNegocio
from utils.sessao import USUARIO_PADRAO, autenticar_credenciais

USUARIOS = {"Ricardo": "s3nha-r", "Jociara": "s3nha-j"}


class TestSenhaEmTempoConstante:
    def test_usa_hmac_compare_digest(self, monkeypatch):
        chamadas = []
        real = hmac.compare_digest
        monkeypatch.setattr(sessao.hmac, "compare_digest", lambda a, b: chamadas.append((a, b)) or real(a, b))
        autenticar_credenciais("Ricardo", "s3nha-r", USUARIOS)
        assert chamadas, "a senha precisa passar por hmac.compare_digest"
        assert all(isinstance(a, bytes) and isinstance(b, bytes) for a, b in chamadas)

    def test_confere_todas_as_entradas_sem_parar_na_primeira(self, monkeypatch):
        n = []
        real = hmac.compare_digest
        monkeypatch.setattr(sessao.hmac, "compare_digest", lambda a, b: n.append(1) or real(a, b))
        autenticar_credenciais("Ricardo", "s3nha-r", USUARIOS)   # acerta já na 1ª entrada
        assert len(n) == len(USUARIOS)

    def test_continua_autenticando_normalmente(self):
        assert autenticar_credenciais("ricardo ", "s3nha-r", USUARIOS) == "Ricardo"
        assert autenticar_credenciais("Jociara", "s3nha-j", USUARIOS) == "Jociara"

    def test_senha_ou_nome_errados(self):
        assert autenticar_credenciais("Ricardo", "s3nha-j", USUARIOS) is None
        assert autenticar_credenciais("Outro", "s3nha-r", USUARIOS) is None

    def test_senha_com_acentos_e_emoji_nao_quebra(self):
        usuarios = {"Ana": "açaí-ção-😀"}
        assert autenticar_credenciais("Ana", "açaí-ção-😀", usuarios) == "Ana"
        assert autenticar_credenciais("Ana", "acai-cao", usuarios) is None

    def test_senha_cadastrada_vazia_nunca_autentica(self):
        assert autenticar_credenciais("Ana", "", {"Ana": ""}) is None
        assert autenticar_credenciais("Ana", None, {"Ana": ""}) is None

    def test_senha_cadastrada_numerica_no_secrets(self):
        assert autenticar_credenciais("Ana", "1234", {"Ana": 1234}) == "Ana"

    def test_digitada_none(self):
        assert autenticar_credenciais("Ricardo", None, USUARIOS) is None

    def test_modo_senha_unica(self):
        assert autenticar_credenciais("", "abc", {}, "abc") == USUARIO_PADRAO
        assert autenticar_credenciais("", "abd", {}, "abc") is None
        assert autenticar_credenciais("", "", {}, "") is None


class TestNeutralizarFormula:
    @pytest.mark.parametrize("texto", ["=1+1", '=HYPERLINK("http://x","a")', "+cmd", "-cmd|' /C calc'!A0",
                                       "@SUM(1)", "\t=x", "  =x", "\r=x", "=", "-A1", "+1+1"])
    def test_texto_perigoso_ganha_apostrofo(self, texto):
        assert neutralizar_formula(texto) == "'" + texto

    @pytest.mark.parametrize("valor", ["Mercado", "Compra de =x", "R$ 10,00", "-12,50", "+3%", "-R$ 9.719,98",
                                       "Dez/26", "", "   ", None, 5, -3.2, 0, True])
    def test_texto_comum_e_numeros_ficam_iguais(self, valor):
        assert neutralizar_formula(valor) == valor


def _linhas(descricao, categoria="Lazer"):
    return pd.DataFrame([dict(mes="2026-12", tipo="despesa", origem="Lançamento", descricao=descricao,
                              categoria=categoria, valor=-5.5)])


def _resumo():
    return pd.DataFrame([{"mes": "2026-12", "Mês": "Dez/26", "Receitas": 0.0, "Cartão": 0.0, "Recorrentes": 0.0,
                          "Outras desp.": 0.0, "Despesas (total)": 0.0, "Saldo projetado": -1.0}])


class TestExportacoesSemFormula:
    def test_excel_descricao_vira_texto_e_nao_formula(self):
        wb = openpyxl.load_workbook(io.BytesIO(gerar_excel_panorama(_linhas('=HYPERLINK("http://x","a")', "@x"), _resumo())))
        ws = wb["Detalhes"]
        for celula in (ws["D2"], ws["E2"]):
            assert celula.data_type == "s", f"{celula.coordinate} virou {celula.data_type}"
            assert celula.value.startswith("'")

    def test_excel_texto_comum_e_valor_negativo_intactos(self):
        wb = openpyxl.load_workbook(io.BytesIO(gerar_excel_panorama(_linhas("Mercado"), _resumo())))
        assert wb["Detalhes"]["D2"].value == "Mercado"
        assert wb["Detalhes"]["F2"].value == -5.5
        assert wb["Resumo"]["G2"].value == -1.0

    def test_csv_nao_tem_formula_solta(self):
        csv = gerar_csv_panorama(_linhas("=cmd|' /C calc'!A0"), _resumo()).decode("utf-8-sig")
        assert "'=cmd" in csv
        assert not re.search(r"(^|,|\n)=cmd", csv)

    def test_nao_altera_os_dataframes_recebidos(self):
        linhas, resumo = _linhas("=1+1"), _resumo()
        l0, r0 = linhas.copy(), resumo.copy()
        gerar_excel_panorama(linhas, resumo)
        gerar_csv_panorama(linhas, resumo)
        pd.testing.assert_frame_equal(linhas, l0)
        pd.testing.assert_frame_equal(resumo, r0)


class _FakeSt:
    def __init__(self):
        self.erros, self.avisos = [], []

    def error(self, t):
        self.erros.append(t)

    def warning(self, t):
        self.avisos.append(t)


@pytest.fixture
def fake_st(monkeypatch):
    f = _FakeSt()
    monkeypatch.setattr(widgets, "st", f)
    return f


class TestMostrarErro:
    SEGREDO = "APIError: 403 spreadsheetId=1AbCdEfGhIjKlMnOp https://sheets.googleapis.com/v4/..."

    def test_erro_tecnico_nao_aparece_na_tela(self, fake_st):
        texto = widgets.mostrar_erro("excluir a despesa", RuntimeError(self.SEGREDO))
        tela = " ".join(fake_st.erros)
        assert "spreadsheetId" not in tela and "googleapis" not in tela and "APIError" not in tela
        assert tela == texto and "Não foi possível excluir a despesa" in tela

    def test_tela_mostra_um_codigo_e_o_log_tem_o_mesmo_codigo_e_o_detalhe(self, fake_st, caplog):
        with caplog.at_level(logging.ERROR, logger="controle_contas"):
            widgets.mostrar_erro("salvar a receita", RuntimeError(self.SEGREDO))
        codigo = re.search(r"código (\w{8})", fake_st.erros[0]).group(1)
        assert any(codigo in r.getMessage() and "spreadsheetId" in r.getMessage() for r in caplog.records)
        assert any(r.exc_info for r in caplog.records)      # traceback guardado

    def test_cada_erro_tem_codigo_diferente(self, fake_st):
        widgets.mostrar_erro("x", RuntimeError("a"))
        widgets.mostrar_erro("x", RuntimeError("a"))
        assert fake_st.erros[0] != fake_st.erros[1]

    def test_erro_de_negocio_aparece_como_esta(self, fake_st, caplog):
        with caplog.at_level(logging.ERROR, logger="controle_contas"):
            widgets.mostrar_erro("corrigir", ErroDeNegocio("O total de parcelas deve estar entre 1 e 48."))
        assert fake_st.erros == ["O total de parcelas deve estar entre 1 e 48."]
        assert not caplog.records

    def test_valueerror_comum_e_tratado_como_tecnico(self, fake_st):
        widgets.mostrar_erro("converter", ValueError("invalid literal for int() with base 10: 'abc'"))
        assert "invalid literal" not in fake_st.erros[0]

    def test_nivel_warning(self, fake_st):
        widgets.mostrar_erro("calcular", RuntimeError("x"), nivel="warning")
        assert fake_st.avisos and not fake_st.erros

    def test_erro_de_negocio_e_um_valueerror(self):
        assert issubclass(ErroDeNegocio, ValueError)


class TestRegrasDeNegocioDeParcelasSaoErroDeNegocio:
    def test_nenhum_raise_valueerror_puro_em_parcelas(self):
        fonte = Path(parcelas.__file__).read_text(encoding="utf-8")
        assert "raise ValueError(" not in fonte
        assert fonte.count("raise ErroDeNegocio(") >= 10


class TestTelasNaoMostramTextoDaExcecao:
    RAIZ = Path(__file__).resolve().parent.parent

    def test_nenhuma_tela_interpola_a_excecao_em_mensagem(self):
        achados = []
        for arq in sorted((self.RAIZ / "paginas").glob("*.py")) + [self.RAIZ / "app.py", self.RAIZ / "auth.py"]:
            for n, linha in enumerate(arq.read_text(encoding="utf-8").splitlines(), 1):
                if re.search(r"st\.(error|warning|info|caption|write|markdown)\(.*(\{e\}|\{exc\}|str\(e\))", linha) \
                        and "ErroDeNegocio" not in linha:
                    achados.append(f"{arq.name}:{n}: {linha.strip()[:90]}")
        # str(e) só é permitido dentro de `except ErroDeNegocio` (mensagem escrita por nós)
        assert not [a for a in achados if "{e}" in a or "{exc}" in a], achados

    def test_str_e_so_depois_de_except_erro_de_negocio(self):
        for arq in sorted((self.RAIZ / "paginas").glob("*.py")):
            linhas = arq.read_text(encoding="utf-8").splitlines()
            for i, linha in enumerate(linhas):
                if "st.error(str(e))" in linha:
                    assert "except ErroDeNegocio as e" in linhas[i - 1], f"{arq.name}:{i + 1}"
