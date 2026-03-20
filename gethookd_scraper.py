#!/usr/bin/env python3
"""
GetHookd.ai - Winning Ads Scraper
Fetches top-performing ads from the Explore endpoint, sorted by engagement
and longevity (longest running = likely profitable/evergreen).

Usage:
    python gethookd_scraper.py --api-key YOUR_KEY
    python gethookd_scraper.py --api-key YOUR_KEY --pages 3 --output ads.json
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone

import requests

BASE_URL = "https://app.gethookd.ai"
HEADERS_TEMPLATE = {
    "Accept": "application/json",
    "Content-Type": "application/json",
}


def make_headers(api_key: str) -> dict:
    return {**HEADERS_TEMPLATE, "Authorization": f"Bearer {api_key}"}


def check_auth(api_key: str) -> dict:
    """Validate API key and return workspace info."""
    resp = requests.get(
        f"{BASE_URL}/api/v1/authcheck",
        headers=make_headers(api_key),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_explore_page(api_key: str, page: int = 1, per_page: int = 100, **filters) -> dict:
    """
    Fetch a page of ads from the Explore endpoint.

    Common filter params (adjust based on your GetHookd plan/docs):
      - sort_by:       e.g. "likes", "shares", "created_at"
      - sort_direction: "asc" | "desc"
      - date_from:     ISO date string
      - date_to:       ISO date string
      - platform:      "facebook" | "instagram" | etc.
      - niche:         keyword/category string
      - format:        "image" | "video" | "carousel"
    """
    params = {
        "page": page,
        "per_page": per_page,
        **filters,
    }
    # Remove None values
    params = {k: v for k, v in params.items() if v is not None}

    resp = requests.get(
        f"{BASE_URL}/api/v1/explore",
        headers=make_headers(api_key),
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_all_ads(api_key: str, max_pages: int = 5, per_page: int = 100, **filters):

    """Fetch multiple pages of ads and return combined list."""
    all_ads = []

    for page in range(1, max_pages + 1):
        print(f"  Fetching page {page}/{max_pages}...", end=" ", flush=True)
        try:
            data = fetch_explore_page(api_key, page=page, per_page=per_page, **filters)
        except requests.HTTPError as e:
            print(f"HTTP {e.response.status_code} — stopping pagination.")
            break

        ads = data.get("data", [])
        if not ads:
            print("no more results.")
            break

        all_ads.extend(ads)
        print(f"got {len(ads)} ads (total: {len(all_ads)})")

        meta = data.get("meta", {})
        if page >= meta.get("last_page", 1):
            break

        time.sleep(0.5)  # be polite to the API

    return all_ads


def rank_ads(ads: list[dict]) -> list[dict]:
    """
    Score and rank ads by:
      1. Engagement (likes + shares + comments where available)
      2. Longevity (how long the ad has been running — older start = more evergreen)
    Returns ads sorted best-first.
    """
    now = datetime.now(timezone.utc)

    def score(ad):
        # Engagement score — field names may vary; adjust to actual response keys
        likes = ad.get("likes_count") or ad.get("likes") or 0
        shares = ad.get("shares_count") or ad.get("shares") or 0
        comments = ad.get("comments_count") or ad.get("comments") or 0
        engagement = likes + (shares * 2) + comments  # shares weighted higher

        # Longevity score — days the ad has been active
        start_raw = ad.get("started_at") or ad.get("created_at") or ad.get("first_seen_at")
        longevity_days = 0
        if start_raw:
            try:
                start_dt = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
                longevity_days = (now - start_dt).days
            except ValueError:
                pass

        # Combined score: engagement + 5pts per day running (evergreen bonus)
        return engagement + (longevity_days * 5)

    return sorted(ads, key=score, reverse=True)


def print_ad_summary(ad: dict, rank: int):
    """Print a readable summary of a single ad."""
    title = ad.get("title") or ad.get("headline") or ad.get("ad_id") or f"Ad #{ad.get('id')}"
    likes = ad.get("likes_count") or ad.get("likes") or "?"
    shares = ad.get("shares_count") or ad.get("shares") or "?"
    started = ad.get("started_at") or ad.get("created_at") or ad.get("first_seen_at") or "unknown"
    brand = ad.get("brand_name") or ad.get("advertiser") or "unknown brand"
    url = ad.get("url") or ad.get("ad_url") or ""
    media_url = ""
    if ad.get("media") and isinstance(ad["media"], list) and ad["media"]:
        media_url = ad["media"][0].get("url", "")

    print(f"\n{'─'*60}")
    print(f"#{rank:>3}  {title}")
    print(f"     Brand:    {brand}")
    print(f"     Likes:    {likes}  |  Shares: {shares}")
    print(f"     Started:  {started}")
    if url:
        print(f"     Ad URL:   {url}")
    if media_url:
        print(f"     Media:    {media_url}")


def main():
    parser = argparse.ArgumentParser(description="Fetch winning ads from GetHookd.ai")
    parser.add_argument("--api-key", required=True, help="Your GetHookd Public API key")
    parser.add_argument("--pages", type=int, default=3, help="Pages to fetch (default: 3)")
    parser.add_argument("--per-page", type=int, default=100, help="Ads per page (default: 100)")
    parser.add_argument("--top", type=int, default=20, help="Show top N ads (default: 20)")
    parser.add_argument("--niche", type=str, default=None, help="Filter by niche/keyword")
    parser.add_argument("--platform", type=str, default=None, help="Platform filter (e.g. facebook)")
    parser.add_argument("--format", type=str, default=None, help="Ad format (image/video/carousel)")
    parser.add_argument("--output", type=str, default=None, help="Save full results to JSON file")
    args = parser.parse_args()

    # 1. Verify API key
    print("Authenticating...")
    try:
        auth = check_auth(args.api_key)
    except requests.HTTPError as e:
        print(f"Auth failed: HTTP {e.response.status_code}")
        sys.exit(1)

    workspace = auth.get("data", {}).get("workspace", {})
    scopes = auth.get("data", {}).get("scopes", [])
    print(f"Authenticated as: {workspace.get('name')} (scopes: {', '.join(scopes)})")

    if "explore:read" not in scopes:
        print("Warning: 'explore:read' scope not found — /explore calls may fail.")

    # 2. Fetch ads
    print(f"\nFetching ads (up to {args.pages} pages × {args.per_page} per page)...")
    filters = {
        "sort_by": "likes",          # sort by engagement
        "sort_direction": "desc",
        "niche": args.niche,
        "platform": args.platform,
        "format": args.format,
    }
    ads = fetch_all_ads(args.api_key, max_pages=args.pages, per_page=args.per_page, **filters)

    if not ads:
        print("No ads returned. Check your scopes or filters.")
        sys.exit(1)

    # 3. Rank by engagement + longevity
    print(f"\nRanking {len(ads)} ads by engagement + longevity...")
    ranked = rank_ads(ads)

    # 4. Display top N
    top_n = ranked[: args.top]
    print(f"\n{'='*60}")
    print(f"  TOP {len(top_n)} WINNING ADS")
    print(f"{'='*60}")
    for i, ad in enumerate(top_n, start=1):
        print_ad_summary(ad, i)

    # 5. Optionally save full results
    if args.output:
        with open(args.output, "w") as f:
            json.dump({"fetched_at": datetime.now(timezone.utc).isoformat(), "ads": ranked}, f, indent=2)
        print(f"\nFull results saved to: {args.output}")

    print(f"\nDone. {len(ads)} ads fetched, top {len(top_n)} shown.")


if __name__ == "__main__":
    main()
