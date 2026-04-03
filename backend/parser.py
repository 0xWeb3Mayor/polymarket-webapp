import re
import requests
import config


def extract_condition_id(url: str) -> str | None:
    """Extract Polymarket condition_id from various URL formats.

    Handles:
    - Raw condition_id: 0xabc123...
    - /market/{condition_id}
    - /event/{slug}/{market-slug} (slug may be condition_id)
    """
    if not url or not url.strip():
        return None

    url = url.strip()

    # Format 1: raw condition_id (0x + hex chars)
    if re.match(r'^0x[a-fA-F0-9]+$', url):
        return url

    # Format 2: /market/{condition_id}
    m = re.search(r'/market/(0x[a-fA-F0-9]+)', url)
    if m:
        return m.group(1)

    # Format 3: /event/{slug}/{market-slug}
    # Check if the market-slug itself is a condition_id
    m = re.search(r'/event/[^/]+/(0x[a-fA-F0-9]+)', url)
    if m:
        return m.group(1)

    # Format 3b: /event/{slug}/{text-slug} — resolve via API
    m = re.search(r'polymarket\.com/event/[^/]+/([^/?#]+)', url)
    if m:
        return _resolve_slug(m.group(1))

    return None


def _resolve_slug(slug: str) -> str | None:
    """Resolve a text market slug to a condition_id via Polymarket API."""
    try:
        resp = requests.get(
            f"{config.API_BASE}/markets",
            params={"slug": slug},
            timeout=10
        )
        if resp.ok:
            data = resp.json()
            markets = data.get("data", [])
            if markets:
                return markets[0].get("condition_id")
    except requests.RequestException:
        pass
    return None
