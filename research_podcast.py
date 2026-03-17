#!/usr/bin/env python3
"""
Automated Research Podcast Pipeline
Fetches recent papers, ranks them via Claude, writes a podcast script,
converts to audio via ElevenLabs, and uploads to Buzzsprout.
"""

import os
import sys
import json
import datetime
import requests
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "Rachel")
BUZZSPROUT_API_KEY = os.getenv("BUZZSPROUT_API_KEY", "")
BUZZSPROUT_PODCAST_ID = os.getenv("BUZZSPROUT_PODCAST_ID", "")
SEARCH_TERM = os.getenv("SEARCH_TERM", "microbiota gut brain axis")

CLAUDE_MODEL = "claude-sonnet-4-20250514"
TODAY = datetime.date.today()
DATE_STR = TODAY.strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# STEP 1 — FETCH PAPERS
# ---------------------------------------------------------------------------

def fetch_papers(search_term: str, top_n: int = 20) -> list[dict]:
    """Query Semantic Scholar for recent papers, return top_n by citation count."""
    print(f"\n[Step 1] Fetching papers for: '{search_term}'")

    base_url = "https://api.semanticscholar.org/graph/v1/paper/search"
    fields = "title,abstract,authors,year,venue,citationCount,externalIds,url,publicationDate"

    def query(days_back: int) -> list[dict]:
        cutoff = (TODAY - datetime.timedelta(days=days_back)).isoformat()
        params = {
            "query": search_term,
            "fields": fields,
            "limit": 100,
            "publicationDateOrYear": f"{cutoff}:",
        }
        resp = requests.get(base_url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json().get("data", [])

    papers = query(7)
    if len(papers) < 5:
        print(f"  Only {len(papers)} papers in last 7 days — expanding to 30 days...")
        papers = query(30)

    if len(papers) < 3:
        print(f"  WARNING: Only {len(papers)} papers found. Exiting.")
        sys.exit(1)

    # Sort by citation count descending
    papers.sort(key=lambda p: p.get("citationCount") or 0, reverse=True)
    papers = papers[:top_n]

    print(f"  Found {len(papers)} papers (top {top_n} by citation count).")
    for i, p in enumerate(papers[:5], 1):
        print(f"  {i}. {p['title'][:80]} | citations: {p.get('citationCount', 0)}")

    return papers


# ---------------------------------------------------------------------------
# STEP 2 — RANK BY QUALITY (Claude)
# ---------------------------------------------------------------------------

def rank_papers(papers: list[dict], search_term: str, top_n: int = 5) -> list[dict]:
    """Send papers to Claude for quality scoring, return top_n."""
    import anthropic

    print(f"\n[Step 2] Ranking {len(papers)} papers with Claude ({CLAUDE_MODEL})...")

    if not ANTHROPIC_API_KEY:
        print("  ERROR: ANTHROPIC_API_KEY not set.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    papers_text = ""
    for i, p in enumerate(papers, 1):
        authors = ", ".join(a.get("name", "") for a in (p.get("authors") or [])[:3])
        doi = (p.get("externalIds") or {}).get("DOI", "N/A")
        papers_text += f"""
Paper {i}:
  Title: {p.get('title', 'N/A')}
  Authors: {authors}
  Year: {p.get('year', 'N/A')}
  Venue/Journal: {p.get('venue', 'N/A')}
  Citation Count: {p.get('citationCount', 0)}
  DOI: {doi}
  Abstract: {(p.get('abstract') or 'No abstract available.')[:600]}
"""

    prompt = f"""You are a scientific quality assessor. Score each paper out of 100 based on:
1. Study type (RCT=highest, meta-analysis, cohort, case study, review, preprint=lowest)
2. Journal prestige (Nature/Cell/Science-tier > specialist top journals > general journals > preprints)
3. Sample size if mentioned in abstract (larger = better)
4. Recency (more recent = better)
5. Relevance to search term: "{search_term}"

Papers to evaluate:
{papers_text}

Return ONLY a JSON array (no markdown, no explanation) with exactly this structure for each paper:
[
  {{
    "paper_number": 1,
    "score": 85,
    "reasoning": "One-line explanation of score"
  }},
  ...
]

Score all {len(papers)} papers."""

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    scores = json.loads(raw)

    # Merge scores into paper dicts
    score_map = {s["paper_number"]: s for s in scores}
    for i, p in enumerate(papers, 1):
        meta = score_map.get(i, {})
        p["claude_score"] = meta.get("score", 0)
        p["claude_reasoning"] = meta.get("reasoning", "")

    # Sort by score descending, take top_n
    ranked = sorted(papers, key=lambda p: p.get("claude_score", 0), reverse=True)[:top_n]

    print(f"  Top {top_n} papers after ranking:")
    for i, p in enumerate(ranked, 1):
        print(f"  {i}. [{p['claude_score']}/100] {p['title'][:70]}")
        print(f"     → {p['claude_reasoning']}")

    return ranked


# ---------------------------------------------------------------------------
# STEP 3 — WRITE PODCAST SCRIPT (Claude)
# ---------------------------------------------------------------------------

def write_script(papers: list[dict], search_term: str) -> str:
    """Ask Claude to write a 3-4 minute podcast script covering the top papers."""
    import anthropic

    print(f"\n[Step 3] Writing podcast script with Claude ({CLAUDE_MODEL})...")

    if not ANTHROPIC_API_KEY:
        print("  ERROR: ANTHROPIC_API_KEY not set.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    papers_summary = ""
    for i, p in enumerate(papers, 1):
        authors = ", ".join(a.get("name", "") for a in (p.get("authors") or [])[:2])
        papers_summary += f"""
Paper {i}: "{p.get('title', 'N/A')}"
  Authors: {authors} | Venue: {p.get('venue', 'N/A')} | Year: {p.get('year', 'N/A')}
  Score: {p.get('claude_score', 0)}/100 — {p.get('claude_reasoning', '')}
  Abstract: {(p.get('abstract') or 'No abstract available.')[:500]}
"""

    prompt = f"""Write a 3-4 minute podcast script (approximately 450-550 words) about the latest research on "{search_term}".

Today's date: {DATE_STR}

Top papers to cover:
{papers_summary}

Tone: Engaging, intelligent, and accessible — like a smart science podcast for a curious general audience. Think "Radiolab" meets "Nature Podcast."

Structure:
1. Punchy intro hook (1-2 sentences that grab attention)
2. Brief overview of why this topic matters right now (2-3 sentences)
3. Cover each paper in 2-3 sentences (highlight the key finding and why it matters)
4. Closing takeaway (1-2 sentences that leave the listener thinking)

Output the script as plain text only. No stage directions, no [MUSIC] cues, no host names, no headers. Just the spoken words, ready to be read aloud."""

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    script = response.content[0].text.strip()
    word_count = len(script.split())
    print(f"  Script written: {word_count} words (~{word_count // 140} min read).")
    return script


# ---------------------------------------------------------------------------
# STEP 4 — TEXT TO SPEECH (ElevenLabs)
# ---------------------------------------------------------------------------

def text_to_speech(script: str) -> str | None:
    """Convert script to MP3 using ElevenLabs. Returns path to MP3 or None."""
    if not ELEVENLABS_API_KEY:
        print("\n[Step 4] Skipping TTS — ELEVENLABS_API_KEY not set.")
        return None

    print(f"\n[Step 4] Converting script to speech (voice: {ELEVENLABS_VOICE_ID})...")

    try:
        from elevenlabs.client import ElevenLabs
        from elevenlabs import save
    except ImportError:
        print("  ERROR: elevenlabs package not installed. Run: pip install elevenlabs")
        return None

    client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
    audio = client.generate(
        text=script,
        voice=ELEVENLABS_VOICE_ID,
        model="eleven_multilingual_v2",
    )

    mp3_path = f"episode_{DATE_STR}.mp3"
    save(audio, mp3_path)
    print(f"  Saved audio: {mp3_path}")
    return mp3_path


# ---------------------------------------------------------------------------
# STEP 5 — UPLOAD TO BUZZSPROUT
# ---------------------------------------------------------------------------

def upload_to_buzzsprout(mp3_path: str, script: str, search_term: str) -> bool:
    """Upload the episode to Buzzsprout. Returns True on success."""
    if not BUZZSPROUT_API_KEY or not BUZZSPROUT_PODCAST_ID:
        print("\n[Step 5] Skipping Buzzsprout upload — API key or podcast ID not set.")
        return False

    print(f"\n[Step 5] Uploading to Buzzsprout (podcast {BUZZSPROUT_PODCAST_ID})...")

    title = f"Research Digest: {search_term} — {DATE_STR}"

    # Auto-generate 2-sentence description from the start of the script
    sentences = [s.strip() for s in script.replace("\n", " ").split(".") if s.strip()]
    description = ". ".join(sentences[:2]) + "."

    url = f"https://www.buzzsprout.com/api/{BUZZSPROUT_PODCAST_ID}/episodes.json"
    headers = {"Authorization": f"Token token={BUZZSPROUT_API_KEY}"}

    with open(mp3_path, "rb") as f:
        data = {
            "title": title,
            "description": description,
            "private": False,
        }
        files = {"audio_file": (os.path.basename(mp3_path), f, "audio/mpeg")}
        resp = requests.post(url, headers=headers, data=data, files=files, timeout=120)

    if resp.status_code in (200, 201):
        ep = resp.json()
        print(f"  Uploaded! Episode ID: {ep.get('id')} — '{title}'")
        return True
    else:
        print(f"  ERROR: Buzzsprout returned {resp.status_code}: {resp.text[:200]}")
        return False


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  Research Podcast Pipeline")
    print(f"  Search term : {SEARCH_TERM}")
    print(f"  Date        : {DATE_STR}")
    print(f"  Claude model: {CLAUDE_MODEL}")
    print("=" * 60)

    # Step 1: Fetch papers
    papers = fetch_papers(SEARCH_TERM)

    # Step 2: Rank by quality
    top_papers = rank_papers(papers, SEARCH_TERM)

    # Step 3: Write podcast script
    script = write_script(top_papers, SEARCH_TERM)

    print("\n" + "-" * 60)
    print("PODCAST SCRIPT PREVIEW (first 300 chars):")
    print(script[:300] + "...")
    print("-" * 60)

    # Steps 4 & 5 require API keys — save script to file if keys are missing
    has_elevenlabs = bool(ELEVENLABS_API_KEY)
    has_buzzsprout = bool(BUZZSPROUT_API_KEY and BUZZSPROUT_PODCAST_ID)

    if not has_elevenlabs or not has_buzzsprout:
        script_path = f"script_{DATE_STR}.txt"
        with open(script_path, "w") as f:
            f.write(f"Search Term: {SEARCH_TERM}\n")
            f.write(f"Date: {DATE_STR}\n\n")
            f.write(script)
        print(f"\n[Info] Script saved to: {script_path}")

    # Step 4: Text to speech
    mp3_path = text_to_speech(script)

    # Step 5: Upload to Buzzsprout
    if mp3_path:
        upload_to_buzzsprout(mp3_path, script, SEARCH_TERM)

    print("\n[Done] Pipeline complete.")


if __name__ == "__main__":
    main()
