// Thin fetch wrapper. Errors carry a user-safe message from the API (never a stack trace).
export class ApiError extends Error {}

export async function api(path, { method = 'GET', body } = {}) {
  let res;
  try {
    res = await fetch(path, { method, headers: body ? { 'Content-Type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined });
  } catch (e) {
    throw new ApiError('Cannot reach the TravelOS server. Is it still running?');
  }
  let data = null;
  try { data = await res.json(); } catch { /* non-JSON */ }
  if (!res.ok) throw new ApiError(data?.error?.message || `Request failed (${res.status})`);
  return data;
}
export const get = (p) => api(p);
export const post = (p, body = {}) => api(p, { method: 'POST', body });
export const put = (p, body = {}) => api(p, { method: 'PUT', body });
export const del = (p) => api(p, { method: 'DELETE' });
export const qs = (o) => Object.entries(o).filter(([, v]) => v !== '' && v != null).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join('&');
