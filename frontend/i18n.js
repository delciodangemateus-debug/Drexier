/**
 * Drexier I18n Engine - Complete Bilingual Translation System (PT / EN)
 * Handles full static DOM, attributes, dynamically rendered templates, notices, and live mutations.
 */
(() => {
  const STORAGE_KEY = "drexier_language";

  const translationsEn = {
  "Visão Geral": "Overview",
  "Desempenho": "Performance",
  "Comparativo": "Comparison",
  "Perguntas Frequentes": "Frequently Asked Questions",
  "Sobre o Software": "About the Software",
  "Entrar": "Sign in",
  "Entrar na Conta": "Sign in to Account",
  "Entrar na Plataforma": "Sign in to Platform",
  "Começar Agora": "Get Started",
  "Comece Hoje Mesmo": "Get Started Today",
  "Criar conta": "Create account",
  "Criar Conta e Começar": "Create Account & Get Started",
  "Criar Conta / Começar Agora": "Create Account / Get Started",
  "Voltar à página inicial": "Back to home",
  "Voltar": "Back",
  "Voltar à lista de clientes": "Back to customer list",
  "Tecnologia Autônoma de Atendimento & Vendas": "Autonomous Customer Support & Sales Technology",
  "Atendimento ao cliente e vendas com mais contexto": "Customer support and sales with more context",
  "Atendimento ao cliente e vendas com": "Customer support and sales with",
  "mais contexto": "more context",
  "A ferramenta definitiva para transformar os e-mails e contactos da sua empresa em vendas e clientes satisfeitos com IA.": "The definitive tool to turn your company's emails and contacts into sales and satisfied customers with AI.",
  "Ver como funciona": "See how it works",
  "Configuração guiada": "Guided setup",
  "Integração com Gmail": "Gmail integration",
  "Integração com Google Gmail": "Integration with Google Gmail",
  "Controle do agente por você": "You control the agent",
  "Controlo do agente na plataforma": "Agent control in the platform",
  "Alex Morgan • Customer": "Alex Morgan • Customer",
  "Subject: Re: Product information": "Subject: Re: Product information",
  "Inbound Inquiry": "Inbound Inquiry",
  "Incoming email": "Incoming email",
  "Business context": "Business context",
  "Draft response • Review before sending": "Draft response • Review before sending",
  "Verified AI Agent": "Verified AI Agent",
  "Active AI Agents": "Active AI Agents",
  "Integração ativa • Agente configurável:": "Active integration • Configurable agent:",
  "Conecte o seu Google Gmail em poucos segundos": "Connect your Google Gmail in seconds",
  "Autentique com um clique através da autorização OAuth 2.0 oficial.": "Authenticate with one click via official OAuth 2.0 authorization.",
  "Autorize o envio e leitura de e-mails na tela oficial e segura da Google.": "Authorize sending and reading emails on Google's official, secure screen.",
  "Conecte a conta comercial do Google Gmail da sua empresa para que a IA Drexier atenda e conduza conversas com os seus clientes diretamente por e-mail.": "Connect your company's official Google Gmail business account so Drexier AI can answer and handle conversations with your customers directly by email.",
  "Conectar Google Gmail Oficial": "Connect Official Google Gmail",
  "Conectar com a Google": "Connect with Google",
  "Conceda as Permissões": "Grant Permissions",
  "Autorize o Gmail e pause o agente quando quiser": "Authorize Gmail and pause the agent whenever you want",
  "Google Gmail • Respostas automáticas configuráveis": "Google Gmail • Configurable automated replies",
  "Google Gmail:": "Google Gmail:",
  "Atendimento Oficial": "Official Support",
  "Canal E-mail Oficial (Google Gmail)": "Official Email Channel (Google Gmail)",
  "Conexão oficial direta com a caixa de entrada para monitorização e respostas reais contínuas.": "Official direct connection to the inbox for real-time monitoring and continuous replies.",
  "Pronto para colocar o atendimento da sua empresa no piloto automático?": "Ready to put your company's customer support on autopilot?",
  "Quer organizar o atendimento do seu negócio?": "Looking to organize your business customer support?",
  "Crie a sua conta, configure as informações da empresa e ligue o e-mail comercial.": "Create your account, configure your company information, and connect your business email.",
  "Crie a sua conta, configure as informações do negócio e explore as ferramentas de atendimento.": "Create your account, configure business information, and explore the support tools.",
  "Tempo de resposta": "Response time",
  "Disponibilidade 24/7": "24/7 Availability",
  "Disponibilidade": "Availability",
  "Organização da caixa": "Inbox organization",
  "Visibilidade dos pedidos": "Order & request visibility",
  "Mais visibilidade": "More visibility",
  "Acompanhamento": "Follow-up",
  "Acompanhamento de clientes": "Customer follow-up",
  "Acompanhe cada conversa": "Track every conversation",
  "Acompanhe mensagens e pedidos no painel": "Track messages and requests on the dashboard",
  "Visão da operação": "Operational overview",
  "Visão clara de contactos diários, mensagens respondidas e taxas de conversão de clientes.": "Clear overview of daily contacts, answered messages, and customer conversion rates.",
  "Mais clareza para acompanhar o atendimento": "More clarity to follow customer support",
  "Tenha uma visão clara das mensagens recebidas e das oportunidades que precisam de atenção.": "Get a clear view of incoming messages and opportunities that need attention.",
  "Centralize pedidos e mensagens para que a equipa saiba quais conversas precisam de acompanhamento.": "Centralize requests and messages so the team knows which conversations require follow-up.",
  "Organize as conversas por e-mail, dê ao agente informações sobre o seu negócio e acompanhe as respostas num só lugar. Você decide quando ativar a automação e pode intervir sempre que precisar.": "Organize email conversations, give the agent context about your business, and track replies in one place. You decide when to enable automation and can step in whenever needed.",
  "Automatize etapas repetitivas do acompanhamento": "Automate repetitive follow-up steps",
  "O painel ajuda a visualizar os clientes e a dar seguimento às conversas por e-mail.": "The dashboard helps you view customers and follow up on email conversations.",
  "Organize o contexto do seu negócio": "Organize your business context",
  "Organize produtos, políticas e respostas frequentes para dar contexto ao agente.": "Organize products, policies, and FAQs to give context to the agent.",
  "Organize as informações usadas pelo agente": "Organize the information used by the agent",
  "A plataforma reúne informações sobre produtos, stock e políticas para dar contexto ao agente. A equipa pode atualizar esses dados e acompanhar as conversas num único painel.": "The platform gathers information about products, stock, and policies to give context to the agent. The team can update this data and track conversations in a single dashboard.",
  "Ative as respostas quando estiver pronto": "Enable replies when you are ready",
  "Ative ou pause as respostas automáticas e configure o contexto do negócio.": "Enable or pause automated replies and configure business context.",
  "Mantenha as informações do negócio completas e atualizadas.": "Keep business information complete and up to date.",
  "Adicione orientações claras e mantenha-as atualizadas.": "Add clear guidelines and keep them up to date.",
  "Exemplo visual, sem dados reais": "Visual example, no real data",
  "Exemplo visual, não representa resultados medidos.": "Visual example, does not represent measured results.",
  "Exemplos visuais de como organizar conversas, contexto do negócio e oportunidades. Os resultados variam conforme a operação e a configuração da conta.": "Visual examples of how to organize conversations, business context, and opportunities. Results vary depending on operations and account settings.",
  "Representação qualitativa, sem métricas de desempenho.": "Qualitative representation, without performance metrics.",
  "Tendência ilustrativa": "Illustrative trend",
  "Gráfico ilustrativo de vendas em tendência crescente, sem dados reais": "Illustrative graph of upward sales trend, without real data",
  "Antes vs. Depois da Automação": "Before vs. After Automation",
  "Comparação funcional": "Functional comparison",
  "Antes (Manual)": "Before (Manual)",
  "Depois (Drexier IA)": "After (Drexier AI)",
  "Atendimento Manual Tradicional": "Traditional Manual Support",
  "Automação Inteligente Drexier": "Drexier Intelligent Automation",
  "Resposta Manual vs. Automação Drexier": "Manual Response vs. Drexier Automation",
  "Uma comparação prática de como o atendimento manual e a automação podem apoiar a gestão de mensagens. Não representa um estudo de desempenho nem garante resultados comerciais.": "A practical comparison of how manual support and automation can support message handling. Does not represent a benchmark study nor guarantee commercial results.",
  "A automação pode ajudar a responder com mais consistência, enquanto o atendimento manual depende da disponibilidade da equipa.": "Automation helps respond with greater consistency, while manual support depends on team availability.",
  "Aspeto": "Aspect",
  "Agilidade no atendimento:": "Response speed:",
  "O tempo de resposta depende dos horários e da disponibilidade de quem atende.": "Response time depends on working hours and team availability.",
  "O tempo de resposta depende da configuração e do serviço": "Response time depends on configuration and service",
  "Quando ativado e configurado, o agente pode preparar respostas com base nas informações do negócio.": "When enabled and configured, the agent can prepare replies based on business context.",
  "Pode responder quando ativada": "Can reply when enabled",
  "Horário da equipa": "Team hours",
  "A cobertura varia conforme os horários da equipa": "Coverage varies according to team working hours",
  "Depende da disponibilidade": "Depends on availability",
  "Depende da equipa": "Depends on the team",
  "Gestão manual": "Manual handling",
  "Consulta manual": "Manual lookup",
  "Consulta manual de produtos e políticas": "Manual lookup of products and policies",
  "A pessoa que atende consulta e aplica as informações disponíveis da empresa.": "The person answering looks up and applies available company information.",
  "Base de conhecimento estruturada e contextual": "Structured, contextual knowledge base",
  "Contexto configurável": "Configurable context",
  "Contexto do negócio:": "Business context:",
  "O agente utiliza os dados e as instruções que a equipa adiciona à plataforma; reveja as respostas e mantenha a base atualizada.": "The agent uses the data and instructions added by your team; review replies and keep the base updated.",
  "Informações de produtos configuradas por si": "Product information configured by you",
  "Produtos, políticas e FAQs": "Products, policies and FAQs",
  "Products, policies and FAQs": "Products, policies and FAQs",
  "Gestão de mensagens e pedidos": "Message & request management",
  "O acompanhamento é feito pela equipa com os processos que já utiliza.": "Follow-up is handled by the team using their existing processes.",
  "Manual e assistido": "Manual and assisted",
  "Pedidos sinalizados para validação": "Requests flagged for validation",
  "Pedidos detetados nas mensagens podem aparecer no painel para revisão e confirmação.": "Requests detected in messages can appear on the dashboard for review and confirmation.",
  "A IA identifica intenções de compra/reserva e permite confirmação rápida pelo proprietário.": "AI identifies purchase/booking intents and allows quick owner confirmation.",
  "Ligar ou desligar": "Turn on or off",
  "On or off": "On or off",
  "You control automation": "You control automation",
  "Human control": "Human control",
  "Configured by your team": "Configured by your team",
  "Automação configurável:": "Configurable automation:",
  "Atendimento com agente configurável": "Support with configurable agent",
  "Apoio automatizado": "Automated assistance",
  "Histórico de conversas acessível à equipa": "Conversation history accessible to the team",
  "Interações com clientes": "Customer interactions",
  "Interações registradas e retidas": "Interactions recorded and retained",
  "Pedidos e oportunidades": "Requests and opportunities",
  "Oportunidades bem organizadas": "Well-organized opportunities",
  "Confiança e visibilidade:": "Trust and visibility:",
  "Segurança e controlo:": "Security and control:",
  "Segurança & Conformidade": "Security & Compliance",
  "Conformidade PCI-DSS Nível 1 Oficial": "Official PCI-DSS Level 1 Compliance",
  "Criptografia Bancária SSL 256-bit": "256-bit SSL Banking Grade Encryption",
  "3D Secure / SCA Antifraude Obrigatório": "Mandatory 3D Secure / SCA Anti-fraud",
  "Stripe com 3D Secure / SCA obrigatório, validação de morada (AVS) e criptografia bancária.": "Stripe with mandatory 3D Secure / SCA, address verification (AVS), and banking encryption.",
  "Pagamento Seguro & Proteção Antifraude": "Secure Payment & Anti-fraud Protection",
  "Sem Fidelização • Cancelamento Livre": "No Commitment • Free Cancellation",
  "Perguntas Frequentes (FAQ)": "Frequently Asked Questions (FAQ)",
  "Perguntas Frequentes sobre o Software": "Frequently Asked Questions about the Software",
  "Dúvidas Comuns": "Common Questions",
  "Tudo o que precisa de compreender sobre o funcionamento, segurança e implementação da plataforma Drexier.": "Everything you need to understand about the operation, security, and setup of the Drexier platform.",
  "O que é o Drexier e como funciona na prática?": "What is Drexier and how does it work in practice?",
  "O Drexier ajuda a organizar o atendimento por e-mail. Depois de ligar a conta e configurar as informações do negócio, pode acompanhar as mensagens e, quando ativado, usar o agente para preparar ou enviar respostas de acordo com as definições da conta.": "Drexier helps organize email customer support. After connecting your account and configuring business information, you can track messages and, when enabled, use the agent to prepare or send responses according to account settings.",
  "Como o Drexier se conecta ao meu e-mail oficial Google Gmail?": "How does Drexier connect to my official Google Gmail email?",
  "A ligação é feita através do fluxo de autorização Google apresentado pela plataforma. Reveja as permissões solicitadas antes de autorizar o acesso e pode desligar a integração nas configurações da conta.": "The connection is established through the Google authorization flow presented by the platform. Review requested permissions before granting access; you can disconnect the integration in account settings at any time.",
  "A IA pode inventar preços, produtos ou prazos incorretos (alucinações)?": "Can the AI invent incorrect prices, products or deadlines (hallucinations)?",
  "Como em qualquer sistema de IA, podem ocorrer respostas incorretas. Configure instruções claras, mantenha os dados atualizados e reveja as respostas, sobretudo antes de enviar informações importantes sobre preços, stock ou políticas.": "As with any AI system, incorrect answers can occur. Set clear instructions, keep data up to date, and review responses, especially before sending key details on pricing, stock, or policies.",
  "Como funciona a validação de pedidos de compra ou agendamentos?": "How does validation of purchase orders or appointments work?",
  "Quando uma mensagem é identificada como um pedido, pode aparecer no painel para validação. Reveja os detalhes e confirme ou responda ao cliente conforme os procedimentos da sua empresa.": "When a message is identified as an order or request, it can appear on the dashboard for validation. Review details and confirm or reply to the customer according to your company's procedures.",
  "Posso desligar o agente ou intervir manualmente quando desejar?": "Can I turn off the agent or intervene manually whenever I want?",
  "Sim. Pode ativar ou pausar o agente pelo interruptor na aba Mensagens e responder manualmente às conversas disponíveis na plataforma.": "Yes. You can activate or pause the agent via the toggle switch in the Messages tab and reply manually to conversations available in the platform.",
  "Preciso de conhecimento técnico ou programadores para configurar?": "Do I need technical skills or developers to configure it?",
  "Não é necessário programar para utilizar as funções principais. Pode ligar o e-mail e preencher as informações do negócio pela interface. A disponibilidade de ajuda adicional depende do suporte oferecido pela plataforma.": "No programming is required to use core features. You can connect email and fill in business information directly through the interface.",
  "Sobre a Plataforma Drexier": "About Drexier Platform",
  "Sobre Nós": "About Us",
  "Conheça a Nossa Filosofia": "Our Philosophy",
  "O Que Fazemos": "What We Do",
  "Como Fazemos": "How We Do It",
  "Porque Somos Diferentes": "Why We Are Different",
  "Ajudamos equipas a organizar a caixa de entrada, acompanhar clientes e gerir respostas por e-mail com apoio de inteligência artificial.": "We help teams organize their inbox, follow up with customers, and manage email replies powered by artificial intelligence.",
  "O Drexier combina gestão de mensagens, contexto configurável do negócio e controlo direto sobre a automação, para que a equipa possa adaptar o atendimento aos seus próprios processos.": "Drexier combines message management, configurable business context, and direct control over automation, so your team can adapt support to their own processes.",
  "Tecnologia desenvolvida com foco intransigente em confiabilidade, elegância visual e resultados financeiros reais.": "Technology developed with an uncompromising focus on reliability, visual elegance, and real financial results.",
  "Plataforma corporativa de atendimento e vendas conduzidas por inteligência artificial autônoma.": "Corporate customer support and sales platform powered by autonomous artificial intelligence.",
  "© 2026 Drexier Technologies. Todos os direitos reservados.": "© 2026 Drexier Technologies. All rights reserved.",
  "Nome completo": "Full name",
  "Email profissional": "Professional email",
  "Senha": "Password",
  "Senha (mínimo 8 caracteres, com letra e número)": "Password (minimum 8 characters, with letter and number)",
  "Confirmar senha": "Confirm password",
  "Tipo de negócio": "Business type",
  "Selecione o segmento": "Select a segment",
  "Serviços": "Services",
  "Vendas": "Sales",
  "Serviços e vendas": "Services and sales",
  "Outro": "Other",
  "Outro Personalizado": "Other Custom",
  "Seu nome ou da empresa": "Your name or company name",
  "Contato de emergência": "Emergency contact",
  "contato@empresa.com": "contact@company.com",
  "seuemail@empresa.com": "you@company.com",
  "Atendimento ao cliente inteligente e organizado.": "Intelligent, organized customer support.",
  "Dashboard": "Dashboard",
  "Mensagens": "Messages",
  "Relatórios": "Reports",
  "Negócio": "Business",
  "Configurações": "Settings",
  "Sair da conta": "Sign out",
  "Sair": "Sign out",
  "Menu": "Menu",
  "Navegação": "Navigation",
  "Visão geral do atendimento": "Customer support overview",
  "Histórico de conversas com clientes": "Customer conversation history",
  "Desempenho e conversões do agente": "Agent performance and conversions",
  "Base de conhecimento e treinamento do agente": "Agent knowledge base and training",
  "Preferências da conta e integrações": "Account preferences and integrations",
  "Ative o Plano Business (59€/mês) para desbloquear a sua IA Drexier": "Activate the Business Plan (€59/month) to unlock your Drexier AI",
  "Acesso às respostas automáticas por e-mail quando o agente estiver ativado, além das ferramentas de treinamento.": "Access to automated email replies when the agent is enabled, plus training tools.",
  "Ativar Subscrição": "Activate Subscription",
  "Subscrever Plano Business (59€/mês)": "Subscribe to Business Plan (€59/month)",
  "Requer Plano Business ativo (59€/mês)": "Requires active Business Plan (€59/month)",
  "Subscrição do Plano Business (59€/mês) necessária.": "Business Plan subscription (€59/month) required.",
  "Novos Clientes Hoje": "New Customers Today",
  "Novos clientes hoje": "New customers today",
  "Novos clientes registados hoje em comparação com o dia anterior.": "New customers registered today compared to the previous day.",
  "Dia anterior: 0": "Previous day: 0",
  "Hoje vs. dia anterior • Volume contínuo": "Today vs. previous day • Continuous volume",
  "Clientes Adquiridos": "Acquired Customers",
  "Clientes adquiridos": "Acquired customers",
  "Número acumulado de contactos únicos que iniciaram conversa com o seu negócio.": "Cumulative number of unique contacts who initiated conversations with your business.",
  "Volume Básico": "Base Volume",
  "Dados reais da conta • últimos 14 dias": "Real account data • past 14 days",
  "Mensagens Respondidas": "Answered Messages",
  "Total de respostas geradas e enviadas aos clientes pela sua IA Gemini e atendentes.": "Total replies generated and sent to customers by your Gemini AI and representatives.",
  "Respostas autônomas oficiais via e-mail": "Official autonomous replies via email",
  "Pedidos Aguardando Validação": "Requests Awaiting Validation",
  "Pedidos para confirmar": "Requests to confirm",
  "Pedidos Para Confirmar": "Requests To Confirm",
  "Pedidos aguardando validação": "Requests awaiting validation",
  "Intenções de compra e pedidos de agendamento recolhidos pelo agente aguardando a sua confirmação.": "Purchase intentions and booking requests gathered by the agent awaiting your confirmation.",
  "Clique para expandir e gerir pedidos a confirmar": "Click to expand and manage requests to confirm",
  "Clique para gerir": "Click to manage",
  "Nenhum pedido pendente de validação no momento. Todos os pedidos e agendamentos foram tratados.": "There are no pending requests to validate right now. All requests and appointments have been handled.",
  "Nenhum pedido pendente de validação.": "No pending requests to validate.",
  "Nenhum pedido pendente.": "No pending requests.",
  "A carregar pedidos pendentes...": "Loading pending requests...",
  "Confirmar (Enviar E-mail via IA)": "Confirm (Send Email via AI)",
  "Não Disponível / Sugerir Outro (IA)": "Unavailable / Suggest Another (AI)",
  "Marcar como Tratado": "Mark as Handled",
  "Ver todos os pedidos": "View all requests",
  "Pedido": "Request",
  "Pedidos": "Requests",
  "Pedido atualizado.": "Request updated.",
  "Pedido marcado como tratado.": "Request marked as handled.",
  "Confirmação enviada por e-mail ao cliente com sucesso!": "Confirmation sent successfully to the customer by email!",
  "Resposta alternativa enviada por e-mail ao cliente com sucesso!": "Alternative response sent successfully to the customer by email!",
  "Confirme ou sugira alternativas — a IA enviará a resposta oficial por e-mail no contexto da conversa.": "Confirm or suggest alternatives — the AI will send the official email response in the context of the conversation.",
  "Detectados pela IA em e-mails de clientes.": "Detected by AI in customer emails.",
  "Sugerir modelo alternativo": "Suggest alternative model",
  "Estado da Integração de E-mail": "Email Integration Status",
  "Integração de E-mail Oficial (Google Gmail)": "Official Email Integration (Google Gmail)",
  "A carregar estado da integração de e-mail...": "Loading email integration status...",
  "E-mail Conectado": "Email Connected",
  "E-mail Oficial": "Official Email",
  "Conectado": "Connected",
  "Desconectado": "Disconnected",
  "LIGADO": "ON",
  "DESLIGADO": "OFF",
  "Ativo": "Active",
  "Ativa": "Active",
  "Desativado": "Disabled",
  "Desativar": "Disable",
  "Sincronizar E-mails": "Sync Emails",
  "Sincronizar E-mails Agora": "Sync Emails Now",
  "Desconectar E-mail": "Disconnect Email",
  "Última Sincronização": "Last Sync",
  "A verificar...": "Checking...",
  "Provedor Oficial": "Official Provider",
  "Nome de Remetente": "Sender Name",
  "Status do Agente IA": "AI Agent Status",
  "Agente IA": "AI Agent",
  "Ativar respostas automáticas do agente": "Enable agent automatic replies",
  "Desativar respostas automáticas do agente": "Disable agent automatic replies",
  "Clique no interruptor para ativar ou desativar o agente": "Click the switch to activate or deactivate the agent",
  "A integração permite consultar as mensagens da caixa de entrada ligada. Quando as respostas automáticas estão ativadas, o agente pode responder usando as informações e instruções configuradas na conta.": "The integration allows reading messages from the connected inbox. When automatic replies are enabled, the agent can reply using the information and instructions configured on the account.",
  "Agente ativado com sucesso! As respostas automáticas estão ativas.": "Agent enabled successfully! Automatic replies are active.",
  "Agente pausado com sucesso.": "Agent paused successfully.",
  "Sincronização concluída com sucesso!": "Sync completed successfully!",
  "Verificar novos e-mails recebidos e responder com a IA": "Check new incoming emails and reply with AI",
  "Conta de e-mail oficial (Google Gmail) conectada com sucesso! A IA já está pronta para responder aos clientes.": "Official email account (Google Gmail) connected successfully! AI is ready to reply to customers.",
  "E-mail desconectado com sucesso.": "Email disconnected successfully.",
  "Falha na ligação do e-mail": "Email connection failed",
  "A carregar mensagens...": "Loading messages...",
  "Ainda não existem conversas. Quando um cliente enviar um e-mail, ele aparecerá aqui.": "No conversations yet. When a customer sends an email, it will appear here.",
  "Ainda não existem conversas registradas.": "No recorded conversations yet.",
  "Sem conversas": "No conversations",
  "Nenhum contato ainda": "No contacts yet",
  "Clientes & Mensagens": "Customers & Messages",
  "Conversas recebidas": "Received conversations",
  "Conversas centralizadas": "Centralized conversations",
  "Conversa": "Conversation",
  "este cliente": "this customer",
  "Selecione um cliente para abrir a conversa e acompanhar a IA em tempo real.": "Select a customer to open the conversation and follow AI in real time.",
  "Selecione um cliente primeiro.": "Select a customer first.",
  "Atendimento oficial por e-mail ativo · A IA Drexier responde automaticamente em tempo real a todas as mensagens enviadas ao seu e-mail vinculado.": "Official email support active · Drexier AI automatically replies in real time to all messages sent to your linked email.",
  "Atendimento oficial por e-mail ativo • A IA Drexier responde automaticamente em tempo real a todas as mensagens deste cliente.": "Official email support active • Drexier AI automatically replies in real time to all messages from this customer.",
  "Escreva aqui a sua resposta oficial ao cliente... (será enviada diretamente para o e-mail dele)": "Write your official reply to the customer here... (it will be sent directly to their email)",
  "Esta resposta será entregue no e-mail do cliente e registrada como Proprietário.": "This reply will be delivered to the customer's email and logged as Owner.",
  "Enviar por E-mail": "Send via Email",
  "Enviar resposta": "Send reply",
  "Eliminar Conversa": "Delete Conversation",
  "Eliminar toda a conversa deste cliente": "Delete this customer's entire conversation",
  "Eliminar esta mensagem": "Delete this message",
  "Eliminar": "Delete",
  "Conversa eliminada com sucesso.": "Conversation deleted successfully.",
  "Mensagem eliminada com sucesso.": "Message deleted successfully.",
  "Sem mensagens nesta conversa.": "No messages in this conversation.",
  "Resposta oficial entregue com sucesso no e-mail do cliente!": "Official reply delivered successfully to the customer's email!",
  "Mensagem oficial entregue no WhatsApp do cliente!": "Official message delivered to customer WhatsApp!",
  "Nova mensagem": "New message",
  "Novas mensagens ou pedidos aguardando": "New messages or requests awaiting",
  "Aquisição diária de clientes": "Daily customer acquisition",
  "Aquisição de clientes": "Customer acquisition",
  "Clientes adquiridos por dia": "Customers acquired per day",
  "Comparação de novos clientes entre hoje e ontem": "Comparison of new customers between today and yesterday",
  "Teste de estilos de resposta": "Response style testing",
  "Registe variantes para acompanhar os resultados. Os contadores só aumentam quando eventos reais forem ligados.": "Register variants to track results. Counters only increase when real events are linked.",
  "Nome do estilo": "Style name",
  "Ex: Direto e Comercial, Formal Executivo...": "e.g.: Direct & Sales-oriented, Formal Executive...",
  "Estrutura de resposta...": "Response structure...",
  "Guardar estilo": "Save style",
  "Ainda não existem variantes.": "No variants yet.",
  "Eliminar este estilo de resposta?": "Delete this response style?",
  "Cards Estruturados": "Structured Cards",
  "Cards Estruturados do Negócio": "Structured Business Cards",
  "Complete as informações do seu negócio": "Complete your business information",
  "Adicione informações claras sobre produtos, políticas e atendimento para dar mais contexto às respostas do agente. Revise as respostas e mantenha esta base atualizada na aba Negócio.": "Add clear information about products, policies, and support to give more context to the agent's replies. Review responses and keep this knowledge base updated in the Business tab.",
  "Completar Cards do Negócio": "Complete Business Cards",
  "Gerir informações na aba Negócio →": "Manage information in the Business tab →",
  "Índice da base": "Base Index",
  "15/100 Índice da base": "15/100 Base Index",
  "0 / 12 preenchidos": "0 / 12 completed",
  "Cards prioritários aguardando preenchimento:": "Priority cards awaiting completion:",
  "Adicione mais dados para atingir o nível de treino ideal": "Add more data to achieve optimal training level",
  "A base ainda tem poucas informações estruturadas. Adicione produtos, políticas e orientações para dar mais contexto às respostas do agente.": "The base currently has limited structured information. Add products, policies, and guidelines to give more context to the agent's responses.",
  "A base contém várias informações do negócio. Mantenha os dados atualizados e reveja as respostas do agente.": "The base contains substantial business information. Keep data up to date and review agent responses.",
  "Organize produtos, políticas e orientações para dar contexto ao agente. Este indicador acompanha o preenchimento da base, não mede a precisão das respostas.": "Organize products, policies, and guidelines to give context to the agent. This indicator tracks knowledge base completion, not answer accuracy.",
  "Cards configurados: 0 / 12 • Treinamentos: 0": "Configured cards: 0 / 12 • Trainings: 0",
  "+ Novo Card Personalizado": "+ New Custom Card",
  "+ Novo Tópico de Treinamento": "+ New Training Topic",
  "+ Novo estilo": "+ New style",
  "Escolha uma categoria para o seu card personalizado:": "Choose a category for your custom card:",
  "Novo Card Personalizado": "New Custom Card",
  "Produtos e Preços": "Products & Prices",
  "Serviços e Procedimentos": "Services & Procedures",
  "Horários de Atendimento": "Business Hours",
  "Marcações e Agendamentos": "Appointments & Scheduling",
  "Formas de Pagamento": "Payment Methods",
  "Formas de Pagamento e Faturação": "Payment Methods & Invoicing",
  "Campanhas e Descontos": "Campaigns & Discounts",
  "Trocas e Devoluções": "Exchanges & Returns",
  "Envios e Prazos": "Shipping & Deadlines",
  "Localização e Morada": "Location & Address",
  "Canais Oficiais de Contacto": "Official Contact Channels",
  "Regras de Suporte e Atendimento": "Support & Service Rules",
  "Regras de Atendimento": "Service Rules",
  "Personalizado": "Custom",
  "Tópico de Treinamento": "Training Topic",
  "Tópicos de Treinamento": "Training Topics",
  "Tópicos & Regulamentos Cadastrados": "Registered Topics & Regulations",
  "Ainda não cadastrou tópicos de treinamento. Use o formulário acima para escrever ou transferir o seu primeiro regulamento!": "No training topics registered yet. Use the form above to write or upload your first regulation!",
  "Central de Treinamento Livre da IA & Documentos": "Free AI Training Center & Documents",
  "Treinamento & Documentos": "Training & Documents",
  "Treinamento Profundo com Ficheiros": "Deep Training with Files",
  "Treinamento ilimitado com documentos": "Unlimited training with documents",
  "Base de conhecimento completa do negócio": "Complete business knowledge base",
  "Base de conhecimento do agente": "Agent knowledge base",
  "Instrua a sua IA": "Instruct your AI",
  "Instruções ao agente": "Agent instructions",
  "Instruções e regras personalizadas à IA": "Custom instructions and rules for AI",
  "Instruções personalizadas": "Custom instructions",
  "Regras de Sigilo para a IA:": "AI Confidentiality Rule:",
  "A IA só deve informar se existe disponibilidade para o produto solicitado. Nunca revela números de stock ou dados sensíveis. Apenas \"Temos em stock\" ou \"Não temos em stock de momento\".": "The AI must only state whether the requested product is available. Never reveal stock counts or sensitive numbers. Use only \"We have it in stock\" or \"We do not have it in stock at the moment\".",
  "Stock": "Stock",
  "Stock de Produtos": "Product Stock",
  "Guardar Stock": "Save Stock",
  "Stock guardado com sucesso. A IA irá apenas informar se tem ou não o produto.": "Stock saved successfully. The AI will only state whether or not the product is available.",
  "Erro ao guardar stock.": "Error saving stock.",
  "Erro ao carregar stock.": "Error loading stock.",
  "Nenhum produto encontrado no card": "No product found in card",
  "Nenhum produto encontrado no card \"Produtos e Preços\".": "No products found in the \"Products & Prices\" card.",
  "Baseado no card \"Produtos e Preços\". A IA apenas informa ao cliente se tem ou não o produto disponível, nunca a quantidade.": "Based on the \"Products & Prices\" card. The AI only informs the customer if the product is available, never the quantity.",
  "Em stock?": "In stock?",
  "Produto": "Product",
  "Preço": "Price",
  "Quantidade (apenas proprietário)": "Quantity (owner only)",
  "0 produtos": "0 products",
  "0 palavras": "0 words",
  "0 caracteres": "0 characters",
  "0 tópicos": "0 topics",
  "Transferir / Carregar Documento Oficial (PDF, Word DOCX, TXT, MD, CSV)": "Upload Official Document (PDF, Word DOCX, TXT, MD, CSV)",
  "Carregue catálogos, regulamentos internos e preçários (PDF, Word DOCX, TXT) sem limites.": "Upload catalogs, internal guidelines, and price lists (PDF, Word DOCX, TXT) with no limits.",
  "Clique aqui ou arraste o ficheiro para carregar automaticamente o conteúdo.": "Click here or drag a file to automatically load its content.",
  "Selecionar Documento": "Select Document",
  "Campo de Escrita Livre (Área de Texto Sem Limites)": "Free-form Text Area (Unlimited)",
  "Escreva livremente regulamentos, normas, contratos e políticas ou transfira documentos (PDF, DOCX, TXT).": "Write regulations, standards, contracts, and policies freely or upload documents (PDF, DOCX, TXT).",
  "Escreva aqui detalhadamente sobre a sua empresa... Cole regulamentos completos, termos de compra, manuais da equipe, exceções de atendimento, políticas de preços... Quanto maior o volume, mais assertivo será o atendimento da IA!": "Write in detail about your company here... Paste complete regulations, terms of purchase, team manuals, support exceptions, pricing policies... The more detailed the context, the more accurate your AI support will be!",
  "Título do Tópico / Regulamento": "Topic / Regulation Title",
  "Ex: Regulamento Interno 2026, Manual de Garantias e Trocas...": "e.g.: Internal Guidelines 2026, Warranty & Returns Manual...",
  "Marcar como Tópico Isolado de Conhecimento (Recomendado)": "Mark as Isolated Knowledge Topic (Recommended)",
  "Diretrizes isoladas que a IA consulta com máxima fidelidade.": "Isolated guidelines that the AI references with surgical accuracy.",
  "Ao marcar um treino como": "When marking a training as",
  "Tópico Isolado": "Isolated Topic",
  ", o conteúdo fica identificado separadamente para ajudar a equipa a organizar as informações.": ", the content is identified separately to help the team organize information.",
  "Este conteúdo será identificado separadamente para ajudar a organizar as informações disponíveis ao agente.": "This content will be identified separately to help organize information available to the agent.",
  "Enviar Regulamentos & Treinar IA": "Submit Regulations & Train AI",
  "Guardar Tópico de Treinamento": "Save Training Topic",
  "Atualizar Tópico de Treinamento": "Update Training Topic",
  "Tópico de treinamento adicionado à base da IA!": "Training topic added to AI knowledge base!",
  "Tópico de treinamento atualizado com sucesso.": "Training topic updated successfully.",
  "Tópico de treinamento eliminado.": "Training topic deleted.",
  "Eliminar o tópico de treinamento": "Delete training topic",
  "Por favor preencha o título e o conteúdo do treinamento.": "Please fill in both the title and the content of the training topic.",
  "Erro ao carregar documento.": "Error loading document.",
  "A carregar e extrair texto de": "Loading and extracting text from",
  "carregado com sucesso.": "uploaded successfully.",
  "Detalhe como cada serviço é realizado e quanto custa para orientar os clientes.": "Detail how each service is performed and how much it costs to guide customers.",
  "Ex: Atendimento de apoio técnico de Segunda a Sexta das 10h às 18h": "e.g.: Technical support Monday to Friday from 10:00 AM to 6:00 PM",
  "Ex: 24 horas de antecedência": "e.g.: 24 hours in advance",
  "Deixe claro os métodos de pagamento para acelerar o fechamento de pedidos.": "State payment methods clearly to speed up order completion.",
  "Ex: Emitimos fatura com NIF. Aceitamos transferências bancárias com envio de comprovativo": "e.g.: We issue official tax invoices. We accept bank transfers with proof of payment",
  "A IA poderá oferecer condições especiais aos clientes interessados.": "The AI can offer special conditions to interested customers.",
  "Regras claras de troca trazem segurança aos clientes e evitam reclamações.": "Clear return policies give customers confidence and prevent disputes.",
  "A IA responderá na hora o valor e prazo de envio quando o cliente perguntar.": "The AI will answer shipping rates and delivery times instantly when customers ask.",
  "Facilite para o cliente encontrar o seu estabelecimento físico.": "Make it easy for customers to find your physical location.",
  "Ex: Em frente ao metro, contamos com estacionamento gratuito para clientes": "e.g.: Across from the subway station, with free parking for customers",
  "Perguntas mais repetidas pelos clientes acompanhadas das respostas oficiais.": "The most frequently asked customer questions alongside their official answers.",
  "Oriente o agente como lidar com situações delicadas ou exigências especiais.": "Guide the agent on how to handle sensitive situations or special requests.",
  "Ex: Atendimento Prioritário": "e.g.: Priority Support",
  "Faturação": "Billing",
  "Faturação e Plano de Subscrição SaaS": "Billing & SaaS Subscription Plan",
  "Gestão da subscrição mensal, emissão de faturas e controlo seguro de pagamentos via Stripe.": "Management of monthly subscription, invoice generation, and secure Stripe payment processing.",
  "PLANO OFICIAL • ACESSO COMPLETO SAAS": "OFFICIAL PLAN • COMPLETE SAAS ACCESS",
  "Plano Business": "Business Plan",
  "Plano Ativo (59€/mês)": "Active Plan (€59/month)",
  "Sem Plano Ativo": "No Active Plan",
  "A sua subscrição está ativa e regularizada!": "Your subscription is active and in good standing!",
  "Acesso total desbloqueado à IA Drexier, respostas automáticas oficiais por e-mail e treinamento de ficheiros.": "Full access unlocked to Drexier AI, official automated email replies, and file training.",
  "Ativar Plano Business (59€/mês)": "Activate Business Plan (€59/month)",
  "Cobrança mensal no cartão • Cancele quando quiser": "Monthly charge to card • Cancel anytime",
  "Gerir Cartão e Descarregar Faturas na Stripe": "Manage Card & Download Invoices on Stripe",
  "Atualizar Cartão de Pagamento na Stripe": "Update Payment Card on Stripe",
  "Atualize os dados do seu cartão na Stripe para manter o atendimento com IA ativo.": "Update your card details on Stripe to keep AI support active.",
  "Falha no Pagamento do Cartão": "Card Payment Failure",
  "O último pagamento mensal foi recusado pela sua entidade bancária. Atualize os dados do seu cartão na Stripe para manter o atendimento ativo.": "The last monthly payment was declined by your bank. Update your card on Stripe to keep support active.",
  "A aceder ao portal seguro...": "Opening secure portal...",
  "A preparar checkout seguro da Stripe...": "Preparing secure Stripe checkout...",
  "Já pagou? Clique aqui para verificar com a Stripe imediatamente": "Already paid? Click here to verify with Stripe immediately",
  "Já paguei / Atualizar Status": "I have paid / Refresh Status",
  "Aguardando pagamento confirmado": "Awaiting confirmed payment",
  "Próxima renovação automática:": "Next automatic renewal:",
  "Pagamento efetuado com sucesso! O seu Plano Business (59€/mês) está ativo e o acesso total está desbloqueado.": "Payment completed successfully! Your Business Plan (€59/month) is active and full access is unlocked.",
  "O processo de subscrição foi interrompido. Pode aderir ao Plano Business a qualquer momento na aba Faturação.": "The subscription process was interrupted. You can join the Business Plan at any time in the Billing tab.",
  "Não foi possível abrir o portal da Stripe.": "Could not open Stripe portal.",
  "Instruções do Agente": "Agent Instructions",
  "Defina o tom, o estilo e as regras gerais de atendimento.": "Define the tone, style, and general guidelines for customer support.",
  "Escreva as instruções para o agente.": "Write instructions for the agent.",
  "Guardar instruções": "Save instructions",
  "Respostas obrigatórias": "Mandatory responses",
  "Defina mensagens que devem ser usadas em etapas específicas. Deixe em branco as que não quiser configurar.": "Define messages that must be used at specific stages. Leave blank any you do not wish to set.",
  "Primeira resposta": "Initial reply",
  "Quando o cliente demonstrar intenção de compra/marcação": "When customer expresses purchase or booking intent",
  "Quando não souber a resposta": "When the answer is unknown",
  "Encerramento": "Closing",
  "Guardar respostas": "Save responses",
  "Conta": "Account",
  "Nome de usuário": "Username",
  "Email cadastrado": "Registered email",
  "Descrição do negócio": "Business description",
  "Língua do agente": "Agent language",
  "Guardar conta": "Save account",
  "Personalize a sua conta e o agente": "Customize your account and the agent",
  "Configure nas abas ao lado as regras, tom de voz e respostas do suporte.": "Configure guidelines, tone of voice, and support responses in the tabs alongside.",
  "Confirmar saída?": "Confirm sign out?",
  "Tem a certeza de que deseja sair da sua conta?": "Are you sure you want to sign out of your account?",
  "Cancelar": "Cancel",
  "Fechar": "Close",
  "Confirmar": "Confirm",
  "Guardar alterações": "Save changes",
  "Funcionalidade Bloqueada": "Feature Locked",
  "Esta funcionalidade está disponível exclusivamente para assinantes do": "This feature is available exclusively to subscribers of the",
  "Esta funcionalidade está disponível exclusivamente para assinantes do Plano Business.": "This feature is available exclusively to Business Plan subscribers.",
  "Ative a sua subscrição para desbloquear o acesso total ao Drexier AI.": "Activate your subscription to unlock full access to Drexier AI.",
  "59€/mês": "€59/month",
  "/mês": "/month",
  "/ mês": "/ month",
  "Respostas automáticas configuráveis por e-mail": "Configurable automated email replies",
  "Integração Gmail & respostas automáticas": "Gmail integration & automated replies",
  "Dashboard completo de conversões": "Complete conversion dashboard",
  "Sem fidelização • Cancele a qualquer momento • Pagamento seguro via Stripe": "No commitment • Cancel anytime • Secure payment via Stripe",
  "Tem a certeza de que deseja eliminar esta mensagem?": "Are you sure you want to delete this message?",
  "Tem a certeza de que deseja eliminar o card": "Are you sure you want to delete card",
  "Tem a certeza de que deseja eliminar todas as mensagens e o histórico de": "Are you sure you want to delete all messages and history for",
  "Ocorreu um erro.": "An error occurred.",
  "Pedido registado no dashboard.": "Request logged on dashboard.",
  "Pedido aguardando confirmação do proprietário.": "Request awaiting owner confirmation.",
  "Hoje": "Today",
  "Ontem": "Yesterday",
  "Data": "Date",
  "Hora": "Time",
  "Status": "Status",
  "Cliente": "Customer",
  "Assunto": "Subject",
  "Mensagem": "Message",
  "Nome": "Name",
  "Email": "Email",
  "Telefone": "Phone",
  "Canal": "Channel",
  "Channel": "Channel",
  "Detalhes": "Details",
  "Desempenho Geral": "Overall Performance",
  "Calibração Inicial": "Initial Calibration",
  "Acesso": "Access",
  "A IA responde desde": "The AI has been responding since",
  "Connected by account owner": "Connected by account owner",
  "Drexier Email Assistant • Product Preview": "Drexier Email Assistant • Product Preview",
  "Illustrative conversation • Your settings determine how replies are handled": "Illustrative conversation • Your settings determine how replies are handled",
  "Illustrative interface": "Illustrative interface",
  "Your knowledge": "Your knowledge",
  "Workspace agent": "Workspace agent",
  "Business information reviewed • Example workflow": "Business information reviewed • Example workflow",
  "Drexier — Atendimento inteligente para a sua empresa": "Drexier — Intelligent support for your business",
  "Switch to English": "Switch to English",
  "Switch to Portuguese": "Mudar para Português",
  "AI PLATFORM": "AI PLATFORM",
  "Acompanhe": "Track",
  "Ao aderir, o valor de 59€ é cobrado no seu cartão através do checkout seguro da Stripe e todas as funcionalidades ficam liberadas.": "Upon subscribing, €59 is charged to your card via secure Stripe checkout and all features are unlocked.",
  "Ao conectar a sua conta através da página oficial da Google, o Drexier recebe autorização segura para ler dúvidas recebidas e enviar respostas inteligentes conduzidas pela IA.": "By connecting your account through Google's official page, Drexier receives secure authorization to read incoming questions and send intelligent replies powered by AI.",
  "Atualizar": "Refresh",
  "Automação de Respostas": "Automated Replies",
  "Como as conversas são organizadas e acompanhadas.": "How conversations are organized and tracked.",
  "Como o retorno é preparado e enviado.": "How replies are prepared and sent.",
  "Como pedidos que precisam de acompanhamento são identificados.": "How requests requiring follow-up are identified.",
  "Como produtos, preços e políticas são consultados durante o atendimento.": "How products, prices, and policies are referenced during support.",
  "Configuração da Stripe Pendente no ficheiro .env": "Stripe configuration pending in .env file",
  "Configuração de Credenciais Pendente no ficheiro .env": "Credentials configuration pending in .env file",
  "Contexto do agente:": "Agent context:",
  "Dashboard e Métricas em Tempo Real": "Dashboard & Real-time Metrics",
  "Deutsch": "Deutsch",
  "English": "English",
  "Español": "Español",
  "Français": "Français",
  "Português": "Português",
  "FAQ": "FAQ",
  "Gerir Pedidos": "Manage Requests",
  "Informações do negócio": "Business information",
  "Integração": "Integration",
  "Não foi possível carregar o estado do e-mail:": "Could not load email status:",
  "Oportunidades": "Opportunities",
  "PT · EN": "PT · EN",
  "Para ativar a ligação com um clique, adicione as chaves no seu ficheiro": "To enable one-click connection, add the keys to your file",
  "Para ativar cobranças reais com cartão e faturação automática, preencha no seu ficheiro": "To enable real card charges and automated billing, fill in your file",
  "Regra de Sigilo para a IA:": "AI Confidentiality Rule:",
  "Subscreva com 1 Clique e Ative a sua Conta Imediatamente": "Subscribe with 1 Click & Activate your Account Immediately",
  "Texto da resposta": "Reply text",
  "Validação de Pedidos & Marcações": "Validation of Requests & Bookings",
  "Visão geral": "Overview",
  "Erro ao carregar mensagens:": "Error loading messages:",
  "Erro ao carregar status de faturação:": "Error loading billing status:",
  "Erro ao verificar subscrição.": "Error verifying subscription.",
  "Erro na autorização do fornecedor de e-mail.": "Error authorizing email provider.",
  "Erro no carregamento:": "Error loading:",
  "clientes": "customers",
  "cliente": "customer",
  "Erro ao carregar pedidos:": "Error loading requests:"
};

  const translationsPt = {
  "Overview": "Visão geral",
  "Performance": "Desempenho",
  "Comparison": "Comparativo",
  "Frequently Asked Questions": "Perguntas Frequentes",
  "About the Software": "Sobre o Software",
  "Sign in": "Entrar",
  "Sign in to Account": "Entrar na Conta",
  "Sign in to Platform": "Entrar na Plataforma",
  "Get Started": "Começar Agora",
  "Get Started Today": "Comece Hoje Mesmo",
  "Create account": "Criar conta",
  "Create Account & Get Started": "Criar Conta e Começar",
  "Create Account / Get Started": "Criar Conta / Começar Agora",
  "Back to home": "Voltar à página inicial",
  "Back": "Voltar",
  "Back to customer list": "Voltar à lista de clientes",
  "Autonomous Customer Support & Sales Technology": "Tecnologia Autônoma de Atendimento & Vendas",
  "Customer support and sales with more context": "Atendimento ao cliente e vendas com mais contexto",
  "Customer support and sales with": "Atendimento ao cliente e vendas com",
  "more context": "mais contexto",
  "The definitive tool to turn your company's emails and contacts into sales and satisfied customers with AI.": "A ferramenta definitiva para transformar os e-mails e contactos da sua empresa em vendas e clientes satisfeitos com IA.",
  "See how it works": "Ver como funciona",
  "Guided setup": "Configuração guiada",
  "Gmail integration": "Integração com Gmail",
  "Integration with Google Gmail": "Integração com Google Gmail",
  "You control the agent": "Controle do agente por você",
  "Agent control in the platform": "Controlo do agente na plataforma",
  "Alex Morgan • Customer": "Alex Morgan • Customer",
  "Subject: Re: Product information": "Subject: Re: Product information",
  "Inbound Inquiry": "Inbound Inquiry",
  "Incoming email": "Incoming email",
  "Business context": "Business context",
  "Draft response • Review before sending": "Draft response • Review before sending",
  "Verified AI Agent": "Verified AI Agent",
  "Active AI Agents": "Active AI Agents",
  "Active integration • Configurable agent:": "Integração ativa • Agente configurável:",
  "Connect your Google Gmail in seconds": "Conecte o seu Google Gmail em poucos segundos",
  "Authenticate with one click via official OAuth 2.0 authorization.": "Autentique com um clique através da autorização OAuth 2.0 oficial.",
  "Authorize sending and reading emails on Google's official, secure screen.": "Autorize o envio e leitura de e-mails na tela oficial e segura da Google.",
  "Connect your company's official Google Gmail business account so Drexier AI can answer and handle conversations with your customers directly by email.": "Conecte a conta comercial do Google Gmail da sua empresa para que a IA Drexier atenda e conduza conversas com os seus clientes diretamente por e-mail.",
  "Connect Official Google Gmail": "Conectar Google Gmail Oficial",
  "Connect with Google": "Conectar com a Google",
  "Grant Permissions": "Conceda as Permissões",
  "Authorize Gmail and pause the agent whenever you want": "Autorize o Gmail e pause o agente quando quiser",
  "Google Gmail • Configurable automated replies": "Google Gmail • Respostas automáticas configuráveis",
  "Google Gmail:": "Google Gmail:",
  "Official Support": "Atendimento Oficial",
  "Official Email Channel (Google Gmail)": "Canal E-mail Oficial (Google Gmail)",
  "Official direct connection to the inbox for real-time monitoring and continuous replies.": "Conexão oficial direta com a caixa de entrada para monitorização e respostas reais contínuas.",
  "Ready to put your company's customer support on autopilot?": "Pronto para colocar o atendimento da sua empresa no piloto automático?",
  "Looking to organize your business customer support?": "Quer organizar o atendimento do seu negócio?",
  "Create your account, configure your company information, and connect your business email.": "Crie a sua conta, configure as informações da empresa e ligue o e-mail comercial.",
  "Create your account, configure business information, and explore the support tools.": "Crie a sua conta, configure as informações do negócio e explore as ferramentas de atendimento.",
  "Response time": "Tempo de resposta",
  "24/7 Availability": "Disponibilidade 24/7",
  "Availability": "Disponibilidade",
  "Inbox organization": "Organização da caixa",
  "Order & request visibility": "Visibilidade dos pedidos",
  "More visibility": "Mais visibilidade",
  "Follow-up": "Acompanhamento",
  "Customer follow-up": "Acompanhamento de clientes",
  "Track every conversation": "Acompanhe cada conversa",
  "Track messages and requests on the dashboard": "Acompanhe mensagens e pedidos no painel",
  "Operational overview": "Visão da operação",
  "Clear overview of daily contacts, answered messages, and customer conversion rates.": "Visão clara de contactos diários, mensagens respondidas e taxas de conversão de clientes.",
  "More clarity to follow customer support": "Mais clareza para acompanhar o atendimento",
  "Get a clear view of incoming messages and opportunities that need attention.": "Tenha uma visão clara das mensagens recebidas e das oportunidades que precisam de atenção.",
  "Centralize requests and messages so the team knows which conversations require follow-up.": "Centralize pedidos e mensagens para que a equipa saiba quais conversas precisam de acompanhamento.",
  "Organize email conversations, give the agent context about your business, and track replies in one place. You decide when to enable automation and can step in whenever needed.": "Organize as conversas por e-mail, dê ao agente informações sobre o seu negócio e acompanhe as respostas num só lugar. Você decide quando ativar a automação e pode intervir sempre que precisar.",
  "Automate repetitive follow-up steps": "Automatize etapas repetitivas do acompanhamento",
  "The dashboard helps you view customers and follow up on email conversations.": "O painel ajuda a visualizar os clientes e a dar seguimento às conversas por e-mail.",
  "Organize your business context": "Organize o contexto do seu negócio",
  "Organize products, policies, and FAQs to give context to the agent.": "Organize produtos, políticas e respostas frequentes para dar contexto ao agente.",
  "Organize the information used by the agent": "Organize as informações usadas pelo agente",
  "The platform gathers information about products, stock, and policies to give context to the agent. The team can update this data and track conversations in a single dashboard.": "A plataforma reúne informações sobre produtos, stock e políticas para dar contexto ao agente. A equipa pode atualizar esses dados e acompanhar as conversas num único painel.",
  "Enable replies when you are ready": "Ative as respostas quando estiver pronto",
  "Enable or pause automated replies and configure business context.": "Ative ou pause as respostas automáticas e configure o contexto do negócio.",
  "Keep business information complete and up to date.": "Mantenha as informações do negócio completas e atualizadas.",
  "Add clear guidelines and keep them up to date.": "Adicione orientações claras e mantenha-as atualizadas.",
  "Visual example, no real data": "Exemplo visual, sem dados reais",
  "Visual example, does not represent measured results.": "Exemplo visual, não representa resultados medidos.",
  "Visual examples of how to organize conversations, business context, and opportunities. Results vary depending on operations and account settings.": "Exemplos visuais de como organizar conversas, contexto do negócio e oportunidades. Os resultados variam conforme a operação e a configuração da conta.",
  "Qualitative representation, without performance metrics.": "Representação qualitativa, sem métricas de desempenho.",
  "Illustrative trend": "Tendência ilustrativa",
  "Illustrative graph of upward sales trend, without real data": "Gráfico ilustrativo de vendas em tendência crescente, sem dados reais",
  "Before vs. After Automation": "Antes vs. Depois da Automação",
  "Functional comparison": "Comparação funcional",
  "Before (Manual)": "Antes (Manual)",
  "After (Drexier AI)": "Depois (Drexier IA)",
  "Traditional Manual Support": "Atendimento Manual Tradicional",
  "Drexier Intelligent Automation": "Automação Inteligente Drexier",
  "Manual Response vs. Drexier Automation": "Resposta Manual vs. Automação Drexier",
  "A practical comparison of how manual support and automation can support message handling. Does not represent a benchmark study nor guarantee commercial results.": "Uma comparação prática de como o atendimento manual e a automação podem apoiar a gestão de mensagens. Não representa um estudo de desempenho nem garante resultados comerciais.",
  "Automation helps respond with greater consistency, while manual support depends on team availability.": "A automação pode ajudar a responder com mais consistência, enquanto o atendimento manual depende da disponibilidade da equipa.",
  "Aspect": "Aspeto",
  "Response speed:": "Agilidade no atendimento:",
  "Response time depends on working hours and team availability.": "O tempo de resposta depende dos horários e da disponibilidade de quem atende.",
  "Response time depends on configuration and service": "O tempo de resposta depende da configuração e do serviço",
  "When enabled and configured, the agent can prepare replies based on business context.": "Quando ativado e configurado, o agente pode preparar respostas com base nas informações do negócio.",
  "Can reply when enabled": "Pode responder quando ativada",
  "Team hours": "Horário da equipa",
  "Coverage varies according to team working hours": "A cobertura varia conforme os horários da equipa",
  "Depends on availability": "Depende da disponibilidade",
  "Depends on the team": "Depende da equipa",
  "Manual handling": "Gestão manual",
  "Manual lookup": "Consulta manual",
  "Manual lookup of products and policies": "Consulta manual de produtos e políticas",
  "The person answering looks up and applies available company information.": "A pessoa que atende consulta e aplica as informações disponíveis da empresa.",
  "Structured, contextual knowledge base": "Base de conhecimento estruturada e contextual",
  "Configurable context": "Contexto configurável",
  "Business context:": "Contexto do negócio:",
  "The agent uses the data and instructions added by your team; review replies and keep the base updated.": "O agente utiliza os dados e as instruções que a equipa adiciona à plataforma; reveja as respostas e mantenha a base atualizada.",
  "Product information configured by you": "Informações de produtos configuradas por si",
  "Products, policies and FAQs": "Products, policies and FAQs",
  "Message & request management": "Gestão de mensagens e pedidos",
  "Follow-up is handled by the team using their existing processes.": "O acompanhamento é feito pela equipa com os processos que já utiliza.",
  "Manual and assisted": "Manual e assistido",
  "Requests flagged for validation": "Pedidos sinalizados para validação",
  "Requests detected in messages can appear on the dashboard for review and confirmation.": "Pedidos detetados nas mensagens podem aparecer no painel para revisão e confirmação.",
  "AI identifies purchase/booking intents and allows quick owner confirmation.": "A IA identifica intenções de compra/reserva e permite confirmação rápida pelo proprietário.",
  "Turn on or off": "Ligar ou desligar",
  "On or off": "On or off",
  "You control automation": "You control automation",
  "Human control": "Human control",
  "Configured by your team": "Configured by your team",
  "Configurable automation:": "Automação configurável:",
  "Support with configurable agent": "Atendimento com agente configurável",
  "Automated assistance": "Apoio automatizado",
  "Conversation history accessible to the team": "Histórico de conversas acessível à equipa",
  "Customer interactions": "Interações com clientes",
  "Interactions recorded and retained": "Interações registradas e retidas",
  "Requests and opportunities": "Pedidos e oportunidades",
  "Well-organized opportunities": "Oportunidades bem organizadas",
  "Trust and visibility:": "Confiança e visibilidade:",
  "Security and control:": "Segurança e controlo:",
  "Security & Compliance": "Segurança & Conformidade",
  "Official PCI-DSS Level 1 Compliance": "Conformidade PCI-DSS Nível 1 Oficial",
  "256-bit SSL Banking Grade Encryption": "Criptografia Bancária SSL 256-bit",
  "Mandatory 3D Secure / SCA Anti-fraud": "3D Secure / SCA Antifraude Obrigatório",
  "Stripe with mandatory 3D Secure / SCA, address verification (AVS), and banking encryption.": "Stripe com 3D Secure / SCA obrigatório, validação de morada (AVS) e criptografia bancária.",
  "Secure Payment & Anti-fraud Protection": "Pagamento Seguro & Proteção Antifraude",
  "No Commitment • Free Cancellation": "Sem Fidelização • Cancelamento Livre",
  "Frequently Asked Questions (FAQ)": "Perguntas Frequentes (FAQ)",
  "Frequently Asked Questions about the Software": "Perguntas Frequentes sobre o Software",
  "Common Questions": "Dúvidas Comuns",
  "Everything you need to understand about the operation, security, and setup of the Drexier platform.": "Tudo o que precisa de compreender sobre o funcionamento, segurança e implementação da plataforma Drexier.",
  "What is Drexier and how does it work in practice?": "O que é o Drexier e como funciona na prática?",
  "Drexier helps organize email customer support. After connecting your account and configuring business information, you can track messages and, when enabled, use the agent to prepare or send responses according to account settings.": "O Drexier ajuda a organizar o atendimento por e-mail. Depois de ligar a conta e configurar as informações do negócio, pode acompanhar as mensagens e, quando ativado, usar o agente para preparar ou enviar respostas de acordo com as definições da conta.",
  "How does Drexier connect to my official Google Gmail email?": "Como o Drexier se conecta ao meu e-mail oficial Google Gmail?",
  "The connection is established through the Google authorization flow presented by the platform. Review requested permissions before granting access; you can disconnect the integration in account settings at any time.": "A ligação é feita através do fluxo de autorização Google apresentado pela plataforma. Reveja as permissões solicitadas antes de autorizar o acesso e pode desligar a integração nas configurações da conta.",
  "Can the AI invent incorrect prices, products or deadlines (hallucinations)?": "A IA pode inventar preços, produtos ou prazos incorretos (alucinações)?",
  "As with any AI system, incorrect answers can occur. Set clear instructions, keep data up to date, and review responses, especially before sending key details on pricing, stock, or policies.": "Como em qualquer sistema de IA, podem ocorrer respostas incorretas. Configure instruções claras, mantenha os dados atualizados e reveja as respostas, sobretudo antes de enviar informações importantes sobre preços, stock ou políticas.",
  "How does validation of purchase orders or appointments work?": "Como funciona a validação de pedidos de compra ou agendamentos?",
  "When a message is identified as an order or request, it can appear on the dashboard for validation. Review details and confirm or reply to the customer according to your company's procedures.": "Quando uma mensagem é identificada como um pedido, pode aparecer no painel para validação. Reveja os detalhes e confirme ou responda ao cliente conforme os procedimentos da sua empresa.",
  "Can I turn off the agent or intervene manually whenever I want?": "Posso desligar o agente ou intervir manualmente quando desejar?",
  "Yes. You can activate or pause the agent via the toggle switch in the Messages tab and reply manually to conversations available in the platform.": "Sim. Pode ativar ou pausar o agente pelo interruptor na aba Mensagens e responder manualmente às conversas disponíveis na plataforma.",
  "Do I need technical skills or developers to configure it?": "Preciso de conhecimento técnico ou programadores para configurar?",
  "No programming is required to use core features. You can connect email and fill in business information directly through the interface.": "Não é necessário programar para utilizar as funções principais. Pode ligar o e-mail e preencher as informações do negócio pela interface. A disponibilidade de ajuda adicional depende do suporte oferecido pela plataforma.",
  "About Drexier Platform": "Sobre a Plataforma Drexier",
  "About Us": "Sobre Nós",
  "Our Philosophy": "Conheça a Nossa Filosofia",
  "What We Do": "O Que Fazemos",
  "How We Do It": "Como Fazemos",
  "Why We Are Different": "Porque Somos Diferentes",
  "We help teams organize their inbox, follow up with customers, and manage email replies powered by artificial intelligence.": "Ajudamos equipas a organizar a caixa de entrada, acompanhar clientes e gerir respostas por e-mail com apoio de inteligência artificial.",
  "Drexier combines message management, configurable business context, and direct control over automation, so your team can adapt support to their own processes.": "O Drexier combina gestão de mensagens, contexto configurável do negócio e controlo direto sobre a automação, para que a equipa possa adaptar o atendimento aos seus próprios processos.",
  "Technology developed with an uncompromising focus on reliability, visual elegance, and real financial results.": "Tecnologia desenvolvida com foco intransigente em confiabilidade, elegância visual e resultados financeiros reais.",
  "Corporate customer support and sales platform powered by autonomous artificial intelligence.": "Plataforma corporativa de atendimento e vendas conduzidas por inteligência artificial autônoma.",
  "© 2026 Drexier Technologies. All rights reserved.": "© 2026 Drexier Technologies. Todos os direitos reservados.",
  "Full name": "Nome completo",
  "Professional email": "Email profissional",
  "Password": "Senha",
  "Password (minimum 8 characters, with letter and number)": "Senha (mínimo 8 caracteres, com letra e número)",
  "Confirm password": "Confirmar senha",
  "Business type": "Tipo de negócio",
  "Select a segment": "Selecione o segmento",
  "Services": "Serviços",
  "Sales": "Vendas",
  "Services and sales": "Serviços e vendas",
  "Other": "Outro",
  "Other Custom": "Outro Personalizado",
  "Your name or company name": "Seu nome ou da empresa",
  "Emergency contact": "Contato de emergência",
  "contact@company.com": "contato@empresa.com",
  "you@company.com": "seuemail@empresa.com",
  "Intelligent, organized customer support.": "Atendimento ao cliente inteligente e organizado.",
  "Dashboard": "Dashboard",
  "Messages": "Mensagens",
  "Reports": "Relatórios",
  "Business": "Negócio",
  "Settings": "Configurações",
  "Sign out": "Sair",
  "Menu": "Menu",
  "Navigation": "Navegação",
  "Customer support overview": "Visão geral do atendimento",
  "Customer conversation history": "Histórico de conversas com clientes",
  "Agent performance and conversions": "Desempenho e conversões do agente",
  "Agent knowledge base and training": "Base de conhecimento e treinamento do agente",
  "Account preferences and integrations": "Preferências da conta e integrações",
  "Activate the Business Plan (€59/month) to unlock your Drexier AI": "Ative o Plano Business (59€/mês) para desbloquear a sua IA Drexier",
  "Access to automated email replies when the agent is enabled, plus training tools.": "Acesso às respostas automáticas por e-mail quando o agente estiver ativado, além das ferramentas de treinamento.",
  "Activate Subscription": "Ativar Subscrição",
  "Subscribe to Business Plan (€59/month)": "Subscrever Plano Business (59€/mês)",
  "Requires active Business Plan (€59/month)": "Requer Plano Business ativo (59€/mês)",
  "Business Plan subscription (€59/month) required.": "Subscrição do Plano Business (59€/mês) necessária.",
  "New Customers Today": "Novos Clientes Hoje",
  "New customers today": "Novos clientes hoje",
  "New customers registered today compared to the previous day.": "Novos clientes registados hoje em comparação com o dia anterior.",
  "Previous day: 0": "Dia anterior: 0",
  "Today vs. previous day • Continuous volume": "Hoje vs. dia anterior • Volume contínuo",
  "Acquired Customers": "Clientes Adquiridos",
  "Acquired customers": "Clientes adquiridos",
  "Cumulative number of unique contacts who initiated conversations with your business.": "Número acumulado de contactos únicos que iniciaram conversa com o seu negócio.",
  "Base Volume": "Volume Básico",
  "Real account data • past 14 days": "Dados reais da conta • últimos 14 dias",
  "Answered Messages": "Mensagens Respondidas",
  "Total replies generated and sent to customers by your Gemini AI and representatives.": "Total de respostas geradas e enviadas aos clientes pela sua IA Gemini e atendentes.",
  "Official autonomous replies via email": "Respostas autônomas oficiais via e-mail",
  "Requests Awaiting Validation": "Pedidos Aguardando Validação",
  "Requests to confirm": "Pedidos para confirmar",
  "Requests To Confirm": "Pedidos Para Confirmar",
  "Requests awaiting validation": "Pedidos aguardando validação",
  "Purchase intentions and booking requests gathered by the agent awaiting your confirmation.": "Intenções de compra e pedidos de agendamento recolhidos pelo agente aguardando a sua confirmação.",
  "Click to expand and manage requests to confirm": "Clique para expandir e gerir pedidos a confirmar",
  "Click to manage": "Clique para gerir",
  "There are no pending requests to validate right now. All requests and appointments have been handled.": "Nenhum pedido pendente de validação no momento. Todos os pedidos e agendamentos foram tratados.",
  "No pending requests to validate.": "Nenhum pedido pendente de validação.",
  "No pending requests.": "Nenhum pedido pendente.",
  "Loading pending requests...": "A carregar pedidos pendentes...",
  "Confirm (Send Email via AI)": "Confirmar (Enviar E-mail via IA)",
  "Unavailable / Suggest Another (AI)": "Não Disponível / Sugerir Outro (IA)",
  "Mark as Handled": "Marcar como Tratado",
  "View all requests": "Ver todos os pedidos",
  "Request": "Pedido",
  "Requests": "Pedidos",
  "Request updated.": "Pedido atualizado.",
  "Request marked as handled.": "Pedido marcado como tratado.",
  "Confirmation sent successfully to the customer by email!": "Confirmação enviada por e-mail ao cliente com sucesso!",
  "Alternative response sent successfully to the customer by email!": "Resposta alternativa enviada por e-mail ao cliente com sucesso!",
  "Confirm or suggest alternatives — the AI will send the official email response in the context of the conversation.": "Confirme ou sugira alternativas — a IA enviará a resposta oficial por e-mail no contexto da conversa.",
  "Detected by AI in customer emails.": "Detectados pela IA em e-mails de clientes.",
  "Suggest alternative model": "Sugerir modelo alternativo",
  "Email Integration Status": "Estado da Integração de E-mail",
  "Official Email Integration (Google Gmail)": "Integração de E-mail Oficial (Google Gmail)",
  "Loading email integration status...": "A carregar estado da integração de e-mail...",
  "Email Connected": "E-mail Conectado",
  "Official Email": "E-mail Oficial",
  "Connected": "Conectado",
  "Disconnected": "Desconectado",
  "ON": "LIGADO",
  "OFF": "DESLIGADO",
  "Active": "Ativa",
  "Disabled": "Desativado",
  "Disable": "Desativar",
  "Sync Emails": "Sincronizar E-mails",
  "Sync Emails Now": "Sincronizar E-mails Agora",
  "Disconnect Email": "Desconectar E-mail",
  "Last Sync": "Última Sincronização",
  "Checking...": "A verificar...",
  "Official Provider": "Provedor Oficial",
  "Sender Name": "Nome de Remetente",
  "AI Agent Status": "Status do Agente IA",
  "AI Agent": "Agente IA",
  "Enable agent automatic replies": "Ativar respostas automáticas do agente",
  "Disable agent automatic replies": "Desativar respostas automáticas do agente",
  "Click the switch to activate or deactivate the agent": "Clique no interruptor para ativar ou desativar o agente",
  "The integration allows reading messages from the connected inbox. When automatic replies are enabled, the agent can reply using the information and instructions configured on the account.": "A integração permite consultar as mensagens da caixa de entrada ligada. Quando as respostas automáticas estão ativadas, o agente pode responder usando as informações e instruções configuradas na conta.",
  "Agent enabled successfully! Automatic replies are active.": "Agente ativado com sucesso! As respostas automáticas estão ativas.",
  "Agent paused successfully.": "Agente pausado com sucesso.",
  "Sync completed successfully!": "Sincronização concluída com sucesso!",
  "Check new incoming emails and reply with AI": "Verificar novos e-mails recebidos e responder com a IA",
  "Official email account (Google Gmail) connected successfully! AI is ready to reply to customers.": "Conta de e-mail oficial (Google Gmail) conectada com sucesso! A IA já está pronta para responder aos clientes.",
  "Email disconnected successfully.": "E-mail desconectado com sucesso.",
  "Email connection failed": "Falha na ligação do e-mail",
  "Loading messages...": "A carregar mensagens...",
  "No conversations yet. When a customer sends an email, it will appear here.": "Ainda não existem conversas. Quando um cliente enviar um e-mail, ele aparecerá aqui.",
  "No recorded conversations yet.": "Ainda não existem conversas registradas.",
  "No conversations": "Sem conversas",
  "No contacts yet": "Nenhum contato ainda",
  "Customers & Messages": "Clientes & Mensagens",
  "Received conversations": "Conversas recebidas",
  "Centralized conversations": "Conversas centralizadas",
  "Conversation": "Conversa",
  "this customer": "este cliente",
  "Select a customer to open the conversation and follow AI in real time.": "Selecione um cliente para abrir a conversa e acompanhar a IA em tempo real.",
  "Select a customer first.": "Selecione um cliente primeiro.",
  "Official email support active · Drexier AI automatically replies in real time to all messages sent to your linked email.": "Atendimento oficial por e-mail ativo · A IA Drexier responde automaticamente em tempo real a todas as mensagens enviadas ao seu e-mail vinculado.",
  "Official email support active • Drexier AI automatically replies in real time to all messages from this customer.": "Atendimento oficial por e-mail ativo • A IA Drexier responde automaticamente em tempo real a todas as mensagens deste cliente.",
  "Write your official reply to the customer here... (it will be sent directly to their email)": "Escreva aqui a sua resposta oficial ao cliente... (será enviada diretamente para o e-mail dele)",
  "This reply will be delivered to the customer's email and logged as Owner.": "Esta resposta será entregue no e-mail do cliente e registrada como Proprietário.",
  "Send via Email": "Enviar por E-mail",
  "Send reply": "Enviar resposta",
  "Delete Conversation": "Eliminar Conversa",
  "Delete this customer's entire conversation": "Eliminar toda a conversa deste cliente",
  "Delete this message": "Eliminar esta mensagem",
  "Delete": "Eliminar",
  "Conversation deleted successfully.": "Conversa eliminada com sucesso.",
  "Message deleted successfully.": "Mensagem eliminada com sucesso.",
  "No messages in this conversation.": "Sem mensagens nesta conversa.",
  "Official reply delivered successfully to the customer's email!": "Resposta oficial entregue com sucesso no e-mail do cliente!",
  "Official message delivered to customer WhatsApp!": "Mensagem oficial entregue no WhatsApp do cliente!",
  "New message": "Nova mensagem",
  "New messages or requests awaiting": "Novas mensagens ou pedidos aguardando",
  "Daily customer acquisition": "Aquisição diária de clientes",
  "Customer acquisition": "Aquisição de clientes",
  "Customers acquired per day": "Clientes adquiridos por dia",
  "Comparison of new customers between today and yesterday": "Comparação de novos clientes entre hoje e ontem",
  "Response style testing": "Teste de estilos de resposta",
  "Register variants to track results. Counters only increase when real events are linked.": "Registe variantes para acompanhar os resultados. Os contadores só aumentam quando eventos reais forem ligados.",
  "Style name": "Nome do estilo",
  "e.g.: Direct & Sales-oriented, Formal Executive...": "Ex: Direto e Comercial, Formal Executivo...",
  "Response structure...": "Estrutura de resposta...",
  "Save style": "Guardar estilo",
  "No variants yet.": "Ainda não existem variantes.",
  "Delete this response style?": "Eliminar este estilo de resposta?",
  "Structured Cards": "Cards Estruturados",
  "Structured Business Cards": "Cards Estruturados do Negócio",
  "Complete your business information": "Complete as informações do seu negócio",
  "Add clear information about products, policies, and support to give more context to the agent's replies. Review responses and keep this knowledge base updated in the Business tab.": "Adicione informações claras sobre produtos, políticas e atendimento para dar mais contexto às respostas do agente. Revise as respostas e mantenha esta base atualizada na aba Negócio.",
  "Complete Business Cards": "Completar Cards do Negócio",
  "Manage information in the Business tab →": "Gerir informações na aba Negócio →",
  "Base Index": "Índice da base",
  "15/100 Base Index": "15/100 Índice da base",
  "0 / 12 completed": "0 / 12 preenchidos",
  "Priority cards awaiting completion:": "Cards prioritários aguardando preenchimento:",
  "Add more data to achieve optimal training level": "Adicione mais dados para atingir o nível de treino ideal",
  "The base currently has limited structured information. Add products, policies, and guidelines to give more context to the agent's responses.": "A base ainda tem poucas informações estruturadas. Adicione produtos, políticas e orientações para dar mais contexto às respostas do agente.",
  "The base contains substantial business information. Keep data up to date and review agent responses.": "A base contém várias informações do negócio. Mantenha os dados atualizados e reveja as respostas do agente.",
  "Organize products, policies, and guidelines to give context to the agent. This indicator tracks knowledge base completion, not answer accuracy.": "Organize produtos, políticas e orientações para dar contexto ao agente. Este indicador acompanha o preenchimento da base, não mede a precisão das respostas.",
  "Configured cards: 0 / 12 • Trainings: 0": "Cards configurados: 0 / 12 • Treinamentos: 0",
  "+ New Custom Card": "+ Novo Card Personalizado",
  "+ New Training Topic": "+ Novo Tópico de Treinamento",
  "+ New style": "+ Novo estilo",
  "Choose a category for your custom card:": "Escolha uma categoria para o seu card personalizado:",
  "New Custom Card": "Novo Card Personalizado",
  "Products & Prices": "Produtos e Preços",
  "Services & Procedures": "Serviços e Procedimentos",
  "Business Hours": "Horários de Atendimento",
  "Appointments & Scheduling": "Marcações e Agendamentos",
  "Payment Methods": "Formas de Pagamento",
  "Payment Methods & Invoicing": "Formas de Pagamento e Faturação",
  "Campaigns & Discounts": "Campanhas e Descontos",
  "Exchanges & Returns": "Trocas e Devoluções",
  "Shipping & Deadlines": "Envios e Prazos",
  "Location & Address": "Localização e Morada",
  "Official Contact Channels": "Canais Oficiais de Contacto",
  "Support & Service Rules": "Regras de Suporte e Atendimento",
  "Service Rules": "Regras de Atendimento",
  "Custom": "Personalizado",
  "Training Topic": "Tópico de Treinamento",
  "Training Topics": "Tópicos de Treinamento",
  "Registered Topics & Regulations": "Tópicos & Regulamentos Cadastrados",
  "No training topics registered yet. Use the form above to write or upload your first regulation!": "Ainda não cadastrou tópicos de treinamento. Use o formulário acima para escrever ou transferir o seu primeiro regulamento!",
  "Free AI Training Center & Documents": "Central de Treinamento Livre da IA & Documentos",
  "Training & Documents": "Treinamento & Documentos",
  "Deep Training with Files": "Treinamento Profundo com Ficheiros",
  "Unlimited training with documents": "Treinamento ilimitado com documentos",
  "Complete business knowledge base": "Base de conhecimento completa do negócio",
  "Agent knowledge base": "Base de conhecimento do agente",
  "Instruct your AI": "Instrua a sua IA",
  "Agent instructions": "Instruções ao agente",
  "Custom instructions and rules for AI": "Instruções e regras personalizadas à IA",
  "Custom instructions": "Instruções personalizadas",
  "AI Confidentiality Rule:": "Regra de Sigilo para a IA:",
  "The AI must only state whether the requested product is available. Never reveal stock counts or sensitive numbers. Use only \"We have it in stock\" or \"We do not have it in stock at the moment\".": "A IA só deve informar se existe disponibilidade para o produto solicitado. Nunca revela números de stock ou dados sensíveis. Apenas \"Temos em stock\" ou \"Não temos em stock de momento\".",
  "Stock": "Stock",
  "Product Stock": "Stock de Produtos",
  "Save Stock": "Guardar Stock",
  "Stock saved successfully. The AI will only state whether or not the product is available.": "Stock guardado com sucesso. A IA irá apenas informar se tem ou não o produto.",
  "Error saving stock.": "Erro ao guardar stock.",
  "Error loading stock.": "Erro ao carregar stock.",
  "No product found in card": "Nenhum produto encontrado no card",
  "No products found in the \"Products & Prices\" card.": "Nenhum produto encontrado no card \"Produtos e Preços\".",
  "Based on the \"Products & Prices\" card. The AI only informs the customer if the product is available, never the quantity.": "Baseado no card \"Produtos e Preços\". A IA apenas informa ao cliente se tem ou não o produto disponível, nunca a quantidade.",
  "In stock?": "Em stock?",
  "Product": "Produto",
  "Price": "Preço",
  "Quantity (owner only)": "Quantidade (apenas proprietário)",
  "0 products": "0 produtos",
  "0 words": "0 palavras",
  "0 characters": "0 caracteres",
  "0 topics": "0 tópicos",
  "Upload Official Document (PDF, Word DOCX, TXT, MD, CSV)": "Transferir / Carregar Documento Oficial (PDF, Word DOCX, TXT, MD, CSV)",
  "Upload catalogs, internal guidelines, and price lists (PDF, Word DOCX, TXT) with no limits.": "Carregue catálogos, regulamentos internos e preçários (PDF, Word DOCX, TXT) sem limites.",
  "Click here or drag a file to automatically load its content.": "Clique aqui ou arraste o ficheiro para carregar automaticamente o conteúdo.",
  "Select Document": "Selecionar Documento",
  "Free-form Text Area (Unlimited)": "Campo de Escrita Livre (Área de Texto Sem Limites)",
  "Write regulations, standards, contracts, and policies freely or upload documents (PDF, DOCX, TXT).": "Escreva livremente regulamentos, normas, contratos e políticas ou transfira documentos (PDF, DOCX, TXT).",
  "Write in detail about your company here... Paste complete regulations, terms of purchase, team manuals, support exceptions, pricing policies... The more detailed the context, the more accurate your AI support will be!": "Escreva aqui detalhadamente sobre a sua empresa... Cole regulamentos completos, termos de compra, manuais da equipe, exceções de atendimento, políticas de preços... Quanto maior o volume, mais assertivo será o atendimento da IA!",
  "Topic / Regulation Title": "Título do Tópico / Regulamento",
  "e.g.: Internal Guidelines 2026, Warranty & Returns Manual...": "Ex: Regulamento Interno 2026, Manual de Garantias e Trocas...",
  "Mark as Isolated Knowledge Topic (Recommended)": "Marcar como Tópico Isolado de Conhecimento (Recomendado)",
  "Isolated guidelines that the AI references with surgical accuracy.": "Diretrizes isoladas que a IA consulta com máxima fidelidade.",
  "When marking a training as": "Ao marcar um treino como",
  "Isolated Topic": "Tópico Isolado",
  ", the content is identified separately to help the team organize information.": ", o conteúdo fica identificado separadamente para ajudar a equipa a organizar as informações.",
  "This content will be identified separately to help organize information available to the agent.": "Este conteúdo será identificado separadamente para ajudar a organizar as informações disponíveis ao agente.",
  "Submit Regulations & Train AI": "Enviar Regulamentos & Treinar IA",
  "Save Training Topic": "Guardar Tópico de Treinamento",
  "Update Training Topic": "Atualizar Tópico de Treinamento",
  "Training topic added to AI knowledge base!": "Tópico de treinamento adicionado à base da IA!",
  "Training topic updated successfully.": "Tópico de treinamento atualizado com sucesso.",
  "Training topic deleted.": "Tópico de treinamento eliminado.",
  "Delete training topic": "Eliminar o tópico de treinamento",
  "Please fill in both the title and the content of the training topic.": "Por favor preencha o título e o conteúdo do treinamento.",
  "Error loading document.": "Erro ao carregar documento.",
  "Loading and extracting text from": "A carregar e extrair texto de",
  "uploaded successfully.": "carregado com sucesso.",
  "Detail how each service is performed and how much it costs to guide customers.": "Detalhe como cada serviço é realizado e quanto custa para orientar os clientes.",
  "e.g.: Technical support Monday to Friday from 10:00 AM to 6:00 PM": "Ex: Atendimento de apoio técnico de Segunda a Sexta das 10h às 18h",
  "e.g.: 24 hours in advance": "Ex: 24 horas de antecedência",
  "State payment methods clearly to speed up order completion.": "Deixe claro os métodos de pagamento para acelerar o fechamento de pedidos.",
  "e.g.: We issue official tax invoices. We accept bank transfers with proof of payment": "Ex: Emitimos fatura com NIF. Aceitamos transferências bancárias com envio de comprovativo",
  "The AI can offer special conditions to interested customers.": "A IA poderá oferecer condições especiais aos clientes interessados.",
  "Clear return policies give customers confidence and prevent disputes.": "Regras claras de troca trazem segurança aos clientes e evitam reclamações.",
  "The AI will answer shipping rates and delivery times instantly when customers ask.": "A IA responderá na hora o valor e prazo de envio quando o cliente perguntar.",
  "Make it easy for customers to find your physical location.": "Facilite para o cliente encontrar o seu estabelecimento físico.",
  "e.g.: Across from the subway station, with free parking for customers": "Ex: Em frente ao metro, contamos com estacionamento gratuito para clientes",
  "The most frequently asked customer questions alongside their official answers.": "Perguntas mais repetidas pelos clientes acompanhadas das respostas oficiais.",
  "Guide the agent on how to handle sensitive situations or special requests.": "Oriente o agente como lidar com situações delicadas ou exigências especiais.",
  "e.g.: Priority Support": "Ex: Atendimento Prioritário",
  "Billing": "Faturação",
  "Billing & SaaS Subscription Plan": "Faturação e Plano de Subscrição SaaS",
  "Management of monthly subscription, invoice generation, and secure Stripe payment processing.": "Gestão da subscrição mensal, emissão de faturas e controlo seguro de pagamentos via Stripe.",
  "OFFICIAL PLAN • COMPLETE SAAS ACCESS": "PLANO OFICIAL • ACESSO COMPLETO SAAS",
  "Business Plan": "Plano Business",
  "Active Plan (€59/month)": "Plano Ativo (59€/mês)",
  "No Active Plan": "Sem Plano Ativo",
  "Your subscription is active and in good standing!": "A sua subscrição está ativa e regularizada!",
  "Full access unlocked to Drexier AI, official automated email replies, and file training.": "Acesso total desbloqueado à IA Drexier, respostas automáticas oficiais por e-mail e treinamento de ficheiros.",
  "Activate Business Plan (€59/month)": "Ativar Plano Business (59€/mês)",
  "Monthly charge to card • Cancel anytime": "Cobrança mensal no cartão • Cancele quando quiser",
  "Manage Card & Download Invoices on Stripe": "Gerir Cartão e Descarregar Faturas na Stripe",
  "Update Payment Card on Stripe": "Atualizar Cartão de Pagamento na Stripe",
  "Update your card details on Stripe to keep AI support active.": "Atualize os dados do seu cartão na Stripe para manter o atendimento com IA ativo.",
  "Card Payment Failure": "Falha no Pagamento do Cartão",
  "The last monthly payment was declined by your bank. Update your card on Stripe to keep support active.": "O último pagamento mensal foi recusado pela sua entidade bancária. Atualize os dados do seu cartão na Stripe para manter o atendimento ativo.",
  "Opening secure portal...": "A aceder ao portal seguro...",
  "Preparing secure Stripe checkout...": "A preparar checkout seguro da Stripe...",
  "Already paid? Click here to verify with Stripe immediately": "Já pagou? Clique aqui para verificar com a Stripe imediatamente",
  "I have paid / Refresh Status": "Já paguei / Atualizar Status",
  "Awaiting confirmed payment": "Aguardando pagamento confirmado",
  "Next automatic renewal:": "Próxima renovação automática:",
  "Payment completed successfully! Your Business Plan (€59/month) is active and full access is unlocked.": "Pagamento efetuado com sucesso! O seu Plano Business (59€/mês) está ativo e o acesso total está desbloqueado.",
  "The subscription process was interrupted. You can join the Business Plan at any time in the Billing tab.": "O processo de subscrição foi interrompido. Pode aderir ao Plano Business a qualquer momento na aba Faturação.",
  "Could not open Stripe portal.": "Não foi possível abrir o portal da Stripe.",
  "Agent Instructions": "Instruções do Agente",
  "Define the tone, style, and general guidelines for customer support.": "Defina o tom, o estilo e as regras gerais de atendimento.",
  "Write instructions for the agent.": "Escreva as instruções para o agente.",
  "Save instructions": "Guardar instruções",
  "Mandatory responses": "Respostas obrigatórias",
  "Define messages that must be used at specific stages. Leave blank any you do not wish to set.": "Defina mensagens que devem ser usadas em etapas específicas. Deixe em branco as que não quiser configurar.",
  "Initial reply": "Primeira resposta",
  "When customer expresses purchase or booking intent": "Quando o cliente demonstrar intenção de compra/marcação",
  "When the answer is unknown": "Quando não souber a resposta",
  "Closing": "Encerramento",
  "Save responses": "Guardar respostas",
  "Account": "Conta",
  "Username": "Nome de usuário",
  "Registered email": "Email cadastrado",
  "Business description": "Descrição do negócio",
  "Agent language": "Língua do agente",
  "Save account": "Guardar conta",
  "Customize your account and the agent": "Personalize a sua conta e o agente",
  "Configure guidelines, tone of voice, and support responses in the tabs alongside.": "Configure nas abas ao lado as regras, tom de voz e respostas do suporte.",
  "Confirm sign out?": "Confirmar saída?",
  "Are you sure you want to sign out of your account?": "Tem a certeza de que deseja sair da sua conta?",
  "Cancel": "Cancelar",
  "Close": "Fechar",
  "Confirm": "Confirmar",
  "Save changes": "Guardar alterações",
  "Feature Locked": "Funcionalidade Bloqueada",
  "This feature is available exclusively to subscribers of the": "Esta funcionalidade está disponível exclusivamente para assinantes do",
  "This feature is available exclusively to Business Plan subscribers.": "Esta funcionalidade está disponível exclusivamente para assinantes do Plano Business.",
  "Activate your subscription to unlock full access to Drexier AI.": "Ative a sua subscrição para desbloquear o acesso total ao Drexier AI.",
  "€59/month": "59€/mês",
  "/month": "/mês",
  "/ month": "/ mês",
  "Configurable automated email replies": "Respostas automáticas configuráveis por e-mail",
  "Gmail integration & automated replies": "Integração Gmail & respostas automáticas",
  "Complete conversion dashboard": "Dashboard completo de conversões",
  "No commitment • Cancel anytime • Secure payment via Stripe": "Sem fidelização • Cancele a qualquer momento • Pagamento seguro via Stripe",
  "Are you sure you want to delete this message?": "Tem a certeza de que deseja eliminar esta mensagem?",
  "Are you sure you want to delete card": "Tem a certeza de que deseja eliminar o card",
  "Are you sure you want to delete all messages and history for": "Tem a certeza de que deseja eliminar todas as mensagens e o histórico de",
  "An error occurred.": "Ocorreu um erro.",
  "Request logged on dashboard.": "Pedido registado no dashboard.",
  "Request awaiting owner confirmation.": "Pedido aguardando confirmação do proprietário.",
  "Today": "Hoje",
  "Yesterday": "Ontem",
  "Date": "Data",
  "Time": "Hora",
  "Status": "Status",
  "Customer": "Cliente",
  "Subject": "Assunto",
  "Message": "Mensagem",
  "Name": "Nome",
  "Email": "Email",
  "Phone": "Telefone",
  "Channel": "Channel",
  "Details": "Detalhes",
  "Overall Performance": "Desempenho Geral",
  "Initial Calibration": "Calibração Inicial",
  "Access": "Acesso",
  "The AI has been responding since": "A IA responde desde",
  "Connected by account owner": "Connected by account owner",
  "Drexier Email Assistant • Product Preview": "Drexier Email Assistant • Product Preview",
  "Illustrative conversation • Your settings determine how replies are handled": "Illustrative conversation • Your settings determine how replies are handled",
  "Illustrative interface": "Illustrative interface",
  "Your knowledge": "Your knowledge",
  "Workspace agent": "Workspace agent",
  "Business information reviewed • Example workflow": "Business information reviewed • Example workflow",
  "Drexier — Intelligent support for your business": "Drexier — Atendimento inteligente para a sua empresa",
  "Switch to English": "Switch to English",
  "Mudar para Português": "Switch to Portuguese",
  "AI PLATFORM": "AI PLATFORM",
  "Track": "Acompanhe",
  "Upon subscribing, €59 is charged to your card via secure Stripe checkout and all features are unlocked.": "Ao aderir, o valor de 59€ é cobrado no seu cartão através do checkout seguro da Stripe e todas as funcionalidades ficam liberadas.",
  "By connecting your account through Google's official page, Drexier receives secure authorization to read incoming questions and send intelligent replies powered by AI.": "Ao conectar a sua conta através da página oficial da Google, o Drexier recebe autorização segura para ler dúvidas recebidas e enviar respostas inteligentes conduzidas pela IA.",
  "Refresh": "Atualizar",
  "Automated Replies": "Automação de Respostas",
  "How conversations are organized and tracked.": "Como as conversas são organizadas e acompanhadas.",
  "How replies are prepared and sent.": "Como o retorno é preparado e enviado.",
  "How requests requiring follow-up are identified.": "Como pedidos que precisam de acompanhamento são identificados.",
  "How products, prices, and policies are referenced during support.": "Como produtos, preços e políticas são consultados durante o atendimento.",
  "Stripe configuration pending in .env file": "Configuração da Stripe Pendente no ficheiro .env",
  "Credentials configuration pending in .env file": "Configuração de Credenciais Pendente no ficheiro .env",
  "Agent context:": "Contexto do agente:",
  "Dashboard & Real-time Metrics": "Dashboard e Métricas em Tempo Real",
  "Deutsch": "Deutsch",
  "English": "English",
  "Español": "Español",
  "Français": "Français",
  "Português": "Português",
  "FAQ": "FAQ",
  "Manage Requests": "Gerir Pedidos",
  "Business information": "Informações do negócio",
  "Integration": "Integração",
  "Could not load email status:": "Não foi possível carregar o estado do e-mail:",
  "Opportunities": "Oportunidades",
  "PT · EN": "PT · EN",
  "To enable one-click connection, add the keys to your file": "Para ativar a ligação com um clique, adicione as chaves no seu ficheiro",
  "To enable real card charges and automated billing, fill in your file": "Para ativar cobranças reais com cartão e faturação automática, preencha no seu ficheiro",
  "Subscribe with 1 Click & Activate your Account Immediately": "Subscreva com 1 Clique e Ative a sua Conta Imediatamente",
  "Reply text": "Texto da resposta",
  "Validation of Requests & Bookings": "Validação de Pedidos & Marcações",
  "Error loading messages:": "Erro ao carregar mensagens:",
  "Error loading billing status:": "Erro ao carregar status de faturação:",
  "Error verifying subscription.": "Erro ao verificar subscrição.",
  "Error authorizing email provider.": "Erro na autorização do fornecedor de e-mail.",
  "Error loading:": "Erro no carregamento:",
  "customers": "clientes",
  "customer": "cliente",
  "Error loading requests:": "Erro ao carregar pedidos:"
};

  // Dynamic template pattern handlers
  const patternTranslators = [
    {
      // "Cards configurados: 0 / 12 • Treinamentos: 0"
      matchEn: /Cards configurados:\s*(\d+)\s*\/\s*(\d+)\s*[•·]\s*Treinamentos:\s*(\d+)/i,
      renderEn: (m) => `Configured cards: ${m[1]} / ${m[2]} • Trainings: ${m[3]}`,
      matchPt: /Configured cards:\s*(\d+)\s*\/\s*(\d+)\s*[•·]\s*Trainings:\s*(\d+)/i,
      renderPt: (m) => `Cards configurados: ${m[1]} / ${m[2]} • Treinamentos: ${m[3]}`
    },
    {
      // "${count} clientes"
      matchEn: /(\d+)\s+clientes\b/i,
      renderEn: (m) => `${m[1]} customers`,
      matchPt: /(\d+)\s+customers\b/i,
      renderPt: (m) => `${m[1]} clientes`
    },
    {
      // "extraído com sucesso! (N palavras adicionadas)."
      matchEn: /extra[íi]do com sucesso!\s*\((\d+)\s+palavras adicionadas\)\./i,
      renderEn: (m) => `extracted successfully! (${m[1]} words added).`,
      matchPt: /extracted successfully!\s*\((\d+)\s+words added\)\./i,
      renderPt: (m) => `extraído com sucesso! (${m[1]} palavras adicionadas).`
    },
    {
      // "Tem a certeza de que deseja eliminar todas as mensagens e o histórico de NAME?"
      matchEn: /Tem a certeza de que deseja eliminar todas as mensagens e o hist[óo]rico de\s+(.+)\?/i,
      renderEn: (m) => `Are you sure you want to delete all messages and history for ${m[1]}?`,
      matchPt: /Are you sure you want to delete all messages and history for\s+(.+)\?/i,
      renderPt: (m) => `Tem a certeza de que deseja eliminar todas as mensagens e o histórico de ${m[1]}?`
    },
    {
      // "Tem a certeza de que deseja eliminar o card NAME?"
      matchEn: /Tem a certeza de que deseja eliminar o card\s+(.+)\?/i,
      renderEn: (m) => `Are you sure you want to delete card ${m[1]}?`,
      matchPt: /Are you sure you want to delete card\s+(.+)\?/i,
      renderPt: (m) => `Tem a certeza de que deseja eliminar o card ${m[1]}?`
    },
    {
      // "Erro ao carregar mensagens: ERROR"
      matchEn: /Erro ao carregar mensagens:\s*(.+)/i,
      renderEn: (m) => `Error loading messages: ${m[1]}`,
      matchPt: /Error loading messages:\s*(.+)/i,
      renderPt: (m) => `Erro ao carregar mensagens: ${m[1]}`
    },
    {
      // "Falha na ligação do e-mail: REASON"
      matchEn: /Falha na liga[çc][ãa]o do e-mail:\s*(.+)/i,
      renderEn: (m) => `Email connection failed: ${m[1]}`,
      matchPt: /Email connection failed:\s*(.+)/i,
      renderPt: (m) => `Falha na ligação do e-mail: ${m[1]}`
    }
  ];

  let currentLanguage = localStorage.getItem(STORAGE_KEY) || "pt";

  function translateText(value, targetLang = currentLanguage) {
    if (!value || typeof value !== "string") return value;
    const match = value.match(/^(\s*)([\s\S]*?)(\s*)$/);
    if (!match) return value;
    const [, leading, body, trailing] = match;
    if (!body) return value;

    if (targetLang === "en") {
      if (Object.prototype.hasOwnProperty.call(translationsEn, body)) {
        return leading + translationsEn[body] + trailing;
      }
      for (const p of patternTranslators) {
        const m = body.match(p.matchEn);
        if (m) return leading + p.renderEn(m) + trailing;
      }
    } else if (targetLang === "pt") {
      if (Object.prototype.hasOwnProperty.call(translationsPt, body)) {
        return leading + translationsPt[body] + trailing;
      }
      for (const p of patternTranslators) {
        const m = body.match(p.matchPt);
        if (m) return leading + p.renderPt(m) + trailing;
      }
    }
    return value;
  }

  const originalTexts = new WeakMap();
  const originalAttrs = new WeakMap();
  const attrNames = ["placeholder", "title", "aria-label"];

  function shouldSkipNode(node) {
    if (!node) return true;
    const parent = node.parentElement;
    if (!parent) return true;
    const tag = parent.tagName;
    if (tag === "SCRIPT" || tag === "STYLE" || tag === "CODE" || tag === "PRE" || tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
    if (parent.classList && parent.classList.contains("no-translate")) return true;
    if (parent.closest && parent.closest(".no-translate")) return true;
    return false;
  }

  function translateNode(node) {
    if (shouldSkipNode(node)) return;
    const val = node.nodeValue;
    if (!val || !val.trim()) return;

    if (!originalTexts.has(node)) {
      originalTexts.set(node, val);
    }

    const baseVal = originalTexts.get(node);
    if (currentLanguage === "en") {
      node.nodeValue = translateText(baseVal, "en");
    } else {
      node.nodeValue = translateText(baseVal, "pt") || baseVal;
    }
  }

  function translateAttributes(el) {
    if (!el || el.nodeType !== Node.ELEMENT_NODE) return;
    const tag = el.tagName;
    if (tag === "SCRIPT" || tag === "STYLE" || tag === "CODE" || tag === "PRE") return;
    if (el.classList && el.classList.contains("no-translate")) return;

    for (let i = 0; i < attrNames.length; i++) {
      const name = attrNames[i];
      if (!el.hasAttribute(name)) continue;

      let stored = originalAttrs.get(el);
      if (!stored) {
        stored = {};
        originalAttrs.set(el, stored);
      }

      if (!(name in stored)) {
        stored[name] = el.getAttribute(name);
      }

      const original = stored[name];
      if (currentLanguage === "en") {
        el.setAttribute(name, translateText(original, "en"));
      } else {
        el.setAttribute(name, translateText(original, "pt") || original);
      }
    }

    // Handle <select> <option> texts
    if (tag === "OPTION") {
      if (!originalTexts.has(el)) {
        originalTexts.set(el, el.textContent);
      }
      const original = originalTexts.get(el);
      el.textContent = currentLanguage === "en" ? translateText(original, "en") : (translateText(original, "pt") || original);
    }
  }

  let isObserving = false;

  function translateTree(root = document.body) {
    if (!root) return;

    const wasObserving = isObserving;
    if (wasObserving) stopObserving();

    try {
      if (root.nodeType === Node.ELEMENT_NODE) {
        translateAttributes(root);
        const elements = root.querySelectorAll("*");
        for (let i = 0; i < elements.length; i++) {
          translateAttributes(elements[i]);
        }
      }

      const walker = document.createTreeWalker(
        root,
        NodeFilter.SHOW_TEXT,
        {
          acceptNode(node) {
            if (shouldSkipNode(node)) return NodeFilter.FILTER_REJECT;
            return node.nodeValue && node.nodeValue.trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
          }
        }
      );

      const nodes = [];
      while (walker.nextNode()) {
        nodes.push(walker.currentNode);
      }
      for (let i = 0; i < nodes.length; i++) {
        translateNode(nodes[i]);
      }
    } finally {
      if (wasObserving) startObserving();
    }
  }

  function updateSwitcherUI(lang) {
    document.querySelectorAll(".lang-btn").forEach((btn) => {
      const btnLang = btn.dataset.lang;
      const isActive = btnLang === lang;
      btn.classList.toggle("active", isActive);
      btn.setAttribute("aria-pressed", isActive ? "true" : "false");
    });

    document.querySelectorAll(".language-toggle").forEach((toggle) => {
      const isEn = lang === "en";
      toggle.classList.toggle("is-en", isEn);
      toggle.setAttribute("aria-label", isEn ? "Mudar para Português" : "Switch to English");
      toggle.setAttribute("title", isEn ? "Mudar para Português" : "Switch to English");
      const label = toggle.querySelector(".language-toggle-label");
      if (label) {
        label.textContent = isEn ? "EN · PT" : "PT · EN";
      }
    });
  }

  const DrexierI18n = {
    getLanguage: () => currentLanguage,
    t: (str) => translateText(str, currentLanguage),
    translate: (str) => translateText(str, currentLanguage),
    setLanguage(lang) {
      if (!["pt", "en"].includes(lang)) return;
      if (currentLanguage === lang) return;
      currentLanguage = lang;
      localStorage.setItem(STORAGE_KEY, lang);
      document.documentElement.lang = lang;
      document.title = lang === "en"
        ? "Drexier — Intelligent support for your business"
        : "Drexier — Atendimento inteligente para a sua empresa";

      updateSwitcherUI(lang);
      translateTree(document.body);

      // Notificação global instantânea
      window.dispatchEvent(new CustomEvent("drexier:languagechange", { detail: { language: lang } }));
    }
  };

  window.DrexierI18n = DrexierI18n;
  window.t = DrexierI18n.t;

  function bindEvents() {
    document.addEventListener("click", (e) => {
      const langBtn = e.target.closest(".lang-btn");
      if (langBtn && langBtn.dataset.lang) {
        e.preventDefault();
        DrexierI18n.setLanguage(langBtn.dataset.lang);
        return;
      }

      const toggle = e.target.closest(".language-toggle");
      if (toggle) {
        e.preventDefault();
        DrexierI18n.setLanguage(currentLanguage === "pt" ? "en" : "pt");
      }
    });
  }

  let translateTimer = null;
  const pendingNodes = new Set();

  function processPendingNodes() {
    translateTimer = null;
    if (!pendingNodes.size || currentLanguage !== "en") {
      pendingNodes.clear();
      return;
    }
    const nodes = Array.from(pendingNodes);
    pendingNodes.clear();

    stopObserving();
    try {
      for (let i = 0; i < nodes.length; i++) {
        const node = nodes[i];
        if (!node.isConnected) continue;
        if (node.nodeType === Node.TEXT_NODE) {
          translateNode(node);
        } else if (node.nodeType === Node.ELEMENT_NODE) {
          translateTree(node);
        }
      }
    } finally {
      startObserving();
    }
  }

  const observer = new MutationObserver((mutations) => {
    if (currentLanguage !== "en") return;
    for (let i = 0; i < mutations.length; i++) {
      const mutation = mutations[i];
      if (mutation.type === "childList") {
        for (let j = 0; j < mutation.addedNodes.length; j++) {
          const node = mutation.addedNodes[j];
          if (node.nodeType === Node.ELEMENT_NODE || node.nodeType === Node.TEXT_NODE) {
            pendingNodes.add(node);
          }
        }
      }
    }
    if (pendingNodes.size && !translateTimer) {
      translateTimer = requestAnimationFrame(processPendingNodes);
    }
  });

  function startObserving() {
    if (isObserving || !document.body) return;
    observer.observe(document.body, {
      childList: true,
      subtree: true
    });
    isObserving = true;
  }

  function stopObserving() {
    if (!isObserving) return;
    observer.disconnect();
    isObserving = false;
  }

  function init() {
    bindEvents();
    updateSwitcherUI(currentLanguage);
    if (currentLanguage === "en") {
      translateTree(document.body);
    }
    startObserving();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
