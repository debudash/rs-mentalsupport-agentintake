import { vi } from 'vitest';

type Handler = (body: unknown, init?: RequestInit) => { status?: number; json: unknown };

/** Route-based fetch mock: `routes['POST /api/consent'] = () => ({ json: {...} })`. */
export function mockFetch(routes: Record<string, Handler>) {
  const calls: { key: string; body: unknown }[] = [];
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString();
    const path = url.split('?')[0];
    const key = `${init?.method ?? 'GET'} ${path}`;
    const body = typeof init?.body === 'string' ? JSON.parse(init.body) : init?.body;
    calls.push({ key, body });
    const handler = routes[key];
    if (!handler) return new Response(JSON.stringify({ detail: 'not mocked' }), { status: 404 });
    const { status = 200, json } = handler(body, init);
    return new Response(JSON.stringify(json), {
      status,
      headers: { 'Content-Type': 'application/json' },
    });
  });
  vi.stubGlobal('fetch', fn);
  return calls;
}
