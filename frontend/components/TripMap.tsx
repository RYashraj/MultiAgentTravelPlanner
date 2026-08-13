"use client";

import { useEffect, useRef, useState } from "react";
import { BedDouble, MapPin } from "lucide-react";

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

const HOTEL_PIN =
  "https://maps.google.com/mapfiles/ms/icons/purple-dot.png";
const ATTRACTION_PIN =
  "https://maps.google.com/mapfiles/ms/icons/green-dot.png";

let mapsScriptPromise: Promise<void> | null = null;

function loadGoogleMaps(apiKey: string): Promise<void> {
  if (typeof window === "undefined") return Promise.reject("no window");
  if ((window as any).google?.maps) return Promise.resolve();
  if (mapsScriptPromise) return mapsScriptPromise;

  mapsScriptPromise = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = `https://maps.googleapis.com/maps/api/js?key=${apiKey}`;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Failed to load Google Maps"));
    document.head.appendChild(script);
  });
  return mapsScriptPromise;
}

export function TripMap({ destination, hotels = [], attractions = [] }: TripMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error" | "no-key">(
    "loading"
  );

  const places = [
    ...hotels.slice(0, 4).map((p) => ({ ...p, kind: "hotel" as const })),
    ...attractions.slice(0, 6).map((p) => ({ ...p, kind: "attraction" as const })),
  ];

  useEffect(() => {
    const apiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY;
    if (!apiKey) {
      setStatus("no-key");
      return;
    }
    if (places.length === 0) {
      setStatus("error");
      return;
    }

    let cancelled = false;

    loadGoogleMaps(apiKey)
      .then(() => {
        if (cancelled || !containerRef.current) return;
        const google = (window as any).google;
        const geocoder = new google.maps.Geocoder();

        geocoder.geocode({ address: destination }, (results: any, geoStatus: string) => {
          if (cancelled) return;
          const center =
            geoStatus === "OK" && results?.[0]
              ? results[0].geometry.location
              : { lat: 20.5937, lng: 78.9629 }; // fallback: India centroid

          const map = new google.maps.Map(containerRef.current, {
            center,
            zoom: 12,
            disableDefaultUI: true,
            zoomControl: true,
            styles: [
              { elementType: "geometry", stylers: [{ color: "#0f172a" }] },
              { elementType: "labels.text.stroke", stylers: [{ color: "#0f172a" }] },
              { elementType: "labels.text.fill", stylers: [{ color: "#94a3b8" }] },
              { featureType: "road", elementType: "geometry", stylers: [{ color: "#1e293b" }] },
              { featureType: "water", elementType: "geometry", stylers: [{ color: "#0b0f19" }] },
              { featureType: "poi", elementType: "labels", stylers: [{ visibility: "off" }] },
            ],
          });

          const infoWindow = new google.maps.InfoWindow();
          const bounds = new google.maps.LatLngBounds();
          let placed = 0;

          places.forEach((place) => {
            geocoder.geocode(
              { address: `${place.name}, ${destination}` },
              (res: any, s: string) => {
                if (cancelled) return;
                if (s !== "OK" || !res?.[0]) return;
                const position = res[0].geometry.location;

                const marker = new google.maps.Marker({
                  map,
                  position,
                  title: place.name,
                  icon: place.kind === "hotel" ? HOTEL_PIN : ATTRACTION_PIN,
                });

                marker.addListener("click", () => {
                  infoWindow.setContent(
                    `<div style="font-family: sans-serif; max-width: 200px;">
                      <p style="font-weight:600; margin:0 0 4px; color:#0f172a;">${place.name}</p>
                      ${place.description ? `<p style="font-size:12px; margin:0; color:#475569;">${place.description}</p>` : ""}
                      ${place.rating ? `<p style="font-size:11px; margin:4px 0 0; color:#b45309;">★ ${place.rating}</p>` : ""}
                    </div>`
                  );
                  infoWindow.open(map, marker);
                });

                bounds.extend(position);
                placed += 1;
                if (placed > 0) map.fitBounds(bounds);
              }
            );
          });

          setStatus("ready");
        });
      })
      .catch(() => {
        if (!cancelled) setStatus("error");
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [destination, hotels.length, attractions.length]);

  if (status === "no-key" || status === "error") {
    // Graceful fallback: no map, but the places are still useful as a list.
    return (
      <div className="bg-[var(--color-surface-alt)] border border-[var(--color-border)] rounded-2xl p-5">
        <p className="text-xs text-[var(--color-text-muted)] mb-3">
          {status === "no-key"
            ? "Map unavailable (missing Google Maps API key)."
            : "Not enough location data to show a map yet."}
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {places.map((p, i) => (
            <div key={i} className="flex items-center gap-2 bg-[var(--color-surface)]/40 rounded-lg px-3 py-2">
              {p.kind === "hotel" ? (
                <BedDouble className="w-3.5 h-3.5 text-purple-400 shrink-0" />
              ) : (
                <MapPin className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
              )}
              <span className="text-xs text-[var(--color-text-secondary)] truncate">{p.name}</span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="bg-[var(--color-surface-alt)] border border-[var(--color-border)] rounded-2xl overflow-hidden">
      <div className="flex items-center gap-4 px-4 py-2.5 border-b border-[var(--color-border)] text-[10px] text-[var(--color-text-muted)]">
        <span className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-purple-400" /> Hotels
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-emerald-400" /> Attractions
        </span>
        {status === "loading" && <span className="ml-auto animate-pulse">Loading map…</span>}
      </div>
      <div ref={containerRef} className="w-full h-[320px] sm:h-[400px]" />
    </div>
  );
}
