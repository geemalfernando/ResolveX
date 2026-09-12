"""Customer checkout and authenticated merchant/rider fulfillment."""
from dataclasses import asdict
from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt
from typing import Optional, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, TypeAdapter

from ..auth import AuthPrincipal, current_user, require_roles
from ..db import get_supabase
from .. import workflows as wf

router = APIRouter(prefix='/commerce', tags=['commerce'])
MENU = [
    dict(id='rice', name='Chicken rice & curry', price=1250, category='Sri Lankan', emoji='🍛'),
    dict(id='kottu', name='Vegetable cheese kottu', price=1100, category='Sri Lankan', emoji='🥘'),
    dict(id='burger', name='Grilled chicken burger', price=1450, category='Burgers', emoji='🍔'),
    dict(id='noodles', name='Vegetable noodles', price=950, category='Vegetarian', emoji='🍜'),
    dict(id='juice', name='Fresh lime juice', price=350, category='Drinks', emoji='🍋'),
]


def _distance_km(lat1, lng1, lat2, lng2):
    if None in (lat1, lng1, lat2, lng2):
        return None
    radius = 6371.0
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * radius * asin(sqrt(a))


def _active_rider_loads():
    loads = {}
    for order in wf.rows('orders'):
        if order.get('rider_id') and order.get('status') in ('ready', 'picked_up'):
            loads[order['rider_id']] = loads.get(order['rider_id'], 0) + 1
    return loads


def _pick_nearby_rider(order, exclude_ids=None):
    exclude_ids = set(exclude_ids or [])
    sb = get_supabase()
    merchant = sb.table('merchants').select('lat,lng,zone_id').eq('id', order['merchant_id']).single().execute().data
    riders = sb.table('riders').select('id,name,vehicle,zone_id,lat,lng,last_location_at').eq('zone_id', order['zone_id']).execute().data or []
    riders = [r for r in riders if r['id'] not in exclude_ids]
    if not riders:
        return None

    loads = _active_rider_loads()
    idle = [r for r in riders if loads.get(r['id'], 0) == 0]
    pool = idle or riders

    for rider in pool:
        rider['_distance_km'] = _distance_km(merchant['lat'], merchant['lng'], rider.get('lat'), rider.get('lng'))
        rider['_load'] = loads.get(rider['id'], 0)

    pool.sort(
        key=lambda rider: (
            rider['_distance_km'] is None,
            rider['_distance_km'] if rider['_distance_km'] is not None else 999999,
            rider['_load'],
            rider['name'],
        )
    )
    return pool[0]


def _audit_reassignment(order_id, from_rider_id, to_rider_id, reason):
    try:
        get_supabase().table('rider_reassignments').insert(
            dict(
                order_id=order_id,
                from_rider_id=from_rider_id,
                to_rider_id=to_rider_id,
                reason=reason,
            )
        ).execute()
    except Exception:
        pass


@router.get('/catalog')
def catalog():
    merchants = get_supabase().table('merchants').select('id,name,address,zone_id,avg_prep_minutes').execute().data or []
    return dict(merchants=merchants, products=MENU, currency='LKR')


@router.get('/me')
def me(principal: AuthPrincipal = Depends(current_user)):
    return asdict(principal)


class CartItem(BaseModel):
    product_id: str
    qty: int = Field(ge=1, le=20)


class Checkout(BaseModel):
    request_id: UUID
    merchant_id: UUID
    items: list[CartItem] = Field(min_length=1, max_length=20)
    address: str = Field(min_length=8, max_length=500)
    phone: str = Field(min_length=7, max_length=30)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    instructions: str = Field(default='', max_length=500)


def find_order(order_id):
    rows = get_supabase().table('orders').select('*').eq('id', str(order_id)).execute().data or []
    if not rows:
        raise HTTPException(404, 'Order not found')
    return rows[0]


def authorize_order(order, principal):
    if principal.role in ('admin', 'ops', 'support'):
        return
    if principal.role == 'customer' and order['customer_id'] == principal.customer_id:
        return
    if principal.role == 'partner' and order['merchant_id'] == principal.merchant_id:
        return
    if principal.role == 'rider' and order.get('rider_id') == principal.rider_id:
        return
    raise HTTPException(403, 'This order does not belong to your account')


@router.post('/orders')
def checkout(body: Checkout, principal: AuthPrincipal = Depends(require_roles('customer'))):
    if not principal.customer_id:
        raise HTTPException(403, 'Customer account is not linked')
    sb = get_supabase()
    with wf.LOCK:
        existing = sb.table('orders').select('*').eq('id', str(body.request_id)).execute().data or []
        if existing:
            authorize_order(existing[0], principal)
            return existing[0]
        merchants = sb.table('merchants').select('*').eq('id', str(body.merchant_id)).execute().data or []
        if not merchants:
            raise HTTPException(404, 'Restaurant not found')
        merchant = merchants[0]
        prices = {p['id']: p for p in MENU}
        items = []
        delivery = dict(
            address=body.address.strip(),
            phone=body.phone,
            lat=body.lat,
            lng=body.lng,
            instructions=body.instructions,
        )
        for item in body.items:
            if item.product_id not in prices:
                raise HTTPException(422, 'Product is unavailable')
            product = prices[item.product_id]
            items.append(
                dict(
                    product_id=product['id'],
                    name=product['name'],
                    qty=item.qty,
                    price=product['price'],
                    delivery=delivery,
                )
            )
        row = dict(
            id=str(body.request_id),
            merchant_id=merchant['id'],
            customer_id=principal.customer_id,
            zone_id=merchant['zone_id'],
            items=items,
            status='placed',
            placed_at=wf.now(),
            promised_prep_minutes=merchant['avg_prep_minutes'],
            promised_delivery_minutes=merchant['avg_prep_minutes'] + 25,
            is_late_flagged=False,
        )
        sb.table('orders').insert(row).execute()
        return row


@router.get('/orders')
def my_orders(principal: AuthPrincipal = Depends(current_user)):
    if principal.role == 'customer':
        filters = {'customer_id': principal.customer_id}
    elif principal.role == 'partner':
        filters = {'merchant_id': principal.merchant_id}
    elif principal.role == 'rider':
        filters = {'rider_id': principal.rider_id}
    elif principal.role in ('admin', 'ops', 'support'):
        filters = {}
    else:
        raise HTTPException(403, 'Order access is not assigned')
    if any(v is None for v in filters.values()):
        raise HTTPException(403, 'Account is not linked')

    rows = wf.rows('orders', **filters)
    for order in rows:
        if order['status'] in wf.OPEN:
            placed = TypeAdapter(datetime).validate_python(order['placed_at'])
            late = (datetime.now(timezone.utc) - placed).total_seconds() / 60 > order['promised_delivery_minutes']
            if late != order.get('is_late_flagged', False):
                get_supabase().table('orders').update({'is_late_flagged': late}).eq('id', order['id']).eq('status', order['status']).execute()
                order['is_late_flagged'] = late

    cases = wf.rows('cases')
    claims = {}
    for case in cases:
        claims.setdefault(case['order_id'], []).append(case['id'])
    return [dict(o, case_ids=claims.get(o['id'], [])) for o in sorted(rows, key=lambda r: r['placed_at'], reverse=True)]


class Stage(BaseModel):
    action: Literal['accept', 'reject', 'pack', 'handover', 'deliver', 'decline_delivery']
    rider_id: Optional[UUID] = None
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lng: Optional[float] = Field(default=None, ge=-180, le=180)


@router.post('/orders/{order_id}/stage')
def stage(order_id: UUID, body: Stage, principal: AuthPrincipal = Depends(require_roles('partner', 'rider', 'admin'))):
    merchant_actions = {'accept', 'reject', 'pack', 'handover'}
    rider_actions = {'deliver', 'decline_delivery'}
    if body.action in merchant_actions and principal.role not in ('partner', 'admin'):
        raise HTTPException(403, 'Only the restaurant can update preparation and handover')
    if body.action in rider_actions and principal.role not in ('rider', 'admin'):
        raise HTTPException(403, 'Only the assigned rider can update delivery')

    with wf.LOCK:
        order = find_order(order_id)
        authorize_order(order, principal)

        if body.action == 'decline_delivery':
            if order['status'] != 'ready':
                raise HTTPException(409, 'Only packed orders can be declined by a rider')
            previous = order.get('rider_id')
            replacement = _pick_nearby_rider(order, exclude_ids={previous} if previous else set())
            next_rider = replacement['id'] if replacement else None
            result = get_supabase().table('orders').update({'rider_id': next_rider}).eq('id', str(order_id)).eq('status', 'ready').execute().data
            if not result:
                raise HTTPException(409, 'Order changed; refresh and try again')
            _audit_reassignment(str(order_id), previous, next_rider, 'rider_rejected')
            return dict(result[0], assignment_pending=next_rider is None)

        transitions = {
            'accept': ('placed', 'preparing', 'prep_started_at'),
            'reject': ('placed', 'cancelled', None),
            'pack': ('preparing', 'ready', 'ready_at'),
            'handover': ('ready', 'picked_up', 'picked_up_at'),
            'deliver': ('picked_up', 'dropped_off', 'dropped_off_at'),
        }
        before, after, timestamp = transitions[body.action]
        if order['status'] != before:
            raise HTTPException(409, f"Order is {order['status']}; expected {before}")

        update = dict(status=after)
        if timestamp:
            update[timestamp] = wf.now()

        if body.action == 'pack':
            rider = _pick_nearby_rider(order)
            update['rider_id'] = rider['id'] if rider else None

        if body.action == 'handover':
            assigned_rider_id = order.get('rider_id')
            if not assigned_rider_id:
                rider = _pick_nearby_rider(order)
                if not rider:
                    raise HTTPException(409, 'No rider is available in this zone yet')
                assigned_rider_id = rider['id']
                update['rider_id'] = assigned_rider_id
            merchant = get_supabase().table('merchants').select('lat,lng').eq('id', order['merchant_id']).single().execute().data
            gps({**order, 'rider_id': assigned_rider_id}, merchant['lat'], merchant['lng'], 0)

        if body.action == 'deliver':
            if body.lat is None or body.lng is None:
                raise HTTPException(422, 'Delivery location is required')
            gps(order, body.lat, body.lng, 0)
            placed = TypeAdapter(datetime).validate_python(order['placed_at'])
            update['is_late_flagged'] = (datetime.now(timezone.utc) - placed).total_seconds() / 60 > order['promised_delivery_minutes']

        result = get_supabase().table('orders').update(update).eq('id', str(order_id)).eq('status', before).execute().data
        if not result:
            raise HTTPException(409, 'Order changed; refresh and try again')
        return result[0]


def gps(order, lat, lng, speed):
    get_supabase().table('rider_gps_points').insert(
        dict(
            order_id=order['id'],
            rider_id=order['rider_id'],
            lat=lat,
            lng=lng,
            speed_kmh=speed,
            recorded_at=wf.now(),
        )
    ).execute()


class Position(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    speed_kmh: float = Field(default=0, ge=0, le=150)


@router.post('/rider/location')
def rider_location(body: Position, principal: AuthPrincipal = Depends(require_roles('rider', 'admin'))):
    if principal.role == 'rider' and not principal.rider_id:
        raise HTTPException(403, 'Rider account is not linked')
    rider_id = principal.rider_id
    if principal.role == 'admin' and not rider_id:
        raise HTTPException(422, 'Admin session is not linked to a rider')
    result = get_supabase().table('riders').update(
        {'lat': body.lat, 'lng': body.lng, 'last_location_at': wf.now()}
    ).eq('id', rider_id).execute().data
    if not result:
        raise HTTPException(404, 'Rider not found')
    return {'saved': True, 'rider_id': rider_id}


@router.post('/orders/{order_id}/position')
def position(order_id: UUID, body: Position, principal: AuthPrincipal = Depends(require_roles('rider', 'admin'))):
    order = find_order(order_id)
    authorize_order(order, principal)
    if order['status'] != 'picked_up':
        raise HTTPException(409, 'Location updates require an active delivery')
    gps(order, body.lat, body.lng, body.speed_kmh)
    get_supabase().table('riders').update(
        {'lat': body.lat, 'lng': body.lng, 'last_location_at': wf.now()}
    ).eq('id', order['rider_id']).execute()
    return {'saved': True}


@router.get('/riders')
def riders(principal: AuthPrincipal = Depends(require_roles('partner', 'admin', 'ops'))):
    return get_supabase().table('riders').select('id,name,vehicle,zone_id,lat,lng,last_location_at').execute().data or []


class RiderAccount(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=12, max_length=128)
    name: str = Field(min_length=2, max_length=100)
    zone_id: str = Field(min_length=1, max_length=100)
    vehicle: Literal['bike', 'scooter', 'car'] = 'bike'


@router.post('/riders')
def create_rider(body: RiderAccount, principal: AuthPrincipal = Depends(require_roles('admin'))):
    sb = get_supabase()
    rid = str(uuid4())
    sb.table('riders').insert(dict(id=rid, name=body.name, phone='', vehicle=body.vehicle, zone_id=body.zone_id)).execute()
    try:
        user = sb.auth.admin.create_user(
            dict(
                email=body.email,
                password=body.password,
                email_confirm=True,
                app_metadata=dict(role='rider', rider_id=rid, display_name=body.name),
            )
        ).user
    except Exception as exc:
        sb.table('riders').delete().eq('id', rid).execute()
        raise HTTPException(400, 'Could not create account. Check the email is unused and the password meets requirements.') from exc
    return dict(rider_id=rid, user_id=user.id)
