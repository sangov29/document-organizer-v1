'use client';
import { FormEvent, useEffect, useState } from 'react';
import Link from 'next/link';
import { API } from '../../lib/api';
type Doc = {id:string; original_filename:string; status:string; size_bytes:number; uploaded_at:string; duplicate_of_document_id?:string|null};
type BulkItem = {filename:string; outcome:string; message?:string};
const familyOptions = ['identity','utility','banking','educational','employment','invoice_receipt','travel','unknown'];
const pretty = (value:string) => value.replaceAll('_',' ').replace(/\b\w/g, letter => letter.toUpperCase());
const formatBytes = (bytes:number) => bytes < 1024 ? `${bytes} B` : bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
export default function Documents() {
  const [docs, setDocs] = useState<Doc[]>([]); const [selected, setSelected] = useState<string[]>([]); const [message, setMessage] = useState(''); const [bulk, setBulk] = useState<BulkItem[]>([]); const [pendingDuplicate, setPendingDuplicate] = useState<File|null>(null); const [ready, setReady] = useState(false); const [family, setFamily] = useState(''); const [fieldValue, setFieldValue] = useState(''); const [uploadedFrom, setUploadedFrom] = useState(''); const [uploadedTo, setUploadedTo] = useState(''); const [page, setPage] = useState(1); const [total, setTotal] = useState(0);
  const token = () => localStorage.getItem('access_token') ?? '';
  async function load(nextPage = page) {
    const accessToken = token();
    if (!accessToken) { window.location.href = '/login'; return; }
    const params = new URLSearchParams({page:String(nextPage), page_size:'10'}); if (family) params.set('family', family); if (fieldValue) params.set('field_value', fieldValue); if (uploadedFrom) params.set('uploaded_from', `${uploadedFrom}T00:00:00Z`); if (uploadedTo) params.set('uploaded_to', `${uploadedTo}T23:59:59Z`);
    const r = await fetch(`${API}/api/v1/documents/search?${params}`, {headers:{Authorization:`Bearer ${accessToken}`}});
    if (r.status === 401) { localStorage.removeItem('access_token'); window.location.href = '/login'; return; }
    if (r.ok) { const body = await r.json(); setDocs(body.items); setTotal(body.total); setPage(body.page); setSelected([]); }
    else setMessage('Documents could not be loaded.');
  }
  useEffect(() => { setReady(true); load(1); }, []);
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
  return <div className="dashboard"><div className="page-heading"><div><div className="eyebrow">Your private workspace</div><h1>Documents</h1><p className="muted">Upload, review and find your important documents.</p></div><button className="secondary compact" onClick={logout}>Logout</button></div>
    <div className="stats"><div><strong>{total}</strong><span>Total documents</span></div><div><strong>{docs.filter(d=>d.status === 'needs_review').length}</strong><span>Need review on this page</span></div><div><strong>{selected.length}</strong><span>Selected for export</span></div></div>
    <section className="upload-grid"><div className="panel"><span className="panel-kicker">Quick upload</span><h2>Add one document</h2><p className="muted">PDF, JPG or PNG. Processing runs securely in the background.</p><form onSubmit={upload}><label className="file-drop" htmlFor="single-file"><span>Choose PDF, JPG or PNG</span><small>Select one document to process</small></label><input className="visually-hidden" id="single-file" name="file" type="file" accept="application/pdf,image/jpeg,image/png" required/><button disabled={!ready}>Upload</button></form></div>
    <div className="panel"><span className="panel-kicker">Batch import</span><h2>Add multiple files</h2><p className="muted">Upload a group while keeping failures isolated to each file.</p><form onSubmit={bulkUpload}><label className="file-drop"><span>Choose multiple documents</span><small>Each file is validated independently</small><input className="visually-hidden" name="files" type="file" accept="application/pdf,image/jpeg,image/png" multiple required/></label><button disabled={!ready}>Upload selected files</button></form></div></section>
    {pendingDuplicate && <div className="card" role="alert"><strong>Duplicate detected</strong><div>This exact document already exists.</div><button onClick={keepDuplicate}>Keep another copy</button><button className="secondary" onClick={()=>{setPendingDuplicate(null);setMessage('Duplicate upload cancelled.');}}>Cancel</button></div>}
    {message && <p className="notice" role="status">{message}</p>}{bulk.map((i,idx)=><div className="card" key={`${i.filename}-${idx}`}><strong>{i.filename}</strong><div>{i.outcome}</div><div className="muted">{i.message}</div></div>)}
    <section className="library-section"><div className="section-heading"><div><span className="panel-kicker">Library</span><h2>Your documents</h2></div>{docs.length > 0 && <button type="button" className="secondary" onClick={exportSelected}>Export selected CSV</button>}</div>
    <form onSubmit={e=>{e.preventDefault();load(1);}} className="filters"><label>Family<select aria-label="Filter by family" value={family} onChange={e=>setFamily(e.target.value)}><option value="">All families</option>{familyOptions.map(value=><option key={value} value={value}>{pretty(value)}</option>)}</select></label><label>Search extracted values<input aria-label="Search field values" value={fieldValue} placeholder="e.g. invoice number" onChange={e=>setFieldValue(e.target.value)}/></label><label>Uploaded from<input type="date" value={uploadedFrom} onChange={e=>setUploadedFrom(e.target.value)}/></label><label>Uploaded to<input type="date" value={uploadedTo} onChange={e=>setUploadedTo(e.target.value)}/></label><button type="submit">Apply filters</button></form>
    <div className="document-list">{docs.map(d=><article className="document-row" data-testid="document-card" key={d.id}><label className="select-box"><input type="checkbox" aria-label={`Select ${d.original_filename}`} checked={selected.includes(d.id)} onChange={event => setSelected(event.target.checked ? [...selected, d.id] : selected.filter(id => id !== d.id))}/></label><div className="file-symbol" aria-hidden="true">DOC</div><div className="document-main"><Link href={`/documents/${d.id}`}><strong>{d.original_filename}</strong></Link><div className="muted">{new Date(d.uploaded_at).toLocaleDateString()} · {formatBytes(d.size_bytes)}{d.duplicate_of_document_id ? ' · Kept duplicate' : ''}</div></div><span className={`status status-${d.status}`}>{pretty(d.status)}</span><Link className="row-arrow" aria-label={`Open ${d.original_filename}`} href={`/documents/${d.id}`}>→</Link></article>)}</div>
    {docs.length === 0 && <div className="empty-state"><span>◎</span><h3>No documents found</h3><p>Upload your first document or adjust the filters above.</p></div>}
    <div className="pagination"><p>{total} document{total === 1 ? '' : 's'} · Page {page}</p><div><button className="secondary" type="button" disabled={page === 1} onClick={()=>load(page-1)}>Previous</button><button className="secondary" type="button" disabled={page*10 >= total} onClick={()=>load(page+1)}>Next</button></div></div></section></div>;
}
