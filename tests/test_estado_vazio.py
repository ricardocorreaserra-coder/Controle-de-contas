"""Etapa 6b: estado vazio padrão, percentuais e navegação por código."""
import pytest

from utils import navegacao
from utils.formatacao import estado_vazio_html, fmt_percentual, kpi_card_html


class TestFmtPercentual:
    def test_casos_comuns(self):
        assert fmt_percentual(3031.05, 9719.98) == "31,2%"
        assert fmt_percentual(1, 4) == "25,0%"
        assert fmt_percentual(5, 5) == "100,0%"

    def test_parte_zero(self):
        assert fmt_percentual(0, 100) == "0,0%"

    @pytest.mark.parametrize("total", [0, -5, None, "", "abc"])
    def test_total_zero_ou_invalido(self, total):
        assert fmt_percentual(10, total) == "0,0%"

    def test_parte_invalida(self):
        assert fmt_percentual(None, 100) == "0,0%"

    def test_complementares_somam_cerca_de_100(self):
        cc, total = 3031.05, 9719.98
        assert fmt_percentual(cc, total) == "31,2%"
        assert fmt_percentual(total - cc, total) == "68,8%"


class TestEstadoVazioHtml:
    def test_tem_icone_titulo_e_frase(self):
        h = estado_vazio_html("🏦", "Nenhum movimento em Nov/26", "Lance uma receita.")
        assert "🏦" in h and "Nenhum movimento em Nov/26" in h and "Lance uma receita." in h

    def test_escapa_html(self):
        h = estado_vazio_html("<i>", "<b>t</b>", "<script>x</script>")
        assert "<b>" not in h and "<script>" not in h and "&lt;script&gt;" in h

    def test_sem_cor_fixa_de_fundo_ou_texto(self):
        # regra 8: só herda a cor do tema
        h = estado_vazio_html("x", "t", "f").lower()
        assert "background" not in h and "color:" not in h and "#" not in h


class TestKpiAlturaMinima:
    def test_padrao_continua_8_6rem(self):
        assert "min-height:8.6rem" in kpi_card_html("x", "r", "v", "blue")

    def test_altura_personalizada(self):
        h = kpi_card_html("x", "r", "v", "blue", altura_min="5.5rem")
        assert "min-height:5.5rem" in h and "8.6rem" not in h

    def test_altura_e_escapada(self):
        assert '"><script' not in kpi_card_html("x", "r", "v", "blue", altura_min='1rem"><script>')


class _FakeSt:
    def __init__(self):
        self.session_state, self.avisos, self.trocas = {}, [], []

    def warning(self, msg):
        self.avisos.append(msg)

    def switch_page(self, pagina):
        self.trocas.append(pagina)


@pytest.fixture
def fake_st(monkeypatch):
    fake = _FakeSt()
    monkeypatch.setattr(navegacao, "st", fake)
    return fake


class TestNavegacao:
    def test_registrar_e_buscar(self, fake_st):
        navegacao.registrar_paginas({"lancar-despesa": "PAG_D", "lancar-receita": "PAG_R"})
        assert navegacao.pagina_registrada("lancar-despesa") == "PAG_D"
        assert navegacao.pagina_registrada("nao-existe") is None

    def test_ir_para_troca_de_pagina(self, fake_st):
        navegacao.registrar_paginas({"lancar-receita": "PAG_R"})
        navegacao.ir_para("lancar-receita")
        assert fake_st.trocas == ["PAG_R"] and fake_st.avisos == []

    def test_ir_para_sem_registro_avisa_e_nao_quebra(self, fake_st):
        navegacao.ir_para("lancar-despesa")
        assert fake_st.trocas == [] and len(fake_st.avisos) == 1

    def test_registrar_de_novo_substitui(self, fake_st):
        navegacao.registrar_paginas({"a": 1})
        navegacao.registrar_paginas({"b": 2})
        assert navegacao.pagina_registrada("a") is None and navegacao.pagina_registrada("b") == 2

    def test_registrar_copia_o_mapa(self, fake_st):
        mapa = {"a": 1}
        navegacao.registrar_paginas(mapa)
        mapa["a"] = 99
        assert navegacao.pagina_registrada("a") == 1
