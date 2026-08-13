"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Navbar } from "@/components/Navbar";
import { AuthGuard } from "@/components/AuthGuard";
import { ItineraryCard } from "@/components/ItineraryCard";
import { TripMap } from "@/components/TripMap";
import { apiFetch } from "@/lib/api";
import {
  Plane,
  ChevronLeft,
  AlertTriangle,
  CheckCircle,
  Clock,
  Star,
  ThermometerSun,
  Calendar,
  TrendingUp,
  Sparkles,
  MapPin,
  Cloud,
  DollarSign,
  BedDouble,
} from "lucide-react";

// ─── Types ──────────────────────────────────────────────────────────────────

type SectionStatus = "ok" | "partial" | "unavailable" | "complete" | "incomplete";

interface DashboardSection {
  status: SectionStatus;
  data?: any;
  message?: string;
}

interface DashboardData {
  trip_id: string;
  destination: string;
  trip_status: string;
  itinerary: {
    status: SectionStatus;
    content?: string;
    created_at?: string;
    message?: string;
  };
  flights: DashboardSection;
  hotels: DashboardSection;
  weather: DashboardSection;
  attractions: DashboardSection;
  budget: DashboardSection;
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function SectionBadge({ status }: { status: SectionStatus }) {
  if (status === "ok" || status === "complete") {
    return (
      <span className="flex items-center gap-1 text-[10px] font-semibold text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 rounded-full px-2 py-0.5">
        <CheckCircle className="w-2.5 h-2.5" /> Live
      </span>
    );
  }
  if (status === "partial" || status === "incomplete") {
    return (
      <span className="flex items-center gap-1 text-[10px] font-semibold text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded-full px-2 py-0.5">
        <Clock className="w-2.5 h-2.5" /> Partial
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1 text-[10px] font-semibold text-[var(--color-text-muted)] bg-[var(--color-surface)] border border-[var(--color-border)] rounded-full px-2 py-0.5">
      <AlertTriangle className="w-2.5 h-2.5" /> Unavailable
    </span>
  );
}

const GRADIENTS: Record<string, string> = {
  indigo: "from-indigo-500 to-purple-600",
  violet: "from-violet-500 to-purple-600",
  amber: "from-amber-500 to-orange-600",
  emerald: "from-emerald-500 to-teal-600",
  rose: "from-rose-500 to-pink-600",
};

function SectionCard({
  icon: Icon,
  title,
  status,
  children,
  color = "indigo",
  className = "",
}: {
  icon: React.ElementType;
  title: string;
  status: SectionStatus;
  children: React.ReactNode;
  color?: string;
  className?: string;
}) {
  return (
    <div
      className={`bg-[var(--color-surface-alt)] border border-[var(--color-border)] rounded-2xl overflow-hidden hover:border-slate-600/60 transition-colors ${className}`}
    >
      <div className="flex items-center justify-between px-5 pt-4 pb-3 border-b border-[var(--color-border)]/40">
        <div className="flex items-center gap-3">
          <div
            className={`w-8 h-8 rounded-xl bg-gradient-to-br ${GRADIENTS[color] || GRADIENTS.indigo} flex items-center justify-center shadow-lg`}
          >
            <Icon className="w-4 h-4 text-white" />
          </div>
          <h3 className="text-sm font-bold text-white">{title}</h3>
        </div>
        <SectionBadge status={status} />
      </div>
      <div className="p-5">{children}</div>
    </div>
  );
}

function Unavail({ msg }: { msg?: string }) {
  return (
    <div className="flex items-center gap-2 text-[var(--color-text-muted)] text-sm py-2">
      <AlertTriangle className="w-4 h-4 shrink-0" />
      <span>{msg || "Data unavailable."}</span>
    </div>
  );
}

// ─── Section renderers ───────────────────────────────────────────────────────

function FlightSec({ s }: { s: DashboardSection }) {
  if (s.status === "unavailable" || !s.data) return <Unavail msg={s.message} />;
  const d = s.data;
  if (!d.found) {
    return (
      <div className="space-y-2">
        <Unavail msg={d.reason} />
        {d.notes && <p className="text-xs text-[var(--color-text-secondary)]">{d.notes}</p>}
      </div>
    );
  }
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Plane className="w-4 h-4 text-indigo-400 shrink-0" />
        <span className="text-sm font-semibold text-white">{d.carrier}</span>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="bg-[var(--color-surface-hover)] rounded-xl p-3">
          <p className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wider mb-1">One-Way</p>
          <p className="text-lg font-bold text-white">Rs.{(d.price_inr || 0).toLocaleString()}</p>
        </div>
        <div className="bg-[var(--color-surface-hover)] rounded-xl p-3">
          <p className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wider mb-1">Round Trip</p>
          <p className="text-lg font-bold text-indigo-400">Rs.{(d.roundtrip_price_inr || 0).toLocaleString()}</p>
        </div>
      </div>
      {d.price_range_inr && <p className="text-xs text-[var(--color-text-secondary)]">Range: {d.price_range_inr}</p>}
      {d.frequency && <p className="text-xs text-[var(--color-text-muted)]">{d.frequency}</p>}
      {d.notes && <p className="text-xs text-indigo-300/70 italic">{d.notes}</p>}
    </div>
  );
}

function HotelSec({ s }: { s: DashboardSection }) {
  if (s.status === "unavailable" || !s.data) return <Unavail msg={s.message} />;
  const d = s.data;
  return (
    <div className="space-y-3">
      {d.budget_tier && (
        <div className="inline-flex bg-purple-500/10 border border-purple-500/20 rounded-full px-2 py-0.5">
          <span className="text-[10px] font-semibold text-purple-300 uppercase">{d.budget_tier}</span>
        </div>
      )}
      {(d.cheapest_nightly_inr || 0) > 0 && (
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-[var(--color-surface-hover)] rounded-xl p-3">
            <p className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wider mb-1">From / Night</p>
            <p className="text-lg font-bold text-white">Rs.{(d.cheapest_nightly_inr || 0).toLocaleString()}</p>
          </div>
          {(d.total_hotel_estimate_inr || 0) > 0 && (
            <div className="bg-[var(--color-surface-hover)] rounded-xl p-3">
              <p className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wider mb-1">Stay Total</p>
              <p className="text-lg font-bold text-purple-400">Rs.{(d.total_hotel_estimate_inr || 0).toLocaleString()}</p>
            </div>
          )}
        </div>
      )}
      {d.hotels && d.hotels.length > 0 ? (
        <div className="space-y-2">
          {d.hotels.slice(0, 3).map((h: { name: string; description: string; rating?: number }, i: number) => (
            <div key={i} className="bg-[var(--color-surface)]/40 rounded-xl p-3">
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-white truncate">{h.name}</p>
                  <p className="text-xs text-[var(--color-text-secondary)] mt-0.5 leading-relaxed">{h.description}</p>
                </div>
                {h.rating && (
                  <span className="flex items-center gap-0.5 text-xs font-bold text-amber-400 shrink-0">
                    <Star className="w-3 h-3 fill-amber-400" />{h.rating}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      ) : !d.found ? (
        <Unavail msg={d.reason} />
      ) : null}
      {d.notes && <p className="text-xs text-purple-300/70 italic mt-1">{d.notes}</p>}
    </div>
  );
}

function WeatherSec({ s }: { s: DashboardSection }) {
  if (s.status === "unavailable" || !s.data) return <Unavail msg={s.message} />;
  const d = s.data;
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-4">
        <ThermometerSun className="w-10 h-10 text-amber-400" />
        <div>
          <p className="text-2xl font-bold text-white">{d.temp}</p>
          <p className="text-sm text-amber-300">{d.condition}</p>
        </div>
      </div>
      {d.forecast && <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed">{d.forecast}</p>}
    </div>
  );
}

function AttrSec({ s }: { s: DashboardSection }) {
  if (s.status === "unavailable" || !s.data || s.data.length === 0)
    return <Unavail msg={s.message} />;
  return (
    <div className="space-y-2">
      {s.data.slice(0, 5).map((a: { name: string; description: string; rating?: number }, i: number) => (
        <div key={i} className="flex items-start gap-3 bg-[var(--color-surface)]/40 rounded-xl p-3">
          <div className="w-5 h-5 rounded-lg bg-emerald-500/20 flex items-center justify-center shrink-0 mt-0.5">
            <span className="text-[10px] font-bold text-emerald-400">{i + 1}</span>
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm font-semibold text-white truncate">{a.name}</p>
              {a.rating && (
                <span className="flex items-center gap-0.5 text-xs font-bold text-amber-400 shrink-0">
                  <Star className="w-3 h-3 fill-amber-400" />{a.rating}
                </span>
              )}
            </div>
            <p className="text-xs text-[var(--color-text-secondary)] mt-0.5 leading-relaxed line-clamp-2">{a.description}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

function BudgetSec({ s }: { s: DashboardSection }) {
  if (s.status === "unavailable" || !s.data) return <Unavail msg={s.message} />;
  const d = s.data;
  const bd = d.breakdown as { flights: string; accommodation: string; daily_expenses: string; total: string } | undefined;
  return (
    <div className="space-y-4">
      {d.grand_total_inr != null && (
        <div className="bg-gradient-to-br from-rose-500/10 to-pink-600/10 border border-rose-500/20 rounded-xl p-4 text-center">
          <p className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wider mb-1">Total Estimated Budget</p>
          <p className="text-3xl font-extrabold text-white">Rs.{d.grand_total_inr.toLocaleString()}</p>
          {d.budget_tier && (
            <p className="text-xs text-rose-300 mt-1 capitalize">{d.budget_tier} tier trip</p>
          )}
        </div>
      )}
      {bd && (
        <div className="grid gap-2">
          {[
            { l: "Flights", v: bd.flights, I: Plane },
            { l: "Accommodation", v: bd.accommodation, I: BedDouble },
            { l: "Daily Expenses", v: bd.daily_expenses, I: TrendingUp },
          ].map((x) => (
            <div key={x.l} className="flex items-start gap-3 bg-[var(--color-surface)]/40 rounded-xl p-3">
              <x.I className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
              <div>
                <p className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wider">{x.l}</p>
                <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed">{x.v}</p>
              </div>
            </div>
          ))}
        </div>
      )}
      {d.status && d.status !== "complete" && (
        <div className="bg-amber-500/10 border border-amber-500/20 rounded-xl p-3">
          <p className="text-xs text-amber-400 font-semibold mb-1">Budget status: {d.status}</p>
          {d.missing && d.missing.length > 0 && (
            <p className="text-xs text-[var(--color-text-secondary)]">Data gaps: {(d.missing as string[]).join(", ")}</p>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Main Component ──────────────────────────────────────────────────────────

function DashboardContent() {
  const params = useParams<{ id: string }>();
  const tripId = params.id;
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiFetch<DashboardData>(`/trips/${tripId}/dashboard`)
      .then((d) => {
        if (!cancelled) setDashboard(d);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Could not load dashboard.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [tripId]);

  return (
    <main className="min-h-screen bg-[var(--color-bg)] text-[var(--color-text-primary)] font-sans">
      <Navbar />
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8 space-y-6">

        {/* Header */}
        <div className="flex items-center gap-4 flex-wrap">
          <Link
            href={`/trips/${tripId}`}
            className="w-9 h-9 rounded-xl bg-[var(--color-surface)] border border-[var(--color-border)] flex items-center justify-center text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:border-[var(--color-border)] transition-all"
          >
            <ChevronLeft className="w-5 h-5" />
          </Link>
          <div className="min-w-0">
            <h1 className="text-lg sm:text-2xl font-extrabold bg-gradient-to-r from-indigo-400 via-purple-400 to-pink-400 bg-clip-text text-transparent break-words">
              {dashboard ? `${dashboard.destination} Dashboard` : "Trip Dashboard"}
            </h1>
            <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
              {dashboard?.trip_status ? `Status: ${dashboard.trip_status}` : "Loading…"}
            </p>
          </div>
          {!isLoading && (
            <div className="sm:ml-auto flex items-center gap-1.5 text-xs text-indigo-400 bg-indigo-500/10 border border-indigo-500/20 rounded-full px-3 py-1">
              <Sparkles className="w-3 h-3" /> v0.2-full-mvp
            </div>
          )}
        </div>

        {/* Loading skeleton */}
        {isLoading && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-48 rounded-2xl bg-[var(--color-surface)]/40 animate-pulse" />
            ))}
          </div>
        )}

        {/* Error state — section-independent fallback */}
        {error && !isLoading && (
          <div className="bg-red-950/40 border border-red-900/60 rounded-2xl p-8 text-center space-y-3">
            <AlertTriangle className="w-10 h-10 text-red-400 mx-auto" />
            <p className="text-sm text-red-400 font-semibold">{error}</p>
            <p className="text-xs text-[var(--color-text-muted)]">
              Ensure the backend is running and a trip itinerary has been generated via chat first.
            </p>
            <Link
              href={`/trips/${tripId}`}
              className="inline-flex items-center gap-1.5 text-xs text-indigo-400 hover:text-[var(--color-text-primary)] transition-colors"
            >
              <ChevronLeft className="w-3 h-3" /> Back to planning chat
            </Link>
          </div>
        )}

        {/* Full dashboard */}
        {dashboard && !error && (
          <div className="space-y-5">
            {/* Itinerary — full width */}
            {dashboard.itinerary?.content ? (
              <ItineraryCard
                content={dashboard.itinerary.content}
                destination={dashboard.destination}
                createdAt={dashboard.itinerary.created_at}
              />
            ) : (
              <div className="bg-[var(--color-surface-alt)] border border-[var(--color-border)] rounded-2xl p-8 text-center space-y-3">
                <Calendar className="w-10 h-10 text-[var(--color-text-muted)] mx-auto" />
                <p className="text-sm text-[var(--color-text-secondary)]">No itinerary generated yet.</p>
                <Link
                  href={`/trips/${tripId}`}
                  className="text-xs text-indigo-400 hover:text-[var(--color-text-primary)] transition-colors"
                >
                  Go to chat to generate your itinerary
                </Link>
              </div>
            )}

            {/* Agent data grid — 3 cols, independent degradation */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              <SectionCard icon={Plane} title="Flights" status={dashboard.flights.status} color="indigo">
                <FlightSec s={dashboard.flights} />
              </SectionCard>

              <SectionCard icon={BedDouble} title="Hotels" status={dashboard.hotels.status} color="violet">
                <HotelSec s={dashboard.hotels} />
              </SectionCard>

              <SectionCard icon={ThermometerSun} title="Weather" status={dashboard.weather.status} color="amber">
                <WeatherSec s={dashboard.weather} />
              </SectionCard>

              <SectionCard icon={MapPin} title="Top Attractions" status={dashboard.attractions.status} color="emerald">
                <AttrSec s={dashboard.attractions} />
              </SectionCard>

              {(dashboard.hotels.data?.hotels?.length > 0 || dashboard.attractions.data?.length > 0) && (
                <div className="md:col-span-2 lg:col-span-3">
                  <TripMap
                    destination={dashboard.destination}
                    hotels={dashboard.hotels.data?.hotels || []}
                    attractions={dashboard.attractions.data || []}
                  />
                </div>
              )}

              <div className="lg:col-span-2">
                <SectionCard
                  icon={DollarSign}
                  title="Budget Breakdown"
                  status={dashboard.budget.status}
                  color="rose"
                  className="h-full"
                >
                  <BudgetSec s={dashboard.budget} />
                </SectionCard>
              </div>
            </div>

            {/* Footer */}
            <div className="flex items-center justify-between text-xs text-[var(--color-text-muted)] pt-2">
              <span>VoyagerAI • 5-agent pipeline: Coordinator → Flight → Hotel → Budget → Planner</span>
              <Link href={`/trips/${tripId}`} className="text-indigo-500 hover:text-indigo-400 transition-colors">
                Back to chat →
              </Link>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}

export default function DashboardPage() {
  return (
    <AuthGuard>
      <DashboardContent />
    </AuthGuard>
  );
}
