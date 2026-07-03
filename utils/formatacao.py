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
