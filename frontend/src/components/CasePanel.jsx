import RiderRouteCheck from './RiderRouteCheck';
import { actionLabel, faultLabel, publicFault, resolution } from '../lib/api';
export default function CasePanel({ record, technical = false }) {
  const c = record.case, v = record.verdict, w = c?.workflow ?? {};
  if (!c) return null;
  const results = record.check_results ?? w.checks ?? [];
  const timing = results.find(r=>r.check_name==='timing')?.details ?? {};
  const routeCheck = results.find(r=>r.check_name==='rider_route');
  const zone = results.find(r=>r.check_name==='zone')?.details ?? {};
  const photo = results.find(r=>r.check_name==='photo')?.details ?? {};
  const history = results.find(r=>r.check_name==='claim_history')?.details ?? {};
  return <section className="space-y-4" data-testid="case-panel">
    <div className="flex justify-between gap-4"><div><h2 className="font-semibold">Case {record.case_id?.slice(0,8).toUpperCase()}</h2><p className="text-xs text-slate-500 break-all">Order {c.order.id}</p></div><span className="text-sm">{record.status}</span></div>
    <div className="rounded-lg bg-slate-50 p-4"><div className="text-xs uppercase text-slate-500">AI assessment</div><h3 className="text-lg font-bold">{faultLabel(publicFault(record))}</h3>
      {v?.cause_category==='EXTERNAL' && <p>Zone-wide external disruption. Neither merchant nor rider is held responsible.</p>}
      {v && <p className="text-sm">Fault assessment confidence: {(v.confidence*100).toFixed(2)}%</p>}
      <p className="mt-2 font-medium">{actionLabel(resolution(record))}</p>
      {timing.predicted_delivery_minutes != null && <p className="text-sm">Expected delivery: {timing.predicted_delivery_minutes} min</p>}
      {w.refund && <div className="mt-2 text-emerald-800">LKR {w.refund.amount.toLocaleString()} · {w.refund.status}<p className="text-xs">{w.refund.reference} · Demo refund (no payment charged)</p></div>}
    </div>
    <div><h3 className="font-medium">Complaint</h3><p>{c.complaint?.type?.replaceAll('_',' ') ?? 'Proactive delivery incident — no complaint received'}</p><p className="text-sm text-slate-600">{c.complaint?.description}</p>
      {c.complaint?.photo_url && <img src={c.complaint.photo_url} alt="Customer evidence" className="mt-2 max-h-48 rounded-lg"/>}
    </div>
    <div className="text-sm space-y-2"><h3 className="font-medium">Why this assessment?</h3>
      <p><b>Timing:</b> Preparation {timing.prep_minutes ?? 'unknown'} / {timing.prep_promised_minutes ?? '—'} min expected. Delivery {timing.delivery_minutes ?? 'in progress'} / {timing.delivery_promised_minutes ?? '—'} min promised.</p>
      <p><b>Zone:</b> {zone.late_orders_count ?? 0} of {zone.open_orders_count ?? 0} active deliveries delayed ({((zone.late_ratio ?? 0)*100).toFixed(0)}%). Average delay {zone.average_delay_minutes?.toFixed(1) ?? 'unknown'} min.</p>
      <p><b>Photo:</b> {!c.complaint?.photo_url ? (v?.claim_assessment?.photo_required ? 'Required evidence missing' : 'Not required for this incident') : photo.complaint_supported === true ? 'Complaint supported by visible evidence' : 'Photo requires review'}{photo.spillage_detected ? ' · Spillage visible' : ''}</p>
      {technical && <p><b>Claim history:</b> {history.claims_last_90_days ?? 0} prior claims; {v?.claim_assessment?.risk_level ?? 'unknown'} risk. {v?.claim_assessment?.reason}</p>}
    </div>
    <RiderRouteCheck check={routeCheck} />
    {technical && w.fraud_screening && <section className="rounded-lg border bg-amber-50 p-4 text-sm"><h3 className="font-semibold">Automated claim-history screening</h3><p>{w.fraud_screening.summary}</p><p>{w.fraud_screening.status === 'review_required' ? 'Automatic refund held for support review.' : 'No claim-history risk hold.'} This is a risk signal, not a finding of fraud.</p></section>}
    {w.demo_scenario && <p className="text-xs text-slate-500">Demo scenario: {w.demo_scenario.label} · Synthetic data</p>}
    {w.partner && <p className="text-sm"><b>Partner response:</b> {w.partner.status} — {w.partner.reason}</p>}
    <details><summary className="cursor-pointer text-sm font-medium">Technical details</summary><div className="mt-3 space-y-2">
      {Object.entries(v?.class_probabilities ?? {}).sort((a,b)=>b[1]-a[1]).map(([label,prob])=><div key={label}><div className="flex justify-between text-xs"><span>{label}</span><span>{(prob*100).toFixed(2)}%</span></div><div className="h-2 rounded bg-slate-100"><div className="h-2 rounded bg-indigo-500" style={{width:`${prob*100}%`}}/></div></div>)}
      {technical && <><p className="text-xs">{v?.model_name} · {v?.model_version} · ML used: {String(v?.model_used)}</p><p className="text-xs text-slate-500">{v?.label_provenance}</p><pre className="overflow-auto text-xs">{JSON.stringify(v?.features,null,2)}</pre></>}
      {!v?.model_used && <p className="text-xs">Model unavailable; this assessment needs review.</p>}
    </div></details>
    {w.timeline?.length>0 && <details open><summary className="text-sm font-medium">Case timeline</summary><ol className="mt-2 border-l pl-3 space-y-1 text-xs text-slate-500">{w.timeline.map((event,i)=><li key={i}>{new Date(event.at).toLocaleTimeString()} · {event.label}</li>)}</ol></details>}
  </section>;
}
