import "leaflet/dist/leaflet.css";

import L from "leaflet";
import { useEffect, useMemo, useState } from "react";
import { Circle, CircleMarker, MapContainer, Popup, TileLayer, Tooltip } from "react-leaflet";

import { supabase } from "../lib/supabaseClient";

// Default Leaflet marker icons reference files that don't bundle well with Vite;
// we only use CircleMarker below so this isn't needed, but keep Leaflet's default
// icon path fix here in case a future page adds a standard <Marker>.
delete L.Icon.Default.prototype._getIconUrl;

const DEFAULT_CENTER = [6.9271, 79.8612]; // Colombo, Sri Lanka — swap for your demo city
const TRAFFIC_ZONES = {
  ZONE_A: [6.9271, 79.8612],
  ZONE_B: [6.9521, 79.8762],
  ZONE_C: [6.9071, 79.8812],
  ZONE_D: [6.9371, 79.8362],
};

const MOCK_ORDERS = [
  { id: "mock-1", zone_id: "ZONE_A", lat: 6.9271, lng: 79.8612, status: "picked_up", is_late_flagged: false },
  { id: "mock-2", zone_id: "ZONE_D", lat: 6.9165, lng: 79.8478, status: "preparing", is_late_flagged: true },
  { id: "mock-3", zone_id: "ZONE_A", lat: 6.935, lng: 79.845, status: "dropped_off", is_late_flagged: false },
];

const STATUS_COLOR = {
  placed: "#94a3b8",
  preparing: "#f59e0b",
  ready: "#f59e0b",
  picked_up: "#3b82f6",
  dropped_off: "#22c55e",
  completed: "#22c55e",
};

function markerColor(order) {
  if (order.is_late_flagged) return "#ef4444";
  return STATUS_COLOR[order.status] ?? "#64748b";
}

/**
 * Live map of open orders. Subscribes to Supabase Realtime changes on `orders` so
 * dots move/recolor as riders progress and the live feed flags late orders.
 * Falls back to MOCK_ORDERS if Supabase isn't configured yet.
 */
export default function MapView({ zoneId = null, height = "100%" }) {
  const [orders, setOrders] = useState(MOCK_ORDERS);

  useEffect(() => {
    let isMounted = true;

    // TODO: orders don't carry their own lat/lng — join merchants (pickup) or the latest
    // rider_gps_points row (in-transit) server-side (e.g. a Postgres view) and select from
    // that instead. Left as mock data here so the map renders before that view exists.
    async function loadInitial() {
      let query = supabase.from("open_order_positions").select("id, zone_id, lat, lng, status, is_late_flagged");
      if (zoneId) query = query.eq("zone_id", zoneId);
      const { data, error } = await query;
      if (!error && data?.length && isMounted) {
        setOrders(data);
      }
    }
    loadInitial();

    const channel = supabase
      .channel("orders-realtime")
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "orders" },
        (payload) => {
          setOrders((prev) => {
            const updated = payload.new;
            if (!updated?.id) return prev;
            const idx = prev.findIndex((o) => o.id === updated.id);
            if (idx === -1) return [...prev, updated];
            const next = [...prev];
            next[idx] = { ...next[idx], ...updated };
            return next;
          });
        }
      )
      .subscribe();

    return () => {
      isMounted = false;
      supabase.removeChannel(channel);
    };
  }, [zoneId]);

  const points = useMemo(() => orders.filter((o) => o.lat && o.lng), [orders]);
  const trafficAreas = useMemo(() => {
    const byZone = new Map();
    Object.entries(TRAFFIC_ZONES).forEach(([zone, [lat, lng]]) => {
      byZone.set(zone, { zone, lat, lng, count: 0, late: 0 });
    });
    points.forEach((order) => {
      const zone = order.zone_id ?? "ZONE_A";
      const current = byZone.get(zone) ?? { zone, lat: 0, lng: 0, count: 0, late: 0 };
      if (current.count > 0 || !TRAFFIC_ZONES[zone]) {
        current.lat += Number(order.lat);
        current.lng += Number(order.lng);
      }
      current.count += 1;
      current.late += order.is_late_flagged ? 1 : 0;
      byZone.set(zone, current);
    });
    return [...byZone.values()].map((area) => ({
      ...area,
      lat: area.count ? area.lat / area.count : area.lat,
      lng: area.count ? area.lng / area.count : area.lng,
      lateRatio: area.late / area.count,
    }));
  }, [points]);

  function trafficColor(lateRatio) {
    if (lateRatio >= 0.6) return "#dc2626";
    if (lateRatio >= 0.3) return "#f59e0b";
    return "#22c55e";
  }

  return (
    <MapContainer center={DEFAULT_CENTER} zoom={13} style={{ height, width: "100%" }}>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {trafficAreas.map((area) => {
        const color = trafficColor(area.lateRatio);
        const traffic = area.lateRatio >= 0.6 ? "Jam" : area.lateRatio >= 0.3 ? "High" : "Normal";
        return (
          <Circle
            key={`traffic-${area.zone}`}
            center={[area.lat, area.lng]}
            radius={1200}
            pathOptions={{ color, fillColor: color, fillOpacity: 0.2, weight: 3 }}
          >
            <Tooltip permanent direction="top">
              {area.zone}: {traffic} traffic ({Math.round(area.lateRatio * 100)}% late)
            </Tooltip>
          </Circle>
        );
      })}
      {points.map((order) => (
        <CircleMarker
          key={order.id}
          center={[order.lat, order.lng]}
          radius={9}
          pathOptions={{ color: markerColor(order), fillColor: markerColor(order), fillOpacity: 0.8 }}
        >
          <Popup>
            <div className="text-sm">
              <div className="font-semibold">Order {order.id}</div>
              <div>Status: {order.status}</div>
              {order.is_late_flagged && <div className="text-red-600 font-medium">Flagged late</div>}
            </div>
          </Popup>
        </CircleMarker>
      ))}
    </MapContainer>
  );
}
