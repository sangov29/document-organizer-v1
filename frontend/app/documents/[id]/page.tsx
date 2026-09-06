'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { API } from '../../../lib/api';

type Doc = {
  id:string; original_filename:string; mime_type:string; status:string;
  size_bytes:number; sha256:string; uploaded_at:string; duplicate_of_document_id?:string|null;
};

type Provenance = {
  id:string;
  source_document_id:string; source_page_id?:string|null; visual_region_id?:string|null;
  provider:string; model_version:string; method:string; confidence?:number|null; processed_at:string;
};

type Correction = {
  id:string; prior_value?:string|null; corrected_value:string; user_id:string;
  prior_provenance_id?:string|null; created_at:string;
};

type ExtractedField = {
  id:string; field_name:string; value?:string|null; confidence?:number|null;
  trust_state:string; criticality:string; schema_version?:string|null;
  provenance:Provenance; corrections:Correction[]; sensitive:boolean;
  sensitivity_type?:string|null; masked:boolean;
};

type SensitiveRegion = {
  id:string; region_type:string; sensitivity_type:string;
  bbox:{x:number;y:number;width:number;height:number}; concealed:boolean;
};

type Analysis = {
  document_id:string;
  classification:{family:string; confidence:number; provider:string; model_version:string; method:string; configured_threshold:number; review_required:boolean; reviewed_at?:string|null; provenance:Provenance};
  fields:ExtractedField[];
  sensitive_regions:SensitiveRegion[];
};

export default function DocumentDetail() {
  const params = useParams<{id:string}>();
  const [document, setDocument] = useState<Doc|null>(null);
  const [analysis, setAnalysis] = useState<Analysis|null>(null);
  const [drafts, setDrafts] = useState<Record<string,string>>({});
  const [revealedFields, setRevealedFields] = useState<Record<string,string>>({});
  const [revealedRegions, setRevealedRegions] = useState<Record<string,string>>({});
  const [message, setMessage] = useState('Loading document…');

  useEffect(() => {
    async function load() {
      const token = localStorage.getItem('access_token');
      if (!token) { window.location.href = '/login'; return; }
      const response = await fetch(`${API}/api/v1/documents/${params.id}`, {headers:{Authorization:`Bearer ${token}`}});
      if (response.status === 401) { localStorage.removeItem('access_token'); window.location.href = '/login'; return; }
      if (response.status === 404) { setMessage('Document not found.'); return; }
      if (!response.ok) { setMessage('Document could not be loaded.'); return; }
      setDocument(await response.json());
      for (let attempt = 0; attempt < 30; attempt += 1) {
        const analysisResponse = await fetch(`${API}/api/v1/documents/${params.id}/analysis`, {headers:{Authorization:`Bearer ${token}`}});
        if (analysisResponse.ok) {
          setAnalysis(await analysisResponse.json());
          setMessage('');
          return;
        }
        if (analysisResponse.status !== 202) {
          setMessage('Document analysis could not be loaded.');
          return;
        }
        setMessage('Document analysis is still processing…');
        await new Promise(resolve => setTimeout(resolve, 1000));
      }
      setMessage('Document analysis is still processing. Refresh this page shortly.');
    }
    load();
  }, [params.id]);

  async function reviewField(field: ExtractedField, action: 'confirm'|'correct') {
    const token = localStorage.getItem('access_token');
    if (!token) { window.location.href = '/login'; return; }
    const response = await fetch(`${API}/api/v1/documents/${params.id}/fields/${field.id}/review`, {
      method: 'POST',
      headers: {Authorization:`Bearer ${token}`, 'Content-Type':'application/json'},
      body: JSON.stringify(action === 'correct' ? {action, value: drafts[field.id] ?? field.value ?? ''} : {action}),
    });
    if (!response.ok) { setMessage('Field review could not be saved.'); return; }
    setAnalysis(await response.json());
    setMessage(action === 'correct' ? 'Correction saved.' : 'Field confirmed.');
  }

  async function confirmClassification() {
    const token = localStorage.getItem('access_token');
    if (!token) { window.location.href = '/login'; return; }
    const response = await fetch(`${API}/api/v1/documents/${params.id}/classification/review`, {method:'POST', headers:{Authorization:`Bearer ${token}`, 'Content-Type':'application/json'}, body:JSON.stringify({action:'confirm'})});
    if (!response.ok) { setMessage('Classification review could not be saved.'); return; }
    setAnalysis(await response.json()); setMessage('Classification confirmed.');
  }

  async function revealField(field: ExtractedField) {
    const token = localStorage.getItem('access_token');
    if (!token) { window.location.href = '/login'; return; }
    const response = await fetch(`${API}/api/v1/documents/${params.id}/fields/${field.id}/reveal`, {method:'POST', headers:{Authorization:`Bearer ${token}`}, cache:'no-store'});
    if (!response.ok) { setMessage('Sensitive value could not be revealed.'); return; }
    const result = await response.json();
    setRevealedFields({...revealedFields, [field.id]:result.revealed_value});
    setMessage('Sensitive value temporarily revealed.');
  }

  async function revealRegion(region: SensitiveRegion) {
    const token = localStorage.getItem('access_token');
    if (!token) { window.location.href = '/login'; return; }
    const response = await fetch(`${API}/api/v1/documents/${params.id}/regions/${region.id}/reveal`, {method:'POST', headers:{Authorization:`Bearer ${token}`}, cache:'no-store'});
    if (!response.ok) { setMessage('Sensitive region could not be revealed.'); return; }
    const result = await response.json();
    setRevealedRegions({...revealedRegions, [region.id]:`data:${result.media_type};base64,${result.content_base64}`});
    setMessage('Sensitive region temporarily revealed.');
  }

  async function downloadJson() {
    const token = localStorage.getItem('access_token');
    if (!token) { window.location.href = '/login'; return; }
    const response = await fetch(`${API}/api/v1/documents/${params.id}/export.json`, {headers:{Authorization:`Bearer ${token}`}, cache:'no-store'});
    if (!response.ok) { setMessage('Document export could not be created.'); return; }
    const url = URL.createObjectURL(await response.blob()); const a = window.document.createElement('a'); a.href = url; a.download = `document-${params.id}.json`; a.click(); URL.revokeObjectURL(url); setMessage('JSON export downloaded.');
  }

  return <><p><Link href="/documents">← Back to documents</Link></p><h1>Document details</h1>
    <p role="status">{message}</p>
    {document && <div className="card" data-testid="document-detail">
      <h2>{document.original_filename}</h2>
      <p><button type="button" onClick={downloadJson}>Download JSON</button></p>
      {document.duplicate_of_document_id && <p><strong>Kept duplicate</strong></p>}
      <dl><dt>Status</dt><dd>{document.status}</dd><dt>Type</dt><dd>{document.mime_type}</dd><dt>Size</dt><dd>{document.size_bytes} bytes</dd><dt>Uploaded</dt><dd>{new Date(document.uploaded_at).toLocaleString()}</dd><dt>SHA-256</dt><dd className="hash">{document.sha256}</dd>{document.duplicate_of_document_id && <><dt>Duplicate of</dt><dd className="hash">{document.duplicate_of_document_id}</dd></>}</dl>
    </div>}
    {analysis && <section aria-labelledby="analysis-heading">
      <h2 id="analysis-heading">Document analysis</h2>
      <div className="card" data-testid="classification">
        <h3>Classification</h3>
        <p><strong>{analysis.classification.family}</strong> · {Math.round(analysis.classification.confidence * 100)}% confidence</p>
        <details><summary>Classification provenance</summary><p>{analysis.classification.provider} · {analysis.classification.model_version} · {analysis.classification.method}</p></details>
        {analysis.classification.review_required && <div role="alert"><p>This classification is ambiguous and must be reviewed before fields can be approved.</p><button type="button" onClick={confirmClassification}>Confirm {analysis.classification.family}</button></div>}
      </div>
      <h3>Extracted fields</h3>
      {analysis.fields.map(field => <article className="card" data-testid={`field-${field.field_name}`} key={field.id}>
        <h4>{field.field_name.replaceAll('_', ' ')}</h4>
        <p><strong>{revealedFields[field.id] ?? field.value ?? 'Not found'}</strong>{field.masked && !revealedFields[field.id] && ' (masked)'}</p>
        <p>{field.trust_state} · {field.criticality}{field.confidence == null ? '' : ` · ${Math.round(field.confidence * 100)}% confidence`}</p>
        {field.sensitive && <p><button type="button" onClick={() => revealField(field)}>Reveal {field.field_name.replaceAll('_', ' ')}</button></p>}
        <label>Correct {field.field_name}<input aria-label={`Correct ${field.field_name}`} placeholder={field.sensitive ? 'Enter replacement value' : ''} value={drafts[field.id] ?? (field.sensitive ? '' : field.value ?? '')} onChange={event => setDrafts({...drafts, [field.id]:event.target.value})}/></label>
        <button type="button" disabled={analysis.classification.review_required} onClick={() => reviewField(field, 'correct')}>Save correction</button>{' '}
        <button type="button" disabled={analysis.classification.review_required} onClick={() => reviewField(field, 'confirm')}>Confirm</button>
        <details><summary>Provenance</summary><p>{field.provenance.provider} · {field.provenance.model_version} · {field.provenance.method}</p><p className="hash">Page: {field.provenance.source_page_id ?? 'document level'} · Region: {field.provenance.visual_region_id ?? 'not recorded'}</p></details>
        {field.corrections.length > 0 && <div><h5>Correction history</h5><ul>{field.corrections.map(correction => <li key={correction.id}>{correction.prior_value ?? 'Not found'} → {correction.corrected_value} · {new Date(correction.created_at).toLocaleString()}</li>)}</ul></div>}
      </article>)}
      {analysis.sensitive_regions.length > 0 && <div data-testid="sensitive-regions"><h3>Sensitive regions</h3>{analysis.sensitive_regions.map(region => <article className="card" data-testid={`region-${region.region_type}`} key={region.id}>
        <h4>{region.region_type.replaceAll('_', ' ')}</h4>
        {revealedRegions[region.id]
          ? <img src={revealedRegions[region.id]} alt={`Temporarily revealed ${region.region_type}`} />
          : <p className="concealed">Sensitive region concealed</p>}
        <button type="button" onClick={() => revealRegion(region)}>Reveal {region.region_type.replaceAll('_', ' ')}</button>
      </article>)}</div>}
    </section>}
  </>;
}
