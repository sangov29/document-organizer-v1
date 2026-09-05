'use client';
import { FormEvent, useState } from 'react';
import { api } from '../../lib/api';
export default function ResetPassword() {
  const [message, setMessage] = useState('');
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const data = new FormData(e.currentTarget);
    const token = new URLSearchParams(window.location.search).get('token');
    if (!token) { setMessage('Reset link is missing a token.'); return; }
    try { const r = await api('/auth/password-reset/confirm', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({token, new_password:data.get('password')})}); setMessage(r.message); }
    catch (e) { setMessage(e instanceof Error ? e.message : 'Reset failed'); }
  }
  return <><h1>Choose a new password</h1><form onSubmit={submit}><input name="password" type="password" minLength={12} placeholder="New password (12+ chars)" required/><button>Reset password</button></form><p>{message}</p></>;
}
