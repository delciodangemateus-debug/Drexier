# ANÁLISE COMPLETA E SEGURA - REPOSITÓRIO DREXIER
**Data:** 2026-10-28  
**Modo:** APENAS ANÁLISE - NADA SERÁ REMOVIDO  
**Diretório:** C:\Users\USER\Downloads\Drexier  

> ATENÇÃO: App funcional com Stripe/Supabase/paywall. Últimos commits indicam sistema de pagamentos ativo. Toda sugestão é baseada em referências verificadas, mas quando houver dúvida classifiquei como 'risco: incerto' e não proponho remoção imediata.

## 1) VISÃO GERAL DA STACK

### Framework & Arquitetura
- Tipo: Monorepo com backend + frontend estático servido pela API
- Backend: Python + FastAPI (Uvicorn via 
pm run server)
- Frontend: Vanilla JS/CSS/HTML em rontend/ (Vite para dev/build)
- Configuração: ite.config.js (proxy /api -> 127.0.0.1:8000, build outDir ../dist)
- Package: "type": "module", scripts dev/server/build/preview

### Rotas / Endpoints
- Routers: billing (/api/billing/*), email (/api/email/*), whatsapp (/api/whatsapp/*) em ackend/main.py
- Worker background em main.py processa emails respeitando paywall via is_subscription_active

### Banco de Dados
- Principal/único: Supabase (conforme commits). Implementado via ackend/database.py + ackend/supabase_client.py + ackend/supabase_adapter.py. schema.sql presente (PROTEGIDO).

### Autenticação
- ackend/auth.py - hash senha, JWT (create/decode/verify)

### Pagamentos / Paywall (Stripe)
- Router: ackend/routers/billing.py (config/status/verify-session/checkout/portal/webhook com validação Stripe-Signature)
- Service: ackend/services/billing_service.py (Plano Business 59,00EUR/mes, 5900 cents)
- Frontend: rontend/app.js + rontend/index.html com lógica de paywall estrita

### Outros
- Email: ackend/routers/email.py, ackend/services/email_service.py
- WhatsApp: ackend/routers/whatsapp.py, ackend/services/whatsapp.py (integrado e testado)
- Agent: ackend/services/agent.py
- Analytics: ackend/services/analytics.py usado por /api/analytics em main, frontend e testes

## 2) CANDIDATOS AGRUPADOS

### A) Arquivos órfãos prováveis
| Caminho exato | Motivo | Evidências | Confiança | Impacto | Risco | Observação |
|---------------|--------|-----------|------------|---------|-------|------------|
| backend/__init__.py | Vazio, sem refs externas | Sem hits externos; mesmo hash dos outros __init__ vazios | Média | Baixo | incerto | Não remover sem testar imports em cópia isolada |
| backend/routers/__init__.py | Vazio, sem refs externas | Idem | Média | Baixo | incerto | Não remover sem testar imports |
| backend/services/__init__.py | Vazio, sem refs externas | Idem | Média | Baixo | incerto | Não remover sem testar imports |

### B) Duplicados
| Caminho exato | Motivo | Evidências | Confiança | Impacto | Risco | Observação |
|---------------|--------|-----------|------------|---------|-------|------------|
| backend/__init__.py, backend/routers/__init__.py, backend/services/__init__.py | Mesmo conteúdo SHA256 (todos vazios) | Hash idêntico confirmado | Alta | Baixo | incerto | São arquivos de pacote por diretório - não são cópias redundantes funcionais. Não propor remoção. |

### C) Código morto/comentado
| Caminho exato | Motivo | Evidências | Confiança | Impacto | Risco | Observação |
|---------------|--------|-----------|------------|---------|-------|------------|
| Nenhum arquivo inteiro identificado como órfão | Investigado | analytics.py usado em main/frontend/testes; whatsapp integrado/testado; supabase usado por database/main | Alta | N/A | baixo | Sem candidato com alta confiança. |
| Comentários pontuais | Presentes mas majoritariamente explicativos/segurança | Contagens: main.py 3/499, email_service.py 61/1487, whatsapp.py 33/570, agent.py 12/487, frontend/app.js 117/3294 | Média | Baixo | incerto | Não remover por regex - revisão humana apenas se certeza absoluta. |

### D) Pastas vazias/suspeitas
| Caminho exato | Motivo | Evidências | Confiança | Impacto | Risco | Observação |
|---------------|--------|-----------|------------|---------|-------|------------|
| data/ | Apenas .gitkeep | Sem arquivos de dados no repo; pode ser usado em runtime | Média | Baixo | incerto | Não remover. |
| __pycache__/, .pytest_cache/ | Caches | Ignorados por regras | Alta | Baixo | incerto | Ignorar conforme instruções. |
| node_modules/, .git/, dist/ | Deps/VCS/build | Ignorados/regeneráveis mas não "código-fonte morto" | Alta | Alto | incerto | NUNCA remover. |
| docs/API.md | Documentação | Pequeno, sem refs críticas | Média | Baixo | incerto | Manter. |

## 3) PLANO EM 3 FASES

### FASE 1 - Altíssimo cuidado / Baixo risco (SOMENTE VERIFICAÇÃO)
1. git status/diff/log
2. python -m pytest -v
3. Testar imports principais (backend.main, routers, services)
4. npm run build
5. Verificar necessidade dos __init__.py

### FASE 2 - Médio risco (SÓ SE FASE 1 OK)
1. Testar remoção temporária dos 3 __init__.py em cópia/branch isolada com todos os testes/imports
2. Investigar data/ apenas se houver evidências fortes de não-uso (incluir deploy/config)
3. Só prosseguir com provas

### FASE 3 - Só com confirmação
1. Apenas com prova irrefutável de não-uso + testes OK + reversível
2. NUNCA tocar: schema.sql, .env.example, migrações, README.md, configs essenciais, código Stripe/paywall/auth/supabase

## 4) COMANDOS DE VERIFICAÇÃO
`powershell
git -C C:\Users\USER\Downloads\Drexier status
git -C C:\Users\USER\Downloads\Drexier log --oneline -5
cd C:\Users\USER\Downloads\Drexier; python -m pytest -v
cd C:\Users\USER\Downloads\Drexier; python -c "import backend.main, backend.database, backend.auth, backend.routers.billing, backend.routers.email, backend.routers.whatsapp, backend.services.billing_service; print('IMPORTS_OK')"
cd C:\Users\USER\Downloads\Drexier; npm run build
`

## 5) QUICK WINS SEGUROS
Nenhum identificado com alta confiança. Não há ações recomendadas para execução imediata. Prioridade é validar FASE 1 mantendo tudo intacto.

## RESUMO EXECUTIVO
- Stack: FastAPI + Vanilla JS/Vite + Supabase + Stripe + Email(Gmail) + WhatsApp
- 34 arquivos fonte analisados (ignorando dirs proibidos)
- Sem órfãos claros de alta confiança; únicos suspeitos com 'incerto': 3 __init__.py vazios (padrão pacote)
- analytics.py/whatsapp/supabase infra estão EM USO
- Protegidos rigorosamente: schema.sql, .env.example, Stripe/paywall, auth, configs essenciais
- RECOMENDAÇÃO: NÃO REMOVER NADA AGORA - executar apenas FASE 1 (verificação)
