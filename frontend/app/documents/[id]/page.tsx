'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { API } from '../../../lib/api';

type Doc = {
  id:string; original_filename:string; mime_type:string; status:string;
  size_bytes:number; sha256:string; uploaded_at:string; duplicate_of_document_id?:string|null;
};

export default function DocumentDetail() {
  const params = useParams<{id:string}>();
  const [document, setDocument] = useState<Doc|null>(null);
  const [message, setMessage] = useState('Loading document…');

  useEffect(() => {
    async function load() {
      const token = localStorage.getItem('access_token');
      if (!token) { window.location.href = '/login'; return; }
      const response = await fetch(`${API}/api/v1/documents/${params.id}`, {headers:{Authorization:`Bearer ${token}`}});
      if (response.status === 401) { localStorage.removeItem('access_token'); window.location.href = '/login'; return; }
      if (response.status === 404) { setMessage('Document not found.'); return; }
      if (!response.ok) { setMessage('Document could not be loaded.'); return; }
      setDocument(await response.json()); setMessage('');
    }
    load();
  }, [params.id]);

  return <><p><Link href="/documents">← Back to documents</Link></p><h1>Document details</h1>
    <p role="status">{message}</p>
    {document && <div className="card" data-testid="document-detail">
      <h2>{document.original_filename}</h2>
      {document.duplicate_of_document_id && <p><strong>Kept duplicate</strong></p>}
      <dl><dt>Status</dt><dd>{document.status}</dd><dt>Type</dt><dd>{document.mime_type}</dd><dt>Size</dt><dd>{document.size_bytes} bytes</dd><dt>Uploaded</dt><dd>{new Date(document.uploaded_at).toLocaleString()}</dd><dt>SHA-256</dt><dd className="hash">{document.sha256}</dd>{document.duplicate_of_document_id && <><dt>Duplicate of</dt><dd className="hash">{document.duplicate_of_document_id}</dd></>}</dl>
    </div>}
  </>;
}
