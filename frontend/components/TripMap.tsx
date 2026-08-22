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

// Geocoding results rarely change for a given address, and Google's
// Geocoding API is rate-limited per second — caching means a place we've
// already resolved (e.g. on a re-render, or across trips to the same
// destination) never fires a second network request or eats into the quota.
const geocodeCache = new Map<string, any>();

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Geocodes a single address, retrying with backoff if Google's Geocoder
 * reports OVER_QUERY_LIMIT. Without this, bursts of requests (one per
 * place) intermittently get rate-limited, and the marker for whichever
 * place happened to lose the race just silently never appears — so the
 * same trip renders a different set of markers on every load.
 */
async function geocodeWithRetry(
  geocoder: any,
  address: string,
  maxAttempts = 3
): Promise<any | null> {
  if (geocodeCache.has(address)) return geocodeCache.get(address);

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    const result = await new Promise<any | null>((resolve) => {
      geocoder.geocode({ address }, (res: any, status: string) => {
        if (status === "OK" && res?.[0]) {
          resolve(res[0]);
        } else if (status === "OVER_QUERY_LIMIT") {
          resolve("retry");
        } else {
          resolve(null);
        }
      });
    });

    if (result === "retry") {
      // Exponential backoff: 400ms, 800ms, 1600ms.
      await sleep(400 * Math.pow(2, attempt));
      continue;
    }

    geocodeCache.set(address, result);
    return result;
  }

  return null;
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
      .then(async () => {
        if (cancelled || !containerRef.current) return;
        const google = (window as any).google;
        const geocoder = new google.maps.Geocoder();

        const destResult = await geocodeWithRetry(geocoder, destination);
        if (cancelled || !containerRef.current) return;

        const center = destResult
          ? destResult.geometry.location
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

        // Geocode places one at a time (small gap between requests) instead
        // of firing them all in parallel — this is what actually keeps us
        // under Google's per-second rate limit, so the same places resolve
        // successfully every time rather than a different subset each load.
        for (const place of places) {
          if (cancelled) return;

          const result = await geocodeWithRetry(geocoder, `${place.name}, ${destination}`);
          if (cancelled || !result) continue;

          const position = result.geometry.location;

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

          // Small gap between requests so we stay under the rate limit
          // instead of bursting every place's request at once.
          await sleep(150);
        }

        if (cancelled) return;
        if (placed > 0) map.fitBounds(bounds);
        setStatus("ready");
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
