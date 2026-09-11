'use client';
import { FormEvent, useState } from 'react';
import { API } from '../../lib/api';
export default function Security() {
  const [secret, setSecret] = useState(''); const [uri, setUri] = useState(''); const [message, setMessage] = useState('');
  const token = () => localStorage.getItem('access_token') ?? '';
  async function setup() {
    const r = await fetch(`${API}/api/v1/auth/totp/setup`, {method:'POST', headers:{Authorization:`Bearer ${token()}`}});
    const b = await r.json(); if (!r.ok) { setMessage(b.detail ?? 'Setup failed'); return; } setSecret(b.secret); setUri(b.provisioning_uri); setMessage('Add this secret to your authenticator, then confirm a code.');
  }
  async function confirm(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const data = new FormData(e.currentTarget);
    const r = await fetch(`${API}/api/v1/auth/totp/confirm`, {method:'POST', headers:{Authorization:`Bearer ${token()}`,'Content-Type':'application/json'}, body:JSON.stringify({code:data.get('code')})});
    setMessage(r.ok ? 'TOTP enabled.' : 'Could not confirm TOTP code.');
  }
  return <section className="security-page"><div className="page-heading"><div><p className="eyebrow">Account protection</p><h1>Security</h1><p className="muted">Add a second verification step to protect your private documents.</p></div><div className="security-badge"><span>2FA</span><strong>Authenticator app</strong></div></div>
    <div className="security-grid"><article className="panel security-overview"><span className="step-number">1</span><div><p className="panel-kicker">Connect an app</p><h2>Set up your authenticator</h2><p className="muted">Generate a secret, then add it to Google Authenticator, Microsoft Authenticator or another TOTP app.</p><button onClick={setup}>Set up authenticator</button></div></article>
    <article className="panel security-overview"><span className="step-number">2</span><div><p className="panel-kicker">Verify setup</p><h2>Confirm a code</h2><p className="muted">Enter the current six-digit code. Two-factor authentication becomes mandatory only after confirmation.</p><form onSubmit={confirm}><label>Authenticator code<input name="code" inputMode="numeric" pattern="[0-9]*" placeholder="000000" autoComplete="one-time-code" required/></label><button>Confirm</button></form></div></article></div>
    {secret && <aside className="secret-card" aria-live="polite"><div><p className="panel-kicker">Manual setup key</p><strong className="secret-value">{secret}</strong><p className="muted uri">{uri}</p></div><span className="privacy-chip">Keep private</span></aside>}
    <p role="status" className={message ? 'form-message' : ''}>{message}</p>
  </section>;
}
