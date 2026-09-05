import './globals.css';
import Link from 'next/link';
export const metadata = { title: 'Document Organizer V1' };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><main>
    <nav><Link href="/">Home</Link><Link href="/register">Register</Link><Link href="/login">Login</Link><Link href="/documents">Documents</Link></nav>
    {children}
  </main></body></html>;
}
