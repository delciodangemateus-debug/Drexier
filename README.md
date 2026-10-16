# Drexier

Plataforma base de atendimento ao cliente com IA, com backend Python (FastAPI), frontend responsivo (HTML/CSS/JavaScript) e base de dados SQLite.

## Requisitos
- Python 3.11+
- pip

## Instalação e Execução

### 1. Dependências do Python
```bash
pip install -r requirements.txt
```

### 2. Dependências do Frontend (Node.js / npm)
```bash
npm install
```

### 3. Configuração de Ambiente
Copie `.env.example` para `.env` (já criado nesta configuração):
```bash
cp .env.example .env
```

### 4. Como Executar

Abra **dois terminais**:

- **Terminal 1 (Backend):**
  ```bash
  npm run server
  ```
  O backend FastAPI iniciará em `http://127.0.0.1:8000`.

- **Terminal 2 (Frontend):**
  ```bash
  npm run dev
  ```
  O servidor de desenvolvimento Vite iniciará em `http://localhost:5173`. As chamadas à API são automaticamente redirecionadas para o backend via proxy.

## Estrutura
- `backend/main.py`: rotas HTTP e arranque da aplicação.
- `backend/database.py`: conexão SQLite e criação das tabelas vazias.
- `backend/auth.py`: hashing de senha e tokens de sessão.
- `backend/services/`: lógica de negócio, autenticação e respostas do agente.
- `frontend/`: interface responsiva.
- `tests/`: testes iniciais.
- `.env.example`: modelo de variáveis de ambiente.
- `data/`: base SQLite criada automaticamente.

## Notas importantes
- A base de dados inicia sem clientes, mensagens, produtos, serviços, campanhas ou relatórios de exemplo.
- O dashboard e os relatórios mostram estados vazios até serem inseridos dados reais.
- O fluxo de mensagens é preparado para receber mensagens e usar a base de informações do negócio. A integração com WhatsApp está intencionalmente vazia, conforme solicitado.
- **Motor de IA (Google Gemini)**: A resposta e condução das conversas é gerida pelo Google Gemini (`gemini-1.5-flash`). Obtenha uma chave gratuita em [Google AI Studio](https://aistudio.google.com/app/apikey) e adicione no `.env` em `GEMINI_API_KEY`. Se a chave não for configurada, o agente aciona o fallback local seguro usando as informações cadastradas.
- A confirmação final de venda/agendamento é manual pelo proprietário. A aplicação regista pedidos pendentes e mostra-os no dashboard.
- Antes de produção: usar HTTPS, configurar uma chave `SECRET_KEY` forte, configurar CORS/domínio, backups, limites de pedidos, política de privacidade e um provedor de e-mail/recuperação de senha. Este projeto é uma base funcional, não uma implantação de produção auditada.
