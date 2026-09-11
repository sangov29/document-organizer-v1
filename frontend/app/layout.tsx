import './globals.css';
import Link from 'next/link';
export const metadata = { title: 'DocuFlow — Intelligent Document Organizer' };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>
    <header className="site-header"><div className="nav-shell">
      <Link className="brand" href="/"><span className="brand-mark" aria-hidden="true">D</span><span>DocuFlow</span></Link>
      <nav aria-label="Primary navigation"><Link href="/">Home</Link><Link href="/documents">Documents</Link><Link href="/security">Security</Link><Link href="/login">Sign in</Link><Link className="nav-cta" href="/register">Get started</Link></nav>
    </div></header>
    <main>{children}</main>
    <footer><span>DocuFlow</span><span>Private document intelligence, under your control.</span></footer>
  </body></html>;
}
