# patch_app.py: Enhances frontend/app.js with all Enterprise interactions
import re

with open("frontend/app.js", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Update loadStockTab to compute the 4 KPIs and show variant pills, status badges, and edit/delete actions
# Let's inspect where loadStockTab is in code
old_load_stock_regex = r"function loadStockTab\(\) \{[\s\S]*?\}\s*#\[btn-refresh-stock\]"

new_load_stock = '''function loadStockTab() {
  try {
    const productosCard = infoCache.find(x => x.kind === "productos");
    const items = Array.isArray(productosCard?.metadata?.items) ? productosCard.metadata.items : [];
    const tbody = $("#stock-table-body");
    const badge = $("#badge-stock-stat");
    if (badge) badge.textContent = `${items.length} ${items.length === 1 ? 'produto' : 'produtos'}`;

    // Carregar stock existente do cache local
    const saved = localStorage.getItem("drexier_stock_map");
    if (saved) {
      try { stockDataCache = JSON.parse(saved); } catch { stockDataCache = {}; }
    }

    let totalProducts = items.length;
    let availableCount = 0;
    let lowCount = 0;
    let outCount = 0;

    items.forEach((it, idx) => {
      const key = it.id || it.name || `item_${idx}`;
      if (stockDataCache[key] === undefined) {
        stockDataCache[key] = { inStock: true, qty: 10, variants: it.variants || "" };
      }
      const st = stockDataCache[key];
      const qty = parseInt(st.qty, 10) || 0;
      const isInStock = st.inStock !== false && qty > 0;
      if (!isInStock || qty === 0) {
        outCount++;
      } else if (qty <= 5) {
        lowCount++;
        availableCount++;
      } else {
        availableCount++;
      }
    });

    // Atualizar os 4 KPI cards de stock
    const kpiTotal = $("#stock-kpi-total");
    const kpiAvail = $("#stock-kpi-available");
    const kpiLow = $("#stock-kpi-low");
    const kpiOut = $("#stock-kpi-out");
    if (kpiTotal) kpiTotal.textContent = totalProducts;
    if (kpiAvail) kpiAvail.textContent = availableCount;
    if (kpiLow) kpiLow.textContent = lowCount;
    if (kpiOut) kpiOut.textContent = outCount;

    if (!tbody) return;
    tbody.innerHTML = "";

    if (!items.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 7;
      td.style.padding = "24px 14px";
      td.style.textAlign = "center";
      td.style.color = "var(--text-tertiary)";
      td.innerHTML = 'Nenhum produto registado no inventário.<br><button type="button" class="btn primary small" id="btn-empty-add-stock" style="margin-top:10px;">+ Adicionar Primeiro Produto</button>';
      tr.appendChild(td);
      tbody.appendChild(tr);
      td.querySelector("#btn-empty-add-stock")?.addEventListener("click", () => openStockProductModal());
      return;
    }

    items.forEach((it, idx) => {
      const key = it.id || it.name || `item_${idx}`;
      const st = stockDataCache[key] || { inStock: true, qty: 10 };
      const qty = parseInt(st.qty, 10) || 0;
      const isInStock = st.inStock !== false && qty > 0;

      const tr = document.createElement("tr");

      // Coluna 1: Produto (Nome + Detalhes)
      const tdName = document.createElement("td");
      tdName.innerHTML = `<div style="font-weight:600; color:var(--text-primary);">${escapeHtml(it.name || "Produto sem nome")}</div>${it.details ? `<div style="font-size:12px; color:var(--text-tertiary); margin-top:2px;">${escapeHtml(it.details)}</div>` : ''}`;

      // Coluna 2: Preço
      const tdPrice = document.createElement("td");
      tdPrice.style.fontWeight = "600";
      tdPrice.textContent = it.price || "Sob consulta";

      // Coluna 3: Variantes (pills)
      const tdVariants = document.createElement("td");
      const variantsText = it.variants || st.variants || "";
      if (variantsText) {
        const vList = variantsText.split(",").map(v => v.trim()).filter(Boolean);
        const pillsHtml = vList.map(v => `<span class="badge" style="background:var(--surface-elevated); color:var(--text-secondary); margin:2px 4px 2px 0; font-size:11.5px; border:1px solid var(--border-subtle);">${escapeHtml(v)}</span>`).join("");
        tdVariants.innerHTML = pillsHtml || '<span class="muted">-</span>';
      } else {
        tdVariants.innerHTML = '<span class="muted" style="font-size:12px;">Padrão</span>';
      }

      // Coluna 4: Estado
      const tdStatus = document.createElement("td");
      if (!isInStock || qty === 0) {
        tdStatus.innerHTML = '<span class="badge" style="background:var(--color-error-bg); color:var(--color-error); font-weight:600;">Esgotado</span>';
      } else if (qty <= 5) {
        tdStatus.innerHTML = '<span class="badge" style="background:var(--color-warning-bg); color:var(--color-warning); font-weight:600;">Stock Baixo</span>';
      } else {
        tdStatus.innerHTML = '<span class="badge" style="background:var(--color-success-bg); color:var(--color-success); font-weight:600;">Disponível</span>';
      }

      // Coluna 5: Em Stock (Sim / Não)
      const tdInStock = document.createElement("td");
      const select = document.createElement("select");
      select.style.padding = "6px 8px";
      select.style.fontSize = "13px";
      const optYes = document.createElement("option");
      optYes.value = "yes";
      optYes.textContent = "Sim";
      const optNo = document.createElement("option");
      optNo.value = "no";
      optNo.textContent = "Não";
      select.value = isInStock ? "yes" : "no";
      select.onchange = () => {
        stockDataCache[key].inStock = select.value === "yes";
        try { localStorage.setItem("drexier_stock_map", JSON.stringify(stockDataCache)); } catch(_) {}
        loadStockTab();
      };
      select.append(optYes, optNo);
      tdInStock.appendChild(select);

      // Coluna 6: Quantidade
      const tdQty = document.createElement("td");
      const inputQty = document.createElement("input");
      inputQty.type = "number";
      inputQty.min = "0";
      inputQty.step = "1";
      inputQty.value = qty;
      inputQty.style.padding = "6px 8px";
      inputQty.style.width = "90px";
      inputQty.style.fontSize = "13px";
      inputQty.onchange = () => {
        const val = parseInt(inputQty.value || "0", 10) || 0;
        stockDataCache[key].qty = val;
        stockDataCache[key].inStock = val > 0;
        try { localStorage.setItem("drexier_stock_map", JSON.stringify(stockDataCache)); } catch(_) {}
        loadStockTab();
      };
      tdQty.appendChild(inputQty);

      // Coluna 7: Ações (Editar / Eliminar)
      const tdActions = document.createElement("td");
      const btnEdit = document.createElement("button");
      btnEdit.className = "btn xs outline";
      btnEdit.textContent = "Editar";
      btnEdit.title = "Editar informações e variantes";
      btnEdit.style.marginRight = "6px";
      btnEdit.onclick = () => openStockProductModal(idx);

      const btnDel = document.createElement("button");
      btnDel.className = "btn xs danger";
      btnDel.innerHTML = "&times;";
      btnDel.title = "Eliminar produto do stock";
      btnDel.onclick = async () => {
        if (!confirm(`Tem a certeza de que deseja eliminar "${it.name}" do stock?`)) return;
        items.splice(idx, 1);
        productosCard.metadata = productosCard.metadata || {};
        productosCard.metadata.items = items;
        productosCard.content = compileItemsToContent(items, productosCard.metadata.generalNote || "");
        delete stockDataCache[key];
        try { localStorage.setItem("drexier_stock_map", JSON.stringify(stockDataCache)); } catch(_) {}
        try {
          await api(`/api/business-info/${productosCard.id}`, {
            method: "PUT",
            body: JSON.stringify({
              kind: productosCard.kind,
              title: productosCard.title,
              content: productosCard.content,
              metadata: productosCard.metadata
            })
          });
          showNotice("Produto removido do inventário.");
          loadStockTab();
          renderCardsFromCache();
        } catch (err) {
          showNotice(err.message, true);
        }
      };

      tdActions.append(btnEdit, btnDel);
      tr.append(tdName, tdPrice, tdVariants, tdStatus, tdInStock, tdQty, tdActions);
      tbody.appendChild(tr);
    });
  } catch (e) {
    showNotice("Erro ao carregar stock: " + e.message, true);
  }
}

function openStockProductModal(editIndex = null) {
  if (!paywallCheck()) return;
  const modal = $("#stock-product-modal");
  if (!modal) return;
  const productosCard = infoCache.find(x => x.kind === "productos");
  const items = Array.isArray(productosCard?.metadata?.items) ? productosCard.metadata.items : [];

  const titleEl = $("#stock-modal-title");
  const idxInput = $("#stock-item-index");
  const nameInput = $("#stock-item-name");
  const priceInput = $("#stock-item-price");
  const qtyInput = $("#stock-item-qty");
  const variantsInput = $("#stock-item-variants");
  const detailsInput = $("#stock-item-details");

  if (editIndex !== null && items[editIndex]) {
    const it = items[editIndex];
    const key = it.id || it.name || `item_${editIndex}`;
    const st = stockDataCache[key] || { qty: 10 };
    if (titleEl) titleEl.textContent = "Editar Produto no Stock";
    if (idxInput) idxInput.value = String(editIndex);
    if (nameInput) nameInput.value = it.name || "";
    if (priceInput) priceInput.value = it.price || "";
    if (qtyInput) qtyInput.value = st.qty ?? 10;
    if (variantsInput) variantsInput.value = it.variants || st.variants || "";
    if (detailsInput) detailsInput.value = it.details || "";
  } else {
    if (titleEl) titleEl.textContent = "Adicionar Produto ao Stock";
    if (idxInput) idxInput.value = "";
    if (nameInput) nameInput.value = "";
    if (priceInput) priceInput.value = "";
    if (qtyInput) qtyInput.value = "10";
    if (variantsInput) variantsInput.value = "";
    if (detailsInput) detailsInput.value = "";
  }

  modal.classList.remove("hidden");
  nameInput?.focus();
}

function closeStockProductModal() {
  const modal = $("#stock-product-modal");
  if (modal) modal.classList.add("hidden");
}

$("#close-stock-modal")?.addEventListener("click", closeStockProductModal);
$("#btn-cancel-stock-modal")?.addEventListener("click", closeStockProductModal);
$("#stock-product-modal")?.addEventListener("click", (e) => {
  if (e.target === $("#stock-product-modal")) closeStockProductModal();
});
$("#btn-add-stock-product")?.addEventListener("click", () => openStockProductModal());

$("#stock-product-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!paywallCheck()) return;

  const idxVal = $("#stock-item-index")?.value;
  const name = $("#stock-item-name")?.value.trim() || "";
  const price = $("#stock-item-price")?.value.trim() || "";
  const qty = parseInt($("#stock-item-qty")?.value || "0", 10) || 0;
  const variants = $("#stock-item-variants")?.value.trim() || "";
  const details = $("#stock-item-details")?.value.trim() || "";

  if (!name) {
    showNotice("Preencha o nome do produto.", true);
    return;
  }

  let productosCard = infoCache.find(x => x.kind === "productos");
  if (!productosCard) {
    try {
      productosCard = await api("/api/business-info", {
        method: "POST",
        body: JSON.stringify({
          kind: "productos",
          title: "Produtos e Preços",
          content: "Lista de Produtos e Preços",
          metadata: { items: [], generalNote: "" }
        })
      });
      infoCache.push(productosCard);
    } catch (err) {
      showNotice(err.message, true);
      return;
    }
  }

  const meta = productosCard.metadata || {};
  const items = Array.isArray(meta.items) ? [...meta.items] : [];

  const isEdit = idxVal !== "" && idxVal !== null && idxVal !== undefined;
  const targetIdx = isEdit ? parseInt(idxVal, 10) : null;

  const itemObj = {
    id: (isEdit && items[targetIdx]?.id) ? items[targetIdx].id : Date.now().toString(),
    name,
    price,
    variants,
    details
  };

  if (isEdit && items[targetIdx]) {
    items[targetIdx] = itemObj;
  } else {
    items.push(itemObj);
  }

  meta.items = items;
  productosCard.metadata = meta;
  productosCard.content = compileItemsToContent(items, meta.generalNote || "");

  // Atualizar cache de stock
  const key = itemObj.id || itemObj.name;
  stockDataCache[key] = {
    inStock: qty > 0,
    qty: qty,
    variants: variants
  };
  try { localStorage.setItem("drexier_stock_map", JSON.stringify(stockDataCache)); } catch(_) {}

  closeStockProductModal();
  loadStockTab();
  renderCardsFromCache();

  try {
    await api(`/api/business-info/${productosCard.id}`, {
      method: "PUT",
      body: JSON.stringify({
        kind: productosCard.kind,
        title: productosCard.title,
        content: productosCard.content,
        metadata: productosCard.metadata
      })
    });
    showNotice(isEdit ? "Produto atualizado no stock com sucesso." : "Novo produto adicionado ao stock com sucesso!");
  } catch (err) {
    showNotice(err.message, true);
  }
});
'''

# Replace loadStockTab implementation
code = re.sub(r'function loadStockTab\(\) \{[\s\S]*?\}\s*(?=\$\("#btn-refresh-stock"\))', new_load_stock + '\n\n', code)

# Write updated code
with open("frontend/app.js", "w", encoding="utf-8") as f:
    f.write(code)

print("Updated loadStockTab and added stock product modal!")
