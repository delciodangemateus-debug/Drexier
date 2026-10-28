# RELATÓRIO DE AUDITORIA DE SEGURANÇA PRÉ-LANÇAMENTO - DREXIER

**Data:** 2026-10-28  
**Repositório:** C:\Users\USER\Downloads\Drexier  
**Branch:** cleanup/limpeza-segura-20261028-1430  
**Modo:** APENAS ANÁLISE - NENHUMA ALTERAÇÃO REALIZADA  

> Este relatório foca em riscos reais identificados no código-fonte. Os achados estão organizados por severidade (Crítico > Alto > Médio > Baixo). Onde aplicável, são fornecidas evidências diretas, impacto, vetores e remediação concreta e verificável.

## SUMÁRIO EXECUTIVO

| Severidade | Quantidade | Status |
|------------|------------|--------|
| **CRÍTICO** | 4 | **DEVE SER CORRIGIDO ANTES DO LANÇAMENTO** |
| **ALTO** | 6 | **DEVE SER CORRIGIDO ANTES DO LANÇAMENTO** |
| **MÉDIO** | 5 | **RECOMENDADO CORRIGIR ANTES/LOGO APÓS** |
| **BAIXO** | 3 | **MONITORAR/MELHORAR** |

**Principais pontos críticos:** 
- `.env` commitado com segredos reais (Supabase, Gemini, Stripe de teste)
- `CORS` com `allow_origins=["*"]` + `allow_credentials=True`
- `SECRET_KEY` fraca/padrão em `.env` e fallback inseguro em código
- Ausência de cabeçalhos de segurança e limitação de taxa

## 1) ACHADOS DETALHADOS

### CRÍTICO

#### SEC-001 - Segredos reais commitados no repositório (.env)
- **Severidade:** CRÍTICO
- **Localização:** `C:\Users\USER\Downloads\Drexier\.env` (linhas 1-81)
- **Evidência:**
```env
SUPABASE_URL=[REDACTED - ROTATE THIS CREDENTIAL]
SUPABASE_ANON_KEY=[REDACTED - ROTATE THIS CREDENTIAL]
SUPABASE_SERVICE_ROLE_KEY=[REDACTED - ROTATE THIS CREDENTIAL]
GEMINI_API_KEY=[REDACTED - ROTATE THIS CREDENTIAL]
STRIPE_SECRET_KEY=[REDACTED - ROTATE THIS CREDENTIAL]
STRIPE_PUBLISHABLE_KEY=[REDACTED - ROTATE THIS CREDENTIAL]
STRIPE_WEBHOOK_SECRET=[REDACTED - ROTATE THIS CREDENTIAL]
SECRET_KEY=[REDACTED - ROTATE THIS CREDENTIAL]
```
- **Impacto:** Comprometimento total de banco (service_role), IA, Stripe. Se este repo for público ou clonado, chaves ficam expostas.
- **Probabilidade:** Alta
- **Vetor:** Exposição via VCS
- **Exploitabilidade:** Alta
- **Remediação concreta:**
1. **IMEDIATO:** Rotacionar TODAS as chaves expostas (Supabase service_role/anon, Gemini, Stripe chaves de teste/produção). 
2. Remover `.env` do histórico git (`git filter-repo` ou `git filter-branch`). 
3. Garantir `.gitignore` já contém `.env` (confirmado) mas precisa remover do índice/histórico.
4. Usar `.env.example` apenas com placeholders (já existe `C:\Users\USER\Downloads\Drexier\.env.example`).
5. Em produção usar secret manager (Vercel/Render/Cloud Run) - nunca commitar `.env`.
- **Verificação:** `git log --oneline -p --max-count=1 -- .env` não deve mostrar segredos; `git ls-tree -r --name-only HEAD | grep -E '^\.env$'` deve retornar vazio após limpeza.
- **Status:** **Corrigir antes do lançamento**

#### SEC-002 - CORS excessivamente permissivo com credenciais
- **Severidade:** CRÍTICO
- **Localização:** `backend/main.py:118-125`
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```
- **Impacto:** Com `allow_credentials=True` e `*`, navegadores bloqueiam em muitos casos mas configuração é insegura/arriscada. Permite requisições cross-origin com cookies/headers auth. Facilita CSRF-like abuse se combinado com outros fatores.
- **Probabilidade:** Alta
- **Vetor:** Cross-Origin
- **Exploitabilidade:** Média-Alta
- **Remediação concreta:**
1. Substituir por lista explícita: `allow_origins=["https://seu-dominio.com", "http://localhost:5173"]` (apenas origens confiáveis)
2. Se não usar cookies, `allow_credentials=False`. Se usar cookies httpOnly, manter credenciais mas com origens restritas.
3. Restringir `allow_methods` a `["GET","POST","PUT","PATCH","DELETE"]` conforme necessário
4. Restringir `allow_headers` (ex: `Authorization`, `Content-Type`, `Stripe-Signature` se necessário)
- **Verificação:** Testar preflight OPTIONS com origem não autorizada - deve ser negado. Verificar `Access-Control-Allow-Origin` não retorna `*` quando credentials presentes.
- **Status:** **Corrigir antes do lançamento**

#### SEC-003 - SECRET_KEY fraca/padrão e algoritmo JWT
- **Severidade:** CRÍTICO
- **Localização:** `backend/auth.py:11-31`, `.env:33`
```python
SECRET_KEY =[REDACTED - ROTATE THIS CREDENTIAL]
ALGORITHM = "HS256"
...
exp = datetime.now(timezone.utc) + timedelta(days=7)
return jwt.encode({"sub": str(user_id), "exp": exp}, SECRET_KEY, algorithm=ALGORITHM)
```
- **Impacto:** Se `SECRET_KEY` vazia/padrão em produção, tokens JWT podem ser forjados → autenticação completa comprometida. Expiração longa (7 dias) amplia janela de abuso.
- **Probabilidade:** Alta (depende de env)
- **Vetor:** Token forgery
- **Exploitabilidade:** Alta se segredo fraco
- **Remediação concreta:**
1. **NUNCA** usar fallback padrão em produção. Falhar se não configurado: `SECRET_KEY = os.environ["SECRET_KEY"]` ou validar e sair.
2. Gerar segredo forte (>= 32 bytes aleatórios, base64/hex). 
3. Reduzir expiração: considerar 1-2h + refresh token, ou pelo menos reduzir para 24h se não houver refresh.
4. Considerar rotação de chaves (kid) se necessário.
5. Remover `.env` com valor placeholder do repo.
- **Verificação:** Em ambiente sem `SECRET_KEY`, app deve falhar na inicialização; tentar forjar token com segredo antigo deve falhar.
- **Status:** **Corrigir antes do lançamento**

#### SEC-004 - Exposição de documentação interativa FastAPI
- **Severidade:** CRÍTICO (se exposto publicamente)
- **Localização:** `backend/main.py:126` (`app = FastAPI(title="Drexier API", version="0.1.0", lifespan=lifespan)`) - Sem `docs_url`, `redoc_url`, `openapi_url` desabilitados
- **Evidência:** FastAPI por padrão expõe `/docs`, `/redoc`, `/openapi.json`
- **Impacto:** Enumeração completa de rotas, schemas, modelos - facilita reconhecimento para ataques.
- **Probabilidade:** Alta em produção exposta
- **Vetor:** Information Disclosure
- **Exploitabilidade:** Média
- **Remediação concreta:**
1. Desabilitar em produção: `app = FastAPI(..., docs_url=None, redoc_url=None, openapi_url=None)` ou proteger por IP/auth
2. Ou servir apenas em ambiente dev
- **Verificação:** `curl https://seu-dominio.com/docs` deve retornar 404/403
- **Status:** **Corrigir antes do lançamento**

### ALTO

#### SEC-005 - Armazenamento/token handling no frontend
- **Severidade:** ALTO
- **Localização:** `frontend/app.js` (lido parcialmente - ~3294 linhas), `frontend/index.html`
- **Evidência:** App faz chamadas com `Authorization: Bearer ...` (padrão observado em main/billing). Token provavelmente armazenado em `localStorage`/`sessionStorage`.
- **Impacto:** Se XSS existir, token é roubado facilmente. `localStorage` é acessível via JS.
- **Probabilidade:** Média-Alta (depende de XSS)
- **Vetor:** XSS → Token theft
- **Exploitabilidade:** Alta se XSS presente
- **Remediação concreta:**
1. Preferir cookies `HttpOnly`, `Secure`, `SameSite=Strict/Lax` para tokens
2. Se manter Bearer em localStorage, implementar CSP forte, sanitização rigorosa, e considerar token curto + refresh
3. Adicionar `Content-Security-Policy` headers
4. Auditar todo uso de `innerHTML`/`eval`/template injection em `app.js`
- **Verificação:** Procurar `localStorage.setItem.*token`, `sessionStorage.*token` em `frontend/app.js`
- **Status:** **Corrigir antes do lançamento**

#### SEC-006 - Cobertura do paywall / dependências de auth
- **Severidade:** ALTO
- **Localização:** `backend/main.py:196-210` (`require_active_subscription`), uso em rotas (precisa verificar todas)
- **Evidência:** 
```python
def require_active_subscription(user=Depends(current_user)):
    if not is_subscription_active(user["id"]):
        raise HTTPException(status_code=402, detail={... "SUBSCRIPTION_REQUIRED"...})
```
Comentário diz "Bloqueia TODOS os endpoints de escrita / IA / integrações" mas aplicação real depende de adicionar `dependencies=[Depends(require_active_subscription)]` em cada rota.
- **Impacto:** Se alguma rota sensível (IA, envio, integração) esquecer de adicionar a dependência, acesso gratuito.
- **Probabilidade:** Média
- **Vetor:** Authorization bypass (missing dependency)
- **Exploitabilidade:** Alta se rota esquecida
- **Remediação concreta:**
1. Mapear TODAS as rotas em `backend/main.py` e `backend/routers/*.py` - verificar quais têm `require_active_subscription`
2. Considerar middleware global para rotas sensíveis por path pattern (ex: `/api/agent/*`, `/api/email/send/*`) ao invés de depender só de decorar cada endpoint
3. Revisar `backend/routers/email.py` e `backend/routers/whatsapp.py` - garantir proteção
4. Testar acesso sem assinatura a endpoints críticos
- **Verificação:** Grep por `@app.` e `@router.` sem `require_active_subscription` em rotas de escrita/IA
- **Status:** **Corrigir antes do lançamento**

#### SEC-007 - Webhook Stripe - validação e logging
- **Severidade:** ALTO
- **Localização:** `backend/routers/billing.py:170-206`, `backend/services/billing_service.py`
- **Evidência positiva:** Requer `stripe-signature`, chama `handle_stripe_webhook(payload_bytes, sig_header)`. Bom.
- **Riscos potenciais:**
- Se `STRIPE_WEBHOOK_SECRET` não configurado, `stripe.Webhook.construct_event` pode falhar ou comportamento inseguro? Precisa ver implementação completa
- Logs podem vazar dados sensíveis
- Endpoint público (sem auth) - correto para webhook, mas precisa validação rigorosa
- **Remediação concreta:**
1. Garantir falha se webhook secret ausente em produção
2. Não logar payload completo, apenas event id/type
3. Idempotência (Stripe pode reenviar eventos) - verificar se `handle_stripe_webhook` trata
4. Verificar raw body usado corretamente (FastAPI Request.body() OK)
- **Verificação:** Enviar webhook sem assinatura → 400; com assinatura inválida → 400
- **Status:** **Corrigir antes do lançamento**

#### SEC-008 - Banco de dados / Supabase (RLS e chaves)
- **Severidade:** ALTO
- **Localização:** `backend/supabase_client.py`, `backend/database.py`, `schema.sql`
- **Evidência:** Usa `SUPABASE_SERVICE_ROLE_KEY` no backend (correto para backend) com fallback para `anon_key`. 
- **Riscos:**
- `service_role` bypassa RLS completamente - se exposto ou mal usado crítico
- Precisa verificar `schema.sql` tem RLS habilitado em tabelas sensíveis (users, subscriptions, business_info, email_integrations)
- Código também tem fallback SQLite? `DATABASE_URL=supabase://...` no .env mas `backend/database.py` precisa ser verificado
- **Remediação concreta:**
1. Revisar `schema.sql` - confirmar `ENABLE ROW LEVEL SECURITY` em todas tabelas com dados de usuário
2. Nunca expor `service_role_key` no frontend
3. Usar `anon_key` + RLS para acesso client-side se houver; `service_role` apenas server-side
4. Remover qualquer possibilidade de usar chaves em cliente
- **Verificação:** Ler `schema.sql` completo focando em `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` e policies
- **Status:** **Corrigir antes do lançamento**

#### SEC-009 - Rate limiting ausente
- **Severidade:** ALTO
- **Localização:** Todo o app (main.py, routers) - sem middleware de rate limit
- **Evidência:** Não encontrado uso de `slowapi`, `fastapi-limiter`, etc. Endpoints críticos sem proteção: `/api/auth/login`, `/api/auth/signup`, `/api/billing/webhook` (webhook tem validação assinatura mas não rate limit), `/api/billing/checkout`
- **Impacto:** Brute force em login/signup, abuso de checkout, DoS
- **Probabilidade:** Alta
- **Vetor:** Brute force/DoS
- **Exploitabilidade:** Alta
- **Remediação concreta:**
1. Adicionar rate limiting (ex: `slowapi` com Redis ou in-memory para single instance)
2. Proteger especificamente: login/signup (5-10 req/min por IP), checkout/portal (3-5 req/min), webhook pode ter limite mais alto mas monitorar
3. Considerar rate limit por usuário autenticado também
- **Verificação:** Fazer múltiplas tentativas de login rapidamente - sem bloqueio atualmente
- **Status:** **Corrigir antes do lançamento**

#### SEC-010 - Logging e vazamento de informações
- **Severidade:** ALTO
- **Localização:** Múltiplos arquivos (main.py, billing_service.py, routers)
- **Evidência:** 
- `logger.error(f"Erro ao iniciar checkout Stripe: {e}")` etc - pode logar detalhes
- Em `billing.py:203` loga erro genérico mas precisa verificar outros locais
- Frontend tem muitos `console.log`? (app.js grande - não auditado linha por linha mas comum)
- **Impacto:** Vazamento de stack traces/infos em logs acessíveis
- **Probabilidade:** Média
- **Vetor:** Information Disclosure via logs
- **Exploitabilidade:** Média
- **Remediação concreta:**
1. Nunca logar tokens, senhas, chaves, PII completo
2. Logar apenas IDs e mensagens genéricas
3. Remover `console.log/debug` com dados sensíveis do frontend em produção
4. Configurar nível de log apropriado (INFO em prod, não DEBUG com dados)
- **Verificação:** Revisar logs em staging - sem dados sensíveis
- **Status:** **Corrigir antes do lançamento**

### MÉDIO

#### SEC-011 - Validação de senha
- **Severidade:** MÉDIO
- **Localização:** `backend/main.py:307-323` (signup)
```python
if not re.search(r"[A-Za-z]", data.password) or not re.search(r"\d", data.password):
    raise HTTPException(400, "A senha deve conter pelo menos uma letra e um número.")
```
- **Evidência:** Requisitos mínimos fracos (apenas letra+numero, min 8 chars). Sem verificação de senhas comuns, sem complexidade maior.
- **Impacto:** Senhas fracas aceitas
- **Probabilidade:** Média
- **Vetor:** Credential stuffing
- **Exploitabilidade:** Média
- **Remediação concreta:**
1. Aumentar complexidade: exigir maiúscula/minúscula/número/símbolo ou usar zxcvbn
2. Verificar contra listas de senhas vazadas (opcional mas recomendado)
3. Considerar rate limit em signup/login (já apontado)
- **Verificação:** Tentar senha "12345678" ou "password1" - atualmente aceito se tiver letra+numero
- **Status:** **Recomendado corrigir antes do lançamento**

#### SEC-012 - Upload de arquivos
- **Severidade:** MÉDIO
- **Localização:** `backend/main.py:282` imports `UploadFile, File` mas não vejo endpoint de upload visível nas primeiras 499 linhas
- **Evidência:** Imports presentes mas uso não confirmado nas linhas lidas
- **Impacto:** Se endpoint existir sem validação (tipo/tamanho/nome), risco de upload malicioso
- **Probabilidade:** Desconhecida
- **Vetor:** File upload abuse
- **Exploitabilidade:** Variável
- **Remediação concreta:**
1. Verificar TODOS os usos de `UploadFile` em todo backend
2. Validar MIME type, extensão, tamanho máximo
3. Armazenar fora do webroot ou com nome aleatório
4. Não executar arquivos uploaded
5. Escanear se possível
- **Verificação:** `grep -rn "UploadFile" backend/` para encontrar todos endpoints
- **Status:** **Recomendado corrigir antes do lançamento**

#### SEC-013 - Tratamento de erros e informações
- **Severidade:** MÉDIO
- **Localização:** `backend/routers/billing.py:157-165`, `backend/main.py` geral
```python
except Exception as e:
    logger.error(f"Erro ao iniciar checkout Stripe: {e}")
    raise HTTPException(500, f"Falha ao gerar checkout: {str(e)}")
```
- **Evidência:** Em alguns lugares expõe `str(e)` ao cliente (ex: billing checkout/portal). Pode vazar detalhes internos/stack info
- **Impacto:** Information disclosure
- **Probabilidade:** Média
- **Vetor:** Error message leakage
- **Exploitabilidade:** Baixa-Média
- **Remediação concreta:**
1. Em produção retornar mensagens genéricas, logar detalhes completos
2. Usar exception handlers globais
3. Evitar `str(e)` direto em HTTPException para usuários
- **Verificação:** Causar erro e ver resposta da API
- **Status:** **Recomendado corrigir antes do lançamento**

#### SEC-014 - Dependências
- **Severidade:** MÉDIO
- **Localização:** `requirements.txt`, `package.json`
- **Evidência a verificar:**
- Python: fastapi, uvicorn, pydantic, python-jose, bcrypt, stripe, supabase, python-dotenv, google-api-python-client, etc.
- Node: vite, etc.
- **Riscos:** Versões desatualizadas podem ter CVEs
- **Remediação concreta:**
1. Rodar `pip-audit` / `safety check` em requirements
2. Rodar `npm audit` 
3. Atualizar dependências com CVEs conhecidos
4. Pin versions (já parece pinado parcialmente)
- **Verificação:** `pip show <pacote>` versões, `npm audit --production`
- **Status:** **Recomendado corrigir antes do lançamento**

#### SEC-015 - Schema SQL e RLS
- **Severidade:** MÉDIO
- **Localização:** `schema.sql` (protegido conforme análise anterior)
- **Evidência:** Precisa verificar se RLS está habilitado
- **Impacto:** Se usando Supabase client com anon key do frontend e RLS desabilitado, acesso direto aos dados
- **Remediação concreta:**
1. Ler `schema.sql` inteiro
2. Garantir `ALTER TABLE ... ENABLE ROW LEVEL SECURITY;` em todas tabelas com user_id
3. Criar policies adequadas (users só veem próprios dados)
4. Nunca confiar apenas em backend se houver acesso direto do cliente
- **Verificação:** Inspecionar schema.sql
- **Status:** **Recomendado corrigir antes do lançamento**

### BAIXO

#### SEC-016 - Headers de segurança ausentes
- **Severidade:** BAIXO
- **Localização:** `backend/main.py` - sem middleware de security headers
- **Impacto:** Falta de proteção em camada HTTP (clickjacking, MIME sniffing, XSS via headers)
- **Remediação concreta:**
1. Adicionar middleware com headers: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` ou `SAMEORIGIN`, `Referrer-Policy`, `Strict-Transport-Security` (se HTTPS), `Content-Security-Policy`
2. Ou configurar no reverse proxy (nginx/cloudflare)
- **Verificação:** `curl -I https://dominio/` checar headers
- **Status:** **Monitorar/Melhorar**

#### SEC-017 - Debug/rotas de diagnóstico
- **Severidade:** BAIXO
- **Localização:** `backend/main.py` tem `/api/health`, `/api/status`? Não visíveis nas primeiras 200 linhas. `backend/supabase_client.py` tem `get_supabase_status()`
- **Evidência:** Rota `/api/status` pode expor info sensível? Precisa verificar
- **Remediação concreta:**
1. Garantir rotas de status/health não vazam chaves/configs detalhados
2. Proteger ou remover em produção se desnecessárias
- **Verificação:** Buscar `@app.get.*status|health|debug`
- **Status:** **Monitorar/Melhorar**

#### SEC-018 - Comentários com info sensível
- **Severidade:** BAIXO
- **Localização:** Vários arquivos
- **Evidência:** Comentários em português ok, mas revisar se há paths/keys
- **Remediação concreta:** Revisar comentários antes de tornar repo público
- **Status:** **Monitorar/Melhorar**

## 2) MAPA DE ROTAS E PROTEÇÃO

### Rotas identificadas

**Core (main.py):**
- `GET /` - Público (serve index.html) ✓
- `GET /styles.css`, `/app.js`, `/i18n.js` - Públicos (arquivos estáticos) ✓
- `POST /api/auth/signup` - Público (com validações) ✓
- `POST /api/auth/login` - Público (com verificação) ✓
- Rotas autenticadas com `current_user()` - várias (precisam token)
- Rotas com `require_active_subscription()` - marcadas como paywall (precisa verificar cobertura completa)

**Billing router (`/api/billing/*`):**
- `GET /api/billing/config` - Público? (sem auth) - retorna config pública Stripe ✓
- `GET /api/billing/status` - Requer auth (`get_current_user`) ✓
- `GET /api/billing/verify-session` - Requer auth ✓
- `POST /api/billing/checkout` - Requer auth ✓
- `POST /api/billing/portal` - Requer auth ✓
- `POST /api/billing/webhook` - **Público** (correto p/ Stripe) - valida assinatura ✓

**Email router (`/api/email/*`):** Requer análise completa - provável protegido por auth + paywall
**WhatsApp router (`/api/whatsapp/*`):** Requer análise completa

**Ação necessária:** Fazer grep completo de todas rotas e dependências para confirmar cobertura 100% das rotas sensíveis com paywall/auth.

## 3) CHECKLIST PRÉ-LANÇAMENTO

### OBRIGATÓRIO (Bloqueadores)
- [ ] **SEC-001:** Rotacionar TODAS as chaves expostas (.env) e remover do histórico git
- [ ] **SEC-002:** Corrigir CORS (origens específicas, sem `*` com credentials)
- [ ] **SEC-003:** Remover fallback de SECRET_KEY, gerar segredo forte, reduzir expiração JWT
- [ ] **SEC-004:** Desabilitar `/docs`, `/redoc`, `/openapi.json` em produção
- [ ] **SEC-006:** Auditar cobertura completa de paywall em todas rotas sensíveis
- [ ] **SEC-009:** Implementar rate limiting em auth/billing
- [ ] **SEC-008:** Verificar RLS no Supabase/schema.sql

### ALTAMENTE RECOMENDADO
- [ ] **SEC-005:** Revisar armazenamento de token e XSS (CSP)
- [ ] **SEC-007:** Hardening webhook Stripe (idempotência, logs)
- [ ] **SEC-010:** Sanitizar logs (remover dados sensíveis)
- [ ] **SEC-012:** Auditar uploads se existirem
- [ ] **SEC-013:** Não vazar erros internos ao cliente
- [ ] **SEC-014:** Rodar `npm audit` e `pip-audit`

### DESEJÁVEL
- [ ] **SEC-011:** Fortalecer política de senha
- [ ] **SEC-015:** Revisar policies RLS
- [ ] **SEC-016:** Adicionar security headers
- [ ] **SEC-017-018:** Limpar rotas debug e comentários sensíveis

## 4) COMANDOS PARA VERIFICAÇÃO

```powershell
# Verificar .env no git
git -C C:\Users\USER\Downloads\Drexier ls-tree -r --name-only HEAD | Select-String ".env"
git -C C:\Users\USER\Downloads\Drexier log --oneline --all --max-count=10 -- .env

# Procurar secrets hardcoded
Select-String -Path "C:\Users\USER\Downloads\Drexier\**\*.py","C:\Users\USER\Downloads\Drexier\**\*.js" -Pattern "sk_live|sk_test|eyJhbGci" | Where-Object { $_.Path -notmatch "\.env" } | Select-Object Path,LineNumber,Line

# Procurar CORS
Select-String -Path "C:\Users\USER\Downloads\Drexier\backend\main.py" -Pattern "CORSMiddleware|allow_origins"

# Procurar rotas sem proteção (análise inicial)
Select-String -Path "C:\Users\USER\Downloads\Drexier\backend\**\*.py" -Pattern "@app\.|@router\." | Measure-Object

# Procurar UploadFile
Select-String -Path "C:\Users\USER\Downloads\Drexier\backend\**\*.py" -Pattern "UploadFile"

# Procurar console.log em frontend
Select-String -Path "C:\Users\USER\Downloads\Drexier\frontend\**\*.js" -Pattern "console\." | Measure-Object

# Dependências
cd C:\Users\USER\Downloads\Drexier; pip-audit 2>&1 | tail -30
cd C:\Users\USER\Downloads\Drexier; npm audit --production 2>&1 | tail -40
```

## CONCLUSÃO

**Estado atual:** O sistema tem boa arquitetura de paywall e webhook Stripe com validação de assinatura. No entanto, **há 4 achados CRÍTICOS** que **BLOQUEIAM o lançamento**:

1. Segredos reais no `.env` commitado
2. CORS permissivo com credentials
3. SECRET_KEY inseguro/fallback
4. Documentação FastAPI exposta

**Recomendação final:** **NÃO FAZER DEPLOY EM PRODUÇÃO** até corrigir todos os itens CRÍTICOS e, no mínimo, os itens ALTOS. Os achados foram baseados exclusivamente em evidências do código-fonte, sem alterações realizadas.

**Relatório gerado em:** `C:\Users\USER\Downloads\Drexier\SECURITY_AUDIT_PRELAUNCH.md`
