"""Trava a limpeza do `use_container_width` (deprecado; o Streamlit avisa que será removido).

Código novo usa `width="stretch"` (ou `width="content"`) — regra 26.
"""
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTAS = ["paginas", "utils", "logica", "sheets"]
SOLTOS = ["app.py", "auth.py", "config.py"]


def _arquivos_do_app():
    for nome in SOLTOS:
        yield RAIZ / nome
    for pasta in PASTAS:
        yield from sorted((RAIZ / pasta).rglob("*.py"))


def test_nenhum_arquivo_usa_use_container_width():
    achados = []
    for arq in _arquivos_do_app():
        for n, linha in enumerate(arq.read_text(encoding="utf-8").splitlines(), 1):
            if "use_container_width" in linha:
                achados.append(f"{arq.relative_to(RAIZ)}:{n}")
    assert not achados, "Troque por width=\"stretch\": " + ", ".join(achados)


def test_os_widgets_usados_aceitam_o_parametro_width():
    """Se uma atualização do Streamlit tirar o `width`, este teste avisa antes do site quebrar."""
    import inspect
    import streamlit as st
    for nome in ("button", "form_submit_button", "download_button", "dataframe", "plotly_chart"):
        assert "width" in inspect.signature(getattr(st, nome)).parameters, nome


def test_so_valores_validos_de_width_nos_widgets():
    """width="stretch"/"content" ou um número; nada de True/False (o formato antigo)."""
    ruim = []
    padrao = re.compile(r"\bwidth\s*=\s*(True|False)\b")
    for arq in _arquivos_do_app():
        for n, linha in enumerate(arq.read_text(encoding="utf-8").splitlines(), 1):
            if padrao.search(linha):
                ruim.append(f"{arq.relative_to(RAIZ)}:{n}")
    assert not ruim, ", ".join(ruim)
