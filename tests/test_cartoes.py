"""
Testes para logica/cartoes.py:

- estimar_vencimento_parcela(): cálculo automático por "dia fixo do mês",
  usado apenas como estimativa/fallback (função pura, sem dependência de
  Sheets/Streamlit).
- resolver_vencimento_parcela(): decide entre usar um fechamento MANUAL já
  registrado (prioridade) ou cair na estimativa automática. Também é pura,
  pois recebe a lista de fechamentos já carregada como parâmetro.
"""

from datetime import date

from logica.cartoes import estimar_vencimento_parcela, resolver_vencimento_parcela


class TestEstimarVencimentoParcela:

    def test_compra_antes_do_fechamento_primeira_parcela(self):
        # Cartão fecha dia 5, vence dia 12. Compra em 01/07 (antes do fechamento)
        # -> a fatura corrente ainda pode receber a compra.
        resultado = estimar_vencimento_parcela(
            data_compra=date(2026, 7, 1), dia_fechamento=5, dia_vencimento=12, num_parcela=1
        )
        assert resultado == date(2026, 7, 12)

    def test_compra_depois_do_fechamento_vai_para_proxima_fatura(self):
        # Mesma configuração, mas a compra em 10/07 é depois do fechamento (dia 5)
        # -> só entra na fatura seguinte.
        resultado = estimar_vencimento_parcela(
            data_compra=date(2026, 7, 10), dia_fechamento=5, dia_vencimento=12, num_parcela=1
        )
        assert resultado == date(2026, 8, 12)

    def test_compra_no_dia_exato_do_fechamento_ainda_entra_na_fatura_atual(self):
        # data_compra > fechamento é a condição — no dia exato, ainda é a fatura atual.
        resultado = estimar_vencimento_parcela(
            data_compra=date(2026, 7, 5), dia_fechamento=5, dia_vencimento=12, num_parcela=1
        )
        assert resultado == date(2026, 7, 12)

    def test_dia_vencimento_menor_que_fechamento_soma_mes_extra(self):
        # Cartão fecha dia 25, vence dia 2 do mês seguinte (Santander no cadastro padrão).
        # Como vencimento(2) < fechamento(25), o cálculo já teria empurrado um mês
        # a mais mesmo estando dentro do ciclo de fechamento.
        resultado = estimar_vencimento_parcela(
            data_compra=date(2026, 7, 1), dia_fechamento=25, dia_vencimento=2, num_parcela=1
        )
        assert resultado == date(2026, 8, 2)

    def test_segunda_e_terceira_parcelas_avancam_um_mes_por_parcela(self):
        base_kwargs = dict(data_compra=date(2026, 7, 1), dia_fechamento=5, dia_vencimento=12)
        p1 = estimar_vencimento_parcela(**base_kwargs, num_parcela=1)
        p2 = estimar_vencimento_parcela(**base_kwargs, num_parcela=2)
        p3 = estimar_vencimento_parcela(**base_kwargs, num_parcela=3)
        assert p1 == date(2026, 7, 12)
        assert p2 == date(2026, 8, 12)
        assert p3 == date(2026, 9, 12)

    def test_dia_fechamento_invalido_para_o_mes_usa_ultimo_dia(self):
        # Fevereiro de 2026 (não bissexto) não tem dia 31; a função deve
        # tratar isso como "fechamento no último dia do mês" (28/02) em vez
        # de estourar ValueError.
        resultado = estimar_vencimento_parcela(
            data_compra=date(2026, 2, 15), dia_fechamento=31, dia_vencimento=5, num_parcela=1
        )
        assert resultado == date(2026, 3, 5)

    def test_dia_vencimento_e_limitado_ao_ultimo_dia_do_mes_de_vencimento(self):
        # Vencimento configurado como dia 31, mas cai em setembro (30 dias)
        # -> deve ser limitado (capado) a 30.
        resultado = estimar_vencimento_parcela(
            data_compra=date(2026, 9, 1), dia_fechamento=5, dia_vencimento=31, num_parcela=1
        )
        assert resultado == date(2026, 9, 30)

    def test_virada_de_ano_na_projecao_de_parcelas(self):
        resultado = estimar_vencimento_parcela(
            data_compra=date(2026, 11, 20), dia_fechamento=5, dia_vencimento=12, num_parcela=3
        )
        # compra após fechamento (+1) + 2 meses de parcela (parcela 3 -> +2) = +3 meses a partir de novembro
        assert resultado == date(2027, 2, 12)


class TestResolverVencimentoParcela:

    def test_usa_fechamento_manual_quando_disponivel(self):
        # Fechamento real registrado prevalece sobre a estimativa automática.
        fechamentos = [{
            "mes_referencia": "2026-07",
            "data_fechamento": date(2026, 7, 3),
            "data_vencimento": date(2026, 7, 10),
        }]
        venc, origem = resolver_vencimento_parcela(
            data_compra=date(2026, 7, 1), dia_fechamento=5, dia_vencimento=12,
            num_parcela=1, fechamentos_ordenados=fechamentos
        )
        assert venc == date(2026, 7, 10)
        assert origem == "manual"

    def test_cai_para_estimativa_quando_nao_ha_fechamento_manual(self):
        venc, origem = resolver_vencimento_parcela(
            data_compra=date(2026, 7, 1), dia_fechamento=5, dia_vencimento=12,
            num_parcela=1, fechamentos_ordenados=[]
        )
        assert venc == date(2026, 7, 12)  # mesmo resultado de estimar_vencimento_parcela
        assert origem == "estimado"

    def test_fechamento_manual_prevalece_mesmo_se_diferente_da_estimativa(self):
        # Fechamento real ficou 2 dias depois do que o dia fixo cadastrado sugeriria —
        # é exatamente o caso que motivou essa mudança (fechamento varia mês a mês).
        fechamentos = [{
            "mes_referencia": "2026-07",
            "data_fechamento": date(2026, 7, 7),
            "data_vencimento": date(2026, 7, 14),
        }]
        venc, origem = resolver_vencimento_parcela(
            data_compra=date(2026, 7, 1), dia_fechamento=5, dia_vencimento=12,
            num_parcela=1, fechamentos_ordenados=fechamentos
        )
        assert venc == date(2026, 7, 14)  # não é 12 (estimativa) — é 14 (real)
        assert origem == "manual"

    def test_segunda_parcela_usa_o_segundo_fechamento_manual(self):
        fechamentos = [
            {"mes_referencia": "2026-07", "data_fechamento": date(2026, 7, 5), "data_vencimento": date(2026, 7, 12)},
            {"mes_referencia": "2026-08", "data_fechamento": date(2026, 8, 6), "data_vencimento": date(2026, 8, 13)},
        ]
        venc, origem = resolver_vencimento_parcela(
            data_compra=date(2026, 7, 1), dia_fechamento=5, dia_vencimento=12,
            num_parcela=2, fechamentos_ordenados=fechamentos
        )
        assert venc == date(2026, 8, 13)
        assert origem == "manual"

    def test_parcela_futura_sem_fechamento_suficiente_cai_para_estimativa(self):
        # Só há fechamento manual para a 1ª parcela — a 3ª ainda não tem
        # fechamento futuro registrado, então recai na estimativa.
        fechamentos = [
            {"mes_referencia": "2026-07", "data_fechamento": date(2026, 7, 5), "data_vencimento": date(2026, 7, 12)},
        ]
        venc, origem = resolver_vencimento_parcela(
            data_compra=date(2026, 7, 1), dia_fechamento=5, dia_vencimento=12,
            num_parcela=3, fechamentos_ordenados=fechamentos
        )
        assert venc == date(2026, 9, 12)  # estimativa automática para a 3ª parcela
        assert origem == "estimado"

    def test_buraco_no_meio_nao_desalinha_as_parcelas_seguintes(self):
        # Fechamento de agosto NÃO foi registrado (buraco), mas isso não
        # deve "empurrar" a parcela de setembro para o lugar errado — cada
        # parcela busca seu próprio mês-alvo, não uma posição na lista.
        # Este é o cenário que motivou a reescrita do algoritmo.
        fechamentos = [
            {"mes_referencia": "2026-07", "data_fechamento": date(2026, 7, 5), "data_vencimento": date(2026, 7, 12)},
            {"mes_referencia": "2026-09", "data_fechamento": date(2026, 9, 4), "data_vencimento": date(2026, 9, 11)},
        ]
        v1, o1 = resolver_vencimento_parcela(date(2026, 7, 1), 5, 12, 1, fechamentos)
        v2, o2 = resolver_vencimento_parcela(date(2026, 7, 1), 5, 12, 2, fechamentos)
        v3, o3 = resolver_vencimento_parcela(date(2026, 7, 1), 5, 12, 3, fechamentos)

        assert (v1, o1) == (date(2026, 7, 12), "manual")   # usa o fechamento real de julho
        assert (v2, o2) == (date(2026, 8, 12), "estimado")  # agosto não registrado -> estimativa isolada, não quebra nada
        assert (v3, o3) == (date(2026, 9, 11), "manual")    # setembro segue usando o fechamento real normalmente

    def test_fechamentos_fora_de_ordem_na_lista_ainda_funcionam(self):
        # indexar_fechamentos_por_mes busca por rótulo, não por ordem —
        # então o resultado não deve depender da lista já estar ordenada
        # (mesmo que fechamentos_ordenados_por_cartao sempre a ordene).
        fechamentos = [
            {"mes_referencia": "2026-09", "data_fechamento": date(2026, 9, 4), "data_vencimento": date(2026, 9, 11)},
            {"mes_referencia": "2026-07", "data_fechamento": date(2026, 7, 5), "data_vencimento": date(2026, 7, 12)},
        ]
        venc, origem = resolver_vencimento_parcela(
            data_compra=date(2026, 7, 1), dia_fechamento=5, dia_vencimento=12,
            num_parcela=1, fechamentos_ordenados=fechamentos
        )
        assert venc == date(2026, 7, 12)
        assert origem == "manual"

