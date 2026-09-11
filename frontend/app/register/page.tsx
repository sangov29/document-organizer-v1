'use client';
import { FormEvent, useState } from 'react';
import Link from 'next/link';
import { api } from '../../lib/api';
export default function Register() {
  const [message, setMessage] = useState('');
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const data = new FormData(e.currentTarget);
    try { const user = await api('/auth/register', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({email:data.get('email'), password:data.get('password')})}); setMessage(user.message); }
    catch (e) { setMessage(e instanceof Error ? e.message : 'Registration failed'); }
  }
  return <section className="auth-shell"><div className="auth-intro">
    <p className="eyebrow">Your intelligent archive</p><h1>Make documents useful.</h1>
    <p>Turn scans and PDFs into searchable, structured information with a complete audit trail.</p>
    <ul className="benefit-list"><li>OCR and document classification</li><li>Verified fields with provenance</li><li>Protected sensitive information</li></ul>
  </div><div className="auth-card"><p className="panel-kicker">Get started</p><h2>Register</h2><p className="muted">Create your private DocuFlow workspace.</p>
    <form onSubmit={submit}><label>Email address<input name="email" type="email" placeholder="you@example.com" autoComplete="email" required/></label><label>Password<input name="password" type="password" minLength={12} placeholder="At least 12 characters" autoComplete="new-password" required/></label><p className="field-help">Use 12 or more characters. A verification link will be sent to your email.</p><button>Register</button></form>
    <p className="auth-switch">Already registered? <Link href="/login">Sign in</Link></p><p role="status" className={message ? 'form-message' : ''}>{message}</p>
  </div></section>;
}
