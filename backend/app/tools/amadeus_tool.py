"""
AmadeusTool: best-effort Amadeus sandbox wrapper for flight offers.

Design decisions per roadmap:
  - Amadeus sandbox data is sparse for many routes — this is documented and expected.
  - Real API call is attempted only if AMADEUS_API_KEY + AMADEUS_API_SECRET are set.
  - Rate limits, timeouts, empty results all return a structured error dict — never crash.
  - On any failure, falls back to FlightAgent mock data gracefully.
  - Fabricating data is explicitly prohibited — empty sandbox = "not found", not fake data.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def _get_amadeus_credentials() -> tuple[str | None, str | None]:
    """Read Amadeus credentials from environment — never raises."""
    try:
        from app.core.config import get_settings
        s = get_settings()
        key = getattr(s, "amadeus_api_key", None) or os.environ.get("AMADEUS_API_KEY")
        secret = getattr(s, "amadeus_api_secret", None) or os.environ.get("AMADEUS_API_SECRET")
        return key, secret
    except Exception as exc:
        logger.debug("Could not load Amadeus credentials: %s", exc)
        return None, None


def search_flights_amadeus(
    origin_iata: str,
    destination_iata: str,
    departure_date: str,
    adults: int = 1,
    max_results: int = 5,
) -> dict[str, Any]:
    """
    Search Amadeus Flight Offers Search API for real flight data.

    Args:
        origin_iata:      IATA code (e.g., "BOM" for Mumbai).
        destination_iata: IATA code (e.g., "DEL" for Delhi).
        departure_date:   Date string YYYY-MM-DD.
        adults:           Number of adult passengers.
        max_results:      Maximum number of offers to return.

    Returns:
        Dict with keys: found, source, offers (list), error (when found=False).
        Never raises — all errors return found=False with error description.
    """
    api_key, api_secret = _get_amadeus_credentials()

    if not api_key or not api_secret:
        logger.info("AmadeusTool: credentials not configured — skipping live call")
        return {
            "found": False,
            "source": "amadeus_sandbox",
            "offers": [],
            "error": "Amadeus API credentials not configured (AMADEUS_API_KEY / AMADEUS_API_SECRET missing).",
            "fallback_note": "Using mock flight data from FlightAgent instead.",
        }

    try:
        import httpx

        # Step 1: Get access token
        token_resp = httpx.post(
            "https://test.api.amadeus.com/v1/security/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": api_key,
                "client_secret": api_secret,
            },
            timeout=10.0,
        )
        token_resp.raise_for_status()
        access_token = token_resp.json()["access_token"]

        # Step 2: Search flight offers
        search_resp = httpx.get(
            "https://test.api.amadeus.com/v2/shopping/flight-offers",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "originLocationCode": origin_iata.upper(),
                "destinationLocationCode": destination_iata.upper(),
                "departureDate": departure_date,
                "adults": adults,
                "max": max_results,
                "currencyCode": "INR",
            },
            timeout=15.0,
        )

        if search_resp.status_code == 429:
            return {
                "found": False,
                "source": "amadeus_sandbox",
                "offers": [],
                "error": "Amadeus API rate limit hit (429). Try again after a minute.",
                "fallback_note": "Using mock flight data from FlightAgent.",
            }

        search_resp.raise_for_status()
        data = search_resp.json()
        offers_raw = data.get("data", [])

        if not offers_raw:
            return {
                "found": False,
                "source": "amadeus_sandbox",
                "offers": [],
                "error": (
                    f"Amadeus sandbox returned 0 offers for {origin_iata} -> {destination_iata} "
                    f"on {departure_date}. Sandbox data is sparse for some routes — this is expected."
                ),
                "fallback_note": "Using mock flight data from FlightAgent for demo reliability.",
            }

        # Parse relevant fields from offers
        offers = []
        for offer in offers_raw[:max_results]:
            try:
                price = offer.get("price", {})
                itineraries = offer.get("itineraries", [])
                segments = itineraries[0].get("segments", []) if itineraries else []
                carrier_codes = list({s.get("carrierCode", "??") for s in segments})

                offers.append({
                    "carrier_codes": carrier_codes,
                    "price_inr": float(price.get("total", 0)),
                    "currency": price.get("currency", "INR"),
                    "duration": itineraries[0].get("duration", "N/A") if itineraries else "N/A",
                    "stops": len(segments) - 1,
                    "departure": segments[0].get("departure", {}).get("at", "N/A") if segments else "N/A",
                    "arrival": segments[-1].get("arrival", {}).get("at", "N/A") if segments else "N/A",
                })
            except (KeyError, IndexError, TypeError) as parse_err:
                logger.debug("AmadeusTool: failed to parse offer: %s", parse_err)
                continue

        if not offers:
            return {
                "found": False,
                "source": "amadeus_sandbox",
                "offers": [],
                "error": "Amadeus returned offers but none could be parsed successfully.",
                "fallback_note": "Using mock flight data from FlightAgent.",
            }

        return {
            "found": True,
            "source": "amadeus_sandbox",
            "offers": offers,
            "count": len(offers),
        }

    except Exception as exc:
        logger.warning(
            "AmadeusTool: %s -> %s search failed: %s", origin_iata, destination_iata, exc
        )
        return {
            "found": False,
            "source": "amadeus_sandbox",
            "offers": [],
            "error": f"Amadeus API call failed: {type(exc).__name__}: {exc}",
            "fallback_note": "Using mock flight data from FlightAgent.",
        }
