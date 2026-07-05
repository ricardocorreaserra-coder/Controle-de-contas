"""
Constantes e configurações globais da aplicação.
Centralizar aqui evita duplicação e facilita ajustes futuros
(ex.: novas categorias, novos modos de pagamento).
"""

# ── Meses em português ────────────────────────────────────────────────────────
MESES_PT = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr",
    5: "Mai", 6: "Jun", 7: "Jul", 8: "Ago",
    9: "Set", 10: "Out", 11: "Nov", 12: "Dez"
}

# ── Constantes de domínio ───────────────────────────────────────────────────────
PAGAMENTOS   = ["Dinheiro", "Cartão de crédito", "Débito", "Pix", "Vale alimentação"]
CAT_DESP     = ["Alimentação", "Transporte", "Saúde", "Moradia", "Lazer",
                 "Educação", "Vestuário", "Despesa bancária", "Outros"]
CAT_REC      = ["Salário", "Freelance", "Investimentos", "Aluguel recebido", "Outros"]
PARCELAS_OPT = [1, 2, 3, 4, 5, 6, 10, 12, 18, 24]
DIA_VENCIMENTO_PADRAO = 10  # usado apenas se um cartão referenciado não for encontrado no cadastro

# ── Google Sheets ──────────────────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

EXPECTED_HEADERS = {
    "despesas": ["id", "descricao", "valor", "data", "local",
                 "pagamento", "categoria", "cartao", "n_parcelas",
                 "observacao", "criado_em", "recorrente", "recorrencia_fim"],
    "parcelas": ["id", "despesa_id", "numero", "total",
                 "valor", "vencimento", "status", "descricao", "cartao",
                 "origem_vencimento"],
    "receitas": ["id", "descricao", "valor", "data",
                 "categoria", "observacao", "criado_em", "recorrente", "recorrencia_fim"],
    "cartoes":  ["id", "nome", "limite", "dia_fechamento", "dia_vencimento", "criado_em"],
    "planejamento": ["id", "tipo", "descricao", "valor", "mes",
                      "categoria", "observacao", "criado_em"],
    # Fechamentos reais de fatura, registrados manualmente pelo usuário —
    # ver logica/fechamentos.py para o motivo desta tabela existir.
    "fechamentos": ["id", "cartao", "mes_referencia", "data_fechamento",
                     "data_vencimento", "observacao", "criado_em"],
    # Empréstimos — aba isolada, apenas para consulta e controle. NUNCA
    # entra em nenhuma soma de despesas, dashboard ou planejamento —
    # ver logica/emprestimos.py.
    # `valor_total_devido` é sempre CALCULADO (valor_parcela × parcelas_restantes),
    # nunca digitado manualmente. `proxima_data_vencimento` é a data-base a
    # partir da qual a baixa automática das parcelas é calculada.
    "emprestimos": ["id", "descricao", "banco", "valor_parcela",
                     "parcelas_restantes", "proxima_data_vencimento",
                     "valor_total_devido", "criado_em", "atualizado_em"],
}

# ── CSS da aplicação ─────────────────────────────────────────────────────────────
CSS = """
<style>
    .main-header {
        background: linear-gradient(135deg, #2563eb, #1e40af);
        color: white; padding: 1rem 1.5rem; border-radius: 10px;
        margin-bottom: 1.5rem;
        display: flex; align-items: center; gap: 0.5rem;
    }
    .card {
        background: white; border: 1px solid #e2e8f0;
        border-radius: 12px; padding: 1.25rem 1.5rem;
        text-align: center;
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05), 0 2px 4px -1px rgba(0,0,0,0.03);
        transition: transform 0.2s, box-shadow 0.2s;
    }
    .card:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 15px -3px rgba(0,0,0,0.05), 0 4px 6px -2px rgba(0,0,0,0.03);
    }
    .card-label { font-size: 0.85rem; color: #64748b; margin-bottom: 6px; font-weight: 500; }
    .card-value { font-size: 1.5rem; font-weight: 700; }
    .green  { color: #16a34a; }
    .red    { color: #dc2626; }
    .blue   { color: #2563eb; }
    .orange { color: #d97706; }
    .stTabs [data-baseweb="tab"] { font-size: 0.95rem; }
    div[data-testid="stSuccess"] { border-radius: 8px; }
    div[data-testid="stWarning"] { border-radius: 8px; }
    .login-box {
        max-width: 360px; margin: 6rem auto; text-align: center;
        padding: 2rem; background: white; border-radius: 16px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 4px 24px rgba(0,0,0,0.07);
    }
    .plan-banner {
        background: #eff6ff; border: 1px solid #bfdbfe; color: #1e3a8a;
        padding: 0.75rem 1rem; border-radius: 10px; margin-bottom: 1rem;
        font-size: 0.92rem;
    }
</style>
"""
