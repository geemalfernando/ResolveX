import { useEffect, useState } from "react";

import { API_BASE_URL } from "../lib/supabaseClient";

const RESOLUTION_LABELS = {
  SUPPORT_TICKET: "Human Support Review",
  NEED_MORE_INFO: "More Evidence Needed",
  AUTO_REFUND: "Automatic Refund",
  ZONE_BROADCAST: "Zone Delay Notice",
};

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
  const [photoFile, setPhotoFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    const caseId = new URLSearchParams(window.location.search).get("case");
    if (!caseId) return;
    const controller = new AbortController();
    fetch(`${API_BASE_URL}/cases/${encodeURIComponent(caseId)}`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(`Could not load saved case (${response.status})`);
        const savedCase = await response.json();
        if (!savedCase.verdict) throw new Error("This case has no saved verdict. Analysis persistence needs attention.");
        setResult(savedCase);
      })
      .catch((err) => { if (err.name !== "AbortError") setError(err.message); });
    return () => controller.abort();
  }, []);

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setResult(null);

    try {
      let photoUrl = null;
      if (photoFile) {
        setUploading(true);
        const uploadBody = new FormData();
        uploadBody.append("file", photoFile);
        const uploadRes = await fetch(`${API_BASE_URL}/cases/upload-photo`, {
          method: "POST",
          body: uploadBody,
        });
        const uploadResult = await uploadRes.json().catch(() => ({}));
        if (!uploadRes.ok) throw new Error(uploadResult.detail || `Photo upload failed (${uploadRes.status})`);
        photoUrl = uploadResult.photo_url;
      }

      const res = await fetch(`${API_BASE_URL}/cases`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          order_id: orderId,
          complaint_type: complaintType,
          description: description || null,
          photo_url: photoUrl,
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
      setUploading(false);
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
          <label className="block text-sm font-medium mb-1">Evidence photo (optional)</label>
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp"
            onChange={(e) => setPhotoFile(e.target.files?.[0] ?? null)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
          <p className="text-xs text-slate-400 mt-1">
            JPG, PNG, or WebP. The image is uploaded securely before the case is analyzed.
          </p>
        </div>

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-md bg-slate-900 text-white text-sm font-medium py-2 disabled:opacity-50"
        >
          {uploading ? "Uploading photo..." : submitting ? "Submitting..." : "Submit report"}
        </button>
      </form>

      {error && (
        <div className="mt-4 rounded-md bg-red-50 text-red-700 text-sm px-3 py-2">{error}</div>
      )}

      {result && (
        <div className="mt-4 rounded-md bg-slate-50 border px-3 py-3 text-sm">
          <div className="font-semibold mb-1">AI Fault Assessment</div>
          {result.fault?.model_used && <div>Confidence: {result.fault.confidence_level}</div>}
          <div>Prediction: {result.verdict?.fault_prediction ?? result.verdict?.fault_party ?? "pending"}</div>
          <div className="text-slate-600">
            {result.verdict?.model_used ? "Model confidence" : "Rule fallback confidence"}: {result.verdict?.confidence != null ? `${(result.verdict.confidence * 100).toFixed(2)}%` : "—"}
          </div>
          {Object.entries(result.verdict?.class_probabilities ?? {})
            .sort((a, b) => b[1] - a[1])
            .map(([party, probability]) => (
              <div key={party} className="mt-2">
                <div className="flex justify-between"><span>{party}</span><span>{(probability * 100).toFixed(2)}%</span></div>
                <div className="h-2 rounded bg-slate-200"><div className="h-2 rounded bg-blue-600" style={{ width: `${probability * 100}%` }} /></div>
              </div>
            ))}
          <div className="mt-3 font-semibold">Resolution: {RESOLUTION_LABELS[result.resolution?.action ?? result.verdict?.outcome] ?? "pending"}</div>
          {result.verdict?.model_used ? (
            <div className="text-xs text-slate-500">{result.verdict.model_name} · {result.verdict.model_version}
              {result.verdict.label_provenance && <div>{result.verdict.label_provenance}</div>}
            </div>
          ) : (
            <div className="mt-2 text-amber-800">ML inference unavailable: {result.verdict?.fallback_reason ?? "No model inference recorded"}</div>
          )}
          {(() => {
            const timing = result.check_results?.find((check) => check.check_name === "timing");
            const predicted = timing?.details?.predicted_delivery_minutes;
            const photo = result.check_results?.find((check) => check.check_name === "photo");
            return (
              <div className="mt-3 border-t pt-2 text-slate-600 space-y-1">
                <div className="font-semibold">ETA Prediction</div>
                {predicted != null ? <div>Expected delivery: {predicted} minutes</div> : <div>ETA model unavailable; promised delivery time used.</div>}
                <div className="font-semibold pt-2">Evidence</div>
                {photo && (
                  <div>
                    Photo: {!result.case?.complaint?.photo_url && result.case?.complaint?.type === "late" ? "Not required for lateness" : photo.summary}
                    {photo.details?.detected_items?.length > 0 && (
                      <div>Detected items: {photo.details.detected_items.join(", ")}</div>
                    )}
                    {photo.details?.match != null && <div>Damage detected: {photo.details?.damage_detected ? "yes" : "no"}</div>}
                  </div>
                )}
                {result.verdict?.features?.stationary_time_min != null && <div>Longest rider stop: {result.verdict.features.stationary_time_min.toFixed(1)} minutes</div>}
                {result.verdict?.features?.route_deviation_km != null && <div>Extra route distance: {result.verdict.features.route_deviation_km.toFixed(2)} km</div>}
                {result.verdict?.features?.prep_delay_min != null && <div>Merchant prep delay: {result.verdict.features.prep_delay_min.toFixed(1)} minutes</div>}
                {result.check_results?.filter((check) => check.check_name !== "photo").map((check) => (
                  <div key={check.check_name}>
                    {check.check_name}: {check.summary}
                  </div>
                ))}
              </div>
            );
          })()}
        </div>
      )}
    </div>
  );
}
