"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import Link from "next/link";

interface AgentRunStats {
  total: number;
  by_status: Record<string, number>;
  success_rate_percent: number;
}

interface AdminStats {
  total_users: number;
  total_trips: number;
  agent_runs: AgentRunStats;
}

function StatCard({
  label,
  value,
  sub,
  icon,
  color,
}: {
  label: string;
  value: string | number;
  sub?: string;
  icon: string;
  color: string;
}) {
  return (
    <div className="stat-card" style={{ borderColor: color }}>
      <div className="stat-icon" style={{ background: color + "22", color }}>
        {icon}
      </div>
      <div className="stat-body">
        <div className="stat-label">{label}</div>
        <div className="stat-value">{value}</div>
        {sub && <div className="stat-sub">{sub}</div>}
      </div>
    </div>
  );
}

function ProgressBar({ label, value, max, color }: { label: string; value: number; max: number; color: string }) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div className="progress-row">
      <div className="progress-label">
        <span className="progress-name">{label}</span>
        <span className="progress-count">{value} <span className="progress-pct">({pct}%)</span></span>
      </div>
      <div className="progress-track">
        <div className="progress-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  );
}

export default function AdminPage() {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<AdminStats>("/admin/stats")
      .then(setStats)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const statusColors: Record<string, string> = {
    success: "#22c55e",
    running: "#3b82f6",
    failed: "#ef4444",
    timeout: "#f59e0b",
    error: "#f97316",
  };

  return (
    <div className="admin-page">
      <style>{`
        .admin-page {
          min-height: 100vh;
          background: #0b0f19;
          color: #f1f5f9;
          font-family: 'Inter', sans-serif;
          padding: 2rem;
        }
        .admin-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 2.5rem;
        }
        .admin-title {
          font-size: 1.75rem;
          font-weight: 700;
          background: linear-gradient(135deg, #818cf8, #38bdf8);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
        }
        .admin-subtitle {
          font-size: 0.9rem;
          color: #64748b;
          margin-top: 0.25rem;
        }
        .back-link {
          color: #64748b;
          text-decoration: none;
          font-size: 0.875rem;
          display: flex;
          align-items: center;
          gap: 0.35rem;
          transition: color 0.2s;
        }
        .back-link:hover { color: #94a3b8; }
        .stats-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
          gap: 1.25rem;
          margin-bottom: 2rem;
        }
        .stat-card {
          background: #0f172a;
          border-radius: 1rem;
          border-left: 4px solid;
          padding: 1.5rem;
          display: flex;
          align-items: flex-start;
          gap: 1rem;
          transition: transform 0.2s;
        }
        .stat-card:hover { transform: translateY(-2px); }
        .stat-icon {
          width: 2.75rem;
          height: 2.75rem;
          border-radius: 0.75rem;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 1.3rem;
          flex-shrink: 0;
        }
        .stat-label {
          font-size: 0.8rem;
          color: #64748b;
          font-weight: 500;
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }
        .stat-value {
          font-size: 2rem;
          font-weight: 700;
          color: #f1f5f9;
          line-height: 1.2;
          margin-top: 0.25rem;
        }
        .stat-sub {
          font-size: 0.8rem;
          color: #64748b;
          margin-top: 0.25rem;
        }
        .section {
          background: #0f172a;
          border-radius: 1rem;
          padding: 1.5rem;
          margin-bottom: 1.5rem;
          border: 1px solid #1e293b;
        }
        .section-title {
          font-size: 1rem;
          font-weight: 600;
          color: #94a3b8;
          margin-bottom: 1.25rem;
          display: flex;
          align-items: center;
          gap: 0.5rem;
        }
        .progress-row { margin-bottom: 1rem; }
        .progress-label {
          display: flex;
          justify-content: space-between;
          margin-bottom: 0.4rem;
          font-size: 0.875rem;
        }
        .progress-name { color: #e2e8f0; text-transform: capitalize; }
        .progress-count { color: #94a3b8; font-weight: 600; }
        .progress-pct { color: #64748b; font-weight: 400; }
        .progress-track {
          height: 8px;
          background: #1e293b;
          border-radius: 999px;
          overflow: hidden;
        }
        .progress-fill {
          height: 100%;
          border-radius: 999px;
          transition: width 1s ease-out;
        }
        .success-rate {
          display: flex;
          align-items: center;
          gap: 1rem;
        }
        .rate-circle {
          width: 80px;
          height: 80px;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 1.25rem;
          font-weight: 700;
          flex-shrink: 0;
        }
        .rate-label {
          font-size: 0.875rem;
          color: #64748b;
        }
        .rate-val {
          font-size: 1.5rem;
          font-weight: 700;
          color: #22c55e;
          margin-top: 0.2rem;
        }
        .loading-shimmer {
          background: linear-gradient(90deg, #1e293b 25%, #2d3f55 50%, #1e293b 75%);
          background-size: 200% 100%;
          animation: shimmer 1.4s infinite;
          border-radius: 0.5rem;
          height: 2rem;
          margin: 0.5rem 0;
        }
        @keyframes shimmer {
          0% { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }
        .error-box {
          background: #450a0a;
          border: 1px solid #ef4444;
          border-radius: 0.75rem;
          padding: 1.25rem;
          color: #fca5a5;
          font-size: 0.9rem;
        }
        .badge {
          display: inline-block;
          padding: 0.2rem 0.6rem;
          border-radius: 999px;
          font-size: 0.75rem;
          font-weight: 600;
          background: #1e293b;
          color: #94a3b8;
        }
      `}</style>

      <div className="admin-header">
        <div>
          <div className="admin-title">🛡️ Admin Dashboard</div>
          <div className="admin-subtitle">VoyagerAI — Real-time usage statistics</div>
        </div>
        <Link href="/" className="back-link">
          ← Back to App
        </Link>
      </div>

      {loading && (
        <div>
          {[...Array(4)].map((_, i) => (
            <div key={i} className="loading-shimmer" style={{ height: "100px", marginBottom: "1rem" }} />
          ))}
        </div>
      )}

      {error && (
        <div className="error-box">
          ⚠️ Failed to load stats: {error}
        </div>
      )}

      {stats && (
        <>
          <div className="stats-grid">
            <StatCard
              label="Total Users"
              value={stats.total_users.toLocaleString()}
              icon="👥"
              color="#818cf8"
              sub="Registered accounts"
            />
            <StatCard
              label="Total Trips"
              value={stats.total_trips.toLocaleString()}
              icon="✈️"
              color="#38bdf8"
              sub="All-time plans created"
            />
            <StatCard
              label="Agent Runs"
              value={stats.agent_runs.total.toLocaleString()}
              icon="🤖"
              color="#a78bfa"
              sub="All-time agent executions"
            />
            <StatCard
              label="Success Rate"
              value={`${stats.agent_runs.success_rate_percent}%`}
              icon="✅"
              color="#22c55e"
              sub={`${stats.agent_runs.by_status["success"] ?? 0} successful runs`}
            />
          </div>

          <div className="section">
            <div className="section-title">
              🤖 Agent Run Breakdown
              <span className="badge">{stats.agent_runs.total} total</span>
            </div>
            {Object.entries(stats.agent_runs.by_status).map(([status, count]) => (
              <ProgressBar
                key={status}
                label={status}
                value={count}
                max={stats.agent_runs.total}
                color={statusColors[status] ?? "#94a3b8"}
              />
            ))}
            {Object.keys(stats.agent_runs.by_status).length === 0 && (
              <div style={{ color: "#64748b", fontSize: "0.875rem" }}>
                No agent runs recorded yet.
              </div>
            )}
          </div>

          <div className="section">
            <div className="section-title">📊 Platform Health</div>
            <div className="success-rate">
              <div
                className="rate-circle"
                style={{
                  background: `conic-gradient(#22c55e ${stats.agent_runs.success_rate_percent * 3.6}deg, #1e293b 0deg)`,
                }}
              >
                {stats.agent_runs.success_rate_percent > 0
                  ? `${stats.agent_runs.success_rate_percent}%`
                  : "N/A"}
              </div>
              <div>
                <div className="rate-label">Agent Success Rate</div>
                <div className="rate-val">{stats.agent_runs.success_rate_percent}% successful</div>
                <div style={{ color: "#64748b", fontSize: "0.8rem", marginTop: "0.25rem" }}>
                  Based on {stats.agent_runs.total} total runs
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
