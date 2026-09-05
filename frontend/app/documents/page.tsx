'use client';
import { FormEvent, useEffect, useState } from 'react';
import Link from 'next/link';
import { API } from '../../lib/api';
type Doc = {id:string; original_filename:string; status:string; size_bytes:number; uploaded_at:string};
type BulkItem = {filename:string; outcome:string; message?:string};
export default function Documents() {
  const [docs, setDocs] = useState<Doc[]>([]); const [message, setMessage] = useState(''); const [bulk, setBulk] = useState<BulkItem[]>([]);
  const token = () => localStorage.getItem('access_token') ?? '';
  async function load() { const r = await fetch(`${API}/api/v1/documents`, {headers:{Authorization:`Bearer ${token()}`}}); if (r.ok) setDocs(await r.json()); }
  useEffect(() => { load(); }, []);
  async function logout() {
    const r = await fetch(`${API}/api/v1/auth/logout`, {method:'POST', headers:{Authorization:`Bearer ${token()}`}});
    if (r.ok) { localStorage.removeItem('access_token'); window.location.href = '/login'; } else setMessage('Logout failed');
  }
  async function upload(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const fd = new FormData(e.currentTarget); const r = await fetch(`${API}/api/v1/documents`, {method:'POST', headers:{Authorization:`Bearer ${token()}`}, body:fd}); const b = await r.json().catch(()=>null); setMessage(r.ok ? `Queued ${b.original_filename}` : JSON.stringify(b?.detail ?? b)); if (r.ok) load();
  }
  async function bulkUpload(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const fd = new FormData(e.currentTarget); const r = await fetch(`${API}/api/v1/documents/bulk`, {method:'POST', headers:{Authorization:`Bearer ${token()}`}, body:fd}); const b = await r.json().catch(()=>null); if (r.ok) { setBulk(b.items); setMessage(`Queued ${b.queued_count}; ${b.failed_count} not queued.`); load(); } else setMessage('Bulk upload failed before item processing.');
  }
  return <><h1>Documents</h1><button onClick={logout}>Logout</button> <Link href="/security">Security</Link>
    <h2>Single upload</h2><form onSubmit={upload}><input name="file" type="file" accept="application/pdf,image/jpeg,image/png" required/><button>Upload</button></form>
    <h2>Bulk upload</h2><form onSubmit={bulkUpload}><input name="files" type="file" accept="application/pdf,image/jpeg,image/png" multiple required/><button>Upload selected files</button></form>
    <p>{message}</p>{bulk.map((i,idx)=><div className="card" key={`${i.filename}-${idx}`}><strong>{i.filename}</strong><div>{i.outcome}</div><div className="muted">{i.message}</div></div>)}
    {docs.map(d=><div className="card" key={d.id}><strong>{d.original_filename}</strong><div className="muted">{d.status} · {d.size_bytes} bytes</div></div>)}</>;
}
