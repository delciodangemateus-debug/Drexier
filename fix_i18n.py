# fix_i18n.py: cleans up frontend/i18n.js syntax
with open("frontend/i18n.js", "r", encoding="utf-8") as f:
    text = f.read()

# Fix missing comma on line 568:
# "Erro ao carregar pedidos:": "Error loading requests:"
# "A intelig
text = text.replace('"Erro ao carregar pedidos:": "Error loading requests:"\n  "A intelig', '"Erro ao carregar pedidos:": "Error loading requests:",\n  "A intelig')
text = text.replace('"Erro ao carregar pedidos:": "Error loading requests:"\r\n  "A intelig', '"Erro ao carregar pedidos:": "Error loading requests:",\r\n  "A intelig')

# Also check translationsPt
# Let's check if there is a similar issue in translationsPt
text = text.replace('"Error loading requests:": "Erro ao carregar pedidos:"\n  "The intelligence', '"Error loading requests:": "Erro ao carregar pedidos:",\n  "The intelligence')
text = text.replace('"Error loading requests:": "Erro ao carregar pedidos:"\r\n  "The intelligence', '"Error loading requests:": "Erro ao carregar pedidos:",\r\n  "The intelligence')

with open("frontend/i18n.js", "w", encoding="utf-8") as f:
    f.write(text)

print("Fixed i18n commas!")
