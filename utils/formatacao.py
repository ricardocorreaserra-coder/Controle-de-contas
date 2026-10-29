"""
Funções de formatação e sanitização de valores exibidos ao usuário.
Sem dependência de Streamlit nem de Google Sheets — fáceis de testar isoladamente.
"""

import html as _html
import re
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP


def fmt_moeda(v):
    try:
        return "R$ {:,.2f}".format(float(v)).replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"


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


def kpi_card_html(icone, label, value, color_class, sublinhas=()):
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
        '<div class="card" style="min-height:8.6rem;">'
        f'<div class="card-label">{_html.escape(str(icone))} {_html.escape(str(label))}</div>'
        f'<div class="card-value {color_class}">{_html.escape(str(value))}</div>'
        f"{subs}</div>"
    )


def fmt_moeda_inteiro(v):
    """'R$ 4.805' (sem centavos) — para blocos estreitos como a linha do tempo."""
    try:
        # ROUND_HALF_UP: 420,50 → 421 (o arredondamento padrão do Python daria 420)
        inteiro = int(Decimal(str(float(v))).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        return "R$ {:,}".format(inteiro).replace(",", ".")
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
.tl-sel .tl-mes,.tl-sel .tl-valor{color:#dc2626;opacity:1;}
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

