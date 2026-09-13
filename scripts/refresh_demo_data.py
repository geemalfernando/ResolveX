"""Replace recognized seed data with named scenarios; preserve login-linked identities.

Dry run: python scripts/refresh_demo_data.py --backup scripts/seed_output/database_backup_....json
Apply the reviewed plan: add --apply. The backup is required and never committed.
"""
import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['PHOTO_USE_GEMINI'] = 'false'
os.environ['AGGREGATOR_USE_GEMINI'] = 'false'
from backend.app import workflows as wf
from backend.app.models import CreateCaseRequest
from backend.app.routers.cases import create_case
from backend.app.ml.fault_model import fault_model
from backend.app.ml.eta_model import eta_model
from backend.app.config import get_settings
import seed_data as legacy

SCENARIOS = [
 ('kitchen_delay','Kitchen preparation delay','late',50,52,62),
 ('rider_detour','Rider takes a long detour','late',12,15,80),
 ('long_stop','Rider stationary for 20 minutes','late',12,15,65),
 ('far_dropoff','Delivery recorded away from address','not_delivered',12,15,55),
 ('zone_delay','Area-wide delivery disruption','late',12,15,80),
 ('repeat_claims','Frequent claims require review','late',50,52,70),
 ('denied_history','Repeated denied claims require review','late',50,52,70),
 ('damaged','Damaged packaging; photo needed','damaged',12,15,35),
 ('wrong_item','Wrong item; photo needed','wrong_item',12,15,35),
 ('missing_item','Missing item; photo needed','missing_item',12,15,35),
 ('tampering','Broken seal; photo needed','tampering',12,15,35),
 ('not_delivered','Late order with no delivery recorded','not_delivered',12,15,None),
 ('missing_gps','Delayed order with no GPS evidence','late',12,15,65),
 ('on_time','On-time delivery, no complaint',None,12,15,30),
]
def uid(label):
 return str(uuid.uuid5(uuid.NAMESPACE_URL,'resolvex/scenarios/v2/'+label))

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--backup',type=Path,required=True);parser.add_argument('--apply',action='store_true');args=parser.parse_args()
 snapshot=json.loads(args.backup.read_text())
 known={}
 for table,fn in [('merchants',legacy.seed_merchants),('riders',legacy.seed_riders),('customers',legacy.seed_customers)]:
  known[table]={r['name'] for r in fn(MagicMock())}
  unknown=[r['id'] for r in snapshot[table] if r['name'] not in known[table] and not r['zone_id'].startswith(('BUSY_','ML_VERIFY_','DEMO_V2_')) and r['name'] not in ('ResolveX Demo Merchant','Demo Customer')]
  if unknown: raise RuntimeError(f'Unrecognized {table}; refusing deletion: {unknown}')
 linked_customers={p['customer_id'] for p in snapshot['user_profiles'] if p.get('customer_id')}
 linked_merchants={p['merchant_id'] for p in snapshot['user_profiles'] if p.get('merchant_id')}
 print('Replacement scenarios:',json.dumps([s[1] for s in SCENARIOS]))
 print('Preserving login profiles:',len(snapshot['user_profiles']),'and linked identities:',len(linked_customers)+len(linked_merchants))
 if not args.apply: return
 sb=wf.get_supabase()
 # Refuse stale snapshots before performing any deletion.
 for table in snapshot:
  if table=='user_profiles':
   current=sb.table(table).select('*').execute().data or []
   if current!=snapshot[table]: raise RuntimeError('Login profiles changed since backup')
  elif {r['id'] for r in wf.rows(table)}!={r['id'] for r in snapshot[table]}:
   raise RuntimeError(f'{table} changed since backup; create a fresh backup')
 for table in ['check_results','verdicts','support_tickets','cases','complaints','refund_history','rider_gps_points','orders','riders','customers','merchants']:
  keep=linked_customers if table=='customers' else linked_merchants if table=='merchants' else set()
  ids=[r['id'] for r in snapshot[table] if r['id'] not in keep]
  for start in range(0,len(ids),100): sb.table(table).delete().in_('id',ids[start:start+100]).execute()
  print('Removed',table,len(ids),flush=True)
 settings=get_settings();fault_model.load(settings.fault_model_path);eta_model.load(settings.eta_model_path)
 now=datetime.now(timezone.utc);manifest=[]
 for i,(key,label,complaint,ready,pickup,drop) in enumerate(SCENARIOS):
  zone='DEMO_V2_COLOMBO_'+key.upper()
  # The merchant behind the partner login keeps its own restaurant and zone; a
  # scenario zone has no riders with a login, so orders placed there cannot be delivered.
  mid=uid(key+'/merchant')
  cid=next(iter(linked_customers)) if i==0 and linked_customers else uid(key+'/customer')
  rid=uid(key+'/rider');oid=uid(key+'/order')
  sb.table('merchants').insert(dict(id=mid,name=['Cinnamon Kitchen','Bambalapitiya Rice & Curry','Wellawatte Family Meals'][i%3]+' · '+label,zone_id=zone,address='Colombo demo restaurant',lat=6.9,lng=79.8,avg_prep_minutes=15)).execute()
  if cid not in linked_customers: sb.table('customers').insert(dict(id=cid,name=['Amaya','Nimal','Dilini','Kavindu','Ishara','Sachini','Ravindu'][i%7]+' · '+label,email=f'{key}@demo.resolvex.invalid',phone='0000000000',address=f'{12+i} Demo Lane, Colombo',zone_id=zone,lat=6.91,lng=79.81)).execute()
  sb.table('riders').insert(dict(id=rid,name=['Kasun','Tharindu','Malith','Dinesh'][i%4]+' · Demo',phone='0000000000',vehicle='bike',zone_id=zone)).execute()
  if i == 0:
   sb.table('customers').update(dict(lat=6.91,lng=79.81,zone_id=zone)).eq('id',cid).execute()
  # Keep the authenticated identity while replacing its seeded delivery geography.
  customer=sb.table('customers').select('*').eq('id',cid).single().execute().data
  merchant=sb.table('merchants').select('*').eq('id',mid).single().execute().data
  placed=now-timedelta(minutes=120)
  stamp=lambda m:(placed+timedelta(minutes=m)).isoformat() if m is not None else None
  base=dict(merchant_id=mid,customer_id=cid,rider_id=rid,zone_id=zone,items=[dict(name='Chicken rice and curry',qty=1,price=1250),dict(name='Fresh lime juice',qty=1,price=350)],promised_prep_minutes=15,promised_delivery_minutes=35)
  sb.table('orders').insert(dict(base,id=oid,status='dropped_off' if drop else 'picked_up',placed_at=stamp(0),prep_started_at=stamp(1),ready_at=stamp(ready),picked_up_at=stamp(pickup),dropped_off_at=stamp(drop),is_late_flagged=drop is None or drop>35)).execute()
  # Valid timestamp-ordered GPS points, confined to the actual delivery interval.
  if key!='missing_gps':
   points=[]
   for j in range(9):
    f=j/8;lat=merchant['lat']+(customer['lat']-merchant['lat'])*f;lng=merchant['lng']+(customer['lng']-merchant['lng'])*f
    minute=pickup+((drop or 90)-pickup)*f
    if key=='rider_detour' and 2<=j<=5: lng-=0.035
    if key=='long_stop' and 2<=j<=5: lat=merchant['lat'];lng=merchant['lng']
    if key=='far_dropoff':lat-=0.01*f;lng-=0.01*f
    points.append(dict(order_id=oid,rider_id=rid,lat=lat,lng=lng,speed_kmh=0 if key=='long_stop' and 2<=j<=5 else 18,recorded_at=stamp(minute)))
   sb.table('rider_gps_points').insert(points).execute()
  if key=='not_delivered':
   for j in range(5):
    sb.table('orders').insert(dict(base,id=uid(f'{key}/background/{j}'),status='preparing',placed_at=(now-timedelta(minutes=10)).isoformat(),prep_started_at=(now-timedelta(minutes=9)).isoformat(),is_late_flagged=False)).execute()
  if key=='zone_delay':
   for j in range(10):
    sb.table('orders').insert(dict(base,id=uid(f'{key}/background/{j}'),status='preparing',placed_at=(now-timedelta(minutes=70 if j<8 else 10)).isoformat(),prep_started_at=(now-timedelta(minutes=69 if j<8 else 9)).isoformat(),is_late_flagged=j<8)).execute()
  if key in ('repeat_claims','denied_history'):
   for j in range(6):
    old=now-timedelta(days=3+j*4);hid=uid(f'{key}/history-order/{j}')
    sb.table('orders').insert(dict(base,id=hid,status='dropped_off',placed_at=old.isoformat(),prep_started_at=(old+timedelta(minutes=1)).isoformat(),ready_at=(old+timedelta(minutes=15)).isoformat(),picked_up_at=(old+timedelta(minutes=18)).isoformat(),dropped_off_at=(old+timedelta(minutes=45)).isoformat(),is_late_flagged=True)).execute()
    sb.table('refund_history').insert(dict(id=uid(f'{key}/refund/{j}'),customer_id=cid,order_id=hid,reason=['late','damaged','missing_item'][j%3],amount=1600 if key=='repeat_claims' else 0,outcome='approved' if key=='repeat_claims' else 'denied',created_at=(old+timedelta(hours=1)).isoformat())).execute()
  result=create_case(CreateCaseRequest(order_id=oid,trigger='customer_complaint' if complaint else 'live_feed_late',complaint_type=complaint,description=f'Demo scenario: {label}' if complaint else None))
  result.case.workflow['demo_scenario']=dict(key=key,label=label,synthetic=True)
  wf.save_case(result.case)
  item=dict(scenario=key,description=label,order_id=oid,case_id=result.case_id,outcome=result.verdict.outcome.value,risk=result.case.workflow['fraud_screening']['status'],refund=result.case.workflow.get('refund'))
  manifest.append(item)
  (ROOT/'scripts/seed_output/scenario_manifest.json').write_text(json.dumps(manifest,indent=2))
  print(key,item['outcome'],item['risk'],flush=True)
 print('Complete: scripts/seed_output/scenario_manifest.json')
if __name__=='__main__': main()
