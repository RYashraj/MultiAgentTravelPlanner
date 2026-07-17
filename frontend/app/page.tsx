"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Navbar } from "@/components/Navbar";
import { useAuth } from "@/contexts/AuthContext";
import { Activity, Play, RotateCcw, AlertTriangle, CheckCircle, Database, Server, Clock, Compass } from "lucide-react";

type HealthResponse = {
  status: string;
  service: string;
  database: string;
};

type PingState =
  | { phase: "loading" }
  | { phase: "success"; data: HealthResponse; latency: number }
  | { phase: "error"; message: string };

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";

export default function Home() {
  const { user, isLoading: isAuthLoading } = useAuth();
  const [pingState, setPingState] = useState<PingState>({ phase: "loading" });
  const [refreshKey, setRefreshKey] = useState<number>(0);

  // Simulator State
  const [simStep, setSimStep] = useState<number>(0);
  const [isSimulating, setIsSimulating] = useState<boolean>(false);
  const [simLog, setSimLog] = useState<string[]>([]);

  // Ping Health Hook
  useEffect(() => {
    let cancelled = false;
    const startTime = performance.now();

    async function pingBackend() {
      try {
        const res = await fetch(`${API_BASE_URL}/health`);
        const endTime = performance.now();
        const latency = Math.round(endTime - startTime);

        if (!res.ok) throw new Error(`Backend responded with ${res.status}`);
        const data: HealthResponse = await res.json();
        if (!cancelled) setPingState({ phase: "success", data, latency });
      } catch (err) {
        if (!cancelled) {
          setPingState({
            phase: "error",
            message: err instanceof Error ? err.message : "Could not reach the backend",
          });
        }
      }
    }

    setPingState({ phase: "loading" });
    pingBackend();
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  // Simulator Handler
  const runSimulation = async () => {
    if (isSimulating) return;
    setIsSimulating(true);
    setSimStep(1);
    setSimLog(["[Coordinator] Received request: 'Plan a 4-day trip to Tokyo within $1200'"]);

    const steps = [
      {
        step: 2,
        log: "✔ [Logistics Agent] Scanning flight paths and schedules to HND/NRT. Best deal found: $580 roundtrip.",
      },
      {
        step: 3,
        log: "✔ [Accommodation Agent] Querying hotel vacancies in Shibuya. Found boutique hostel at $65/night.",
      },
      {
        step: 4,
        log: "✔ [Experiences Agent] Curation complete: Senso-ji temple, Shibuya Crossing, and culinary ramen tour.",
      },
      {
        step: 5,
        log: "✔ [Coordinator] Feasibility checks complete. Aggregating final day-by-day markdown...",
      },
    ];

    for (const item of steps) {
      await new Promise((resolve) => setTimeout(resolve, 1200));
      setSimStep(item.step);
      setSimLog((prev) => [...prev, item.log]);
    }
    setIsSimulating(false);
  };

  const resetSimulation = () => {
    setSimStep(0);
    setSimLog([]);
    setIsSimulating(false);
  };

  return (
    <main className="min-h-screen bg-[#0b0f19] text-slate-100 font-sans flex flex-col">
      <div className="absolute top-0 left-1/4 w-[500px] h-[500px] bg-indigo-500/5 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute top-1/3 right-1/4 w-[400px] h-[400px] bg-purple-500/5 rounded-full blur-[100px] pointer-events-none" />

      <Navbar />

      <div className="max-w-6xl w-full mx-auto px-6 py-10 flex-1 flex flex-col space-y-10">
        
        {/* Welcome Banner */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-6 bg-slate-900/40 border border-slate-800/80 rounded-3xl p-6 backdrop-blur-sm">
          <div className="space-y-2">
            <span className="text-[10px] font-mono tracking-wider uppercase bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 px-3 py-1 rounded-full">
              Week 3 Milestone Complete
            </span>
            <h2 className="text-xl font-bold text-white mt-2">VoyagerAI Orchestrator</h2>
            <p className="text-sm text-slate-400 max-w-xl">
              {user
                ? "You are signed in! Start orchestrating your travel conversations in the Dashboard."
                : "Create a mock or real account to start building custom day-by-day itineraries with autonomous agents."}
            </p>
          </div>
          <div className="flex items-center gap-3 shrink-0">
            <button
              onClick={() => setRefreshKey((k) => k + 1)}
              className="p-3 rounded-xl bg-slate-800 hover:bg-slate-750 text-slate-300 hover:text-white transition-all border border-slate-700/60"
              title="Ping backend status"
            >
              <RotateCcw className="w-4 h-4" />
            </button>
            {!isAuthLoading && (
              <Link
                href={user ? "/trips" : "/login"}
                className="px-6 py-3 bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 font-semibold text-sm text-white rounded-xl shadow-lg shadow-indigo-500/20 transition-all whitespace-nowrap"
              >
                {user ? "Go to Dashboard →" : "Sign In to Plan →"}
              </Link>
            )}
          </div>
        </div>

        {/* Section 1: System Status */}
        <section className="space-y-4">
          <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-widest flex items-center gap-2">
            <Activity className="w-4.5 h-4.5 text-indigo-400" />
            System Status
          </h3>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* Backend Gateway */}
            <div className="bg-slate-900/30 border border-slate-800/80 rounded-2xl p-5 flex items-start gap-4">
              <div className="p-3 rounded-xl bg-indigo-500/10 text-indigo-400">
                <Server className="w-5 h-5" />
              </div>
              <div className="space-y-1">
                <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">FastAPI Gateway</h4>
                {pingState.phase === "loading" && <span className="text-xs text-slate-500">Checking...</span>}
                {pingState.phase === "error" && (
                  <span className="text-xs text-red-400 flex items-center gap-1.5 mt-1 font-semibold">
                    <AlertTriangle className="w-3.5 h-3.5" /> Offline
                  </span>
                )}
                {pingState.phase === "success" && (
                  <span className="text-xs text-emerald-400 flex items-center gap-1.5 mt-1 font-semibold">
                    <CheckCircle className="w-3.5 h-3.5" /> Connected
                  </span>
                )}
              </div>
            </div>

            {/* Database Layer */}
            <div className="bg-slate-900/30 border border-slate-800/80 rounded-2xl p-5 flex items-start gap-4">
              <div className="p-3 rounded-xl bg-purple-500/10 text-purple-400">
                <Database className="w-5 h-5" />
              </div>
              <div className="space-y-1">
                <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Database Connection</h4>
                {pingState.phase === "loading" && <span className="text-xs text-slate-500">Checking...</span>}
                {pingState.phase === "error" && (
                  <span className="text-xs text-red-400 flex items-center gap-1.5 mt-1 font-semibold">
                    <AlertTriangle className="w-3.5 h-3.5" /> Unreachable
                  </span>
                )}
                {pingState.phase === "success" && (
                  <span className="text-xs text-emerald-400 flex items-center gap-1.5 mt-1 font-semibold">
                    <CheckCircle className="w-3.5 h-3.5" /> {pingState.data.database}
                  </span>
                )}
              </div>
            </div>

            {/* API Latency */}
            <div className="bg-slate-900/30 border border-slate-800/80 rounded-2xl p-5 flex items-start gap-4">
              <div className="p-3 rounded-xl bg-teal-500/10 text-teal-400">
                <Clock className="w-5 h-5" />
              </div>
              <div className="space-y-1">
                <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">API Latency</h4>
                {pingState.phase === "loading" && <span className="text-xs text-slate-500">Checking...</span>}
                {pingState.phase === "error" && <span className="text-xs text-slate-500">N/A</span>}
                {pingState.phase === "success" && (
                  <span className="text-xs text-teal-400 font-semibold mt-1 block">
                    {pingState.latency} ms
                  </span>
                )}
              </div>
            </div>
          </div>
        </section>

        {/* Section 2: Pipeline Simulator */}
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-widest flex items-center gap-2">
              <Compass className="w-4.5 h-4.5 text-indigo-400" />
              Interactive Multi-Agent Simulation
            </h3>
            <div className="flex items-center gap-2">
              {simStep > 0 && (
                <button
                  onClick={resetSimulation}
                  className="px-3 py-1.5 rounded-lg border border-slate-800 bg-slate-900 hover:bg-slate-850 text-slate-300 hover:text-white text-xs transition-all flex items-center gap-1.5"
                >
                  <RotateCcw className="w-3 h-3" /> Reset
                </button>
              )}
              <button
                onClick={runSimulation}
                disabled={isSimulating}
                className="px-4 py-1.5 bg-indigo-500 hover:bg-indigo-600 disabled:bg-indigo-950/45 disabled:text-slate-500 disabled:cursor-not-allowed text-xs text-white rounded-lg transition-all flex items-center gap-1.5 shadow-lg shadow-indigo-500/15"
              >
                <Play className="w-3 h-3" /> {isSimulating ? "Simulating..." : "Run Offline Simulation"}
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            
            {/* Visual Agent Steps Grid */}
            <div className="bg-slate-900/35 border border-slate-850 rounded-3xl p-6 space-y-4">
              <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Execution Flow Nodes</h4>
              
              <div className="space-y-4">
                {/* Node 1 */}
                <div className={`p-4 rounded-2xl border transition-all flex items-start gap-4 ${
                  simStep >= 1 ? "bg-slate-900/60 border-indigo-500/30" : "bg-slate-950/20 border-slate-900/50 opacity-40"
                }`}>
                  <div className={`w-8 h-8 rounded-xl flex items-center justify-center text-xs font-mono font-bold shrink-0 ${
                    simStep >= 1 ? "bg-indigo-500/15 text-indigo-400 border border-indigo-500/30" : "bg-slate-800 text-slate-500"
                  }`}>
                    01
                  </div>
                  <div>
                    <h5 className="text-xs font-bold text-slate-200">Coordinator Agent Node</h5>
                    <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">
                      Accepts query, locks graph schema parameters, and boots up sub-agent states.
                    </p>
                  </div>
                </div>

                {/* Node 2 */}
                <div className={`p-4 rounded-2xl border transition-all flex items-start gap-4 ${
                  simStep >= 2 ? "bg-slate-900/60 border-indigo-500/30" : "bg-slate-950/20 border-slate-900/50 opacity-40"
                }`}>
                  <div className={`w-8 h-8 rounded-xl flex items-center justify-center text-xs font-mono font-bold shrink-0 ${
                    simStep >= 2 ? "bg-indigo-500/15 text-indigo-400 border border-indigo-500/30" : "bg-slate-800 text-slate-500"
                  }`}>
                    02
                  </div>
                  <div>
                    <h5 className="text-xs font-bold text-slate-200">Logistics & Accommodation Nodes</h5>
                    <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">
                      Resolves flights routing schedules and lodging vacancies dynamically.
                    </p>
                  </div>
                </div>

                {/* Node 3 */}
                <div className={`p-4 rounded-2xl border transition-all flex items-start gap-4 ${
                  simStep >= 3 ? "bg-slate-900/60 border-indigo-500/30" : "bg-slate-950/20 border-slate-900/50 opacity-40"
                }`}>
                  <div className={`w-8 h-8 rounded-xl flex items-center justify-center text-xs font-mono font-bold shrink-0 ${
                    simStep >= 3 ? "bg-indigo-500/15 text-indigo-400 border border-indigo-500/30" : "bg-slate-800 text-slate-500"
                  }`}>
                    03
                  </div>
                  <div>
                    <h5 className="text-xs font-bold text-slate-200">Experiences & Budget Nodes</h5>
                    <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">
                      Parses sight-seeing activities and runs strict limit calculations.
                    </p>
                  </div>
                </div>

                {/* Node 4 */}
                <div className={`p-4 rounded-2xl border transition-all flex items-start gap-4 ${
                  simStep >= 5 ? "bg-slate-900/60 border-emerald-500/25" : "bg-slate-950/20 border-slate-900/50 opacity-40"
                }`}>
                  <div className={`w-8 h-8 rounded-xl flex items-center justify-center text-xs font-mono font-bold shrink-0 ${
                    simStep >= 5 ? "bg-emerald-500/15 text-emerald-450 border border-emerald-500/30" : "bg-slate-800 text-slate-500"
                  }`}>
                    04
                  </div>
                  <div>
                    <h5 className="text-xs font-bold text-slate-200">Final Compilation Node</h5>
                    <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">
                      Aggregates metrics and prints the finalized Day-by-Day travel itinerary.
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* Output Logs Console */}
            <div className="flex flex-col space-y-4">
              <div className="bg-slate-950 border border-slate-850 rounded-3xl p-6 flex-1 flex flex-col font-mono relative overflow-hidden min-h-[300px]">
                <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-indigo-500 via-purple-500 to-emerald-500" />
                <div className="flex items-center gap-2 text-slate-500 text-[10px] border-b border-slate-900 pb-3 mb-4 select-none">
                  <span className="w-2.5 h-2.5 rounded-full bg-red-500/20 border border-red-500/30" />
                  <span className="w-2.5 h-2.5 rounded-full bg-yellow-500/20 border border-yellow-500/30" />
                  <span className="w-2.5 h-2.5 rounded-full bg-green-500/20 border border-green-500/30" />
                  <span className="ml-2">agent_execution_logs.log</span>
                </div>

                <div className="flex-1 space-y-3 overflow-y-auto text-xs scrollbar-thin scrollbar-thumb-slate-800 scrollbar-track-transparent">
                  {simLog.length === 0 && (
                    <div className="text-slate-600 italic select-none">Console idle. Hit &quot;Run Offline Simulation&quot; to test graph transitions.</div>
                  )}
                  {simLog.map((log, index) => (
                    <div key={index} className="flex gap-2">
                      <span className="text-indigo-500 select-none">&gt;</span>
                      <span className={log.startsWith("✔") ? "text-emerald-400 font-semibold" : "text-slate-350"}>
                        {log}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {simStep === 5 && !isSimulating && (
                <div className="bg-slate-900/50 border border-emerald-500/30 rounded-2xl p-5 animate-fade-in space-y-2">
                  <div className="flex items-center gap-2 text-emerald-450 text-xs font-semibold">
                    <CheckCircle className="w-4 h-4" /> Itinerary Compiled Successfully!
                  </div>
                  <div className="text-[11px] text-slate-400 space-y-1 mt-2">
                    <p className="font-semibold text-slate-300">🗼 Tokyo 4-Day Plan Overview:</p>
                    <p>• Flight: Roundtrip NRT ($580)</p>
                    <p>• Stay: Shibuya Boutique Stay ($260)</p>
                    <p>• Buffer remaining: $360 for shopping & dining</p>
                  </div>
                </div>
              )}
            </div>

          </div>
        </section>

      </div>

      <footer className="border-t border-slate-900/60 py-6 text-center text-xs text-slate-600 bg-slate-950/20 mt-12">
        <p>© 2026 VoyagerAI. Autonomous Multi-Agent AI Travel Planner.</p>
      </footer>
    </main>
  );
}
