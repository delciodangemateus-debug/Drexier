# -*- coding: utf-8 -*-
"""Comprehensive CSS builder for Drexier Violet Intelligence Design System."""

css_content = """/* ============================================================
   DREXIER — VIOLET INTELLIGENCE DESIGN SYSTEM
   Official Enterprise SaaS Palette & Tokens
   ============================================================ */

:root {
  /* FUNDOS */
  --bg-main: #111217;
  --bg-secondary: #15151D;
  --surface-primary: #1B1A23;
  --surface-elevated: #22202C;
  --surface-interaction: #2B2737;

  /* VIOLET */
  --violet-primary: #8065C9;
  --violet-dark: #6650A9;
  --violet-light: #A993E8;
  --lavender: #B9A8EC;
  --violet-subtle: #30283F;
  --violet-hover: #9278D8;

  /* TIPOGRAFIA */
  --text-primary: #F1EDF5;
  --text-secondary: #B2ACBB;
  --text-tertiary: #898394;
  --text-disabled: #625D6D;

  /* BORDAS */
  --border-primary: #393442;
  --border-subtle: #2D2936;
  --border-active: #8065C9;

  /* ESTADOS */
  --color-success: #79A98C;
  --color-success-bg: #1D3028;
  --color-warning: #D3AC72;
  --color-warning-bg: #352B20;
  --color-error: #CE777E;
  --color-error-bg: #382329;
  --color-info: #819BD2;

  /* COMPATIBILITY ALIASES */
  --surface: var(--bg-main);
  --surface-alt: var(--bg-secondary);
  --surface-card: var(--surface-primary);
  --surface-card-subtle: var(--surface-elevated);
  --black: #08080B;
  --white: #FFFFFF;
  --text-muted: var(--text-tertiary);
  --text-subtle: var(--text-disabled);
  --border: var(--border-primary);
  --border-hover: var(--violet-hover);
  --border-focus: var(--violet-primary);
  --accent: var(--violet-primary);
  --accent-hover: var(--violet-hover);
  --accent-gradient: linear-gradient(135deg, var(--violet-dark) 0%, var(--violet-primary) 100%);
  --danger: var(--color-error);
  --danger-bg: var(--color-error-bg);
  --danger-border: #5A2D35;
  --success: var(--color-success);
  --success-bg: var(--color-success-bg);
  --success-border: #2D4C3A;

  /* ELEVATION & SHADOWS */
  --shadow-xs: 0 1px 2px rgba(0, 0, 0, 0.4);
  --shadow-sm: 0 2px 6px rgba(0, 0, 0, 0.45), 0 1px 2px rgba(0, 0, 0, 0.3);
  --shadow-md: 0 6px 18px rgba(0, 0, 0, 0.55), 0 2px 6px rgba(128, 101, 201, 0.08);
  --shadow-lg: 0 14px 38px rgba(0, 0, 0, 0.65), 0 4px 14px rgba(128, 101, 201, 0.12);
  --shadow-xl: 0 24px 60px rgba(0, 0, 0, 0.75), 0 8px 24px rgba(128, 101, 201, 0.16);

  /* GEOMETRY & TYPOGRAPHY */
  --radius-xs: 4px;
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 16px;
  --radius-xl: 20px;
  --radius-full: 9999px;

  --font: 'Plus Jakarta Sans', 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  --font-display: 'Space Grotesk', var(--font);

  /* TIMING & EASING */
  --transition-fast: 140ms cubic-bezier(0.4, 0, 0.2, 1);
  --transition: 200ms cubic-bezier(0.4, 0, 0.2, 1);
  --transition-slow: 280ms cubic-bezier(0.4, 0, 0.2, 1);
}

/* Auth state instant hide */
html.is-authenticated #landing {
  display: none !important;
}
html.is-authenticated #auth {
  display: none !important;
}

/* ============================================================
   RESET & GLOBAL BASE
   ============================================================ */
*, *::before, *::after {
  box-sizing: border-box;
}

html {
  scroll-behavior: smooth;
  color-scheme: dark;
}

body {
  margin: 0;
  padding: 0;
  background-color: var(--bg-main);
  color: var(--text-primary);
  font: 14px/1.6 var(--font);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  background-image:
    radial-gradient(circle at 50% 0%, rgba(128, 101, 201, 0.07) 0%, transparent 60%),
    radial-gradient(circle at 85% 15%, rgba(169, 147, 232, 0.04) 0%, transparent 40%);
  background-attachment: fixed;
  overflow-x: hidden;
}

::selection {
  background-color: var(--violet-subtle);
  color: var(--text-primary);
}

::-webkit-scrollbar {
  width: 7px;
  height: 7px;
}
::-webkit-scrollbar-track {
  background: var(--bg-main);
}
::-webkit-scrollbar-thumb {
  background: var(--border-primary);
  border-radius: var(--radius-full);
}
::-webkit-scrollbar-thumb:hover {
  background: var(--violet-dark);
}

button, input, textarea, select {
  font: inherit;
  color: inherit;
}

button {
  cursor: pointer;
  background: none;
  border: none;
}

button:focus-visible, input:focus-visible, textarea:focus-visible, select:focus-visible {
  outline: 2px solid var(--violet-primary);
  outline-offset: 2px;
}

.hidden {
  display: none !important;
}

.muted {
  color: var(--text-secondary);
  font-size: 13px;
  margin: 0.2rem 0;
  line-height: 1.5;
}

hr {
  border: 0;
  border-top: 1px solid var(--border-primary);
  margin: 20px 0;
}

.wordmark {
  font-family: var(--font-display);
  font-size: 24px;
  font-weight: 800;
  letter-spacing: -0.8px;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 8px;
}

.svg-icon {
  display: inline-block;
  vertical-align: middle;
  flex-shrink: 0;
  stroke-linecap: round;
  stroke-linejoin: round;
}

/* ============================================================
   BUTTONS
   ============================================================ */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border-radius: var(--radius-sm);
  padding: 9px 16px;
  font-size: 13.5px;
  font-weight: 600;
  letter-spacing: -0.15px;
  transition: background-color var(--transition), border-color var(--transition), color var(--transition), box-shadow var(--transition), transform var(--transition-fast);
  white-space: nowrap;
  user-select: none;
  position: relative;
  text-decoration: none;
  min-height: 38px;
}

.btn:active {
  transform: translateY(1px);
}

.btn.primary {
  background: var(--violet-primary);
  color: #FFFFFF;
  border: 1px solid var(--violet-primary);
  box-shadow: 0 2px 8px rgba(128, 101, 201, 0.28);
}

.btn.primary:hover {
  background: var(--violet-hover);
  border-color: var(--violet-hover);
  box-shadow: 0 4px 14px rgba(128, 101, 201, 0.38);
}

.btn.outline, .btn.secondary {
  background: var(--surface-primary);
  color: var(--text-primary);
  border: 1px solid var(--border-primary);
}

.btn.outline:hover, .btn.secondary:hover {
  background: var(--surface-interaction);
  border-color: var(--border-subtle);
  color: var(--text-primary);
}

.btn.ghost {
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid transparent;
}

.btn.ghost:hover {
  background: var(--surface-interaction);
  color: var(--text-primary);
}

.btn.danger, .btn.danger.outline {
  background: var(--color-error-bg);
  color: var(--color-error);
  border: 1px solid var(--danger-border);
}

.btn.danger:hover {
  background: #472228;
  border-color: var(--color-error);
  color: #FFFFFF;
}

.btn.small {
  padding: 6px 12px;
  font-size: 12.5px;
  min-height: 32px;
}

.btn.xs {
  padding: 4px 8px;
  font-size: 11px;
  min-height: 24px;
  border-radius: var(--radius-xs);
}

.btn.btn-large {
  padding: 12px 24px;
  font-size: 14.5px;
  min-height: 44px;
  border-radius: var(--radius-sm);
}

.btn:disabled, .btn[disabled] {
  opacity: 0.45;
  cursor: not-allowed;
  pointer-events: none;
}

.btn-google {
  background: #FFFFFF;
  color: #1F1F1F;
  border: 1px solid #DADCE0;
  display: inline-flex;
  align-items: center;
  gap: 12px;
  font-weight: 600;
  border-radius: var(--radius-sm);
  transition: all var(--transition);
}

.btn-google:hover {
  background: #F8F9FA;
  box-shadow: 0 2px 6px rgba(0,0,0,0.15);
}

/* ============================================================
   FORMS & INPUTS
   ============================================================ */
.form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

input, textarea, select {
  background: var(--surface-primary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-sm);
  padding: 10px 14px;
  color: var(--text-primary);
  font-size: 13.5px;
  transition: border-color var(--transition), box-shadow var(--transition);
  outline: none;
}

input::placeholder, textarea::placeholder {
  color: var(--text-disabled);
}

input:hover, textarea:hover, select:hover {
  border-color: var(--border-subtle);
}

input:focus, textarea:focus, select:focus {
  border-color: var(--border-active);
  box-shadow: 0 0 0 3px rgba(128, 101, 201, 0.18);
  background: var(--surface-elevated);
}

input:disabled, textarea:disabled, select:disabled {
  background: var(--bg-secondary);
  border-color: var(--border-subtle);
  color: var(--text-disabled);
  cursor: not-allowed;
}

select {
  appearance: none;
  background-image: url("data:image/svg+xml;charset=UTF-8,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23898394' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3e%3cpolyline points='6 9 12 15 18 9'%3e%3c/polyline%3e%3c/svg%3e");
  background-repeat: no-repeat;
  background-position: right 12px center;
  background-size: 15px;
  padding-right: 36px;
}

textarea {
  resize: vertical;
  line-height: 1.5;
}

.notice {
  background: var(--surface-elevated);
  border: 1px solid var(--border-primary);
  border-left: 3px solid var(--violet-primary);
  padding: 12px 16px;
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: 13.5px;
  margin-bottom: 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  box-shadow: var(--shadow-sm);
}

.notice.error-notice {
  background: var(--color-error-bg);
  border-color: var(--danger-border);
  border-left-color: var(--color-error);
  color: #F8D7DA;
}

.error {
  color: var(--color-error);
  font-size: 12.5px;
  margin: 4px 0 0;
}

/* BADGES */
.badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: var(--radius-full);
  font-size: 11.5px;
  font-weight: 600;
  text-transform: capitalize;
}

.badge-connected {
  background: var(--color-success-bg);
  color: var(--color-success);
  border: 1px solid var(--success-border);
}

.badge-disconnected {
  background: var(--surface-interaction);
  color: var(--text-tertiary);
  border: 1px solid var(--border-primary);
}

/* LANGUAGE SELECTOR */
.language-selector {
  display: inline-flex;
  align-items: center;
  background: var(--surface-primary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-sm);
  padding: 3px;
  gap: 2px;
}

.lang-btn {
  padding: 4px 10px;
  font-size: 11.5px;
  font-weight: 700;
  letter-spacing: 0.3px;
  color: var(--text-tertiary);
  border-radius: 5px;
  transition: all var(--transition-fast);
}

.lang-btn:hover {
  color: var(--text-primary);
}

.lang-btn.active {
  background: var(--violet-primary);
  color: #FFFFFF;
}

/* ============================================================
   LANDING PAGE (VIOLET INTELLIGENCE EDITORIAL)
   ============================================================ */
.landing-shell {
  min-height: 100vh;
  background-color: var(--bg-main);
  color: var(--text-primary);
  position: relative;
}

.lp-container {
  max-width: 1220px;
  margin: 0 auto;
  padding: 0 24px;
}

.lp-header {
  position: sticky;
  top: 0;
  z-index: 100;
  background: rgba(17, 18, 23, 0.88);
  backdrop-filter: blur(14px);
  border-bottom: 1px solid var(--border-subtle);
  transition: all var(--transition);
}

.lp-header-inner {
  height: 72px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
}

.lp-brand-link {
  text-decoration: none;
  display: flex;
  align-items: center;
  gap: 10px;
}

.lp-wordmark {
  font-family: var(--font-display);
  font-size: 22px;
  font-weight: 800;
  color: var(--text-primary);
  letter-spacing: -0.6px;
}

.lp-brand-badge {
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.8px;
  background: var(--violet-subtle);
  color: var(--lavender);
  border: 1px solid rgba(128, 101, 201, 0.3);
  padding: 3px 8px;
  border-radius: var(--radius-full);
}

.lp-nav {
  display: flex;
  align-items: center;
  gap: 28px;
}

.lp-nav-link {
  text-decoration: none;
  color: var(--text-secondary);
  font-size: 13.5px;
  font-weight: 500;
  transition: color var(--transition);
}

.lp-nav-link:hover {
  color: var(--text-primary);
}

.lp-header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* HERO SECTION */
.lp-hero-section {
  padding: 84px 0 64px;
  position: relative;
}

.lp-hero-grid {
  display: grid;
  grid-template-columns: 1.05fr 1fr;
  gap: 52px;
  align-items: center;
}

.lp-pill-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: var(--surface-primary);
  border: 1px solid var(--border-primary);
  color: var(--lavender);
  padding: 6px 14px;
  border-radius: var(--radius-full);
  font-size: 12.5px;
  font-weight: 600;
  margin-bottom: 24px;
}

.lp-hero-title {
  font-size: 46px;
  line-height: 1.15;
  font-weight: 800;
  letter-spacing: -1.4px;
  margin: 0 0 20px;
  color: var(--text-primary);
}

.lp-title-highlight {
  color: var(--violet-light);
  background: linear-gradient(135deg, var(--lavender) 0%, var(--violet-light) 60%, var(--violet-primary) 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.lp-hero-subtitle {
  font-size: 16.5px;
  line-height: 1.6;
  color: var(--text-secondary);
  margin: 0 0 32px;
  max-width: 520px;
}

.lp-hero-actions {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 32px;
  flex-wrap: wrap;
}

.lp-hero-guarantees {
  display: flex;
  align-items: center;
  gap: 20px;
  flex-wrap: wrap;
}

.lp-hero-guarantee-item {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 12.5px;
  color: var(--text-tertiary);
}

.lp-hero-guarantee-item svg {
  color: var(--color-success);
}

/* HERO SHOWCASE FRAME */
.lp-hero-visual-wrapper {
  position: relative;
}

.lp-visual-frame {
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xl);
  overflow: hidden;
}

.lp-visual-header {
  height: 44px;
  background: var(--surface-primary);
  border-bottom: 1px solid var(--border-subtle);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
}

.lp-visual-dots {
  display: flex;
  gap: 6px;
}

.lp-vdot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--border-primary);
}

.lp-visual-title {
  font-size: 11.5px;
  color: var(--text-tertiary);
  font-weight: 500;
}

.lp-visual-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--color-success);
}

.lp-live-beacon {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-success);
  box-shadow: 0 0 8px var(--color-success);
}

.lp-telemetry-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1px;
  background: var(--border-subtle);
  border-bottom: 1px solid var(--border-subtle);
}

.lp-telemetry-item {
  background: var(--surface-primary);
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
}

.lp-telemetry-label {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-bottom: 3px;
}

.lp-telemetry-val {
  font-size: 13.5px;
  font-weight: 700;
  color: var(--text-primary);
}

.lp-gold-val {
  color: var(--lavender);
}

.lp-telemetry-sub {
  font-size: 10.5px;
  color: var(--text-disabled);
  margin-top: 2px;
}

.lp-dialogue-mockup {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.lp-mock-bubble {
  border-radius: var(--radius-md);
  padding: 16px;
  max-width: 92%;
  box-shadow: var(--shadow-sm);
}

.lp-client-bubble {
  background: var(--surface-primary);
  border: 1px solid var(--border-primary);
  align-self: flex-start;
}

.lp-agent-bubble {
  background: var(--surface-elevated);
  border: 1px solid var(--border-active);
  align-self: flex-end;
}

.lp-bubble-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
  font-size: 11.5px;
}

.lp-client-tag {
  background: var(--surface-interaction);
  color: var(--text-secondary);
  padding: 2px 7px;
  border-radius: 4px;
  font-weight: 600;
}

.lp-agent-badge {
  background: var(--violet-subtle);
  color: var(--lavender);
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.lp-bubble-subject {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.lp-bubble-text {
  margin: 0;
  font-size: 13.5px;
  line-height: 1.5;
  color: var(--text-primary);
}

.lp-flow-line {
  display: flex;
  align-items: center;
  gap: 10px;
  justify-content: center;
  font-size: 11.5px;
  color: var(--text-tertiary);
  padding: 6px 0;
}

.lp-flow-pulse {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--violet-primary);
}

.lp-agent-footer {
  margin-top: 10px;
  display: flex;
  align-items: center;
}

.lp-audit-tag {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--text-tertiary);
}

/* TICKER */
.lp-ticker-section {
  padding: 28px 0;
  background: var(--bg-secondary);
  border-top: 1px solid var(--border-subtle);
  border-bottom: 1px solid var(--border-subtle);
  overflow: hidden;
}

.lp-ticker-track-wrap {
  overflow: hidden;
  white-space: nowrap;
}

.lp-ticker-track {
  display: flex;
  gap: 40px;
  animation: ticker-slide 35s linear infinite;
}

@keyframes ticker-slide {
  from { transform: translateX(0); }
  to { transform: translateX(-50%); }
}

.lp-ticker-item {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  color: var(--text-secondary);
  flex-shrink: 0;
}

.lp-ticker-item svg {
  color: var(--violet-primary);
}

.lp-ticker-item strong {
  color: var(--text-primary);
}

/* SECTIONS */
.lp-section {
  padding: 92px 0;
  position: relative;
}

.lp-section-header {
  text-align: center;
  max-width: 680px;
  margin: 0 auto 56px;
}

.lp-section-tag {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 1px;
  text-transform: uppercase;
  color: var(--lavender);
  margin-bottom: 12px;
  display: inline-block;
}

.lp-section-title {
  font-size: 34px;
  font-weight: 800;
  letter-spacing: -0.9px;
  margin: 0 0 16px;
  color: var(--text-primary);
}

.lp-section-desc {
  font-size: 15.5px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin: 0;
}

/* HOW IT WORKS */
.lp-steps-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 28px;
}

.lp-step-card {
  background: var(--surface-primary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-lg);
  padding: 32px 28px;
  position: relative;
  transition: transform var(--transition), border-color var(--transition), box-shadow var(--transition);
}

.lp-step-card:hover {
  transform: translateY(-3px);
  border-color: var(--border-active);
  box-shadow: var(--shadow-md);
}

.lp-step-number {
  font-family: var(--font-display);
  font-size: 32px;
  font-weight: 800;
  color: var(--violet-primary);
  opacity: 0.85;
  margin-bottom: 16px;
}

.lp-step-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 12px;
}

.lp-step-text {
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin: 0;
}

/* FEATURES */
.lp-features-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 24px;
}

.lp-feature-card {
  background: var(--surface-primary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-lg);
  padding: 30px 26px;
  transition: all var(--transition);
}

.lp-feature-card:hover {
  border-color: var(--border-active);
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
}

.lp-feature-icon {
  width: 44px;
  height: 44px;
  border-radius: var(--radius-md);
  background: var(--violet-subtle);
  color: var(--lavender);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 20px;
}

.lp-feature-title {
  font-size: 17px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 10px;
}

.lp-feature-desc {
  font-size: 13.5px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin: 0;
}

/* AUTHORITY */
.lp-authority-section {
  padding: 80px 0;
  background: linear-gradient(180deg, var(--bg-main) 0%, var(--bg-secondary) 100%);
  border-top: 1px solid var(--border-subtle);
  border-bottom: 1px solid var(--border-subtle);
  text-align: center;
}

.lp-authority-quote {
  font-size: 32px;
  font-weight: 800;
  letter-spacing: -0.8px;
  color: var(--text-primary);
  max-width: 820px;
  margin: 0 auto 20px;
  line-height: 1.3;
}

.lp-authority-sub {
  font-size: 16px;
  color: var(--text-secondary);
  max-width: 640px;
  margin: 0 auto;
  line-height: 1.6;
}

/* FAQ */
.lp-faq-accordion {
  max-width: 780px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.lp-faq-item {
  background: var(--surface-primary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  overflow: hidden;
  transition: border-color var(--transition);
}

.lp-faq-item:hover {
  border-color: var(--border-subtle);
}

.lp-faq-question {
  width: 100%;
  padding: 18px 22px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  text-align: left;
}

.lp-faq-icon {
  font-size: 18px;
  color: var(--text-tertiary);
  transition: transform var(--transition);
}

.lp-faq-item.open .lp-faq-icon {
  transform: rotate(45deg);
  color: var(--violet-light);
}

.lp-faq-answer {
  padding: 0 22px 18px;
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-secondary);
}

/* FOOTER */
.lp-footer {
  background: var(--bg-secondary);
  border-top: 1px solid var(--border-subtle);
  padding: 60px 0 36px;
}

.lp-footer-grid {
  display: grid;
  grid-template-columns: 1.4fr 1fr 1fr;
  gap: 40px;
  margin-bottom: 48px;
}

.lp-footer-col h4 {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 16px;
}

.lp-footer-links {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.lp-footer-links a {
  text-decoration: none;
  font-size: 13.5px;
  color: var(--text-secondary);
  transition: color var(--transition);
}

.lp-footer-links a:hover {
  color: var(--text-primary);
}

.lp-footer-bottom {
  border-top: 1px solid var(--border-subtle);
  padding-top: 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12.5px;
  color: var(--text-tertiary);
}

/* ============================================================
   AUTH SHELL
   ============================================================ */
.auth-shell {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  background-color: var(--bg-main);
  position: relative;
}

.auth-top-nav {
  position: absolute;
  top: 24px;
  left: 24px;
}

.auth-card {
  width: 100%;
  max-width: 440px;
  background: var(--surface-primary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-xl);
  padding: 38px 34px;
  box-shadow: var(--shadow-xl);
}

.auth-mark {
  justify-content: center;
  margin-bottom: 6px;
}

.auth-sub {
  text-align: center;
  margin-bottom: 24px;
}

.tabs {
  display: flex;
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  padding: 4px;
  margin-bottom: 24px;
  gap: 4px;
}

.tab {
  flex: 1;
  padding: 8px 12px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  border-radius: 6px;
  transition: all var(--transition-fast);
  text-align: center;
}

.tab:hover {
  color: var(--text-primary);
}

.tab.active {
  background: var(--surface-elevated);
  color: var(--text-primary);
  box-shadow: var(--shadow-xs);
}

/* ============================================================
   APP SHELL
   ============================================================ */
.app {
  display: flex;
  min-height: 100vh;
  background-color: var(--bg-main);
  color: var(--text-primary);
  position: relative;
}

.sidebar {
  width: 250px;
  background: var(--bg-secondary);
  border-right: 1px solid var(--border-primary);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  position: sticky;
  top: 0;
  height: 100vh;
  transition: width var(--transition), transform var(--transition);
  z-index: 50;
  overflow: hidden;
}

.sidebar.is-collapsed {
  width: 76px;
}

.sidebar-header {
  height: 68px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 18px;
  border-bottom: 1px solid var(--border-subtle);
  flex-shrink: 0;
}

.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  text-decoration: none;
  overflow: hidden;
  white-space: nowrap;
}

.sidebar-brand .side-mark {
  font-size: 21px;
}

.sidebar-toggle-btn {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
  transition: all var(--transition);
}

.sidebar-toggle-btn:hover {
  background: var(--surface-interaction);
  color: var(--text-primary);
}

.sidebar.is-collapsed .sidebar-brand-text {
  display: none;
}

#nav {
  padding: 16px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  overflow-y: auto;
}

.nav-item {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  font-size: 13.5px;
  font-weight: 500;
  transition: all var(--transition-fast);
  position: relative;
  text-decoration: none;
  white-space: nowrap;
}

.nav-item-content {
  display: flex;
  align-items: center;
  gap: 12px;
}

.nav-item svg {
  color: var(--text-tertiary);
  transition: color var(--transition-fast);
}

.nav-item:hover {
  background: var(--surface-primary);
  color: var(--text-primary);
}

.nav-item:hover svg {
  color: var(--text-primary);
}

.nav-item.active {
  background: var(--surface-elevated);
  color: var(--text-primary);
  font-weight: 600;
}

.nav-item.active svg {
  color: var(--violet-primary);
}

.nav-item.active::before {
  content: "";
  position: absolute;
  left: 0;
  top: 8px;
  bottom: 8px;
  width: 3px;
  border-radius: 0 3px 3px 0;
  background: var(--violet-primary);
}

.sidebar.is-collapsed .nav-item {
  justify-content: center;
  padding: 12px;
}

.sidebar.is-collapsed .nav-item-content span:not(.svg-icon) {
  display: none;
}

.nav-unread-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--violet-primary);
  box-shadow: 0 0 6px var(--violet-primary);
}

.sidebar-bottom {
  padding: 16px 14px;
  border-top: 1px solid var(--border-subtle);
  display: flex;
  flex-direction: column;
  gap: 10px;
  background: var(--bg-secondary);
}

.sidebar-agent-status {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11.5px;
  padding: 6px 10px;
  border-radius: var(--radius-sm);
  background: var(--surface-primary);
  border: 1px solid var(--border-subtle);
  color: var(--text-secondary);
}

.sidebar-user-block {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

#side-user {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sidebar.is-collapsed .sidebar-bottom {
  padding: 12px 8px;
  align-items: center;
}

.sidebar.is-collapsed .sidebar-agent-status span {
  display: none;
}

.sidebar.is-collapsed #side-user {
  display: none;
}

/* MAIN */
.main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background-color: var(--bg-main);
}

.topbar {
  height: 68px;
  background: var(--bg-main);
  border-bottom: 1px solid var(--border-primary);
  padding: 0 28px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  position: sticky;
  top: 0;
  z-index: 40;
}

.topbar-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.topbar-titles {
  display: flex;
  flex-direction: column;
}

#page-title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.3px;
}

#page-subtitle {
  margin: 0;
  font-size: 12.5px;
  color: var(--text-tertiary);
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 14px;
}

.topbar-agent-pill {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 5px 12px;
  border-radius: var(--radius-full);
  font-size: 12px;
  font-weight: 600;
  background: var(--surface-primary);
  border: 1px solid var(--border-primary);
  color: var(--text-secondary);
}

.topbar-agent-pill.active {
  color: var(--color-success);
  border-color: var(--success-border);
  background: var(--color-success-bg);
}

.pulse-indicator {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
}

#mobile-menu {
  display: none;
}

.page {
  padding: 28px;
  max-width: 1440px;
  width: 100%;
  margin: 0 auto;
}

.panel {
  background: var(--surface-primary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-lg);
  padding: 24px;
  margin-bottom: 24px;
  box-shadow: var(--shadow-sm);
}

.panel-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 12px;
}

.panel-heading h2 {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.2px;
}

/* ============================================================
   DASHBOARD RECONSTRUCTION (7 KEY KPI CARDS + CHARTS)
   ============================================================ */
.dashboard-header-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
  flex-wrap: wrap;
  gap: 16px;
}

.dashboard-period-selector {
  display: flex;
  align-items: center;
  background: var(--surface-primary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-sm);
  padding: 3px;
  gap: 2px;
}

.period-btn {
  padding: 5px 12px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  border-radius: 6px;
  transition: all var(--transition-fast);
}

.period-btn.active {
  background: var(--surface-elevated);
  color: var(--text-primary);
  box-shadow: var(--shadow-xs);
}

/* 7 KPI CARDS GRID */
.kpi-seven-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

@media (max-width: 1200px) {
  .kpi-seven-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

.kpi-card, .metric {
  background: var(--surface-primary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
  transition: all var(--transition);
  position: relative;
  overflow: hidden;
}

.kpi-card:hover, .metric:hover {
  border-color: var(--border-subtle);
  background: var(--surface-elevated);
  transform: translateY(-2px);
  box-shadow: var(--shadow-sm);
}

.kpi-card.hero-kpi {
  grid-column: span 2;
  background: linear-gradient(135deg, var(--surface-primary) 0%, var(--surface-elevated) 100%);
  border-color: rgba(128, 101, 201, 0.28);
}

.kpi-card-top, .bento-metric-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.kpi-card-label, .bento-metric-label {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-secondary);
}

.kpi-card-icon, .bento-metric-icon {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm);
  background: var(--surface-interaction);
  color: var(--violet-light);
  display: flex;
  align-items: center;
  justify-content: center;
}

.kpi-card-value, .bento-metric-number {
  font-size: 28px;
  font-weight: 800;
  color: var(--text-primary);
  letter-spacing: -0.8px;
  line-height: 1.1;
  margin-bottom: 6px;
}

.kpi-card-sub, .bento-metric-sub {
  font-size: 11.5px;
  color: var(--text-tertiary);
  display: flex;
  align-items: center;
  gap: 6px;
}

.kpi-trend-pill, .bento-compare-pill {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  background: var(--surface-interaction);
  color: var(--lavender);
}

.kpi-trend-pill.up {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.clickable, .clickable-card {
  cursor: pointer;
}

/* MAIN ROW */
.dashboard-main-row {
  display: grid;
  grid-template-columns: 1.6fr 1fr;
  gap: 24px;
  margin-bottom: 24px;
}

@media (max-width: 1024px) {
  .dashboard-main-row {
    grid-template-columns: 1fr;
  }
}

.chart {
  min-height: 220px;
  width: 100%;
  display: flex;
  align-items: flex-end;
  gap: 18px;
  padding: 16px 8px;
}

.bar-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  height: 100%;
  justify-content: flex-end;
}

.bar-box {
  width: 100%;
  max-width: 54px;
  background: var(--violet-subtle);
  border-radius: 6px 6px 0 0;
  border: 1px solid var(--border-active);
  transition: height var(--transition-slow), background var(--transition);
  position: relative;
}

.bar-box:hover {
  background: var(--violet-primary);
}

.bar-val {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-primary);
}

.bar-label {
  font-size: 11.5px;
  color: var(--text-tertiary);
}

/* LOWER ROW */
.dashboard-lower-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
}

@media (max-width: 900px) {
  .dashboard-lower-row {
    grid-template-columns: 1fr;
  }
}

.activity-feed-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.activity-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  background: var(--surface-elevated);
  border: 1px solid var(--border-subtle);
  font-size: 12.5px;
}

.activity-icon-bubble {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--surface-interaction);
  color: var(--violet-light);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-top: 2px;
}

.activity-info strong {
  display: block;
  color: var(--text-primary);
  margin-bottom: 2px;
}

.activity-time {
  font-size: 11px;
  color: var(--text-disabled);
}

.insight-box {
  background: var(--surface-elevated);
  border: 1px solid var(--border-primary);
  border-left: 3px solid var(--violet-primary);
  border-radius: var(--radius-sm);
  padding: 14px 16px;
  margin-bottom: 12px;
}

.insight-box strong {
  display: block;
  font-size: 13.5px;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.insight-box p {
  margin: 0;
  font-size: 12.5px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.pending-card {
  background: var(--surface-elevated);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  padding: 14px;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.pending-card strong {
  font-size: 13.5px;
  color: var(--text-primary);
}

.pending-card p {
  margin: 3px 0 0;
  font-size: 12px;
  color: var(--text-secondary);
}

.knowledge-hero-banner {
  background: linear-gradient(135deg, var(--surface-primary) 0%, var(--surface-elevated) 100%);
  border: 1px solid var(--border-active);
  border-radius: var(--radius-lg);
  padding: 24px;
  margin-bottom: 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  box-shadow: var(--shadow-sm);
}

.knowledge-hero-content {
  flex: 1;
}

.knowledge-hero-top {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.knowledge-hero-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  font-weight: 700;
  color: var(--lavender);
  background: var(--violet-subtle);
  padding: 3px 8px;
  border-radius: 4px;
}

.knowledge-hero-title {
  margin: 0 0 6px;
  font-size: 18px;
  font-weight: 800;
  color: var(--text-primary);
}

.knowledge-hero-desc {
  margin: 0 0 16px;
  font-size: 13px;
  color: var(--text-secondary);
  max-width: 680px;
}

.knowledge-progress-bar {
  height: 7px;
  background: var(--bg-main);
  border-radius: var(--radius-full);
  overflow: hidden;
  margin-bottom: 8px;
}

.knowledge-progress-fill {
  height: 100%;
  background: var(--violet-primary);
  border-radius: var(--radius-full);
  transition: width var(--transition-slow);
}

.knowledge-progress-stats {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  color: var(--text-secondary);
}

.knowledge-missing-pills-wrap {
  margin-top: 12px;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.knowledge-pill-btn {
  background: var(--surface-interaction);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-full);
  padding: 3px 10px;
  font-size: 11.5px;
  color: var(--lavender);
  transition: all var(--transition-fast);
}

.knowledge-pill-btn:hover {
  background: var(--violet-subtle);
  border-color: var(--violet-primary);
}

/* ============================================================
   MENSAGENS (3-COLUMN WORKSPACE)
   ============================================================ */
.messages-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.messages-header-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.messages-top-controls {
  display: flex;
  align-items: center;
  gap: 12px;
}

.agent-master-switch-box {
  display: flex;
  align-items: center;
  gap: 10px;
  background: var(--surface-primary);
  border: 1px solid var(--border-primary);
  padding: 6px 12px;
  border-radius: var(--radius-sm);
}

.agent-switch-info {
  display: flex;
  flex-direction: column;
}

.agent-switch-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-primary);
}

.agent-switch-sub {
  font-size: 10px;
  color: var(--text-tertiary);
}

.agent-slider-switch {
  width: 52px;
  height: 26px;
  background: var(--surface-interaction);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-full);
  position: relative;
  transition: all var(--transition);
  padding: 2px;
}

.agent-slider-switch.active {
  background: var(--violet-primary);
  border-color: var(--violet-primary);
}

.switch-slider-thumb {
  width: 20px;
  height: 20px;
  background: #FFFFFF;
  border-radius: 50%;
  position: absolute;
  top: 2px;
  left: 2px;
  transition: transform var(--transition);
  box-shadow: 0 1px 3px rgba(0,0,0,0.4);
}

.agent-slider-switch.active .switch-slider-thumb {
  transform: translateX(26px);
}

.switch-label-state {
  display: none;
}

.messages-workspace {
  display: grid;
  grid-template-columns: 320px 1fr 290px;
  gap: 16px;
  height: calc(100vh - 200px);
  min-height: 560px;
}

@media (max-width: 1280px) {
  .messages-workspace {
    grid-template-columns: 300px 1fr;
  }
  .messages-profile-panel {
    display: none;
  }
}

@media (max-width: 840px) {
  .messages-workspace {
    grid-template-columns: 1fr;
  }
}

.messages-inbox-col {
  background: var(--surface-primary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-lg);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.inbox-search-header {
  padding: 14px;
  border-bottom: 1px solid var(--border-subtle);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.inbox-search-header input {
  width: 100%;
  font-size: 13px;
  padding: 8px 12px;
}

.inbox-filter-pills {
  display: flex;
  gap: 6px;
}

.inbox-filter-pill {
  padding: 3px 9px;
  font-size: 11.5px;
  font-weight: 600;
  color: var(--text-secondary);
  border-radius: var(--radius-full);
  background: var(--surface-elevated);
}

.inbox-filter-pill.active {
  background: var(--violet-subtle);
  color: var(--lavender);
  border: 1px solid var(--border-active);
}

.contact-card-grid {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.contact-card-item {
  padding: 14px 16px;
  border-bottom: 1px solid var(--border-subtle);
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
  transition: all var(--transition-fast);
  position: relative;
}

.contact-card-item:hover {
  background: var(--surface-elevated);
}

.contact-card-item.selected, .contact-card-item.active {
  background: var(--surface-elevated);
  border-left: 3px solid var(--violet-primary);
}

.contact-card-avatar {
  width: 38px;
  height: 38px;
  border-radius: 50%;
  background: var(--surface-interaction);
  color: var(--lavender);
  font-size: 14px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border: 1px solid var(--border-subtle);
}

.contact-card-info {
  flex: 1;
  min-width: 0;
}

.contact-card-name {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 2px;
}

.contact-channel-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 4px;
  background: var(--surface-interaction);
  color: var(--text-tertiary);
}

.contact-channel-badge.email {
  background: var(--violet-subtle);
  color: var(--lavender);
}

.contact-card-meta {
  font-size: 11.5px;
  color: var(--text-tertiary);
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.contact-card-last-msg {
  font-size: 12px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.contact-card-arrow {
  color: var(--text-tertiary);
  font-size: 16px;
}

.messages-canvas-col {
  background: var(--surface-primary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-lg);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.chat-header {
  height: 64px;
  padding: 0 20px;
  background: var(--surface-primary);
  border-bottom: 1px solid var(--border-subtle);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.conversation-live-bar {
  padding: 7px 16px;
  background: var(--surface-elevated);
  border-bottom: 1px solid var(--border-subtle);
  font-size: 11.5px;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: 8px;
}

.live-pulse-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-success);
  box-shadow: 0 0 6px var(--color-success);
}

.conversation {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.bubble {
  max-width: 78%;
  padding: 14px 18px;
  border-radius: var(--radius-md);
  font-size: 13.5px;
  line-height: 1.5;
  box-shadow: var(--shadow-xs);
  position: relative;
}

.bubble.customer {
  align-self: flex-start;
  background: var(--surface-elevated);
  border: 1px solid var(--border-primary);
  color: var(--text-primary);
}

.bubble.agent {
  align-self: flex-end;
  background: var(--surface-interaction);
  border: 1px solid var(--border-active);
  color: var(--text-primary);
}

.bubble.owner {
  align-self: flex-end;
  background: var(--violet-dark);
  border: 1px solid var(--violet-light);
  color: #FFFFFF;
}

.bubble-footer {
  margin-top: 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.bubble-footer small {
  font-size: 11px;
  color: var(--text-tertiary);
}

.btn-delete-msg {
  color: var(--text-disabled);
  padding: 2px 4px;
  border-radius: 4px;
  transition: all var(--transition-fast);
}

.btn-delete-msg:hover {
  color: var(--color-error);
  background: var(--color-error-bg);
}

.owner-reply-box {
  padding: 16px 20px;
  background: var(--surface-primary);
  border-top: 1px solid var(--border-subtle);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.owner-reply-box textarea {
  width: 100%;
  font-size: 13.5px;
}

.owner-reply-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.messages-profile-panel {
  background: var(--surface-primary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-lg);
  padding: 20px;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

.profile-section-heading {
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  color: var(--text-tertiary);
  margin-bottom: 12px;
}

.profile-field-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-bottom: 12px;
}

.profile-field-label {
  font-size: 11px;
  color: var(--text-tertiary);
}

.profile-field-value {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

/* ============================================================
   RELATÓRIOS
   ============================================================ */
.reports-kpi-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.chart.line-chart {
  height: 260px;
}

.chart-labels {
  display: flex;
  justify-content: space-between;
  padding: 10px 0 0;
  font-size: 11px;
  color: var(--text-tertiary);
  border-top: 1px solid var(--border-subtle);
}

.variant-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 16px;
}

.variant-card {
  background: var(--surface-elevated);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  padding: 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

/* ============================================================
   NEGÓCIO & BANCO DE STOCK
   ============================================================ */
.business-subtabs-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--surface-primary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  padding: 6px;
  margin-bottom: 24px;
  overflow-x: auto;
}

.business-subtab {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 18px;
  border-radius: var(--radius-sm);
  font-size: 13.5px;
  font-weight: 600;
  color: var(--text-secondary);
  transition: all var(--transition-fast);
  white-space: nowrap;
}

.business-subtab:hover {
  color: var(--text-primary);
  background: var(--surface-interaction);
}

.business-subtab.active {
  background: var(--surface-elevated);
  color: var(--text-primary);
  border: 1px solid var(--border-active);
  box-shadow: var(--shadow-xs);
}

.subtab-pill {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 7px;
  border-radius: var(--radius-full);
  background: var(--surface-interaction);
  color: var(--text-tertiary);
}

.business-subtab.active .subtab-pill {
  background: var(--violet-subtle);
  color: var(--lavender);
}

/* CARDS DO NEGÓCIO */
.card-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
  margin-top: 20px;
}

@media (max-width: 1100px) {
  .card-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 720px) {
  .card-grid {
    grid-template-columns: 1fr;
  }
}

.business-card-item {
  background: var(--surface-primary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  padding: 22px;
  display: flex;
  flex-direction: column;
  transition: all var(--transition);
  position: relative;
}

.business-card-item:hover {
  border-color: var(--border-active);
  transform: translateY(-2px);
  box-shadow: var(--shadow-sm);
}

.business-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.business-card-icon-box {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-sm);
  background: var(--violet-subtle);
  color: var(--lavender);
  display: flex;
  align-items: center;
  justify-content: center;
}

.business-card-status-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 7px;
  border-radius: 4px;
}

.business-card-status-badge.configured {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.business-card-status-badge.pending {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.business-card-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 6px;
}

.business-card-desc {
  font-size: 12.5px;
  color: var(--text-secondary);
  line-height: 1.5;
  margin: 0 0 16px;
  flex: 1;
}

.business-card-items-preview {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 16px;
}

.preview-pill {
  font-size: 12px;
  color: var(--text-secondary);
  background: var(--surface-elevated);
  padding: 4px 8px;
  border-radius: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* KIND PICKER */
.kind-picker {
  background: var(--surface-elevated);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  padding: 20px;
  margin-top: 16px;
}

.kind-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-top: 14px;
}

@media (max-width: 900px) {
  .kind-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

.kind-option {
  background: var(--surface-primary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-sm);
  padding: 12px;
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  color: var(--text-secondary);
  transition: all var(--transition-fast);
}

.kind-option:hover {
  background: var(--surface-interaction);
  border-color: var(--border-active);
  color: var(--text-primary);
}

/* BANCO DE STOCK */
.stock-kpi-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

@media (max-width: 900px) {
  .stock-kpi-row {
    grid-template-columns: repeat(2, 1fr);
  }
}

.stock-table-wrap {
  overflow-x: auto;
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
}

.stock-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
}

.stock-table th {
  background: var(--surface-elevated);
  padding: 12px 16px;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border-primary);
}

.stock-table td {
  padding: 14px 16px;
  font-size: 13.5px;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-primary);
}

.stock-table tr:hover td {
  background: var(--surface-elevated);
}

.stock-status-tag {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11.5px;
  font-weight: 600;
}

.stock-status-tag.available {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.stock-status-tag.low {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.stock-status-tag.out {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.variant-pill-tag {
  display: inline-block;
  background: var(--surface-interaction);
  border: 1px solid var(--border-subtle);
  border-radius: 4px;
  padding: 2px 6px;
  font-size: 11px;
  color: var(--lavender);
  margin: 2px;
}

/* TREINAMENTO LIVRE */
.training-induce-box {
  background: var(--surface-elevated);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  padding: 16px 20px;
  display: flex;
  align-items: flex-start;
  gap: 14px;
  margin-bottom: 20px;
}

.training-induce-icon {
  color: var(--violet-light);
  margin-top: 2px;
}

.training-upload-zone {
  border: 2px dashed var(--border-primary);
  border-radius: var(--radius-md);
  padding: 28px;
  text-align: center;
  background: var(--surface-elevated);
  cursor: pointer;
  transition: all var(--transition);
}

.training-upload-zone:hover, .training-upload-zone.dragover {
  border-color: var(--violet-primary);
  background: var(--surface-interaction);
}

.training-meter-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--surface-elevated);
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-subtle);
  margin-top: 10px;
}

.stat-pill {
  font-size: 12px;
  color: var(--text-secondary);
  background: var(--surface-interaction);
  padding: 3px 8px;
  border-radius: 4px;
}

/* ============================================================
   CONFIGURAÇÕES & AGENT STUDIO
   ============================================================ */
.settings-tabs {
  display: flex;
  gap: 6px;
  border-bottom: 1px solid var(--border-primary);
  margin-bottom: 24px;
  overflow-x: auto;
}

.settings-tab {
  padding: 10px 18px;
  font-size: 13.5px;
  font-weight: 600;
  color: var(--text-secondary);
  border-bottom: 2px solid transparent;
  transition: all var(--transition-fast);
  white-space: nowrap;
}

.settings-tab:hover {
  color: var(--text-primary);
}

.settings-tab.active {
  color: var(--violet-light);
  border-bottom-color: var(--violet-primary);
}

/* AGENT STUDIO INTERNALS */
.agent-studio-shell {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.agent-studio-subnav {
  display: flex;
  gap: 6px;
  background: var(--surface-elevated);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  padding: 4px;
  overflow-x: auto;
}

.agent-studio-subtab {
  flex: 1;
  padding: 8px 12px;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-secondary);
  border-radius: 6px;
  text-align: center;
  transition: all var(--transition-fast);
  white-space: nowrap;
}

.agent-studio-subtab.active {
  background: var(--violet-primary);
  color: #FFFFFF;
}

.agent-studio-card {
  background: var(--surface-primary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-lg);
  padding: 24px;
}

/* GMAIL VIEW */
.wa-hero-card, .wa-connected-card {
  background: var(--surface-elevated);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-lg);
  padding: 28px;
}

.wa-steps-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
  margin: 24px 0;
}

.wa-step-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.wa-step-num {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--violet-primary);
  color: #FFFFFF;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 13px;
  flex-shrink: 0;
}

.wa-info-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-top: 20px;
}

.wa-info-item {
  background: var(--surface-primary);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
}

.wa-info-label {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-bottom: 4px;
}

.wa-alert-box {
  background: var(--color-warning-bg);
  border: 1px solid #634C2B;
  border-radius: var(--radius-md);
  padding: 16px 20px;
  display: flex;
  align-items: flex-start;
  gap: 14px;
  margin-bottom: 20px;
}

.wa-alert-icon {
  color: var(--color-warning);
  margin-top: 2px;
}

/* STRIPE VIEW */
.billing-featured-card {
  background: linear-gradient(135deg, var(--surface-primary) 0%, var(--surface-elevated) 100%);
  border: 1px solid var(--border-active);
  border-radius: var(--radius-lg);
  padding: 32px;
  position: relative;
  overflow: hidden;
}

.billing-badge-flag {
  display: inline-block;
  background: var(--violet-subtle);
  color: var(--lavender);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.6px;
  padding: 4px 10px;
  border-radius: var(--radius-full);
  margin-bottom: 16px;
}

.billing-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 28px;
  flex-wrap: wrap;
}

.billing-plan-name {
  margin: 0 0 6px;
  font-size: 26px;
  font-weight: 800;
  color: var(--text-primary);
}

.billing-price-box {
  display: flex;
  align-items: baseline;
  gap: 4px;
}

.billing-currency {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
}

.billing-amount {
  font-size: 40px;
  font-weight: 800;
  color: var(--text-primary);
  line-height: 1;
}

.billing-cents {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-secondary);
}

.billing-period {
  font-size: 14px;
  color: var(--text-tertiary);
  margin-left: 4px;
}

.billing-features-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 18px;
  margin-bottom: 32px;
}

.billing-feature-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.billing-feature-item .feature-icon {
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  background: var(--violet-subtle);
  color: var(--lavender);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.billing-security-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-top: 24px;
  padding-top: 20px;
  border-top: 1px solid var(--border-subtle);
  flex-wrap: wrap;
}

.security-badge-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-tertiary);
}

/* ============================================================
   MODALS & EXPANDED CARDS
   ============================================================ */
.modal-backdrop, .modal {
  position: fixed;
  inset: 0;
  background: rgba(8, 8, 11, 0.78);
  backdrop-filter: blur(8px);
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.modal-card {
  width: 100%;
  max-width: 520px;
  background: var(--surface-primary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-lg);
  padding: 30px;
  box-shadow: var(--shadow-xl);
  position: relative;
}

.modal-card.modal-card-large {
  max-width: 780px;
}

.modal-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 20px;
}

.modal-close-btn {
  font-size: 22px;
  color: var(--text-tertiary);
  transition: color var(--transition-fast);
  line-height: 1;
}

.modal-close-btn:hover {
  color: var(--text-primary);
}

/* EXPANDED BUSINESS CARD */
.expanded-card-shell {
  width: 100%;
  max-width: 760px;
  background: var(--surface-primary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-lg);
  padding: 32px;
  box-shadow: var(--shadow-xl);
  max-height: 90vh;
  overflow-y: auto;
}

.expanded-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border-subtle);
}

.expanded-header-kbadge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-weight: 700;
  color: var(--lavender);
  background: var(--violet-subtle);
  padding: 3px 8px;
  border-radius: 4px;
  margin-bottom: 6px;
}

.expanded-header-kbadge-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--violet-light);
}

.expanded-header-title {
  margin: 0 0 4px;
  font-size: 20px;
  font-weight: 800;
  color: var(--text-primary);
}

.expanded-header-subtitle {
  margin: 0;
  font-size: 12.5px;
  color: var(--text-tertiary);
}

.expanded-close {
  font-size: 24px;
  color: var(--text-tertiary);
  transition: color var(--transition-fast);
  line-height: 1;
}

.expanded-close:hover {
  color: var(--text-primary);
}

.modal-section {
  margin-bottom: 24px;
}

.modal-section-label {
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  color: var(--text-tertiary);
  margin-bottom: 12px;
}

.modal-items-count {
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 12px;
}

.items-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 18px;
}

.item-entry {
  background: var(--surface-elevated);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  padding: 12px 14px;
  display: flex;
  align-items: center;
  gap: 14px;
  transition: all var(--transition-fast);
}

.item-entry.editing {
  border-color: var(--border-active);
  background: var(--surface-interaction);
}

.item-entry-index {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--surface-interaction);
  color: var(--lavender);
  font-size: 11px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.item-entry-info {
  flex: 1;
  min-width: 0;
}

.item-entry-title {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 10px;
}

.item-entry-price {
  font-size: 12px;
  color: var(--lavender);
  font-weight: 700;
  background: var(--violet-subtle);
  padding: 1px 6px;
  border-radius: 4px;
}

.item-entry-desc {
  margin: 3px 0 0;
  font-size: 12px;
  color: var(--text-secondary);
}

.item-entry-actions {
  display: flex;
  gap: 6px;
}

.item-inline-builder {
  background: var(--surface-elevated);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  padding: 18px;
  margin-bottom: 20px;
}

.item-builder-title {
  font-size: 13.5px;
  font-weight: 700;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
}

.item-builder-badge {
  font-size: 10px;
  font-weight: 700;
  background: var(--violet-primary);
  color: #FFFFFF;
  padding: 1px 5px;
  border-radius: 3px;
}

.item-builder-grid {
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  gap: 12px;
  margin-bottom: 12px;
}

.item-builder-label {
  display: flex;
  flex-direction: column;
  gap: 5px;
  font-size: 12px;
  color: var(--text-secondary);
}

.modal-card-settings {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.modal-card-settings-label {
  display: flex;
  flex-direction: column;
  gap: 5px;
  font-size: 12.5px;
  color: var(--text-secondary);
}

.expanded-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 24px;
  padding-top: 18px;
  border-top: 1px solid var(--border-subtle);
}

/* ============================================================
   RESPONSIVE DESIGN
   ============================================================ */
@media (max-width: 768px) {
  .topbar {
    padding: 0 16px;
  }
  #mobile-menu {
    display: inline-flex;
  }
  .sidebar {
    position: fixed;
    top: 0;
    left: 0;
    bottom: 0;
    transform: translateX(-100%);
    width: 260px !important;
  }
  .sidebar.open {
    transform: translateX(0);
  }
  .page {
    padding: 16px;
  }
  .lp-hero-grid {
    grid-template-columns: 1fr;
    gap: 36px;
  }
  .lp-hero-title {
    font-size: 32px;
  }
  .lp-steps-grid, .lp-features-grid, .billing-features-grid {
    grid-template-columns: 1fr;
  }
  .kpi-seven-grid {
    grid-template-columns: 1fr;
  }
  .kpi-card.hero-kpi {
    grid-column: span 1;
  }
}
"""

with open("frontend/styles.css", "w", encoding="utf-8") as f:
    f.write(css_content)

print(f"styles.css updated: {len(css_content)} chars.")
