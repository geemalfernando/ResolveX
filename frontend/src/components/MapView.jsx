import "leaflet/dist/leaflet.css";

import L from "leaflet";
import { useMemo } from "react";
import { Circle, CircleMarker, MapContainer, Popup, TileLayer, Tooltip } from "react-leaflet";

delete L.Icon.Default.prototype._getIconUrl;

const DEFAULT_CENTER = [6.9271, 79.8612];
const TRAFFIC_ZONES = {
  ZONE_A: [6.9271, 79.8612],
  ZONE_B: [6.9521, 79.8762],
  ZONE_C: [6.9071, 79.8812],
  ZONE_D: [6.9371, 79.8362],
};

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

export default function MapView({ orders = [], height = "100%" }) {
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
    return [...byZone.values()]
      .filter((area) => area.count || TRAFFIC_ZONES[area.zone])
      .map((area) => ({
        ...area,
        lat: area.count ? area.lat / area.count : area.lat,
        lng: area.count ? area.lng / area.count : area.lng,
        lateRatio: area.count ? area.late / area.count : 0,
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
          <Circle key={`traffic-${area.zone}`} center={[area.lat, area.lng]} radius={1200}
            pathOptions={{ color, fillColor: color, fillOpacity: 0.2, weight: 3 }}>
            <Tooltip permanent direction="top">
              {area.zone}: {traffic} traffic ({Math.round(area.lateRatio * 100)}% late)
            </Tooltip>
          </Circle>
        );
      })}
      {points.map((order) => (
        <CircleMarker key={order.id} center={[order.lat, order.lng]} radius={9}
          pathOptions={{ color: markerColor(order), fillColor: markerColor(order), fillOpacity: 0.8 }}>
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
