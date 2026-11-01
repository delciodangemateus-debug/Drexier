import re

with open("frontend/index.html", "r", encoding="utf-8") as f:
    text = f.read()

ids = set(re.findall(r'id="([^"]+)"', text))
reqs = [
    'sidebar-toggle-btn', 'metric-messages', 'metric-contacts', 'metric-today', 
    'metric-pending', 'metric-ai-conversations', 'metric-bookings', 'metric-conversion-rate',
    'dashboard-activity-feed', 'dashboard-insights', 'contacts-search-input',
    'profile-client-name', 'profile-client-key', 'profile-client-status', 'profile-client-interest',
    'btn-toggle-takeover', 'stock-kpi-total', 'stock-kpi-available', 'stock-kpi-low', 'stock-kpi-out',
    'stock-product-modal', 'btn-add-stock-product', 'stock-product-form',
    'setting-agent-studio', 'agent-tab-overview', 'agent-tab-personality', 'agent-tab-instructions',
    'agent-tab-mandatory', 'agent-tab-rules', 'agent-tab-goals'
]

missing = [r for r in reqs if r not in ids]
print("Missing IDs:", missing if missing else "None! All 30 required IDs found.")
