'use client';
import { FormEvent, useState } from 'react';
import { api } from '../../lib/api';
export default function Register() {
  const [message, setMessage] = useState('');
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const data = new FormData(e.currentTarget);
    try { const user = await api('/auth/register', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({email:data.get('email'), password:data.get('password')})}); setMessage(user.message); }
    catch (e) { setMessage(e instanceof Error ? e.message : 'Registration failed'); }
  }
  return <><h1>Register</h1><form onSubmit={submit}><input name="email" type="email" placeholder="Email" required/><input name="password" type="password" minLength={12} placeholder="Password (12+ chars)" required/><button>Register</button></form><p role="status">{message}</p></>;
}
