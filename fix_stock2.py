import re
p=r'backend/services/agent.py'
s=open(p,encoding='utf-8').read()
old='REGRAS CRITICAS DE CONFIABILIDADE (GROUNDING):'
new=old+chr(13)+chr(10)+'- REGRAS CRITICAS DE DISPONIBILIDADE (STOCK): So podes informar se o produto tem OU NAO tem disponibilidade. NUNCA reveles quantidades, stock numerico, quantidades restantes ou qualquer dado sensivel do stock. Usa apenas respostas binarias do tipo  Temos em stock ou Nao temos em stock.'
# try with accents
if old not in s:
    old2='REGRAS CR\u00cdTICAS DE CONFIABILIDADE (GROUNDING):'
else:
    old2=old
if old2 in s and 'DISPONIBILIDADE' not in s:
    new2=old2+chr(13)+chr(10)+'- REGRAS CR\u00cdTICAS DE DISPONIBILIDADE (STOCK): S\u00f3 podes informar se o produto tem OU N\u00c3O tem disponibilidade. NUNCA reveles quantidades, stock num\u00e9rico, quantidades restantes ou qualquer dado sens\u00edvel do stock. Usa apenas respostas bin\u00e1rias do tipo \'Temos em stock\' ou \'N\u00e3o temos em stock\'.'
    open(p,'w',encoding='utf-8').write(s.replace(old2,new2))
    print('ok')
else:
    print('skip')
