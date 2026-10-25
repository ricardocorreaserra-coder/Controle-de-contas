"""
Testes dos avisos de confirmação das movimentações (utils/widgets.py):
`avisar`, `concluir_com_sucesso`, `exibir_mensagem_pendente` e
`exibir_toasts_pendentes`.

Por que existem: toda gravação termina em `st.rerun()`, que descarta qualquer
`st.success()` chamado antes dele. O aviso precisa ser AGENDADO e exibido na
execução seguinte — e na aba certa (telas com abas executam todas as abas).

O `streamlit` é trocado por um objeto falso que só registra as chamadas.
"""

import pytest

import utils.widgets as w


class FakeSt:
    def __init__(self):
        self.session_state = {}
        self.chamadas = []
        self.reruns = 0

    def success(self, msg, icon=None):
        self.chamadas.append(("success", msg, icon))

    def warning(self, msg, icon=None):
        self.chamadas.append(("warning", msg, icon))

    def toast(self, msg, icon=None, duration=None):
        self.chamadas.append(("toast", msg, icon, duration))

    def rerun(self):
        self.reruns += 1


@pytest.fixture
def fake(monkeypatch):
    f = FakeSt()
    monkeypatch.setattr(w, "st", f)
    return f


class TestAvisar:

    def test_apenas_agenda_nao_mostra_nada_ainda(self, fake):
        w.avisar("Despesa lançada")
        assert fake.chamadas == []
        assert fake.reruns == 0

    def test_quadro_mostra_sucesso_com_icone_e_descarta(self, fake):
        w.avisar("Despesa lançada")
        w.exibir_mensagem_pendente()
        assert fake.chamadas == [("success", "Despesa lançada", "✅")]
        w.exibir_mensagem_pendente()                      # já foi consumida
        assert len(fake.chamadas) == 1

    def test_tipo_excluido_usa_icone_de_lixeira(self, fake):
        w.avisar("Despesa #5 excluída", tipo="excluido")
        w.exibir_mensagem_pendente()
        assert fake.chamadas == [("success", "Despesa #5 excluída", "🗑️")]

    def test_tipo_aviso_usa_warning(self, fake):
        w.avisar("Parcela estornada", tipo="aviso")
        w.exibir_mensagem_pendente()
        assert fake.chamadas == [("warning", "Parcela estornada", "⚠️")]

    def test_tipo_desconhecido_vira_sucesso(self, fake):
        w.avisar("x", tipo="qualquer-coisa")
        w.exibir_mensagem_pendente()
        assert fake.chamadas[0][0] == "success"

    def test_sem_aviso_pendente_nao_mostra_nada(self, fake):
        w.exibir_mensagem_pendente()
        w.exibir_toasts_pendentes()
        assert fake.chamadas == []

    def test_texto_simples_no_formato_antigo_conta_como_sucesso(self, fake):
        fake.session_state[w.CHAVE_AVISO] = "mensagem antiga"
        w.exibir_mensagem_pendente()
        assert fake.chamadas == [("success", "mensagem antiga", "✅")]


class TestChavesPorAba:
    """Regressão: com a chave genérica, a 1ª aba a ler 'roubava' a mensagem."""

    def test_mensagem_de_uma_chave_nao_aparece_em_outra(self, fake):
        w.avisar("Cartão excluído", chave="_msg_cartoes")
        w.exibir_mensagem_pendente()                      # outra aba (chave genérica)
        w.exibir_mensagem_pendente("_msg_fechamentos")    # outra aba
        assert fake.chamadas == []
        w.exibir_mensagem_pendente("_msg_cartoes")        # a aba certa
        assert [c[1] for c in fake.chamadas] == ["Cartão excluído"]

    def test_avisos_em_chaves_diferentes_nao_se_sobrepoem(self, fake):
        w.avisar("A", chave="_a")
        w.avisar("B", chave="_b")
        w.exibir_mensagem_pendente("_b")
        w.exibir_mensagem_pendente("_a")
        assert [c[1] for c in fake.chamadas] == ["B", "A"]


class TestToasts:

    def test_toast_aparece_so_quando_exibir_toasts_pendentes_roda(self, fake):
        w.avisar("Despesa lançada")
        assert not [c for c in fake.chamadas if c[0] == "toast"]
        w.exibir_toasts_pendentes()
        assert fake.chamadas == [("toast", "Despesa lançada", "✅", "long")]

    def test_toast_e_exibido_uma_unica_vez(self, fake):
        w.avisar("x")
        w.exibir_toasts_pendentes()
        w.exibir_toasts_pendentes()
        assert len(fake.chamadas) == 1

    def test_varios_avisos_viram_varios_toasts_em_ordem(self, fake):
        w.avisar("primeiro", chave="_a")
        w.avisar("segundo", chave="_b", tipo="excluido")
        w.exibir_toasts_pendentes()
        assert fake.chamadas == [("toast", "primeiro", "✅", "long"),
                                 ("toast", "segundo", "🗑️", "long")]

    def test_toast_independe_da_aba_do_quadro(self, fake):
        # o aviso flutuante aparece mesmo que o quadro (chave) nunca seja lido
        w.avisar("Fechamento excluído", chave="_msg_fechamentos", tipo="excluido")
        w.exibir_toasts_pendentes()
        assert fake.chamadas[0][:2] == ("toast", "Fechamento excluído")

    def test_toast_e_quadro_nao_se_consomem_mutuamente(self, fake):
        w.avisar("x")
        w.exibir_toasts_pendentes()
        w.exibir_mensagem_pendente()
        assert [c[0] for c in fake.chamadas] == ["toast", "success"]


class TestConcluirComSucesso:

    def test_agenda_avisos_e_faz_rerun(self, fake):
        w.concluir_com_sucesso("Receita lançada")
        assert fake.reruns == 1
        w.exibir_mensagem_pendente()
        w.exibir_toasts_pendentes()
        assert [c[0] for c in fake.chamadas] == ["success", "toast"]

    def test_limpa_um_campo_de_valor(self, fake):
        w.concluir_com_sucesso("ok", campo_valor_base_key="desp_valor")
        assert fake.session_state["_v__desp_valor"] == 1

    def test_limpa_varios_campos_de_valor(self, fake):
        w.concluir_com_sucesso("ok", campo_valor_base_key=["a", "b"])
        assert fake.session_state["_v__a"] == 1
        assert fake.session_state["_v__b"] == 1

    def test_aceita_chave_e_tipo(self, fake):
        w.concluir_com_sucesso("Cartão cadastrado", chave="_msg_cartoes", tipo="sucesso")
        w.exibir_mensagem_pendente()                      # chave genérica: nada
        assert fake.chamadas == []
        w.exibir_mensagem_pendente("_msg_cartoes")
        assert fake.chamadas == [("success", "Cartão cadastrado", "✅")]
