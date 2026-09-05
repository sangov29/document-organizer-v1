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
  return <><h1>Security</h1><button onClick={setup}>Set up authenticator</button>{secret && <div className="card"><strong>Secret</strong><div>{secret}</div><div className="muted">{uri}</div></div>}<form onSubmit={confirm}><input name="code" inputMode="numeric" placeholder="Authenticator code" required/><button>Confirm</button></form><p>{message}</p></>;
}
