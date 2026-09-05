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
  return <><h1>Login</h1><form onSubmit={submit}>
    <input name="email" type="email" placeholder="Email" required/>
    <input name="password" type="password" placeholder="Password" required/>
    <input name="totp_code" inputMode="numeric" placeholder="Authenticator code (if enabled)"/>
    <button>Login</button>
  </form><p><Link href="/forgot-password">Forgot password?</Link></p><p>{message}</p></>;
}
