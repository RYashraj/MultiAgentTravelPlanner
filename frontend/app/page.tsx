"use client";

import { useEffect, useState } from "react";

type HealthResponse = {
  status: string;
  service: string;
  database: string;
};

type PingState =
  | { phase: "loading" }
  | { phase: "success"; data: HealthResponse }
  | { phase: "error"; message: string };

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";

export default function Home() {
  const [state, setState] = useState<PingState>({ phase: "loading" });

  useEffect(() => {
    let cancelled = false;

    async function pingBackend() {
      try {
        const res = await fetch(`${API_BASE_URL}/health`);
        if (!res.ok) throw new Error(`Backend responded with ${res.status}`);
        const data: HealthResponse = await res.json();
        if (!cancelled) setState({ phase: "success", data });
      } catch (err) {
        if (!cancelled) {
          setState({
            phase: "error",
            message:
              err instanceof Error
                ? err.message
                : "Could not reach the backend",
          });
        }
      }
    }

    pingBackend();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 p-8">
      <h1 className="text-3xl font-bold">VoyagerAI</h1>
      <p className="text-slate-500">Week 2 — infrastructure check</p>

      <div className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        {state.phase === "loading" && (
          <p className="text-slate-500">Pinging backend…</p>
        )}

        {state.phase === "success" && (
          <div className="space-y-2">
            <StatusRow label="API" value={state.data.status} ok />
            <StatusRow
              label="Database"
              value={state.data.database}
              ok={state.data.database === "connected"}
            />
            <StatusRow label="Service" value={state.data.service} ok />
          </div>
        )}

        {state.phase === "error" && (
          <div className="space-y-2">
            <StatusRow label="API" value="unreachable" ok={false} />
            <p className="text-sm text-slate-400">{state.message}</p>
            <p className="text-xs text-slate-400">
              Is the backend running on {API_BASE_URL}?
            </p>
          </div>
        )}
      </div>
    </main>
  );
}

function StatusRow({
  label,
  value,
  ok,
}: {
  label: string;
  value: string;
  ok: boolean;
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-slate-600">{label}</span>
      <span
        className={`rounded-full px-3 py-1 text-sm font-medium ${
          ok ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
        }`}
      >
        {value}
      </span>
    </div>
  );
}
