"""
Testes das listas de categorias (config.py) e de `opcoes_categoria`
(utils/widgets.py), que protege a categoria já gravada numa edição.

A categoria é gravada como TEXTO em cada lançamento da planilha. Por isso os
nomes que já existiam NÃO podem mudar de grafia: lançamentos antigos
continuam com o nome velho.
"""

from config import CAT_DESP, CAT_REC
from utils.widgets import opcoes_categoria

# Nomes que já existiam antes da ampliação das listas — não podem sumir.
CAT_DESP_ANTIGAS = ["Alimentação", "Transporte", "Saúde", "Moradia", "Lazer",
                    "Educação", "Vestuário", "Despesa bancária", "Outros"]
CAT_REC_ANTIGAS = ["Salário", "Freelance", "Investimentos", "Aluguel recebido", "Outros"]


class TestListas:

    def test_despesas_tem_19_categorias(self):
        assert len(CAT_DESP) == 19

    def test_receitas_tem_7_categorias(self):
        assert len(CAT_REC) == 7

    def test_sem_duplicatas(self):
        assert len(set(CAT_DESP)) == len(CAT_DESP)
        assert len(set(CAT_REC)) == len(CAT_REC)

    def test_outros_e_sempre_o_ultimo(self):
        assert CAT_DESP[-1] == "Outros"
        assert CAT_REC[-1] == "Outros"

    def test_nomes_antigos_continuam_com_a_mesma_grafia(self):
        assert set(CAT_DESP_ANTIGAS) <= set(CAT_DESP)
        assert set(CAT_REC_ANTIGAS) <= set(CAT_REC)

    def test_novas_categorias_de_despesa_estao_presentes(self):
        novas = ["Restaurantes e delivery", "Contas da casa", "Assinaturas e serviços",
                 "Cuidados pessoais", "Filhos e família", "Pets", "Impostos e taxas",
                 "Seguros", "Viagens", "Presentes e doações"]
        assert set(novas) <= set(CAT_DESP)

    def test_novas_categorias_de_receita_estao_presentes(self):
        assert {"13º e férias", "Reembolsos"} <= set(CAT_REC)

    def test_venda_de_bens_nao_existe(self):
        assert "Venda de bens" not in CAT_REC
        assert "Venda de bens" not in CAT_DESP

    def test_nenhum_nome_vazio_nem_com_espacos_nas_pontas(self):
        for nome in CAT_DESP + CAT_REC:
            assert nome and nome == nome.strip()


class TestOpcoesCategoria:

    def test_categoria_da_lista_vem_selecionada(self):
        opcoes, idx = opcoes_categoria(CAT_DESP, "Moradia")
        assert opcoes[idx] == "Moradia"
        assert opcoes == [""] + CAT_DESP

    def test_categoria_vazia_seleciona_o_vazio(self):
        opcoes, idx = opcoes_categoria(CAT_DESP, "")
        assert opcoes[idx] == ""
        assert idx == 0

    def test_categoria_fora_da_lista_e_preservada_no_fim(self):
        opcoes, idx = opcoes_categoria(CAT_DESP, "Categoria Antiga")
        assert opcoes[idx] == "Categoria Antiga"
        assert opcoes[-1] == "Categoria Antiga"
        assert opcoes[:-1] == [""] + CAT_DESP

    def test_nao_altera_a_lista_original(self):
        antes = list(CAT_REC)
        opcoes_categoria(CAT_REC, "Outra Coisa")
        assert CAT_REC == antes

    def test_none_e_nan_viram_vazio(self):
        for valor in (None, float("nan")):
            opcoes, idx = opcoes_categoria(CAT_DESP, valor)
            assert opcoes[idx] == ""
            assert "nan" not in opcoes and "None" not in opcoes

    def test_espacos_nas_pontas_sao_ignorados(self):
        opcoes, idx = opcoes_categoria(CAT_DESP, "  Lazer  ")
        assert opcoes[idx] == "Lazer"
        assert len(opcoes) == len(CAT_DESP) + 1

    def test_funciona_com_receitas(self):
        opcoes, idx = opcoes_categoria(CAT_REC, "13º e férias")
        assert opcoes[idx] == "13º e férias"
