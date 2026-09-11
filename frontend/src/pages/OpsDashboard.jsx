import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import MapView from '../components/MapView';

export default function OpsDashboard(){
 const [ops,setOps]=useState(null),[feed,setFeed]=useState(null),[positions,setPositions]=useState([]),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const load=()=>Promise.all([api('/workflow/ops'),api('/demo/state'),api('/workflow/ops/positions')])
   .then(([o,f,p])=>{setOps(o);setFeed(f);setPositions(p);setError('');})
   .catch(e=>setError(e.message));
 useEffect(()=>{load();const id=setInterval(load,5000);return()=>clearInterval(id);},[]);
 async function control(action){setBusy(true);setError('');try{setFeed(await api('/demo/control',{action}));await load();}catch(e){setError(e.message);}finally{setBusy(false);}}
 return <div className="max-w-7xl mx-auto p-6 space-y-5">
   <div className="flex items-center justify-between"><div><h1 className="text-2xl font-bold">Delivery operations</h1><p className="text-sm text-slate-500">Restricted to Ops and Admin users.</p></div><button className="btn-secondary" onClick={load}>Refresh</button></div>
   {error&&<p role="alert" className="rounded-lg bg-red-50 p-3 text-red-700">{error}</p>}
   <div className="grid grid-cols-2 md:grid-cols-6 gap-3">{Object.entries(ops?.counts??{}).map(([k,v])=><div className="rounded-lg border bg-white p-3" key={k}><p className="text-xs capitalize">{k.replaceAll('_',' ')}</p><b className="text-2xl">{v}</b></div>)}</div>
   <div className="grid lg:grid-cols-2 gap-5">
    <section className="rounded-xl border bg-white p-5"><div className="flex justify-between"><h2 className="font-bold">Live delivery feed</h2><span className="text-xs">{feed?.running?'Running':'Paused'} · Accelerated demo</span></div><div className="flex flex-wrap gap-2 my-4">{[['start','Start Busy Evening'],['pause','Pause'],['reset','Reset Demo'],['step','Next Stage']].map(([a,l])=><button className="btn-secondary" disabled={busy} key={a} onClick={()=>control(a)}>{l}</button>)}</div>{feed?.error&&<p role="alert">{feed.error}</p>}<div className="max-h-[30rem] overflow-auto space-y-2">{feed?.orders?.map(o=><div key={o.id} className={`border-l-4 rounded p-3 bg-slate-50 ${o.late?'border-red-500':o.stage==='READY'?'border-amber-400':'border-emerald-500'}`}><div className="flex justify-between"><b>{o.scenario} · {o.id.slice(0,8)}</b><span>{o.stage}</span></div><p className="text-xs">Promised {o.expected_minutes??30} min · ETA {o.eta_minutes??'pending'} · {o.late?'Late':'On track'}</p>{o.case_id?<p className="text-sm font-medium text-red-700">Incident {o.case_id.slice(0,8)} created automatically before complaint</p>:<p className="text-xs">No customer complaint</p>}</div>)}</div></section>
    <div className="rounded-xl overflow-hidden border h-[36rem]"><MapView orders={positions}/></div>
   </div>
   <section className="rounded-xl border bg-white p-5"><h2 className="font-bold mb-3">Live cases</h2><div className="grid md:grid-cols-2 gap-3">{ops?.cases?.slice(0,40).map(c=><article className="rounded border p-3 text-sm" key={c.case_id}><b>Order {c.case?.order?.id?.slice(0,8)}</b><p>{c.case?.trigger} · {c.verdict?.outcome ?? c.status}</p>{c.verdict?.outcome==='SUPPORT_TICKET'&&<span className="text-amber-700">Needs review</span>}</article>)}</div><p className="text-xs text-slate-500 mt-3">Detailed claim-risk assessment is available to administrators in Claim Risk.</p></section>
   <section className="rounded-xl border bg-white p-5"><h2 className="font-bold mb-3">Active zone incidents</h2>{(ops?.zone_incidents??[]).length===0&&<p className="text-sm text-slate-500">No active zone incidents.</p>}{ops?.zone_incidents?.map(z=><div key={z.id} className="border-t py-3"><b>{z.id} · {z.zone_id}</b><p>{z.active_orders} active orders · {z.late_orders} late · {z.customers_notified} customers notified</p><details><summary>Affected orders and notices</summary>{z.notifications.map(n=><p className="text-xs py-1" key={n.id}>{n.order_ids.join(', ')} — Notice delivered in app</p>)}</details></div>)}</section>
 </div>;
}
