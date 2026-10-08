"""
Guarda de regressão da compatibilidade com tema claro/escuro (B-05).

O app precisa funcionar nos dois temas do Streamlit. Isto NÃO testa o
visual (não há navegador nos testes) — só impede a volta de duas coisas que
já quebraram o modo escuro: cores claras fixas no CSS e o template de
gráfico `plotly_white` (fundo branco forçado). Ver comentário acima do CSS
em config.py.
"""

from pathlib import Path

import pytest

from config import CSS

RAIZ = Path(__file__).resolve().parent.parent

# Cores claras que funcionavam só no tema claro. Em fundo escuro, texto/box
# com elas fica ilegível ou vira um retângulo branco no meio da tela.
CORES_CLARAS_PROIBIDAS = ["background: white", "#e2e8f0", "#64748b", "#eff6ff", "#bfdbfe", "#1e3a8a"]


class TestCssCompativelComTemaEscuro:

    @pytest.mark.parametrize("cor", CORES_CLARAS_PROIBIDAS)
    def test_css_sem_cor_clara_fixa(self, cor):
        assert cor not in CSS, (
            f"{cor!r} voltou ao CSS — fica ilegível no tema escuro. "
            "Use rgba(128,128,128,x) ou herde a cor do texto."
        )

    def test_cartao_usa_fundo_translucido(self):
        assert "rgba(128,128,128" in CSS

    def test_login_nao_tem_cinza_fixo_no_html(self):
        assert "#64748b" not in (RAIZ / "auth.py").read_text(encoding="utf-8")


class TestGraficosSeguemTemaDoStreamlit:

    def test_nenhuma_pagina_forca_plotly_white(self):
        # `template="plotly_white"` sobrescreve o template padrão do
        # Streamlit (que segue o tema) e força fundo branco/texto escuro.
        for arq in sorted((RAIZ / "paginas").glob("*.py")):
            assert "plotly_white" not in arq.read_text(encoding="utf-8"), (
                f"{arq.name} usa plotly_white — o gráfico não acompanha o tema escuro."
            )
