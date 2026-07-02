const BASE = '/api/v1';

let accessToken: string | null = localStorage.getItem('de-access');
let refreshToken: string | null = localStorage.getItem('de-refresh');

export function setTokens(access: string | null, refresh: string | null) {
  accessToken = access;
  refreshToken = refresh;
  if (access) localStorage.setItem('de-access', access);
  else localStorage.removeItem('de-access');
  if (refresh) localStorage.setItem('de-refresh', refresh);
  else localStorage.removeItem('de-refresh');
}

export function getAccessToken() {
  return accessToken;
}

async function tryRefresh(): Promise<boolean> {
  if (!refreshToken) return false;
  const res = await fetch(`${BASE}/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!res.ok) {
    setTokens(null, null);
    return false;
  }
  const data = await res.json();
  setTokens(data.access_token, data.refresh_token);
  return true;
}

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : JSON.stringify(detail));
    this.status = status;
    this.detail = detail;
  }
}

export async function api<T = unknown>(
  path: string,
  options: RequestInit = {},
  retried = false,
): Promise<T> {
  const headers = new Headers(options.headers);
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`);
  if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  const res = await fetch(`${BASE}${path}`, { ...options, headers });
  if (res.status === 401 && !retried && (await tryRefresh())) {
    return api<T>(path, options, true);
  }
  if (!res.ok) {
    let detail: unknown;
    try {
      detail = (await res.json()).detail;
    } catch {
      detail = res.statusText;
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  const contentType = res.headers.get('content-type') ?? '';
  return (contentType.includes('application/json') ? res.json() : res.text()) as Promise<T>;
}

/** Fetches a protected binary (page image, thumbnail, download) with the JWT
 *  and returns an object URL — plain <img src> can't send Authorization. */
export async function fetchBlobUrl(path: string, retried = false): Promise<string> {
  const headers = new Headers();
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`);
  const res = await fetch(`${BASE}${path}`, { headers });
  if (res.status === 401 && !retried && (await tryRefresh())) {
    return fetchBlobUrl(path, true);
  }
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  return URL.createObjectURL(await res.blob());
}

/** Downloads a protected file to disk via a temporary object URL. */
export async function downloadFile(path: string, filename: string): Promise<void> {
  const url = await fetchBlobUrl(path);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
