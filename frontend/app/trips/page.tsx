"use client";

import { useEffect, useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Navbar } from "@/components/Navbar";
import { AuthGuard } from "@/components/AuthGuard";
import { apiFetch, ApiError } from "@/lib/api";

type Trip = {
  id: string;
  destination: string;
  created_at: string;
};

function TripsPageContent() {
  const router = useRouter();

  const [trips, setTrips] = useState<Trip[]>([]);
  const [isLoadingTrips, setIsLoadingTrips] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [destination, setDestination] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadTrips() {
      try {
        const data = await apiFetch<Trip[]>("/trips");
        if (!cancelled) setTrips(data);
      } catch (err) {
        // GET /trips ships later in the roadmap — treat "not built yet" as
        // an empty list rather than a broken page.
        if (!cancelled) {
          if (err instanceof ApiError && err.status === 404) {
            setTrips([]);
          } else {
            setLoadError(
              err instanceof Error ? err.message : "Couldn't load your trips."
            );
          }
        }
      } finally {
        if (!cancelled) setIsLoadingTrips(false);
      }
    }

    loadTrips();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleCreateTrip = async (e: FormEvent) => {
    e.preventDefault();
    if (!destination.trim()) return;

    setIsCreating(true);
    setCreateError(null);
    try {
      const trip = await apiFetch<Trip>("/trips", {
        method: "POST",
        body: JSON.stringify({ destination: destination.trim() }),
      });
      router.push(`/trips/${trip.id}`);
    } catch (err) {
      setCreateError(
        err instanceof Error ? err.message : "Couldn't create that trip."
      );
      setIsCreating(false);
    }
  };

  return (
    <main className="min-h-screen bg-[#0b0f19] text-slate-100 font-sans">
      <div className="absolute top-0 left-1/4 w-[500px] h-[500px] bg-indigo-500/10 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute top-1/3 right-1/4 w-[400px] h-[400px] bg-purple-500/10 rounded-full blur-[100px] pointer-events-none" />

      <Navbar />

      <div className="max-w-5xl mx-auto px-6 py-10 space-y-8">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-300 flex items-center gap-2">
              <span className="w-1.5 h-4 bg-indigo-500 rounded-full" />
              Your Trips
            </h2>
            <p className="text-sm text-slate-500 mt-1">
              Every trip is its own conversation with your planning agents.
            </p>
          </div>
          <button
            onClick={() => setIsModalOpen(true)}
            className="px-5 py-2.5 bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 font-medium text-sm text-white rounded-xl shadow-lg shadow-indigo-500/25 transition-all flex items-center justify-center gap-2"
          >
            <svg
              className="w-4 h-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2.5}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
            </svg>
            Plan a new trip
          </button>
        </div>

        {isLoadingTrips ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                className="h-28 rounded-2xl bg-slate-900/40 border border-slate-800/60 animate-pulse"
              />
            ))}
          </div>
        ) : loadError ? (
          <div className="text-sm text-red-400 bg-red-950/40 border border-red-900/60 rounded-xl px-4 py-3">
            {loadError}
          </div>
        ) : trips.length === 0 ? (
          <div className="bg-slate-900/40 border border-dashed border-slate-800 rounded-2xl p-12 text-center">
            <div className="w-12 h-12 mx-auto rounded-xl bg-gradient-to-tr from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/30 mb-4">
              <svg
                className="w-6 h-6 text-white"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
            </div>
            <h3 className="text-slate-200 font-semibold">No trips yet</h3>
            <p className="text-sm text-slate-500 mt-1 max-w-sm mx-auto">
              Tell your agent crew where you want to go, and they&apos;ll start
              building an itinerary with you.
            </p>
            <button
              onClick={() => setIsModalOpen(true)}
              className="mt-5 px-5 py-2.5 bg-slate-800 hover:bg-slate-700 border border-slate-700/60 text-sm font-medium text-slate-200 rounded-xl transition-all"
            >
              Plan your first trip
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {trips.map((trip) => (
              <button
                key={trip.id}
                onClick={() => router.push(`/trips/${trip.id}`)}
                className="text-left bg-slate-900/60 border border-slate-800/80 rounded-2xl p-5 hover:border-indigo-500/50 hover:bg-slate-900 transition-all group"
              >
                <div className="flex items-center justify-between mb-3">
                  <span className="w-9 h-9 rounded-lg bg-indigo-500/10 border border-indigo-500/30 flex items-center justify-center text-indigo-400 group-hover:bg-indigo-500/20 transition-all">
                    <svg
                      className="w-4 h-4"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                      strokeWidth={2}
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"
                      />
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"
                      />
                    </svg>
                  </span>
                  <span className="text-[10px] text-slate-500 font-mono">
                    {new Date(trip.created_at).toLocaleDateString()}
                  </span>
                </div>
                <h3 className="font-semibold text-slate-100 group-hover:text-white">
                  {trip.destination}
                </h3>
                <p className="text-xs text-slate-500 mt-1">Open conversation →</p>
              </button>
            ))}
          </div>
        )}
      </div>

      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
          <div
            className="absolute inset-0 bg-slate-950/70 backdrop-blur-sm"
            onClick={() => !isCreating && setIsModalOpen(false)}
          />
          <div className="relative w-full max-w-md bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-2xl">
            <h3 className="text-lg font-semibold text-white mb-1">
              Plan a new trip
            </h3>
            <p className="text-sm text-slate-500 mb-5">
              Where are you headed? You can add dates and budget in the chat.
            </p>
            <form onSubmit={handleCreateTrip} className="space-y-4">
              {createError && (
                <div className="text-sm text-red-400 bg-red-950/40 border border-red-900/60 rounded-lg px-4 py-3">
                  {createError}
                </div>
              )}
              <input
                autoFocus
                type="text"
                value={destination}
                onChange={(e) => setDestination(e.target.value)}
                placeholder="e.g. Tokyo, Japan"
                className="w-full bg-slate-950/60 border border-slate-800 rounded-xl px-4 py-2.5 text-sm text-slate-100 placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-indigo-500/60 focus:border-indigo-500/60 transition-all"
              />
              <div className="flex gap-3 justify-end">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  disabled={isCreating}
                  className="px-4 py-2 text-sm font-medium text-slate-400 hover:text-slate-200 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isCreating || !destination.trim()}
                  className="px-5 py-2 bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 disabled:from-indigo-900/50 disabled:to-purple-900/50 disabled:cursor-not-allowed font-medium text-sm text-white rounded-xl shadow-lg shadow-indigo-500/25 transition-all"
                >
                  {isCreating ? "Starting…" : "Start planning"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </main>
  );
}

export default function TripsPage() {
  return (
    <AuthGuard>
      <TripsPageContent />
    </AuthGuard>
  );
}
