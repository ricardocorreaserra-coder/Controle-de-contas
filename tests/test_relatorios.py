"""
Testes de logica/relatorios.py (PDFs para impressão de cada tela).

Os testes LEEM O TEXTO de dentro dos PDFs gerados (com pypdf, que fica só no
requirements-dev.txt), então conferem de verdade acentos, remoção de emojis,
repetição do cabeçalho em cada página, numeração, e os valores dos relatórios.
"""

import io
from datetime import datetime

import pandas as pd
import pytest

pypdf = pytest.importorskip("pypdf")

from logica.relatorios import (  # noqa: E402
    Secao, _alinha_direita, _txt, gerar_pdf, pdf_dashboard, pdf_faturas_futuras,
    secao_participacao,
)

AGORA = datetime(2026, 10, 9, 10, 15)


def ler(pdf_bytes: bytes):
    """Devolve (lista de textos por página, leitor do pypdf)."""
    leitor = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    return [p.extract_text() for p in leitor.pages], leitor


def tabela_grande(n=120, colunas=("ID", "Descrição", "Valor", "Data")):
    return pd.DataFrame({
        "ID": range(1, n + 1),
        "Descrição": [f"Compra {i} São João" for i in range(1, n + 1)],
        "Valor": [f"R$ {i * 10:,.2f}" for i in range(1, n + 1)],
        "Data": ["09/10/2026"] * n,
    })[list(colunas)]


# ─────────────────────────────────────────────────────────────────────────────
# _txt
# ─────────────────────────────────────────────────────────────────────────────

class TestTxt:

    def test_none_e_nan_viram_vazio(self):
        assert _txt(None) == ""
        assert _txt(float("nan")) == ""

    def test_emojis_sao_removidos(self):
        assert _txt("✅ Pago") == "Pago"
        assert _txt("📌 Pendente") == "Pendente"
        assert _txt("❌ Vencido") == "Vencido"
        assert _txt("⏳ Pendente") == "Pendente"
        assert _txt("🔧 Estimado") == "Estimado"

    def test_acentos_do_portugues_sao_mantidos(self):
        assert _txt("Alimentação, São João, ação, é, ü, ñ, 13º") == "Alimentação, São João, ação, é, ü, ñ, 13º"

    def test_travessao_e_aspas_tipograficas_viram_ascii(self):
        assert _txt("a – b — c “x” ‘y’ …") == 'a - b - c "x" \'y\' ...'

    def test_quebras_de_linha_viram_espaco(self):
        assert _txt("linha1\nlinha2\t  fim") == "linha1 linha2 fim"

    def test_numeros_viram_texto(self):
        assert _txt(12) == "12"
        assert _txt(3.5) == "3.5"


class TestAlinhaDireita:

    def test_valores_em_reais_ficam_a_direita(self):
        assert _alinha_direita("Valor", ["R$ 1,00", "R$ 1.234,56", "-R$ 5,00"], ())

    def test_percentuais_e_numeros_ficam_a_direita(self):
        assert _alinha_direita("x", ["88,1%", "6,0%"], ())
        assert _alinha_direita("x", ["1", "20", ""], ())

    def test_texto_fica_a_esquerda(self):
        assert not _alinha_direita("Descrição", ["Mercado", "R$ 5,00"], ())

    def test_coluna_vazia_fica_a_esquerda(self):
        assert not _alinha_direita("Obs", ["", ""], ())

    def test_coluna_forcada(self):
        assert _alinha_direita("Descrição", ["abc"], ("Descrição",))


# ─────────────────────────────────────────────────────────────────────────────
# gerar_pdf
# ─────────────────────────────────────────────────────────────────────────────

class TestGerarPdf:

    def test_devolve_um_pdf_valido(self):
        b = gerar_pdf("Teste", secoes=[Secao("", tabela_grande(3))], agora=AGORA)
        assert isinstance(b, bytes)
        assert b.startswith(b"%PDF-")
        textos, leitor = ler(b)
        assert len(leitor.pages) == 1

    def test_titulo_subtitulo_e_carimbo(self):
        b = gerar_pdf("Despesas", "Período: Out/26", secoes=[Secao("", tabela_grande(2))],
                      emitido_por="Ricardo", agora=AGORA)
        texto = ler(b)[0][0]
        assert "Despesas" in texto
        assert "Período: Out/26" in texto
        assert "Emitido em 09/10/2026 10:15 por Ricardo" in texto

    def test_carimbo_sem_nome_nao_tem_por(self):
        texto = ler(gerar_pdf("X", secoes=[Secao("", tabela_grande(1))], agora=AGORA))[0][0]
        assert "Emitido em 09/10/2026 10:15" in texto
        assert " por " not in texto.split("Emitido em")[1].split("\n")[0]

    def test_carimbo_padrao_usa_horario_de_brasilia(self, monkeypatch):
        """O servidor roda em UTC: 01:30 UTC do dia 10 são 22:30 do dia 09 em Brasília."""
        from datetime import timezone
        import logica.relatorios as rel

        class RelogioFalso(datetime):
            @classmethod
            def now(cls, tz=None):
                base = datetime(2026, 10, 10, 1, 30, tzinfo=timezone.utc)
                return base.astimezone(tz) if tz else base

        monkeypatch.setattr(rel, "datetime", RelogioFalso)
        texto = ler(gerar_pdf("X", secoes=[Secao("", tabela_grande(1))]))[0][0]
        assert "Emitido em 09/10/2026 22:30" in texto

    def test_acentos_chegam_ao_pdf(self):
        df = pd.DataFrame({"Categoria": ["Alimentação", "Educação"], "Descrição": ["São João", "Açaí"]})
        texto = ler(gerar_pdf("Teste", secoes=[Secao("", df)], agora=AGORA))[0][0]
        for palavra in ("Alimentação", "Educação", "São João", "Açaí"):
            assert palavra in texto

    def test_emojis_nao_aparecem_mas_o_texto_sim(self):
        df = pd.DataFrame({"Status": ["✅ Pago", "📌 Pendente"]})
        texto = ler(gerar_pdf("Teste", secoes=[Secao("", df)], agora=AGORA))[0][0]
        assert "Pago" in texto and "Pendente" in texto
        assert "✅" not in texto and "📌" not in texto

    def test_tabela_grande_gera_varias_paginas_com_cabecalho_repetido(self):
        textos, leitor = ler(gerar_pdf("Muitas", secoes=[Secao("", tabela_grande(150))], agora=AGORA))
        assert len(leitor.pages) > 1
        for t in textos:
            assert "Descrição" in t and "Valor" in t       # cabeçalho em TODAS as páginas

    def test_todas_as_linhas_foram_impressas(self):
        textos, _ = ler(gerar_pdf("Muitas", secoes=[Secao("", tabela_grande(150))], agora=AGORA))
        tudo = "\n".join(textos)
        for i in (1, 75, 150):
            assert f"Compra {i} São João" in tudo

    def test_numeracao_de_paginas(self):
        textos, leitor = ler(gerar_pdf("Muitas", secoes=[Secao("", tabela_grande(150))], agora=AGORA))
        n = len(leitor.pages)
        assert f"Página 1/{n}" in textos[0]
        assert f"Página {n}/{n}" in textos[-1]

    def test_orientacao_automatica(self):
        retrato = gerar_pdf("X", secoes=[Secao("", tabela_grande(2))], agora=AGORA)           # 4 colunas
        paisagem = gerar_pdf("X", secoes=[Secao("", pd.DataFrame(
            {f"Col{i}": ["a", "b"] for i in range(8)}))], agora=AGORA)                          # 8 colunas
        caixa_r = ler(retrato)[1].pages[0].mediabox
        caixa_p = ler(paisagem)[1].pages[0].mediabox
        assert caixa_r.height > caixa_r.width
        assert caixa_p.width > caixa_p.height

    def test_orientacao_forcada(self):
        b = gerar_pdf("X", secoes=[Secao("", tabela_grande(2))], orientacao="L", agora=AGORA)
        caixa = ler(b)[1].pages[0].mediabox
        assert caixa.width > caixa.height

    def test_secao_vazia_mostra_aviso(self):
        texto = ler(gerar_pdf("X", secoes=[Secao("Tabela", pd.DataFrame())], agora=AGORA))[0][0]
        assert "Tabela" in texto and "Nenhum registro." in texto

    def test_sem_secoes_nem_kpis_nao_quebra(self):
        textos, leitor = ler(gerar_pdf("Só título", agora=AGORA))
        assert len(leitor.pages) == 1 and "Só título" in textos[0]

    def test_kpis_aparecem_com_rotulo_e_valor(self):
        kpis = [("Total", "R$ 9.700,00", "azul"), ("Crédito", "R$ 4.100,00", "verde")]
        texto = ler(gerar_pdf("X", kpis=kpis, secoes=[Secao("", tabela_grande(1))], agora=AGORA))[0][0]
        for t in ("Total", "R$ 9.700,00", "Crédito", "R$ 4.100,00"):
            assert t in texto

    def test_mais_de_quatro_kpis_quebram_em_duas_linhas(self):
        kpis = [(f"K{i}", f"R$ {i},00", "neutro") for i in range(1, 7)]
        texto = ler(gerar_pdf("X", kpis=kpis, secoes=[Secao("", tabela_grande(1))], agora=AGORA))[0][0]
        for i in range(1, 7):
            assert f"K{i}" in texto and f"R$ {i},00" in texto

    def test_cor_de_kpi_desconhecida_nao_quebra(self):
        gerar_pdf("X", kpis=[("A", "1", "rosa-choque")], agora=AGORA)

    def test_palavra_gigante_sem_espacos_nao_quebra(self):
        df = pd.DataFrame({"Obs": ["x" * 400], "Valor": ["R$ 1,00"]})
        b = gerar_pdf("X", secoes=[Secao("", df)], agora=AGORA)
        assert b.startswith(b"%PDF-")

    def test_palavra_gigante_nao_espreme_as_outras_colunas(self):
        df = pd.DataFrame({"Obs": ["https://exemplo.com/" + "x" * 400], "Valor": ["R$ 1,00"],
                           "Data": ["09/10/2026"]})
        texto = ler(gerar_pdf("X", secoes=[Secao("", df)], agora=AGORA))[0][0]
        assert "R$ 1,00" in texto and "09/10/2026" in texto

    def test_mensagem_de_vazio_personalizada(self):
        s = Secao("T", pd.DataFrame(), vazio="Nada por aqui.")
        assert "Nada por aqui." in ler(gerar_pdf("X", secoes=[s], agora=AGORA))[0][0]

    def test_tabela_com_muitas_colunas_nao_quebra(self):
        df = pd.DataFrame({f"Coluna {i}": [f"valor {i}"] * 3 for i in range(14)})
        textos, _ = ler(gerar_pdf("Larga", secoes=[Secao("", df)], agora=AGORA))
        assert "Coluna 13" in textos[0]

    def test_valores_nulos_viram_celula_vazia(self):
        df = pd.DataFrame({"A": ["x", None], "B": [float("nan"), "y"]})
        texto = ler(gerar_pdf("X", secoes=[Secao("", df)], agora=AGORA))[0][0]
        assert "None" not in texto and "nan" not in texto

    def test_coluna_da_barra_nao_vira_texto(self):
        df = pd.DataFrame({"Item": ["a", "b"], "Valor": ["R$ 1,00", "R$ 3,00"], "_barra": [0.25, 0.75]})
        texto = ler(gerar_pdf("X", secoes=[Secao("", df, barra="_barra")], agora=AGORA))[0][0]
        assert "_barra" not in texto and "0.25" not in texto

    def test_secoes_na_ordem_e_com_nota(self):
        s1 = Secao("Primeira", tabela_grande(2), nota="Nota importante.")
        s2 = Secao("Segunda", tabela_grande(2))
        texto = ler(gerar_pdf("X", secoes=[s1, s2], agora=AGORA))[0][0]
        assert texto.index("Primeira") < texto.index("Nota importante.") < texto.index("Segunda")

    def test_desempenho_com_500_linhas(self):
        import time
        t0 = time.time()
        gerar_pdf("Grande", secoes=[Secao("", tabela_grande(500))], agora=AGORA)
        assert time.time() - t0 < 15


# ─────────────────────────────────────────────────────────────────────────────
# secao_participacao
# ─────────────────────────────────────────────────────────────────────────────

class TestSecaoParticipacao:

    def df(self):
        return pd.DataFrame({"Categoria": ["Transporte", "Outros", "Alimentação"],
                             "Valor": [10.0, 880.0, 110.0]})

    def test_ordena_do_maior_para_o_menor(self):
        s = secao_participacao("Por categoria", "Categoria", self.df())
        assert list(s.df["Categoria"]) == ["Outros", "Alimentação", "Transporte"]

    def test_percentuais_corretos_e_formatados(self):
        s = secao_participacao("Por categoria", "Categoria", self.df())
        assert list(s.df["Participação"]) == ["88,0%", "11,0%", "1,0%"]
        assert list(s.df["Valor"]) == ["R$ 880,00", "R$ 110,00", "R$ 10,00"]

    def test_barras_somam_um(self):
        s = secao_participacao("x", "Categoria", self.df())
        assert s.barra == "_barra"
        assert sum(s.df["_barra"]) == pytest.approx(1.0)

    def test_vazio_devolve_secao_com_mensagem_de_sem_dados(self):
        s = secao_participacao("x", "Categoria", pd.DataFrame())
        assert s.df.empty and s.vazio == "Sem dados para o período."

    def test_total_zero_nao_divide_por_zero(self):
        df = pd.DataFrame({"Categoria": ["A", "B"], "Valor": [0.0, 0.0]})
        s = secao_participacao("x", "Categoria", df)
        assert list(s.df["Participação"]) == ["0,0%", "0,0%"]

    def test_nao_altera_o_dataframe_original(self):
        df = self.df()
        secao_participacao("x", "Categoria", df)
        assert list(df["Categoria"]) == ["Transporte", "Outros", "Alimentação"]


# ─────────────────────────────────────────────────────────────────────────────
# pdf_dashboard
# ─────────────────────────────────────────────────────────────────────────────

def dados_dashboard():
    hist = pd.DataFrame({"Mês": ["Mai/26", "Jun/26", "Jul/26", "Ago/26", "Set/26", "Out/26"],
                         "Receita": [0, 0, 300.5, 0, 0, 0],
                         "Despesa": [0, 0, 0, 37800.1, 14900.9, 992.58]})
    cat = pd.DataFrame({"Categoria": ["Outros", "Alimentação", "Educação", "Transporte"],
                        "Valor": [873.9, 59.9, 47.8, 10.9]})
    pag = pd.DataFrame({"Pagamento": ["Pix", "Dinheiro"], "Valor": [757.5, 235.08]})
    return hist, cat, pag


class TestPdfDashboard:

    def test_conteudo_principal(self):
        hist, cat, pag = dados_dashboard()
        b = pdf_dashboard("Out/26", 0.0, 992.58, -992.58, hist, cat, pag,
                          emitido_por="Jociara", agora=AGORA)
        texto = ler(b)[0][0]
        for t in ("Dashboard", "Período: Out/26", "Receitas do mês", "Despesas do mês",
                  "Saldo do mês", "R$ 992,58", "-R$ 992,58".replace("-R$ ", "R$ -"),
                  "Histórico dos últimos 6 meses", "Despesas por categoria",
                  "Despesas por forma de pagamento", "Outros", "Alimentação", "Pix", "Dinheiro"):
            assert t in texto, t

    def test_percentuais_e_saldo_do_historico(self):
        hist, cat, pag = dados_dashboard()
        texto = ler(pdf_dashboard("Out/26", 0.0, 992.58, -992.58, hist, cat, pag, agora=AGORA))[0][0]
        assert "88,1%" in texto and "76,3%" in texto
        assert "R$ -37.800,10" in texto           # saldo de agosto no histórico

    def test_nota_sobre_pendentes(self):
        hist, cat, pag = dados_dashboard()
        texto = ler(pdf_dashboard("Out/26", 0.0, 1.0, -1.0, hist, cat, pag, agora=AGORA))[0][0]
        assert "pendentes" in texto

    def test_mes_sem_despesas_nao_quebra(self):
        hist, _, _ = dados_dashboard()
        b = pdf_dashboard("Out/26", 0.0, 0.0, 0.0, hist, pd.DataFrame(), pd.DataFrame(), agora=AGORA)
        texto = ler(b)[0][0]
        assert "Sem dados para o período." in texto

    def test_nao_altera_o_historico_original(self):
        hist, cat, pag = dados_dashboard()
        pdf_dashboard("Out/26", 0.0, 1.0, -1.0, hist, cat, pag, agora=AGORA)
        assert list(hist.columns) == ["Mês", "Receita", "Despesa"]


# ─────────────────────────────────────────────────────────────────────────────
# pdf_faturas_futuras
# ─────────────────────────────────────────────────────────────────────────────

def dados_faturas():
    return pd.DataFrame({
        "Mês Vencimento": ["2026-11", "2026-11", "2026-12", "2027-01", "2027-01"],
        "cartao": ["Nubank", "Itaú", "Nubank", "Nubank", "Itaú"],
        "valor": [250.5, 100.0, 250.5, 1234.56, 99.9],
    })


class TestPdfFaturasFuturas:

    def test_pivo_por_mes_e_cartao(self):
        texto = ler(pdf_faturas_futuras(dados_faturas(), agora=AGORA))[0][0]
        for t in ("Projeção de Faturas Futuras", "Nov/26", "Dez/26", "Jan/27",
                  "Nubank", "Itaú", "R$ 350,50", "R$ 1.334,46"):
            assert t in texto, t

    def test_linha_de_total_geral_e_kpis(self):
        texto = ler(pdf_faturas_futuras(dados_faturas(), agora=AGORA))[0][0]
        assert "TOTAL" in texto
        assert "R$ 1.935,46" in texto             # soma de tudo
        assert "Faturas futuras" in texto

    def test_meses_em_ordem_cronologica(self):
        texto = ler(pdf_faturas_futuras(dados_faturas(), agora=AGORA))[0][0]
        assert texto.index("Nov/26") < texto.index("Dez/26") < texto.index("Jan/27")

    def test_detalhe_opcional(self):
        det = pd.DataFrame({"Descrição/Item": ["Geladeira"], "Valor": ["R$ 250,50"]})
        texto = ler(pdf_faturas_futuras(dados_faturas(), det, "Detalhamento - Nov/26 (Nubank)",
                                        agora=AGORA))[0][0]
        assert "Detalhamento - Nov/26 (Nubank)" in texto and "Geladeira" in texto

    def test_sem_detalhe_nao_imprime_secao_de_detalhe(self):
        texto = ler(pdf_faturas_futuras(dados_faturas(), None, agora=AGORA))[0][0]
        assert "Detalhamento" not in texto

    def test_detalhe_vazio_e_ignorado(self):
        texto = ler(pdf_faturas_futuras(dados_faturas(), pd.DataFrame(), "Detalhamento X",
                                        agora=AGORA))[0][0]
        assert "Detalhamento X" not in texto

    def test_um_unico_cartao(self):
        d = dados_faturas()[dados_faturas()["cartao"] == "Nubank"]
        texto = ler(pdf_faturas_futuras(d, agora=AGORA))[0][0]
        assert "Nubank" in texto and "Itaú" not in texto

    def test_nao_altera_o_dataframe_original(self):
        d = dados_faturas()
        pdf_faturas_futuras(d, agora=AGORA)
        assert list(d.columns) == ["Mês Vencimento", "cartao", "valor"]
