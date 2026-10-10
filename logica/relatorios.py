"""
Relatórios em PDF para IMPRESSÃO de cada tela.

Tudo aqui é função pura (sem Streamlit e sem planilha): recebe DataFrames já
prontos e devolve os bytes do PDF. Cada tela passa exatamente a tabela que
mostra na tela (mesmos filtros, mesmas colunas), então "o que se vê é o que se
imprime" — e, diferente do Ctrl+P do navegador, o PDF sai COMPLETO (todas as
linhas, com quebra de página e cabeçalho repetido).

Peças:
  • gerar_pdf(...)        → monta o documento: título, quadros de totais e
                            uma ou mais tabelas (`Secao`).
  • Secao                 → uma tabela do relatório (com barra opcional).
  • pdf_dashboard(...)    → relatório do Dashboard (histórico + participação).
  • pdf_faturas_futuras() → pivô de faturas futuras por cartão.

Limitação deliberada: o PDF usa as fontes padrão (Helvetica), que só têm
caracteres latinos (acentos do português incluídos). Emojis e símbolos fora
disso são descartados por `_txt` — por exemplo "✅ Pago" sai como "Pago".
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pandas as pd
from fpdf import FPDF
from fpdf.enums import MethodReturnValue, XPos, YPos

from utils.datas import fmt_mes_str_pt
from utils.formatacao import fmt_moeda

# Horário de Brasília (o Brasil não tem mais horário de verão desde 2019).
# Offset fixo de propósito: não depende de tzdata instalado no servidor.
_FUSO_BR = timezone(timedelta(hours=-3))

# ── Aparência ────────────────────────────────────────────────────────────────
_MARGEM = 10            # mm
_FONTE = "Helvetica"
_COR_BORDA = (200, 200, 200)
_COR_CABECALHO = (228, 231, 236)
_COR_ZEBRA = (246, 247, 249)
_COR_BARRA = (59, 130, 246)
_COR_BARRA_FUNDO = (226, 229, 234)
_CORES_KPI = {
    "verde": (22, 130, 70), "vermelho": (200, 40, 40), "azul": (37, 99, 235),
    "laranja": (200, 110, 10), "neutro": (30, 30, 30),
}

_SUBSTITUICOES = {
    "\u2013": "-", "\u2014": "-", "\u2022": "-", "\u2018": "'", "\u2019": "'",
    "\u201c": '"', "\u201d": '"', "\u2026": "...", "\u20ac": "EUR",
    "\u00a0": " ", "\u2192": "->", "\u2190": "<-",
}


def _txt(valor) -> str:
    """Texto seguro para o PDF: sem None/NaN, sem emoji, só latin-1, em uma linha."""
    if valor is None or (isinstance(valor, float) and valor != valor):
        return ""
    s = str(valor)
    for k, r in _SUBSTITUICOES.items():
        s = s.replace(k, r)
    s = s.encode("latin-1", "ignore").decode("latin-1")
    return " ".join(s.split())


@dataclass
class Secao:
    """Uma tabela do relatório. `df` deve conter textos já formatados."""
    titulo: str
    df: pd.DataFrame
    direita: tuple = ()          # colunas alinhadas à direita (além das detectadas)
    barra: str | None = None     # coluna numérica 0..1 desenhada como barra (não vira texto)
    nota: str = ""
    vazio: str = "Nenhum registro."   # texto quando a tabela não tem linhas


_RE_NUMERICO = re.compile(r"^-?(R\$ ?)?-?[\d.,]+%?$")


def _alinha_direita(coluna: str, textos: list[str], extras: tuple) -> bool:
    if coluna in extras:
        return True
    preenchidos = [t for t in textos if t]
    return bool(preenchidos) and all(_RE_NUMERICO.match(t) for t in preenchidos)


class _PDF(FPDF):
    def __init__(self, titulo_curto: str, carimbo: str, orientacao: str):
        super().__init__(orientation=orientacao, unit="mm", format="A4")
        self.titulo_curto = _txt(titulo_curto)
        self.carimbo = _txt(carimbo)
        self.set_margins(_MARGEM, 16, _MARGEM)
        self.c_margin = 0                 # o espaçamento interno das células é feito à mão
        self.set_auto_page_break(False)   # a quebra de página é feita à mão
        self.alias_nb_pages()

    def header(self):
        self.set_font(_FONTE, size=8)
        self.set_text_color(110, 110, 110)
        self.set_xy(self.l_margin, 7)
        self.cell(self.epw / 2, 4, f"Controle de Contas  |  {self.titulo_curto}",
                  new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.cell(self.epw / 2, 4, self.carimbo, align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*_COR_BORDA)
        self.line(self.l_margin, 12.5, self.w - self.r_margin, 12.5)
        self.set_y(16)
        self.set_text_color(0, 0, 0)

    def footer(self):
        self.set_y(-10)
        self.set_font(_FONTE, size=8)
        self.set_text_color(110, 110, 110)
        self.cell(0, 4, f"Página {self.page_no()}/{{nb}}", align="C")
        self.set_text_color(0, 0, 0)

    @property
    def limite_y(self) -> float:
        return self.h - 14


def _kpis(pdf: _PDF, kpis) -> None:
    if not kpis:
        return
    por_linha = min(len(kpis), 4)
    folga = 4
    larg = (pdf.epw - folga * (por_linha - 1)) / por_linha
    alt = 15
    y_linha = pdf.get_y()
    for i, (rotulo, valor, cor) in enumerate(kpis):
        col = i % por_linha
        if col == 0 and i > 0:
            y_linha += alt + folga
        if col == 0 and y_linha + alt > pdf.limite_y:
            pdf.add_page()
            y_linha = pdf.get_y()
        x = pdf.l_margin + col * (larg + folga)
        pdf.set_draw_color(*_COR_BORDA)
        pdf.set_fill_color(250, 250, 251)
        pdf.rect(x, y_linha, larg, alt, style="DF", round_corners=True, corner_radius=2)
        pdf.set_xy(x + 2.5, y_linha + 2)
        pdf.set_font(_FONTE, size=8)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(larg - 5, 4, _txt(rotulo), new_x=XPos.LEFT, new_y=YPos.NEXT)
        pdf.set_x(x + 2.5)
        pdf.set_font(_FONTE, style="B", size=12)
        pdf.set_text_color(*_CORES_KPI.get(cor, _CORES_KPI["neutro"]))
        pdf.cell(larg - 5, 6, _txt(valor), new_x=XPos.LEFT, new_y=YPos.NEXT)
    pdf.set_text_color(0, 0, 0)
    pdf.set_xy(pdf.l_margin, y_linha + alt + 6)


def _titulo_secao(pdf: _PDF, titulo: str) -> None:
    if pdf.get_y() + 20 > pdf.limite_y:
        pdf.add_page()
    pdf.set_font(_FONTE, style="B", size=11)
    pdf.set_x(pdf.l_margin)
    pdf.cell(0, 6, _txt(titulo), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_y(pdf.get_y() + 1)


def _tabela(pdf: _PDF, secao: Secao) -> None:
    df = secao.df
    colunas = [c for c in df.columns if c != secao.barra]
    cabecalhos = [_txt(c) for c in colunas]
    linhas = [[_txt(v) for v in reg] for reg in df[colunas].itertuples(index=False, name=None)]
    barras = ([float(v) if v == v else 0.0 for v in df[secao.barra]]
              if secao.barra else [])

    tam_fonte = 8 if len(colunas) <= 9 else 7
    lh = tam_fonte * 0.5          # altura de cada linha de texto (mm)
    pad_x, pad_y = 1.2, 1.0

    # Larguras: cada coluna recebe, no mínimo, o espaço da sua MAIOR PALAVRA (para
    # nunca quebrar uma palavra no meio) e, idealmente, o espaço do texto inteiro
    # (limitado, para um texto longo quebrar em linhas em vez de engolir as outras
    # colunas). O que sobra da página é repartido entre as colunas.
    folga_txt = 2 * pad_x + 0.6
    larg_barra = min(pdf.epw * 0.25, 55) if secao.barra else 0.0
    util = pdf.epw - larg_barra

    def medir(texto: str, negrito: bool) -> float:
        pdf.set_font(_FONTE, style="B" if negrito else "", size=tam_fonte)
        return pdf.get_string_width(texto)

    minimos, ideais = [], []
    for j, cab in enumerate(cabecalhos):
        celulas = [l[j] for l in linhas[:300]]
        palavras = [(w, True) for w in cab.split()] + [(w, False) for c in celulas for w in c.split()]
        # Teto de 30 mm: uma "palavra" gigante (link, código) passa a quebrar por
        # caractere em vez de espremer as demais colunas até não caber nem uma letra.
        minimo = min(max([medir(w, neg) for w, neg in palavras] + [3.0]), 30.0) + folga_txt
        ideal = max([medir(cab, True)] + [medir(c, False) for c in celulas]) + folga_txt
        minimos.append(minimo)
        ideais.append(max(min(ideal, 70.0), minimo))

    if sum(ideais) <= util:
        sobra = util - sum(ideais)
        larguras = [i + sobra * i / sum(ideais) for i in ideais]
    elif sum(minimos) < util:
        resto = util - sum(minimos)
        folgas = [i - m for i, m in zip(ideais, minimos)]
        total_folga = sum(folgas) or 1.0
        larguras = [m + resto * f / total_folga for m, f in zip(minimos, folgas)]
    else:                                   # tabela larga demais: encolhe todas
        larguras = [m * util / sum(minimos) for m in minimos]
    if secao.barra:
        larguras.append(larg_barra)
        cabecalhos.append("")

    direita = [_alinha_direita(c, [l[j] for l in linhas], secao.direita)
               for j, c in enumerate(colunas)]
    if secao.barra:
        direita.append(False)

    def contar_linhas(texto: str, largura: float) -> int:
        partes = pdf.multi_cell(largura - 2 * pad_x, lh, texto, dry_run=True,
                                output=MethodReturnValue.LINES)
        return max(1, len(partes))

    def desenhar_cabecalho():
        pdf.set_font(_FONTE, style="B", size=tam_fonte)
        n = max(contar_linhas(c, w) for c, w in zip(cabecalhos, larguras))
        h = n * lh + 2 * pad_y
        y = pdf.get_y()
        x = pdf.l_margin
        pdf.set_draw_color(*_COR_BORDA)
        pdf.set_fill_color(*_COR_CABECALHO)
        for c, w, d in zip(cabecalhos, larguras, direita):
            pdf.rect(x, y, w, h, style="DF")
            pdf.set_xy(x + pad_x, y + pad_y)
            pdf.multi_cell(w - 2 * pad_x, lh, c, align="R" if d else "L",
                           new_x=XPos.LEFT, new_y=YPos.NEXT)
            x += w
        pdf.set_y(y + h)
        pdf.set_font(_FONTE, size=tam_fonte)

    pdf.set_font(_FONTE, size=tam_fonte)
    if pdf.get_y() + 20 > pdf.limite_y:
        pdf.add_page()
    desenhar_cabecalho()

    for i, linha in enumerate(linhas):
        textos = list(linha)
        if secao.barra:
            textos.append("")
        n = max(contar_linhas(t, w) for t, w in zip(textos, larguras))
        h = n * lh + 2 * pad_y
        if pdf.get_y() + h > pdf.limite_y:
            pdf.add_page()
            desenhar_cabecalho()
        y = pdf.get_y()
        x = pdf.l_margin
        pdf.set_draw_color(*_COR_BORDA)
        if i % 2:
            pdf.set_fill_color(*_COR_ZEBRA)
        else:
            pdf.set_fill_color(255, 255, 255)
        for j, (t, w, d) in enumerate(zip(textos, larguras, direita)):
            pdf.rect(x, y, w, h, style="DF")
            if secao.barra and j == len(larguras) - 1:
                frac = min(max(barras[i], 0.0), 1.0)
                bx, bw, by = x + pad_x, w - 2 * pad_x, y + h / 2 - 1.3
                pdf.set_fill_color(*_COR_BARRA_FUNDO)
                pdf.rect(bx, by, bw, 2.6, style="F")
                if frac > 0:
                    pdf.set_fill_color(*_COR_BARRA)
                    pdf.rect(bx, by, max(bw * frac, 0.4), 2.6, style="F")
            else:
                pdf.set_xy(x + pad_x, y + pad_y)
                pdf.multi_cell(w - 2 * pad_x, lh, t, align="R" if d else "L",
                               new_x=XPos.LEFT, new_y=YPos.NEXT)
            x += w
        pdf.set_y(y + h)


def gerar_pdf(titulo: str, subtitulo: str = "", kpis=(), secoes=(),
              orientacao: str = "auto", emitido_por: str = "", agora=None) -> bytes:
    """
    Monta o PDF de uma tela.

    titulo/subtitulo : cabeçalho (o subtítulo costuma trazer o período e os filtros).
    kpis             : lista de (rótulo, valor já formatado, cor) com cor em
                       "verde" | "vermelho" | "azul" | "laranja" | "neutro".
    secoes           : lista de `Secao` (tabelas) na ordem de impressão.
    orientacao       : "P", "L" ou "auto" (paisagem se alguma tabela tiver mais de 6 colunas).
    emitido_por      : nome de quem gerou (aparece no cabeçalho de todas as páginas).
    agora            : data/hora do carimbo (só para testes); padrão = agora, horário de Brasília.
    """
    secoes = list(secoes)
    if orientacao == "auto":
        largura_max = max((len([c for c in s.df.columns if c != s.barra]) for s in secoes), default=0)
        orientacao = "L" if largura_max > 6 else "P"

    agora = agora or datetime.now(_FUSO_BR)
    carimbo = f"Emitido em {agora.strftime('%d/%m/%Y %H:%M')}"
    if emitido_por:
        carimbo += f" por {emitido_por}"

    pdf = _PDF(titulo, carimbo, orientacao)
    pdf.set_title(_txt(titulo))
    pdf.set_author("Controle de Contas")
    pdf.add_page()

    pdf.set_font(_FONTE, style="B", size=16)
    pdf.cell(0, 8, _txt(titulo), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if subtitulo:
        pdf.set_font(_FONTE, size=9)
        pdf.set_text_color(90, 90, 90)
        pdf.multi_cell(0, 4.5, _txt(subtitulo), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0, 0, 0)
    pdf.set_y(pdf.get_y() + 3)

    _kpis(pdf, kpis)

    for s in secoes:
        if s.titulo:
            _titulo_secao(pdf, s.titulo)
        if s.df is None or s.df.empty:
            pdf.set_font(_FONTE, style="I", size=9)
            pdf.set_text_color(110, 110, 110)
            pdf.cell(0, 6, _txt(s.vazio), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_text_color(0, 0, 0)
        else:
            _tabela(pdf, s)
        if s.nota:
            pdf.set_font(_FONTE, style="I", size=8)
            pdf.set_text_color(110, 110, 110)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, 4, _txt(s.nota), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_text_color(0, 0, 0)
        pdf.set_y(pdf.get_y() + 5)

    return bytes(pdf.output())


# ─────────────────────────────────────────────────────────────────────────────
# Relatórios específicos
# ─────────────────────────────────────────────────────────────────────────────

def _pct(p: float) -> str:
    return f"{p * 100:.1f}%".replace(".", ",")


def secao_participacao(titulo: str, nome_coluna: str, df_valores: pd.DataFrame,
                       nota: str = "") -> Secao:
    """
    Tabela "item / valor / participação" com barra, ordenada do maior para o menor.
    `df_valores` tem duas colunas: o nome do item (`nome_coluna`) e "Valor" (float).
    """
    if df_valores is None or df_valores.empty:
        return Secao(titulo, pd.DataFrame(), nota=nota, vazio="Sem dados para o período.")
    d = df_valores.copy()
    d["Valor"] = pd.to_numeric(d["Valor"], errors="coerce").fillna(0.0)
    d = d.sort_values("Valor", ascending=False)
    total = float(d["Valor"].sum())
    frac = (d["Valor"] / total) if total > 0 else d["Valor"] * 0.0
    show = pd.DataFrame({
        nome_coluna: d[nome_coluna].values,
        "Valor": d["Valor"].map(fmt_moeda).values,
        "Participação": [_pct(f) for f in frac],
        "_barra": frac.values,
    })
    return Secao(titulo, show, barra="_barra", nota=nota)


def pdf_dashboard(periodo: str, total_rec: float, total_desp: float, saldo: float,
                  df_hist: pd.DataFrame, df_cat: pd.DataFrame, df_pag: pd.DataFrame,
                  emitido_por: str = "", agora=None) -> bytes:
    """
    Relatório do Dashboard.
    df_hist : colunas "Mês", "Receita", "Despesa" (floats) — últimos 6 meses.
    df_cat  : colunas "Categoria", "Valor" — despesas do mês por categoria.
    df_pag  : colunas "Pagamento", "Valor" — despesas do mês por forma de pagamento.
    """
    hist = df_hist.copy()
    hist["Saldo"] = hist["Receita"] - hist["Despesa"]
    hist_show = pd.DataFrame({
        "Mês": hist["Mês"].values,
        "Receitas": hist["Receita"].map(fmt_moeda).values,
        "Despesas": hist["Despesa"].map(fmt_moeda).values,
        "Saldo": hist["Saldo"].map(fmt_moeda).values,
    })
    nota = "Não inclui despesas pendentes (ainda não pagas)."
    return gerar_pdf(
        "Dashboard", f"Período: {periodo}",
        kpis=[("Receitas do mês", fmt_moeda(total_rec), "verde"),
              ("Despesas do mês", fmt_moeda(total_desp), "vermelho"),
              ("Saldo do mês", fmt_moeda(saldo), "verde" if saldo >= 0 else "vermelho")],
        secoes=[
            Secao("Histórico dos últimos 6 meses", hist_show),
            secao_participacao("Despesas por categoria", "Categoria", df_cat, nota=nota),
            secao_participacao("Despesas por forma de pagamento", "Pagamento", df_pag, nota=nota),
        ],
        emitido_por=emitido_por, agora=agora,
    )


def pdf_faturas_futuras(df_pend: pd.DataFrame, df_detalhe: pd.DataFrame | None = None,
                        titulo_detalhe: str = "", emitido_por: str = "", agora=None) -> bytes:
    """
    Projeção de faturas futuras.
    df_pend    : parcelas PENDENTES, com colunas "Mês Vencimento" ('AAAA-MM'),
                 "cartao" e "valor" (float).
    df_detalhe : (opcional) tabela já formatada da fatura específica selecionada na tela.
    """
    d = df_pend.copy()
    d["valor"] = pd.to_numeric(d["valor"], errors="coerce").fillna(0.0)
    piv = d.pivot_table(index="Mês Vencimento", columns="cartao", values="valor",
                        aggfunc="sum", fill_value=0.0).sort_index()
    piv.columns.name = None
    totais_mes = piv.sum(axis=1)
    maior = float(totais_mes.max()) if len(totais_mes) else 0.0

    show = pd.DataFrame({"Fatura": [fmt_mes_str_pt(m) for m in piv.index]})
    for cartao in piv.columns:
        show[str(cartao)] = piv[cartao].map(fmt_moeda).values
    show["Total"] = totais_mes.map(fmt_moeda).values
    show["_barra"] = (totais_mes / maior).values if maior > 0 else 0.0

    linha_total = {"Fatura": "TOTAL"}
    for cartao in piv.columns:
        linha_total[str(cartao)] = fmt_moeda(float(piv[cartao].sum()))
    linha_total["Total"] = fmt_moeda(float(totais_mes.sum()))
    linha_total["_barra"] = 0.0
    show = pd.concat([show, pd.DataFrame([linha_total])], ignore_index=True)

    secoes = [Secao("Valores projetados por fatura", show, barra="_barra",
                    nota="Considera apenas parcelas pendentes, agrupadas pelo mês de vencimento.")]
    if df_detalhe is not None and not df_detalhe.empty:
        secoes.append(Secao(titulo_detalhe or "Detalhamento da fatura selecionada", df_detalhe))

    return gerar_pdf(
        "Projeção de Faturas Futuras", "Cartão de crédito - parcelas pendentes",
        kpis=[("A pagar (todas as faturas)", fmt_moeda(float(totais_mes.sum())), "laranja"),
              ("Faturas futuras", str(len(piv.index)), "azul")],
        secoes=secoes, emitido_por=emitido_por, agora=agora,
    )
