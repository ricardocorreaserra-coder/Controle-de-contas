"""
Testes para as funções puras de sheets/client.py que protegem contra IDs
duplicados quando duas pessoas gravam ao mesmo tempo (acesso compartilhado).

Nenhuma delas fala com o Google Sheets — recebem os dados já lidos.
"""

from sheets.client import numero_linha_do_range, resolver_colisao_id


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
