const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
const initialParams = new URLSearchParams(window.location.search);
if (initialParams.get("token")) {
  localStorage.setItem("drexier_token", initialParams.get("token"));
}
let token = localStorage.getItem("drexier_token") || "";
let me = null, selectedContact = null, infoCache = [], activePage = "dashboard";
let currentExpandedCardId = null, currentEditingItemIndex = null;

const kindNames = {
  horarios: "Horários",
  productos: "Produtos e preços",
  marcacoes: "Tempo para marcações",
  campanhas: "Campanhas",
  servicos: "Serviços e disponibilidade",
  personalizado: "Personalizado"
};

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function authHeaders(json = true) {
  return {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(json ? { "Content-Type": "application/json" } : {})
  };
}

async function api(url, options = {}) {
  const res = await fetch(url, {
    ...options,
    headers: { ...authHeaders(options.body !== undefined), ...(options.headers || {}) }
  });
  let data = {};
  try { data = await res.json(); } catch {}
  if (!res.ok) {
    if (res.status === 401 && token) { logoutNow(); }
    throw new Error(data.detail || "Ocorreu um erro.");
  }
  return data;
}

function showNotice(msg, error = false) {
  const n = $("#notice");
  n.textContent = msg;
  n.classList.remove("hidden", "error-notice");
  if (error) n.classList.add("error-notice");
  window.scrollTo({ top: 0, behavior: "smooth" });
  setTimeout(() => n.classList.add("hidden"), 5000);
}

/* Modal Expansível Global com Fundo Desfocado */
function openModal(htmlContent) {
  const modal = $("#card-expand-modal");
  const shell = $("#expanded-card-content");
  shell.innerHTML = htmlContent;
  modal.classList.remove("hidden");
  document.body.style.overflow = "hidden";
}

function closeModal() {
  const modal = $("#card-expand-modal");
  modal.classList.add("hidden");
  document.body.style.overflow = "";
  currentExpandedCardId = null;
  currentEditingItemIndex = null;
}

$("#card-expand-modal").addEventListener("click", e => {
  if (e.target === $("#card-expand-modal")) closeModal();
});

window.addEventListener("keydown", e => {
  if (e.key === "Escape" && !$("#card-expand-modal").classList.contains("hidden")) {
    closeModal();
  }
});

/* Autenticação */
function setAuthTab(tab) {
  $$("[data-auth]").forEach(b => b.classList.toggle("active", b.dataset.auth === tab));
  $("#login-form").classList.toggle("hidden", tab !== "login");
  $("#signup-form").classList.toggle("hidden", tab !== "signup");
  $("#auth-error").textContent = "";
}
$$("[data-auth]").forEach(b => b.addEventListener("click", () => setAuthTab(b.dataset.auth)));

$("#login-form").addEventListener("submit", async e => {
  e.preventDefault();
  $("#auth-error").textContent = "";
  const d = Object.fromEntries(new FormData(e.target));
  try {
    const r = await api("/api/auth/login", { method: "POST", body: JSON.stringify(d) });
    token = r.token;
    localStorage.setItem("drexier_token", token);
    await boot();
  } catch (err) {
    $("#auth-error").textContent = err.message;
  }
});

$("#signup-form").addEventListener("submit", async e => {
  e.preventDefault();
  $("#auth-error").textContent = "";
  const d = Object.fromEntries(new FormData(e.target));
  if (d.password !== d.confirm_password) {
    $("#auth-error").textContent = "As senhas não coincidem.";
    return;
  }
  try {
    const r = await api("/api/auth/signup", { method: "POST", body: JSON.stringify(d) });
    token = r.token;
    localStorage.setItem("drexier_token", token);
    await boot();
  } catch (err) {
    $("#auth-error").textContent = err.message;
  }
});

function openApp() {
  $("#auth").classList.add("hidden");
  $("#app").classList.remove("hidden");
}

async function boot() {
  try {
    me = await api("/api/me");
    openApp();
    startLivePolling();
    $("#side-user").textContent = me.name;
    $("#top-user").textContent = me.email;
    fillSettings();

    // Deteta se o utilizador acabou de autorizar na Google ou Microsoft via OAuth
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get("email_auth") === "success") {
      const provider = urlParams.get("provider") === "microsoft" ? "Microsoft Outlook" : "Google Gmail";
      showNotice(`Conta de e-mail oficial (${provider}) conectada com sucesso! A IA já está pronta para responder aos clientes.`);
      window.history.replaceState({}, document.title, window.location.pathname);
      await navigate("settings");
      $$("[data-setting]").forEach(x => x.classList.toggle("active", x.dataset.setting === "integration"));
      $$(".setting-panel").forEach(x => x.classList.toggle("hidden", x.id !== "setting-integration"));
      await loadEmailStatus();
      return;
    } else if (urlParams.get("email_auth") === "error") {
      const reason = urlParams.get("reason") || "Erro na autorização do fornecedor de e-mail.";
      showNotice(`Falha na ligação do e-mail: ${reason}`, true);
      window.history.replaceState({}, document.title, window.location.pathname);
      await navigate("settings");
      return;
    }

    await navigate("dashboard");
  } catch (err) {
    if (token) {
      $("#auth").classList.remove("hidden");
      $("#app").classList.add("hidden");
      $("#auth-error").textContent = err.message;
    }
  }
}

function logoutNow() {
  stopLivePolling();
  token = "";
  me = null;
  localStorage.removeItem("drexier_token");
  $("#app").classList.add("hidden");
  $("#auth").classList.remove("hidden");
  $("#confirm-modal").classList.add("hidden");
  closeModal();
}

$("#logout").addEventListener("click", () => $("#confirm-modal").classList.remove("hidden"));
$("#logout-account").addEventListener("click", () => $("#confirm-modal").classList.remove("hidden"));
$("#cancel-logout").addEventListener("click", () => $("#confirm-modal").classList.add("hidden"));
$("#confirm-logout").addEventListener("click", logoutNow);
$("#mobile-menu").addEventListener("click", () => $(".sidebar").classList.toggle("open"));
$$("[data-page]").forEach(b => b.addEventListener("click", () => navigate(b.dataset.page)));
$$("[data-goto]").forEach(b => b.addEventListener("click", () => navigate(b.dataset.goto)));

const pageMeta = {
  dashboard: ["Dashboard", "Visão geral do atendimento"],
  messages: ["Mensagens", "Interações com clientes"],
  reports: ["Relatórios", "Aquisição e desempenho das respostas"],
  business: ["Negócio", "Base de conhecimento do agente"],
  settings: ["Configurações", "Personalize a sua conta e o agente"]
};

async function navigate(page) {
  activePage = page;
  $$("[data-page]").forEach(b => b.classList.toggle("active", b.dataset.page === page));
  $$(".page").forEach(s => s.classList.toggle("hidden", s.id !== `page-${page}`));
  $("#page-title").textContent = pageMeta[page][0];
  $("#page-subtitle").textContent = pageMeta[page][1];
  $(".sidebar").classList.remove("open");
  try {
    if (page === "dashboard") await loadDashboard();
    if (page === "messages") {
      if (!selectedContact) {
        $("#messages-chat-view")?.classList.add("hidden");
        $("#messages-inbox-view")?.classList.remove("hidden");
      }
      await loadContacts();
      await loadEmailStatus();
    }
    if (page === "reports") await loadReports();
    if (page === "business") await loadInfo();
    if (page === "settings") {
      await loadMe();
      await loadEmailStatus();
    }
  } catch (e) {
    showNotice(e.message, true);
  }
}

/* Gráfico de Barras */
function renderBars(target, values) {
  const el = $(target);
  el.innerHTML = "";
  const max = Math.max(1, ...values.map(x => x.count));
  values.forEach(v => {
    const g = document.createElement("div");
    g.className = "bar-group";
    const val = document.createElement("span");
    val.className = "bar-value";
    val.textContent = v.count;
    const bar = document.createElement("div");
    bar.className = "bar";
    bar.style.height = `${Math.max(2, (v.count / max) * 125)}px`;
    bar.title = `${v.date}: ${v.count}`;
    const label = document.createElement("span");
    label.className = "bar-label";
    label.textContent = v.date.slice(5);
    g.append(val, bar, label);
    el.append(g);
  });
}

/* Dashboard com Cards Expansíveis */
function expandMetricCard(title, value, description) {
  openModal(`
    <div class="expanded-header">
      <div class="expanded-header-left">
        <div class="expanded-header-kbadge"><span class="expanded-header-kbadge-dot"></span>MÉTRICA</div>
        <h2 class="expanded-header-title">${escapeHtml(title)}</h2>
      </div>
      <button class="expanded-close" id="modal-close-btn">✕</button>
    </div>
    <div class="expanded-body">
      <div class="modal-metric-center">
        <div class="modal-metric-value">${escapeHtml(value)}</div>
        <p class="modal-metric-desc">${escapeHtml(description)}</p>
      </div>
    </div>
    <div class="expanded-footer" style="justify-content:flex-end">
      <button class="btn primary" id="modal-done-btn">Fechar</button>
    </div>
  `);
  $("#modal-close-btn").onclick = closeModal;
  $("#modal-done-btn").onclick = closeModal;
}

async function loadDashboard() {
  const d = await api("/api/dashboard");
  $("#metric-messages").textContent = d.messages_answered;
  $("#metric-contacts").textContent = d.total_contacts;
  $("#metric-today").textContent = d.today_contacts;
  $("#metric-pending").textContent = d.pending_count;
  $("#compare-yesterday").textContent = `Dia anterior: ${d.yesterday_contacts}`;

  // Tornar os 4 cards de métricas clicáveis e expansíveis
  const metrics = $$(".metric");
  const metricData = [
    { title: "Mensagens Respondidas", val: d.messages_answered, desc: "Total de respostas geradas e enviadas aos clientes pela sua IA Gemini e atendentes." },
    { title: "Clientes Adquiridos", val: d.total_contacts, desc: "Número acumulado de contactos únicos que iniciaram conversa com o seu negócio." },
    { title: "Novos Clientes Hoje", val: `${d.today_contacts} (Ontem: ${d.yesterday_contacts})`, desc: "Novos clientes registados hoje em comparação com o dia anterior." },
    { title: "Pedidos Para Confirmar", val: d.pending_count, desc: "Intenções de compra e pedidos de agendamento recolhidos pelo agente aguardando a sua confirmação." }
  ];
  metrics.forEach((m, i) => {
    m.classList.add("clickable-card");
    m.title = "Clique para expandir";
    if (i === 3 || m.id === "card-metric-pending") {
      m.onclick = () => openPendingConfirmationsModal();
    } else {
      m.onclick = () => expandMetricCard(metricData[i].title, metricData[i].val, metricData[i].desc);
    }
  });

  renderBars("#dashboard-chart", [{ date: "Ontem", count: d.yesterday_contacts }, { date: "Hoje", count: d.today_contacts }]);

  const list = $("#pending-list");
  list.innerHTML = "";
  if (!d.pending_requests.length) {
    list.className = "empty";
    list.textContent = "Nenhum pedido pendente.";
    return;
  }
  list.className = "pending-list";
  d.pending_requests.forEach(r => {
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

    // Expandir modal de validação ao clicar no card
    card.onclick = () => openPendingConfirmationsModal();

    card.append(info, btnGroup);
    list.append(card);
  });
}

$("#btn-open-pending-modal")?.addEventListener("click", () => openPendingConfirmationsModal());

/* Modal Centralizado de Confirmação Automática / Alternativa com IA */
async function openPendingConfirmationsModal() {
  const modal = $("#pending-expand-modal");
  const modalBody = $("#pending-modal-body");
  if (!modal || !modalBody) return;

  modal.classList.remove("hidden");
  document.body.style.overflow = "hidden";
  modalBody.innerHTML = '<div class="empty">A carregar pedidos pendentes...</div>';

  try {
    const d = await api("/api/dashboard");
    const requests = d.pending_requests || [];
    renderPendingModalList(requests);
  } catch (err) {
    modalBody.innerHTML = `<div class="empty">Erro ao carregar pedidos: ${escapeHtml(err.message)}</div>`;
  }
}

function closePendingConfirmationsModal() {
  const modal = $("#pending-expand-modal");
  if (modal) modal.classList.add("hidden");
  document.body.style.overflow = "";
}

$("#close-pending-modal")?.addEventListener("click", closePendingConfirmationsModal);
$("#pending-expand-modal")?.addEventListener("click", e => {
  if (e.target === $("#pending-expand-modal")) closePendingConfirmationsModal();
});
window.addEventListener("keydown", e => {
  if (e.key === "Escape" && !$("#pending-expand-modal")?.classList.contains("hidden")) {
    closePendingConfirmationsModal();
  }
});

function renderPendingModalList(requests) {
  const modalBody = $("#pending-modal-body");
  modalBody.innerHTML = "";
  if (!requests.length) {
    modalBody.innerHTML = '<div class="empty">Nenhum pedido pendente de validação no momento. Todos os pedidos e agendamentos foram tratados.</div>';
    return;
  }

  requests.forEach(r => {
    const card = document.createElement("div");
    card.className = "pending-action-card";

    const header = document.createElement("div");
    header.className = "pending-action-card-header";

    const clientInfo = document.createElement("div");
    clientInfo.innerHTML = `<strong>${escapeHtml(r.name || r.contact_key)}</strong> <span class="muted" style="font-size:12px;">(${escapeHtml(r.contact_key)})</span>`;

    const typeBadge = document.createElement("span");
    typeBadge.className = "pending-action-type";
    typeBadge.textContent = r.request_type || "Pedido";

    header.append(clientInfo, typeBadge);

    const detailsBox = document.createElement("div");
    detailsBox.className = "modal-text-block";
    detailsBox.style.background = "#ffffff";
    detailsBox.style.padding = "10px 14px";
    detailsBox.style.border = "1px solid var(--border)";
    detailsBox.style.borderRadius = "var(--radius-sm)";
    detailsBox.style.fontSize = "13px";
    detailsBox.style.lineHeight = "1.5";
    detailsBox.textContent = r.details || "Pedido aguardando confirmação do proprietário.";

    const noteBox = document.createElement("div");
    noteBox.className = "pending-note-box";
    const noteLabel = document.createElement("label");
    noteLabel.style.fontSize = "12px";
    noteLabel.style.fontWeight = "600";
    noteLabel.style.color = "var(--gray-600)";
    noteLabel.textContent = "Observação ou instrução para a resposta da IA (opcional):";
    const noteInput = document.createElement("textarea");
    noteInput.rows = 2;
    noteInput.placeholder = "Ex: 'Confirmar para as 15h', 'Informar que temos vaga às 16h', ou 'Sugerir modelo alternativo'...";
    noteBox.append(noteLabel, noteInput);

    const actions = document.createElement("div");
    actions.className = "pending-action-buttons";

    const btnConfirm = document.createElement("button");
    btnConfirm.className = "btn-confirm-action";
    btnConfirm.innerHTML = "✓ Confirmar (Enviar E-mail via IA)";
    btnConfirm.onclick = async () => {
      btnConfirm.disabled = true;
      btnReject.disabled = true;
      btnConfirm.textContent = "A gerar e enviar e-mail oficial...";
      try {
        const res = await api(`/api/conversions/${r.id}/action`, {
          method: "POST",
          body: JSON.stringify({ action: "confirm", note: noteInput.value.trim() })
        });
        showNotice(res.detail || "Confirmação enviada por e-mail ao cliente com sucesso!");
        await openPendingConfirmationsModal();
        await loadDashboard();
      } catch (err) {
        showNotice(err.message, true);
        btnConfirm.disabled = false;
        btnReject.disabled = false;
        btnConfirm.innerHTML = "✓ Confirmar (Enviar E-mail via IA)";
      }
    };

    const btnReject = document.createElement("button");
    btnReject.className = "btn-reject-action";
    btnReject.innerHTML = "✕ Não Disponível / Sugerir Outro (IA)";
    btnReject.onclick = async () => {
      btnConfirm.disabled = true;
      btnReject.disabled = true;
      btnReject.textContent = "A gerar e enviar e-mail oficial...";
      try {
        const res = await api(`/api/conversions/${r.id}/action`, {
          method: "POST",
          body: JSON.stringify({ action: "reject", note: noteInput.value.trim() })
        });
        showNotice(res.detail || "Resposta alternativa enviada por e-mail ao cliente com sucesso!");
        await openPendingConfirmationsModal();
        await loadDashboard();
      } catch (err) {
        showNotice(err.message, true);
        btnConfirm.disabled = false;
        btnReject.disabled = false;
        btnReject.innerHTML = "✕ Não Disponível / Sugerir Outro (IA)";
      }
    };

    const btnResolveDirect = document.createElement("button");
    btnResolveDirect.className = "btn outline small";
    btnResolveDirect.textContent = "Apenas Marcar Tratado";
    btnResolveDirect.style.marginLeft = "auto";
    btnResolveDirect.onclick = async () => {
      try {
        await api(`/api/conversions/${r.id}/resolve`, { method: "POST" });
        showNotice("Pedido marcado como tratado.");
        await openPendingConfirmationsModal();
        await loadDashboard();
      } catch (err) {
        showNotice(err.message, true);
      }
    };

    actions.append(btnConfirm, btnReject, btnResolveDirect);

    card.append(header, detailsBox, noteBox, actions);
    modalBody.append(card);
  });
}

/* Mensagens */
let contactsCache = [];

async function loadContacts(keepChatOpen = true) {
  contactsCache = await api("/api/contacts");
  const list = $("#contacts-list");
  if (!list) return;

  list.innerHTML = "";
  if (!contactsCache.length) {
    list.className = "contact-card-grid empty";
    list.textContent = "Ainda não existem conversas. Quando um cliente enviar um e-mail, ele aparecerá aqui.";
    return;
  }
  list.className = "contact-card-grid";

  contactsCache.forEach(c => {
    const card = document.createElement("article");
    card.className = "contact-card-item";

    const initial = (c.name || c.contact_key || "C").trim()[0]?.toUpperCase() || "C";
    const avatar = document.createElement("div");
    avatar.className = "contact-card-avatar";
    avatar.textContent = initial;

    const info = document.createElement("div");
    info.className = "contact-card-info";

    const name = document.createElement("div");
    name.className = "contact-card-name";
    name.textContent = c.name || c.contact_key;

    const email = document.createElement("div");
    email.className = "contact-card-meta";
    email.textContent = c.contact_key;

    const lastMsg = document.createElement("div");
    lastMsg.className = "contact-card-last-msg";
    lastMsg.textContent = c.last_message ? (c.last_message.slice(0, 85) + (c.last_message.length > 85 ? "..." : "")) : "Sem mensagens ainda";

    info.append(name, email, lastMsg);

    const arrow = document.createElement("div");
    arrow.className = "contact-card-arrow";
    arrow.textContent = "→";

    card.append(avatar, info, arrow);
    card.onclick = () => openConversation(c.id);
    list.append(card);
  });

  if (keepChatOpen && selectedContact && contactsCache.some(c => c.id === selectedContact)) {
    if (!$("#messages-chat-view")?.classList.contains("hidden")) {
      await renderConversationMessages(selectedContact, false);
    }
  }
}

$("#refresh-contacts")?.addEventListener("click", () => loadContacts(true).catch(e => showNotice(e.message, true)));

async function openConversation(id) {
  selectedContact = id;
  const c = contactsCache.find(x => x.id === id);

  // Alterna as visualizações: fecha a lista de cards e abre a sala de chat do cliente
  $("#messages-inbox-view")?.classList.add("hidden");
  $("#messages-chat-view")?.classList.remove("hidden");

  $("#conversation-title").textContent = c ? (c.name || c.contact_key) : "Conversa";
  $("#conversation-subtitle").textContent = c ? `E-mail oficial: ${c.contact_key}` : "";
  $("#btn-delete-conversation")?.classList.remove("hidden");

  await renderConversationMessages(id, true);
}

async function renderConversationMessages(id, autoScroll = true) {
  const el = $("#conversation");
  if (!el) return;

  try {
    const msgs = await api(`/api/contacts/${id}/messages`);
    el.innerHTML = "";
    el.className = "conversation";

    if (!msgs.length) {
      el.className = "conversation empty";
      el.textContent = "Sem mensagens nesta conversa.";
      return;
    }

    msgs.forEach(m => {
      const b = document.createElement("div");
      b.className = `bubble ${m.sender}`;

      const textNode = document.createElement("div");
      textNode.textContent = m.content;
      b.append(textNode);

      const footer = document.createElement("div");
      footer.className = "bubble-footer";

      const time = document.createElement("small");
      const senderLabel = m.sender === "customer" ? "Cliente" : m.sender === "agent" ? "IA Drexier" : "Proprietário (Você)";
      time.textContent = `${senderLabel} · ${m.created_at || ""}`;
      footer.append(time);

      const delBtn = document.createElement("button");
      delBtn.type = "button";
      delBtn.className = "btn-delete-msg";
      delBtn.title = "Eliminar esta mensagem";
      delBtn.textContent = "🗑️";
      delBtn.onclick = async (ev) => {
        ev.stopPropagation();
        if (!confirm("Tem a certeza de que deseja eliminar esta mensagem?")) return;
        try {
          await api(`/api/messages/${m.id}`, { method: "DELETE" });
          showNotice("Mensagem eliminada com sucesso.");
          await renderConversationMessages(id, false);
          await loadContacts(true);
        } catch (err) {
          showNotice(err.message, true);
        }
      };
      footer.append(delBtn);

      b.append(footer);
      el.append(b);
    });

    if (autoScroll) {
      el.scrollTop = el.scrollHeight;
    }
  } catch (err) {
    el.className = "conversation empty";
    el.textContent = `Erro ao carregar mensagens: ${err.message}`;
  }
}

// Botão para voltar à lista de clientes (Cards)
$("#btn-back-to-inbox")?.addEventListener("click", () => {
  selectedContact = null;
  $("#messages-chat-view")?.classList.add("hidden");
  $("#messages-inbox-view")?.classList.remove("hidden");
  loadContacts(false);
});

// Envio de resposta oficial direta do proprietário por e-mail
$("#owner-reply-form")?.addEventListener("submit", async e => {
  e.preventDefault();
  if (!selectedContact) {
    showNotice("Selecione um cliente primeiro.", true);
    return;
  }
  const input = $("#owner-reply-input");
  const msg = input.value.trim();
  if (!msg) return;

  const btn = $("#btn-send-owner-reply");
  const originalText = btn.textContent;
  btn.disabled = true;
  btn.textContent = "A enviar por e-mail...";

  try {
    const res = await api(`/api/contacts/${selectedContact}/reply`, {
      method: "POST",
      body: JSON.stringify({ message: msg })
    });
    input.value = "";
    showNotice(res.detail || "Resposta oficial entregue com sucesso no e-mail do cliente!");
    await renderConversationMessages(selectedContact, true);
    await loadContacts(true);
  } catch (err) {
    showNotice(err.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
});

$("#btn-delete-conversation")?.addEventListener("click", async () => {
  if (!selectedContact) return;
  const c = contactsCache.find(x => x.id === selectedContact);
  const name = c ? (c.name || c.contact_key) : "este cliente";
  if (!confirm(`Tem a certeza de que deseja eliminar todas as mensagens e o histórico de ${name}?`)) return;
  try {
    await api(`/api/contacts/${selectedContact}`, { method: "DELETE" });
    showNotice("Conversa eliminada com sucesso.");
    selectedContact = null;
    $("#messages-chat-view")?.classList.add("hidden");
    $("#messages-inbox-view")?.classList.remove("hidden");
    await loadContacts(false);
    await loadDashboard();
  } catch (err) {
    showNotice(err.message, true);
  }
});

// Suporte retrocompatível se existir algum formulário residual de conversão
$("#conversion-form")?.addEventListener("submit", async e => {
  e.preventDefault();
  if (!selectedContact) {
    showNotice("Selecione um cliente primeiro.", true);
    return;
  }
  const d = Object.fromEntries(new FormData(e.target));
  try {
    await api(`/api/contacts/${selectedContact}/conversion`, { method: "POST", body: JSON.stringify(d) });
    showNotice("Pedido registado no dashboard.");
    e.target.reset();
    await loadDashboard();
  } catch (err) {
    showNotice(err.message, true);
  }
});

/* Relatórios */
async function loadReports() {
  const d = await api("/api/analytics");
  const el = $("#reports-chart");
  el.innerHTML = "";
  const vals = d.acquisitions;
  const w = 760, h = 190, pad = 18, max = Math.max(1, ...vals.map(v => v.count));
  const pts = vals.map((v, i) => ({
    x: pad + i * (w - 2 * pad) / Math.max(1, vals.length - 1),
    y: h - pad - (v.count / max) * (h - 2 * pad),
    ...v
  }));
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
  const poly = document.createElementNS(svg.namespaceURI, "polyline");
  poly.setAttribute("points", pts.map(p => `${p.x},${p.y}`).join(" "));
  poly.setAttribute("fill", "none");
  poly.setAttribute("stroke", "#111");
  poly.setAttribute("stroke-width", "2.5");
  svg.append(poly);

  pts.forEach(p => {
    const circle = document.createElementNS(svg.namespaceURI, "circle");
    circle.setAttribute("cx", p.x);
    circle.setAttribute("cy", p.y);
    circle.setAttribute("r", "3.5");
    circle.setAttribute("fill", "#111");
    const title = document.createElementNS(svg.namespaceURI, "title");
    title.textContent = `${p.date}: ${p.count} clientes`;
    circle.append(title);
    svg.append(circle);
  });
  el.append(svg);

  $("#chart-labels").innerHTML = "";
  [vals[0], vals[Math.floor(vals.length / 2)], vals[vals.length - 1]].forEach(v => {
    const s = document.createElement("span");
    s.textContent = `${v.date} · ${v.count}`;
    $("#chart-labels").append(s);
  });

  const list = $("#variants-list");
  list.innerHTML = "";
  if (!d.variants.length) {
    list.className = "variant-list empty";
    list.textContent = "Ainda não existem variantes.";
    return;
  }
  list.className = "variant-list card-grid";
  d.variants.forEach(v => {
    const card = document.createElement("article");
    card.className = "variant-card clickable-card";
    const h = document.createElement("h3");
    h.textContent = v.label;
    const p = document.createElement("p");
    p.textContent = v.response_text;
    const stats = document.createElement("p");
    stats.textContent = `Envios: ${v.sent_count} · Conversões: ${v.conversions}`;

    card.onclick = () => {
      openModal(`
        <div class="expanded-header">
          <div class="expanded-header-left">
            <div class="expanded-header-kbadge"><span class="expanded-header-kbadge-dot"></span>VARIANTE DE RESPOSTA</div>
            <h2 class="expanded-header-title">${escapeHtml(v.label)}</h2>
          </div>
          <button class="expanded-close" id="modal-close-btn">✕</button>
        </div>
        <div class="expanded-body">
          <div class="modal-section">
            <div class="modal-section-label">Texto configurado</div>
            <div class="modal-text-block">${escapeHtml(v.response_text)}</div>
          </div>
          <div class="modal-section">
            <div class="modal-section-label">Estatísticas</div>
            <div class="modal-stat-row">
              <div class="modal-stat-chip"><span>Envios</span><strong>${v.sent_count}</strong></div>
              <div class="modal-stat-chip"><span>Conversões</span><strong>${v.conversions}</strong></div>
            </div>
          </div>
        </div>
        <div class="expanded-footer">
          <button class="btn outline small danger" id="delete-variant-modal-btn">Eliminar estilo</button>
          <button class="btn primary" id="modal-done-btn">Fechar</button>
        </div>
      `);
      $("#modal-close-btn").onclick = closeModal;
      $("#modal-done-btn").onclick = closeModal;
      $("#delete-variant-modal-btn").onclick = async () => {
        if (!confirm("Eliminar este estilo de resposta?")) return;
        try {
          await api(`/api/variants/${v.id}`, { method: "DELETE" });
          closeModal();
          loadReports();
        } catch (e) {
          showNotice(e.message, true);
        }
      };
    };

    card.append(h, p, stats);
    list.append(card);
  });
}

$("#add-variant").addEventListener("click", () => $("#variant-form").classList.remove("hidden"));
$("#cancel-variant").addEventListener("click", () => $("#variant-form").classList.add("hidden"));
$("#variant-form").addEventListener("submit", async e => {
  e.preventDefault();
  try {
    await api("/api/variants", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(e.target))) });
    e.target.reset();
    e.target.classList.add("hidden");
    showNotice("Estilo guardado.");
    loadReports();
  } catch (err) {
    showNotice(err.message, true);
  }
});

/* ========================================================================= */
/* ABA NEGÓCIO: CARDS EXPANSÍVEIS E GESTÃO DE MÚLTIPLOS ITENS POR CARD      */
/* ========================================================================= */

function compileItemsToContent(items, generalNote = "") {
  if (!items || !items.length) {
    return generalNote || "Sem itens cadastrados.";
  }
  const lines = items.map(it => {
    const parts = [it.name || "Item"];
    if (it.price) parts.push(`Preço: ${it.price}`);
    if (it.details) parts.push(`Detalhes: ${it.details}`);
    return "• " + parts.join(" | ");
  });
  if (generalNote) {
    lines.push(`\nNota geral: ${generalNote}`);
  }
  return lines.join("\n");
}

function renderBusinessCardItemsHtml(it, editingIndex = null) {
  const meta = it.metadata || {};
  const items = Array.isArray(meta.items) ? meta.items : [];
  const kindTitle = kindNames[it.kind] || it.kind;
  const editItem = (editingIndex !== null && items[editingIndex]) ? items[editingIndex] : null;

  let itemsHtml = "";
  if (!items.length) {
    itemsHtml = `
      <div class="item-entry-empty">
        Nenhum item adicionado a este card ainda.<br>
        <span class="muted">Adicione todos os seus produtos, serviços ou horários aqui em baixo para que a IA os utilize nas respostas.</span>
      </div>
    `;
  } else {
    itemsHtml = `<div class="items-list">` + items.map((item, idx) => `
      <div class="item-entry ${editingIndex === idx ? 'editing' : ''}">
        <div class="item-entry-index">${idx + 1}</div>
        <div class="item-entry-info">
          <div class="item-entry-title">
            <span>${escapeHtml(item.name || "Item")}</span>
            ${item.price ? `<span class="item-entry-price">${escapeHtml(item.price)}</span>` : ""}
          </div>
          ${item.details ? `<p class="item-entry-desc">${escapeHtml(item.details)}</p>` : ""}
        </div>
        <div class="item-entry-actions">
          <button class="btn xs ghost edit-item-action" data-idx="${idx}">Editar</button>
          <button class="btn xs danger delete-item-action" data-idx="${idx}">✕</button>
        </div>
      </div>
    `).join("") + `</div>`;
  }

  const isProductOrService = ["productos", "servicos"].includes(it.kind);
  const namePlaceholder = isProductOrService ? "Ex: Ténis Running Pro ou Corte Clássico" : "Ex: Segunda a Sexta ou Campanha Verão";
  const pricePlaceholder = isProductOrService ? "Ex: 80€ ou 15€" : "Ex: 09h às 18h ou 20% Desc.";
  const detailsPlaceholder = isProductOrService ? "Ex: Tamanhos 38 ao 44, cores preto e azul" : "Ex: Válido para marcações online até fim do mês";

  return `
    <div class="expanded-header">
      <div class="expanded-header-left">
        <div class="expanded-header-kbadge"><span class="expanded-header-kbadge-dot"></span>${kindTitle}</div>
        <h2 class="expanded-header-title">${escapeHtml(it.title)}</h2>
        <p class="expanded-header-subtitle">${items.length} ${items.length === 1 ? 'item cadastrado' : 'itens cadastrados'}</p>
      </div>
      <button class="expanded-close" id="modal-close-btn" title="Fechar">✕</button>
    </div>
    <div class="expanded-body">
      <div class="modal-section">
        <div class="modal-section-label">Itens do card</div>
        <div class="modal-items-count"><span class="modal-items-count-num">${items.length}</span> itens neste card</div>
        ${itemsHtml}
      </div>

      <div class="item-inline-builder">
        <div class="item-builder-title">
          ${editItem ? "Editar item" : "+ Adicionar novo item"}
          ${!editItem ? `<span class="item-builder-badge">NOVO</span>` : ""}
        </div>
        <div class="item-builder-grid">
          <div class="item-builder-label">Nome / Título<input id="builder-name" placeholder="${namePlaceholder}" value="${editItem ? escapeHtml(editItem.name || '') : ''}"></div>
          <div class="item-builder-label">Preço / Valor / Horário<input id="builder-price" placeholder="${pricePlaceholder}" value="${editItem ? escapeHtml(editItem.price || '') : ''}"></div>
        </div>
        <div class="item-builder-label">Detalhes adicionais (opcional)<input id="builder-details" placeholder="${detailsPlaceholder}" value="${editItem ? escapeHtml(editItem.details || '') : ''}"></div>
        <div class="actions" style="margin-top:8px">
          <button class="btn primary small" id="builder-save-btn">${editItem ? "Guardar alterações" : "Adicionar ao card"}</button>
          ${editItem ? `<button class="btn ghost small" id="builder-cancel-btn">Cancelar</button>` : ""}
        </div>
      </div>

      <div class="modal-section">
        <div class="modal-section-label">Definições do card</div>
        <div class="modal-card-settings">
          <div class="modal-card-settings-label">Título do Card<input id="card-title-field" value="${escapeHtml(it.title)}"></div>
          <div class="modal-card-settings-label">Observações gerais ou políticas<textarea id="card-general-notes" rows="2" placeholder="Ex: Entregas em 24h em Portugal continental...">${escapeHtml(meta.generalNote || '')}</textarea></div>
        </div>
      </div>
    </div>
    <div class="expanded-footer">
      <button class="btn outline small danger" id="delete-entire-card-btn">Eliminar card</button>
      <button class="btn primary" id="modal-done-btn">Concluído</button>
    </div>
  `;
}

function openExpandBusinessCard(cardId, editingIdx = null) {
  const it = infoCache.find(x => x.id === cardId);
  if (!it) return;
  currentExpandedCardId = cardId;
  currentEditingItemIndex = editingIdx;

  const html = renderBusinessCardItemsHtml(it, editingIdx);
  openModal(html);

  // Vincular eventos dentro do card expandido
  $("#modal-close-btn").onclick = closeModal;
  $("#modal-done-btn").onclick = async () => {
    await saveCardGeneralData(cardId);
    closeModal();
  };

  // Botão Adicionar / Atualizar item
  $("#builder-save-btn").onclick = async () => {
    const name = $("#builder-name").value.trim();
    const price = $("#builder-price").value.trim();
    const details = $("#builder-details").value.trim();

    if (!name) {
      alert("Por favor, preencha o nome do item.");
      return;
    }

    const meta = it.metadata || {};
    const items = Array.isArray(meta.items) ? [...meta.items] : [];

    if (editingIdx !== null && items[editingIdx]) {
      items[editingIdx] = { ...items[editingIdx], name, price, details };
    } else {
      items.push({ id: Date.now().toString(), name, price, details });
    }

    meta.items = items;
    meta.generalNote = $("#card-general-notes").value.trim();
    it.metadata = meta;
    it.title = $("#card-title-field").value.trim() || it.title;
    it.content = compileItemsToContent(items, meta.generalNote);

    try {
      await api(`/api/business-info/${cardId}`, {
        method: "PUT",
        body: JSON.stringify({
          kind: it.kind,
          title: it.title,
          content: it.content,
          metadata: it.metadata
        })
      });
      await loadInfo();
      openExpandBusinessCard(cardId, null);
    } catch (err) {
      showNotice(err.message, true);
    }
  };

  if ($("#builder-cancel-btn")) {
    $("#builder-cancel-btn").onclick = () => openExpandBusinessCard(cardId, null);
  }

  // Ações de Editar e Eliminar itens
  $$(".edit-item-action").forEach(btn => {
    btn.onclick = () => {
      const idx = parseInt(btn.dataset.idx, 10);
      openExpandBusinessCard(cardId, idx);
    };
  });

  $$(".delete-item-action").forEach(btn => {
    btn.onclick = async () => {
      const idx = parseInt(btn.dataset.idx, 10);
      const meta = it.metadata || {};
      const items = Array.isArray(meta.items) ? [...meta.items] : [];
      items.splice(idx, 1);
      meta.items = items;
      it.metadata = meta;
      it.content = compileItemsToContent(items, $("#card-general-notes").value.trim());

      try {
        await api(`/api/business-info/${cardId}`, {
          method: "PUT",
          body: JSON.stringify({
            kind: it.kind,
            title: it.title,
            content: it.content,
            metadata: it.metadata
          })
        });
        await loadInfo();
        openExpandBusinessCard(cardId, null);
      } catch (err) {
        showNotice(err.message, true);
      }
    };
  });

  // Eliminar card inteiro
  $("#delete-entire-card-btn").onclick = async () => {
    if (!confirm(`Tem a certeza de que deseja eliminar o card "${it.title}" e todos os seus itens?`)) return;
    try {
      await api(`/api/business-info/${cardId}`, { method: "DELETE" });
      showNotice("Card eliminado.");
      closeModal();
      await loadInfo();
    } catch (err) {
      showNotice(err.message, true);
    }
  };
}

async function saveCardGeneralData(cardId) {
  const it = infoCache.find(x => x.id === cardId);
  if (!it) return;
  const newTitle = $("#card-title-field")?.value.trim() || it.title;
  const newNotes = $("#card-general-notes")?.value.trim() || "";
  const meta = it.metadata || {};
  meta.generalNote = newNotes;
  it.title = newTitle;
  it.metadata = meta;
  it.content = compileItemsToContent(meta.items || [], newNotes);

  try {
    await api(`/api/business-info/${cardId}`, {
      method: "PUT",
      body: JSON.stringify({
        kind: it.kind,
        title: it.title,
        content: it.content,
        metadata: it.metadata
      })
    });
    await loadInfo();
  } catch (err) {
    showNotice(err.message, true);
  }
}

async function loadInfo() {
  infoCache = await api("/api/business-info");
  const list = $("#info-list");
  list.innerHTML = "";
  if (!infoCache.length) {
    list.className = "card-grid empty";
    list.textContent = "Ainda não existem informações cadastradas.";
    return;
  }
  list.className = "card-grid";

  const kindIcons = {
    horarios: "🕐", productos: "📦", marcacoes: "📅",
    campanhas: "🎯", servicos: "⚙️", personalizado: "✏️"
  };

  infoCache.forEach(it => {
    const meta = it.metadata || {};
    const items = Array.isArray(meta.items) ? meta.items : [];

    const card = document.createElement("article");
    card.className = "info-card";

    // Accent stripe
    const stripe = document.createElement("div");
    stripe.className = "info-card-stripe";

    // Body
    const body = document.createElement("div");
    body.className = "info-card-body";

    // Top row: kind badge + chevron
    const top = document.createElement("div");
    top.className = "info-card-top";

    const kindBadge = document.createElement("div");
    kindBadge.className = "card-kind-badge";
    const icon = document.createElement("span");
    icon.className = "card-kind-icon";
    icon.textContent = kindIcons[it.kind] || "📋";
    kindBadge.append(icon, document.createTextNode(kindNames[it.kind] || it.kind));

    const chevron = document.createElement("span");
    chevron.className = "card-chevron";
    chevron.textContent = "›";

    top.append(kindBadge, chevron);

    // Title
    const h = document.createElement("h3");
    h.className = "info-card-title";
    h.textContent = it.title;

    // Preview
    const preview = document.createElement("div");
    preview.className = "info-card-preview";

    if (items.length > 0) {
      const count = document.createElement("div");
      count.className = "info-card-count";
      count.textContent = `${items.length} ${items.length === 1 ? "item cadastrado" : "itens cadastrados"}`;

      const chips = document.createElement("div");
      chips.className = "preview-chips";
      items.slice(0, 3).forEach(item => {
        const chip = document.createElement("span");
        chip.className = "preview-chip";
        const name = document.createElement("span");
        name.className = "preview-chip-name";
        name.textContent = item.name || "Item";
        chip.append(name);
        if (item.price) {
          const price = document.createElement("span");
          price.className = "preview-chip-price";
          price.textContent = item.price;
          chip.append(price);
        }
        chips.append(chip);
      });
      if (items.length > 3) {
        const more = document.createElement("span");
        more.className = "preview-chip-more";
        more.textContent = `+${items.length - 3} mais`;
        chips.append(more);
      }
      preview.append(count, chips);
    } else {
      const p = document.createElement("p");
      p.className = "info-card-text-preview";
      p.textContent = it.content ? (it.content.slice(0, 110) + (it.content.length > 110 ? "…" : "")) : "Sem itens cadastrados.";
      preview.append(p);
    }

    body.append(top, h, preview);

    // Footer
    const footer = document.createElement("div");
    footer.className = "info-card-footer";
    const cta = document.createElement("span");
    cta.className = "info-card-cta";
    cta.textContent = "Gerir itens";
    const arrow = document.createElement("span");
    arrow.className = "info-card-arrow";
    arrow.textContent = "→";
    footer.append(cta, arrow);

    card.append(stripe, body, footer);
    card.onclick = () => openExpandBusinessCard(it.id);
    list.append(card);
  });
}

// Botão Nova Informação / Seletor de Tipo
$("#new-info").addEventListener("click", () => {
  $("#info-kind-picker").classList.toggle("hidden");
});

$$(".kind-option").forEach(b => b.addEventListener("click", async () => {
  const kind = b.dataset.kind;
  $("#info-kind-picker").classList.add("hidden");

  // Se já existe um card deste tipo, abre o card existente para concentrar todos os itens no mesmo card
  const existing = infoCache.find(x => x.kind === kind);
  if (existing) {
    showNotice(`Aberto o card de ${kindNames[kind] || kind} existente.`);
    openExpandBusinessCard(existing.id);
    return;
  }

  // Se ainda não existe, cria o card da categoria e abre diretamente expandido para cadastrar os itens
  try {
    const defaultTitle = kindNames[kind] || "Informações";
    const created = await api("/api/business-info", {
      method: "POST",
      body: JSON.stringify({
        kind: kind,
        title: defaultTitle,
        content: `Lista de ${defaultTitle}`,
        metadata: { items: [], generalNote: "" }
      })
    });
    showNotice(`Card de ${defaultTitle} criado. Adicione os itens.`);
    await loadInfo();
    openExpandBusinessCard(created.id);
  } catch (err) {
    showNotice(err.message, true);
  }
}));

/* Configurações */
$$("[data-setting]").forEach(b => b.addEventListener("click", () => {
  $$("[data-setting]").forEach(x => x.classList.toggle("active", x === b));
  $$(".setting-panel").forEach(x => x.classList.toggle("hidden", x.id !== `setting-${b.dataset.setting}`));
  if (b.dataset.setting === "integration") {
    loadEmailStatus();
  }
}));

function fillSettings() {
  if (!me) return;
  const f = $("#account-form");
  f.elements.name.value = me.name || "";
  f.elements.email.value = me.email || "";
  f.elements.business_type.value = me.business_type || "Outro";
  f.elements.business_description.value = me.business_description || "";
  f.elements.language.value = me.language || "Português";
  $("#instructions-form").elements.instructions.value = me.agent_instructions || "";
  const mandatory = me.mandatory_responses || {};
  const mf = $("#mandatory-form");
  ["greeting", "unknown", "conversion", "closing"].forEach(k => mf.elements[k].value = mandatory[k] || "");
}

async function loadMe() {
  me = await api("/api/me");
  fillSettings();
}

$("#instructions-form").addEventListener("submit", async e => {
  e.preventDefault();
  try {
    const meNow = await api("/api/me");
    await api("/api/agent-settings", {
      method: "PUT",
      body: JSON.stringify({ instructions: e.target.elements.instructions.value, mandatory_responses: meNow.mandatory_responses || {} })
    });
    me = await api("/api/me");
    fillSettings();
    showNotice("Instruções guardadas.");
  } catch (err) {
    showNotice(err.message, true);
  }
});

$("#mandatory-form").addEventListener("submit", async e => {
  e.preventDefault();
  try {
    const meNow = await api("/api/me");
    const mandatory = Object.fromEntries(["greeting", "unknown", "conversion", "closing"].map(k => [k, e.target.elements[k].value.trim()]));
    await api("/api/agent-settings", {
      method: "PUT",
      body: JSON.stringify({ instructions: meNow.agent_instructions || "", mandatory_responses: mandatory })
    });
    me = await api("/api/me");
    showNotice("Respostas obrigatórias guardadas.");
  } catch (err) {
    showNotice(err.message, true);
  }
});

$("#account-form").addEventListener("submit", async e => {
  e.preventDefault();
  const d = Object.fromEntries(new FormData(e.target));
  delete d.email;
  try {
    await api("/api/account", { method: "PUT", body: JSON.stringify(d) });
    me = await api("/api/me");
    fillSettings();
    $("#side-user").textContent = me.name;
    showNotice("Conta atualizada.");
  } catch (err) {
    showNotice(err.message, true);
  }
});

/* ════════════════════════════════════════════════════════════
   INTEGRAÇÃO DE E-MAIL OFICIAL (GOOGLE GMAIL & MICROSOFT OUTLOOK)
   ════════════════════════════════════════════════════════════ */
let emailConfig = null;

async function loadEmailStatus() {
  const loading = $("#email-loading-state");
  const envWarning = $("#email-env-warning");
  const disconnectedView = $("#email-disconnected-view");
  const connectedView = $("#email-connected-view");
  const badge = $("#email-status-badge");

  if (!loading || !disconnectedView || !connectedView) return;

  loading.classList.remove("hidden");
  envWarning?.classList.add("hidden");
  disconnectedView.classList.add("hidden");
  connectedView.classList.add("hidden");

  try {
    // 1. Obtém a configuração pública de provedores (Google e Microsoft)
    try {
      emailConfig = await api("/api/email/config");
      const hasConfig = emailConfig && (emailConfig.google?.configured || emailConfig.microsoft?.configured);
      if (!hasConfig && envWarning) {
        envWarning.classList.remove("hidden");
      }
    } catch (e) {
      console.warn("[Drexier] Não foi possível obter configuração pública de e-mail:", e);
    }

    // 2. Consulta o status da integração de e-mail da conta atual
    const data = await api("/api/email/status");
    loading.classList.add("hidden");

    if (data.connected && data.integration) {
      const it = data.integration;
      if (badge) {
        badge.textContent = "Conectado";
        badge.className = "badge badge-connected";
      }

      let providerName = "E-mail Oficial";
      if (it.provider === "google") providerName = "Google Gmail";
      else if (it.provider === "microsoft") providerName = "Microsoft Outlook";
      else if (it.provider === "smtp_imap") providerName = "Servidor SMTP / IMAP";

      const dispProvider = $("#email-display-provider");
      const dispAddr = $("#email-display-address");
      const infoProv = $("#email-info-provider");
      const infoName = $("#email-info-name");
      const infoLastSync = $("#email-info-last-sync");

      if (dispProvider) dispProvider.textContent = `${providerName} Conectado`;
      if (dispAddr) dispAddr.textContent = it.email_address;
      if (infoProv) infoProv.textContent = providerName;
      if (infoName) infoName.textContent = it.display_name || me?.name || "Atendimento Oficial";
      if (infoLastSync) {
        infoLastSync.textContent = it.last_sync_at ? new Date(it.last_sync_at).toLocaleString("pt-PT") : "Ainda não sincronizado";
      }

      updateAutoReplyUI(Boolean(it.auto_reply_enabled), true);
      connectedView.classList.remove("hidden");
    } else {
      updateAutoReplyUI(false, false);
      if (badge) {
        badge.textContent = "Desconectado";
        badge.className = "badge badge-disconnected";
      }
      disconnectedView.classList.remove("hidden");
    }
  } catch (err) {
    loading.classList.add("hidden");
    disconnectedView.classList.remove("hidden");
    showNotice("Não foi possível carregar o estado do e-mail: " + err.message, true);
  }
}

// Conectar via Google Gmail (OAuth 2.0 Oficial)
$("#btn-connect-google")?.addEventListener("click", async () => {
  const statusEl = $("#email-connect-status");
  try {
    if (statusEl) statusEl.textContent = "A preparar ligação segura com a Google...";
    const res = await api("/api/email/oauth/google/url");
    if (res && res.url) {
      if (statusEl) statusEl.textContent = "A redirecionar para a página oficial da Google...";
      window.location.href = res.url;
    } else {
      throw new Error("URL de autenticação Google não fornecida pelo servidor.");
    }
  } catch (err) {
    if (statusEl) statusEl.textContent = "";
    showNotice(err.message, true);
  }
});

// Conectar via Microsoft Outlook (OAuth 2.0 Oficial)
$("#btn-connect-microsoft")?.addEventListener("click", async () => {
  const statusEl = $("#email-connect-status");
  try {
    if (statusEl) statusEl.textContent = "A preparar ligação segura com a Microsoft...";
    const res = await api("/api/email/oauth/microsoft/url");
    if (res && res.url) {
      if (statusEl) statusEl.textContent = "A redirecionar para a página oficial da Microsoft...";
      window.location.href = res.url;
    } else {
      throw new Error("URL de autenticação Microsoft não fornecida pelo servidor.");
    }
  } catch (err) {
    if (statusEl) statusEl.textContent = "";
    showNotice(err.message, true);
  }
});

// Toggle formulário manual de e-mail (SMTP/IMAP)
$("#btn-toggle-manual-email")?.addEventListener("click", () => {
  $("#email-manual-box")?.classList.toggle("hidden");
});
$("#btn-cancel-manual-email")?.addEventListener("click", () => {
  $("#email-manual-box")?.classList.add("hidden");
});

// Envio formulário manual de e-mail
$("#email-manual-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const d = Object.fromEntries(new FormData(e.target));
  d.smtp_port = parseInt(d.smtp_port, 10) || 587;
  try {
    const res = await api("/api/email/connect-manual", {
      method: "POST",
      body: JSON.stringify(d)
    });
    showNotice(res.message || "E-mail conectado com sucesso!");
    $("#email-manual-box")?.classList.add("hidden");
    e.target.reset();
    await loadEmailStatus();
  } catch (err) {
    showNotice(err.message, true);
  }
});

// Desconectar E-mail
$("#btn-email-disconnect")?.addEventListener("click", async () => {
  if (!confirm("Tem a certeza de que deseja desconectar o e-mail oficial desta conta? A IA Drexier deixará de responder aos e-mails recebidos até voltar a conectar.")) {
    return;
  }
  try {
    await api("/api/email/disconnect", { method: "POST" });
    showNotice("E-mail desconectado com sucesso.");
    await loadEmailStatus();
  } catch (err) {
    showNotice(err.message, true);
  }
});

// Sincronização manual de e-mails
async function handleEmailSync(triggerBtn) {
  if (triggerBtn) {
    triggerBtn.disabled = true;
    triggerBtn.textContent = "A sincronizar...";
  }
  try {
    const res = await api("/api/email/sync", { method: "POST" });
    showNotice(res.message || "Sincronização concluída com sucesso!");
    await loadEmailStatus();
    if (activePage === "messages") {
      await loadContacts();
    }
  } catch (err) {
    showNotice(err.message, true);
  } finally {
    if (triggerBtn) {
      triggerBtn.disabled = false;
      triggerBtn.textContent = triggerBtn.id === "btn-sync-emails-messages" ? "Sincronizar E-mails" : "Sincronizar E-mails Agora";
    }
  }
}

$("#btn-email-sync")?.addEventListener("click", (e) => handleEmailSync(e.target));
$("#btn-sync-emails-messages")?.addEventListener("click", (e) => handleEmailSync(e.target));

// Controlo de Respostas Automáticas do Agente
function updateAutoReplyUI(enabled, connected = true) {
  const autoReplyText = $("#email-info-auto-reply");
  const autoReplyBtn = $("#btn-toggle-auto-reply");
  const msgToggleBtn = $("#btn-toggle-auto-reply-messages");
  const liveStatusDot = $("#live-status-dot");
  const liveStatusBar = $("#conversation-live-status");
  const liveStatusText = $("#live-status-text");

  if (!connected) {
    if (autoReplyText) {
      autoReplyText.textContent = "Desconectado";
      autoReplyText.className = "wa-text-gray";
    }
    if (autoReplyBtn) {
      autoReplyBtn.textContent = "Desativado";
      autoReplyBtn.disabled = true;
    }
    if (msgToggleBtn) {
      msgToggleBtn.textContent = "Respostas IA: Desconectado";
      msgToggleBtn.className = "btn outline small";
    }
    return;
  }

  if (autoReplyBtn) autoReplyBtn.disabled = false;

  if (enabled) {
    if (autoReplyText) {
      autoReplyText.textContent = "Ativa";
      autoReplyText.className = "wa-text-green";
    }
    if (autoReplyBtn) {
      autoReplyBtn.textContent = "Desativar";
    }
    if (msgToggleBtn) {
      msgToggleBtn.textContent = "Respostas IA: Ativas";
      msgToggleBtn.className = "btn outline small";
      msgToggleBtn.style.borderColor = "#10b981";
      msgToggleBtn.style.color = "#059669";
    }
    if (liveStatusDot) liveStatusDot.className = "live-pulse-dot";
    if (liveStatusBar) liveStatusBar.className = "conversation-live-bar";
    if (liveStatusText) {
      liveStatusText.textContent = "Atendimento oficial por e-mail ativo · A IA Drexier responde automaticamente em tempo real a todas as mensagens enviadas ao seu e-mail vinculado.";
    }
  } else {
    if (autoReplyText) {
      autoReplyText.textContent = "Pausada";
      autoReplyText.className = "wa-text-gray";
    }
    if (autoReplyBtn) {
      autoReplyBtn.textContent = "Ativar";
    }
    if (msgToggleBtn) {
      msgToggleBtn.textContent = "Respostas IA: Pausadas";
      msgToggleBtn.className = "btn outline small";
      msgToggleBtn.style.borderColor = "#f59e0b";
      msgToggleBtn.style.color = "#d97706";
    }
    if (liveStatusDot) liveStatusDot.className = "live-pulse-dot paused";
    if (liveStatusBar) liveStatusBar.className = "conversation-live-bar paused";
    if (liveStatusText) {
      liveStatusText.textContent = "Respostas automáticas pausadas · As mensagens são recebidas no painel, mas a IA não enviará respostas automáticas por e-mail.";
    }
  }
}

async function toggleAutoReply() {
  try {
    const statusData = await api("/api/email/status");
    if (!statusData.connected) {
      showNotice("Conecte primeiro o seu e-mail nas configurações para gerir as respostas automáticas.", true);
      return;
    }
    const currentEnabled = Boolean(statusData.integration.auto_reply_enabled);
    const newEnabled = !currentEnabled;
    const res = await api("/api/email/auto-reply", {
      method: "POST",
      body: JSON.stringify({ enabled: newEnabled })
    });
    showNotice(res.message);
    updateAutoReplyUI(newEnabled, true);
    await loadEmailStatus();
  } catch (err) {
    showNotice(err.message, true);
  }
}

$("#btn-toggle-auto-reply")?.addEventListener("click", toggleAutoReply);
$("#btn-toggle-auto-reply-messages")?.addEventListener("click", toggleAutoReply);

// Monitorização e atualização contínua em segundo plano (tempo real)
let livePollTimer = null;

function startLivePolling() {
  if (livePollTimer) clearInterval(livePollTimer);
  livePollTimer = setInterval(async () => {
    if (!token) return;
    try {
      if (activePage === "messages") {
        await loadContacts();
      } else if (activePage === "dashboard") {
        await loadDashboard();
      }
    } catch (e) {
      // Ignora falhas temporárias na atualização automática
    }
  }, 15000);
}

function stopLivePolling() {
  if (livePollTimer) {
    clearInterval(livePollTimer);
    livePollTimer = null;
  }
}

if (token) boot();
