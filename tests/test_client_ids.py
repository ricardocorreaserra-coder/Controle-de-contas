"""
Testes para as funções puras de sheets/client.py que protegem contra IDs
duplicados quando duas pessoas gravam ao mesmo tempo (acesso compartilhado).

Nenhuma delas fala com o Google Sheets — recebem os dados já lidos.
"""

from sheets.client import numero_linha_do_range, resolver_colisao_id, montar_linha_por_nome


class TestNumeroLinhaDoRange:

    def test_range_com_nome_de_aba(self):
        assert numero_linha_do_range("despesas!A6:I6") == 6

    def test_range_sem_nome_de_aba(self):
        assert numero_linha_do_range("A12:I12") == 12

    def test_range_de_varias_linhas_devolve_a_primeira(self):
        assert numero_linha_do_range("parcelas!A10:J15") == 10

    def test_linha_com_varios_digitos(self):
        assert numero_linha_do_range("despesas!A1234:M1234") == 1234

    def test_aba_com_espaco_no_nome(self):
        assert numero_linha_do_range("Minha Aba!B7:C7") == 7

    def test_valores_invalidos_devolvem_none(self):
        # Sem linha identificável, quem chama simplesmente pula a checagem.
        assert numero_linha_do_range(None) is None
        assert numero_linha_do_range("") is None
        assert numero_linha_do_range("sem_numeros") is None


class TestResolverColisaoId:

    def test_sem_colisao_devolve_none(self):
        ids = ["id", "1", "2", "3"]
        assert resolver_colisao_id(ids, meu_id=3, minha_linha=4) is None

    def test_primeira_ocorrencia_mantem_o_id(self):
        # Duas linhas com id 3; a de cima (linha 4) tem direito de manter.
        ids = ["id", "1", "2", "3", "3"]
        assert resolver_colisao_id(ids, meu_id=3, minha_linha=4) is None

    def test_segunda_ocorrencia_recebe_id_novo(self):
        # A linha 5 perdeu a disputa e precisa de um id inédito.
        ids = ["id", "1", "2", "3", "3"]
        assert resolver_colisao_id(ids, meu_id=3, minha_linha=5) == 4

    def test_id_novo_e_maior_que_todos_os_existentes(self):
        ids = ["id", "1", "7", "7", "5"]
        assert resolver_colisao_id(ids, meu_id=7, minha_linha=4) == 8

    def test_colisao_tripla_todas_menos_a_primeira_cedem(self):
        ids = ["id", "2", "2", "2"]
        assert resolver_colisao_id(ids, meu_id=2, minha_linha=2) is None
        assert resolver_colisao_id(ids, meu_id=2, minha_linha=3) == 3
        assert resolver_colisao_id(ids, meu_id=2, minha_linha=4) == 3

    def test_ignora_celulas_nao_numericas_ao_calcular_o_proximo_id(self):
        ids = ["id", "1", "abc", "4", "4"]
        assert resolver_colisao_id(ids, meu_id=4, minha_linha=5) == 5

    def test_planilha_so_com_cabecalho_nao_tem_colisao(self):
        assert resolver_colisao_id(["id"], meu_id=1, minha_linha=2) is None

    def test_compara_ids_como_texto_para_tolerar_formatos_da_planilha(self):
        # O Sheets pode devolver os números como string; a comparação não
        # pode depender do tipo.
        ids = ["id", "10", "10"]
        assert resolver_colisao_id(ids, meu_id="10", minha_linha=3) == 11


class TestMontarLinhaPorNome:
    """
    Esta é a função que corrige o bug real encontrado em produção: a
    planilha `emprestimos` teve uma coluna inserida "no meio" da lista
    declarada em EXPECTED_HEADERS (`proxima_data_vencimento`) num momento
    posterior à criação da aba. Como a migração de headers só acrescenta
    colunas ao FINAL da planilha física, a ordem real divergiu da ordem
    do código — e uma escrita posicional gravava cada valor na coluna
    errada. `montar_linha_por_nome` elimina essa classe de bug: a linha é
    sempre montada seguindo a ordem física real (o cabeçalho passado),
    nunca a ordem em que os campos aparecem no dict.
    """

    def test_ordem_do_dict_nao_importa_so_a_do_cabecalho(self):
        cabecalho = ["id", "descricao", "valor"]
        valores = {"valor": 99.9, "descricao": "Teste"}  # ordem invertida no dict
        assert montar_linha_por_nome(cabecalho, valores, id_valor=7) == [7, "Teste", 99.9]

    def test_reproduz_o_cenario_real_do_bug_coluna_no_meio(self):
        # Cabeçalho físico real: proxima_data_vencimento foi parar no
        # FINAL (posição 9), não na posição 6 como o código "imaginava".
        cabecalho = [
            "id", "descricao", "banco", "valor_parcela", "parcelas_restantes",
            "valor_total_devido", "criado_em", "atualizado_em",
            "proxima_data_vencimento", "lancado_por",
        ]
        valores = {
            "descricao": "Empréstimo Teste", "banco": "Banco X",
            "valor_parcela": 100.0, "parcelas_restantes": 10,
            "proxima_data_vencimento": "2026-10-15",
            "valor_total_devido": 1000.0,
            "criado_em": "2026-09-15 18:00:00", "atualizado_em": "2026-09-15 18:00:00",
            "lancado_por": "Ricardo",
        }
        linha = montar_linha_por_nome(cabecalho, valores, id_valor=1)
        # Cada valor cai na coluna certa, mesmo com a ordem física "fora
        # de ordem" em relação a quando cada campo foi criado no código.
        assert linha[cabecalho.index("valor_total_devido")] == 1000.0
        assert linha[cabecalho.index("proxima_data_vencimento")] == "2026-10-15"
        assert linha[cabecalho.index("atualizado_em")] == "2026-09-15 18:00:00"

    def test_coluna_ausente_no_dict_vira_string_vazia(self):
        cabecalho = ["id", "descricao", "observacao"]
        linha = montar_linha_por_nome(cabecalho, {"descricao": "X"}, id_valor=1)
        assert linha == [1, "X", ""]

    def test_chave_extra_no_dict_sem_coluna_correspondente_e_ignorada(self):
        cabecalho = ["id", "descricao"]
        valores = {"descricao": "X", "campo_que_nao_existe_na_planilha": "y"}
        assert montar_linha_por_nome(cabecalho, valores, id_valor=1) == [1, "X"]

    def test_cabecalho_vazio_devolve_linha_vazia(self):
        assert montar_linha_por_nome([], {"qualquer": 1}, id_valor=1) == []
