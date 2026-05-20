# Automotive Hermes Profile — Design Spec
**Date:** 2026-05-19
**Status:** Approved

---

## Overview

A dedicated Hermes profile (`auto-parts`) that enables an automotive parts identification assistant over WhatsApp. Users post a photo of a part, a VIN number, and an explicit request (e.g., "Can you find me this part?"). The agent identifies the part using its native vision + LLM + web search capabilities and optionally queries a parts catalog database via a separate microservice.

---

## Architecture

Two services deployed on Railway in the same project:

```
WhatsApp Group
  │  photo + VIN + explicit request ("find me this part")
  ▼
┌─────────────────────────────────┐
│  hermes-auto-parts              │  Railway — Public
│  (Hermes, auto-parts profile)   │
│  ┌─────────────────────────┐    │
│  │  WhatsApp Gateway       │    │
│  └───────────┬─────────────┘    │
│              │                  │
│  ┌───────────▼─────────────┐    │
│  │  Agent                  │    │
│  │  - native vision        │    │
│  │  - native LLM reasoning │    │
│  │  - native web search    │    │
│  │  - parts_db_lookup tool │────┼──► hermes-auto-parts-api (internal)
│  └─────────────────────────┘    │
└─────────────────────────────────┘

┌─────────────────────────────────┐
│  hermes-auto-parts-api          │  Railway — Private (internal only)
│  Thin DB proxy (FastAPI)        │
│  POST /lookup                   │
│  └── db_adapter.py (pluggable)  │
└─────────────────────────────────┘
```

---

## Trigger Conditions

The agent responds based on **context**, not a rigid checklist. The SOUL.md instructs the agent to use judgment:

- A photo + "what part is this?" → agent identifies the part, attempts lookup
- A VIN + part name in text → agent skips vision, goes straight to lookup
- A photo + VIN + "find me this part" → full flow (vision + VIN + DB/web)
- A general automotive question (no photo, no VIN) → agent answers from LLM knowledge or web search
- An ambiguous message → agent asks a clarifying question before acting

The agent does not trigger on non-automotive messages in the chat.

---

## End-to-End Data Flow

1. WhatsApp group member sends: photo of part + VIN + "Can you find me this part?"
2. Hermes gateway receives the message, extracts the image URL and VIN string
3. Hermes agent uses **native vision** to describe the part from the image
4. Hermes agent uses **native LLM** to combine part description + VIN-derived vehicle info (make/model/year) into a structured query
5. Hermes agent calls `parts_db_lookup` tool → `POST hermes-auto-parts-api.railway.internal/lookup`
6. If DB returns a match: reply with part number, name, and category
7. If no match (or API unavailable): Hermes falls back to **native web search** to resolve the part number
8. Hermes replies to the WhatsApp group with the result

---

## Hermes Profile Changes (this repo)

### What stays the same (no code changes)
- Vision capability (native to the configured model)
- LLM reasoning (native)
- Web search (built-in tool, already enabled)
- Shell exec, file editor, bash runner (kept — useful for research edge cases)

### What gets disabled in `config.yaml`
- All messaging platforms except WhatsApp
- Computer use
- Image generation
- Video generation
- Kanban
- Cron / curator
- Multi-agent dispatch

### New files (minimal)
| File | Purpose |
|---|---|
| `tools/automotive/parts_lookup.py` | ~50-line HTTP client tool — calls `PARTS_API_URL/lookup` with part description + VIN, returns structured result |
| `~/.hermes/profiles/auto-parts/SOUL.md` | Automotive assistant persona — focused, concise, part-number-oriented |
| `~/.hermes/profiles/auto-parts/config.yaml` | Profile config — WhatsApp enabled, unnecessary tools disabled |

### Tool schema
```python
parts_db_lookup(
    part_description: str,  # from vision analysis
    vin: str,               # raw VIN from user message
) -> {
    "part_number": str,
    "part_name": str,
    "category": str,
    "confidence": float,
    "source": "db" | "not_found"
}
```

---

## hermes-auto-parts-api (new repo)

**Repo:** `durambrook/hermes-auto-parts-api` (sibling directory: `../hermes-auto-parts-api/`)

**Purpose:** Thin DB query proxy. No vision, no LLM, no web search. Receives a structured query and returns matching parts from the catalog.

### Structure
```
hermes-auto-parts-api/
├── main.py                  # FastAPI app
├── routers/
│   └── parts.py             # POST /lookup
├── services/
│   └── db_adapter.py        # Abstract PartsDB interface + mock stub
├── Dockerfile
├── railway.toml
└── .env.example
```

### Endpoint
```
POST /lookup
{
  "part_description": "front brake caliper, single piston",
  "vin": "1HGBH41JXMN109186"
}
→ {
  "part_number": "33901-S84-A01",
  "part_name": "Brake Caliper – Front",
  "category": "Brakes",
  "vehicle": { "make": "Honda", "model": "Civic", "year": "2021" },
  "confidence": 0.92
}
```

VIN decoding (make/model/year) is handled internally by the API — the caller only needs to pass the raw VIN string.

### DB Adapter interface (pluggable)
```python
class PartsDB(ABC):
    async def lookup(self, description: str, vehicle: VehicleInfo) -> PartResult | None:
        ...

class MockPartsDB(PartsDB):
    # Returns plausible stub data for development
    ...
```

Real database implementations (MySQL, REST catalog API, etc.) implement `PartsDB` and are swapped in via env var (`PARTS_DB_BACKEND`).

---

## Railway Deployment

| Service | Repo | Visibility | Notes |
|---|---|---|---|
| `hermes-auto-parts` | this repo | **Public** | WhatsApp webhook receiver |
| `hermes-auto-parts-api` | `durambrook/hermes-auto-parts-api` | **Private** | Internal networking only |

### Networking
- `hermes-auto-parts` calls `hermes-auto-parts-api` via Railway private networking: `http://hermes-auto-parts-api.railway.internal/lookup`
- `hermes-auto-parts-api` is not publicly reachable

### Key environment variables
| Var | Service | Value |
|---|---|---|
| `PARTS_API_URL` | hermes-auto-parts | `http://hermes-auto-parts-api.railway.internal` |
| `HERMES_HOME` | hermes-auto-parts | `/data/profiles/auto-parts` |
| `PARTS_DB_BACKEND` | hermes-auto-parts-api | `mock` (until real DB is ready) |
| `ANTHROPIC_API_KEY` | hermes-auto-parts | (secret) |

---

## WhatsApp Connection

- Backend: `whatsapp-web.js` (personal account, no Meta approval required)
- On first deploy: Hermes prints a QR code in logs — scan with the bot's WhatsApp account
- The bot responds in **both group chats and individual DMs** — no restriction to a single group
- Session persists in Railway volume so re-auth isn't needed on redeploy

---

## Web Dashboard

Hermes ships a built-in web UI (`hermes web`, default port 9119). The `hermes-auto-parts` Railway service exposes this as a second public port so you can monitor the agent from a browser.

**What the dashboard shows (built-in):**
- Session history (all WhatsApp conversations)
- Gateway status (WhatsApp connection state, QR code on first auth)
- Config editor (toolset, model, etc.)
- Logs viewer

**Access:** Railway will assign a public URL to port 9119 on the `hermes-auto-parts` service. Protect it with Hermes's built-in dashboard auth (set `WEB_AUTH_TOKEN` env var).

**Optional later:** A custom "Auto Parts" tab (Hermes dashboard plugin) could show lookup history, part hit rates, and DB adapter status in a single view.

---

## Phased Rollout

| Phase | What works |
|---|---|
| **Phase 1 (now)** | Vision + LLM + web search resolves parts. `hermes-auto-parts-api` returns mock data |
| **Phase 2** | Real DB wired into `db_adapter.py`. DB is primary, web search is fallback |
| **Phase 3** | Optionally expose `hermes-auto-parts-api` to additional clients (mobile app, web UI) |

---

## Out of Scope

- User authentication / authorization within WhatsApp
- Parts ordering or purchasing
- Image generation or video
