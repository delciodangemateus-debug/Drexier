# append_i18n.py
import json

with open("frontend/i18n.js", "r", encoding="utf-8") as f:
    text = f.read()

# Bilingual dictionary of new UI terms
new_pairs = {
    "A inteligência que transforma conversas em clientes.": "The intelligence that transforms conversations into customers.",
    "O Drexier utiliza inteligência artificial para conduzir conversas comerciais, responder aos seus clientes e acompanhar o processo de compra, enquanto o seu negócio continua a avançar.": "Drexier uses artificial intelligence to handle commercial conversations, answer your customers, and guide the purchasing process, while your business keeps moving forward.",
    "Conhecer a plataforma": "Explore the platform",
    "Atendimento Ativo": "Active Support",
    "Operação contínua": "Continuous operation",
    "OAuth 2.0 verificado": "OAuth 2.0 verified",
    "100% Conectada": "100% Connected",
    "Produtos, regras & stock": "Products, rules & inventory",
    "Controlo Total": "Full Control",
    "Assumir a qualquer hora": "Take over anytime",
    "Entrada de Email": "Inbound Email",
    "Como o Drexier conduz o seu atendimento": "How Drexier powers your customer support",
    "O cliente inicia a conversa": "The customer starts the conversation",
    "A IA compreende e responde": "AI understands and responds",
    "Condução à oportunidade": "Guiding the opportunity",
    "A arquitetura do agente comercial": "The commercial agent architecture",
    "Conexão Oficial Gmail": "Official Gmail Connection",
    "Banco de Stock Dinâmico": "Dynamic Inventory Stock",
    "Diretrizes & Personalidade": "Guidelines & Personality",
    "Intervenção Humana Instantânea": "Instant Human Takeover",
    "Inteligência do Negócio": "Business Intelligence",
    "Plataforma Enterprise Segura": "Secure Enterprise Platform",
    "A tecnologia deve libertar a liderança para desenhar o futuro, enquanto a inteligência artificial assegura a excelência de cada conversa com o cliente.": "Technology should free leadership to design the future, while artificial intelligence ensures excellence in every customer conversation.",
    "Perguntas Frequentes": "Frequently Asked Questions",
    "Como funciona a integração oficial com o Google Gmail?": "How does the official Google Gmail integration work?",
    "A IA pode inventar descontos ou divulgar o stock do armazém?": "Can the AI invent discounts or reveal warehouse stock?",
    "O que acontece quando o cliente deseja falar com um operador humano?": "What happens when a customer wants to speak with a human agent?",
    "Quais os limites de conversação do plano Business?": "What are the conversation limits of the Business plan?",
    "Como a IA aprende os detalhes e regras do meu catálogo?": "How does AI learn the details and rules of my catalog?",
    "Acelere o atendimento comercial da sua empresa": "Accelerate your company's commercial support",
    "Atendimento Comercial Inteligente": "Intelligent Commercial Support",
    "Desempenho Comercial": "Commercial Performance",
    "Última atualização em tempo real": "Last real-time update",
    "7 Dias": "7 Days",
    "30 Dias": "30 Days",
    "Mensagens Recebidas": "Received Messages",
    "Mensagens oficiais registadas": "Registered official messages",
    "Atendidas pela IA": "Answered by AI",
    "Clientes na Base": "Contacts in Base",
    "Contactos acumulados": "Accumulated contacts",
    "Vendas & Pedidos": "Sales & Orders",
    "Aguardando confirmação": "Awaiting confirmation",
    "Marcações Adquiridas": "Acquired Bookings",
    "Agendamentos detetados": "Detected bookings",
    "Taxa de Conversão": "Conversion Rate",
    "Conversões de contactos": "Contact conversions",
    "Aquisição de Novos Contactos": "New Contact Acquisition",
    "Atividade Recente": "Recent Activity",
    "Últimos eventos do sistema": "Latest system events",
    "Análise de Dados Reais": "Real Data Analysis",
    "Pesquisar conversas por nome ou email...": "Search conversations by name or email...",
    "Todas": "All",
    "Não lidas": "Unread",
    "Assumir Atendimento": "Take Over Support",
    "Devolver à IA": "Hand Back to AI",
    "Perfil do Cliente": "Customer Profile",
    "Origem": "Source",
    "Estado Comercial": "Commercial Status",
    "Inteligência Contextual": "Contextual Intelligence",
    "Interesse Identificado": "Identified Interest",
    "Modo de Atendimento": "Support Mode",
    "Banco de Stock & Inventário": "Inventory & Stock Bank",
    "Total de Produtos": "Total Products",
    "Disponíveis": "Available",
    "Stock Baixo": "Low Stock",
    "Esgotados": "Out of Stock",
    "Variações (Tamanho / Cor)": "Variants (Size / Color)",
    "Quantidade (Proprietário)": "Quantity (Owner)",
    "Agent Studio – Centro de Controlo da IA": "Agent Studio – AI Control Center",
    "Visão Geral": "Overview",
    "Personalidade & Tom": "Personality & Tone",
    "Instruções Gerais": "General Instructions",
    "Respostas Obrigatórias": "Mandatory Responses",
    "Regras & Sigilo": "Rules & Secrecy",
    "Objetivos Comerciais": "Commercial Goals",
    "Estado do Agente": "Agent Status",
    "Sigilo de Quantidades": "Quantity Secrecy",
    "Ativo por Omissão": "Active by Default",
    "Personalidade & Postura Comunicacional": "Personality & Communication Posture",
    "Instruções Gerais de Atendimento": "General Support Instructions",
    "Regras & Sigilo de Inventário": "Rules & Inventory Secrecy",
    "Sigilo Absoluto de Quantidade de Stock": "Absolute Inventory Quantity Secrecy",
    "Limites de Negociação": "Negotiation Boundaries",
    "Objetivos Comerciais da IA": "Commercial AI Goals",
    "Condução Orientada à Conversão": "Conversion-Oriented Guidance",
    "Conta & Perfil da Empresa": "Account & Company Profile",
    "Adicionar Produto ao Stock": "Add Product to Inventory",
    "Editar Produto no Stock": "Edit Inventory Product",
    "Sincronizado automaticamente com o card Produtos e Preços.": "Automatically synchronized with Products and Prices card.",
    "Nome do Produto": "Product Name",
    "Quantidade em Stock": "Quantity in Stock",
    "Variações de Tamanho / Cor (separadas por vírgula)": "Size / Color Variants (comma separated)",
    "Detalhes e Condições Adicionais": "Details and Additional Conditions",
    "Guardar Produto": "Save Product"
}

# Format objects to insert
en_lines = []
for k, v in new_pairs.items():
    en_lines.append(f'  {json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False)},')

pt_lines = []
for k, v in new_pairs.items():
    pt_lines.append(f'  {json.dumps(v, ensure_ascii=False)}: {json.dumps(k, ensure_ascii=False)},')

# Insert into translationsEn right before `};\n\n  const translationsPt`
marker_en = "};\n\n  const translationsPt"
if marker_en in text:
    text = text.replace(marker_en, "\n" + "\n".join(en_lines) + "\n" + marker_en)
else:
    # try windows newline
    marker_en_crlf = "};\r\n\r\n  const translationsPt"
    text = text.replace(marker_en_crlf, "\r\n" + "\r\n".join(en_lines) + "\r\n" + marker_en_crlf)

# Insert into translationsPt right before the end of translationsPt object
marker_pt = "  return language === \"en\" ? (translationsEn[trimmed] || trimmed) : (translationsPt[trimmed] || trimmed);"
# The closing of translationsPt is right before this return or its preceding comment
# Let's find the closing brace before window.translate
lines = text.splitlines(True)
for i in range(len(lines)-1, 0, -1):
    if lines[i].strip() == "};" and "translationsPt" not in lines[i]:
        # This is the closing of translationsPt
        lines.insert(i, "\n" + "\n".join(pt_lines) + "\n")
        break

text = "".join(lines)

with open("frontend/i18n.js", "w", encoding="utf-8") as f:
    f.write(text)

print("Safely merged i18n pairs!")
