const STYLES = {
  AUTO_REFUND: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  SUPPORT_TICKET: "bg-amber-50 text-amber-900 ring-amber-200",
  NEED_MORE_INFO: "bg-sky-50 text-sky-800 ring-sky-200",
  ZONE_BROADCAST: "bg-indigo-50 text-indigo-800 ring-indigo-200",
  NO_ACTION: "bg-slate-100 text-slate-700 ring-slate-200",
};

const LABELS = {
  AUTO_REFUND: "Auto refund",
  SUPPORT_TICKET: "Needs review",
  NEED_MORE_INFO: "More evidence",
  ZONE_BROADCAST: "Zone notice",
  NO_ACTION: "No action",
};

export function outcomeLabel(outcome) {
  return LABELS[outcome] ?? outcome?.replaceAll("_", " ") ?? "Pending";
}

export default function OutcomeBadge({ outcome, large = false }) {
  const tone = STYLES[outcome] ?? "bg-slate-100 text-slate-600 ring-slate-200";
  return (
    <span
      className={`inline-flex items-center rounded-full ring-1 font-semibold ${
        large ? "px-3 py-1 text-sm" : "px-2.5 py-0.5 text-[11px] tracking-wide"
      } ${tone}`}
    >
      {outcomeLabel(outcome)}
    </span>
  );
}
