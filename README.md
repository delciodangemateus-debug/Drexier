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

## Integração Oficial de E-mail (Google Gmail & Microsoft Outlook)

O Drexier atende clientes, tira dúvidas e conduz conversas **exclusivamente por e-mail** utilizando IA inteligente com suporte a tom de voz, regras do negócio e respostas obrigatórias:

1. **Configuração de Chaves no `.env`**:
   - **Google Gmail (OAuth 2.0)**:
     - `GOOGLE_CLIENT_ID`: ID do cliente OAuth criado no [Google Cloud Console](https://console.cloud.google.com/).
     - `GOOGLE_CLIENT_SECRET`: Segredo do cliente Google.
     - `GOOGLE_REDIRECT_URI`: `http://localhost:8000/api/email/oauth/google/callback`
   - **Microsoft Outlook (Microsoft Graph)**:
     - `MICROSOFT_CLIENT_ID`: ID da aplicação criada no [Azure Portal](https://portal.azure.com/).
     - `MICROSOFT_CLIENT_SECRET`: Segredo da aplicação.
     - `MICROSOFT_REDIRECT_URI`: `http://localhost:8000/api/email/oauth/microsoft/callback`
     - `MICROSOFT_TENANT_ID`: `common`
   - **Conexão Direta (Opcional - SMTP / IMAP)**:
     - `EMAIL_SMTP_HOST`, `EMAIL_SMTP_PORT`, `EMAIL_SMTP_USER`, `EMAIL_SMTP_PASSWORD`

2. **Fluxo do Utilizador no Painel**:
   - O cliente regista-se no Drexier e entra no painel.
   - Acede a **Configurações > Integração**.
   - Clica no botão **Conectar Google Gmail** ou **Conectar Microsoft Outlook**.
   - Acede à página oficial do fornecedor e concede as permissões solicitadas (leitura e envio de e-mails em seu nome).
   - O Drexier conclui a ligação de forma 100% segura e exibe o estado **Conectado**.
   - O utilizador pode aceder às abas **Instruções ao agente**, **Respostas obrigatórias** e **Negócio** para instruir a IA sobre a forma de responder às questões, tom de voz para guiar a conversa e regras de suporte.

3. **Recepção e Resposta Automática com IA**:
   - Ao receber e-mails de clientes na caixa de entrada, o Drexier lê a dúvida, localiza o cliente, constrói o histórico da conversa e as diretrizes do negócio.
   - O motor de IA (Google Gemini) formula a resposta inteligente e atenciosa.
   - A resposta é enviada de volta ao e-mail do cliente mantendo a linha de assunto (`Re: ...`) e a conversa no painel.
   - **Controlo de Respostas Automáticas**: O utilizador pode a qualquer momento pausar ou reativar as respostas automáticas da IA tanto na aba **Mensagens** (botão direto `Respostas IA: Ativas / Pausadas`) quanto em **Configurações > Integração**. Quando pausado, as mensagens continuam a ser recebidas e organizadas no painel, mas a IA não envia e-mails automaticamente.
   - **Gestão e Eliminação de Mensagens**: Na aba **Mensagens**, é possível eliminar mensagens individuais (botão `🗑️` em cada balão de mensagem) ou eliminar conversas inteiras com um clique (`Eliminar Conversa`).

## Integração WhatsApp (Removida da Interface do Cliente)
- A opção de integração com WhatsApp foi **completamente eliminada da interface do cliente**. O atendimento oficial e ativo da plataforma é focado exclusivamente em e-mail (Gmail & Outlook). O backend mantém suporte legado e webhooks de contingência.

## Notas importantes
- A base de dados isola as ligações de e-mail, contactos, mensagens e informações de negócio por utilizador (`user_id`).
- **Motor de IA (Google Gemini)**: A resposta e condução das conversas é gerida pelo Google Gemini. Obtenha uma chave gratuita em [Google AI Studio](https://aistudio.google.com/app/apikey) e adicione no `.env` em `GEMINI_API_KEY`. Se a chave não for configurada, o agente aciona o fallback local seguro usando as informações cadastradas.
- A confirmação final de venda/agendamento é manual pelo proprietário. A aplicação regista pedidos pendentes e mostra-os no dashboard.
