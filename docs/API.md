# API principal

A documentação interativa gerada pelo FastAPI estará em `/docs` quando o servidor estiver em execução.

- `POST /api/auth/signup` — criar conta
- `POST /api/auth/login` — iniciar sessão
- `GET /api/dashboard` — métricas reais e pedidos pendentes
- `DELETE /api/account` — elimina a conta após validar a senha e confirmar na Stripe que a assinatura não será renovada; o período pago permanece, sem reembolso
- `GET /api/contacts` — clientes/conversas
- `POST /api/simulate/incoming` — registar mensagem e gerar resposta (endpoint de teste autenticado)
- `GET/POST /api/business-info` — consultar/adicionar informação do negócio
- `PUT/DELETE /api/business-info/{id}` — editar/remover informação
- `GET /api/analytics` — série diária e estilos de resposta
- `POST /api/contacts/{id}/conversion` — registar intenção de compra/marcação
- `POST /api/conversions/{id}/resolve` — marcar pedido como tratado
