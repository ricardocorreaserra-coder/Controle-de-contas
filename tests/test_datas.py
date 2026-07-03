"""
Testes para utils/datas.py — manipulação de datas e meses.

seletor_mes_ano() não é testada aqui pois é um widget de UI (usa
st.columns/st.selectbox) e depende de um contexto de execução do Streamlit;
ela não é uma função pura.
"""

import re
from datetime import date

from utils.datas import (
    fmt_mes_pt,
    fmt_mes_str_pt,
    add_months,
    hoje_str,
    proximos_12_meses,
    mes_ativo_recorrencia,
)


# ── fmt_mes_pt ─────────────────────────────────────────────────────────────────

class TestFmtMesPt:

    def test_mes_meio_de_ano(self):
        assert fmt_mes_pt(date(2026, 7, 1)) == "Jul/26"

    def test_mes_janeiro(self):
        assert fmt_mes_pt(date(2030, 1, 15)) == "Jan/30"

    def test_mes_dezembro(self):
        assert fmt_mes_pt(date(2025, 12, 25)) == "Dez/25"

    def test_ano_com_dois_digitos(self):
        # garante que só os 2 últimos dígitos do ano aparecem
        assert fmt_mes_pt(date(2099, 3, 1)) == "Mar/99"


# ── fmt_mes_str_pt ─────────────────────────────────────────────────────────────

class TestFmtMesStrPt:

    def test_conversao_valida(self):
        assert fmt_mes_str_pt("2026-07") == "Jul/26"

    def test_conversao_mes_janeiro(self):
        assert fmt_mes_str_pt("2030-01") == "Jan/30"

    def test_string_invalida_retorna_original(self):
        assert fmt_mes_str_pt("nao-e-um-mes") == "nao-e-um-mes"

    def test_string_vazia_retorna_original(self):
        assert fmt_mes_str_pt("") == ""

    def test_mes_fora_do_intervalo_retorna_original(self):
        # mês 13 não existe em MESES_PT -> deve cair no except e devolver o original
        assert fmt_mes_str_pt("2026-13") == "2026-13"


# ── add_months ─────────────────────────────────────────────────────────────────

class TestAddMonths:

    def test_soma_simples(self):
        assert add_months(date(2026, 7, 15), 3) == date(2026, 10, 15)

    def test_soma_com_virada_de_ano(self):
        assert add_months(date(2026, 11, 1), 3) == date(2027, 2, 1)

    def test_subtracao_meses_negativos(self):
        assert add_months(date(2026, 7, 15), -2) == date(2026, 5, 15)

    def test_subtracao_com_virada_de_ano(self):
        assert add_months(date(2026, 1, 15), -2) == date(2025, 11, 15)

    def test_fim_de_mes_ano_nao_bissexto(self):
        # 31/jan + 1 mês -> fevereiro só tem 28 dias em 2026
        assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)

    def test_fim_de_mes_ano_bissexto(self):
        # 2024 é bissexto -> fevereiro tem 29 dias
        assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)

    def test_zero_meses_retorna_mesma_data(self):
        assert add_months(date(2026, 7, 15), 0) == date(2026, 7, 15)

    def test_dia_31_para_mes_de_30_dias(self):
        assert add_months(date(2026, 8, 31), 1) == date(2026, 9, 30)


# ── hoje_str ───────────────────────────────────────────────────────────────────

class TestHojeStr:

    def test_formato_e_valor(self):
        resultado = hoje_str()
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", resultado)
        assert resultado == date.today().strftime("%Y-%m-%d")


# ── proximos_12_meses ────────────────────────────────────────────────────────────

class TestProximos12Meses:

    def test_retorna_doze_meses(self):
        assert len(proximos_12_meses()) == 12

    def test_formato_de_cada_item(self):
        for mes in proximos_12_meses():
            assert re.match(r"^\d{4}-\d{2}$", mes)

    def test_primeiro_mes_e_o_mes_seguinte_ao_atual(self):
        hoje = date.today()
        esperado = add_months(date(hoje.year, hoje.month, 1), 1).strftime("%Y-%m")
        assert proximos_12_meses()[0] == esperado

    def test_sequencia_e_crescente_sem_duplicatas(self):
        meses = proximos_12_meses()
        assert meses == sorted(meses)
        assert len(meses) == len(set(meses))

    def test_meses_sao_consecutivos(self):
        meses = proximos_12_meses()
        for i in range(len(meses) - 1):
            ano1, mes1 = map(int, meses[i].split("-"))
            ano2, mes2 = map(int, meses[i + 1].split("-"))
            data1 = date(ano1, mes1, 1)
            assert add_months(data1, 1) == date(ano2, mes2, 1)


# ── mes_ativo_recorrencia ─────────────────────────────────────────────────────

class TestMesAtivoRecorrencia:

    def test_mes_antes_do_inicio_e_inativo(self):
        assert mes_ativo_recorrencia("2026-05", date(2026, 7, 1), None) is False

    def test_mes_igual_ao_inicio_e_ativo(self):
        assert mes_ativo_recorrencia("2026-07", date(2026, 7, 1), None) is True

    def test_mes_apos_inicio_sem_fim_e_ativo(self):
        assert mes_ativo_recorrencia("2027-01", date(2026, 7, 1), None) is True

    def test_mes_apos_fim_e_inativo(self):
        assert mes_ativo_recorrencia("2026-10", date(2026, 7, 1), "2026-08-15") is False

    def test_mes_igual_ao_mes_do_fim_ainda_e_ativo(self):
        # a recorrência é encerrada "a partir de" essa data, então o próprio
        # mês do encerramento ainda conta como ativo
        assert mes_ativo_recorrencia("2026-08", date(2026, 7, 1), "2026-08-15") is True

    def test_mes_antes_do_fim_e_ativo(self):
        assert mes_ativo_recorrencia("2026-07", date(2026, 7, 1), "2026-12-01") is True

    def test_data_fim_vazia_e_tratada_como_sem_fim(self):
        assert mes_ativo_recorrencia("2030-01", date(2026, 7, 1), "") is True

    def test_data_fim_none_e_tratada_como_sem_fim(self):
        assert mes_ativo_recorrencia("2030-01", date(2026, 7, 1), None) is True
