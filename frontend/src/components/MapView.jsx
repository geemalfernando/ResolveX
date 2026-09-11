import "leaflet/dist/leaflet.css";

import L from "leaflet";
import { useEffect, useMemo, useState } from "react";
import { CircleMarker, MapContainer, Popup, TileLayer } from "react-leaflet";

import { supabase } from "../lib/supabaseClient";

// Default Leaflet marker icons reference files that don't bundle well with Vite;
// we only use CircleMarker below so this isn't needed, but keep Leaflet's default
// icon path fix here in case a future page adds a standard <Marker>.
delete L.Icon.Default.prototype._getIconUrl;

const DEFAULT_CENTER = [6.9271, 79.8612]; // Colombo, Sri Lanka — swap for your demo city

const MOCK_ORDERS = [
  { id: "mock-1", lat: 6.9271, lng: 79.8612, status: "picked_up", is_late_flagged: false },
  { id: "mock-2", lat: 6.9165, lng: 79.8478, status: "preparing", is_late_flagged: true },
  { id: "mock-3", lat: 6.935, lng: 79.845, status: "dropped_off", is_late_flagged: false },
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
      let query = supabase.from("open_order_positions").select("id, lat, lng, status, is_late_flagged");
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

  return (
    <MapContainer center={DEFAULT_CENTER} zoom={13} style={{ height, width: "100%" }}>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
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
