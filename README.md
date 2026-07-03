# Controle de Contas — Estrutura Modular

Este projeto foi dividido a partir de um único arquivo `app.py` de ~1400
linhas em módulos menores, organizados por responsabilidade. O
comportamento da aplicação é **idêntico** ao original — nenhuma lógica foi
alterada, apenas reorganizada.

## Como rodar

```bash
pip install -r requirements.txt
streamlit run app.py
```

Para rodar os testes localmente, instale também as dependências de
desenvolvimento:

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

`requirements.txt` tem as versões pinadas exatamente nas que foram usadas
para validar esta versão modular (testes unitários + boot do app rodando
num venv limpo) — evita que uma atualização futura de alguma dependência
quebre o app sem aviso. `requirements-dev.txt` só tem `pytest`/`pytest-cov`
e não precisa subir para o Streamlit Cloud.

Configure `secrets.toml` (em `.streamlit/secrets.toml`) exatamente como no
projeto original, com `APP_PASSWORD`, `SHEET_NAME` e `gcp_service_account`.

## Deploy no Streamlit Community Cloud

O Streamlit Cloud instala as dependências direto de `requirements.txt` na
raiz do repositório — não é preciso configurar mais nada além disso. Os
secrets continuam sendo configurados separadamente, pelo painel
**Settings → Secrets** do app (não vêm do Git).

## Estrutura de pastas

```
app.py                         # Ponto de entrada: page_config, CSS, auth, monta as abas
config.py                      # Constantes (categorias, pagamentos, headers, CSS)
auth.py                        # Autenticação por senha (S-01 / B-01)

utils/
  formatacao.py                # fmt_moeda, parse_valor, card_html, converter_data_para_exibicao
  datas.py                     # add_months, fmt_mes_pt, seletor_mes_ano, proximos_12_meses...

sheets/
  client.py                    # Conexão com Google Sheets, get_sheet, sheet_to_df, next_id
  loaders.py                   # Funções de carregamento cacheadas (@st.cache_data)

logica/
  despesas.py                  # salvar/excluir despesa, encerrar recorrência
  receitas.py                  # salvar/excluir receita, encerrar recorrência
  cartoes.py                   # cálculo de vencimento, cadastro/exclusão de cartão
  parcelas.py                  # divisão de parcelas, lançamento manual, baixa de fatura
  planejamento.py              # projeção de 12 meses (R-01) + cache em session_state (R-03)
  exportacao.py                # geração de Excel/CSV (R-02)

paginas/
  dashboard.py                 # Aba 📊 Dashboard
  lancar_despesa.py            # Aba ➖ Lançar Despesa
  lancar_receita.py            # Aba ➕ Lançar Receita
  lista_despesas.py            # Aba ☰ Despesas
  cartao_credito.py            # Aba 💳 Cartão de Crédito (4 sub-abas)
  conta_corrente.py            # Aba 🏦 Conta Corrente
  planejamento_12_meses.py     # Aba 🔮 Planejamento 12 Meses (3 sub-abas)
```

## Ponto de atenção: cache do Streamlit

`st.cache_data` e `st.cache_resource` associam o cache ao **objeto de
função**, não ao arquivo onde ele é chamado. Por isso:

- Todas as funções decoradas (`get_sheets_client`, `get_workbook` em
  `sheets/client.py`; `carregar_cartoes`, `carregar_despesas`,
  `carregar_receitas`, `carregar_parcelas`, `carregar_planejamento` em
  `sheets/loaders.py`) são definidas **uma única vez** em todo o projeto.
- Qualquer módulo que precise ler dados ou invalidar cache (`.clear()`)
  **importa** a função original — nunca recria uma versão equivalente.
  Isso é o que garante que, por exemplo, `carregar_despesas.clear()`
  chamado em `logica/despesas.py` realmente limpe o mesmo cache usado
  por `paginas/dashboard.py`.
- O panorama de 12 meses (`logica/planejamento.py`) usa
  `st.session_state` em vez de `@st.cache_data`, pois depende da
  combinação de várias fontes já cacheadas e precisa de um botão de
  atualização manual explícito (`invalidar_cache_panorama`).

## Fechamento de fatura: manual, não mais um "dia fixo do mês"

A data real em que uma fatura fecha varia de mês para mês (ajustes do
banco, fins de semana, feriados). Por isso o cálculo deixou de assumir um
dia fixo como fonte de verdade:

- **`logica/fechamentos.py`** — novo módulo onde você registra, por cartão
  e por mês (aba **🗓️ Fechamentos**, dentro de 💳 Cartão de Crédito), o
  fechamento e o vencimento **reais** de cada fatura.
- **`logica/cartoes.py`** — `estimar_vencimento_parcela` (o antigo
  `calcular_vencimento_parcela`, renomeado) continua existindo, mas agora
  só como estimativa/fallback. `resolver_vencimento_parcela` é a função
  usada pelo restante do app: prioriza o fechamento manual já registrado
  para o mês da parcela e só recai na estimativa quando não há registro
  ainda.
- **Parcelas ganham uma "origem"** (`origem_vencimento`, coluna nova na
  planilha `parcelas`): `manual` quando o vencimento veio de um fechamento
  confirmado (ou foi digitado à mão), `estimado` quando ainda é um cálculo
  automático provisório. A aba **📊 Parcelas** mostra essa origem como
  badge (✅ Confirmado / 🔧 Estimado) e permite corrigir o vencimento de
  qualquer parcela manualmente a qualquer momento.
- Sheets já existentes são migrados automaticamente: `_migrar_headers_se_preciso`
  (em `sheets/client.py`) adiciona a coluna `origem_vencimento` e cria a
  aba `fechamentos` na primeira execução, sem apagar dados existentes.
  Parcelas antigas (sem essa coluna preenchida) são tratadas como
  "estimado" por segurança, já que de fato vieram do cálculo automático.

### Resistência a "buracos" na sequência de fechamentos

A primeira versão de `resolver_vencimento_parcela` casava a N-ésima
parcela com a N-ésima **posição** na lista de fechamentos registrados. Se
um mês fosse esquecido no meio (ex.: registrou julho e setembro, mas
pulou agosto), a 2ª parcela acabava casando com o fechamento de setembro
em vez de cair numa estimativa isolada de agosto — o buraco "empurrava"
todas as parcelas seguintes daquela compra para o mês errado. Esse
comportamento antigo está documentado (e coberto por teste, para não
regredir) em `obter_fechamento_parcela`, mantida só por compatibilidade.

A correção trocou "posição na lista" por "busca por rótulo de mês":

- **`indexar_fechamentos_por_mes`** transforma a lista num dicionário
  `{"2026-07": {...}, "2026-09": {...}}`.
- **`resolver_vencimento_parcela`** calcula o mês-alvo de cada parcela
  (mês da 1ª parcela + N-1) e busca diretamente por esse rótulo — não por
  posição. Um mês faltando afeta *só aquele mês*; as parcelas seguintes
  continuam encontrando seus próprios fechamentos normalmente.
- **`detectar_buracos_fechamentos`** varre o intervalo já coberto pelos
  fechamentos registrados de um cartão e aponta quais meses ainda faltam.
  Não é mais uma questão de correção (a resolução já é robusta a isso),
  mas é um aviso útil: a aba **🗓️ Fechamentos** mostra um `st.warning`
  por cartão listando os meses sem fechamento confirmado, para você saber
  quais parcelas ainda estão rodando na estimativa automática.

Veja `tests/test_cartoes.py::TestResolverVencimentoParcela::test_buraco_no_meio_nao_desalinha_as_parcelas_seguintes`
e `tests/test_fechamentos.py::TestObterFechamentoParcelaLegado::test_com_buraco_no_meio_a_versao_legada_desalinha_a_parcela_seguinte`
para ver as duas versões (corrigida e antiga) lado a lado.

## Testes automatizados

Foram escritos testes unitários (`pytest`) para as funções puras do
projeto — aquelas sem dependência de Streamlit nem do Google Sheets,
que recebem entrada e devolvem saída de forma previsível:

```
tests/
  conftest.py           # garante que a raiz do projeto esteja no sys.path
  test_formatacao.py     # fmt_moeda, parse_valor, converter_data_para_exibicao, card_html
  test_datas.py           # fmt_mes_pt, fmt_mes_str_pt, add_months, mes_ativo_recorrencia, proximos_12_meses
  test_cartoes.py         # estimar_vencimento_parcela (fallback) e resolver_vencimento_parcela (prioriza manual, resistente a buracos)
  test_parcelas.py        # valores_parcelas (garante que a soma das parcelas bate com o total — B-03)
  test_fechamentos.py     # encontrar_fechamento_para_compra, indexar_fechamentos_por_mes, detectar_buracos_fechamentos
```

Rodar os testes:

```bash
pip install pytest pytest-cov   # pytest-cov é opcional, só para o relatório de cobertura
pytest                          # roda a suíte inteira (112 testes)
pytest --cov=utils --cov=logica --cov-report=term-missing   # com cobertura
```

**Cobertura obtida** nos módulos alvo (funções puras apenas):

| Módulo                 | Cobertura | Observação |
|-------------------------|-----------|------------|
| `utils/formatacao.py`   | 100%      | Todas as funções são puras. |
| `utils/datas.py`        | 85%       | Único trecho não coberto é `seletor_mes_ano`, um widget Streamlit (não é função pura). |
| `logica/cartoes.py`     | parcial   | Só `calcular_vencimento_parcela` é pura; `salvar_cartao`, `excluir_cartao` e `cartao_tem_vinculos` dependem do Sheets e ficam de fora (candidatas a testes de integração, não unitários). |
| `logica/parcelas.py`    | parcial   | Só `valores_parcelas` é pura; o restante (`salvar_parcela_manual`, `atualizar_parcela`, `baixar_fatura_mes`) idem. |

Funções que ainda dependem do Google Sheets (`salvar_despesa`,
`excluir_cartao`, `baixar_fatura_mes` etc.) não foram testadas aqui —
para cobri-las seria necessário mockar `gspread`/`get_sheet`, o que é
um próximo passo natural (testes de integração com um dublê de
planilha), mas não estão no escopo de "funções puras".

## O que muda para você no dia a dia

- Para adicionar uma nova aba: crie `paginas/nova_aba.py` com uma função
  `render()`, importe em `app.py` e adicione a chamada dentro do `with
  tab_x:`.
- Para mudar uma regra de negócio (ex.: cálculo de parcelas): edite
  apenas o arquivo correspondente em `logica/`, sem tocar em nenhuma
  página.
- Para testar uma função isoladamente (ex.: `valores_parcelas`,
  `calcular_vencimento_parcela`, `mes_ativo_recorrencia`): elas não
  dependem de Streamlit nem do Google Sheets, então podem ser importadas
  e testadas com `pytest` sem precisar rodar o app inteiro.

## Verificações já realizadas

- ✅ Todos os arquivos compilam sem erro de sintaxe (`python3 -m
  py_compile`).
- ✅ O app sobe com `streamlit run app.py` sem erros de importação
  (testado localmente).
- ✅ Nenhuma função cacheada foi definida em mais de um lugar
  (verificado via grep).
