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

  const formatStatus = (value:string) => value.replaceAll('_', ' ').replace(/\b\w/g, letter => letter.toUpperCase());
  const formatSize = (bytes:number) => bytes < 1024 ? `${bytes} B` : bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;

  return <div className="detail-page"><Link className="back-link" href="/documents">← Back to documents</Link>
    <div className="page-heading detail-heading"><div><p className="eyebrow">Review workspace</p><h1>Document details</h1><p className="muted">Inspect classification, verify extracted fields and trace every result.</p></div>{document && <button type="button" className="secondary" onClick={downloadJson}>Download JSON</button>}</div>
    {message && <p role="status" className="notice">{message}</p>}
    {document && <div className="document-summary" data-testid="document-detail">
      <div className="summary-title"><span className="file-symbol large">DOC</span><div><h2>{document.original_filename}</h2><div className="summary-chips"><span className={`status status-${document.status}`}>{formatStatus(document.status)}</span>{document.duplicate_of_document_id && <span className="status">Kept duplicate</span>}</div></div></div>
      <dl className="metadata-grid"><div><dt>File type</dt><dd>{document.mime_type}</dd></div><div><dt>File size</dt><dd>{formatSize(document.size_bytes)}</dd></div><div><dt>Uploaded</dt><dd>{new Date(document.uploaded_at).toLocaleString()}</dd></div><div className="wide"><dt>SHA-256 fingerprint</dt><dd className="hash">{document.sha256}</dd></div>{document.duplicate_of_document_id && <div className="wide"><dt>Canonical document</dt><dd className="hash">{document.duplicate_of_document_id}</dd></div>}</dl>
    </div>}
    {analysis && <section aria-labelledby="analysis-heading">
      <div className="section-heading analysis-title"><div><p className="eyebrow">AI results</p><h2 id="analysis-heading">Document analysis</h2></div><span className="analysis-count">{analysis.fields.length} fields found</span></div>
      <div className="classification-card" data-testid="classification">
        <div><p className="panel-kicker">Classification</p><h3>{formatStatus(analysis.classification.family)}</h3><p className="muted">{analysis.classification.review_required ? 'Review required before confirming fields' : 'Ready for field review'}</p></div>
        <div className="confidence"><strong>{Math.round(analysis.classification.confidence * 100)}%</strong><span>confidence</span></div>
        <details><summary>Classification provenance</summary><p>{analysis.classification.provider} · {analysis.classification.model_version} · {analysis.classification.method}</p></details>
        {analysis.classification.review_required && <div className="review-alert" role="alert"><p>This classification is ambiguous and must be reviewed before fields can be approved.</p><button type="button" onClick={confirmClassification}>Confirm {analysis.classification.family}</button></div>}
      </div>
      <div className="section-heading fields-heading"><div><p className="eyebrow">Structured data</p><h3>Extracted fields</h3></div><p className="muted">Confirm accurate values or save a correction.</p></div>
      <div className="field-list">{analysis.fields.map(field => <article className="field-card" data-testid={`field-${field.field_name}`} key={field.id}>
        <div className="field-header"><div><h4>{formatStatus(field.field_name)}</h4><div className="summary-chips"><span className={`trust trust-${field.trust_state}`}>{formatStatus(field.trust_state)}</span><span className="trust">{formatStatus(field.criticality)}</span>{field.confidence != null && <span className="trust">{Math.round(field.confidence * 100)}% confidence</span>}</div></div>{field.sensitive && <span className="privacy-chip">Sensitive</span>}</div>
        <p className={`field-value ${field.masked && !revealedFields[field.id] ? 'masked-value' : ''}`}><strong>{revealedFields[field.id] ?? field.value ?? 'Not found'}</strong>{field.masked && !revealedFields[field.id] && ' (masked)'}</p>
        {field.sensitive && <button className="secondary compact" type="button" onClick={() => revealField(field)}>Reveal {field.field_name.replaceAll('_', ' ')}</button>}
        <div className="review-controls"><label>Correct {field.field_name}<input aria-label={`Correct ${field.field_name}`} placeholder={field.sensitive ? 'Enter replacement value' : ''} value={drafts[field.id] ?? (field.sensitive ? '' : field.value ?? '')} onChange={event => setDrafts({...drafts, [field.id]:event.target.value})}/></label><div><button type="button" disabled={analysis.classification.review_required} onClick={() => reviewField(field, 'correct')}>Save correction</button><button className="secondary" type="button" disabled={analysis.classification.review_required} onClick={() => reviewField(field, 'confirm')}>Confirm</button></div></div>
        <details><summary>Provenance</summary><p>{field.provenance.provider} · {field.provenance.model_version} · {field.provenance.method}</p><p className="hash">Page: {field.provenance.source_page_id ?? 'document level'} · Region: {field.provenance.visual_region_id ?? 'not recorded'}</p></details>
        {field.corrections.length > 0 && <div className="history"><h5>Correction history</h5><ul>{field.corrections.map(correction => <li key={correction.id}>{correction.prior_value ?? 'Not found'} → {correction.corrected_value} · {new Date(correction.created_at).toLocaleString()}</li>)}</ul></div>}
      </article>)}</div>
      {analysis.sensitive_regions.length > 0 && <div className="sensitive-section" data-testid="sensitive-regions"><div className="section-heading"><div><p className="eyebrow">Protected content</p><h3>Sensitive regions</h3></div><p className="muted">Reveals are temporary and audited.</p></div><div className="region-grid">{analysis.sensitive_regions.map(region => <article className="region-card" data-testid={`region-${region.region_type}`} key={region.id}>
        <div className="field-header"><h4>{formatStatus(region.region_type)}</h4><span className="privacy-chip">Concealed</span></div>
        {revealedRegions[region.id]
          ? <img src={revealedRegions[region.id]} alt={`Temporarily revealed ${region.region_type}`} />
          : <div className="concealed"><span>••••••••</span><small>Sensitive region concealed</small></div>}
        <button type="button" onClick={() => revealRegion(region)}>Reveal {region.region_type.replaceAll('_', ' ')}</button>
      </article>)}</div></div>}
    </section>}
  </div>;
}
