'use client';
import { FormEvent, useEffect, useState } from 'react';
import Link from 'next/link';
import { API } from '../../lib/api';
type Doc = {id:string; original_filename:string; status:string; size_bytes:number; uploaded_at:string; duplicate_of_document_id?:string|null};
type BulkItem = {filename:string; outcome:string; message?:string};
export default function Documents() {
  const [docs, setDocs] = useState<Doc[]>([]); const [selected, setSelected] = useState<string[]>([]); const [message, setMessage] = useState(''); const [bulk, setBulk] = useState<BulkItem[]>([]); const [pendingDuplicate, setPendingDuplicate] = useState<File|null>(null); const [ready, setReady] = useState(false);
  const token = () => localStorage.getItem('access_token') ?? '';
  async function load() {
    const accessToken = token();
    if (!accessToken) { window.location.href = '/login'; return; }
    const r = await fetch(`${API}/api/v1/documents`, {headers:{Authorization:`Bearer ${accessToken}`}});
    if (r.status === 401) { localStorage.removeItem('access_token'); window.location.href = '/login'; return; }
    if (r.ok) setDocs(await r.json());
    else setMessage('Documents could not be loaded.');
  }
  useEffect(() => { setReady(true); load(); }, []);
  async function logout() {
    const r = await fetch(`${API}/api/v1/auth/logout`, {method:'POST', headers:{Authorization:`Bearer ${token()}`}});
    if (r.ok) { localStorage.removeItem('access_token'); window.location.href = '/login'; } else setMessage('Logout failed');
  }
  async function upload(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const form = e.currentTarget; const fd = new FormData(form); const file = fd.get('file');
    const r = await fetch(`${API}/api/v1/documents`, {method:'POST', headers:{Authorization:`Bearer ${token()}`}, body:fd}); const b = await r.json().catch(()=>null);
    if (r.ok) { setPendingDuplicate(null); setMessage(`Queued ${b.original_filename}`); form.reset(); load(); return; }
    if (r.status === 409 && b?.detail?.code === 'duplicate_document' && file instanceof File) {
      setPendingDuplicate(file); setMessage('This exact document already exists. Keep another copy?'); return;
    }
    setPendingDuplicate(null); setMessage(typeof b?.detail === 'string' ? b.detail : 'Upload failed.');
  }
  async function keepDuplicate() {
    if (!pendingDuplicate) return;
    const fd = new FormData(); fd.set('file', pendingDuplicate); fd.set('duplicate_action', 'keep');
    const r = await fetch(`${API}/api/v1/documents`, {method:'POST', headers:{Authorization:`Bearer ${token()}`}, body:fd}); const b = await r.json().catch(()=>null);
    if (r.ok) { setMessage(`Kept duplicate ${b.original_filename}`); setPendingDuplicate(null); load(); }
    else setMessage(typeof b?.detail === 'string' ? b.detail : 'Duplicate could not be kept.');
  }
  async function bulkUpload(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const fd = new FormData(e.currentTarget); const r = await fetch(`${API}/api/v1/documents/bulk`, {method:'POST', headers:{Authorization:`Bearer ${token()}`}, body:fd}); const b = await r.json().catch(()=>null); if (r.ok) { setBulk(b.items); setMessage(`Queued ${b.queued_count}; ${b.failed_count} not queued.`); load(); } else setMessage('Bulk upload failed before item processing.');
  }
  async function exportSelected() {
    if (!selected.length) { setMessage('Select at least one document to export.'); return; }
    const r = await fetch(`${API}/api/v1/documents/batch/export.csv`, {method:'POST', headers:{Authorization:`Bearer ${token()}`, 'Content-Type':'application/json'}, body:JSON.stringify({document_ids:selected})});
    if (!r.ok) { setMessage('Selected documents could not be exported.'); return; }
    const url = URL.createObjectURL(await r.blob()); const a = document.createElement('a'); a.href = url; a.download = 'documents-export.csv'; a.click(); URL.revokeObjectURL(url); setMessage(`Exported ${selected.length} document${selected.length === 1 ? '' : 's'}.`);
  }
  return <><h1>Documents</h1><button onClick={logout}>Logout</button> <Link href="/security">Security</Link>
    <h2>Single upload</h2><form onSubmit={upload}><label htmlFor="single-file">Choose PDF, JPG or PNG</label><input id="single-file" name="file" type="file" accept="application/pdf,image/jpeg,image/png" required/><button disabled={!ready}>Upload</button></form>
    {pendingDuplicate && <div className="card" role="alert"><strong>Duplicate detected</strong><div>This exact document already exists.</div><button onClick={keepDuplicate}>Keep another copy</button><button className="secondary" onClick={()=>{setPendingDuplicate(null);setMessage('Duplicate upload cancelled.');}}>Cancel</button></div>}
    <h2>Bulk upload</h2><form onSubmit={bulkUpload}><input name="files" type="file" accept="application/pdf,image/jpeg,image/png" multiple required/><button disabled={!ready}>Upload selected files</button></form>
    <p role="status">{message}</p>{bulk.map((i,idx)=><div className="card" key={`${i.filename}-${idx}`}><strong>{i.filename}</strong><div>{i.outcome}</div><div className="muted">{i.message}</div></div>)}
    <h2>Your documents</h2>{docs.length > 0 && <p><button type="button" onClick={exportSelected}>Export selected CSV</button></p>}{docs.map(d=><div className="card" data-testid="document-card" key={d.id}><label><input type="checkbox" aria-label={`Select ${d.original_filename}`} checked={selected.includes(d.id)} onChange={event => setSelected(event.target.checked ? [...selected, d.id] : selected.filter(id => id !== d.id))}/> Select for export</label><br/><Link href={`/documents/${d.id}`}><strong>{d.original_filename}</strong></Link><div className="muted">{d.status} · {d.size_bytes} bytes{d.duplicate_of_document_id ? ' · kept duplicate' : ''}</div></div>)}</>;
}
