"""
Regras de negócio relacionadas a cartões de crédito: cálculo de vencimento
de parcela, cadastro/exclusão de cartão e verificação de vínculos.

ADAPTAÇÃO — fechamento manual: a data real de fechamento da fatura varia de
mês para mês, então o "dia fixo do mês" cadastrado no cartão não é mais
tratado como fonte de verdade — é apenas uma ESTIMATIVA usada enquanto o
fechamento real daquele mês ainda não foi registrado manualmente (ver
`logica/fechamentos.py`). Use sempre `resolver_vencimento_parcela` a partir
de código novo; `estimar_vencimento_parcela` só existe como o cálculo de
fallback interno (e para pré-preencher sugestões na UI).
"""

import calendar
from datetime import date, datetime

from sheets.client import get_sheet, sheet_to_df, delete_rows_batch, append_row_id_unico
from sheets.loaders import carregar_cartoes, carregar_despesas, carregar_parcelas
from utils.datas import add_months
from logica.fechamentos import encontrar_fechamento_para_compra, indexar_fechamentos_por_mes


def estimar_vencimento_parcela(data_compra: date, dia_fechamento: int, dia_vencimento: int, num_parcela: int) -> date:
    """
    Estimativa automática do vencimento, assumindo que o cartão sempre fecha
    no mesmo dia do mês (`dia_fechamento`). É uma aproximação — a fonte de
    verdade é o fechamento manual registrado em `logica/fechamentos.py`;
    esta função só deve ser usada como fallback (via `resolver_vencimento_parcela`)
    ou para sugerir um valor inicial ao cadastrar um fechamento manual.
    """
    try:
        fechamento_mes_compra = date(data_compra.year, data_compra.month, dia_fechamento)
    except ValueError:
        last_day = calendar.monthrange(data_compra.year, data_compra.month)[1]
        fechamento_mes_compra = date(data_compra.year, data_compra.month, last_day)
    meses_adicionais = 1 if data_compra > fechamento_mes_compra else 0
    total_meses = meses_adicionais + (num_parcela - 1)
    if dia_vencimento < dia_fechamento:
        total_meses += 1
    venc = add_months(data_compra, total_meses)
    max_day = calendar.monthrange(venc.year, venc.month)[1]
    return date(venc.year, venc.month, min(dia_vencimento, max_day))


def resolver_vencimento_parcela(data_compra: date, dia_fechamento: int, dia_vencimento: int,
                                 num_parcela: int, fechamentos_ordenados: list) -> tuple:
    """
    Determina o vencimento de uma parcela, priorizando o fechamento
    MANUALMENTE registrado para o mês correspondente (mais preciso, pois
    reflete a data real). Só recai na estimativa automática quando nenhum
    fechamento manual cobre esse mês específico ainda.

    `fechamentos_ordenados` deve vir de
    `logica.fechamentos.fechamentos_ordenados_por_cartao(cartao)`.

    Estratégia em 2 passos — resistente a "buracos" no meio da sequência de
    fechamentos registrados (ver discussão detalhada em
    `logica/fechamentos.py`):

      1) Usa `encontrar_fechamento_para_compra` para achar, entre os
         fechamentos manuais registrados, aquele que a COMPRA realmente
         atravessou (comparação por data real). Esse é o mês-base da 1ª
         parcela; se não houver fechamento aplicável ainda, o mês-base vem
         da estimativa automática.
      2) Cada parcela calcula seu próprio mês-alvo (mês-base + N-1 meses) e
         busca DIRETAMENTE por esse rótulo de mês nos fechamentos
         registrados — não pela posição na lista. Assim, um mês faltando
         no meio afeta só aquela parcela específica; as parcelas seguintes
         continuam encontrando seus próprios fechamentos normalmente, sem
         efeito cascata.

    Retorna (data_vencimento: date, origem: str), onde origem é
    'manual' (fechamento confirmado pelo usuário) ou
    'estimado' (calculado automaticamente, ainda não confirmado).
    """
    fechamentos_por_mes = indexar_fechamentos_por_mes(fechamentos_ordenados)

    idx_base = encontrar_fechamento_para_compra(data_compra, fechamentos_ordenados)
    if idx_base is not None:
        mes_base = fechamentos_ordenados[idx_base]["mes_referencia"]
    else:
        mes_base = estimar_vencimento_parcela(data_compra, dia_fechamento, dia_vencimento, 1).strftime("%Y-%m")

    ano_base, mes_base_num = map(int, mes_base.split("-"))
    mes_alvo = add_months(date(ano_base, mes_base_num, 1), num_parcela - 1).strftime("%Y-%m")

    fechamento = fechamentos_por_mes.get(mes_alvo)
    if fechamento is not None:
        return fechamento["data_vencimento"], "manual"
    return estimar_vencimento_parcela(data_compra, dia_fechamento, dia_vencimento, num_parcela), "estimado"


def salvar_cartao(nome, limite, dia_fechamento, dia_vencimento):
    ws = get_sheet("cartoes")
    append_row_id_unico(ws, [nome, limite, dia_fechamento, dia_vencimento,
                             datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
    carregar_cartoes.clear()


# Item 3 · Verificar vínculos antes de excluir cartão
def cartao_tem_vinculos(nome_cartao: str) -> dict:
    """
    Retorna dict com contagens de despesas e parcelas pendentes vinculadas ao cartão.
    Usado para bloquear exclusão se houver vínculos ativos.
    """
    df_d = carregar_despesas()
    df_p = carregar_parcelas()

    n_despesas = 0
    n_parcelas_pendentes = 0

    if not df_d.empty and "cartao" in df_d.columns:
        n_despesas = int((df_d["cartao"].astype(str) == nome_cartao).sum())

    if not df_p.empty and "cartao" in df_p.columns:
        mask_p = (df_p["cartao"].astype(str) == nome_cartao) & \
                 (df_p["status"].astype(str) == "pendente")
        n_parcelas_pendentes = int(mask_p.sum())

    return {"despesas": n_despesas, "parcelas_pendentes": n_parcelas_pendentes}


def excluir_cartao(cid: int):
    ws = get_sheet("cartoes")
    df = sheet_to_df(ws)
    if not df.empty:
        delete_rows_batch(ws, df[df["id"].astype(str) == str(cid)].index.tolist())
    carregar_cartoes.clear()
