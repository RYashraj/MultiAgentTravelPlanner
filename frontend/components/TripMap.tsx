"use client";

import { BedDouble, MapPin, Map } from "lucide-react";

type Place = {
  name: string;
  description?: string;
  rating?: number;
};

type TripMapProps = {
  destination: string;
  hotels?: Place[];
  attractions?: Place[];
};

export function TripMap({ destination, hotels = [], attractions = [] }: TripMapProps) {
  const places = [
    ...hotels.slice(0, 4).map((p) => ({ ...p, kind: "hotel" as const })),
    ...attractions.slice(0, 6).map((p) => ({ ...p, kind: "attraction" as const })),
  ];

  // Build a clean OpenStreetMap embed URL — free, no API key, always works
  const encodedDestination = encodeURIComponent(destination);
  const osmEmbedUrl = `https://www.openstreetmap.org/export/embed.html?bbox=-180,-85,180,85&layer=mapnik&marker=0,0&query=${encodedDestination}`;
  const osmSearchUrl = `https://www.openstreetmap.org/search?query=${encodedDestination}`;

  return (
    <div className="bg-[var(--color-surface-alt)] border border-[var(--color-border)] rounded-2xl overflow-hidden">
      {/* Header legend */}
      <div className="flex items-center gap-4 px-4 py-2.5 border-b border-[var(--color-border)] text-[10px] text-[var(--color-text-muted)]">
        <span className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-purple-400" /> Hotels
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-emerald-400" /> Attractions
        </span>
        <a
          href={osmSearchUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="ml-auto flex items-center gap-1 text-[var(--color-text-muted)] hover:text-[var(--color-primary)] transition-colors"
        >
          <Map className="w-3 h-3" />
          Open full map ↗
        </a>
      </div>

      {/* OpenStreetMap iframe — free, no billing, no API key */}
      <div className="relative w-full h-[320px] sm:h-[380px]">
        <iframe
          title={`Map of ${destination}`}
          src={`https://www.openstreetmap.org/export/embed.html?layer=mapnik&query=${encodedDestination}`}
          className="w-full h-full border-0"
          loading="lazy"
          allowFullScreen
          style={{ filter: "invert(90%) hue-rotate(180deg)" }} // dark map to match app theme
        />
      </div>

      {/* Place list below the map */}
      {places.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 p-3 border-t border-[var(--color-border)]">
          {places.map((p, i) => (
            <div
              key={i}
              className="flex items-center gap-2 bg-[var(--color-surface)]/40 rounded-lg px-3 py-2"
            >
              {p.kind === "hotel" ? (
                <BedDouble className="w-3.5 h-3.5 text-purple-400 shrink-0" />
              ) : (
                <MapPin className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
              )}
              <span className="text-xs text-[var(--color-text-secondary)] truncate">
                {p.name}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
