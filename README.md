# 💰 Controle de Contas — Versão Web

Aplicação de controle financeiro pessoal construída com **Streamlit + Google Sheets**, pronta para ser publicada gratuitamente no **Streamlit Community Cloud**.

---

## ✅ Funcionalidades

- 📊 Dashboard com gráficos (histórico 6 meses, categorias, pagamentos)
- ➖ Lançamento de despesas com suporte a parcelamento
- ➕ Lançamento de receitas
- ☰ Lista de despesas com filtros por mês, pagamento e categoria
- 💳 Controle de cartão de crédito (parcelas, baixa, estorno, fatura)
- 🏦 Extrato de conta corrente com saldo acumulado

---

## 🚀 Como publicar (passo a passo)

### 1. Criar a Planilha no Google Sheets

1. Acesse [sheets.google.com](https://sheets.google.com) e crie uma nova planilha
2. Nomeie-a exatamente: **`Controle de Contas`**
3. As abas (despesas, parcelas, receitas) serão criadas automaticamente pelo app

---

### 2. Criar credenciais no Google Cloud

1. Acesse [console.cloud.google.com](https://console.cloud.google.com)
2. Crie um projeto (ou use um existente)
3. Vá em **APIs e Serviços → Biblioteca** e ative:
   - `Google Sheets API`
   - `Google Drive API`
4. Vá em **APIs e Serviços → Credenciais**
5. Clique em **Criar credenciais → Conta de serviço**
6. Dê um nome e clique em **Criar**
7. Na conta criada, clique em **Chaves → Adicionar chave → JSON**
8. Salve o arquivo JSON baixado

---

### 3. Compartilhar a planilha com a conta de serviço

1. Abra o JSON baixado e copie o valor de `client_email`
2. Na planilha do Google Sheets, clique em **Compartilhar**
3. Cole o `client_email` e dê permissão de **Editor**

---

### 4. Configurar o projeto

```
controle_contas_web/
├── app.py
├── requirements.txt
└── .streamlit/
    └── secrets.toml       ← criar este arquivo
```

Crie o arquivo `.streamlit/secrets.toml` baseado no arquivo `secrets.toml.example`:

```toml
SHEET_NAME = "Controle de Contas"

[gcp_service_account]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----\n"
client_email = "...@....iam.gserviceaccount.com"
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."
```

> ⚠️ **NUNCA** adicione `secrets.toml` ao GitHub. Adicione ao `.gitignore`.

---

### 5. Testar localmente (opcional)

```bash
pip install -r requirements.txt
streamlit run app.py
```

---

### 6. Publicar no Streamlit Community Cloud

1. Suba o projeto para um repositório **GitHub** (sem o `secrets.toml`)
2. Acesse [share.streamlit.io](https://share.streamlit.io)
3. Faça login com sua conta Google
4. Clique em **New app**
5. Selecione seu repositório, branch `main` e arquivo `app.py`
6. Clique em **Advanced settings → Secrets** e cole o conteúdo do `secrets.toml`
7. Clique em **Deploy!**

Em poucos minutos você terá um link público como:
`https://seu-app.streamlit.app`

---

## 📁 .gitignore recomendado

```
.streamlit/secrets.toml
__pycache__/
*.pyc
.env
```

---

## 🛠 Dependências

| Biblioteca | Uso |
|---|---|
| streamlit | Interface web |
| gspread | Acesso ao Google Sheets |
| google-auth | Autenticação Google |
| pandas | Manipulação de dados |
| plotly | Gráficos interativos |
