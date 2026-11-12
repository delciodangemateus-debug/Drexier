# AN�LISE COMPLETA E SEGURA - REPOSIT�RIO DREXIER
**Data:** 2026-10-28  
**Modo:** APENAS AN�LISE - NADA SER� REMOVIDO
**Diret�rio:** C:\Users\USER\Downloads\Drexier

> ATEN��O: App funcional com Stripe/Supabase/paywall. �ltimos commits indicam sistema de pagamentos ativo. Toda sugest�o � baseada em refer�ncias verificadas, mas quando houver d�vida classifiquei como 'risco: incerto' e n�o proponho remo��o imediata.

## 1) VIS�O GERAL DA STACK

### Framework & Arquitetura
- Tipo: Monorepo com backend + frontend est�tico servido pela API
- Backend: Python + FastAPI (Uvicorn via 
pm run server)
- Frontend: Vanilla JS/CSS/HTML em rontend/ (Vite para dev/build)
- Configura��o: ite.config.js (proxy /api -> 127.0.0.1:8000, build outDir ../dist)
- Package: "type": "module", scripts dev/server/build/preview

### Rotas / Endpoints
- Routers: billing (/api/billing/*) e email (/api/email/*) em backend/main.py
- Worker background em main.py processa emails respeitando paywall via is_subscription_active

### Banco de Dados
- Principal/�nico: Supabase (conforme commits). Implementado via ackend/database.py + ackend/supabase_client.py + ackend/supabase_adapter.py. schema.sql presente (PROTEGIDO).

### Autentica��o
- ackend/auth.py - hash senha, JWT (create/decode/verify)

### Pagamentos / Paywall (Stripe)
- Router: ackend/routers/billing.py (config/status/verify-session/checkout/portal/webhook com valida��o Stripe-Signature)
- Service: ackend/services/billing_service.py (Plano Business 59,00EUR/mes, 5900 cents)
- Frontend: rontend/app.js + rontend/index.html com l�gica de paywall estrita

### Outros
- Email: ackend/routers/email.py, ackend/services/email_service.py
- Agent: ackend/services/agent.py
- Analytics: ackend/services/analytics.py usado por /api/analytics em main, frontend e testes

## 2) CANDIDATOS AGRUPADOS

### A) Arquivos �rf�os prov�veis
| Caminho exato | Motivo | Evid�ncias | Confian�a | Impacto | Risco | Observa��o |
|---------------|--------|-----------|------------|---------|-------|------------|
| backend/__init__.py | Vazio, sem refs externas | Sem hits externos; mesmo hash dos outros __init__ vazios | M�dia | Baixo | incerto | N�o remover sem testar imports em c�pia isolada |
| backend/routers/__init__.py | Vazio, sem refs externas | Idem | M�dia | Baixo | incerto | N�o remover sem testar imports |
| backend/services/__init__.py | Vazio, sem refs externas | Idem | M�dia | Baixo | incerto | N�o remover sem testar imports |

### B) Duplicados
| Caminho exato | Motivo | Evid�ncias | Confian�a | Impacto | Risco | Observa��o |
|---------------|--------|-----------|------------|---------|-------|------------|
| backend/__init__.py, backend/routers/__init__.py, backend/services/__init__.py | Mesmo conte�do SHA256 (todos vazios) | Hash id�ntico confirmado | Alta | Baixo | incerto | S�o arquivos de pacote por diret�rio - n�o s�o c�pias redundantes funcionais. N�o propor remo��o. |

### C) C�digo morto/comentado
| Caminho exato | Motivo | Evid�ncias | Confian�a | Impacto | Risco | Observa��o |
|---------------|--------|-----------|------------|---------|-------|------------|
| Nenhum arquivo inteiro identificado como �rf�o | Investigado | analytics.py usado em main/frontend/testes; supabase usado por database/main | Alta | N/A | baixo | Sem candidato com alta confian�a. |
| Coment�rios pontuais | Presentes mas majoritariamente explicativos/seguran�a | Contagens: main.py 3/499, email_service.py 61/1487, agent.py 12/487, frontend/app.js 117/3294 | M�dia | Baixo | incerto | N�o remover por regex - revis�o humana apenas se certeza absoluta. |

### D) Pastas vazias/suspeitas
| Caminho exato | Motivo | Evid�ncias | Confian�a | Impacto | Risco | Observa��o |
|---------------|--------|-----------|------------|---------|-------|------------|
| data/ | Apenas .gitkeep | Sem arquivos de dados no repo; pode ser usado em runtime | M�dia | Baixo | incerto | N�o remover. |
| __pycache__/, .pytest_cache/ | Caches | Ignorados por regras | Alta | Baixo | incerto | Ignorar conforme instru��es. |
| node_modules/, .git/, dist/ | Deps/VCS/build | Ignorados/regener�veis mas n�o "c�digo-fonte morto" | Alta | Alto | incerto | NUNCA remover. |
| docs/API.md | Documenta��o | Pequeno, sem refs cr�ticas | M�dia | Baixo | incerto | Manter. |

## 3) PLANO EM 3 FASES

### FASE 1 - Alt�ssimo cuidado / Baixo risco (SOMENTE VERIFICA��O)
1. git status/diff/log
2. python -m pytest -v
3. Testar imports principais (backend.main, routers, services)
4. npm run build
5. Verificar necessidade dos __init__.py

### FASE 2 - M�dio risco (S� SE FASE 1 OK)
1. Testar remo��o tempor�ria dos 3 __init__.py em c�pia/branch isolada com todos os testes/imports
2. Investigar data/ apenas se houver evid�ncias fortes de n�o-uso (incluir deploy/config)
3. S� prosseguir com provas

### FASE 3 - S� com confirma��o
1. Apenas com prova irrefut�vel de n�o-uso + testes OK + revers�vel
2. NUNCA tocar: schema.sql, .env.example, migra��es, README.md, configs essenciais, c�digo Stripe/paywall/auth/supabase

## 4) COMANDOS DE VERIFICA��O
`powershell
git -C C:\Users\USER\Downloads\Drexier status
git -C C:\Users\USER\Downloads\Drexier log --oneline -5
cd C:\Users\USER\Downloads\Drexier; python -m pytest -v
cd C:\Users\USER\Downloads\Drexier; python -c "import backend.main, backend.database, backend.auth, backend.routers.billing, backend.routers.email, backend.services.billing_service; print('IMPORTS_OK')"
cd C:\Users\USER\Downloads\Drexier; npm run build
`

## 5) QUICK WINS SEGUROS
Nenhum identificado com alta confian�a. N�o h� a��es recomendadas para execu��o imediata. Prioridade � validar FASE 1 mantendo tudo intacto.

## RESUMO EXECUTIVO
- Stack: FastAPI + Vanilla JS/Vite + Supabase + Stripe + Email(Gmail)
- 34 arquivos fonte analisados (ignorando dirs proibidos)
- Sem �rf�os claros de alta confian�a; �nicos suspeitos com 'incerto': 3 __init__.py vazios (padr�o pacote)
- analytics.py/supabase infra est�o EM USO
- Protegidos rigorosamente: schema.sql, .env.example, Stripe/paywall, auth, configs essenciais
- RECOMENDA��O: N�O REMOVER NADA AGORA - executar apenas FASE 1 (verifica��o)
