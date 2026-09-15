"""
Registro manual de fechamentos de fatura, por cartão e por mês.

MOTIVAÇÃO: a data real em que uma fatura fecha varia de mês para mês
(ajustes do banco, fins de semana, feriados) — não é seguro assumir que o
cartão sempre fecha no mesmo "dia fixo do mês". Por isso, em vez de confiar
apenas no cálculo automático (`logica.cartoes.estimar_vencimento_parcela`),
o usuário passa a registrar aqui o fechamento e o vencimento reais de cada
fatura à medida que eles acontecem. Esse registro é a fonte de verdade
usada por `logica.cartoes.resolver_vencimento_parcela` para decidir em qual
fatura uma compra (ou parcela) efetivamente cai; o cálculo automático
continua existindo só como estimativa/fallback para meses ainda não
confirmados manualmente.

As funções puras deste módulo (sem dependência de Sheets/Streamlit) são:
`encontrar_fechamento_para_compra`, `indexar_fechamentos_por_mes` e
`detectar_buracos_fechamentos`. `obter_fechamento_parcela` também é pura,
mas está mantida apenas por compatibilidade — veja o aviso em sua
docstring.
"""

from datetime import date, datetime

from sheets.client import get_sheet, sheet_to_df, delete_rows_batch, append_row_id_unico
from sheets.loaders import carregar_fechamentos
from utils.datas import add_months


def _parse_data(s) -> date:
    return datetime.strptime(str(s), "%Y-%m-%d").date()


# ── Funções puras ────────────────────────────────────────────────────────────

def encontrar_fechamento_para_compra(data_compra: date, fechamentos_ordenados: list):
    """
    Retorna o índice, dentro de `fechamentos_ordenados`, do fechamento com
    a MENOR data de fechamento que ainda seja igual ou posterior à data da
    compra — ou seja, a fatura em que essa compra efetivamente cai.

    Não depende da lista já estar ordenada (faz uma busca pelo mínimo, não
    um "primeiro que encontrar"), embora na prática ela sempre venha
    ordenada de `fechamentos_ordenados_por_cartao`.

    Retorna None se nenhum fechamento futuro suficiente foi registrado
    ainda para essa compra (quem chamar deve então recorrer à estimativa
    automática).
    """
    candidatos = [(i, f) for i, f in enumerate(fechamentos_ordenados) if f["data_fechamento"] >= data_compra]
    if not candidatos:
        return None
    return min(candidatos, key=lambda par: par[1]["data_fechamento"])[0]


def obter_fechamento_parcela(data_compra: date, num_parcela: int, fechamentos_ordenados: list):
    """
    ATENÇÃO — mantida por compatibilidade, mas NÃO é mais usada por
    `resolver_vencimento_parcela` (ver módulo `logica/cartoes.py`).

    Retorna o registro de fechamento correspondente à N-ésima parcela de
    uma compra andando N-1 posições na lista a partir do fechamento da 1ª
    parcela. Essa abordagem quebra quando há um mês "pulado" no meio dos
    fechamentos registrados: a partir do buraco, todas as parcelas
    seguintes acabam casando com o fechamento errado (deslocadas em uma
    posição). Foi substituída por `indexar_fechamentos_por_mes` +
    resolução por rótulo de mês, que resolve cada parcela de forma
    independente e não sofre esse efeito cascata.
    """
    idx_base = encontrar_fechamento_para_compra(data_compra, fechamentos_ordenados)
    if idx_base is None:
        return None
    idx_parcela = idx_base + (num_parcela - 1)
    if idx_parcela >= len(fechamentos_ordenados):
        return None
    return fechamentos_ordenados[idx_parcela]


def indexar_fechamentos_por_mes(fechamentos_ordenados: list) -> dict:
    """
    Converte a lista de fechamentos num dicionário indexado por
    `mes_referencia` (ex.: {"2026-07": {...}, "2026-09": {...}}).

    É essa busca por RÓTULO DE MÊS — em vez de posição na lista — que torna
    `resolver_vencimento_parcela` resistente a "buracos": se agosto não foi
    registrado, procurar por "2026-08" simplesmente não encontra nada e
    aquela parcela específica cai na estimativa automática, sem deslocar
    as parcelas de setembro/outubro/etc., que continuam sendo encontradas
    normalmente pelo próprio rótulo.

    Em caso de `mes_referencia` duplicado (dois fechamentos cadastrados
    para o mesmo mês por engano), o último da lista prevalece.
    """
    return {f["mes_referencia"]: f for f in fechamentos_ordenados if f.get("mes_referencia")}


def detectar_buracos_fechamentos(fechamentos_ordenados: list) -> list:
    """
    Verifica se há meses "pulados" entre o primeiro e o último fechamento
    registrado para um cartão — ou seja, meses dentro do intervalo já
    coberto que ainda não têm um fechamento manual confirmado.

    Isso NÃO é mais uma questão de correção (resolver_vencimento_parcela
    já isola cada mês independentemente), mas continua sendo útil como
    aviso: esses meses vão gerar parcelas com origem 'estimado' até serem
    registrados manualmente.

    Retorna a lista de meses faltando (formato 'YYYY-MM'), em ordem
    cronológica. Lista vazia = sem buracos (ou menos de 2 fechamentos
    registrados, caso em que não há intervalo para checar).
    """
    meses_registrados = {f["mes_referencia"] for f in fechamentos_ordenados if f.get("mes_referencia")}
    if len(meses_registrados) < 2:
        return []
    ordenados = sorted(meses_registrados)
    ano_p, mes_p = map(int, ordenados[0].split("-"))
    ano_u, mes_u = map(int, ordenados[-1].split("-"))
    cursor = date(ano_p, mes_p, 1)
    fim = date(ano_u, mes_u, 1)
    faltando = []
    while cursor < fim:
        rotulo = cursor.strftime("%Y-%m")
        if rotulo not in meses_registrados:
            faltando.append(rotulo)
        cursor = add_months(cursor, 1)
    return faltando


# ── Persistência (Google Sheets) ────────────────────────────────────────────

def fechamentos_ordenados_por_cartao(cartao: str) -> list:
    """
    Carrega os fechamentos registrados para um cartão e devolve a lista
    ordenada cronologicamente, com as datas já convertidas para `date`
    (pronta para uso em `logica.cartoes.resolver_vencimento_parcela`).
    Registros com datas malformadas são ignorados silenciosamente.
    """
    df = carregar_fechamentos()
    if df.empty:
        return []
    df_c = df[df["cartao"].astype(str) == cartao].copy()
    if df_c.empty:
        return []
    registros = []
    for _, row in df_c.iterrows():
        try:
            registros.append({
                "id": row["id"],
                "mes_referencia": str(row["mes_referencia"]),
                "data_fechamento": _parse_data(row["data_fechamento"]),
                "data_vencimento": _parse_data(row["data_vencimento"]),
                "observacao": row.get("observacao", ""),
            })
        except Exception:
            continue
    registros.sort(key=lambda r: r["data_fechamento"])
    return registros


def salvar_fechamento(cartao: str, mes_referencia: str, data_fechamento: date,
                       data_vencimento: date, obs: str = ""):
    ws = get_sheet("fechamentos")
    append_row_id_unico(ws, [cartao, mes_referencia,
                             data_fechamento.strftime("%Y-%m-%d"),
                             data_vencimento.strftime("%Y-%m-%d"), obs,
                             datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
    carregar_fechamentos.clear()


def excluir_fechamento(fid: int):
    ws = get_sheet("fechamentos")
    df = sheet_to_df(ws)
    if not df.empty:
        delete_rows_batch(ws, df[df["id"].astype(str) == str(fid)].index.tolist())
    carregar_fechamentos.clear()
