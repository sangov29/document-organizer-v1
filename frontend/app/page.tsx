import Link from 'next/link';

export default function Home() {
  return <section className="hero">
    <div className="eyebrow">Private · searchable · explainable</div>
    <h1>Your documents,<br/><span>finally organized.</span></h1>
    <p className="hero-copy">Upload everyday documents and let DocuFlow securely read, classify and organize them—with every extracted detail linked back to its source.</p>
    <div className="hero-actions"><Link className="button-link" href="/register">Organize your documents</Link><Link className="text-link" href="/login">I already have an account →</Link></div>
    <div className="feature-grid">
      <article><span className="feature-icon">01</span><h2>Understand</h2><p>PaddleOCR reads PDFs and images, then identifies the document family and important fields.</p></article>
      <article><span className="feature-icon">02</span><h2>Verify</h2><p>Confidence, provenance and review history keep every automated decision transparent.</p></article>
      <article><span className="feature-icon">03</span><h2>Protect</h2><p>Financial details and signatures stay concealed until you explicitly choose to reveal them.</p></article>
    </div>
  </section>;
}
