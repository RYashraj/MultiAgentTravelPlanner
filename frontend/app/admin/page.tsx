"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Navbar } from "@/components/Navbar";
import { AuthGuard } from "@/components/AuthGuard";
import { apiFetch, ApiError } from "@/lib/api";
import {
  ShieldAlert,
  Activity,
  Users,
  MapPin,
  CheckCircle,
  XCircle,
  Clock,
  RefreshCw,
} from "lucide-react";

interface AdminMetrics {
  total_trips: number;
  total_users: number;
  total_agent_runs: number;
  completed_agent_runs: number;
  failed_agent_runs: number;
}

interface AgentRunSummary {
  id: string;
  trip_id: string;
  agent_name: string;
  status: string;
  duration_seconds: number | null;
  started_at: string | null;
}

interface AdminData {
  metrics: AdminMetrics;
  recent_agent_runs: AgentRunSummary[];
}

function AdminDashboardContent() {
  const [data, setData] = useState<AdminData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchStats = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const stats = await apiFetch<AdminData>("/admin/stats");
      setData(stats);
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setError("Access Denied: Server-side admin authorization required.");
      } else {
        setError(err instanceof Error ? err.message : "Failed to load admin statistics.");
      }
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchStats();
  }, []);

  return (
    <main className="min-h-screen bg-[var(--color-bg)] text-[var(--color-text-primary)] font-sans">
      <Navbar />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8 space-y-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[var(--color-border)]/60 pb-5">
          <div>
            <h1 className="text-xl sm:text-2xl font-extrabold text-[var(--color-text-primary)] flex items-center gap-2">
              <span className="w-2 h-5 bg-purple-500 rounded-full" />
              System Admin & Telemetry
            </h1>
            <p className="text-xs text-[var(--color-text-muted)] mt-1">
              Real-time audit log of agent executions, trip creation, and system metrics.
            </p>
          </div>
          <button
            onClick={fetchStats}
            disabled={isLoading}
            className="px-4 py-2 bg-[var(--color-surface)] hover:bg-[var(--color-surface-hover)] border border-[var(--color-border)] text-xs font-semibold text-[var(--color-text-secondary)] rounded-xl transition-all flex items-center gap-2 shrink-0 self-start sm:self-auto"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin" : ""}`} />
            Refresh Telemetry
          </button>
        </div>

        {/* Error / Forbidden State */}
        {error && (
          <div className="bg-red-950/40 border border-red-900/60 rounded-2xl p-6 text-center space-y-3">
            <ShieldAlert className="w-10 h-10 text-red-400 mx-auto" />
            <h3 className="text-base font-bold text-red-400">{error}</h3>
            <p className="text-xs text-[var(--color-text-muted)] max-w-md mx-auto">
              This view enforces server-side authorization. Log in with an authorized admin account (e.g., admin@example.com).
            </p>
            <Link
              href="/trips"
              className="inline-flex items-center gap-1.5 text-xs text-indigo-400 hover:text-[var(--color-text-primary)] transition-colors mt-2"
            >
              ← Back to Trips
            </Link>
          </div>
        )}

        {/* Loading State */}
        {isLoading && !data && !error && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-28 rounded-2xl bg-[var(--color-surface)]/40 animate-pulse" />
            ))}
          </div>
        )}

        {/* Admin Data View */}
        {data && !error && (
          <div className="space-y-8">
            {/* Top Metric Cards */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
              <div className="bg-[var(--color-surface-alt)] border border-[var(--color-border)] rounded-2xl p-4">
                <div className="flex items-center justify-between text-[var(--color-text-muted)] mb-2">
                  <span className="text-[10px] font-mono uppercase tracking-wider">Total Trips</span>
                  <MapPin className="w-4 h-4 text-indigo-400" />
                </div>
                <p className="text-2xl font-bold text-white">{data.metrics.total_trips}</p>
              </div>

              <div className="bg-[var(--color-surface-alt)] border border-[var(--color-border)] rounded-2xl p-4">
                <div className="flex items-center justify-between text-[var(--color-text-muted)] mb-2">
                  <span className="text-[10px] font-mono uppercase tracking-wider">Total Users</span>
                  <Users className="w-4 h-4 text-purple-400" />
                </div>
                <p className="text-2xl font-bold text-white">{data.metrics.total_users}</p>
              </div>

              <div className="bg-[var(--color-surface-alt)] border border-[var(--color-border)] rounded-2xl p-4">
                <div className="flex items-center justify-between text-[var(--color-text-muted)] mb-2">
                  <span className="text-[10px] font-mono uppercase tracking-wider">Agent Runs</span>
                  <Activity className="w-4 h-4 text-blue-400" />
                </div>
                <p className="text-2xl font-bold text-white">{data.metrics.total_agent_runs}</p>
              </div>

              <div className="bg-[var(--color-surface-alt)] border border-[var(--color-border)] rounded-2xl p-4">
                <div className="flex items-center justify-between text-[var(--color-text-muted)] mb-2">
                  <span className="text-[10px] font-mono uppercase tracking-wider">Successful</span>
                  <CheckCircle className="w-4 h-4 text-emerald-400" />
                </div>
                <p className="text-2xl font-bold text-emerald-400">{data.metrics.completed_agent_runs}</p>
              </div>

              <div className="bg-[var(--color-surface-alt)] border border-[var(--color-border)] rounded-2xl p-4">
                <div className="flex items-center justify-between text-[var(--color-text-muted)] mb-2">
                  <span className="text-[10px] font-mono uppercase tracking-wider">Failed Runs</span>
                  <XCircle className="w-4 h-4 text-rose-400" />
                </div>
                <p className="text-2xl font-bold text-rose-400">{data.metrics.failed_agent_runs}</p>
              </div>
            </div>

            {/* Agent Runs Audit Table */}
            <div className="bg-[var(--color-surface-alt)] border border-[var(--color-border)] rounded-2xl overflow-hidden">
              <div className="px-5 py-4 border-b border-[var(--color-border)]/60 flex items-center justify-between">
                <h3 className="text-sm font-bold text-white flex items-center gap-2">
                  <Activity className="w-4 h-4 text-indigo-400" />
                  Recent Agent Executions
                </h3>
                <span className="text-xs text-[var(--color-text-muted)]">
                  Showing latest {data.recent_agent_runs.length} runs
                </span>
              </div>

              {data.recent_agent_runs.length === 0 ? (
                <div className="p-8 text-center text-xs text-[var(--color-text-muted)]">
                  No agent execution records found in database yet.
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-[var(--color-surface)] text-[var(--color-text-muted)] uppercase text-[10px] tracking-wider border-b border-[var(--color-border)]/40">
                      <tr>
                        <th className="py-3 px-4">Agent Name</th>
                        <th className="py-3 px-4">Status</th>
                        <th className="py-3 px-4">Duration</th>
                        <th className="py-3 px-4">Trip ID</th>
                        <th className="py-3 px-4">Started At</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[var(--color-border)]/40">
                      {data.recent_agent_runs.map((run) => (
                        <tr key={run.id} className="hover:bg-[var(--color-surface-hover)] transition-colors">
                          <td className="py-3 px-4 font-mono font-semibold text-indigo-300">
                            {run.agent_name}
                          </td>
                          <td className="py-3 px-4">
                            <span
                              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                                run.status === "completed"
                                  ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                                  : run.status === "failed"
                                  ? "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                                  : "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                              }`}
                            >
                              {run.status}
                            </span>
                          </td>
                          <td className="py-3 px-4 text-[var(--color-text-secondary)] font-mono">
                            {run.duration_seconds != null ? `${run.duration_seconds}s` : "In progress"}
                          </td>
                          <td className="py-3 px-4 text-[var(--color-text-muted)] font-mono truncate max-w-[120px]">
                            {run.trip_id}
                          </td>
                          <td className="py-3 px-4 text-[var(--color-text-muted)] font-mono">
                            {run.started_at ? new Date(run.started_at).toLocaleTimeString() : "N/A"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </main>
  );
}

export default function AdminPage() {
  return (
    <AuthGuard>
      <AdminDashboardContent />
    </AuthGuard>
  );
}
