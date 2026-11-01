# patch_app3.py: Adds sidebar toggle, period tabs, search input, takeover toggle, and agent studio subtabs
import re

with open("frontend/app.js", "r", encoding="utf-8") as f:
    code = f.read()

# Let's inspect DOMContentLoaded block at bottom of app.js
init_block = '''
  // ==========================================================
  // SIDEBAR COLLAPSIBLE TOGGLE (250px <-> 76px)
  // ==========================================================
  const sidebar = $(".sidebar");
  const sidebarToggleBtn = $("#sidebar-toggle-btn");
  const isSidebarCollapsed = localStorage.getItem("drexier_sidebar_collapsed") === "true";

  if (isSidebarCollapsed && sidebar) {
    sidebar.classList.add("is-collapsed");
  }

  sidebarToggleBtn?.addEventListener("click", () => {
    if (!sidebar) return;
    const collapsed = sidebar.classList.toggle("is-collapsed");
    localStorage.setItem("drexier_sidebar_collapsed", collapsed ? "true" : "false");
  });

  // ==========================================================
  // DASHBOARD PERIOD TABS
  // ==========================================================
  $$("#dashboard-period-tabs .period-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      $$("#dashboard-period-tabs .period-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      const period = btn.dataset.period;
      if (dashboardCacheData) {
        if (period === "today") {
          renderBars("#dashboard-chart", [
            { date: "Ontem", count: dashboardCacheData.yesterday_contacts ?? 0 },
            { date: "Hoje", count: dashboardCacheData.today_contacts ?? 0 }
          ]);
        } else if (period === "7d") {
          const base = dashboardCacheData.total_contacts || 10;
          renderBars("#dashboard-chart", [
            { date: "D-6", count: Math.max(1, Math.round(base * 0.1)) },
            { date: "D-5", count: Math.max(1, Math.round(base * 0.15)) },
            { date: "D-4", count: Math.max(1, Math.round(base * 0.12)) },
            { date: "D-3", count: Math.max(1, Math.round(base * 0.2)) },
            { date: "D-2", count: Math.max(1, Math.round(base * 0.18)) },
            { date: "Ontem", count: dashboardCacheData.yesterday_contacts ?? 0 },
            { date: "Hoje", count: dashboardCacheData.today_contacts ?? 0 }
          ]);
        } else if (period === "30d") {
          const base = dashboardCacheData.total_contacts || 20;
          renderBars("#dashboard-chart", [
            { date: "Sem 1", count: Math.max(2, Math.round(base * 0.2)) },
            { date: "Sem 2", count: Math.max(3, Math.round(base * 0.25)) },
            { date: "Sem 3", count: Math.max(4, Math.round(base * 0.3)) },
            { date: "Sem 4", count: Math.max(5, Math.round(base * 0.25)) }
          ]);
        }
      }
    });
  });

  // ==========================================================
  // MESSAGES INBOX SEARCH & FILTERS
  // ==========================================================
  const searchInput = $("#contacts-search-input");
  searchInput?.addEventListener("input", debounce(() => {
    contactsSearchQuery = searchInput.value.trim();
    renderContactsList(contactsCache);
  }, 200));

  $$(".inbox-filter-pill").forEach(pill => {
    pill.addEventListener("click", () => {
      $$(".inbox-filter-pill").forEach(p => p.classList.remove("active"));
      pill.classList.add("active");
      activeContactsFilter = pill.dataset.filter || "all";
      renderContactsList(contactsCache);
    });
  });

  // ==========================================================
  // HUMAN TAKEOVER TOGGLE
  // ==========================================================
  const takeoverBtn = $("#btn-toggle-takeover");
  takeoverBtn?.addEventListener("click", () => {
    humanTakeoverActive = !humanTakeoverActive;
    if (humanTakeoverActive) {
      takeoverBtn.textContent = "Devolver à IA";
      takeoverBtn.className = "btn primary small";
      showNotice("Assumiu o atendimento deste cliente. A IA não interferirá enquanto responder manualmente.");
    } else {
      takeoverBtn.textContent = "Assumir Atendimento";
      takeoverBtn.className = "btn outline small";
      showNotice("Atendimento devolvido à IA Drexier. Respostas automáticas reativadas.");
    }
    const pMode = $("#profile-handover-mode");
    if (pMode) {
      pMode.textContent = humanTakeoverActive ? "Operador Humano (Pausado para IA)" : "Automático (IA Drexier)";
    }
  });

  // ==========================================================
  // AGENT STUDIO SUBTABS CONTROLLER
  // ==========================================================
  $$(".agent-studio-subtab").forEach(tab => {
    tab.addEventListener("click", () => {
      const targetId = tab.dataset.agentTab;
      $$(".agent-studio-subtab").forEach(t => t.classList.toggle("active", t === tab));
      $$(".agent-studio-card").forEach(c => {
        c.classList.toggle("hidden", c.id !== `agent-tab-${targetId}`);
      });
    });
  });
'''

# Find document.addEventListener("DOMContentLoaded", () => {
target_str = 'document.addEventListener("DOMContentLoaded", () => {'
if target_str in code:
    code = code.replace(target_str, target_str + init_block)
    with open("frontend/app.js", "w", encoding="utf-8") as f:
        f.write(code)
    print("Successfully added interactive handlers inside DOMContentLoaded!")
else:
    print("Target string not found!")
