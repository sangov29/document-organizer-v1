'use client';
import { useEffect, useState } from 'react';
import { api } from '../../lib/api';

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

  return <><h1>Email verification</h1><p role="status">{message}</p></>;
}
