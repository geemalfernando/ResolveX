import unittest
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
from backend.app.routers import commerce as c
from backend.app.auth import AuthPrincipal

class DB:
 def __init__(self):self.tables={t:[] for t in ['orders','merchants','riders','rider_gps_points']}
 def table(self,t):return Query(self,t)
class Query:
 def __init__(self,db,t):self.db=db;self.t=t;self.filters=[];self.action='select';self.body=None;self.one=False
 def select(self,*a,**kw):return self
 def eq(self,k,v):self.filters.append((k,v));return self
 def insert(self,b):self.action='insert';self.body=b;return self
 def update(self,b):self.action='update';self.body=b;return self
 def single(self):self.one=True;return self
 def limit(self,n):return self
 def execute(self):
  rows=self.db.tables[self.t]
  if self.action=='insert':
   new=self.body if isinstance(self.body,list) else [self.body];rows.extend(dict(r) for r in new);out=new
  else:
   out=[r for r in rows if all(r.get(k)==v for k,v in self.filters)]
   if self.action=='update':
    for r in out:r.update(self.body)
  return SimpleNamespace(data=(dict(out[0]) if self.one and out else [dict(r) for r in out]))

class CommerceTests(unittest.TestCase):
 def setUp(self):
  self.db=DB();self.mid=str(uuid4());self.rid=str(uuid4());self.cid=str(uuid4())
  self.db.tables['merchants']=[dict(id=self.mid,zone_id='ZONE_A',avg_prep_minutes=15,lat=6.9,lng=79.8)]
  self.db.tables['riders']=[dict(id=self.rid, name='Kasun', zone_id='ZONE_A')]
  self.customer=AuthPrincipal('customer',None,'customer',customer_id=self.cid)
  self.partner=AuthPrincipal('partner',None,'partner',merchant_id=self.mid)
  self.rider=AuthPrincipal('rider',None,'rider',rider_id=self.rid)
  self.patch=patch.object(c,'get_supabase',return_value=self.db);self.patch.start();self.addCleanup(self.patch.stop)
  self.photos=patch.object(c,'has_evidence',return_value=True);self.photos.start();self.addCleanup(self.photos.stop)
 def checkout(self, pay=True):
  body=c.Checkout(request_id=uuid4(),merchant_id=self.mid,items=[dict(product_id='rice',qty=2)],address='12 Colombo Lane',phone='0771234567',lat=6.91,lng=79.81)
  order=c.checkout(body,self.customer)
  if pay:
   order=c.pay_order(body.request_id,c.PayOrder(holder='Demo Customer'),self.customer)
  return order,body
 def test_checkout_authoritative_price_and_retry(self):
  order,body=self.checkout(pay=False);again=c.checkout(body,self.customer)
  self.assertEqual(order['items'][0]['price'],1250);self.assertEqual(again['id'],order['id']);self.assertEqual(len(self.db.tables['orders']),1)
  self.assertEqual(order['items'][0]['delivery']['address'],'12 Colombo Lane')
  self.assertEqual(order['items'][0]['payment']['status'],'pending')
  paid=c.pay_order(body.request_id,c.PayOrder(holder='Demo Customer'),self.customer)
  self.assertEqual(paid['items'][0]['payment']['last4'],'4242')
  self.assertEqual(paid['items'][0]['payment']['gateway'],'ResolveX Pay')
  self.assertNotIn('number', paid['items'][0]['payment'])
 def test_unpaid_order_cannot_be_accepted(self):
  order,_=self.checkout(pay=False)
  with self.assertRaises(HTTPException) as error:c.stage(order['id'],c.Stage(action='accept'),self.partner)
  self.assertEqual(error.exception.status_code,402)
 def test_cross_account_order_denied(self):
  order,_=self.checkout()
  with self.assertRaises(HTTPException) as error:c.authorize_order(order,AuthPrincipal('other',None,'customer',customer_id=str(uuid4())))
  self.assertEqual(error.exception.status_code,403)
 def test_complete_fulfillment_and_gps(self):
  order,_=self.checkout();oid=order['id']
  for action in ['accept','pack','handover']:
   c.stage(oid,c.Stage(action=action,rider_id=self.rid if action=='handover' else None),self.partner)
  c.position(oid,c.Position(lat=6.905,lng=79.805),self.rider)
  final=c.stage(oid,c.Stage(action='deliver',lat=6.91,lng=79.81),self.rider)
  self.assertEqual(final['status'],'dropped_off')
  for key in ['prep_started_at','ready_at','picked_up_at','dropped_off_at']:self.assertTrue(final[key])
  self.assertEqual(len(self.db.tables['rider_gps_points']),3)
 def test_invalid_transition_and_unassigned_rider(self):
  order,_=self.checkout()
  with self.assertRaises(HTTPException) as error:c.stage(order['id'],c.Stage(action='pack'),self.partner)
  self.assertEqual(error.exception.status_code,409)
  with self.assertRaises(HTTPException) as error:c.stage(order['id'],c.Stage(action='deliver',lat=1,lng=1),self.rider)
  self.assertEqual(error.exception.status_code,403)
 def test_pack_and_deliver_require_photos(self):
  order,_=self.checkout()
  c.stage(order['id'],c.Stage(action='accept'),self.partner)
  with patch.object(c,'has_evidence',return_value=False):
   with self.assertRaises(HTTPException) as error:c.stage(order['id'],c.Stage(action='pack'),self.partner)
  self.assertEqual(error.exception.status_code,422)
  self.assertIn('packing photo', error.exception.detail.lower())
 def test_declined_demo_card_does_not_place_order(self):
  body=c.Checkout(request_id=uuid4(),merchant_id=self.mid,items=[dict(product_id='rice',qty=1)],address='12 Colombo Lane',phone='0771234567',lat=6.91,lng=79.81,payment=dict(holder='Demo Customer',number='4000000000000002',expiry='12/28',cvc='123'))
  with self.assertRaises(HTTPException) as error:c.checkout(body,self.customer)
  self.assertEqual(error.exception.status_code,402)
  self.assertEqual(self.db.tables['orders'],[])
