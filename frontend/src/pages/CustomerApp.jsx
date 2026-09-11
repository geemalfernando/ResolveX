import { useState } from "react";

import { API_BASE_URL } from "../lib/supabaseClient";

const COMPLAINT_TYPES = [
  { value: "late", label: "Order was late" },
  { value: "wrong_item", label: "Wrong item" },
  { value: "damaged", label: "Item was damaged" },
  { value: "missing_item", label: "Item missing" },
];

/**
 * Customer-facing complaint form, presented at phone width (no native app for the hackathon).
 * Submits POST /cases and shows the resulting outcome once the pipeline runs.
 */
export default function CustomerApp() {
  const [orderId, setOrderId] = useState("");
  const [complaintType, setComplaintType] = useState(COMPLAINT_TYPES[0].value);
  const [description, setDescription] = useState("");
  const [photoUrl, setPhotoUrl] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setResult(null);

    try {
      const res = await fetch(`${API_BASE_URL}/cases`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          order_id: orderId,
          complaint_type: complaintType,
          description: description || null,
          photo_url: photoUrl || null,
          trigger: "customer_complaint",
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Request failed (${res.status})`);
      }
      setResult(await res.json());
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-sm mx-auto min-h-full bg-white shadow-sm px-4 py-6">
      <h1 className="text-xl font-bold mb-1">Report a problem</h1>
      <p className="text-sm text-slate-500 mb-6">
        Tell us what went wrong with your order and we&apos;ll sort it out.
      </p>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium mb-1">Order ID</label>
          <input
            required
            value={orderId}
            onChange={(e) => setOrderId(e.target.value)}
            placeholder="paste the order id"
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">What happened?</label>
          <select
            value={complaintType}
            onChange={(e) => setComplaintType(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
          >
            {COMPLAINT_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">Details (optional)</label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">Photo URL</label>
          <input
            value={photoUrl}
            onChange={(e) => setPhotoUrl(e.target.value)}
            placeholder="Supabase Storage URL (upload wiring TODO)"
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
          <p className="text-xs text-slate-400 mt-1">
            TODO: replace with a real file input that uploads to the `complaint-photos` bucket.
          </p>
        </div>

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-md bg-slate-900 text-white text-sm font-medium py-2 disabled:opacity-50"
        >
          {submitting ? "Submitting..." : "Submit report"}
        </button>
      </form>

      {error && (
        <div className="mt-4 rounded-md bg-red-50 text-red-700 text-sm px-3 py-2">{error}</div>
      )}

      {result && (
        <div className="mt-4 rounded-md bg-slate-50 border px-3 py-3 text-sm">
          <div className="font-semibold mb-1">Outcome: {result.verdict?.outcome ?? "pending"}</div>
          <div className="text-slate-600">
            Fault: {result.verdict?.fault_party ?? "-"} · Confidence:{" "}
            {result.verdict?.confidence ?? "-"}
          </div>
        </div>
      )}
    </div>
  );
}
