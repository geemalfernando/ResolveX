import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import CasePanel from '../components/CasePanel';
export default function PartnerPortal(){
 const [records,setRecords]=useState([]),[tab,setTab]=useState('Needs Response'),[reasons,setReasons]=useState({}),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const load=()=>api('/workflow/cases').then(setRecords).catch(e=>setError(e.message));useEffect(()=>{load();},[]);
 async function respond(id,action){setBusy(true);setError('');try{await api(`/cases/${id}/partner`,{action,reason:reasons[id]??''});await load();}catch(e){setError(e.message);}finally{setBusy(false);}}
 const status=r=>r.case.workflow?.partner?.status==='disputed'?'Disputed':r.status==='resolved'||r.case.workflow?.partner?.status==='accepted'?'Resolved':'Needs Response';
 return <div className="max-w-5xl mx-auto p-6"><h1 className="text-2xl font-bold">Partner response center</h1><div className="flex gap-2 my-4">{['Needs Response','Resolved','Disputed'].map(t=><button className={tab===t?'btn':'btn-secondary'} key={t} onClick={()=>setTab(t)}>{t}</button>)}</div>{error&&<p role="alert" className="text-red-700">{error}</p>}<div className="grid md:grid-cols-2 gap-4">{records.filter(r=>r.verdict&&status(r)===tab).map(r=><article key={r.case_id} className="rounded-xl border bg-white p-5"><CasePanel record={r}/><label className="block mt-4">Response / dispute reason<textarea className="field" value={reasons[r.case_id]??''} onChange={e=>setReasons({...reasons,[r.case_id]:e.target.value})}/></label><div className="flex gap-2 mt-3"><button disabled={busy} className="btn" onClick={()=>respond(r.case_id,'accept')}>Accept verdict</button><button disabled={busy||!reasons[r.case_id]?.trim()} className="btn-secondary" onClick={()=>respond(r.case_id,'dispute')}>Submit dispute</button></div></article>)}</div></div>;
}
