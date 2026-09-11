'use client';
import { FormEvent, useState } from 'react';
import Link from 'next/link';
import { api } from '../../lib/api';
export default function ForgotPassword() {
  const [message, setMessage] = useState('');
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const data = new FormData(e.currentTarget);
    try { const r = await api('/auth/password-reset/request', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({email:data.get('email')})}); setMessage(r.message); }
    catch { setMessage('If the account can be reset, instructions will be sent.'); }
  }
  return <section className="auth-single"><div className="auth-card"><p className="panel-kicker">Account recovery</p><h1>Reset password</h1><p className="muted">Enter your email and we’ll send instructions if the account is eligible for reset.</p><form onSubmit={submit}><label>Email address<input name="email" type="email" placeholder="you@example.com" autoComplete="email" required/></label><button>Send reset link</button></form><p role="status" className={message ? 'form-message' : ''}>{message}</p><p className="auth-switch"><Link href="/login">← Back to login</Link></p></div></section>;
}
