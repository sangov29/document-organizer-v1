'use client';
import { FormEvent, useState } from 'react';
import Link from 'next/link';
import { api } from '../../lib/api';
export default function Login() {
  const [message, setMessage] = useState('');
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const data = new FormData(e.currentTarget);
    const totp = String(data.get('totp_code') ?? '').trim();
    try {
      const result = await api('/auth/login', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({email:data.get('email'), password:data.get('password'), totp_code:totp || null})
      });
      localStorage.setItem('access_token', result.access_token); window.location.href = '/documents';
    } catch (e) { setMessage(e instanceof Error ? e.message : 'Login failed'); }
  }
  return <section className="auth-shell"><div className="auth-intro">
    <p className="eyebrow">Private by design</p><h1>Welcome back.</h1>
    <p>Sign in to organize, review and export your documents securely.</p>
    <div className="trust-note"><span>✓</span><p><strong>Your workspace stays yours.</strong><br/>Sensitive values remain concealed until you explicitly reveal them.</p></div>
  </div><div className="auth-card"><p className="panel-kicker">Account access</p><h2>Login</h2><p className="muted">Enter your credentials to continue.</p>
    <form onSubmit={submit}>
      <label>Email address<input name="email" type="email" placeholder="you@example.com" autoComplete="email" required/></label>
      <label>Password<input name="password" type="password" placeholder="Enter your password" autoComplete="current-password" required/></label>
      <label>Authenticator code <span className="optional">Optional</span><input name="totp_code" inputMode="numeric" placeholder="6-digit code, if enabled" autoComplete="one-time-code"/></label>
      <button>Login</button>
    </form><div className="auth-links"><Link href="/forgot-password">Forgot password?</Link><span>New here? <Link href="/register">Create an account</Link></span></div><p role="status" className={message ? 'form-message' : ''}>{message}</p>
  </div></section>;
}
