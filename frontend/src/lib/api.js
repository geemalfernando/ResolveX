import { API_BASE_URL } from './supabaseClient';
export async function api(path, body) {
  const response = await fetch(`${API_BASE_URL}${path}`, body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  const value = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : `Request failed (${response.status})`);
  return value;
}
export const publicFault = (record) => record.case?.workflow?.human_verdict ?? record.verdict?.fault_party?.toUpperCase() ?? 'PENDING';
export const faultLabel = (party) => ({MERCHANT:'Merchant responsible', RIDER:'Rider responsible', NEITHER:'Neither party at fault', PENDING:'Analysis pending'}[party] ?? party);
export const actionLabel = (action) => ({AUTO_REFUND:'Refund approved', NEED_MORE_INFO:'More evidence required', SUPPORT_TICKET:'Under support review', ZONE_BROADCAST:'Area delay notice issued', NO_ACTION:'No further action required'}[action] ?? action);
export const resolution = (record) => record.case?.workflow?.resolution_action ?? record.verdict?.outcome;
