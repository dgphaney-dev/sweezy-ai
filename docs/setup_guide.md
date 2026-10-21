# Guia de Configuração e Instalação - ProspectAI

Este guia detalha o passo a passo completo para preparar o ambiente de desenvolvimento, configurar as chaves de API necessárias (Google Cloud e OpenAI), inicializar o banco de dados e executar o **ProspectAI** no Windows (PowerShell/CMD) ou Linux/macOS.

---

## 1. Pré-requisitos do Sistema

Antes de iniciar, certifique-se de ter os seguintes componentes instalados na sua máquina:

| Ferramenta | Versão Mínima | Verificação no Terminal | Observação |
| :--- | :--- | :--- | :--- |
| **Python** | 3.12+ | `python --version` ou `py -3.12 --version` | Suporte nativo a tipagem e performance assíncrona. |
| **pip** | 24.0+ | `python -m pip --version` | Gerenciador de pacotes padrão do Python. |
| **Git** | 2.40+ | `git --version` | Controle de versão e clonagem do repositório. |

> [!IMPORTANT]
> No Windows, durante a instalação do Python pelo instalador oficial (`python.org`), certifique-se de marcar a opção **"Add python.exe to PATH"** e selecionar **"Disable path length limit"** na etapa final.

---

## 2. Instalação Passo a Passo

Abra o terminal (PowerShell, Prompt de Comando ou Bash) e siga as etapas abaixo.

### 2.1. Clonar o Repositório
```bash
# Clone o repositório oficial
git clone https://github.com/seu-usuario/prospect-ai.git

# Acesse o diretório do projeto
cd prospect-ai
```
Se o projeto já estiver no diretório de trabalho local:
```powershell
Set-Location -Path "c:\Users\PICHAU\Documents\agente_ia"
```

### 2.2. Criar o Ambiente Virtual (venv)
É fundamental isolar as dependências do projeto para evitar conflitos com outros pacotes do sistema:

```bash
python -m venv venv
```

### 2.3. Ativar o Ambiente Virtual
Ative o ambiente virtual conforme o seu sistema operacional e shell:

- **Windows (PowerShell / Prompt de Comando)**:
  ```powershell
  .\venv\Scripts\activate
  ```
  *(Nota: No PowerShell você também pode chamar `.\venv\Scripts\Activate.ps1`, ou no CMD tradicional `.\venv\Scripts\activate.bat`)*

- **Linux / macOS (Bash / Zsh)**:
  ```bash
  source venv/bin/activate
  ```

> [!TIP]
> Caso o PowerShell bloqueie a execução de scripts com o erro `PSSecurityException` ou `execution of scripts is disabled on this system`, execute o comando abaixo no PowerShell antes de ativar:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

### 2.4. Instalar as Dependências
Com o ambiente ativado (o prefixo `(venv)` aparecerá no início do prompt):

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

## 3. Configuração do Google Cloud Platform (Google Places API)

O **ProspectAI** utiliza a **Places API (New)** da Google para localização geográfica via varredura por quadrícula (grid search).

### Passo 3.1: Criar ou Selecionar um Projeto no Google Cloud
1. Acesse o [Google Cloud Console](https://console.cloud.google.com/).
2. Faça login com sua conta Google.
3. No topo da tela, clique no seletor de projetos e clique no botão **"Novo Projeto"** (New Project).
4. Defina o nome do projeto (exemplo: `ProspectAI-Production`) e clique em **Criar**.

### Passo 3.2: Ativar a Places API (New)
1. No menu lateral esquerdo, navegue até **APIs e Serviços** > **Biblioteca** (Library).
2. Na barra de pesquisa, busque por: `Places API (New)`.
3. Clique sobre o card **"Places API (New)"**.
4. Clique no botão azul **"Ativar"** (Enable).

> [!WARNING]
> Certifique-se de ativar especificamente a **Places API (New)** e não a versão legada (*Places API Legacy*). A versão *New* conta com suporte a `FieldMask`, essencial para reduzir o tráfego de rede e os custos de faturamento em até 70%.

### Passo 3.3: Criar a Chave de API (API Key)
1. No menu lateral esquerdo, vá em **APIs e Serviços** > **Credenciais** (Credentials).
2. Clique no botão **"+ CRIAR CREDENCIAIS"** no topo da página e selecione **"Chave de API"** (API key).
3. Uma janela modal exibirá sua nova chave gerada (com prefixo `AIzaSy...`).
4. Copie a chave para a área de transferência.

### Passo 3.4: Restringir a Chave de API (Segurança Obrigatória)
1. Na janela de confirmação da chave criada (ou na lista de chaves de API), clique em **"Editar chave de API"** (ícone de lápis).
2. Na seção **"Restrições de API"** (API restrictions):
   - Selecione a opção **"Restringir chave"** (Restrict key).
   - No menu suspenso de APIs, marque **exclusivamente**:
     - `Places API (New)`
3. Na seção superior de nome, renomeie para `ProspectAI-Places-Key`.
4. Clique em **Salvar** (Save) no rodapé da página.

---

## 4. Configuração da OpenAI (LLM & Instructor)

O módulo de qualificação e inteligência comercial do ProspectAI é alimentado pelo modelo `gpt-4o-mini` da OpenAI em conjunto com a biblioteca `instructor` para extração estruturada de dados.

### Passo 4.1: Criar Conta e Acessar a Plataforma
1. Acesse o portal para desenvolvedores da OpenAI: [https://platform.openai.com/](https://platform.openai.com/).
2. Faça login ou crie uma conta.

### Passo 4.2: Adicionar Créditos Pré-pagos
1. No menu lateral esquerdo, acesse **Settings** > **Billing** (Faturamento).
2. Clique em **"Add payment details"** e cadastre um cartão de crédito internacional.
3. Clique em **"Add funds"** e adicione o saldo inicial recomendado de **$ 5,00 USD** a **$ 10,00 USD**.

> [!NOTE]
> O modelo `gpt-4o-mini` possui custo extremamente reduzido. A qualificação de cada lead consome em média **$ 0,00015 USD**, de modo que $ 5,00 USD de saldo permitem analisar mais de 25.000 estabelecimentos comerciais.

### Passo 4.3: Gerar a Chave de API
1. No menu lateral esquerdo, acesse **API Keys**.
2. Clique no botão **"+ Create new secret key"**.
3. No campo *Name*, digite `ProspectAI-Agent`.
4. Deixe as permissões como *Default* (All permissions) ou limite a *Model capabilities*.
5. Clique em **Create secret key**.
6. **Copie imediatamente** a chave exibida (ela possui o prefixo `sk-proj-...`), pois ela não será exibida novamente após fechar a janela.

---

## 5. Configuração das Variáveis de Ambiente (`.env`)

Na raiz do projeto existe um arquivo de modelo chamado `.env.example`.

### 5.1. Copiar o Modelo para `.env`
No terminal, faça uma cópia do arquivo de exemplo:

- **Windows (PowerShell)**:
  ```powershell
  Copy-Item -Path .env.example -Destination .env
  ```
- **Linux / macOS / CMD**:
  ```bash
  cp .env.example .env
  ```

Abra o arquivo `.env` gerado e preencha com suas credenciais:

```ini
# Google Places API
GOOGLE_API_KEY=your_google_api_key_here

# OpenAI API  
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o-mini

# Database
DATABASE_URL=sqlite:///./data/prospect_ai.db

# Scan defaults
DEFAULT_SCAN_RADIUS_KM=5
DEFAULT_GRID_STEP_KM=1.5
MAX_RESULTS_PER_SEARCH=20

# Rate limits
GOOGLE_REQUESTS_PER_SECOND=5
BRASILAPI_REQUESTS_PER_SECOND=2
CNPJWS_REQUESTS_PER_MINUTE=3

# LLM
LLM_MAX_CONCURRENT=10
LLM_TEMPERATURE=0.3

# App
APP_TITLE=ProspectAI
APP_THEME=dark
APP_PORT=8550
```

### 5.2. Explicação Detalhada de Cada Variável

| Variável | Tipo | Valor Padrão | Descrição e Finalidade |
| :--- | :--- | :--- | :--- |
| `GOOGLE_API_KEY` | `str` | *(Obrigatório)* | Chave da Google Cloud restrita à Places API (New) para descoberta de comércios. |
| `OPENAI_API_KEY` | `str` | *(Obrigatório)* | Chave secreta da OpenAI para raciocínio e qualificação de oportunidade de POS. |
| `OPENAI_MODEL` | `str` | `gpt-4o-mini` | Modelo LLM utilizado pelo `instructor` para gerar o schema `LeadQualification`. |
| `DATABASE_URL` | `str` | `sqlite:///./data/prospect_ai.db` | URI de conexão SQLAlchemy. O diretório `./data` e o arquivo SQLite são gerados automaticamente. |
| `DEFAULT_SCAN_RADIUS_KM` | `float` | `5` | Raio padrão (em km) a partir do ponto central selecionado no mapa para descoberta. |
| `DEFAULT_GRID_STEP_KM` | `float` | `1.5` | Espaçamento da grade geográfica para cobrir grandes raios sem deixar pontos cegos. |
| `MAX_RESULTS_PER_SEARCH` | `int` | `20` | Quantidade máxima de estabelecimentos coletados por cada quadrícula do grid. |
| `GOOGLE_REQUESTS_PER_SECOND` | `int` | `5` | Controle de vazão (throttling) para não exceder limites de concorrência do Google. |
| `BRASILAPI_REQUESTS_PER_SECOND` | `int` | `2` | Limite de consultas simultâneas na BrasilAPI para evitar bloqueio de IP. |
| `CNPJWS_REQUESTS_PER_MINUTE` | `int` | `3` | Limite no plano gratuito da CNPJ.ws (fallback quando a BrasilAPI falhar). |
| `LLM_MAX_CONCURRENT` | `int` | `10` | Semáforo assíncrono para limitar chamadas concorrentes à OpenAI. |
| `LLM_TEMPERATURE` | `float` | `0.3` | Criatividade da IA. Valores baixos (0.2 - 0.4) garantem maior precisão e aderência estrutural aos campos Pydantic. |
| `APP_TITLE` | `str` | `ProspectAI` | Título exibido na janela principal do aplicativo Flet. |
| `APP_THEME` | `str` | `dark` | Tema visual da aplicação (`dark` ou `light`). |
| `APP_PORT` | `int` | `8550` | Porta local utilizada caso o Flet seja executado no modo Web/Navegador. |

---

## 6. Primeira Execução e Validação

Com as dependências instaladas e o arquivo `.env` preenchido, você pode iniciar o **ProspectAI**.

### 6.1. Iniciar a Aplicação
No diretório raiz do projeto com o venv ativado:

```powershell
python -m app.main
```

> [!NOTE]
> Durante a inicialização automática, o sistema realiza:
> 1. Carregamento e validação das variáveis do `.env`.
> 2. Criação do diretório `./data/` e inicialização das tabelas no SQLite.
> 3. Abertura da interface gráfica desktop moderna em Flet.

### 6.2. Como Executar uma Varredura de Teste (Test Scan)
1. Na barra lateral ou topo do aplicativo, clique na aba **"Nova Varredura"** (New Scan).
2. Configure uma região de teste com raio reduzido para validação rápida:
   - **Região/Cidade**: `Pinheiros, São Paulo - SP`
   - **Latitude Central**: `-23.5617`
   - **Longitude Central**: `-46.6925`
   - **Raio (km)**: `1.0` (recomendado para teste rápido de 1 quadrícula)
   - **Segmento**: Marque `RESTAURANTE` e `PADARIA`.
3. Clique no botão **"Iniciar Varredura"**.

### 6.3. Como Verificar o Funcionamento
- **Logs no Terminal (Rich)**:
  - O terminal exibirá mensagens formatadas indicando a descoberta no Google Places, a consulta de CNPJ na BrasilAPI, a raspagem heurística da web e a qualificação no GPT-4o-mini.
- **Painel Flet**:
  - A tabela de leads será populada em tempo real.
  - Cada lead qualificado exibirá a tag de probabilidade (`HIGH`, `MEDIUM` ou `LOW`), o gancho de abordagem gerado pela IA e um botão de ação rápida para iniciar contato via **WhatsApp** com o texto pré-formatado.

---

## 7. Solução de Problemas Comuns (Troubleshooting)

### 1. `REQUEST_DENIED` ou `google.api_core.exceptions.PermissionDenied`
- **Sintoma**: As buscas por locais falham com erro de autorização.
- **Causa**: A chave de API do Google não foi ativada para o serviço correto, ou o faturamento (Billing) não está vinculado ao projeto Google Cloud.
- **Solução**:
  1. Acesse o Google Cloud Console > Faturamento e confirme que uma conta de faturamento válida está associada ao projeto (o Google concede $ 200 USD de cota mensal gratuita).
  2. Verifique se o serviço ativado é a **Places API (New)**.
  3. Verifique se as restrições de API da chave incluem a Places API (New).

### 2. `openai.RateLimitError: 429 You exceeded your current quota`
- **Sintoma**: O pipeline trava ou falha na etapa de qualificação de leads.
- **Causa**: Saldo de créditos pré-pagos zerado na conta da OpenAI.
- **Solução**:
  1. Acesse [platform.openai.com/settings/billing](https://platform.openai.com/settings/billing).
  2. Adicione pelo menos $ 5,00 USD em créditos.
  3. Certifique-se de que a chave em `.env` pertence ao projeto/organização com créditos ativos.

### 3. `sqlite3.OperationalError: database is locked`
- **Sintoma**: Erro de escrita no SQLite durante inserções concorrentes.
- **Causa**: Alguma ferramenta externa (DBeaver, DB Browser for SQLite) abriu o arquivo `prospect_ai.db` com lock exclusivo de transação.
- **Solução**:
  1. Feche softwares externos de inspeção de banco enquanto o scan estiver em execução.
  2. No ProspectAI, a engine do SQLAlchemy já é configurada com `timeout=30`, mas conexões externas exclusivas impedem gravação.

### 4. Falha na Inicialização da Janela Flet (Tela Preta / GPU)
- **Sintoma**: A janela do Flet fecha imediatamente ou fica em tela preta no Windows.
- **Causa**: Incompatibilidade ou driver desatualizado de aceleração gráfica por hardware.
- **Solução**:
  1. Execute a aplicação no modo navegador Web com:
     ```powershell
     python -m app.main --web
     ```
  2. Ou ative a renderização de fallback por software:
     ```powershell
     $env:FLET_FORCE_WEBVIEW = "true"
     python -m app.main
     ```

### 5. `ModuleNotFoundError: No module named 'app'`
- **Sintoma**: Python não localiza o pacote da aplicação ao executar o comando.
- **Causa**: Comando executado a partir de uma subpasta em vez da raiz do repositório.
- **Solução**:
  1. Navegue para a pasta raiz onde está o arquivo `pyproject.toml` (`c:\Users\PICHAU\Documents\agente_ia`).
  2. Execute utilizando a flag de módulo: `python -m app.main`.
  3. Caso persista, declare a variável de ambiente:
     ```powershell
     $env:PYTHONPATH = "."
     python -m app.main
     ```
