import { useEffect, useState } from "react";
import { api, resolution, uploadApi } from "../lib/api";
import CasePanel from "../components/CasePanel";

const TYPES = {
  late: "Late delivery",
  damaged: "Damaged order",
  wrong_item: "Wrong item",
  missing_item: "Missing item",
  not_delivered: "Order not delivered",
  tampering: "Possible tampering",
};
const ORDER_ID_PATTERN = "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}";
const isOrderId = (value) => new RegExp(`^${ORDER_ID_PATTERN}$`).test(value);
const PHOTO = ["damaged", "wrong_item", "missing_item", "tampering"];

export default function CustomerApp() {
  const [order, setOrder] = useState(new URLSearchParams(location.search).get("order") || "");
  const [type, setType] = useState("late");
  const [description, setDescription] = useState("");
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState("");
  const [record, setRecord] = useState(null);
  const [notices, setNotices] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!file) {
      setPreview("");
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  useEffect(() => {
    const id = new URLSearchParams(location.search).get("case");
    if (id) {
      api(`/cases/${id}`)
        .then((r) => {
          setRecord(r);
          setOrder(r.case.order.id);
        })
        .catch((e) => setError(e.message));
    }
  }, []);

  useEffect(() => {
    setNotices([]);
    if (!isOrderId(order)) return;
    let cancelled = false;
    let timer;
    const load = async () => {
      try {
        const notices = await api(`/notifications?order_id=${encodeURIComponent(order)}`);
        if (!cancelled) setNotices(notices);
      } catch (err) {
        if (cancelled) return;
        if ([401, 403, 404, 422].includes(err.status)) {
          setError(err.message);
          return;
        }
      }
      if (!cancelled) timer = setTimeout(load, 5000);
    };
    load();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [order]);

  async function upload() {
    if (!file) return null;
    const form = new FormData();
    form.append("file", file);
    return (await uploadApi("/cases/upload-photo", form)).photo_url;
  }

  async function submit(event, additional = false) {
    event.preventDefault();
    if (!additional && !isOrderId(order)) {
      setError("Enter a valid Order ID, for example 123e4567-e89b-12d3-a456-426614174000.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const photo = await upload();
      const r = await api(
        additional ? `/cases/${record.case_id}/evidence` : "/cases",
        additional
          ? { photo_url: photo, description }
          : { order_id: order, complaint_type: type, description, photo_url: photo }
      );
      setRecord(r);
      history.replaceState(null, "", `?case=${r.case_id}`);
      setFile(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page-shell space-y-5">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-teal-700">Customer</p>
        <h1 className="text-2xl font-bold tracking-tight">Your delivery, resolved</h1>
        <p className="mt-1 text-sm text-slate-500">Report a problem and see the decision immediately.</p>
      </div>

      {notices.map((n) => (
        <aside key={n.id} className="rounded-2xl border border-amber-200 bg-amber-50 p-4">
          <b>Delivery disruption in your area</b>
          <p className="mt-1 text-sm">{n.message}</p>
          {n.additional_delay_minutes != null && (
            <p className="text-sm">Estimated additional delay: {Math.ceil(n.additional_delay_minutes)} minutes</p>
          )}
        </aside>
      ))}

      {error && (
        <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-700">
          {error}
        </p>
      )}

      {!record && (
        <form onSubmit={(e) => submit(e)} className="panel mx-auto max-w-2xl space-y-4 p-6">
          <label className="block text-sm font-medium">
            Order ID
            <input
              aria-label="Order ID"
              required
              maxLength={36}
              pattern={ORDER_ID_PATTERN}
              title="Enter the 36-character Order ID from your order."
              className="field"
              value={order}
              onChange={(e) => {
                setOrder(e.target.value.trim());
                setError("");
              }}
            />
          </label>
          <label className="block text-sm font-medium">
            What happened?
            <select className="field" value={type} onChange={(e) => setType(e.target.value)}>
              {Object.entries(TYPES).map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm font-medium">
            Details
            <textarea className="field" value={description} onChange={(e) => setDescription(e.target.value)} />
          </label>
          <label className="block text-sm font-medium">
            {PHOTO.includes(type) ? "Evidence photo required" : "Evidence photo optional"}
            <input
              className="field"
              required={PHOTO.includes(type)}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>
          {preview && <img src={preview} alt="Evidence preview" className="max-h-48 rounded-xl" />}
          <button className="btn" disabled={busy}>
            {busy ? "Analyzing…" : "Submit report"}
          </button>
        </form>
      )}

      {record && (
        <div className="mx-auto max-w-3xl space-y-4">
          <div className="panel p-5">
            <CasePanel record={record} />
            {resolution(record) === "NEED_MORE_INFO" && (
              <form onSubmit={(e) => submit(e, true)} className="mt-5 space-y-3 border-t pt-4">
                <h3 className="font-semibold">More evidence required</h3>
                <p className="text-sm text-slate-600">{record.case.workflow.evidence_request}</p>
                <input
                  aria-label="Additional evidence"
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  required={record.verdict?.claim_assessment?.photo_required}
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                />
                {preview && <img src={preview} alt="Additional evidence preview" className="max-h-48 rounded-xl" />}
                <textarea
                  aria-label="Additional explanation"
                  className="field"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
                <button className="btn" disabled={busy}>
                  Upload evidence and re-analyze
                </button>
              </form>
            )}
          </div>
          <button
            className="text-sm font-medium text-teal-800"
            onClick={() => {
              setRecord(null);
              history.replaceState(null, "", "/report");
            }}
          >
            Report another order
          </button>
        </div>
      )}
    </div>
  );
}
