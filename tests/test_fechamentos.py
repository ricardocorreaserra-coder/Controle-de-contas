"""
Testes para as funções puras de logica/fechamentos.py:

- encontrar_fechamento_para_compra() — acha o fechamento cuja data real
  "engoliu" a compra, usado como âncora da 1ª parcela.
- indexar_fechamentos_por_mes() — transforma a lista em busca por rótulo
  de mês, o que torna a resolução de parcelas resistente a buracos.
- detectar_buracos_fechamentos() — aponta meses sem fechamento registrado
  dentro do intervalo já coberto, para avisar o usuário na UI.
- obter_fechamento_parcela() — função LEGADA (busca por posição na lista);
  mantida só por compatibilidade, não é mais usada por
  resolver_vencimento_parcela. Os testes abaixo documentam o comportamento
  dela como estava, mas não use essa função em código novo.

Todas recebem a lista de fechamentos já carregada (não tocam em
Sheets/Streamlit), o que as torna fáceis de testar isoladamente.
"""

from datetime import date

from logica.fechamentos import (
    encontrar_fechamento_para_compra,
    obter_fechamento_parcela,
    indexar_fechamentos_por_mes,
    detectar_buracos_fechamentos,
)


def _f(data_fechamento, data_vencimento, mes_referencia=""):
    return {
        "mes_referencia": mes_referencia,
        "data_fechamento": data_fechamento,
        "data_vencimento": data_vencimento,
    }


class TestEncontrarFechamentoParaCompra:

    def test_compra_antes_do_unico_fechamento_registrado(self):
        fechamentos = [_f(date(2026, 7, 5), date(2026, 7, 12))]
        idx = encontrar_fechamento_para_compra(date(2026, 7, 1), fechamentos)
        assert idx == 0

    def test_compra_no_dia_exato_do_fechamento_ainda_cabe_nele(self):
        # ">=" na comparação -> o próprio dia do fechamento ainda conta.
        fechamentos = [_f(date(2026, 7, 5), date(2026, 7, 12))]
        idx = encontrar_fechamento_para_compra(date(2026, 7, 5), fechamentos)
        assert idx == 0

    def test_compra_apos_o_fechamento_vai_para_o_proximo_registrado(self):
        fechamentos = [
            _f(date(2026, 7, 5), date(2026, 7, 12)),
            _f(date(2026, 8, 6), date(2026, 8, 13)),
        ]
        idx = encontrar_fechamento_para_compra(date(2026, 7, 10), fechamentos)
        assert idx == 1

    def test_nenhum_fechamento_futuro_suficiente_retorna_none(self):
        fechamentos = [_f(date(2026, 7, 5), date(2026, 7, 12))]
        idx = encontrar_fechamento_para_compra(date(2026, 8, 1), fechamentos)
        assert idx is None

    def test_lista_vazia_retorna_none(self):
        assert encontrar_fechamento_para_compra(date(2026, 7, 1), []) is None

    def test_escolhe_o_primeiro_fechamento_aplicavel_mesmo_com_varios_futuros(self):
        fechamentos = [
            _f(date(2026, 7, 5), date(2026, 7, 12)),
            _f(date(2026, 8, 5), date(2026, 8, 12)),
            _f(date(2026, 9, 5), date(2026, 9, 12)),
        ]
        idx = encontrar_fechamento_para_compra(date(2026, 6, 20), fechamentos)
        assert idx == 0  # o primeiro fechamento futuro, não qualquer um deles


class TestObterFechamentoParcelaLegado:
    """Documenta o comportamento da função legada baseada em posição."""

    def test_primeira_parcela_usa_o_fechamento_encontrado(self):
        fechamentos = [_f(date(2026, 7, 5), date(2026, 7, 12), "2026-07")]
        f = obter_fechamento_parcela(date(2026, 7, 1), 1, fechamentos)
        assert f is not None
        assert f["mes_referencia"] == "2026-07"
        assert f["data_vencimento"] == date(2026, 7, 12)

    def test_segunda_parcela_avanca_para_o_proximo_fechamento(self):
        fechamentos = [
            _f(date(2026, 7, 5), date(2026, 7, 12), "2026-07"),
            _f(date(2026, 8, 6), date(2026, 8, 13), "2026-08"),
        ]
        f = obter_fechamento_parcela(date(2026, 7, 1), 2, fechamentos)
        assert f["mes_referencia"] == "2026-08"
        assert f["data_vencimento"] == date(2026, 8, 13)

    def test_parcela_sem_fechamento_futuro_suficiente_retorna_none(self):
        fechamentos = [_f(date(2026, 7, 5), date(2026, 7, 12), "2026-07")]
        f = obter_fechamento_parcela(date(2026, 7, 1), 2, fechamentos)
        assert f is None

    def test_com_buraco_no_meio_a_versao_legada_desalinha_a_parcela_seguinte(self):
        # Este teste documenta EXATAMENTE o defeito que motivou a
        # substituição por indexar_fechamentos_por_mes: com agosto faltando,
        # a "2ª posição" da lista aponta para setembro — não para a
        # estimativa de agosto que deveria ser usada.
        fechamentos = [
            _f(date(2026, 7, 5), date(2026, 7, 12), "2026-07"),
            _f(date(2026, 9, 4), date(2026, 9, 11), "2026-09"),  # agosto pulado
        ]
        f = obter_fechamento_parcela(date(2026, 7, 1), 2, fechamentos)
        # comportamento antigo (com defeito): devolve setembro em vez de
        # cair numa estimativa de agosto.
        assert f["mes_referencia"] == "2026-09"

    def test_lista_vazia_retorna_none(self):
        assert obter_fechamento_parcela(date(2026, 7, 1), 1, []) is None


class TestIndexarFechamentosPorMes:

    def test_indexa_por_mes_referencia(self):
        fechamentos = [
            _f(date(2026, 7, 5), date(2026, 7, 12), "2026-07"),
            _f(date(2026, 9, 4), date(2026, 9, 11), "2026-09"),
        ]
        idx = indexar_fechamentos_por_mes(fechamentos)
        assert set(idx.keys()) == {"2026-07", "2026-09"}
        assert idx["2026-07"]["data_vencimento"] == date(2026, 7, 12)

    def test_lista_vazia_retorna_dict_vazio(self):
        assert indexar_fechamentos_por_mes([]) == {}

    def test_ignora_registros_sem_mes_referencia(self):
        fechamentos = [_f(date(2026, 7, 5), date(2026, 7, 12), "")]
        assert indexar_fechamentos_por_mes(fechamentos) == {}

    def test_mes_duplicado_ultimo_prevalece(self):
        fechamentos = [
            _f(date(2026, 7, 4), date(2026, 7, 11), "2026-07"),
            _f(date(2026, 7, 6), date(2026, 7, 13), "2026-07"),
        ]
        idx = indexar_fechamentos_por_mes(fechamentos)
        assert idx["2026-07"]["data_vencimento"] == date(2026, 7, 13)


class TestDetectarBuracosFechamentos:

    def test_sequencia_contigua_sem_buracos(self):
        fechamentos = [
            _f(date(2026, 7, 5), date(2026, 7, 12), "2026-07"),
            _f(date(2026, 8, 6), date(2026, 8, 13), "2026-08"),
            _f(date(2026, 9, 4), date(2026, 9, 11), "2026-09"),
        ]
        assert detectar_buracos_fechamentos(fechamentos) == []

    def test_um_mes_faltando_no_meio(self):
        fechamentos = [
            _f(date(2026, 7, 5), date(2026, 7, 12), "2026-07"),
            _f(date(2026, 9, 4), date(2026, 9, 11), "2026-09"),
        ]
        assert detectar_buracos_fechamentos(fechamentos) == ["2026-08"]

    def test_varios_meses_faltando(self):
        fechamentos = [
            _f(date(2026, 3, 5), date(2026, 3, 12), "2026-03"),
            _f(date(2026, 7, 5), date(2026, 7, 12), "2026-07"),
        ]
        assert detectar_buracos_fechamentos(fechamentos) == ["2026-04", "2026-05", "2026-06"]

    def test_menos_de_dois_registros_nao_ha_intervalo_a_checar(self):
        fechamentos = [_f(date(2026, 7, 5), date(2026, 7, 12), "2026-07")]
        assert detectar_buracos_fechamentos(fechamentos) == []
        assert detectar_buracos_fechamentos([]) == []

    def test_virada_de_ano_no_intervalo(self):
        fechamentos = [
            _f(date(2026, 11, 5), date(2026, 11, 12), "2026-11"),
            _f(date(2027, 2, 4), date(2027, 2, 11), "2027-02"),
        ]
        assert detectar_buracos_fechamentos(fechamentos) == ["2026-12", "2027-01"]
