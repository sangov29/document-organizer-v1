export const API = process.env.NEXT_PUBLIC_API_URL ?? '';
export async function api(path: string, init?: RequestInit) {
  const response = await fetch(`${API}/api/v1${path}`, init);
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(typeof body?.detail === 'string' ? body.detail : JSON.stringify(body?.detail ?? body));
  return body;
}
