# Research Podcast Pipeline

Automated pipeline that fetches recent academic papers, ranks them using Claude, writes a podcast script, converts it to audio via ElevenLabs, and uploads the episode to Buzzsprout.

## Pipeline Steps

1. **Fetch Papers** — Queries Semantic Scholar for papers published in the last 7 days (falls back to 30 days if fewer than 5 results). Returns the top 20 by citation count.
2. **Rank by Quality** — Sends each paper's metadata to Claude (`claude-sonnet-4-20250514`) for scoring (0–100) based on study type, journal prestige, sample size, recency, and relevance.
3. **Write Script** — Claude writes a 450–550 word podcast script covering the top 5 papers.
4. **Text to Speech** — Converts the script to MP3 using ElevenLabs. Saves as `episode_YYYY-MM-DD.mp3`.
5. **Upload to Buzzsprout** — Publishes the episode with an auto-generated description.

Steps 4 and 5 are skipped gracefully if the relevant API keys are missing; the script is saved to `script_YYYY-MM-DD.txt` instead.

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment variables

Copy the example below into a `.env` file in the same directory as the script:

```env
ANTHROPIC_API_KEY=sk-ant-...
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_ID=Rachel
BUZZSPROUT_API_KEY=...
BUZZSPROUT_PODCAST_ID=...
SEARCH_TERM="microbiota gut brain axis"
```

Only `ANTHROPIC_API_KEY` is required to run Steps 1–3. Steps 4 and 5 are skipped if their keys are absent.

### 3. Run the pipeline

```bash
python research_podcast.py
```

## Configuration

| Variable | Required | Default | Description |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | — | Anthropic API key |
| `ELEVENLABS_API_KEY` | No | — | ElevenLabs API key (skip TTS if absent) |
| `ELEVENLABS_VOICE_ID` | No | `Rachel` | ElevenLabs voice name or ID |
| `BUZZSPROUT_API_KEY` | No | — | Buzzsprout API token |
| `BUZZSPROUT_PODCAST_ID` | No | — | Your Buzzsprout podcast ID |
| `SEARCH_TERM` | No | `microbiota gut brain axis` | Search query for papers |

## Output Files

| File | Description |
|---|---|
| `script_YYYY-MM-DD.txt` | Podcast script (saved when ElevenLabs/Buzzsprout keys are missing) |
| `episode_YYYY-MM-DD.mp3` | Audio episode (when ElevenLabs key is present) |

## Notes

- The Semantic Scholar API is free and requires no key for basic usage.
- ElevenLabs free tier has a monthly character limit; the `eleven_multilingual_v2` model is used by default.
- Buzzsprout's API token and podcast ID can be found under **Account Settings → API Access** in your Buzzsprout dashboard.
