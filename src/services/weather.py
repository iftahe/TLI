import logging
from datetime import timedelta

import requests

from src.bot.utils import get_now

logger = logging.getLogger(__name__)

# Tel Mond, Israel
_LAT = 32.25
_LON = 34.93
_FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"


def get_tomorrow_forecast(api_key: str) -> dict | None:
    """Fetch tomorrow's weather forecast from OpenWeatherMap.

    Returns dict with min_temp, max_temp, humidity, rain_chance
    or None on any failure.
    """
    try:
        resp = requests.get(
            _FORECAST_URL,
            params={
                "lat": _LAT,
                "lon": _LON,
                "units": "metric",
                "lang": "he",
                "appid": api_key,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error(f"OpenWeatherMap API request failed: {e}")
        return None

    try:
        now = get_now()
        tomorrow = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        tomorrow_end = tomorrow.replace(hour=23, minute=59, second=59)

        entries = []
        for entry in data.get("list", []):
            from datetime import datetime, timezone
            dt_utc = datetime.fromtimestamp(entry["dt"], tz=timezone.utc)
            dt_israel = dt_utc.astimezone(now.tzinfo)
            if tomorrow <= dt_israel <= tomorrow_end:
                entries.append(entry)

        if not entries:
            logger.warning("No forecast entries found for tomorrow")
            return None

        min_temp = min(e["main"]["temp_min"] for e in entries)
        max_temp = max(e["main"]["temp_max"] for e in entries)
        humidity = round(sum(e["main"]["humidity"] for e in entries) / len(entries))
        rain_chance = round(max(e.get("pop", 0) for e in entries) * 100)

        return {
            "min_temp": round(min_temp),
            "max_temp": round(max_temp),
            "humidity": humidity,
            "rain_chance": rain_chance,
        }
    except Exception as e:
        logger.error(f"Error parsing OpenWeatherMap response: {e}", exc_info=True)
        return None


def format_clothing_recommendation(forecast: dict) -> str:
    """Generate Hebrew clothing recommendation for adults and children."""
    max_t = forecast["max_temp"]
    min_t = forecast["min_temp"]
    rain = forecast["rain_chance"]

    if max_t >= 30:
        adults = "👕 חם מחר! בגדים קלים ומאווררים. אל תשכחו לשתות"
    elif max_t >= 25:
        adults = "👕 נעים בחוץ — חולצת טי וקצרים"
    elif max_t >= 20 and min_t >= 15:
        adults = "🧥 נעים ביום, קריר בערב — קחו סוודר קל"
    elif max_t >= 15:
        adults = "🧥 שכבות! חולצה ארוכה + ז'קט"
    else:
        adults = "🧣 קר מחר! מעיל חם, צעיף וכובע"

    if rain >= 70:
        adults += "\n☔ סיכוי גבוה לגשם — קחו מטרייה!"
    elif rain >= 40:
        adults += "\n🌂 אולי ירד גשם — שווה לקחת מטרייה"

    kids = ""
    if min_t < 15:
        kids = "🧒 לילדים: שכבה נוספת + כובע"
    if rain >= 40:
        kids_rain = "מגפיים ומעיל גשם"
        if kids:
            kids += " + " + kids_rain
        else:
            kids = "🧒 לילדים: " + kids_rain

    result = adults
    if kids:
        result += "\n" + kids

    return result


def format_weather_line(forecast: dict) -> str:
    """Format a single consolidated weather data line."""
    return (
        f"🌡️ {forecast['min_temp']}°-{forecast['max_temp']}° | "
        f"💧 {forecast['humidity']}% | "
        f"🌧️ {forecast['rain_chance']}% גשם"
    )
