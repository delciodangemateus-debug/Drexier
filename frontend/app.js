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
    if (page === "messages") await loadContacts();
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
    m.onclick = () => expandMetricCard(metricData[i].title, metricData[i].val, metricData[i].desc);
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

    const btn = document.createElement("button");
    btn.className = "btn outline small";
    btn.textContent = "Marcar como tratado";
    btn.onclick = async e => {
      e.stopPropagation();
      try {
        await api(`/api/conversions/${r.id}/resolve`, { method: "POST" });
        showNotice("Pedido atualizado.");
        loadDashboard();
      } catch (err) {
        showNotice(err.message, true);
      }
    };

    // Expandir pedido ao clicar no card
    card.onclick = () => {
      openModal(`
        <div class="expanded-header">
          <div class="expanded-header-left">
            <div class="expanded-header-kbadge"><span class="expanded-header-kbadge-dot"></span>PEDIDO PENDENTE</div>
            <h2 class="expanded-header-title">${escapeHtml(r.name || r.contact_key)}</h2>
          </div>
          <button class="expanded-close" id="modal-close-btn">✕</button>
        </div>
        <div class="expanded-body">
          <div class="modal-section">
            <div class="modal-section-label">Informações do pedido</div>
            <div class="modal-info-row">
              <div class="modal-info-row-label">TIPO</div>
              <div class="modal-info-row-value">${escapeHtml(r.request_type)}</div>
            </div>
            <div class="modal-info-row">
              <div class="modal-info-row-label">CONTACTO</div>
              <div class="modal-info-row-value">${escapeHtml(r.contact_key)}</div>
            </div>
          </div>
          <div class="modal-section">
            <div class="modal-section-label">Detalhes registados pelo agente</div>
            <div class="modal-text-block">${escapeHtml(r.details || 'Sem detalhes específicos informados.')}</div>
          </div>
        </div>
        <div class="expanded-footer">
          <button class="btn outline small danger" id="modal-resolve-btn">Marcar como tratado</button>
          <button class="btn primary" id="modal-done-btn">Fechar</button>
        </div>
      `);
      $("#modal-close-btn").onclick = closeModal;
      $("#modal-done-btn").onclick = closeModal;
      $("#modal-resolve-btn").onclick = async () => {
        try {
          await api(`/api/conversions/${r.id}/resolve`, { method: "POST" });
          showNotice("Pedido marcado como tratado.");
          closeModal();
          loadDashboard();
        } catch (err) {
          showNotice(err.message, true);
        }
      };
    };

    card.append(info, btn);
    list.append(card);
  });
}

/* Mensagens */
let contactsCache = [];
async function loadContacts() {
  contactsCache = await api("/api/contacts");
  const list = $("#contacts-list");
  list.innerHTML = "";
  if (!contactsCache.length) {
    list.className = "empty";
    list.textContent = "Ainda não existem conversas.";
    return;
  }
  list.className = "contact-list";
  contactsCache.forEach(c => {
    const b = document.createElement("button");
    b.className = "contact-item" + (selectedContact === c.id ? " selected" : "");
    const strong = document.createElement("strong");
    strong.textContent = c.name || c.contact_key;
    const small = document.createElement("small");
    small.textContent = c.contact_key;
    const span = document.createElement("span");
    span.textContent = c.last_message || "Sem mensagens";
    b.append(strong, small, span);
    b.onclick = () => openConversation(c.id);
    list.append(b);
  });
  if (selectedContact && contactsCache.some(c => c.id === selectedContact)) {
    await openConversation(selectedContact);
  }
}
$("#refresh-contacts").addEventListener("click", () => loadContacts().catch(e => showNotice(e.message, true)));

async function openConversation(id) {
  selectedContact = id;
  const c = contactsCache.find(x => x.id === id);
  $("#conversation-title").textContent = c ? (c.name || c.contact_key) : "Conversa";
  $$(".contact-item").forEach((b, i) => b.classList.toggle("selected", contactsCache[i]?.id === id));
  const msgs = await api(`/api/contacts/${id}/messages`);
  const el = $("#conversation");
  el.innerHTML = "";
  el.className = "conversation";
  if (!msgs.length) {
    el.className = "conversation empty";
    el.textContent = "Sem mensagens.";
  }
  msgs.forEach(m => {
    const b = document.createElement("div");
    b.className = `bubble ${m.sender}`;
    b.textContent = m.content;
    const time = document.createElement("small");
    time.textContent = `${m.sender === "customer" ? "Cliente" : m.sender === "agent" ? "Agente" : "Proprietário"} · ${m.created_at}`;
    b.append(time);
    el.append(b);
  });
  el.scrollTop = el.scrollHeight;
  $("#conversion-form").classList.remove("hidden");
}

$("#incoming-form").addEventListener("submit", async e => {
  e.preventDefault();
  const d = Object.fromEntries(new FormData(e.target));
  try {
    const r = await api("/api/simulate/incoming", { method: "POST", body: JSON.stringify(d) });
    selectedContact = r.contact_id;
    e.target.reset();
    await loadContacts();
    await openConversation(r.contact_id);
    showNotice("Mensagem respondida com sucesso.");
  } catch (err) {
    showNotice(err.message, true);
  }
});

$("#conversion-form").addEventListener("submit", async e => {
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

      connectedView.classList.remove("hidden");
    } else {
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

// Teste de envio de e-mail
$("#email-test-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const btn = $("#btn-email-test-submit");
  const resultEl = $("#email-test-result");
  const to = form.elements.test_to.value.trim();
  const subject = form.elements.test_subject.value.trim();
  const message = form.elements.test_message.value.trim();

  if (btn) {
    btn.disabled = true;
    btn.textContent = "A enviar e-mail...";
  }
  if (resultEl) {
    resultEl.classList.add("hidden");
    resultEl.className = "wa-test-result";
  }

  try {
    const res = await api("/api/email/test-send", {
      method: "POST",
      body: JSON.stringify({ to, subject, message })
    });
    if (resultEl) {
      resultEl.classList.remove("hidden");
      resultEl.classList.add("success");
      resultEl.textContent = `✅ ${res.message || "E-mail enviado com sucesso!"}`;
    }
  } catch (err) {
    if (resultEl) {
      resultEl.classList.remove("hidden");
      resultEl.classList.add("error");
      resultEl.textContent = `❌ Falha no envio do e-mail: ${err.message}`;
    }
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Enviar Teste";
    }
  }
});


/* ════════════════════════════════════════════════════════════
   INTEGRAÇÃO WHATSAPP OFICIAL COM META EMBEDDED SIGNUP
   ════════════════════════════════════════════════════════════ */
let metaConfig = null;
let fbSdkLoaded = false;
let lastEmbeddedSignupData = null;

// Escuta eventos postMessage emitidos pela Meta durante o fluxo Embedded Signup
window.addEventListener("message", (event) => {
  if (typeof event.origin !== "string") return;
  if (!event.origin.endsWith("facebook.com") && !event.origin.endsWith("meta.com")) return;

  try {
    const raw = typeof event.data === "string" ? JSON.parse(event.data) : event.data;
    if (raw && raw.type === "WA_EMBEDDED_SIGNUP") {
      console.log("[Drexier] Evento Embedded Signup recebido da Meta:", raw);
      if (raw.event === "FINISH" && raw.data) {
        lastEmbeddedSignupData = {
          phone_number_id: raw.data.phone_number_id || "",
          waba_id: raw.data.waba_id || ""
        };
      }
    }
  } catch (err) {
    // Ignora eventos não formatados em JSON
  }
});

// Inicialização dinâmica do SDK do Facebook
async function initMetaSdk() {
  if (fbSdkLoaded && window.FB) return;
  try {
    metaConfig = await api("/api/whatsapp/config");
    if (!metaConfig || !metaConfig.app_id) {
      return;
    }

    if (!window.FB) {
      window.fbAsyncInit = function() {
        window.FB.init({
          appId: metaConfig.app_id,
          autoLogAppEvents: true,
          xfbml: true,
          version: metaConfig.version || "v21.0"
        });
        fbSdkLoaded = true;
      };

      if (!document.getElementById("facebook-jssdk")) {
        const js = document.createElement("script");
        js.id = "facebook-jssdk";
        js.src = "https://connect.facebook.net/pt_PT/sdk.js";
        js.async = true;
        js.defer = true;
        document.body.appendChild(js);
      }
    } else {
      window.FB.init({
        appId: metaConfig.app_id,
        autoLogAppEvents: true,
        xfbml: true,
        version: metaConfig.version || "v21.0"
      });
      fbSdkLoaded = true;
    }
  } catch (err) {
    console.warn("[Drexier] Falha ao carregar SDK da Meta:", err);
  }
}

// Carregar o estado da integração WhatsApp
async function loadWhatsAppStatus() {
  const loading = $("#wa-loading-state");
  const envWarning = $("#wa-env-warning");
  const disconnectedView = $("#wa-disconnected-view");
  const connectedView = $("#wa-connected-view");
  const badge = $("#wa-status-badge");

  if (!loading || !disconnectedView || !connectedView) return;

  loading.classList.remove("hidden");
  envWarning.classList.add("hidden");
  disconnectedView.classList.add("hidden");
  connectedView.classList.add("hidden");

  try {
    await initMetaSdk();

    if (!metaConfig || !metaConfig.configured) {
      envWarning.classList.remove("hidden");
    }

    const data = await api("/api/whatsapp/status");
    loading.classList.add("hidden");

    if (data.connected && data.integration) {
      const it = data.integration;
      badge.textContent = "Conectado";
      badge.className = "badge badge-connected";

      $("#wa-display-name").textContent = it.business_name || "WhatsApp Oficial";
      $("#wa-display-phone").textContent = it.phone_number || it.phone_number_id;
      $("#wa-display-phone-id").textContent = it.phone_number_id;
      $("#wa-display-waba-id").textContent = it.waba_id;
      $("#wa-display-webhook").textContent = it.webhook_subscribed ? "Subscrito & Ativo" : "Pendente";
      $("#wa-display-date").textContent = it.created_at ? new Date(it.created_at).toLocaleDateString("pt-PT") : "-";

      connectedView.classList.remove("hidden");
    } else {
      badge.textContent = "Desconectado";
      badge.className = "badge badge-disconnected";
      disconnectedView.classList.remove("hidden");
    }
  } catch (err) {
    loading.classList.add("hidden");
    disconnectedView.classList.remove("hidden");
    showNotice("Não foi possível carregar o estado do WhatsApp: " + err.message, true);
  }
}

// Iniciar fluxo oficial do Embedded Signup da Meta
function startMetaEmbeddedSignup() {
  const statusEl = $("#wa-connect-status");
  const btn = $("#btn-wa-connect");

  if (!metaConfig || !metaConfig.app_id) {
    showNotice("Preencha o META_APP_ID no seu ficheiro .env antes de iniciar.", true);
    $("#wa-manual-box").classList.remove("hidden");
    return;
  }

  if (!window.FB) {
    showNotice("O SDK da Meta não pôde ser carregado. Pode utilizar a ligação direta por chaves abaixo.", true);
    $("#wa-manual-box").classList.remove("hidden");
    return;
  }

  statusEl.textContent = "A abrir janela oficial da Meta...";
  btn.disabled = true;

  const loginParams = {
    scope: "whatsapp_business_management,whatsapp_business_messaging",
    response_type: "code",
    override_default_response_type: true,
    extras: {
      feature: "whatsapp_embedded_signup",
      version: 2,
      sessionInfoVersion: "3"
    }
  };

  if (metaConfig.config_id) {
    loginParams.config_id = metaConfig.config_id;
  }

  window.FB.login(async (response) => {
    btn.disabled = false;
    if (response.authResponse && response.authResponse.code) {
      statusEl.textContent = "Autenticado na Meta! A concluir ligação e a subscrever webhook...";
      try {
        const payload = {
          code: response.authResponse.code,
          phone_number_id: lastEmbeddedSignupData ? lastEmbeddedSignupData.phone_number_id : undefined,
          waba_id: lastEmbeddedSignupData ? lastEmbeddedSignupData.waba_id : undefined
        };
        const result = await api("/api/whatsapp/connect", {
          method: "POST",
          body: JSON.stringify(payload)
        });
        statusEl.textContent = "";
        showNotice(result.message || "WhatsApp oficial ligado com sucesso!");
        await loadWhatsAppStatus();
      } catch (err) {
        statusEl.textContent = "";
        showNotice("Erro ao concluir ligação na Meta: " + err.message, true);
      }
    } else {
      statusEl.textContent = "";
      if (response.status === "not_authorized" || response.error) {
        showNotice("Ligação cancelada ou não autorizada na Meta.", true);
      }
    }
  }, loginParams);
}

// Conexão manual / direta por credenciais
$("#btn-toggle-manual-wa")?.addEventListener("click", () => {
  $("#wa-manual-box").classList.toggle("hidden");
});
$("#btn-cancel-manual-wa")?.addEventListener("click", () => {
  $("#wa-manual-box").classList.add("hidden");
});

$("#wa-manual-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const d = Object.fromEntries(new FormData(e.target));
  try {
    const res = await api("/api/whatsapp/connect", {
      method: "POST",
      body: JSON.stringify(d)
    });
    showNotice(res.message || "WhatsApp ligado com sucesso!");
    $("#wa-manual-box").classList.add("hidden");
    e.target.reset();
    await loadWhatsAppStatus();
  } catch (err) {
    showNotice(err.message, true);
  }
});

// Desconectar WhatsApp
$("#btn-wa-disconnect")?.addEventListener("click", async () => {
  if (!confirm("Tem a certeza de que deseja desconectar o WhatsApp oficial desta conta? A IA deixará de responder às mensagens até voltar a conectar.")) {
    return;
  }
  try {
    await api("/api/whatsapp/disconnect", { method: "POST" });
    showNotice("WhatsApp desconectado com sucesso.");
    await loadWhatsAppStatus();
  } catch (err) {
    showNotice(err.message, true);
  }
});

// Teste de envio oficial via Meta Cloud API
$("#wa-test-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const btn = $("#btn-wa-test-submit");
  const resultEl = $("#wa-test-result");
  const to = form.elements.test_to.value.trim();
  const message = form.elements.test_message.value.trim();

  btn.disabled = true;
  btn.textContent = "A enviar...";
  resultEl.classList.add("hidden");
  resultEl.className = "wa-test-result";

  try {
    const res = await api("/api/whatsapp/test-send", {
      method: "POST",
      body: JSON.stringify({ to, message })
    });
    resultEl.classList.remove("hidden");
    resultEl.classList.add("success");
    const metaMsgId = res.meta_response?.messages?.[0]?.id || "ok";
    resultEl.textContent = "✅ Mensagem enviada com sucesso pela Meta Cloud API! ID da Meta: " + metaMsgId;
  } catch (err) {
    resultEl.classList.remove("hidden");
    resultEl.classList.add("error");
    resultEl.textContent = "❌ Falha no envio: " + err.message;
  } finally {
    btn.disabled = false;
    btn.textContent = "Enviar Teste";
  }
});

$("#btn-wa-connect")?.addEventListener("click", startMetaEmbeddedSignup);

if (token) boot();
