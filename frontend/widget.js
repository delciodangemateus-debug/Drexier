/**
 * DREXIER AI — Website Chatbot Widget
 * Embeddable script for external websites (placed in <head> or <body>).
 */
(function() {
  'use strict';

  // Evita carregamento múltiplo
  if (window.__drexier_widget_loaded) return;
  window.__drexier_widget_loaded = true;

  // Localiza configurações
  const scriptTag = document.currentScript || (function() {
    const scripts = document.getElementsByTagName('script');
    for (let i = scripts.length - 1; i >= 0; i--) {
      if (scripts[i].src && scripts[i].src.indexOf('widget.js') !== -1) return scripts[i];
    }
    return null;
  })();

  const globalSettings = window.drexierSettings || {};
  const siteKey = globalSettings.siteKey || (scriptTag && scriptTag.getAttribute('data-site-key'));

  if (!siteKey) {
    console.warn('[Drexier AI] Chave do widget (siteKey) não especificada.');
    return;
  }

  // Detecta URL base da API
  let apiUrl = globalSettings.apiUrl || (scriptTag && scriptTag.getAttribute('data-api-url'));
  if (!apiUrl) {
    if (scriptTag && scriptTag.src) {
      try {
        const u = new URL(scriptTag.src);
        apiUrl = u.origin + '/api';
      } catch (e) {
        apiUrl = '/api';
      }
    } else {
      apiUrl = '/api';
    }
  }
  apiUrl = apiUrl.replace(/\/+$/, '');

  // Identificador exclusivo do visitante
  let visitorId = localStorage.getItem('drexier_vid_' + siteKey);
  if (!visitorId) {
    visitorId = 'v_' + Math.random().toString(36).substring(2, 11) + '_' + Date.now().toString(36);
    localStorage.setItem('drexier_vid_' + siteKey, visitorId);
  }

  // Estado local do widget (lê parâmetros embutidos no HEAD com fallback para os padrões neutros)
  let widgetConfig = {
    agent_name: globalSettings.agentName || globalSettings.agent_name || 'Agente Drexier',
    agent_role: globalSettings.agentRole || globalSettings.agent_role || 'Atendente Virtual',
    greeting_message: globalSettings.greetingMessage || globalSettings.greeting_message || 'Olá! Como posso ajudar hoje?',
    theme_color: globalSettings.themeColor || globalSettings.theme_color || '#18181b',
    position: globalSettings.position || 'bottom-right',
    border_radius: globalSettings.borderRadius || globalSettings.border_radius || '16px',
    button_shape: globalSettings.buttonShape || globalSettings.button_shape || 'circle',
    theme_mode: globalSettings.themeMode || globalSettings.theme_mode || 'light'
  };

  let isOpen = false;
  let isSending = false;
  let messageHistory = [];

  // Carrega histórico de mensagens da sessão
  try {
    const saved = sessionStorage.getItem('drexier_msgs_' + siteKey);
    if (saved) messageHistory = JSON.parse(saved);
  } catch (e) {}

  // Estilos CSS do widget
  const styles = `
    #drexier-widget-root {
      position: fixed;
      z-index: 999999;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      font-size: 14px;
      line-height: 1.5;
      color: #1e293b;
      box-sizing: border-box;
      -webkit-font-smoothing: antialiased;
    }
    #drexier-widget-root * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }
    .drexier-pos-bottom-right {
      bottom: 24px;
      right: 24px;
    }
    .drexier-pos-bottom-left {
      bottom: 24px;
      left: 24px;
    }
    /* Botão flutuante */
    #drexier-chat-trigger {
      width: 60px;
      height: 60px;
      border-radius: 50%;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.2), 0 8px 10px -6px rgba(0, 0, 0, 0.2);
      transition: transform 0.25s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.2s ease;
      position: relative;
      border: none;
      outline: none;
      color: #ffffff;
    }
    #drexier-chat-trigger:hover {
      transform: scale(1.06);
      box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.25), 0 10px 10px -5px rgba(0, 0, 0, 0.15);
    }
    #drexier-chat-trigger svg {
      width: 28px;
      height: 28px;
      fill: none;
      stroke: currentColor;
      stroke-width: 2.2;
      stroke-linecap: round;
      stroke-linejoin: round;
      transition: opacity 0.2s ease, transform 0.2s ease;
    }
    #drexier-trigger-open-icon {
      position: absolute;
    }
    #drexier-trigger-close-icon {
      position: absolute;
      opacity: 0;
      transform: rotate(-90deg) scale(0.8);
    }
    #drexier-chat-trigger.is-open #drexier-trigger-open-icon {
      opacity: 0;
      transform: rotate(90deg) scale(0.8);
    }
    #drexier-chat-trigger.is-open #drexier-trigger-close-icon {
      opacity: 1;
      transform: rotate(0) scale(1);
    }

    /* Janela de Chat */
    #drexier-chat-window {
      position: absolute;
      bottom: 76px;
      width: 380px;
      max-width: calc(100vw - 32px);
      height: 560px;
      max-height: calc(100vh - 110px);
      background: #ffffff;
      border-radius: 16px;
      box-shadow: 0 20px 40px -15px rgba(0, 0, 0, 0.2), 0 0 1px 1px rgba(0,0,0,0.06);
      display: flex;
      flex-direction: column;
      overflow: hidden;
      opacity: 0;
      pointer-events: none;
      transform: translateY(16px) scale(0.96);
      transition: opacity 0.25s cubic-bezier(0.16, 1, 0.3, 1), transform 0.25s cubic-bezier(0.16, 1, 0.3, 1);
    }
    .drexier-pos-bottom-right #drexier-chat-window {
      right: 0;
    }
    .drexier-pos-bottom-left #drexier-chat-window {
      left: 0;
    }
    #drexier-chat-window.is-open {
      opacity: 1;
      pointer-events: auto;
      transform: translateY(0) scale(1);
    }

    /* Cabeçalho */
    #drexier-chat-header {
      padding: 16px 20px;
      color: #ffffff;
      display: flex;
      align-items: center;
      justify-content: space-between;
      position: relative;
    }
    .drexier-header-agent-info {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .drexier-agent-avatar {
      width: 40px;
      height: 40px;
      border-radius: 50%;
      background: rgba(255, 255, 255, 0.2);
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 600;
      font-size: 16px;
      color: #ffffff;
      border: 2px solid rgba(255, 255, 255, 0.4);
      flex-shrink: 0;
    }
    .drexier-agent-names {
      display: flex;
      flex-direction: column;
    }
    .drexier-agent-name {
      font-weight: 600;
      font-size: 15px;
      line-height: 1.2;
    }
    .drexier-agent-status {
      font-size: 12px;
      opacity: 0.9;
      display: flex;
      align-items: center;
      gap: 5px;
      margin-top: 3px;
    }
    .drexier-online-dot {
      width: 7px;
      height: 7px;
      background: #10b981;
      border-radius: 50%;
      box-shadow: 0 0 6px #10b981;
    }
    .drexier-header-close-btn {
      background: rgba(255, 255, 255, 0.15);
      border: none;
      width: 28px;
      height: 28px;
      border-radius: 50%;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      color: #ffffff;
      transition: background 0.15s ease;
    }
    .drexier-header-close-btn:hover {
      background: rgba(255, 255, 255, 0.28);
    }

    /* Corpo das Mensagens */
    #drexier-chat-messages {
      flex: 1;
      padding: 18px 16px;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 12px;
      background: #f8fafc;
    }
    .drexier-msg {
      max-width: 82%;
      padding: 10px 14px;
      border-radius: 14px;
      font-size: 13.5px;
      line-height: 1.45;
      word-wrap: break-word;
      animation: drexierFadeIn 0.2s ease forwards;
    }
    @keyframes drexierFadeIn {
      from { opacity: 0; transform: translateY(6px); }
      to { opacity: 1; transform: translateY(0); }
    }
    .drexier-msg-agent {
      align-self: flex-start;
      background: #ffffff;
      color: #1e293b;
      border: 1px solid #e2e8f0;
      border-bottom-left-radius: 4px;
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
    }
    .drexier-msg-visitor {
      align-self: flex-end;
      color: #ffffff;
      border-bottom-right-radius: 4px;
      box-shadow: 0 2px 4px rgba(0, 0, 0, 0.08);
    }
    .drexier-msg-time {
      font-size: 10px;
      opacity: 0.6;
      margin-top: 4px;
      text-align: right;
    }

    /* Digitando */
    .drexier-typing-indicator {
      align-self: flex-start;
      background: #ffffff;
      border: 1px solid #e2e8f0;
      padding: 10px 14px;
      border-radius: 14px;
      border-bottom-left-radius: 4px;
      display: none;
      align-items: center;
      gap: 4px;
    }
    .drexier-typing-indicator.active {
      display: flex;
    }
    .drexier-typing-indicator span {
      width: 6px;
      height: 6px;
      background: #94a3b8;
      border-radius: 50%;
      animation: drexierBounce 1.4s infinite ease-in-out both;
    }
    .drexier-typing-indicator span:nth-child(1) { animation-delay: -0.32s; }
    .drexier-typing-indicator span:nth-child(2) { animation-delay: -0.16s; }
    @keyframes drexierBounce {
      0%, 80%, 100% { transform: scale(0); }
      40% { transform: scale(1); }
    }

    /* Rodapé & Input */
    #drexier-chat-footer {
      padding: 12px 14px 10px;
      background: #ffffff;
      border-top: 1px solid #e2e8f0;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .drexier-input-wrapper {
      display: flex;
      align-items: center;
      background: #f1f5f9;
      border-radius: 24px;
      padding: 4px 6px 4px 14px;
      border: 1px solid transparent;
      transition: border-color 0.2s ease, background 0.2s ease;
    }
    .drexier-input-wrapper:focus-within {
      background: #ffffff;
      border-color: #cbd5e1;
      box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.12);
    }
    #drexier-chat-input {
      flex: 1;
      border: none;
      background: transparent;
      outline: none;
      font-size: 13.5px;
      color: #0f172a;
      resize: none;
      max-height: 72px;
      font-family: inherit;
    }
    #drexier-chat-input::placeholder {
      color: #94a3b8;
    }
    #drexier-chat-send-btn {
      width: 32px;
      height: 32px;
      border-radius: 50%;
      border: none;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      color: #ffffff;
      transition: transform 0.15s ease, opacity 0.15s ease;
      flex-shrink: 0;
    }
    #drexier-chat-send-btn:hover {
      transform: scale(1.05);
    }
    #drexier-chat-send-btn:disabled {
      opacity: 0.5;
      cursor: not-allowed;
      transform: none;
    }
    .drexier-branding {
      text-align: center;
      font-size: 10px;
      color: #94a3b8;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 4px;
      text-decoration: none;
    }
    .drexier-branding strong {
      color: #64748b;
      font-weight: 600;
    }
  `;

  // Injeta estilos
  const styleEl = document.createElement('style');
  styleEl.textContent = styles;
  document.head.appendChild(styleEl);

  // Cria estrutura DOM
  const root = document.createElement('div');
  root.id = 'drexier-widget-root';
  root.className = 'drexier-pos-bottom-right';

  root.innerHTML = `
    <button id="drexier-chat-trigger" aria-label="Abrir chat">
      <svg id="drexier-trigger-open-icon" viewBox="0 0 24 24"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"></path></svg>
      <svg id="drexier-trigger-close-icon" viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
    </button>

    <div id="drexier-chat-window" role="dialog" aria-modal="true" aria-hidden="true">
      <div id="drexier-chat-header">
        <div class="drexier-header-agent-info">
          <div class="drexier-agent-avatar" id="drexier-agent-avatar">D</div>
          <div class="drexier-agent-names">
            <span class="drexier-agent-name" id="drexier-agent-name">Agente Drexier</span>
            <span class="drexier-agent-status">
              <span class="drexier-online-dot"></span>
              <span id="drexier-agent-role">Online • Atendimento</span>
            </span>
          </div>
        </div>
        <button class="drexier-header-close-btn" id="drexier-btn-close" aria-label="Fechar chat">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
        </button>
      </div>

      <div id="drexier-chat-messages">
        <div class="drexier-typing-indicator" id="drexier-typing">
          <span></span><span></span><span></span>
        </div>
      </div>

      <div id="drexier-chat-footer">
        <div class="drexier-input-wrapper">
          <input type="text" id="drexier-chat-input" placeholder="Escreva a sua mensagem..." autocomplete="off" />
          <button type="button" id="drexier-chat-send-btn" aria-label="Enviar mensagem">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
          </button>
        </div>
        <div class="drexier-branding">
          <span>⚡ Atendimento inteligente por</span>
          <strong>Drexier AI</strong>
        </div>
      </div>
    </div>
  `;

  document.body.appendChild(root);

  // Elementos
  const triggerBtn = document.getElementById('drexier-chat-trigger');
  const chatWindow = document.getElementById('drexier-chat-window');
  const closeBtn = document.getElementById('drexier-btn-close');
  const messagesContainer = document.getElementById('drexier-chat-messages');
  const inputEl = document.getElementById('drexier-chat-input');
  const sendBtn = document.getElementById('drexier-chat-send-btn');
  const typingEl = document.getElementById('drexier-typing');
  const agentNameEl = document.getElementById('drexier-agent-name');
  const agentRoleEl = document.getElementById('drexier-agent-role');
  const avatarEl = document.getElementById('drexier-agent-avatar');
  const headerEl = document.getElementById('drexier-chat-header');

  function applyConfig(cfg) {
    widgetConfig = Object.assign(widgetConfig, cfg);
    const color = widgetConfig.theme_color || '#18181b';

    // Aplica posição
    root.className = widgetConfig.position === 'bottom-left' ? 'drexier-pos-bottom-left' : 'drexier-pos-bottom-right';

    // Aplica cores dinâmicas
    triggerBtn.style.backgroundColor = color;
    headerEl.style.backgroundColor = color;
    sendBtn.style.backgroundColor = color;

    // Aplica estrutura ditada pelo utilizador
    if (widgetConfig.border_radius) {
      chatWindow.style.borderRadius = widgetConfig.border_radius;
    }
    if (widgetConfig.button_shape === 'square') {
      triggerBtn.style.borderRadius = '12px';
    } else if (widgetConfig.button_shape === 'pill') {
      triggerBtn.style.borderRadius = '28px';
    } else {
      triggerBtn.style.borderRadius = '50%';
    }
    if (widgetConfig.theme_mode === 'dark') {
      chatWindow.style.background = '#18181b';
      chatWindow.style.color = '#f4f4f5';
      messagesContainer.style.background = '#09090b';
    } else {
      chatWindow.style.background = '#ffffff';
      chatWindow.style.color = '#1e293b';
      messagesContainer.style.background = '#f8fafc';
    }

    // Atualiza cabeçalho
    agentNameEl.textContent = widgetConfig.agent_name || 'Agente Drexier';
    agentRoleEl.textContent = widgetConfig.agent_role || 'Online • Atendimento';

    const initial = (widgetConfig.agent_name || 'D').trim().charAt(0).toUpperCase();
    avatarEl.textContent = initial || 'D';

    // Se histórico estiver vazio, exibe saudação
    if (messageHistory.length === 0 && widgetConfig.greeting_message) {
      appendMessage('agent', widgetConfig.greeting_message);
    }
  }

  function appendMessage(sender, text) {
    const msg = { sender, text, time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) };
    messageHistory.push(msg);
    try {
      sessionStorage.setItem('drexier_msgs_' + siteKey, JSON.stringify(messageHistory));
    } catch (e) {}

    const el = document.createElement('div');
    el.className = 'drexier-msg ' + (sender === 'customer' || sender === 'visitor' ? 'drexier-msg-visitor' : 'drexier-msg-agent');
    if (sender === 'customer' || sender === 'visitor') {
      el.style.backgroundColor = widgetConfig.theme_color || '#18181b';
    }

    const contentDiv = document.createElement('div');
    contentDiv.textContent = text;
    el.appendChild(contentDiv);

    const timeDiv = document.createElement('div');
    timeDiv.className = 'drexier-msg-time';
    timeDiv.textContent = msg.time;
    el.appendChild(timeDiv);

    messagesContainer.insertBefore(el, typingEl);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  function renderHistory() {
    messageHistory.forEach(m => {
      const el = document.createElement('div');
      el.className = 'drexier-msg ' + (m.sender === 'customer' || m.sender === 'visitor' ? 'drexier-msg-visitor' : 'drexier-msg-agent');
      if (m.sender === 'customer' || m.sender === 'visitor') {
        el.style.backgroundColor = widgetConfig.theme_color || '#18181b';
      }
      const c = document.createElement('div');
      c.textContent = m.text;
      el.appendChild(c);
      const t = document.createElement('div');
      t.className = 'drexier-msg-time';
      t.textContent = m.time || '';
      el.appendChild(t);
      messagesContainer.insertBefore(el, typingEl);
    });
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  function toggleChat(open) {
    isOpen = typeof open === 'boolean' ? open : !isOpen;
    if (isOpen) {
      triggerBtn.classList.add('is-open');
      chatWindow.classList.add('is-open');
      chatWindow.setAttribute('aria-hidden', 'false');
      setTimeout(() => inputEl.focus(), 150);
      messagesContainer.scrollTop = messagesContainer.scrollHeight;
    } else {
      triggerBtn.classList.remove('is-open');
      chatWindow.classList.remove('is-open');
      chatWindow.setAttribute('aria-hidden', 'true');
    }
  }

  triggerBtn.addEventListener('click', () => toggleChat());
  closeBtn.addEventListener('click', () => toggleChat(false));

  async function sendMessage() {
    const text = inputEl.value.trim();
    if (!text || isSending) return;

    inputEl.value = '';
    appendMessage('visitor', text);

    isSending = true;
    sendBtn.disabled = true;
    typingEl.classList.add('active');
    messagesContainer.scrollTop = messagesContainer.scrollHeight;

    try {
      const res = await fetch(apiUrl + '/widget/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          site_key: siteKey,
          visitor_id: visitorId,
          message: text
        })
      });

      if (!res.ok) {
        throw new Error('Falha na resposta do servidor: ' + res.status);
      }

      const data = await res.json();
      typingEl.classList.remove('active');
      appendMessage('agent', data.reply || 'Recebemos o seu contacto.');
    } catch (err) {
      typingEl.classList.remove('active');
      appendMessage('agent', 'De momento, não foi possível enviar a resposta. Por favor tente novamente dentro de instantes.');
      console.warn('[Drexier Widget Chat]', err);
    } finally {
      isSending = false;
      sendBtn.disabled = false;
      inputEl.focus();
    }
  }

  sendBtn.addEventListener('click', sendMessage);
  inputEl.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  // Inicialização e Handshake Real com Drexier Backend
  async function initWidget() {
    try {
      const configRes = await fetch(apiUrl + '/widget/config?key=' + encodeURIComponent(siteKey));
      if (configRes.status === 403) {
        console.warn('[Drexier AI] Widget desativado: domínio não autorizado.');
        root.style.display = 'none';
        return;
      }
      if (!configRes.ok) {
        console.warn('[Drexier AI] Não foi possível carregar as configurações do widget.');
        return;
      }

      const cfg = await configRes.json();
      applyConfig(cfg);
      if (messageHistory.length > 0) {
        renderHistory();
      }

      // Emite ping de confirmação de presença (heartbeat)
      fetch(apiUrl + '/widget/ping', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          site_key: siteKey,
          origin: window.location.origin,
          url: window.location.href
        })
      }).catch(() => {});
    } catch (e) {
      console.warn('[Drexier AI] Erro na inicialização do widget:', e);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initWidget);
  } else {
    initWidget();
  }
})();
