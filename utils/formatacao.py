"""
Funções de formatação e sanitização de valores exibidos ao usuário.
Sem dependência de Streamlit nem de Google Sheets — fáceis de testar isoladamente.
"""

import html as _html
import re
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP


def _numero_br(v) -> str:
    """'1.234,56' (valor absoluto, sem sinal e sem símbolo). Levanta erro se não for número."""
    return "{:,.2f}".format(abs(float(v))).replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_moeda(v):
    """'R$ 1.234,56'; negativo vem com o sinal na frente: '-R$ 1.234,56'."""
    try:
        numero = _numero_br(v)
        negativo = float(v) < 0 and numero != "0,00"   # -0,001 não vira "-R$ 0,00"
        return ("-R$ " if negativo else "R$ ") + numero
    except Exception:
        return "R$ 0,00"


def fmt_numero_campo(v) -> str:
    """'1.234,56' (ou '-1.234,56') sem o símbolo — para preencher campos de valor."""
    try:
        numero = _numero_br(v)
        return ("-" if float(v) < 0 and numero != "0,00" else "") + numero
    except Exception:
        return "0,00"


# B-02 · Parser de valor robusto: aceita tanto "1.234,56" (BR) quanto "1234.56" (US)
def parse_valor(texto: str) -> float:
    if texto is None:
        raise ValueError("valor vazio")
    t = str(texto).strip()
    if not t:
        raise ValueError("valor vazio")
    t = re.sub(r"[^0-9.,-]", "", t)
    if "," in t and "." in t:
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
    elif "," in t:
        t = t.replace(".", "").replace(",", ".")
    return float(t)


def formatar_input_moeda(raw: str) -> str:
    """
    Formata dígitos digitados livremente como valor monetário brasileiro,
    preenchendo as casas de centavos da direita para a esquerda — o mesmo
    comportamento usado em apps bancários (digitar "150" vira "1,50";
    digitar "15000" vira "150,00"; digitar só "1" vira "0,01").

    Ignora qualquer caractere que não seja dígito, então também funciona
    se o texto já vier formatado (colado): "1.234,56" -> dígitos "123456"
    -> "1.234,56" (o mesmo resultado, já que os 2 últimos dígitos sempre
    viram os centavos).

    Nunca lança exceção — texto vazio ou só zeros retorna "0,00".
    """
    digitos = re.sub(r"[^0-9]", "", raw or "")
    digitos = digitos.lstrip("0")
    if not digitos:
        return "0,00"
    digitos = digitos.zfill(3)
    parte_inteira, centavos = digitos[:-2], digitos[-2:]
    milhar_fmt = "{:,}".format(int(parte_inteira)).replace(",", ".")
    return f"{milhar_fmt},{centavos}"


def converter_data_para_exibicao(dt_str):
    try:
        return datetime.strptime(str(dt_str), "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        try:
            return datetime.strptime(str(dt_str), "%Y/%m/%d").strftime("%d/%m/%Y")
        except Exception:
            return dt_str


# S-02 · card_html com sanitização via html.escape
def card_html(label, value, color_class):
    label_safe = _html.escape(str(label))
    value_safe = _html.escape(str(value))
    return f"""
    <div class="card">
        <div class="card-label">{label_safe}</div>
        <div class="card-value {color_class}">{value_safe}</div>
    </div>
    """


def kpi_card_html(icone, label, value, color_class, sublinhas=(), altura_min="8.6rem"):
    """
    Cartão de totais do Dashboard: ícone + rótulo, valor grande colorido e,
    opcionalmente, linhas extras `(rótulo, valor)` embaixo.
    Só cores translúcidas/herdadas (tema claro e escuro — regra 8).
    """
    subs = "".join(
        '<div style="display:flex;justify-content:space-between;gap:0.75rem;'
        'font-size:0.8rem;opacity:0.8;margin-top:4px;">'
        f"<span>{_html.escape(str(r))}</span><span>{_html.escape(str(v))}</span></div>"
        for r, v in sublinhas
    )
    if subs:
        subs = ('<div style="border-top:1px solid rgba(128,128,128,0.25);'
                f'margin-top:10px;padding-top:6px;">{subs}</div>')
    return (
        f'<div class="card" style="min-height:{_html.escape(str(altura_min))};">'
        f'<div class="card-label">{_html.escape(str(icone))} {_html.escape(str(label))}</div>'
        f'<div class="card-value {color_class}">{_html.escape(str(value))}</div>'
        f"{subs}</div>"
    )


def fmt_percentual(parte, total) -> str:
    """'31,2%' — parte/total com uma casa decimal e vírgula. Total zero/inválido → '0,0%'."""
    try:
        parte, total = float(parte), float(total)
        if total <= 0:
            return "0,0%"
        return "{:.1f}%".format(parte / total * 100).replace(".", ",")
    except (TypeError, ValueError):
        return "0,0%"


def estado_vazio_html(icone, titulo, frase) -> str:
    """
    Miolo do estado vazio padrão (ícone + título + frase, centralizados). O botão é
    desenhado à parte por `utils.widgets.estado_vazio`. Só herda cor/fundo (regra 8).
    """
    return (
        '<div style="text-align:center;padding:1rem 0.5rem 0.5rem 0.5rem;">'
        f'<div style="font-size:2rem;line-height:1.2;">{_html.escape(str(icone))}</div>'
        f'<div style="font-size:1.1rem;font-weight:600;margin-top:0.4rem;">{_html.escape(str(titulo))}</div>'
        '<div style="font-size:0.9rem;opacity:0.75;max-width:28rem;margin:0.35rem auto 0.5rem auto;">'
        f'{_html.escape(str(frase))}</div></div>'
    )


# Grade dos 3 cartões de totais: todos da altura do mais alto (antes, com st.columns, cada
# cartão tinha a altura do próprio conteúdo). No celular empilha em uma coluna.
_CSS_KPI_GRID = (
    "<style>.kpi-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1rem;"
    "align-items:stretch;}"
    "@media (max-width:640px){.kpi-grid{grid-template-columns:1fr;}}</style>"
)


def kpi_grid_html(cartoes) -> str:
    """Junta cartões de `kpi_card_html` numa grade de 3 colunas com a mesma altura."""
    return _CSS_KPI_GRID + '<div class="kpi-grid">' + "".join(cartoes) + "</div>"


def fmt_moeda_inteiro(v):
    """'R$ 4.805' (sem centavos) — para blocos estreitos como a linha do tempo."""
    try:
        # ROUND_HALF_UP: 420,50 → 421 (o arredondamento padrão do Python daria 420)
        inteiro = int(Decimal(str(float(v))).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        texto = "{:,}".format(abs(inteiro)).replace(",", ".")
        return ("-R$ " if inteiro < 0 else "R$ ") + texto
    except Exception:
        return "—"


# CSS próprio da linha do tempo (vai junto do HTML). Só cores translúcidas/herdadas
# nos blocos comuns (tema claro/escuro — regra 8); o vermelho do destaque é o mesmo
# das classes `.red` do app.
_CSS_LINHA_DO_TEMPO = """
<style>
.tl-grid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:8px;margin:2px 0 6px;}
.tl-bloco{border:1px solid rgba(128,128,128,0.30);background:rgba(128,128,128,0.06);
  border-radius:8px;padding:10px 4px;text-align:center;min-width:0;}
.tl-mes{font-size:0.82rem;opacity:0.75;line-height:1.3;white-space:nowrap;}
.tl-valor{font-size:0.95rem;font-weight:600;margin-top:4px;line-height:1.3;white-space:nowrap;}
.tl-sub{font-size:0.7rem;opacity:0.6;margin-top:2px;line-height:1.2;min-height:0.9rem;}
.tl-fut{border:1px dashed rgba(128,128,128,0.65);background:transparent;}
.tl-fut .tl-valor{opacity:0.85;}
.tl-sel{border:1.5px solid rgba(220,38,38,0.75);background:rgba(220,38,38,0.12);}
.tl-sel .tl-mes,.tl-sel .tl-valor{color:#dc2626;color:light-dark(#dc2626,#f87171);opacity:1;}
.tl-sel.tl-fut{border-style:dashed;}
.tl-legenda{display:flex;flex-wrap:wrap;gap:14px;font-size:0.75rem;opacity:0.75;margin-bottom:14px;}
.tl-sw{display:inline-block;width:14px;height:10px;border-radius:2px;vertical-align:-1px;margin-right:5px;}
.tl-curto{display:none;}
@media (max-width:640px){
  .tl-grid{gap:4px;}
  .tl-bloco{padding:8px 1px;}
  .tl-mes{font-size:0.72rem;}
  .tl-valor{font-size:0.7rem;}
  .tl-longo{display:none;}
  .tl-curto{display:inline;}
}
</style>
"""


def linha_do_tempo_html(blocos) -> str:
    """
    HTML da linha do tempo de meses do Dashboard (blocos de `logica.dashboard.linha_do_tempo`).
    Selecionado em vermelho; mês futuro com borda tracejada e o valor planejado.
    """
    itens = []
    for b in blocos:
        classes = "tl-bloco"
        if b["planejado"]:
            classes += " tl-fut"
        if b["selecionado"]:
            classes += " tl-sel"
        valor = "—" if b["valor"] is None else fmt_moeda_inteiro(b["valor"])
        sub = ('<span class="tl-longo">planejado</span><span class="tl-curto">plan.</span>'
               if b["planejado"] else "")
        rotulo = _html.escape(str(b["rotulo"]))
        tipo = "planejadas" if b["planejado"] else "pagas"
        itens.append(
            f'<div class="{classes}" title="Despesas {tipo} — {rotulo}">'
            f'<div class="tl-mes">{rotulo}</div>'
            f'<div class="tl-valor">{_html.escape(valor)}</div>'
            f'<div class="tl-sub">{sub}</div></div>'
        )
    legenda = (
        '<div class="tl-legenda">'
        '<span><span class="tl-sw" style="border:1.5px solid rgba(220,38,38,0.75);'
        'background:rgba(220,38,38,0.12)"></span>Mês selecionado</span>'
        '<span><span class="tl-sw" style="border:1px solid rgba(128,128,128,0.45);'
        'background:rgba(128,128,128,0.06)"></span>Despesas pagas</span>'
        '<span><span class="tl-sw" style="border:1px dashed rgba(128,128,128,0.8)"></span>'
        'Despesas planejadas</span></div>'
    )
    return _CSS_LINHA_DO_TEMPO + '<div class="tl-grid">' + "".join(itens) + "</div>" + legenda

