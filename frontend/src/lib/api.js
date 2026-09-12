import { API_BASE_URL, supabase } from './supabaseClient';

const ACTIVITY_KEY = 'resolvex-x-activity';

export function getActivity() {
  try {
    return JSON.parse(localStorage.getItem(ACTIVITY_KEY)) || [];
  } catch {
    return [];
  }
}

export function recordActivity(entry) {
  if (typeof window === 'undefined') return;
  const clean = {
    at: new Date().toISOString(),
    method: entry.method || 'GET',
    path: entry.path || '/',
    status: entry.status ?? null,
  };
  const current = getActivity();
  localStorage.setItem(ACTIVITY_KEY, JSON.stringify([...current, clean].slice(-40)));
}

export async function api(path, body, options = {}) {
  const { data: { session } } = await supabase.auth.getSession();
  const headers = { ...(options.headers ?? {}) };
  if (session?.access_token) headers.Authorization = `Bearer ${session.access_token}`;

  const method = body === undefined ? (options.method ?? 'GET') : (options.method ?? 'POST');
  const init = { method, headers };

  if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, init);
  const value = await response.json().catch(() => ({}));

  // Track only method/path/status. Never store request bodies, auth headers,
  // API keys, passwords, cookies, or bearer tokens in assistant activity.
  if (path !== '/assistant/chat') recordActivity({ method, path, status: response.status });

  if (response.status === 401) {
    await supabase.auth.signOut();
    const error = new Error('Your session expired. Please sign in again.');
    error.status = 401;
    throw error;
  }
  if (!response.ok) {
    const error = new Error(typeof value.detail === 'string' ? value.detail : `Request failed (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return value;
}

export async function uploadApi(path, formData) {
  const { data: { session } } = await supabase.auth.getSession();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: session?.access_token ? { Authorization: `Bearer ${session.access_token}` } : {},
    body: formData,
  });
  const value = await response.json().catch(() => ({}));
  recordActivity({ method: 'POST', path, status: response.status });
  if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : `Request failed (${response.status})`);
  return value;
}

export const publicFault = (record) => record.case?.workflow?.human_verdict ?? record.verdict?.fault_party?.toUpperCase() ?? 'PENDING';
export const faultLabel = (party) => ({MERCHANT:'Merchant responsible', RIDER:'Rider responsible', NEITHER:'Neither party at fault', PENDING:'Analysis pending'}[party] ?? party);
export const actionLabel = (action) => ({AUTO_REFUND:'Refund approved automatically', NEED_MORE_INFO:'More evidence required', SUPPORT_TICKET:'Support review required', ZONE_BROADCAST:'Area delay notice issued', NO_ACTION:'No further action required'}[action] ?? action);
export const resolution = (record) => record.case?.workflow?.resolution_action ?? record.verdict?.outcome;
