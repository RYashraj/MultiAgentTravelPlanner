"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { signOut, getSessionToken, getUserEmail } from "../lib/supabase";
import { LogOut, User, Compass, MapPin, Send, Terminal, Calendar, Loader } from "lucide-react";
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
  const [refreshKey, setRefreshKey] = useState<number>(0);

  // Trips State
  const [trips, setTrips] = useState<any[]>([]);
  const [selectedTrip, setSelectedTrip] = useState<any | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [tripsLoading, setTripsLoading] = useState(false);

  // Chat and Itinerary State
  const [messages, setMessages] = useState<any[]>([]);
  const [inputMessage, setInputMessage] = useState("");
  const [itineraries, setItineraries] = useState<any[]>([]);
  const [itinerariesLoading, setItinerariesLoading] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [activeLogs, setActiveLogs] = useState<string[]>([]);

  // 1. Auth Hook
  useEffect(() => {
    const token = getSessionToken();
    if (!token) {
      router.push("/login");
    } else {
      setIsAuthenticated(true);
      setUserEmail(getUserEmail());
    }
  }, [router]);

  // 2. Fetch Trips Hook
  useEffect(() => {
    if (!isAuthenticated) return;

    async function fetchTrips() {
      setTripsLoading(true);
      const token = getSessionToken();
      if (!token) return;

      try {
        const res = await fetch(`${API_BASE_URL}/trips`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.ok) {
          const data = await res.json();
          setTrips(data);
          if (data.length > 0) {
            setSelectedTrip(data[0]);
            fetchMessages(data[0].id);
            fetchItineraries(data[0].id);
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

  // 3. Ping Health Hook
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

  // API Call Helpers
  const fetchMessages = async (tripId: string) => {
    const token = getSessionToken();
    if (!token) return;
    try {
      const res = await fetch(`${API_BASE_URL}/trips/${tripId}/messages`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setMessages(data);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const fetchItineraries = async (tripId: string) => {
    setItinerariesLoading(true);
    const token = getSessionToken();
    if (!token) return;
    try {
      const res = await fetch(`${API_BASE_URL}/trips/${tripId}/itineraries`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setItineraries(data);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setItinerariesLoading(false);
    }
  };

  const handleSignOut = async () => {
    await signOut();
    router.push("/login");
  };

  const handleTripCreated = (newTrip: any) => {
    setTrips((prev) => [newTrip, ...prev]);
    setSelectedTrip(newTrip);
    setMessages([]);
    setItineraries([]);
    setActiveLogs([]);
  };

  const handleSelectTrip = (trip: any) => {
    setSelectedTrip(trip);
    setMessages([]);
    setItineraries([]);
    setActiveLogs([]);
    setInputMessage("");
    setIsSending(false);
    fetchMessages(trip.id);
    fetchItineraries(trip.id);
  };

  // 4. Send Message and Parse SSE Stream
  const sendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputMessage.trim() || !selectedTrip || isSending) return;

    const userText = inputMessage.trim();
    setInputMessage("");
    setIsSending(true);
    setActiveLogs([]);

    // Optimistically append user message
    const tempUserMsg = {
      id: "temp-user-msg",
      sender: "user",
      content: userText,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempUserMsg]);

    const assistantMsgId = "temp-assistant-msg";
    const token = getSessionToken();
    if (!token) return;

    try {
      const response = await fetch(`${API_BASE_URL}/trips/${selectedTrip.id}/messages?stream=true`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ content: userText }),
      });

      if (!response.ok) {
        throw new Error("Failed to send message");
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) throw new Error("No stream reader available");

      let buffer = "";
      let tempAssistantContent = "";

      // Append assistant placeholder bubble
      setMessages((prev) => [
        ...prev,
        {
          id: assistantMsgId,
          sender: "assistant",
          content: "",
          created_at: new Date().toISOString(),
          isStreaming: true,
        },
      ]);

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() || "";

        for (const part of parts) {
          if (!part.trim()) continue;

          const lines = part.split("\n");
          let eventType = "";
          let dataStr = "";

          for (const line of lines) {
            if (line.startsWith("event: ")) {
              eventType = line.substring(7).trim();
            } else if (line.startsWith("data: ")) {
              dataStr = line.substring(6).trim();
            }
          }

          if (eventType && dataStr) {
            try {
              const data = JSON.parse(dataStr);
              if (eventType === "user_message") {
                // Swap temp user message
                setMessages((prev) =>
                  prev.map((msg) => (msg.id === "temp-user-msg" ? data : msg))
                );
              } else if (eventType === "agent_log") {
                // Record sub-agent traces
                setActiveLogs((prev) => [...prev, `[${data.agent}] ${data.content}`]);
              } else if (eventType === "message_chunk") {
                // Append word token
                tempAssistantContent += data.content;
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMsgId
                      ? { ...msg, content: tempAssistantContent }
                      : msg
                  )
                );
              } else if (eventType === "message_complete") {
                // Finalize assistant bubble
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMsgId
                      ? { id: data.id, sender: "assistant", content: data.content, created_at: data.created_at }
                      : msg
                  )
                );
                // Reload stored itineraries to display newly saved day blocks
                fetchItineraries(selectedTrip.id);
              }
            } catch (err) {
              console.error("Failed to parse event", err);
            }
          }
        }
      }
    } catch (err) {
      console.error(err);
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantMsgId
            ? { ...msg, content: "Error: Failed to fetch orchestrator response. Check keys.", isError: true }
            : msg
        )
      );
    } finally {
      setIsSending(false);
    }
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
      {/* Header Gradients */}
      <div className="absolute top-0 left-1/4 w-[500px] h-[500px] bg-indigo-500/5 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute top-1/3 right-1/4 w-[400px] h-[400px] bg-purple-500/5 rounded-full blur-[100px] pointer-events-none" />

      {/* Top sticky Navbar */}
      <header className="border-b border-slate-900 bg-slate-950/40 backdrop-blur-md sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-6 py-4 flex justify-between items-center">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/30">
              <Compass className="w-5 h-5 text-white" />
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
      <div className="flex flex-1 max-w-7xl mx-auto w-full px-6 py-8 gap-8 overflow-hidden">
        
        {/* Left Sidebar: Trips List */}
        <aside className="w-72 border-r border-slate-900 pr-8 flex flex-col space-y-6 shrink-0">
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

          <div className="space-y-2.5 flex-1 overflow-y-auto pr-1 select-none">
            {tripsLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader className="w-5 h-5 text-indigo-400 animate-spin" />
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

        {/* Center Panel: Active Chat Workspace */}
        <div className="flex-1 flex flex-col min-w-0 bg-slate-950/20 border border-slate-900 rounded-3xl overflow-hidden relative">
          {!selectedTrip ? (
            /* Empty State */
            <div className="flex flex-col items-center justify-center flex-1 text-center p-8">
              <Compass className="w-12 h-12 text-slate-600 animate-pulse mb-4" />
              <h3 className="font-semibold text-slate-300 text-base">No Trip Selected</h3>
              <p className="text-xs text-slate-500 max-w-xs mt-1.5 leading-relaxed">
                Select an active trip from the sidebar or click &quot;Plan New Trip&quot; to compile itineraries.
              </p>
            </div>
          ) : (
            /* Real-Time Chat Workspace */
            <div className="flex-1 flex flex-col overflow-hidden">
              {/* Chat Header */}
              <div className="p-5 border-b border-slate-900 bg-slate-900/10 flex justify-between items-center">
                <div className="flex items-center gap-2">
                  <MapPin className="w-4 h-4 text-indigo-400" />
                  <span className="font-semibold text-sm text-slate-200">{selectedTrip.destination}</span>
                  <span className="text-[9px] font-mono uppercase bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 px-1.5 py-0.5 rounded ml-2">
                    {selectedTrip.status}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`w-2 h-2 rounded-full ${pingState.phase === "success" ? "bg-emerald-500" : "bg-red-500"}`} />
                  <span className="text-[10px] text-slate-500 font-mono">API STATUS</span>
                </div>
              </div>

              {/* Messages List Container */}
              <div className="flex-1 overflow-y-auto p-5 space-y-4">
                {messages.length === 0 && !isSending && (
                  <div className="text-center py-12 text-slate-600 text-xs italic">
                    Send a message to begin planning. E.g., &quot;Suggest local attractions and sights.&quot;
                  </div>
                )}

                {messages.map((msg) => {
                  const isUser = msg.sender === "user";
                  return (
                    <div key={msg.id} className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
                      <div
                        className={`max-w-[80%] rounded-2xl p-4 text-sm leading-relaxed border shadow-sm ${
                          isUser
                            ? "bg-indigo-600/10 border-indigo-500/30 text-slate-200"
                            : msg.isError
                            ? "bg-red-950/20 border-red-500/20 text-red-200"
                            : "bg-slate-900/60 border-slate-800/80 text-slate-300"
                        }`}
                      >
                        {/* Message Content */}
                        <div className="whitespace-pre-line">{msg.content || "..."}</div>
                        
                        {/* Timestamp */}
                        <div className="text-[9px] text-slate-500 text-right mt-1.5 font-mono">
                          {new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </div>
                      </div>
                    </div>
                  );
                })}

                {/* Sub-Agent Live Trace Logs Box */}
                {isSending && activeLogs.length > 0 && (
                  <div className="border border-indigo-500/20 bg-indigo-950/10 rounded-2xl p-4 space-y-2 animate-fade-in">
                    <div className="flex items-center gap-2 text-xs text-indigo-400 font-mono font-semibold border-b border-indigo-500/15 pb-2">
                      <Terminal className="w-3.5 h-3.5" />
                      <span>agent_orchestrator_traces.log</span>
                      <Loader className="w-3.5 h-3.5 animate-spin ml-auto" />
                    </div>
                    <div className="space-y-1.5 font-mono text-[11px] text-slate-400">
                      {activeLogs.map((log, idx) => (
                        <div key={idx} className="flex gap-2">
                          <span className="text-slate-600 select-none">&gt;</span>
                          <span>{log}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Message Input Box Form */}
              <form onSubmit={sendMessage} className="p-5 border-t border-slate-900 bg-slate-900/10 flex gap-3">
                <input
                  type="text"
                  value={inputMessage}
                  onChange={(e) => setInputMessage(e.target.value)}
                  placeholder={isSending ? "Planning suite executing..." : "E.g., Suggest 4 days of history tours..."}
                  disabled={isSending}
                  className="flex-1 bg-slate-950 border border-slate-900 rounded-xl py-3 px-4 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all disabled:opacity-50"
                  required
                />
                <button
                  type="submit"
                  disabled={isSending || !inputMessage.trim()}
                  className="px-5 py-3 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-950 disabled:cursor-not-allowed font-medium text-white rounded-xl shadow-lg shadow-indigo-500/10 transition-all flex items-center justify-center gap-2"
                >
                  <Send className="w-4 h-4" />
                </button>
              </form>
            </div>
          )}
        </div>

        {/* Right Sidebar Column: Generated Itineraries Display */}
        <aside className="w-72 border-l border-slate-900 pl-8 flex flex-col space-y-6 shrink-0 select-none">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-400 uppercase tracking-wider border-b border-slate-900 pb-3">
            <Calendar className="w-4 h-4 text-indigo-400" />
            <span>Itinerary Days</span>
          </div>

          <div className="flex-1 overflow-y-auto space-y-3.5 pr-1">
            {itinerariesLoading ? (
              <div className="flex items-center justify-center py-10">
                <Loader className="w-5 h-5 text-indigo-400 animate-spin" />
              </div>
            ) : itineraries.length === 0 ? (
              <div className="text-center py-12 bg-slate-900/10 border border-slate-800/40 rounded-2xl p-4 text-slate-500 text-xs italic leading-relaxed">
                No compiled itinerary segments yet. Prompt your agents to compile one!
              </div>
            ) : (
              itineraries.map((it) => (
                <div key={it.id} className="bg-slate-900/40 border border-slate-800/60 rounded-2xl p-4 space-y-2 text-xs">
                  <div className="flex justify-between items-center text-slate-200 font-semibold border-b border-slate-800/40 pb-1.5">
                    <span>Day {it.day_number}</span>
                    <span className="text-[10px] text-slate-500 font-normal">{it.title}</span>
                  </div>
                  <p className="text-slate-400 leading-relaxed font-sans">{it.description}</p>
                  
                  {/* Activities list */}
                  {it.activities && typeof it.activities === "object" && (
                    <div className="flex flex-wrap gap-1.5 pt-1.5">
                      {Object.values(it.activities).flat().map((act: any, idx: number) => (
                        <span key={idx} className="bg-slate-950 text-indigo-400 border border-slate-800/80 px-2 py-0.5 rounded text-[10px] font-mono">
                          {String(act)}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </aside>

      </div>

      <footer className="border-t border-slate-900 py-6 text-center text-xs text-slate-600 mt-auto bg-slate-950/20">
        <p>© 2026 VoyagerAI. Built for Multi-Agent Travel Planner Skeleton Demo.</p>
      </footer>

      {/* Trip Creation Modal Component */}
      <TripCreationModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onTripCreated={handleTripCreated}
      />
    </main>
  );
}
