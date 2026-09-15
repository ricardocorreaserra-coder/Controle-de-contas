"""
Testes para utils/sessao.py::autenticar_credenciais — a função pura que
decide se um par usuário+senha confere. Não toca em Streamlit.
"""

from utils.sessao import autenticar_credenciais, USUARIO_PADRAO

USUARIOS = {"Ricardo": "senha-r", "Maria": "senha-m"}


class TestModoMultiusuario:

    def test_credenciais_corretas_retornam_o_nome(self):
        assert autenticar_credenciais("Ricardo", "senha-r", USUARIOS) == "Ricardo"
        assert autenticar_credenciais("Maria", "senha-m", USUARIOS) == "Maria"

    def test_nome_e_case_insensitive_e_ignora_espacos(self):
        assert autenticar_credenciais("  ricardo ", "senha-r", USUARIOS) == "Ricardo"
        assert autenticar_credenciais("RICARDO", "senha-r", USUARIOS) == "Ricardo"

    def test_retorna_o_nome_como_cadastrado_nao_como_digitado(self):
        # Importante para a coluna `lancado_por` ficar padronizada.
        assert autenticar_credenciais("ricardo", "senha-r", USUARIOS) == "Ricardo"

    def test_senha_errada_falha(self):
        assert autenticar_credenciais("Ricardo", "senha-m", USUARIOS) is None

    def test_senha_e_case_sensitive(self):
        assert autenticar_credenciais("Ricardo", "SENHA-R", USUARIOS) is None

    def test_usuario_inexistente_falha(self):
        assert autenticar_credenciais("Joao", "senha-r", USUARIOS) is None

    def test_campos_vazios_falham(self):
        assert autenticar_credenciais("", "", USUARIOS) is None
        assert autenticar_credenciais(None, None, USUARIOS) is None

    def test_senha_de_outro_usuario_nao_autentica_como_o_primeiro(self):
        # Garante que a checagem é do PAR, não da senha isolada.
        assert autenticar_credenciais("Ricardo", "senha-m", USUARIOS) is None
        assert autenticar_credenciais("Maria", "senha-r", USUARIOS) is None

    def test_usuarios_configurados_ignoram_a_senha_unica_antiga(self):
        # Se [USUARIOS] existe, APP_PASSWORD não deve mais dar acesso.
        assert autenticar_credenciais("", "senha-antiga", USUARIOS,
                                       senha_unica="senha-antiga") is None


class TestModoSenhaUnicaCompatibilidade:

    def test_senha_unica_correta_autentica_como_usuario_padrao(self):
        assert autenticar_credenciais("", "segredo", {}, senha_unica="segredo") == USUARIO_PADRAO

    def test_senha_unica_ignora_o_campo_de_nome(self):
        assert autenticar_credenciais("qualquer", "segredo", {},
                                       senha_unica="segredo") == USUARIO_PADRAO

    def test_senha_unica_incorreta_falha(self):
        assert autenticar_credenciais("", "errada", {}, senha_unica="segredo") is None

    def test_sem_usuarios_e_sem_senha_unica_nunca_autentica(self):
        assert autenticar_credenciais("qualquer", "qualquer", {}, senha_unica="") is None
