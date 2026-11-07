"""Limite de tentativas de login compartilhado entre sessões (utils/limite_login.py + auth.py)."""
import pytest
from streamlit.testing.v1 import AppTest

import auth
from utils.limite_login import LimiteLogin, texto_espera


class Relogio:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def avancar(self, s):
        self.t += s


@pytest.fixture
def rel():
    return Relogio()


@pytest.fixture
def lim(rel):
    return LimiteLogin(max_falhas=5, janela_s=900, bloqueio_s=900, max_falhas_global=30, relogio=rel)


def falhar(lim, nome, n):
    for _ in range(n):
        lim.registrar_falha(nome)


class TestLimitadorPorNome:
    def test_comeca_livre(self, lim):
        assert lim.segundos_bloqueado("ricardo") == 0 and lim.falhas_restantes("ricardo") == 5

    def test_conta_as_falhas_restantes(self, lim):
        falhar(lim, "ricardo", 2)
        assert lim.falhas_restantes("ricardo") == 3 and lim.segundos_bloqueado("ricardo") == 0

    def test_bloqueia_na_quinta_falha(self, lim):
        falhar(lim, "ricardo", 4)
        assert lim.segundos_bloqueado("ricardo") == 0
        lim.registrar_falha("ricardo")
        assert lim.segundos_bloqueado("ricardo") == 900

    def test_bloqueio_diminui_com_o_tempo_e_termina(self, lim, rel):
        falhar(lim, "ricardo", 5)
        rel.avancar(600)
        assert lim.segundos_bloqueado("ricardo") == 300
        rel.avancar(300)
        assert lim.segundos_bloqueado("ricardo") == 0

    def test_depois_do_bloqueio_recomeca_do_zero(self, lim, rel):
        falhar(lim, "ricardo", 5)
        rel.avancar(901)
        assert lim.falhas_restantes("ricardo") == 5

    def test_falhas_antigas_saem_da_janela(self, lim, rel):
        falhar(lim, "ricardo", 4)
        rel.avancar(901)
        lim.registrar_falha("ricardo")
        assert lim.segundos_bloqueado("ricardo") == 0 and lim.falhas_restantes("ricardo") == 4

    def test_nomes_sao_independentes(self, lim):
        falhar(lim, "ricardo", 5)
        assert lim.segundos_bloqueado("ricardo") > 0
        assert lim.segundos_bloqueado("jociara") == 0 and lim.falhas_restantes("jociara") == 5

    def test_nome_ignora_maiuscula_e_espacos(self, lim):
        falhar(lim, "  Ricardo ", 3)
        falhar(lim, "RICARDO", 2)
        assert lim.segundos_bloqueado("ricardo") == 900

    def test_sucesso_zera_as_falhas_do_nome(self, lim):
        falhar(lim, "ricardo", 4)
        lim.registrar_sucesso("ricardo")
        assert lim.falhas_restantes("ricardo") == 5

    def test_nome_que_nao_existe_tambem_e_contado(self, lim):
        # não pode revelar quais usuários existem: "fulano" é bloqueado igual a "ricardo"
        falhar(lim, "fulano-inexistente", 5)
        assert lim.segundos_bloqueado("fulano-inexistente") == 900

    def test_modo_senha_unica_usa_uma_chave_so(self, lim):
        falhar(lim, "", 5)
        assert lim.segundos_bloqueado("") == 900 and lim.segundos_bloqueado(None) == 900


class TestLimitadorGlobal:
    def test_muitos_nomes_diferentes_bloqueiam_todo_mundo(self, lim):
        for i in range(30):
            lim.registrar_falha(f"nome{i}")          # nenhum nome passa de 1 falha
        assert lim.bloqueio_global() == 900
        assert lim.segundos_bloqueado("ricardo") == 900   # até quem nunca errou

    def test_abaixo_do_limite_global_nao_bloqueia(self, lim):
        for i in range(29):
            lim.registrar_falha(f"nome{i}")
        assert lim.bloqueio_global() == 0 and lim.segundos_bloqueado("ricardo") == 0

    def test_bloqueio_global_termina(self, lim, rel):
        for i in range(30):
            lim.registrar_falha(f"nome{i}")
        rel.avancar(901)
        assert lim.bloqueio_global() == 0 and lim.segundos_bloqueado("ricardo") == 0

    def test_sucesso_nao_zera_o_contador_global(self, lim):
        for i in range(29):
            lim.registrar_falha(f"nome{i}")
        lim.registrar_sucesso("nome0")
        lim.registrar_falha("outro")
        assert lim.bloqueio_global() == 900


class TestLimitesDeMemoria:
    def test_nomes_demais_dividem_uma_chave_so(self, rel):
        lim = LimiteLogin(max_chaves=3, max_falhas_global=10_000, relogio=rel)
        for i in range(50):
            lim.registrar_falha(f"nome{i}")
        assert len(lim._falhas) <= 4          # 3 nomes + a chave "outros"

    def test_nome_gigante_e_cortado(self, lim):
        assert len(lim.normalizar("a" * 5000)) == 64

    def test_chaves_vazias_sao_podadas(self, lim, rel):
        falhar(lim, "a", 2)
        rel.avancar(901)
        lim.segundos_bloqueado("a")
        assert "a" not in lim._falhas


class TestTextoEspera:
    @pytest.mark.parametrize("seg,esperado", [(0, "agora"), (1, "menos de 1 minuto"), (59, "menos de 1 minuto"),
                                              (60, "1 minuto"), (61, "2 minutos"), (900, "15 minutos")])
    def test_textos(self, seg, esperado):
        assert texto_espera(seg) == esperado


# ── Fluxo real de login (auth.py) com várias sessões ──────────────────────────────────
SCRIPT = ("import streamlit as st\nimport auth\nauth.verificar_autenticacao()\n"
          "st.write('ENTROU:' + st.session_state['usuario'])\n")


@pytest.fixture
def app(monkeypatch, rel):
    limitador = LimiteLogin(relogio=rel)
    monkeypatch.setattr(auth, "_limitador", lambda: limitador)       # compartilhado entre as "abas"
    monkeypatch.setattr(auth.time, "sleep", lambda s: None)

    def nova_sessao():
        at = AppTest.from_string(SCRIPT, default_timeout=30)
        at.secrets["APP_PASSWORD"] = "x"
        at.secrets["USUARIOS"] = {"Ricardo": "senha-do-ricardo", "Jociara": "senha-da-jociara"}
        at.run()
        return at
    nova_sessao.limitador = limitador
    return nova_sessao


def tentar(at, nome, senha):
    at.text_input[0].set_value(nome)
    at.text_input[1].set_value(senha)
    at.button[0].click()
    at.run()
    return at


def textos_de_erro(at):
    return " | ".join(e.value for e in at.error)


class TestFluxoDeLogin:
    def test_login_correto_entra(self, app):
        at = tentar(app(), "Ricardo", "senha-do-ricardo")
        assert any("ENTROU:Ricardo" in m.value for m in at.markdown)

    def test_senha_errada_mostra_tentativas_restantes(self, app):
        at = tentar(app(), "Ricardo", "errada")
        assert "Tentativas restantes: 4" in textos_de_erro(at)

    def test_varias_abas_somam_as_falhas(self, app):
        """O furo do contador antigo: cada aba nova começava do zero."""
        for _ in range(5):
            tentar(app(), "Ricardo", "errada")                # cinco sessões diferentes, 1 falha cada
        at = tentar(app(), "Ricardo", "senha-do-ricardo")      # a senha CERTA, numa sexta aba
        assert not any("ENTROU" in m.value for m in at.markdown)
        assert "Muitas tentativas" in textos_de_erro(at)

    def test_bloqueio_nao_confere_nem_a_senha_certa(self, app):
        for _ in range(5):
            tentar(app(), "Ricardo", "errada")
        at = tentar(app(), "RICARDO ", "senha-do-ricardo")
        assert "ENTROU" not in " ".join(m.value for m in at.markdown)

    def test_bloqueio_de_um_usuario_nao_afeta_o_outro(self, app):
        for _ in range(5):
            tentar(app(), "Ricardo", "errada")
        at = tentar(app(), "Jociara", "senha-da-jociara")
        assert any("ENTROU:Jociara" in m.value for m in at.markdown)

    def test_depois_de_15_minutos_libera(self, app, rel):
        for _ in range(5):
            tentar(app(), "Ricardo", "errada")
        rel.avancar(901)
        at = tentar(app(), "Ricardo", "senha-do-ricardo")
        assert any("ENTROU:Ricardo" in m.value for m in at.markdown)

    def test_sucesso_zera_as_falhas(self, app):
        for _ in range(4):
            tentar(app(), "Ricardo", "errada")
        tentar(app(), "Ricardo", "senha-do-ricardo")
        assert app.limitador.falhas_restantes("Ricardo") == 5

    def test_usuario_inexistente_tem_a_mesma_mensagem(self, app):
        a = textos_de_erro(tentar(app(), "Ricardo", "errada"))
        b = textos_de_erro(tentar(app(), "naoexiste", "errada"))
        assert a == b

    def test_bloqueio_global_trava_a_tela_de_login(self, app):
        for i in range(30):
            app.limitador.registrar_falha(f"nome{i}")
        at = app()
        assert len(at.text_input) == 0 and "Muitas tentativas" in textos_de_erro(at)
