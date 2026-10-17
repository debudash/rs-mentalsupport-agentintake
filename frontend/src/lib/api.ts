// Thin client for the FastAPI backend. The browser talks to Supabase only to sign in;
// everything else goes through here with the Supabase access token.

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : 'Request failed');
    this.status = status;
    this.detail = detail;
  }

  /** A sentence that is safe to show a Client. */
  get friendly(): string {
    if (typeof this.detail === 'string') return this.detail;
    if (this.detail && typeof this.detail === 'object' && 'message' in this.detail) {
      return String((this.detail as { message: unknown }).message);
    }
    return 'Something went wrong. Your progress is saved — please try again.';
  }
}

let tokenProvider: () => Promise<string | null> = async () => null;

export function setTokenProvider(provider: () => Promise<string | null>) {
  tokenProvider = provider;
}

async function headers(json: boolean): Promise<HeadersInit> {
  const token = await tokenProvider();
  return {
    ...(json ? { 'Content-Type': 'application/json' } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function handle<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(response.status, body.detail ?? body);
  return body as T;
}

export async function get<T>(path: string): Promise<T> {
  return handle<T>(await fetch(path, { headers: await headers(false) }));
}

export async function post<T>(path: string, body?: unknown): Promise<T> {
  return handle<T>(
    await fetch(path, {
      method: 'POST',
      headers: await headers(true),
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  );
}

export async function upload<T>(path: string, file: Blob, filename: string): Promise<T> {
  const form = new FormData();
  form.append('file', file, filename);
  return handle<T>(
    await fetch(path, { method: 'POST', headers: await headers(false), body: form }),
  );
}

export async function download(path: string): Promise<Blob> {
  const response = await fetch(path, { headers: await headers(false) });
  if (!response.ok) throw new ApiError(response.status, 'Download failed');
  return response.blob();
}

export const timeZone = () => Intl.DateTimeFormat().resolvedOptions().timeZone;
