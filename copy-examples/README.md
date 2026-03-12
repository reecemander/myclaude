# Copy Examples

This folder is how you "train" the copywriting agent on your voice.

**The agent reads every file here before writing anything.** The more good examples you add, the more accurately it will match your style.

---

## How to Add Examples

1. **Paste copy that performed well** — high open rates, good conversion, copy you're proud of
2. Save it as a `.md` file with a descriptive name (e.g., `welcome-email-45pct-open.md`)
3. Include context at the top so the agent understands what worked

### File format

```markdown
---
type: [email | landing-page | ad | social | headline]
result: [e.g., "47% open rate", "3.2% conversion", "best-performing ad Q3 2024"]
audience: [who this was written for]
---

[paste the copy here, exactly as it ran]
```

The `result` field is especially useful — it tells the agent which patterns led to real outcomes.

---

## What Makes a Good Example

- Copy that **actually performed** (don't add stuff you think was good but didn't convert)
- A **range of formats** — emails, headlines, CTAs, long-form pages
- **Different audiences or offers** if you write for more than one product/market
- At least **3–5 examples** for the agent to find real patterns

---

## Examples Already in This Folder

- `pylopurge-landing-page.md` — landing page for PyloPurge supplement (GoodGut Nutrition)

---

## Privacy Note

Don't add copy that contains customer names, private data, or unreleased pricing. These files will be read by AI on every copywriting task.
