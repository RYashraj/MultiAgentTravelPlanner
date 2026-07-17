"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { signOut, getSessionToken, getUserEmail } from "../lib/supabase";
import { LogOut, User, Compass, MapPin } from "lucide-react";
import TripCreationModal from "../components/TripCreationModal";

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
  const router = useRouter();
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [userEmail, setUserEmail] = useState<string | null>(null);
  const [pingState, setPingState] = useState<PingState>({ phase: "loading" });
  const [simStep, setSimStep] = useState<number>(0);
  const [isSimulating, setIsSimulating] = useState<boolean>(false);
  const [simLog, setSimLog] = useState<string[]>([]);
  const [refreshKey, setRefreshKey] = useState<number>(0);

  // Trips State
  const [trips, setTrips] = useState<any[]>([]);
  const [selectedTrip, setSelectedTrip] = useState<any | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [tripsLoading, setTripsLoading] = useState(false);

  useEffect(() => {
    const token = getSessionToken();
    if (!token) {
      router.push("/login");
    } else {
      setIsAuthenticated(true);
      setUserEmail(getUserEmail());
    }
  }, [router]);

  useEffect(() => {
    if (!isAuthenticated) return;

    async function fetchTrips() {
      setTripsLoading(true);
      const token = getSessionToken();
      if (!token) return;

      try {
        const res = await fetch(`${API_BASE_URL}/trips`, {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });
        if (res.ok) {
          const data = await res.json();
          setTrips(data);
          if (data.length > 0) {
            setSelectedTrip(data[0]);
          }
        }
      } catch (err) {
        console.error("Failed to load trips", err);
      } finally {
        setTripsLoading(false);
      }
    }

    fetchTrips();
  }, [isAuthenticated]);

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

  const handleSignOut = async () => {
    await signOut();
    router.push("/login");
  };

  const handleTripCreated = (newTrip: any) => {
    setTrips((prev) => [newTrip, ...prev]);
    setSelectedTrip(newTrip);
  };

  const handleSelectTrip = (trip: any) => {
    setSelectedTrip(trip);
    setSimStep(0);
    setIsSimulating(false);
    setSimLog([]);
  };

  // Simulation steps for the Agent pipeline
  const simulationSteps = [
    {
      title: "User Input & Intent",
      desc: `Supervisor receives: 'Plan a 4-day trip to ${selectedTrip?.destination || "Destination"}, budget $1200'`,
      agent: "Supervisor Agent",
      color: "border-purple-500 text-purple-400",
      bg: "bg-purple-950/20",
    },
    {
      title: "Transport & Routing",
      desc: `Logistics Agent retrieves flights (Amadeus API) & optimizes routes to ${selectedTrip?.destination || "Destination"}`,
      agent: "Logistics Agent",
      color: "border-blue-500 text-blue-400",
      bg: "bg-blue-950/20",
    },
    {
      title: "Lodging Discovery",
      desc: `Accommodation Agent queries stays matching budget restrictions in ${selectedTrip?.destination || "Destination"}`,
      agent: "Accommodation Agent",
      color: "border-teal-500 text-teal-400",
      bg: "bg-teal-950/20",
    },
    {
      title: "Local Experiences",
      desc: `Experience Agent checks top landmarks & food via Google Places API in ${selectedTrip?.destination || "Destination"}`,
      agent: "Experience Agent",
      color: "border-amber-500 text-amber-400",
      bg: "bg-amber-950/20",
    },
    {
      title: "Consolidated Plan",
      desc: `Supervisor validates constraint satisfaction & compiles markdown plan for ${selectedTrip?.destination || "Destination"}`,
      agent: "Supervisor Agent",
      color: "border-emerald-500 text-emerald-400",
      bg: "bg-emerald-950/20",
    },
  ];

  const startSimulation = () => {
    if (isSimulating) return;
    setIsSimulating(true);
    setSimStep(0);
    setSimLog(["[Orchestrator] Received user prompt. Parsing criteria..."]);

    const runNextStep = (step: number) => {
      if (step >= simulationSteps.length) {
        setIsSimulating(false);
        setSimLog((prev) => [...prev, "✔ Itinerary generated successfully!"]);
        return;
      }

      setSimStep(step + 1);
      const stepMessages = [
        `[Logistics] Fetching flights to ${selectedTrip?.destination || "Destination"}. Found optimal route.`,
        `[Accommodation] Searching stays. Found clean boutique hotel in central ${selectedTrip?.destination || "Destination"}.`,
        `[Experiences] Mapping daily activities inside ${selectedTrip?.destination || "Destination"}.`,
        `[Orchestrator] Budget verified for ${selectedTrip?.destination || "Destination"}. Structuring daily itinerary...`,
      ];

      if (step < stepMessages.length) {
        setSimLog((prev) => [...prev, stepMessages[step]]);
      }

      setTimeout(() => runNextStep(step + 1), 2200);
    };

    setTimeout(() => runNextStep(0), 1800);
  };

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-[#0b0f19] flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-indigo-500" />
      </div>
    );
  }

  return (
    <main className="min-h-screen bg-[#0b0f19] text-slate-100 font-sans flex flex-col selection:bg-indigo-500/30">
      {/* Header and Background Glows */}
      <div className="absolute top-0 left-1/4 w-[500px] h-[500px] bg-indigo-500/10 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute top-1/3 right-1/4 w-[400px] h-[400px] bg-purple-500/10 rounded-full blur-[100px] pointer-events-none" />

      <header className="border-b border-slate-800/80 bg-slate-950/40 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 py-4 flex justify-between items-center">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/30">
              <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight bg-gradient-to-r from-white to-slate-300 bg-clip-text text-transparent">
                VoyagerAI
              </h1>
              <p className="text-[10px] text-indigo-400 font-mono tracking-wider uppercase">Multi-Agent Planner</p>
            </div>
          </div>

          <div className="flex items-center gap-4">
            {userEmail && (
              <span className="text-xs text-slate-400 bg-slate-900/80 border border-slate-800/80 px-3 py-1 rounded-full flex items-center gap-1.5">
                <User className="w-3.5 h-3.5 text-indigo-400" />
                {userEmail}
              </span>
            )}
            <button
              onClick={handleSignOut}
              className="text-xs bg-red-950/20 hover:bg-red-900/30 text-red-200 border border-red-500/20 hover:border-red-500/40 px-3 py-1.5 rounded-xl transition-all flex items-center gap-1.5 font-medium"
            >
              <LogOut className="w-3.5 h-3.5" />
              Sign Out
            </button>
            <span className="text-xs bg-slate-800 text-slate-400 px-3 py-1 rounded-full border border-slate-700/50">
              Week 3 Milestone
            </span>
            <button
              onClick={() => setRefreshKey((k) => k + 1)}
              className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition-all border border-slate-700/60"
              title="Refresh Infrastructure Status"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.21 8H17" />
              </svg>
            </button>
          </div>
        </div>
      </header>

      {/* Main Split Screen Sidebar & Workspace Layout */}
      <div className="flex flex-1 max-w-7xl mx-auto w-full px-6 py-10 gap-8">
        
        {/* Left Sidebar */}
        <aside className="w-72 border-r border-slate-800/40 pr-8 flex flex-col space-y-6 shrink-0 z-10">
          <div className="flex justify-between items-center">
            <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Your Trips</h2>
            <span className="text-[10px] bg-indigo-500/10 text-indigo-400 font-mono px-2 py-0.5 rounded-full border border-indigo-500/20">
              {trips.length}
            </span>
          </div>

          <button
            onClick={() => setIsModalOpen(true)}
            className="w-full py-3 bg-indigo-600/10 hover:bg-indigo-600/20 border border-indigo-500/30 hover:border-indigo-500/50 rounded-xl text-indigo-300 font-medium text-sm transition-all flex items-center justify-center gap-2 group animate-pulse"
          >
            <Compass className="w-4 h-4 group-hover:rotate-45 transition-transform" />
            Plan New Trip
          </button>

          <div className="space-y-2.5 max-h-[calc(100vh-280px)] overflow-y-auto pr-1">
            {tripsLoading ? (
              <div className="flex items-center justify-center py-8">
                <div className="animate-spin rounded-full h-5 w-5 border-t-2 border-indigo-500" />
              </div>
            ) : trips.length === 0 ? (
              <div className="text-center py-10 bg-slate-900/10 border border-slate-800/40 rounded-2xl p-4">
                <p className="text-xs text-slate-500 italic">No trips planned yet.</p>
              </div>
            ) : (
              trips.map((trip) => {
                const isSelected = selectedTrip?.id === trip.id;
                return (
                  <button
                    key={trip.id}
                    onClick={() => handleSelectTrip(trip)}
                    className={`w-full text-left p-4 rounded-xl border transition-all flex flex-col gap-1.5 ${
                      isSelected
                        ? "border-indigo-500/50 bg-indigo-950/20 text-white shadow-md shadow-indigo-950/20"
                        : "border-slate-800/50 bg-slate-900/20 text-slate-400 hover:border-slate-800 hover:bg-slate-900/40 hover:text-slate-200"
                    }`}
                  >
                    <div className="flex justify-between items-center">
                      <span className="font-semibold text-sm truncate">{trip.destination}</span>
                      <span className={`text-[9px] font-mono uppercase px-1.5 py-0.5 rounded ${
                        trip.status === "booked"
                          ? "bg-emerald-950/40 text-emerald-400 border border-emerald-500/20"
                          : trip.status === "ready"
                          ? "bg-teal-950/40 text-teal-400 border border-teal-500/20"
                          : "bg-slate-800 text-slate-400"
                      }`}>
                        {trip.status}
                      </span>
                    </div>
                    <span className="text-[10px] text-slate-500 font-mono">
                      {new Date(trip.created_at).toLocaleDateString()}
                    </span>
                  </button>
                );
              })
            )}
          </div>
        </aside>

        {/* Right Workspace panel */}
        <div className="flex-1 space-y-10 min-w-0">
          {!selectedTrip ? (
            /* Empty State */
            <div className="flex flex-col items-center justify-center py-24 text-center space-y-5 bg-slate-900/10 border border-slate-800/40 rounded-3xl p-8 backdrop-blur-sm">
              <div className="w-16 h-16 rounded-2xl bg-indigo-500/5 flex items-center justify-center border border-indigo-500/10 shadow-lg shadow-indigo-500/5">
                <Compass className="w-8 h-8 text-indigo-400 animate-pulse" />
              </div>
              <div className="space-y-1 max-w-sm">
                <h3 className="font-semibold text-slate-200 text-base">Select a trip</h3>
                <p className="text-xs text-slate-400 leading-relaxed">
                  Select an active trip from the sidebar or click &quot;Plan New Trip&quot; to begin planning your next travel adventure.
                </p>
              </div>
              <button
                onClick={() => setIsModalOpen(true)}
                className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white font-medium text-xs rounded-xl shadow-lg shadow-indigo-500/20 transition-all"
              >
                Plan New Trip
              </button>
            </div>
          ) : (
            /* Active Trip Workspace */
            <>
              {/* Section 1: System Status */}
              <section className="space-y-4">
                <h2 className="text-lg font-semibold text-slate-300 flex items-center gap-2">
                  <span className="w-1.5 h-4 bg-indigo-500 rounded-full" />
                  Infrastructure Connection Status
                </h2>

                <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                  {/* API Health */}
                  <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 backdrop-blur-sm relative overflow-hidden transition-all hover:border-slate-700/80">
                    <div className="flex justify-between items-start mb-3">
                      <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">FastAPI Endpoint</span>
                      <span className="text-[10px] text-slate-500 font-mono">PORT 8000</span>
                    </div>
                    <div className="flex items-baseline gap-2 mt-2">
                      <span className="text-2xl font-bold font-mono">/health</span>
                    </div>
                    <div className="mt-4 flex items-center gap-2">
                      {pingState.phase === "loading" && (
                        <>
                          <span className="w-2.5 h-2.5 rounded-full bg-slate-600 animate-pulse" />
                          <span className="text-sm text-slate-500">Pinging backend...</span>
                        </>
                      )}
                      {pingState.phase === "success" && (
                        <>
                          <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-ping absolute" />
                          <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
                          <span className="text-sm font-medium text-emerald-400">API UP ({pingState.latency}ms)</span>
                        </>
                      )}
                      {pingState.phase === "error" && (
                        <>
                          <span className="w-2.5 h-2.5 rounded-full bg-red-500" />
                          <span className="text-sm font-medium text-red-400">UNREACHABLE</span>
                        </>
                      )}
                    </div>
                  </div>

                  {/* Database */}
                  <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 backdrop-blur-sm relative overflow-hidden transition-all hover:border-slate-700/80">
                    <div className="flex justify-between items-start mb-3">
                      <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Database Status</span>
                      <span className="text-[10px] text-slate-500 font-mono">SQLite (Local)</span>
                    </div>
                    <div className="flex items-baseline gap-2 mt-2">
                      <span className="text-2xl font-bold font-mono">voyagerai.db</span>
                    </div>
                    <div className="mt-4 flex items-center gap-2">
                      {pingState.phase === "loading" && (
                        <>
                          <span className="w-2.5 h-2.5 rounded-full bg-slate-600 animate-pulse" />
                          <span className="text-sm text-slate-500">Verifying DB connection...</span>
                        </>
                      )}
                      {pingState.phase === "success" && (
                        <>
                          <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
                          <span className="text-sm font-medium text-emerald-400">
                            DB {pingState.data.database.toUpperCase()}
                          </span>
                        </>
                      )}
                      {pingState.phase === "error" && (
                        <>
                          <span className="w-2.5 h-2.5 rounded-full bg-red-500" />
                          <span className="text-sm font-medium text-red-400">DB DISCONNECTED</span>
                        </>
                      )}
                    </div>
                  </div>

                  {/* Redis Cache */}
                  <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 backdrop-blur-sm relative overflow-hidden transition-all hover:border-slate-700/80">
                    <div className="flex justify-between items-start mb-3">
                      <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">CADASTRAL CACHE</span>
                      <span className="text-[10px] text-slate-500 font-mono">Redis</span>
                    </div>
                    <div className="flex items-baseline gap-2 mt-2">
                      <span className="text-2xl font-bold font-mono">6379</span>
                    </div>
                    <div className="mt-4 flex items-center gap-2">
                      <span className="w-2.5 h-2.5 rounded-full bg-amber-500" />
                      <span className="text-sm font-medium text-amber-400">DOCKER IDLE (LOCAL BYPASS)</span>
                    </div>
                  </div>

                  {/* Environment */}
                  <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 backdrop-blur-sm relative overflow-hidden transition-all hover:border-slate-700/80">
                    <div className="flex justify-between items-start mb-3">
                      <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Active Environment</span>
                      <span className="text-[10px] text-slate-500 font-mono">APP MODE</span>
                    </div>
                    <div className="flex items-baseline gap-2 mt-2">
                      <span className="text-2xl font-bold font-mono text-indigo-400">development</span>
                    </div>
                    <div className="mt-4 flex items-center gap-2">
                      <span className="w-2.5 h-2.5 rounded-full bg-indigo-500" />
                      <span className="text-sm font-medium text-indigo-400">CORS ALLOWED (:3000)</span>
                    </div>
                  </div>
                </div>
              </section>

              {/* Section 2: Interactive Demo Simulator */}
              <section className="space-y-6">
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div>
                    <h2 className="text-lg font-semibold text-slate-300 flex items-center gap-2">
                      <span className="w-1.5 h-4 bg-purple-500 rounded-full" />
                      Interactive Core Pipeline Simulator (Proposed)
                    </h2>
                    <p className="text-sm text-slate-400 mt-1">
                      Visualize how VoyagerAI will resolve your query for <strong className="text-indigo-400">{selectedTrip.destination}</strong>.
                    </p>
                  </div>
                  <div>
                    <button
                      onClick={startSimulation}
                      disabled={isSimulating}
                      className="w-full md:w-auto px-5 py-2.5 bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 disabled:from-indigo-900/50 disabled:to-purple-900/50 disabled:cursor-not-allowed font-medium text-sm text-white rounded-xl shadow-lg shadow-indigo-500/25 transition-all flex items-center justify-center gap-2"
                    >
                      {isSimulating ? (
                        <>
                          <svg className="animate-spin -ml-1 mr-3 h-4.5 w-4.5 text-white" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                          </svg>
                          Executing Pipeline...
                        </>
                      ) : (
                        <>
                          <svg className="w-4.5 h-4.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                            <path strokeLinecap="round" strokeLinejoin="round" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                          </svg>
                          Run Sample Agent Query
                        </>
                      )}
                    </button>
                  </div>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                  {/* Visual Agent Workflow Flowchart */}
                  <div className="lg:col-span-2 space-y-4">
                    <div className="bg-slate-900/40 border border-slate-800/80 rounded-2xl p-6 relative">
                      <div className="space-y-4 relative">
                        {simulationSteps.map((step, idx) => {
                          const isStepActive = simStep === idx + 1;
                          const isStepCompleted = simStep > idx + 1;
                          return (
                            <div
                              key={idx}
                              className={`flex items-start gap-4 p-4 rounded-xl border transition-all duration-500 ${
                                isStepActive
                                  ? `${step.color} ${step.bg} scale-[1.01] shadow-md border-opacity-100`
                                  : isStepCompleted
                                  ? "border-slate-800/50 bg-slate-900/10 text-slate-500 opacity-60"
                                  : "border-slate-800/30 text-slate-600 opacity-40"
                              }`}
                            >
                              <div className="flex flex-col items-center">
                                <div className={`w-8 h-8 rounded-full border flex items-center justify-center font-bold text-sm ${
                                  isStepActive
                                    ? "bg-slate-900 animate-pulse border-indigo-400 text-indigo-400"
                                    : isStepCompleted
                                    ? "bg-slate-950 border-slate-700 text-slate-500"
                                    : "bg-slate-950 border-slate-800 text-slate-700"
                                }`}>
                                  {idx + 1}
                                </div>
                                {idx < simulationSteps.length - 1 && (
                                  <div className={`w-0.5 h-10 my-1 ${
                                    isStepCompleted ? "bg-indigo-900/40" : "bg-slate-900/20"
                                  }`} />
                                )}
                              </div>

                              <div className="space-y-1">
                                <div className="flex items-center gap-2">
                                  <span className="font-semibold text-sm text-slate-200">{step.title}</span>
                                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-950 text-slate-400">
                                    {step.agent}
                                  </span>
                                </div>
                                <p className="text-xs leading-relaxed text-slate-400">{step.desc}</p>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </div>

                  {/* Execution Console Terminal Logs */}
                  <div className="flex flex-col space-y-4">
                    <div className="bg-slate-950 border border-slate-800/80 rounded-2xl p-5 flex-1 flex flex-col font-mono relative overflow-hidden">
                      <div className="absolute top-0 left-0 right-0 h-1.5 bg-gradient-to-r from-indigo-500 via-purple-500 to-teal-500" />
                      <div className="flex items-center gap-2 text-xs text-slate-500 border-b border-slate-800/60 pb-3 mb-4">
                        <span className="w-3 h-3 rounded-full bg-red-500/20 border border-red-500/50" />
                        <span className="w-3 h-3 rounded-full bg-amber-500/20 border border-amber-500/50" />
                        <span className="w-3 h-3 rounded-full bg-green-500/20 border border-green-500/50" />
                        <span className="ml-2">agent_orchestration_logs.sh</span>
                      </div>

                      <div className="flex-1 space-y-2.5 overflow-y-auto text-xs scrollbar-thin scrollbar-thumb-slate-800 scrollbar-track-transparent">
                        {simLog.length === 0 && (
                          <div className="text-slate-600 italic">Console idle. Hit &quot;Run Sample Agent Query&quot; to start simulation.</div>
                        )}
                        {simLog.map((log, index) => (
                          <div key={index} className="flex gap-2">
                            <span className="text-slate-600 select-none">&gt;</span>
                            <span className={log.startsWith("✔") ? "text-emerald-400 font-semibold" : "text-slate-300"}>
                              {log}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Sample output preview */}
                    {simStep === 5 && !isSimulating && (
                      <div className="bg-slate-900/60 border border-emerald-500/40 rounded-2xl p-5 animate-fade-in space-y-3">
                        <div className="flex items-center gap-2 text-emerald-400">
                          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                          </svg>
                          <span className="text-sm font-semibold">Itinerary Mock Complete!</span>
                        </div>
                        <div className="text-xs text-slate-300 space-y-1">
                          <p className="font-semibold text-slate-200">🗼 {selectedTrip.destination} 4-Day Plan Overview:</p>
                          <p>• Flight: Roundtrip Route ($580)</p>
                          <p>• Stay: Boutique Central Stay ($260)</p>
                          <p>• Buffer remaining: $360 for dining/shopping</p>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </section>
            </>
          )}
        </div>
      </div>

      <footer className="border-t border-slate-900 py-6 text-center text-xs text-slate-600 mt-auto animate-fade-in">
        <p>© 2026 VoyagerAI. Built for Multi-Agent Travel Planner Skeleton Demo.</p>
      </footer>

      {/* Trip Creation Modal */}
      <TripCreationModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onTripCreated={handleTripCreated}
      />
    </main>
  );
}

