"""
Funções de formatação e sanitização de valores exibidos ao usuário.
Sem dependência de Streamlit nem de Google Sheets — fáceis de testar isoladamente.
"""

import html as _html
import re
from datetime import datetime


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

