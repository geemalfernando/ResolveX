import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext.jsx';
import { api, getActivity, recordActivity } from '../lib/api.js';

const QUICK = [
  'What did I just do?',
  'Track my latest order',
  'Explain my latest claim',
];

function ActivityRow({ item }) {
  const ok = item.status == null || item.status < 400;
  return (
    <div className="flex items-center gap-2 rounded-xl bg-slate-50 px-3 py-2 text-xs">
      <span className={`h-2 w-2 shrink-0 rounded-full ${ok ? 'bg-emerald-500' : 'bg-rose-500'}`} />
      <span className="font-semibold text-slate-700">{item.method}</span>
      <span className="min-w-0 flex-1 truncate text-slate-500">{item.path}</span>
      {item.status != null && <span className="tabular-nums text-slate-400">{item.status}</span>}
    </div>
  );
}

export default function XAssistant() {
  const { user, role } = useAuth();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState('');
  const [messages, setMessages] = useState([
    { who: 'x', text: 'Hi — I’m X. I can explain what you did in ResolveX, track order progress, and help with claims.' },
  ]);
  const [busy, setBusy] = useState(false);
  const [activityVersion, setActivityVersion] = useState(0);
  const endRef = useRef(null);

  useEffect(() => {
    recordActivity({ method: 'VIEW', path: location.pathname + location.search, status: 200 });
    setActivityVersion((v) => v + 1);
  }, [location.pathname, location.search]);

  useEffect(() => {
    if (open) endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, open]);

  const activity = useMemo(() => getActivity().slice(-8).reverse(), [activityVersion, open]);

  async function ask(text = message) {
    const clean = text.trim();
    if (!clean || busy) return;
    setMessage('');
    setMessages((m) => [...m, { who: 'me', text: clean }]);

    if (!user) {
      setMessages((m) => [...m, { who: 'x', text: 'Sign in first so I can safely use your ResolveX activity and account context.' }]);
      return;
    }

    setBusy(true);
    try {
      const result = await api('/assistant/chat', {
        message: clean,
        page: location.pathname + location.search,
        activity: getActivity().slice(-20),
      });
      setMessages((m) => [...m, { who: 'x', text: result.reply }]);
    } catch (error) {
      setMessages((m) => [...m, { who: 'x', text: `I couldn't reach the assistant: ${error.message}` }]);
    } finally {
      setBusy(false);
      setActivityVersion((v) => v + 1);
    }
  }

  return (
    <>
      {open && (
        <section className="fixed bottom-24 right-4 z-50 flex h-[min(620px,calc(100vh-7rem))] w-[min(390px,calc(100vw-2rem))] flex-col overflow-hidden rounded-[1.75rem] border border-slate-200 bg-white shadow-2xl">
          <header className="relative overflow-hidden bg-slate-950 px-5 py-4 text-white">
            <div className="pointer-events-none absolute -right-8 -top-10 h-28 w-28 rounded-full bg-teal-400/20 blur-2xl" />
            <div className="relative flex items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="grid h-11 w-11 place-items-center rounded-2xl bg-teal-300 text-xl font-black text-slate-950 shadow-lg">X</div>
                <div>
                  <p className="font-semibold">X Assistant</p>
                  <p className="text-xs text-slate-400">{user ? `${role || 'signed in'} · activity aware` : 'sign in for personalized help'}</p>
                </div>
              </div>
              <button type="button" onClick={() => setOpen(false)} className="rounded-full px-2 py-1 text-slate-400 hover:bg-white/10 hover:text-white" aria-label="Close assistant">✕</button>
            </div>
          </header>

          <div className="border-b border-slate-100 px-4 py-3">
            <div className="mb-2 flex items-center justify-between">
              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">Recent activity</p>
              <span className="text-[10px] text-slate-400">No secrets recorded</span>
            </div>
            <div className="space-y-1.5">
              {activity.slice(0, 3).map((item, index) => <ActivityRow key={`${item.at}-${index}`} item={item} />)}
              {!activity.length && <p className="text-xs text-slate-400">Actions will appear as you use ResolveX.</p>}
            </div>
          </div>

          <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
            {messages.map((m, index) => (
              <div key={index} className={`flex ${m.who === 'me' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[86%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed ${m.who === 'me' ? 'bg-teal-700 text-white' : 'bg-slate-100 text-slate-700'}`}>
                  {m.text}
                </div>
              </div>
            ))}
            {busy && <div className="w-fit rounded-2xl bg-slate-100 px-3.5 py-2.5 text-sm text-slate-500">X is checking your activity…</div>}
            <div ref={endRef} />
          </div>

          <div className="border-t border-slate-100 p-3">
            <div className="mb-2 flex gap-1.5 overflow-x-auto pb-1">
              {QUICK.map((q) => (
                <button key={q} type="button" onClick={() => ask(q)} className="whitespace-nowrap rounded-full bg-slate-100 px-3 py-1.5 text-[11px] font-medium text-slate-600 hover:bg-slate-200">
                  {q}
                </button>
              ))}
            </div>
            {!user ? (
              <Link to="/login" className="block rounded-2xl bg-slate-950 px-4 py-3 text-center text-sm font-semibold text-white">Sign in to use X</Link>
            ) : (
              <form onSubmit={(e) => { e.preventDefault(); ask(); }} className="flex items-end gap-2">
                <textarea
                  rows={1}
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  placeholder="Ask X about your order, claim, or recent action…"
                  className="min-h-11 flex-1 resize-none rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm outline-none ring-teal-200 focus:ring-2"
                />
                <button type="submit" disabled={busy || !message.trim()} className="grid h-11 w-11 place-items-center rounded-2xl bg-teal-700 font-bold text-white disabled:opacity-40" aria-label="Send message">↑</button>
              </form>
            )}
            <p className="mt-2 text-center text-[10px] leading-relaxed text-slate-400">Uses the backend AI key. Tokens, passwords, headers and API keys are never stored in activity history.</p>
          </div>
        </section>
      )}

      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="fixed bottom-5 right-5 z-50 grid h-14 w-14 place-items-center rounded-2xl bg-slate-950 text-xl font-black text-teal-300 shadow-[0_16px_45px_-12px_rgba(15,23,42,0.75)] transition hover:-translate-y-1 hover:scale-105"
        aria-label={open ? 'Close X Assistant' : 'Open X Assistant'}
        title="Ask X"
      >
        X
        <span className="absolute -right-1 -top-1 h-3.5 w-3.5 rounded-full border-2 border-white bg-emerald-400" />
      </button>
    </>
  );
}
