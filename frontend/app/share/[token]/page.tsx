'use client';
import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { API } from '../../../lib/api';

type SharedField = {field_name:string;value?:string|null;trust_state:string;sensitive:boolean;masked:boolean};
type SharedDocument = {original_filename:string;family:string;version_number:number;expires_at:string;fields:SharedField[]};

export default function SharedDocumentPage() {
  const params = useParams<{token:string}>();
  const [document,setDocument] = useState<SharedDocument|null>(null);
  const [message,setMessage] = useState('Loading shared document…');
  useEffect(()=>{(async()=>{
    const response=await fetch(`${API}/api/v1/shares/${params.token}`,{cache:'no-store'});
    if(!response.ok){setMessage('This share link is invalid, expired or revoked.');return;}
    setDocument(await response.json());setMessage('');
  })();},[params.token]);
  const pretty=(value:string)=>value.replaceAll('_',' ').replace(/\b\w/g,letter=>letter.toUpperCase());
  return <div className="auth-single"><section className="auth-card shared-card"><p className="eyebrow">Read-only shared document</p>{message&&<p role="status" className="notice">{message}</p>}{document&&<><h1>{document.original_filename}</h1><div className="summary-chips"><span className="status">{pretty(document.family)}</span><span className="status">Version {document.version_number}</span></div><p className="muted">Access expires {new Date(document.expires_at).toLocaleString()}. Sensitive values remain masked.</p><div className="field-list">{document.fields.map(field=><article className="field-card" key={field.field_name}><div className="field-header"><h4>{pretty(field.field_name)}</h4>{field.sensitive&&<span className="privacy-chip">Masked</span>}</div><p className="field-value"><strong>{field.value??'Not found'}</strong></p><span className={`trust trust-${field.trust_state}`}>{pretty(field.trust_state)}</span></article>)}</div></>}</section></div>;
}
