'use client';
import { useEffect, useState } from 'react';
import { api } from '../../lib/api';
import Link from 'next/link';

export default function VerifyEmail() {
  const [message, setMessage] = useState('Verifying…');

  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get('token');
    if (!token) { setMessage('Verification link is missing a token.'); return; }
    api('/auth/verify-email', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({token}),
    }).then(() => setMessage('Email verified. You can now log in.'))
      .catch((e) => setMessage(e instanceof Error ? e.message : 'Verification failed.'));
  }, []);

  return <section className="auth-single"><div className="auth-card status-card"><div className="status-icon">✓</div><p className="panel-kicker">Identity check</p><h1>Email verification</h1><p role="status" className="form-message">{message}</p><Link className="button-link" href="/login">Continue to login</Link></div></section>;
}
