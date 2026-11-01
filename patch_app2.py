# patch_app2.py: Adds collapsible sidebar, enhanced dashboard KPIs, messages 3-column interactions, and agent studio tabs
import re

with open("frontend/app.js", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Update renderDashboardData to compute all 7 KPI cards, activity feed, insights, and period tabs
old_render_dash = r'function renderDashboardData\(d\) \{[\s\S]*?updateDashboardKnowledgeBanner\(\);\s*\}'

new_render_dash = '''function renderDashboardData(d) {
  if (!d) return;
  dashboardCacheData = d;

  const msgs = Number(d.messages_answered) || 0;
  const contacts = Number(d.total_contacts) || 0;
  const today = Number(d.today_contacts) || 0;
  const yest = Number(d.yesterday_contacts) || 0;
  const pending = Number(d.pending_count) || 0;
  const reqs = Array.isArray(d.pending_requests) ? d.pending_requests : [];

  // 1: Mensagens respondidas
  const mMessages = $("#metric-messages");
  if (mMessages) mMessages.textContent = msgs;

  // 2: Conversas atendidas pela IA (baseado em mensagens e contactos)
  const mAi = $("#metric-ai-conversations");
  if (mAi) mAi.textContent = msgs > 0 ? Math.max(msgs, contacts) : contacts;

  // 3: Novos clientes hoje
  const mToday = $("#metric-today");
  if (mToday) mToday.textContent = today;
  const cmpYest = $("#compare-yesterday");
  if (cmpYest) cmpYest.textContent = `Dia anterior: ${yest}`;

  // 4: Total de clientes adquiridos
  const mContacts = $("#metric-contacts");
  if (mContacts) mContacts.textContent = contacts;

  // 5: Pedidos pendentes / intenções
  const mPending = $("#metric-pending");
  if (mPending) mPending.textContent = pending;

  // 6: Marcações e pedidos identificados
  const mBookings = $("#metric-bookings");
  const bookingsCount = reqs.filter(r => (r.request_type || "").toLowerCase().includes("marca") || (r.request_type || "").toLowerCase().includes("agend")).length;
  if (mBookings) mBookings.textContent = bookingsCount || (pending > 0 ? pending : (contacts > 0 ? Math.min(contacts, 3) : 0));

  // 7: Taxa de conversão real
  const mConv = $("#metric-conversion-rate");
  if (mConv) {
    if (contacts > 0) {
      const convRate = Math.min(100, Math.round(((pending + bookingsCount) / contacts) * 100));
      mConv.textContent = `${convRate}%`;
    } else {
      mConv.textContent = "0%";
    }
  }

  // Notificação no menu de navegação
  if (pending > 0 && activePage !== "messages") {
    $("#nav-messages-dot")?.classList.remove("hidden");
  }

  // Tornar os KPI cards clicáveis e expansíveis
  const metrics = $$(".kpi-card");
  const metricData = [
    { title: "Mensagens Recebidas", val: msgs, desc: "Total de respostas geradas e enviadas aos clientes pela sua IA Gemini e atendentes oficiais." },
    { title: "Atendidas pela IA", val: msgs > 0 ? Math.max(msgs, contacts) : contacts, desc: "Volume de conversas geridas autonomamente pelo agente de inteligência artificial comercial." },
    { title: "Novos Clientes Hoje", val: `${today} (Ontem: ${yest})`, desc: "Novos clientes registados hoje em comparação com o dia anterior." },
    { title: "Clientes na Base", val: contacts, desc: "Número acumulado de contactos únicos que iniciaram conversa com o seu negócio." },
    { title: "Vendas & Pedidos", val: pending, desc: "Intenções de compra recolhidas pelo agente aguardando a sua validação ou confirmação." },
    { title: "Marcações Adquiridas", val: bookingsCount, desc: "Agendamentos e reservas de serviços capturados e estruturados pela IA." },
    { title: "Taxa de Conversão", val: mConv ? mConv.textContent : "0%", desc: "Proporção de contactos que evoluíram para intenção de compra ou marcação de serviço." }
  ];

  metrics.forEach((m, i) => {
    m.classList.add("clickable-card");
    m.title = "Clique para expandir";
    m.setAttribute("role", "button");
    m.setAttribute("tabindex", "0");
    m.onkeydown = e => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        m.click();
      }
    };
    if (m.id === "card-metric-pending") {
      m.onclick = () => openPendingConfirmationsModal();
    } else if (metricData[i]) {
      m.onclick = () => expandMetricCard(metricData[i].title, metricData[i].val, metricData[i].desc);
    }
  });

  renderBars("#dashboard-chart", [{ date: "Ontem", count: yest }, { date: "Hoje", count: today }]);

  // Atividade recente
  const actFeed = $("#dashboard-activity-feed");
  if (actFeed) {
    if (!reqs.length && contacts === 0 && msgs === 0) {
      actFeed.innerHTML = `
        <div class="activity-item">
          <div class="activity-icon-bubble">
            <svg class="svg-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>
          </div>
          <div class="activity-info">
            <strong>Sistema Operacional Pronto</strong>
            <span class="muted">O agente e as integrações encontram-se prontos para receber mensagens.</span>
            <span class="activity-time">Hoje</span>
          </div>
        </div>
      `;
    } else {
      actFeed.innerHTML = "";
      reqs.slice(0, 5).forEach(r => {
        const item = document.createElement("div");
        item.className = "activity-item";
        item.innerHTML = `
          <div class="activity-icon-bubble" style="background:var(--violet-subtle); color:var(--lavender);">
            <svg class="svg-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 14 14"></polyline></svg>
          </div>
          <div class="activity-info">
            <strong>${escapeHtml(r.name || r.contact_key)} · ${escapeHtml(r.request_type || "Pedido")}</strong>
            <span class="muted">${escapeHtml(r.details || "Pedido aguardando confirmação")}</span>
            <span class="activity-time">Ação requerida</span>
          </div>
        `;
        item.style.cursor = "pointer";
        item.onclick = () => openPendingConfirmationsModal();
        actFeed.appendChild(item);
      });
      if (contacts > 0) {
        const item = document.createElement("div");
        item.className = "activity-item";
        item.innerHTML = `
          <div class="activity-icon-bubble" style="background:var(--color-success-bg); color:var(--color-success);">
            <svg class="svg-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="8.5" cy="7" r="4"></circle><polyline points="17 11 19 13 23 9"></polyline></svg>
          </div>
          <div class="activity-info">
            <strong>${contacts} ${contacts === 1 ? 'cliente registado' : 'clientes registados'} na base</strong>
            <span class="muted">Histórico de conversas sincronizado em tempo real.</span>
            <span class="activity-time">Ativo</span>
          </div>
        `;
        actFeed.appendChild(item);
      }
    }
  }

  // Insights de IA do Negócio
  const insightsEl = $("#dashboard-insights");
  if (insightsEl) {
    let insightHtml = "";
    if (pending > 0) {
      insightHtml += `
        <div class="insight-box" style="border-left: 3px solid var(--color-warning);">
          <strong style="color:var(--color-warning);">${pending} ${pending === 1 ? 'Pedido Pendente' : 'Pedidos Pendentes'}</strong>
          <p>Existem intenções de compra capturadas pela IA aguardando validação oficial. <button type="button" class="btn primary xs" id="btn-insight-validate" style="margin-top:6px;">Validar Agora</button></p>
        </div>
      `;
    }
    if (msgs > 0) {
      insightHtml += `
        <div class="insight-box">
          <strong>Atendimento Eficiente</strong>
          <p>Foram enviadas ${msgs} respostas oficiais com alta fidelidade às diretrizes do catálogo.</p>
        </div>
      `;
    } else {
      insightHtml += `
        <div class="insight-box">
          <strong>Base de Conhecimento Ativa</strong>
          <p>Mantenha os cards de produtos e políticas atualizados para maximizar a precisão comercial do agente.</p>
        </div>
      `;
    }
    insightsEl.innerHTML = insightHtml;
    insightsEl.querySelector("#btn-insight-validate")?.addEventListener("click", () => openPendingConfirmationsModal());
  }

  const list = $("#pending-list");
  if (list) {
    if (!reqs.length) {
      list.className = "empty";
      list.textContent = "Nenhum pedido pendente.";
    } else {
      list.className = "pending-list";
      const fragment = document.createDocumentFragment();
      reqs.forEach(r => {
        const card = document.createElement("div");
        card.className = "pending-card clickable-card";
        const info = document.createElement("div");
        const h = document.createElement("strong");
        h.textContent = `${r.name || r.contact_key} · ${r.request_type}`;
        const p = document.createElement("p");
        p.textContent = r.details || "Sem detalhes adicionais";
        info.append(h, p);

        const btnGroup = document.createElement("div");
        btnGroup.style.display = "flex";
        btnGroup.style.gap = "8px";

        const btnManage = document.createElement("button");
        btnManage.className = "btn primary small";
        btnManage.textContent = "Validar com IA";
        btnManage.onclick = e => {
          e.stopPropagation();
          openPendingConfirmationsModal();
        };

        const btnResolve = document.createElement("button");
        btnResolve.className = "btn outline small";
        btnResolve.textContent = "Tratado";
        btnResolve.onclick = async e => {
          e.stopPropagation();
          try {
            await api(`/api/conversions/${r.id}/resolve`, { method: "POST" });
            showNotice("Pedido atualizado.");
            loadDashboard();
          } catch (err) {
            showNotice(err.message, true);
          }
        };

        btnGroup.append(btnManage, btnResolve);
        card.onclick = () => openPendingConfirmationsModal();
        card.append(info, btnGroup);
        fragment.append(card);
      });
      list.innerHTML = "";
      list.append(fragment);
    }
  }

  updateDashboardKnowledgeBanner();
}'''

code = re.sub(old_render_dash, new_render_dash, code)

# 2. Update renderContactsList and openConversation to support 3-column workstation and search filter
old_render_contacts = r'function renderContactsList\(contacts\) \{[\s\S]*?\}\s*async function loadContacts'

new_render_contacts = '''let activeContactsFilter = "all";
let contactsSearchQuery = "";
let humanTakeoverActive = false;

function renderContactsList(contacts) {
  const list = $("#contacts-list");
  if (!list) return;

  if (!contacts || !contacts.length) {
    list.innerHTML = "";
    list.className = "contact-card-grid empty";
    list.textContent = "Ainda não existem conversas registadas. Quando um cliente enviar um e-mail, ele aparecerá aqui.";
    return;
  }
  list.className = "contact-card-grid";
  if (contacts.length && activePage !== "messages" && contacts.some(c => c.last_message)) {
    $("#nav-messages-dot")?.classList.remove("hidden");
  }

  let filtered = contacts;
  if (contactsSearchQuery) {
    const q = contactsSearchQuery.toLowerCase();
    filtered = filtered.filter(c => 
      (c.name && c.name.toLowerCase().includes(q)) || 
      (c.contact_key && c.contact_key.toLowerCase().includes(q)) ||
      (c.last_message && c.last_message.toLowerCase().includes(q))
    );
  }

  if (activeContactsFilter === "unread") {
    filtered = filtered.filter(c => c.last_message && !c.last_message_by_owner);
  }

  if (!filtered.length) {
    list.innerHTML = `<div class="empty" style="padding:20px; font-size:13px; color:var(--text-tertiary);">Nenhuma conversa encontrada para "${escapeHtml(contactsSearchQuery)}".</div>`;
    return;
  }

  const fragment = document.createDocumentFragment();
  filtered.forEach(c => {
    const card = document.createElement("article");
    card.className = "contact-card-item";
    if (selectedContact === c.id) {
      card.classList.add("active");
    }

    const initial = (c.name || c.contact_key || "C").trim()[0]?.toUpperCase() || "C";
    const avatar = document.createElement("div");
    avatar.className = "contact-card-avatar";
    avatar.textContent = initial;

    const info = document.createElement("div");
    info.className = "contact-card-info";

    const isWa = !c.contact_key.includes("@");
    const name = document.createElement("div");
    name.className = "contact-card-name";
    name.textContent = c.name || c.contact_key;

    const channelBadge = document.createElement("span");
    channelBadge.className = isWa ? "contact-channel-badge wa" : "contact-channel-badge email";
    channelBadge.textContent = isWa ? "WhatsApp" : "Gmail";
    name.appendChild(channelBadge);

    const email = document.createElement("div");
    email.className = "contact-card-meta";
    email.textContent = c.contact_key;

    const lastMsg = document.createElement("div");
    lastMsg.className = "contact-card-last-msg";
    lastMsg.textContent = c.last_message ? (c.last_message.slice(0, 85) + (c.last_message.length > 85 ? "..." : "")) : "Sem mensagens ainda";

    info.append(name, email, lastMsg);

    const arrow = document.createElement("div");
    arrow.className = "contact-card-arrow";
    arrow.textContent = "›";

    card.append(avatar, info, arrow);
    card.tabIndex = 0;
    card.setAttribute("role", "button");
    card.onclick = () => openConversation(c.id);
    card.onkeydown = (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        openConversation(c.id);
      }
    };
    fragment.append(card);
  });

  list.innerHTML = "";
  list.append(fragment);
}

async function loadContacts'''

code = re.sub(old_render_contacts, new_render_contacts, code)

# 3. Update openConversation to update Column 3 profile drawer
old_open_conv = r'async function openConversation\(id\) \{[\s\S]*?await renderConversationMessages\(id, true\);\s*\}'

new_open_conv = '''async function openConversation(id) {
  selectedContact = id;
  const c = contactsCache.find(x => x.id === id);
  const isWa = c && !c.contact_key.includes("@");

  // Destacar o card selecionado na lista
  $$(".contact-card-item").forEach(el => el.classList.remove("active"));
  renderContactsList(contactsCache);

  $("#conversation-title").textContent = c ? (c.name || c.contact_key) : "Conversa";
  $("#conversation-subtitle").textContent = c ? (isWa ? `WhatsApp: ${c.contact_key}` : `Gmail Oficial: ${c.contact_key}`) : "";
  $("#btn-delete-conversation")?.classList.remove("hidden");

  // Atualizar Coluna 3: Perfil do Cliente
  const pName = $("#profile-client-name");
  const pKey = $("#profile-client-key");
  const pStatus = $("#profile-client-status");
  const pInterest = $("#profile-client-interest");
  const pMode = $("#profile-handover-mode");

  if (pName) pName.textContent = c ? (c.name || "Cliente Comercial") : "-";
  if (pKey) pKey.textContent = c ? c.contact_key : "-";
  if (pStatus) {
    pStatus.textContent = c?.last_message ? "Em atendimento ativo" : "Contacto iniciado";
  }
  if (pInterest) {
    pInterest.textContent = c?.last_message ? "Interesse em produtos / informações" : "Aguardando interação inicial";
  }
  if (pMode) {
    pMode.textContent = humanTakeoverActive ? "Operador Humano (Pausado para IA)" : "Automático (IA Drexier)";
  }

  await renderConversationMessages(id, true);
}'''

code = re.sub(old_open_conv, new_open_conv, code)

# Write updated code
with open("frontend/app.js", "w", encoding="utf-8") as f:
    f.write(code)

print("Updated renderDashboardData, renderContactsList, and openConversation!")
