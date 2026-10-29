"""
Testes da linha do tempo de meses do Dashboard:
  • janela de 6 meses e valor de cada bloco (logica/dashboard.py);
  • HTML dos blocos (utils/formatacao.py);
  • planejado dos meses futuros (logica/planejamento.py) — tem de bater com o
    resumo do panorama do Planejamento 12 Meses.
"""

import pandas as pd
import pytest

import logica.planejamento as plan
from logica.dashboard import janela_meses, linha_do_tempo
from utils.formatacao import fmt_moeda_inteiro, linha_do_tempo_html


def desp(*linhas):
    return pd.DataFrame([{"data": d, "valor": v, "status": s} for d, v, s in linhas])


# ── janela ────────────────────────────────────────────────────────────────────

class TestJanela:
    def test_tres_antes_selecionado_e_dois_depois(self):
        assert janela_meses("2026-10") == ["2026-07", "2026-08", "2026-09",
                                           "2026-10", "2026-11", "2026-12"]

    def test_virada_de_ano_nos_dois_sentidos(self):
        assert janela_meses("2026-01") == ["2025-10", "2025-11", "2025-12",
                                           "2026-01", "2026-02", "2026-03"]
        assert janela_meses("2026-12") == ["2026-09", "2026-10", "2026-11",
                                           "2026-12", "2027-01", "2027-02"]


# ── valor de cada bloco ───────────────────────────────────────────────────────

DESPESAS = desp(("2026-07-10", 100.10, "pago"), ("2026-08-10", 200.20, "pago"),
                ("2026-09-10", 300.30, "pago"), ("2026-10-05", 400.40, "pago"),
                ("2026-10-28", 999.0, "pendente"),     # pendente NÃO entra no pago
                ("2026-11-15", 555.0, "pago"))          # despesa futura não é "paga"


class TestBlocos:
    def test_seis_blocos_na_ordem(self):
        b = linha_do_tempo("2026-10", "2026-10", DESPESAS, {"2026-11": 1.0, "2026-12": 2.0})
        assert [x["mes"] for x in b] == ["2026-07", "2026-08", "2026-09",
                                         "2026-10", "2026-11", "2026-12"]

    def test_passado_e_atual_usam_despesas_pagas(self):
        b = {x["mes"]: x for x in linha_do_tempo("2026-10", "2026-10", DESPESAS, {})}
        assert b["2026-07"]["valor"] == pytest.approx(100.10)
        assert b["2026-09"]["valor"] == pytest.approx(300.30)
        assert b["2026-10"]["valor"] == pytest.approx(400.40)   # pendente de fora
        assert not b["2026-10"]["planejado"] and not b["2026-07"]["planejado"]

    def test_futuro_usa_o_planejado_e_nao_o_lancado(self):
        b = {x["mes"]: x for x in linha_do_tempo("2026-10", "2026-10", DESPESAS,
                                                 {"2026-11": 1234.5, "2026-12": 77.0})}
        assert b["2026-11"]["valor"] == 1234.5     # não 555 (lançado)
        assert b["2026-12"]["valor"] == 77.0
        assert b["2026-11"]["planejado"] and b["2026-12"]["planejado"]

    def test_futuro_sem_planejado_fica_none(self):
        b = {x["mes"]: x for x in linha_do_tempo("2026-10", "2026-10", DESPESAS, {"2026-11": 5.0})}
        assert b["2026-12"]["valor"] is None

    def test_so_o_selecionado_e_marcado(self):
        b = linha_do_tempo("2026-09", "2026-10", DESPESAS, {})
        assert [x["mes"] for x in b if x["selecionado"]] == ["2026-09"]

    def test_selecionado_no_futuro_mostra_planejado_com_destaque(self):
        b = {x["mes"]: x for x in linha_do_tempo("2026-12", "2026-10", DESPESAS,
                                                 {"2026-11": 1.0, "2026-12": 9.0, "2027-01": 3.0, "2027-02": 4.0})}
        assert b["2026-12"]["selecionado"] and b["2026-12"]["planejado"]
        assert b["2026-12"]["valor"] == 9.0
        assert b["2026-10"]["valor"] == pytest.approx(400.40)

    def test_selecionado_no_passado_so_marca_planejado_depois_do_mes_atual(self):
        # selecionado = agosto: a janela (maio a outubro) não passa do mês atual → nada planejado
        b = linha_do_tempo("2026-08", "2026-10", DESPESAS, {})
        assert [x["planejado"] for x in b] == [False] * 6
        # selecionado = setembro: só novembro (depois de outubro) é planejado
        b = {x["mes"]: x["planejado"] for x in linha_do_tempo("2026-09", "2026-10", DESPESAS, {})}
        assert b["2026-10"] is False and b["2026-11"] is True

    def test_rotulos_com_ano_so_no_selecionado_e_em_janeiro(self):
        b = {x["mes"]: x["rotulo"] for x in linha_do_tempo("2026-12", "2026-12", DESPESAS, {})}
        assert b["2026-12"] == "Dez/26"
        assert b["2027-01"] == "Jan/27"
        assert b["2026-10"] == "Out"
        assert b["2027-02"] == "Fev"

    def test_sem_despesas(self):
        for df in (pd.DataFrame(), None):
            assert [x["valor"] for x in linha_do_tempo("2026-10", "2026-10", df, {})][:4] == [0.0] * 4

    def test_mesma_regra_dos_cartoes_do_dashboard(self):
        from logica.dashboard import resumo_mes
        bloco = [x for x in linha_do_tempo("2026-10", "2026-10", DESPESAS, {}) if x["selecionado"]][0]
        assert bloco["valor"] == resumo_mes(DESPESAS, None, "2026-10")["total_desp"]


# ── HTML ──────────────────────────────────────────────────────────────────────

BLOCOS = linha_do_tempo("2026-10", "2026-10", DESPESAS, {"2026-11": 5120.4})   # dez sem planejado


class TestHtml:
    def test_fmt_moeda_inteiro(self):
        assert fmt_moeda_inteiro(4805.5) == "R$ 4.806"
        assert fmt_moeda_inteiro(420.5) == "R$ 421"      # meio sempre para cima (não para o par)
        assert fmt_moeda_inteiro(2.5) == "R$ 3"
        assert fmt_moeda_inteiro(1.4999) == "R$ 1"
        assert fmt_moeda_inteiro(0) == "R$ 0"
        assert fmt_moeda_inteiro(1234567.0) == "R$ 1.234.567"
        assert fmt_moeda_inteiro("x") == "—"

    def test_seis_blocos_um_selecionado_dois_tracejados(self):
        h = linha_do_tempo_html(BLOCOS)
        assert h.count('<div class="tl-bloco') == 6
        assert h.count("tl-sel\"") == 1 or h.count(" tl-sel\"") == 1
        assert h.count('class="tl-bloco tl-fut') == 2

    def test_valores_e_traco_para_sem_planejado(self):
        h = linha_do_tempo_html(BLOCOS)
        assert "R$ 100" in h and "R$ 400" in h and "R$ 5.120" in h
        assert ">—<" in h                          # dezembro sem planejado

    def test_planejado_so_nos_futuros(self):
        h = linha_do_tempo_html(BLOCOS)
        assert h.count('<span class="tl-longo">planejado</span>') == 2

    def test_escapa_html(self):
        h = linha_do_tempo_html([{"mes": "x", "rotulo": "<b>x</b>", "valor": 1.0,
                                  "planejado": False, "selecionado": False}])
        assert "<b>x</b>" not in h and "&lt;b&gt;" in h

    def test_tema_sem_cores_claras_fixas(self):
        h = linha_do_tempo_html(BLOCOS)
        for proibida in ("background: white", "background:white", "#fff", "#e2e8f0",
                         "#64748b", "#eff6ff", "#bfdbfe", "#1e3a8a"):
            assert proibida not in h
        assert "rgba(128,128,128" in h

    def test_tem_regra_para_celular(self):
        assert "@media (max-width:640px)" in linha_do_tempo_html(BLOCOS)


# ── planejado (I/O com loaders trocados) ──────────────────────────────────────

MESES = ["2026-11", "2026-12", "2027-01", "2027-02", "2027-03", "2027-04",
         "2027-05", "2027-06", "2027-07", "2027-08", "2027-09", "2027-10"]


@pytest.fixture
def dados(monkeypatch):
    monkeypatch.setattr(plan, "proximos_12_meses", lambda: list(MESES))
    parcelas = pd.DataFrame([
        {"vencimento": "2026-11-10", "valor": 120.5, "status": "pendente", "descricao": "TV 1/3"},
        {"vencimento": "2026-12-10", "valor": 120.5, "status": "pendente", "descricao": "TV 2/3"},
        {"vencimento": "2026-12-15", "valor": 999.0, "status": "pago", "descricao": "paga"},
    ])
    despesas = pd.DataFrame([
        {"data": "2026-09-05", "valor": 300.0, "pagamento": "Pix", "categoria": "Contas da casa",
         "descricao": "Internet", "recorrente": "sim", "recorrencia_fim": ""},
        {"data": "2026-12-20", "valor": 80.0, "pagamento": "Pix", "categoria": "Lazer",
         "descricao": "Show", "recorrente": "nao", "recorrencia_fim": ""},
    ])
    receitas = pd.DataFrame([
        {"data": "2026-09-01", "valor": 5000.0, "categoria": "Salário", "descricao": "Salário",
         "recorrente": "sim", "recorrencia_fim": ""},
    ])
    planejamento = pd.DataFrame([
        {"mes": "2026-11", "tipo": "despesa", "descricao": "IPTU", "valor": 450.0, "categoria": "Impostos e taxas"},
    ])
    monkeypatch.setattr(plan, "carregar_parcelas", lambda: parcelas)
    monkeypatch.setattr(plan, "carregar_despesas", lambda: despesas)
    monkeypatch.setattr(plan, "carregar_receitas", lambda: receitas)
    monkeypatch.setattr(plan, "carregar_planejamento", lambda: planejamento)


class TestPlanejadoDosMeses:
    def test_bate_com_o_resumo_do_panorama(self, dados):
        _, resumo = plan._computar_panorama()
        proprio = plan.projetar_resumo_meses(MESES)
        pd.testing.assert_frame_equal(resumo.reset_index(drop=True), proprio.reset_index(drop=True))

    def test_despesas_planejadas_somam_as_fontes(self, dados):
        r = plan.despesas_planejadas_por_mes(["2026-11", "2026-12"])
        # nov: parcela 120,50 + internet recorrente 300 + IPTU 450
        assert r["2026-11"] == pytest.approx(870.5)
        # dez: parcela 120,50 + internet 300 + show avulso 80 (parcela paga fica de fora)
        assert r["2026-12"] == pytest.approx(500.5)

    def test_mes_fora_dos_12_cobertos_nao_aparece(self, dados):
        r = plan.despesas_planejadas_por_mes(["2026-10", "2026-11", "2027-11", "2028-01"])
        assert list(r) == ["2026-11"]              # atual (2026-10) e além de 12 meses: sem planejado

    def test_lista_vazia_ou_toda_fora_nao_le_planilha(self, monkeypatch):
        monkeypatch.setattr(plan, "proximos_12_meses", lambda: list(MESES))

        def explode():
            raise AssertionError("não devia ler a planilha")
        for nome in ("carregar_parcelas", "carregar_despesas", "carregar_receitas", "carregar_planejamento"):
            monkeypatch.setattr(plan, nome, explode)
        assert plan.despesas_planejadas_por_mes([]) == {}
        assert plan.despesas_planejadas_por_mes(["2026-01"]) == {}

    def test_planilhas_vazias_dao_zero(self, monkeypatch):
        monkeypatch.setattr(plan, "proximos_12_meses", lambda: list(MESES))
        for nome in ("carregar_parcelas", "carregar_despesas", "carregar_receitas", "carregar_planejamento"):
            monkeypatch.setattr(plan, nome, lambda: pd.DataFrame())
        assert plan.despesas_planejadas_por_mes(["2026-11", "2026-12"]) == {"2026-11": 0.0, "2026-12": 0.0}

    def test_nao_usa_o_cache_de_sessao(self, dados, monkeypatch):
        import streamlit as st
        st.session_state["panorama_cache"] = {"df_linhas": None, "df_resumo": pd.DataFrame(), "ts": None}
        try:
            assert plan.despesas_planejadas_por_mes(["2026-11"])["2026-11"] == pytest.approx(870.5)
        finally:
            st.session_state.pop("panorama_cache", None)
