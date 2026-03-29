# 📊 Twilio Dashboard Extractor

Extrai dados de uso diário de 8 contas Twilio e salva CSVs automaticamente no repositório via GitHub Actions a cada 15 minutos.

---

## 📁 Estrutura de Pastas

```
twilio-dashboard/               ← raiz do repositório
├── .github/
│   └── workflows/
│       └── main.yml            ← automação GitHub Actions
├── .gitignore                  ← protege o .env de ser commitado
├── .env                        ← suas credenciais LOCAIS (não vai pro GitHub)
├── extratorv2.py               ← script principal
├── requirements.txt            ← dependências Python
├── conf_total_marco.csv        ← gerado automaticamente
└── conf_detalhado_marco.csv    ← gerado automaticamente
```

---

## ⚙️ Guia de Configuração — Passo a Passo

### 1. Crie o repositório no GitHub

1. Acesse [github.com/new](https://github.com/new)
2. Dê um nome (ex: `twilio-dashboard`)
3. Deixe **Public** ou **Private** (ambos funcionam)
4. Clique em **Create repository**

---

### 2. Suba os arquivos para o GitHub

No terminal, dentro da pasta do projeto:

```bash
git init
git add .
git commit -m "feat: setup inicial do extrator Twilio"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/twilio-dashboard.git
git push -u origin main
```

---

### 3. Configure os Secrets no GitHub

Os Secrets substituem o arquivo `.env` no ambiente do GitHub Actions.

**Caminho:** `Seu repositório → Settings → Secrets and variables → Actions → New repository secret`

Adicione os seguintes secrets, um por um:

| Nome do Secret | Valor |
|---|---|
| `RECUPERACAO_NS_SID` | Account SID da conta NS |
| `RECUPERACAO_NS_TOKEN` | Auth Token da conta NS |
| `BROADCAST_JOAO_SID` | Account SID da conta Joao |
| `BROADCAST_JOAO_TOKEN` | Auth Token da conta Joao |
| `BROADCAST_BERNARDO_SID` | Account SID da conta Bernardo |
| `BROADCAST_BERNARDO_TOKEN` | Auth Token da conta Bernardo |
| `BROADCAST_RAFA_SID` | Account SID da conta Rafa |
| `BROADCAST_RAFA_TOKEN` | Auth Token da conta Rafa |
| `STANDBY_HAVEN_SID` | Account SID da conta Havenmove |
| `STANDBY_HAVEN_TOKEN` | Auth Token da conta Havenmove |
| `STANDBY_REHABLEAF_SID` | Account SID da conta Rehableaf |
| `STANDBY_REHABLEAF_TOKEN` | Auth Token da conta Rehableaf |
| `STANDBY_RICHARD_SID` | Account SID da conta Richard |
| `STANDBY_RICHARD_TOKEN` | Auth Token da conta Richard |
| `STANDBY_NATUREMOVE_SID` | Account SID da conta Naturemove |
| `STANDBY_NATUREMOVE_TOKEN` | Auth Token da conta Naturemove |

> 💡 Os valores de SID e Token ficam no painel da Twilio em: **Console → Account Info**

---

### 4. Ative permissões de escrita no repositório

Sem isso, o bot não consegue commitar os CSVs.

**Caminho:** `Settings → Actions → General → Workflow permissions`

- Selecione **"Read and write permissions"**
- Marque **"Allow GitHub Actions to create and approve pull requests"**
- Clique em **Save**

---

### 5. Teste manualmente

Antes de esperar o cron rodar:

1. Vá em `Actions` no menu do repositório
2. Clique no workflow **"Extração Twilio - A cada 15 minutos"**
3. Clique em **"Run workflow"** → **"Run workflow"**
4. Acompanhe os logs em tempo real

Se tudo der certo, os arquivos `conf_total_marco.csv` e `conf_detalhado_marco.csv` aparecerão/atualizarão no repositório automaticamente.

---

### 6. Conecte ao Lovable

No painel do Lovable, aponte o fetch dos dados para as URLs raw dos CSVs:

```
https://raw.githubusercontent.com/SEU_USUARIO/twilio-dashboard/main/conf_total_marco.csv
https://raw.githubusercontent.com/SEU_USUARIO/twilio-dashboard/main/conf_detalhado_marco.csv
```

> Substitua `SEU_USUARIO` pelo seu usuário do GitHub.

---

## 🔧 Otimizações aplicadas no script

- **`requests.Session`** — reutiliza conexões TCP entre chamadas, reduzindo overhead de ~15-30% no tempo total
- **Datas dinâmicas** — `START_DATE` é sempre o primeiro dia do mês corrente, eliminando a necessidade de atualizar o script todo mês
- **Cache de pip** — o workflow usa `cache: 'pip'` para não baixar dependências do zero em cada execução

---

## ⚠️ Aviso sobre cron do GitHub Actions

O GitHub Actions tem uma precisão de ~1-2 minutos de atraso no disparo do cron, e em horários de alta demanda pode atrasar até 5 minutos. Isso é normal e esperado.
