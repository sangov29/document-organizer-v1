'use client';
import { FormEvent, useEffect, useState } from 'react';
import Link from 'next/link';
import { API } from '../../lib/api';
type Named = {id:string; name:string};
type Doc = {id:string; original_filename:string; status:string; size_bytes:number; uploaded_at:string; duplicate_of_document_id?:string|null; processing_stage?:string|null; processing_started_at?:string|null; processing_elapsed_seconds?:number|null; processing_active:boolean; processing_stalled:boolean; processing_message?:string|null; structured_field_count:number; extracted_value_count:number; tags:Named[]; collections:Named[]};
type Reminder = {document_id:string; original_filename:string; field_name:string; due_date:string; days_remaining:number; status:'overdue'|'due_soon'|'upcoming'};
type ReminderPreferences = {enabled:boolean; window_days:number};
type BulkItem = {filename:string; outcome:string; message?:string};
type UploadState = 'uploading'|'queued'|'duplicate'|'failed';
type UploadActivity = {id:string; filename:string; state:UploadState; message:string};
type PendingDuplicate = {file:File; activityId:string};
const familyOptions = ['identity','utility','banking','educational','employment','invoice_receipt','travel','unknown'];
const pretty = (value:string) => value.replaceAll('_',' ').replace(/\b\w/g, letter => letter.toUpperCase());
const formatBytes = (bytes:number) => bytes < 1024 ? `${bytes} B` : bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
const formatElapsed = (seconds?:number|null) => { if (seconds == null) return ''; const minutes = Math.floor(seconds / 60); return minutes < 1 ? 'less than a minute' : minutes === 1 ? '1 minute' : `${minutes} minutes`; };
const createUploadId = () => `${Date.now()}-${Math.random().toString(36).slice(2)}`;
export default function Documents() {
  const [docs, setDocs] = useState<Doc[]>([]); const [selected, setSelected] = useState<string[]>([]); const [message, setMessage] = useState(''); const [bulk, setBulk] = useState<BulkItem[]>([]); const [pendingDuplicate, setPendingDuplicate] = useState<PendingDuplicate|null>(null); const [uploadActivity, setUploadActivity] = useState<UploadActivity[]>([]); const [singleFileName, setSingleFileName] = useState(''); const [bulkFileNames, setBulkFileNames] = useState<string[]>([]); const [ready, setReady] = useState(false); const [query, setQuery] = useState(''); const [family, setFamily] = useState(''); const [fieldValue, setFieldValue] = useState(''); const [uploadedFrom, setUploadedFrom] = useState(''); const [uploadedTo, setUploadedTo] = useState(''); const [page, setPage] = useState(1); const [total, setTotal] = useState(0); const [tags, setTags] = useState<Named[]>([]); const [collections, setCollections] = useState<Named[]>([]); const [tagFilter, setTagFilter] = useState(''); const [collectionFilter, setCollectionFilter] = useState(''); const [reminders, setReminders] = useState<Reminder[]>([]); const [reminderPreferences, setReminderPreferences] = useState<ReminderPreferences>({enabled:true, window_days:90});
  const token = () => localStorage.getItem('access_token') ?? '';
  async function load(nextPage = page) {
    const accessToken = token();
    if (!accessToken) { window.location.href = '/login'; return; }
    const params = new URLSearchParams({page:String(nextPage), page_size:'10'}); if (query) params.set('q', query); if (family) params.set('family', family); if (fieldValue) params.set('field_value', fieldValue); if (tagFilter) params.set('tag_id', tagFilter); if (collectionFilter) params.set('collection_id', collectionFilter); if (uploadedFrom) params.set('uploaded_from', `${uploadedFrom}T00:00:00Z`); if (uploadedTo) params.set('uploaded_to', `${uploadedTo}T23:59:59Z`);
    const r = await fetch(`${API}/api/v1/documents/search?${params}`, {headers:{Authorization:`Bearer ${accessToken}`}});
    if (r.status === 401) { localStorage.removeItem('access_token'); window.location.href = '/login'; return; }
    if (r.ok) { const body = await r.json(); setDocs(body.items); setTotal(body.total); setPage(body.page); }
    else setMessage('Documents could not be loaded.');
  }
  async function loadOrganization() {
    const headers = {Authorization:`Bearer ${token()}`};
    const [tagResponse, collectionResponse] = await Promise.all([fetch(`${API}/api/v1/documents/tags`, {headers}), fetch(`${API}/api/v1/documents/collections`, {headers})]);
    if (tagResponse.ok) setTags(await tagResponse.json());
    if (collectionResponse.ok) setCollections(await collectionResponse.json());
  }
  async function loadReminders() {
    const headers = {Authorization:`Bearer ${token()}`};
    const [response, preferences] = await Promise.all([fetch(`${API}/api/v1/documents/reminders`, {headers}), fetch(`${API}/api/v1/documents/reminders/preferences`, {headers})]);
    if (response.ok) setReminders((await response.json()).items);
    if (preferences.ok) setReminderPreferences(await preferences.json());
  }
  async function saveReminderPreferences(e:FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const response = await fetch(`${API}/api/v1/documents/reminders/preferences`, {method:'PUT', headers:{Authorization:`Bearer ${token()}`, 'Content-Type':'application/json'}, body:JSON.stringify(reminderPreferences)});
    if (response.ok) { setReminderPreferences(await response.json()); setMessage('Reminder preferences saved.'); loadReminders(); }
    else setMessage('Reminder preferences could not be saved.');
  }
  useEffect(() => { setReady(true); loadOrganization(); loadReminders(); load(1); }, []);
  useEffect(() => {
    if (!docs.some(document => document.processing_active)) return;
    const timer = window.setTimeout(() => load(page), 5000);
    return () => window.clearTimeout(timer);
  }, [docs, page]);
  async function createNamed(kind:'tags'|'collections', form:HTMLFormElement) {
    const data = new FormData(form); const name = String(data.get('name') ?? '');
    const response = await fetch(`${API}/api/v1/documents/${kind}`, {method:'POST', headers:{Authorization:`Bearer ${token()}`, 'Content-Type':'application/json'}, body:JSON.stringify({name})});
    if (response.ok) { form.reset(); setMessage(`${kind === 'tags' ? 'Tag' : 'Collection'} created.`); loadOrganization(); }
    else setMessage(`${kind === 'tags' ? 'Tag' : 'Collection'} could not be created.`);
  }
  async function assign(kind:'tags'|'collections', documentId:string, resourceId:string) {
    if (!resourceId) return;
    const response = await fetch(`${API}/api/v1/documents/${documentId}/${kind}/${resourceId}`, {method:'PUT', headers:{Authorization:`Bearer ${token()}`}});
    if (response.ok) { setMessage(`${kind === 'tags' ? 'Tag' : 'Collection'} assigned.`); load(); }
    else setMessage('Assignment failed.');
  }
  async function logout() {
    const r = await fetch(`${API}/api/v1/auth/logout`, {method:'POST', headers:{Authorization:`Bearer ${token()}`}});
    if (r.ok) { localStorage.removeItem('access_token'); window.location.href = '/login'; } else setMessage('Logout failed');
  }
  async function upload(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const form = e.currentTarget; const fd = new FormData(form); const file = fd.get('file');
    if (!(file instanceof File) || !file.name) { setMessage('Choose a document first.'); return; }
    const activityId = createUploadId();
    setUploadActivity(current => [{id:activityId, filename:file.name, state:'uploading', message:'Uploading to the secure queue…'}, ...current]);
    form.reset(); setSingleFileName('');
    const r = await fetch(`${API}/api/v1/documents`, {method:'POST', headers:{Authorization:`Bearer ${token()}`}, body:fd}); const b = await r.json().catch(()=>null);
    if (r.ok) { setUploadActivity(current => current.map(item => item.id === activityId ? {...item,state:'queued',message:'Queued for background processing. You can upload another document now.'} : item)); setMessage(`Queued ${b.original_filename}`); load(); return; }
    if (r.status === 409 && b?.detail?.code === 'duplicate_document' && file instanceof File) {
      setPendingDuplicate({file,activityId}); setUploadActivity(current => current.map(item => item.id === activityId ? {...item,state:'duplicate',message:'Duplicate detected. Choose whether to keep another copy.'} : item)); setMessage('This exact document already exists. Keep another copy?'); return;
    }
    const detail = typeof b?.detail === 'string' ? b.detail : 'Upload failed.'; setUploadActivity(current => current.map(item => item.id === activityId ? {...item,state:'failed',message:detail} : item)); setMessage(detail);
  }
  async function keepDuplicate() {
    if (!pendingDuplicate) return;
    const {file,activityId} = pendingDuplicate; setPendingDuplicate(null); setUploadActivity(current => current.map(item => item.id === activityId ? {...item,state:'uploading',message:'Keeping another copy…'} : item));
    const fd = new FormData(); fd.set('file', file); fd.set('duplicate_action', 'keep');
    const r = await fetch(`${API}/api/v1/documents`, {method:'POST', headers:{Authorization:`Bearer ${token()}`}, body:fd}); const b = await r.json().catch(()=>null);
    if (r.ok) { setUploadActivity(current => current.map(item => item.id === activityId ? {...item,state:'queued',message:'Duplicate kept and queued for background processing.'} : item)); setMessage(`Kept duplicate ${b.original_filename}`); load(); }
    else { const detail = typeof b?.detail === 'string' ? b.detail : 'Duplicate could not be kept.'; setUploadActivity(current => current.map(item => item.id === activityId ? {...item,state:'failed',message:detail} : item)); setMessage(detail); }
  }
  async function bulkUpload(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const form = e.currentTarget; const fd = new FormData(form); const files = fd.getAll('files').filter((item): item is File => item instanceof File && Boolean(item.name));
    if (!files.length) { setMessage('Choose at least one document first.'); return; }
    const activities = files.map(file => ({id:createUploadId(),filename:file.name,state:'uploading' as const,message:'Uploading to the secure queue…'}));
    setUploadActivity(current => [...activities, ...current]); form.reset(); setBulkFileNames([]);
    const r = await fetch(`${API}/api/v1/documents/bulk`, {method:'POST', headers:{Authorization:`Bearer ${token()}`}, body:fd}); const b = await r.json().catch(()=>null);
    if (r.ok) {
      const remainingResults = new Map<string,BulkItem[]>(); for (const item of b.items as BulkItem[]) remainingResults.set(item.filename, [...(remainingResults.get(item.filename) ?? []), item]);
      const resultByActivityId = new Map<string,BulkItem>(); for (const activity of activities) { const matches = remainingResults.get(activity.filename) ?? []; const result = matches[0]; if (result) { resultByActivityId.set(activity.id, result); remainingResults.set(activity.filename, matches.slice(1)); } }
      setUploadActivity(current => current.map(item => { const result = resultByActivityId.get(item.id); if (!result) return item; const queued = result.outcome === 'queued'; return {...item,state:queued ? 'queued' : 'failed',message:queued ? 'Queued for background processing. You can upload more documents now.' : result.message || 'This file was not queued.'}; }));
      setBulk(b.items); setMessage(`Queued ${b.queued_count}; ${b.failed_count} not queued.`); load();
    } else { setUploadActivity(current => current.map(item => activities.some(activity => activity.id === item.id) ? {...item,state:'failed',message:'Bulk upload failed before item processing.'} : item)); setMessage('Bulk upload failed before item processing.'); }
  }
  async function exportSelected() {
    if (!selected.length) { setMessage('Select at least one document to export.'); return; }
    const r = await fetch(`${API}/api/v1/documents/batch/export.csv`, {method:'POST', headers:{Authorization:`Bearer ${token()}`, 'Content-Type':'application/json'}, body:JSON.stringify({document_ids:selected})});
    if (!r.ok) { setMessage('Selected documents could not be exported.'); return; }
    const url = URL.createObjectURL(await r.blob()); const a = document.createElement('a'); a.href = url; a.download = 'documents-export.csv'; a.click(); URL.revokeObjectURL(url); setMessage(`Exported ${selected.length} document${selected.length === 1 ? '' : 's'}.`);
  }
  async function deleteDocument(document:Doc) {
    if (!window.confirm(`Permanently delete ${document.original_filename} and its processed data? This cannot be undone.`)) return;
    const response = await fetch(`${API}/api/v1/documents/${document.id}`, {method:'DELETE', headers:{Authorization:`Bearer ${token()}`}});
    if (response.status === 204) {
      setSelected(current => current.filter(id => id !== document.id));
      setMessage(`Deleted ${document.original_filename}.`);
      await load(page);
      return;
    }
    setMessage(response.status === 503 ? 'Storage cleanup is temporarily unavailable. The document was not deleted; please retry.' : 'Document could not be deleted.');
  }
  const pageIds = docs.map(document => document.id);
  const allOnPageSelected = pageIds.length > 0 && pageIds.every(id => selected.includes(id));
  function togglePageSelection() {
    setSelected(current => allOnPageSelected
      ? current.filter(id => !pageIds.includes(id))
      : Array.from(new Set([...current, ...pageIds]))
    );
  }
  return <div className="dashboard"><div className="page-heading"><div><div className="eyebrow">Your private workspace</div><h1>Documents</h1><p className="muted">Upload, review and find your important documents.</p></div><button className="secondary compact" onClick={logout}>Logout</button></div>
    <div className="stats"><div><strong>{total}</strong><span>Total documents</span></div><div><strong>{docs.filter(d=>d.status === 'needs_review').length}</strong><span>Need review on this page</span></div><div><strong>{selected.length}</strong><span>Selected for export</span></div></div>
    <section className="upload-grid"><div className="panel"><span className="panel-kicker">Quick upload</span><h2>Add one document</h2><p className="muted">PDF, JPG or PNG. Uploading and processing continue in the background.</p><form onSubmit={upload}><label className="file-drop" htmlFor="single-file"><span>{singleFileName || 'Choose PDF, JPG or PNG'}</span><small>{singleFileName ? 'Ready to upload' : 'Select one document to process'}</small></label><input className="visually-hidden" id="single-file" name="file" type="file" accept="application/pdf,image/jpeg,image/png" onChange={event=>setSingleFileName(event.target.files?.[0]?.name ?? '')} required/><button disabled={!ready}>Upload</button></form></div>
    <div className="panel"><span className="panel-kicker">Batch import</span><h2>Add multiple files</h2><p className="muted">Upload a group while keeping failures isolated to each file.</p><form onSubmit={bulkUpload}><label className="file-drop"><span>{bulkFileNames.length ? `${bulkFileNames.length} document${bulkFileNames.length === 1 ? '' : 's'} selected` : 'Choose multiple documents'}</span><small>{bulkFileNames.length ? bulkFileNames.join(', ') : 'Each file is validated independently'}</small><input className="visually-hidden" name="files" type="file" accept="application/pdf,image/jpeg,image/png" onChange={event=>setBulkFileNames(Array.from(event.target.files ?? []).map(file=>file.name))} multiple required/></label><button disabled={!ready}>Upload selected files</button></form></div></section>
    {pendingDuplicate && <div className="card" role="alert"><strong>Duplicate detected</strong><div>This exact document already exists.</div><button onClick={keepDuplicate}>Keep another copy</button><button className="secondary" onClick={()=>{const activityId=pendingDuplicate.activityId;setPendingDuplicate(null);setUploadActivity(current=>current.map(item=>item.id===activityId?{...item,state:'failed',message:'Duplicate upload cancelled.'}:item));setMessage('Duplicate upload cancelled.');}}>Cancel</button></div>}
    {uploadActivity.length > 0 && <section className="panel" aria-label="Upload activity"><div className="section-heading"><div><span className="panel-kicker">Upload activity</span><h2>Current session</h2></div><button type="button" className="secondary compact" onClick={()=>setUploadActivity(current=>current.filter(item=>item.state==='uploading'||item.state==='duplicate'))}>Clear finished</button></div><p className="muted">You can choose and upload more files while these documents process.</p><div className="document-list">{uploadActivity.map(item=><article className="document-row" key={item.id}><div className="file-symbol" aria-hidden="true">UP</div><div className="document-main"><strong>{item.filename}</strong><div className="muted">{item.message}</div></div><span className={`status status-${item.state==='queued'?'processing':item.state}`}>{pretty(item.state)}</span></article>)}</div></section>}
    {message && <p className="notice" role="status">{message}</p>}{bulk.map((i,idx)=><div className="card" key={`${i.filename}-${idx}`}><strong>{i.filename}</strong><div>{i.outcome}</div><div className="muted">{i.message}</div></div>)}
    <section className="panel"><span className="panel-kicker">Dates requiring attention</span><h2>Reminders</h2><form className="reminder-preferences" onSubmit={saveReminderPreferences}><label><input type="checkbox" checked={reminderPreferences.enabled} onChange={e=>setReminderPreferences({...reminderPreferences,enabled:e.target.checked})}/> Show in-app reminders</label><label>Look ahead<select value={reminderPreferences.window_days} onChange={e=>setReminderPreferences({...reminderPreferences,window_days:Number(e.target.value)})} disabled={!reminderPreferences.enabled}>{[7,30,60,90,180,365].map(days=><option key={days} value={days}>{days} days</option>)}</select></label><button type="submit" className="secondary compact">Save reminder settings</button></form>{reminderPreferences.enabled && reminders.length === 0 && <p className="muted">No expiry or due dates need attention in this window.</p>}<div className="document-list">{reminders.map(item=><article className="document-row" key={`${item.document_id}-${item.field_name}`}><div className="file-symbol" aria-hidden="true">DATE</div><div className="document-main"><Link href={`/documents/${item.document_id}`}><strong>{item.original_filename}</strong></Link><div className="muted">{pretty(item.field_name)} · {item.due_date}</div></div><span className={`status status-${item.status}`}>{item.status === 'overdue' ? `${Math.abs(item.days_remaining)} days overdue` : item.days_remaining === 0 ? 'Due today' : `${item.days_remaining} days left`}</span></article>)}</div></section>
    <section className="upload-grid"><div className="panel"><span className="panel-kicker">Organize</span><h2>Create a tag</h2><form onSubmit={e=>{e.preventDefault();createNamed('tags', e.currentTarget);}}><label>Tag name<input name="name" maxLength={64} required/></label><button type="submit">Create tag</button></form></div><div className="panel"><span className="panel-kicker">Group</span><h2>Create a collection</h2><form onSubmit={e=>{e.preventDefault();createNamed('collections', e.currentTarget);}}><label>Collection name<input name="name" maxLength={100} required/></label><button type="submit">Create collection</button></form></div></section>
    <section className="library-section"><div className="section-heading"><div><span className="panel-kicker">Library</span><h2>Your documents</h2></div>{docs.length > 0 && <div><button type="button" className="secondary" onClick={togglePageSelection}>{allOnPageSelected ? 'Clear this page' : 'Select this page'}</button><button type="button" className="secondary" onClick={exportSelected}>Export selected CSV</button></div>}</div>
    <form onSubmit={e=>{e.preventDefault();load(1);}} className="filters"><label>Search document text<input aria-label="Search document text" value={query} placeholder="e.g. Acme Corporation" onChange={e=>setQuery(e.target.value)}/></label><label>Family<select aria-label="Filter by family" value={family} onChange={e=>setFamily(e.target.value)}><option value="">All families</option>{familyOptions.map(value=><option key={value} value={value}>{pretty(value)}</option>)}</select></label><label>Tag<select aria-label="Filter by tag" value={tagFilter} onChange={e=>setTagFilter(e.target.value)}><option value="">All tags</option>{tags.map(value=><option key={value.id} value={value.id}>{value.name}</option>)}</select></label><label>Collection<select aria-label="Filter by collection" value={collectionFilter} onChange={e=>setCollectionFilter(e.target.value)}><option value="">All collections</option>{collections.map(value=><option key={value.id} value={value.id}>{value.name}</option>)}</select></label><label>Search extracted values<input aria-label="Search field values" value={fieldValue} placeholder="e.g. invoice number" onChange={e=>setFieldValue(e.target.value)}/></label><label>Uploaded from<input type="date" value={uploadedFrom} onChange={e=>setUploadedFrom(e.target.value)}/></label><label>Uploaded to<input type="date" value={uploadedTo} onChange={e=>setUploadedTo(e.target.value)}/></label><button type="submit">Apply filters</button></form>
    <div className="document-list">{docs.map(d=><article className="document-row" data-testid="document-card" key={d.id}><label className="select-box"><input type="checkbox" aria-label={`Select ${d.original_filename}`} checked={selected.includes(d.id)} onChange={event => setSelected(current => event.target.checked ? Array.from(new Set([...current, d.id])) : current.filter(id => id !== d.id))}/></label><div className="file-symbol" aria-hidden="true">DOC</div><div className="document-main"><Link href={`/documents/${d.id}`}><strong>{d.original_filename}</strong></Link><div className="muted">{new Date(d.uploaded_at).toLocaleDateString()} · {formatBytes(d.size_bytes)}{d.duplicate_of_document_id ? ' · Kept duplicate' : ''}</div>{(d.processing_active || d.status === 'failed') && <div className={d.processing_stalled || d.status === 'failed' ? 'notice' : 'muted'}>{d.processing_stage ? `${pretty(d.processing_stage)} · ` : ''}{d.processing_stalled ? 'Taking longer than expected' : d.status === 'failed' ? 'Processing failed' : 'In progress'}{d.processing_elapsed_seconds != null ? ` for ${formatElapsed(d.processing_elapsed_seconds)}` : ''}. {d.processing_message}</div>}{!d.processing_active && d.status !== 'failed' && <div className={d.extracted_value_count === 0 ? 'notice' : 'muted'}>{d.structured_field_count === 0 ? 'Processing complete · no structured extraction fields are available.' : d.extracted_value_count === 0 ? 'Processing complete · no field values were extracted.' : `${d.extracted_value_count} field value${d.extracted_value_count === 1 ? '' : 's'} extracted.`}</div>}<div className="muted">{d.tags.map(item=>`#${item.name}`).join(' ')}{d.collections.length ? ` · ${d.collections.map(item=>item.name).join(', ')}` : ''}</div><div><select aria-label={`Assign tag to ${d.original_filename}`} defaultValue="" onChange={e=>{assign('tags', d.id, e.target.value); e.target.value='';}}><option value="">Add tag…</option>{tags.filter(item=>!d.tags.some(existing=>existing.id===item.id)).map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select><select aria-label={`Assign collection to ${d.original_filename}`} defaultValue="" onChange={e=>{assign('collections', d.id, e.target.value); e.target.value='';}}><option value="">Add to collection…</option>{collections.filter(item=>!d.collections.some(existing=>existing.id===item.id)).map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select></div></div><span className={`status status-${d.processing_stalled ? 'stalled' : d.status}`}>{d.processing_stalled ? 'Taking longer' : pretty(d.status)}</span><button type="button" className="danger compact" onClick={()=>deleteDocument(d)}>Delete</button><span className="row-arrow" aria-hidden="true">→</span></article>)}</div>
    {docs.length === 0 && <div className="empty-state"><span>◎</span><h3>No documents found</h3><p>Upload your first document or adjust the filters above.</p></div>}
    <div className="pagination"><p>{total} document{total === 1 ? '' : 's'} · Page {page}</p><div><button className="secondary" type="button" disabled={page === 1} onClick={()=>load(page-1)}>Previous</button><button className="secondary" type="button" disabled={page*10 >= total} onClick={()=>load(page+1)}>Next</button></div></div></section></div>;
}
