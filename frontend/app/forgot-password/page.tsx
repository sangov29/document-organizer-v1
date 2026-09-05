'use client';
import { FormEvent, useState } from 'react';
import { api } from '../../lib/api';
export default function ForgotPassword() {
  const [message, setMessage] = useState('');
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const data = new FormData(e.currentTarget);
    try { const r = await api('/auth/password-reset/request', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({email:data.get('email')})}); setMessage(r.message); }
    catch { setMessage('If the account can be reset, instructions will be sent.'); }
  }
  return <><h1>Reset password</h1><form onSubmit={submit}><input name="email" type="email" placeholder="Email" required/><button>Send reset link</button></form><p>{message}</p></>;
}
