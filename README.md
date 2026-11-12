# Drexier

Plataforma de atendimento ao cliente com IA, com backend Python (FastAPI), frontend responsivo (HTML/CSS/JavaScript) e Supabase PostgreSQL como banco de dados persistente.

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

Para executar com dados persistentes, configure `SUPABASE_URL` e
`SUPABASE_SERVICE_ROLE_KEY` no ambiente do backend e execute `schema.sql` no
SQL Editor do projeto. A chave `service_role` é secreta e nunca deve ser usada
no frontend. O Drexier não usa a chave `anon` para acessar os dados próprios.

SQLite é apenas uma opção explícita para desenvolvimento local: defina
`DATABASE_PATH` para um caminho local ou `ALLOW_LOCAL_DATABASE=true`. Em
produção, não habilite o fallback local: serviços com disco efêmero podem
perder os dados locais ao reiniciar. O arranque não apaga bancos SQLite
legados; a migração para o Supabase precisa ser validada antes de remover
qualquer cópia local. Sem as credenciais Supabase, o backend falha
explicitamente em vez de aparentar salvar dados em outro banco.

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
- `backend/database.py`: conexão com Supabase e SQLite somente para testes/desenvolvimento local.
- `backend/auth.py`: hashing de senha e tokens de sessão.
- `backend/services/`: lógica de negócio, autenticação e respostas do agente.
- `frontend/`: interface responsiva.
- `tests/`: testes iniciais.
- `.env.example`: modelo de variáveis de ambiente.
- `data/`: base SQLite criada automaticamente.

## Emails transacionais de autenticação (Resend)

No cadastro e em cada login, o backend envia um código de confirmação através do Resend. O cadastro/login só prossegue quando o envio é confirmado; configure no `.env`:

- `RESEND_API_KEY`: chave criada em [Resend API Keys](https://resend.com/api-keys).
- `RESEND_FROM_EMAIL`: endereço remetente autorizado no Resend (por exemplo, `Drexier <email@seudominio.com>`). O domínio do endereço precisa estar verificado no Resend.
- `SUPABASE_SERVICE_ROLE_KEY`: chave privada do backend; é necessária para persistir e consumir os desafios de autenticação na tabela `auth_challenges`.

Se alguma variável estiver ausente ou o Resend rejeitar o envio, a interface exibirá uma mensagem e não criará uma sessão sem confirmação. O código está em `backend/services/resend_email.py` e é acionado pelos endpoints `POST /api/auth/signup` e `POST /api/auth/login`.

O remetente de teste `onboarding@resend.dev` só pode entregar mensagens de teste para o email da própria conta Resend. Para enviar códigos a outros usuários, verifique um domínio no Resend e use um remetente desse domínio. Em uma base Supabase já existente, execute `supabase_auth_challenges.sql` no SQL Editor para criar a tabela segura de desafios e a função que valida cada código de forma atômica. Em uma instalação nova, o `schema.sql` já inclui essa estrutura.

## Integração Oficial de E-mail (Google Gmail)

O Drexier atende clientes, tira dúvidas e conduz conversas por e-mail utilizando IA inteligente com suporte a tom de voz, regras do negócio e respostas obrigatórias:

1. **Configuração de Chaves no `.env`**:
   - **Google Gmail (OAuth 2.0)**:
     - `GOOGLE_CLIENT_ID`: ID do cliente OAuth criado no [Google Cloud Console](https://console.cloud.google.com/).
     - `GOOGLE_CLIENT_SECRET`: Segredo do cliente Google.
     - `GOOGLE_REDIRECT_URI`: `http://localhost:8000/api/email/oauth/google/callback`

2. **Fluxo do Utilizador no Painel**:
   - O cliente regista-se no Drexier e entra no painel.
   - Acede a **Configurações > Integração**.
   - Clica no botão **Conectar Google Gmail**.
   - Acede à página oficial do fornecedor e concede as permissões solicitadas (leitura e envio de e-mails em seu nome).
   - O Drexier conclui a ligação de forma 100% segura e exibe o estado **Conectado**.
   - O utilizador pode aceder às abas **Instruções ao agente**, **Respostas obrigatórias** e **Negócio** para instruir a IA sobre a forma de responder às questões, tom de voz para guiar a conversa e regras de suporte.

3. **Recepção e Resposta Automática com IA**:
   - Ao receber e-mails de clientes na caixa de entrada, o Drexier lê a dúvida, localiza o cliente, constrói o histórico da conversa e as diretrizes do negócio.
   - O motor de IA (Google Gemini) formula a resposta inteligente e atenciosa.
   - A resposta é enviada de volta ao e-mail do cliente mantendo a linha de assunto (`Re: ...`) e a conversa no painel.
   - **Controlo de Respostas Automáticas**: O utilizador pode a qualquer momento pausar ou reativar as respostas automáticas da IA tanto na aba **Mensagens** (botão direto `Respostas IA: Ativas / Pausadas`) quanto em **Configurações > Integração**. Quando pausado, as mensagens continuam a ser recebidas e organizadas no painel, mas a IA não envia e-mails automaticamente.
   - **Gestão e Eliminação de Mensagens**: Na aba **Mensagens**, é possível eliminar mensagens individuais (botão `🗑️` em cada balão de mensagem) ou eliminar conversas inteiras com um clique (`Eliminar Conversa`).

## Notas importantes
- A base de dados isola as ligações de e-mail, contactos, mensagens e informações de negócio por utilizador (`user_id`).
- Ao reaplicar o `schema.sql`, tabelas e credenciais de canais legados, além de integrações de e-mail que não sejam Gmail, são removidas; contas, conversas e dados do negócio permanecem. Revogue no fornecedor qualquer token legado já emitido. O script também restringe o acesso às tabelas privadas à `service_role`. Configure backups/PITR no Supabase; nenhum script SQL substitui uma política de backup.
- O Gmail mantém IDs processados no banco para deduplicação após reinícios. Erros do provedor agora são reportados como falha de sincronização e não avançam `last_sync_at`.
- A exclusão da conta em **Configurações > Conta** exige a senha e agenda na Stripe o cancelamento no fim do período pago, sem renovação nem reembolso. Os dados locais só são apagados depois da confirmação Stripe; em caso de falha, a conta permanece para permitir nova tentativa. Exclusões manuais diretamente no SQL Editor não acionam essa integração.
- **Motor de IA (Google Gemini)**: A resposta e condução das conversas é gerida pelo Google Gemini. Obtenha uma chave gratuita em [Google AI Studio](https://aistudio.google.com/app/apikey) e adicione no `.env` em `GEMINI_API_KEY`. Se a chave não for configurada, o agente aciona o fallback local seguro usando as informações cadastradas.
- A confirmação final de venda/agendamento é manual pelo proprietário. A aplicação regista pedidos pendentes e mostra-os no dashboard.
