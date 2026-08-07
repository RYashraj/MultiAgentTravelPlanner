"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Navbar } from "@/components/Navbar";
import { AuthGuard } from "@/components/AuthGuard";
import { TripCard, type Trip } from "@/components/TripCard";
import { apiFetch, ApiError } from "@/lib/api";

function SavedTripsContent() {
  const router = useRouter();
  const [trips, setTrips] = useState<Trip[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadSaved() {
      try {
        // Filtering client-side keeps this working whether the backend
        // exposes GET /trips?saved=true or just GET /trips with is_saved.
        const data = await apiFetch<Trip[]>("/trips");
        if (!cancelled) setTrips(data.filter((t) => t.is_saved));
      } catch (err) {
        if (!cancelled) {
          if (err instanceof ApiError && err.status === 404) {
            setTrips([]);
          } else {
            setLoadError(
              err instanceof Error ? err.message : "Couldn't load saved trips."
            );
          }
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    loadSaved();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="min-h-screen bg-[var(--color-bg)] text-[var(--color-text-primary)] font-sans">
      <div className="absolute top-0 left-1/4 w-[500px] h-[500px] bg-indigo-500/10 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute top-1/3 right-1/4 w-[400px] h-[400px] bg-purple-500/10 rounded-full blur-[100px] pointer-events-none" />

      <Navbar />

      <div className="max-w-5xl mx-auto px-4 sm:px-6 py-10 space-y-8">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-[var(--color-text-secondary)] flex items-center gap-2">
              <span className="w-1.5 h-4 bg-amber-400 rounded-full" />
              Saved Trips
            </h2>
            <p className="text-sm text-[var(--color-text-muted)] mt-1">
              The trips you&apos;ve bookmarked for quick access.
            </p>
          </div>
          <Link
            href="/trips"
            className="px-4 py-2.5 bg-[var(--color-surface)] hover:bg-[var(--color-surface-hover)] border border-[var(--color-border)] text-sm font-medium text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] rounded-xl transition-all flex items-center gap-2"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M11 17l-5-5m0 0l5-5m-5 5h12" />
            </svg>
            All trips
          </Link>
        </div>

        {isLoading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                className="h-28 rounded-2xl bg-[var(--color-surface-alt)] border border-[var(--color-border)] animate-pulse"
              />
            ))}
          </div>
        ) : loadError ? (
          <div className="text-sm text-red-400 bg-red-950/40 border border-red-900/60 rounded-xl px-4 py-3">
            {loadError}
          </div>
        ) : trips.length === 0 ? (
          <div className="bg-[var(--color-surface-alt)] border border-dashed border-[var(--color-border)] rounded-2xl p-12 text-center">
            <div className="w-12 h-12 mx-auto rounded-xl bg-gradient-to-tr from-amber-400 to-orange-500 flex items-center justify-center shadow-lg shadow-amber-500/30 mb-4">
              <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
              </svg>
            </div>
            <h3 className="text-[var(--color-text-primary)] font-semibold">No saved trips yet</h3>
            <p className="text-sm text-[var(--color-text-muted)] mt-1 max-w-sm mx-auto">
              Tap the bookmark icon on any trip card to pin it here.
            </p>
            <button
              onClick={() => router.push("/trips")}
              className="mt-5 px-5 py-2.5 bg-[var(--color-surface)] hover:bg-[var(--color-surface-hover)] border border-[var(--color-border)] text-sm font-medium text-[var(--color-text-primary)] rounded-xl transition-all"
            >
              Browse your trips
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {trips.map((trip) => (
              <TripCard
                key={trip.id}
                trip={trip}
                onOpen={(id) => router.push(`/trips/${id}`)}
                onDeleted={(id) => setTrips((prev) => prev.filter((t) => t.id !== id))}
                onSavedChange={(id, isSaved) => {
                  if (!isSaved) setTrips((prev) => prev.filter((t) => t.id !== id));
                }}
              />
            ))}
          </div>
        )}
      </div>
    </main>
  );
}

export default function SavedTripsPage() {
  return (
    <AuthGuard>
      <SavedTripsContent />
    </AuthGuard>
  );
}
