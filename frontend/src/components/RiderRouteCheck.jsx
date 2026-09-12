const issueLabels = {
  long_detour: 'Long detour detected',
  long_stationary_stop: 'Long stationary stop detected',
  dropoff_far_from_address: 'Drop-off far from the delivery address',
};
const metric = (value, unit) => Number.isFinite(value) ? `${value} ${unit}` : 'Unavailable';

export default function RiderRouteCheck({ check }) {
  const details = check?.details ?? {};
  const insufficient = !check || details.reason === 'insufficient_gps_data';
  const modelUsed = details.source === 'isolation_forest';
  return <section aria-label="Rider route analysis" className="rounded-lg border bg-white p-4 space-y-3">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h3 className="font-semibold text-red-800">Rider Route · AI</h3>
      <span className={`rounded-full px-2 py-1 text-xs ${insufficient ? 'bg-slate-100' : check.flagged ? 'bg-amber-100 text-amber-900' : 'bg-emerald-100 text-emerald-900'}`}>
        {insufficient ? 'Awaiting GPS evidence' : check.flagged ? 'Route needs review' : 'No route issues detected'}
      </span>
    </div>
    <p className="text-sm text-slate-600">Flags detours, long stops, or a drop-off far from the address.</p>
    <p className="text-sm">{check?.summary ?? 'Route analysis will appear after this case is analyzed.'}</p>
    {!insufficient && <>
      <dl className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-sm">
        <div><dt className="text-slate-500">Detour ratio</dt><dd className="font-medium">{metric(details.detour_ratio, '× direct distance')}</dd></div>
        <div><dt className="text-slate-500">Longest stop</dt><dd className="font-medium">{metric(details.max_stationary_minutes, 'min')}</dd></div>
        <div><dt className="text-slate-500">Drop-off distance</dt><dd className="font-medium">{metric(details.dropoff_distance_from_address_m, 'm from address')}</dd></div>
      </dl>
      {details.issues?.length > 0 && <ul className="list-disc pl-5 text-sm">{details.issues.map(issue => <li key={issue}>{issueLabels[issue] ?? issue.replaceAll('_', ' ')}</li>)}</ul>}
      <p className="text-xs text-slate-500">{modelUsed ? 'AI route model and GPS rules used. A route flag is evidence for review, not a final fault decision.' : 'GPS rules used; AI model result unavailable for this assessment.'}</p>
    </>}
  </section>;
}
