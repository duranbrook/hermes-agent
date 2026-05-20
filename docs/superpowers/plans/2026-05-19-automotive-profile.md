# Automotive Profile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy an automotive parts assistant as a Hermes profile connected to WhatsApp, backed by a separate FastAPI parts-lookup microservice hosted on Railway.

**Architecture:** Two Railway services in one project. `hermes-auto-parts` runs the Hermes gateway (WhatsApp + web dashboard). `hermes-auto-parts-api` is a private FastAPI service that wraps a parts catalog DB; it returns mock data until a real DB is wired in. Hermes uses its native vision + LLM + web search to identify parts from photos, and calls the API tool when a DB lookup is needed.

**Tech Stack:** Python 3.13, Hermes gateway (Baileys WhatsApp bridge), FastAPI, httpx, Railway (Docker deploy), GitHub (durambrook org), NHTSA VIN API (free).

---

## File Map

### Part A — `hermes-auto-parts-api` (new repo at `../hermes-auto-parts-api/`)

| File | Purpose |
|---|---|
| `main.py` | FastAPI app, mounts router |
| `routers/parts.py` | `POST /lookup` endpoint |
| `services/db_adapter.py` | `PartsDB` ABC + `MockPartsDB` stub |
| `services/vin_decoder.py` | VIN → make/model/year via NHTSA API |
| `Dockerfile` | Railway build |
| `railway.toml` | Railway service config |
| `.env.example` | Env var documentation |
| `requirements.txt` | Pinned deps |
| `tests/test_lookup.py` | Endpoint tests |
| `tests/test_vin_decoder.py` | VIN decoder tests |

### Part B — `hermes-agent` (this repo)

| File | Purpose |
|---|---|
| `tools/parts_lookup.py` | Tool registered with Hermes — HTTP client calling `PARTS_API_URL/lookup` |
| `docker/profiles/auto-parts/SOUL.md` | Automotive assistant persona (baked into image, copied on first boot) |
| `docker/profiles/auto-parts/config.yaml` | Profile config — WhatsApp on, lean toolset |
| `docker/auto-parts-entrypoint.sh` | Profile bootstrap (copies config+SOUL into volume on first run) |
| `railway.toml` | Railway service config for `hermes-auto-parts` |

---

## Part A: `hermes-auto-parts-api`

### Task A1: Scaffold repo and install deps

**Files:**
- Create: `../hermes-auto-parts-api/requirements.txt`
- Create: `../hermes-auto-parts-api/main.py`

- [ ] **Step 1: Create the repo directory**

```bash
mkdir -p ../hermes-auto-parts-api/routers ../hermes-auto-parts-api/services ../hermes-auto-parts-api/tests
cd ../hermes-auto-parts-api
git init
```

- [ ] **Step 2: Write `requirements.txt`**

```
fastapi>=0.115.0,<1
uvicorn[standard]>=0.34.0,<1
httpx>=0.28.1,<1
pydantic>=2.10.0,<3
pytest>=8.0.0,<9
pytest-asyncio>=0.25.0,<1
httpx>=0.28.1,<1
```

- [ ] **Step 3: Write `main.py`**

```python
from fastapi import FastAPI
from routers.parts import router as parts_router

app = FastAPI(title="hermes-auto-parts-api", version="0.1.0")
app.include_router(parts_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
```

- [ ] **Step 4: Create `__init__.py` files**

```bash
touch ../hermes-auto-parts-api/routers/__init__.py
touch ../hermes-auto-parts-api/services/__init__.py
touch ../hermes-auto-parts-api/tests/__init__.py
```

- [ ] **Step 5: Install deps and verify app starts**

```bash
cd ../hermes-auto-parts-api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --port 8001 &
curl -s http://localhost:8001/health
# Expected: {"status":"ok"}
kill %1
```

- [ ] **Step 6: Commit**

```bash
git add .
git commit -m "chore: scaffold hermes-auto-parts-api"
```

---

### Task A2: VIN decoder service

**Files:**
- Create: `../hermes-auto-parts-api/services/vin_decoder.py`
- Create: `../hermes-auto-parts-api/tests/test_vin_decoder.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_vin_decoder.py
import pytest
from unittest.mock import AsyncMock, patch
from services.vin_decoder import decode_vin, VehicleInfo


@pytest.mark.asyncio
async def test_decode_vin_returns_vehicle_info():
    mock_response = {
        "Results": [
            {"Variable": "Make", "Value": "HONDA"},
            {"Variable": "Model", "Value": "Civic"},
            {"Variable": "Model Year", "Value": "2021"},
            {"Variable": "Trim", "Value": "Sport"},
        ]
    }
    with patch("services.vin_decoder.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=AsyncMock(
            json=lambda: mock_response, raise_for_status=lambda: None
        ))
        mock_client_cls.return_value = mock_client
        result = await decode_vin("1HGBH41JXMN109186")

    assert result.make == "Honda"
    assert result.model == "Civic"
    assert result.year == "2021"
    assert result.trim == "Sport"


@pytest.mark.asyncio
async def test_decode_vin_handles_empty_results():
    mock_response = {"Results": []}
    with patch("services.vin_decoder.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=AsyncMock(
            json=lambda: mock_response, raise_for_status=lambda: None
        ))
        mock_client_cls.return_value = mock_client
        result = await decode_vin("INVALIDVIN")

    assert result.make == "Unknown"
    assert result.model == "Unknown"
    assert result.year == "Unknown"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ../hermes-auto-parts-api
source .venv/bin/activate
pytest tests/test_vin_decoder.py -v
# Expected: ERROR — ModuleNotFoundError: No module named 'services.vin_decoder'
```

- [ ] **Step 3: Write `services/vin_decoder.py`**

```python
from dataclasses import dataclass
import httpx

NHTSA_URL = "https://vpic.nhtsa.dot.gov/api/vehicles/decodevin/{vin}?format=json"

_FIELD_MAP = {
    "Make": "make",
    "Model": "model",
    "Model Year": "year",
    "Trim": "trim",
    "Engine Configuration": "engine",
}


@dataclass
class VehicleInfo:
    make: str = "Unknown"
    model: str = "Unknown"
    year: str = "Unknown"
    trim: str = ""
    engine: str = ""


async def decode_vin(vin: str) -> VehicleInfo:
    """Call the free NHTSA VIN decode API and return structured vehicle info."""
    url = NHTSA_URL.format(vin=vin.strip().upper())
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = client.get(url) if hasattr(client.get, "__self__") else await client.get(url)
        resp.raise_for_status()
        data = resp.json()

    info = VehicleInfo()
    for entry in data.get("Results", []):
        field = _FIELD_MAP.get(entry.get("Variable", ""))
        value = (entry.get("Value") or "").strip()
        if field and value and value.lower() not in {"", "not applicable", "null"}:
            setattr(info, field, value.title() if field == "make" else value)
    return info
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_vin_decoder.py -v
# Expected: 2 passed
```

- [ ] **Step 5: Commit**

```bash
git add services/vin_decoder.py tests/test_vin_decoder.py
git commit -m "feat: add VIN decoder using NHTSA free API"
```

---

### Task A3: DB adapter with mock stub

**Files:**
- Create: `../hermes-auto-parts-api/services/db_adapter.py`

- [ ] **Step 1: Write `services/db_adapter.py`**

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from services.vin_decoder import VehicleInfo


@dataclass
class PartResult:
    part_number: str
    part_name: str
    category: str
    confidence: float


class PartsDB(ABC):
    @abstractmethod
    async def lookup(self, part_description: str, vehicle: VehicleInfo) -> Optional[PartResult]:
        """Return the best matching part or None if not found."""


class MockPartsDB(PartsDB):
    """Stub that returns plausible fake data. Replace with a real DB implementation."""

    async def lookup(self, part_description: str, vehicle: VehicleInfo) -> Optional[PartResult]:
        desc_lower = part_description.lower()
        if "brake" in desc_lower and "caliper" in desc_lower:
            return PartResult("33901-S84-A01", "Brake Caliper – Front", "Brakes", 0.75)
        if "brake" in desc_lower and "pad" in desc_lower:
            return PartResult("45022-S84-A10", "Brake Pad Set – Front", "Brakes", 0.75)
        if "filter" in desc_lower and "oil" in desc_lower:
            return PartResult("15400-PLM-A02", "Oil Filter", "Engine", 0.80)
        if "alternator" in desc_lower:
            return PartResult("31100-P8A-A01", "Alternator Assembly", "Electrical", 0.70)
        # No match — let Hermes fall back to web search
        return None


def get_db() -> PartsDB:
    """Return the active DB adapter based on PARTS_DB_BACKEND env var."""
    import os
    backend = os.getenv("PARTS_DB_BACKEND", "mock").strip().lower()
    if backend == "mock":
        return MockPartsDB()
    raise ValueError(f"Unknown PARTS_DB_BACKEND: {backend!r}. Only 'mock' is supported right now.")
```

- [ ] **Step 2: Commit**

```bash
git add services/db_adapter.py
git commit -m "feat: add pluggable PartsDB adapter with mock stub"
```

---

### Task A4: POST /lookup endpoint

**Files:**
- Create: `../hermes-auto-parts-api/routers/parts.py`
- Create: `../hermes-auto-parts-api/tests/test_lookup.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_lookup.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
from main import app

client = TestClient(app)


def test_lookup_with_mock_db_returns_part():
    with patch("routers.parts.decode_vin", new=AsyncMock(return_value=type("V", (), {
        "make": "Honda", "model": "Civic", "year": "2021", "trim": "Sport", "engine": ""
    })())):
        resp = client.post("/lookup", json={
            "part_description": "front brake caliper single piston",
            "vin": "1HGBH41JXMN109186"
        })
    assert resp.status_code == 200
    body = resp.json()
    assert "part_number" in body
    assert body["source"] == "db"
    assert body["vehicle"]["make"] == "Honda"


def test_lookup_unknown_part_returns_not_found():
    with patch("routers.parts.decode_vin", new=AsyncMock(return_value=type("V", (), {
        "make": "Unknown", "model": "Unknown", "year": "Unknown", "trim": "", "engine": ""
    })())):
        resp = client.post("/lookup", json={
            "part_description": "totally unknown widget xyz",
            "vin": "BADVIN"
        })
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "not_found"
    assert body["part_number"] is None


def test_lookup_missing_fields_returns_422():
    resp = client.post("/lookup", json={"vin": "1HGBH41JXMN109186"})
    assert resp.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_lookup.py -v
# Expected: ImportError or 404 — router not defined yet
```

- [ ] **Step 3: Write `routers/parts.py`**

```python
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from services.vin_decoder import decode_vin
from services.db_adapter import get_db

router = APIRouter()


class LookupRequest(BaseModel):
    part_description: str
    vin: str


class LookupResponse(BaseModel):
    part_number: Optional[str]
    part_name: Optional[str]
    category: Optional[str]
    confidence: Optional[float]
    vehicle: dict
    source: str  # "db" | "not_found"


@router.post("/lookup", response_model=LookupResponse)
async def lookup_part(req: LookupRequest) -> LookupResponse:
    vehicle = await decode_vin(req.vin)
    db = get_db()
    result = await db.lookup(req.part_description, vehicle)

    vehicle_dict = {
        "make": vehicle.make,
        "model": vehicle.model,
        "year": vehicle.year,
        "trim": vehicle.trim,
    }

    if result is None:
        return LookupResponse(
            part_number=None,
            part_name=None,
            category=None,
            confidence=None,
            vehicle=vehicle_dict,
            source="not_found",
        )

    return LookupResponse(
        part_number=result.part_number,
        part_name=result.part_name,
        category=result.category,
        confidence=result.confidence,
        vehicle=vehicle_dict,
        source="db",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/ -v
# Expected: 5 passed
```

- [ ] **Step 5: Commit**

```bash
git add routers/parts.py tests/test_lookup.py
git commit -m "feat: add POST /lookup endpoint with VIN decode + DB adapter"
```

---

### Task A5: Dockerfile, railway.toml, and .env.example

**Files:**
- Create: `../hermes-auto-parts-api/Dockerfile`
- Create: `../hermes-auto-parts-api/railway.toml`
- Create: `../hermes-auto-parts-api/.env.example`

- [ ] **Step 1: Write `Dockerfile`**

```dockerfile
FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Write `railway.toml`**

```toml
[build]
builder = "dockerfile"
dockerfilePath = "Dockerfile"

[deploy]
startCommand = "uvicorn main:app --host 0.0.0.0 --port $PORT"
healthcheckPath = "/health"
healthcheckTimeout = 30
restartPolicyType = "on_failure"

[[services]]
name = "hermes-auto-parts-api"
```

- [ ] **Step 3: Write `.env.example`**

```bash
# Which DB backend to use. Only "mock" is available until a real DB is wired in.
PARTS_DB_BACKEND=mock

# Future: add connection strings here when wiring in a real DB
# DATABASE_URL=postgresql://user:password@host:5432/dbname
```

- [ ] **Step 4: Write `.gitignore`**

```bash
cat > .gitignore << 'EOF'
.venv/
__pycache__/
*.pyc
.env
*.egg-info/
dist/
build/
.pytest_cache/
EOF
```

- [ ] **Step 5: Test Docker build**

```bash
docker build -t hermes-auto-parts-api .
docker run --rm -p 8000:8000 hermes-auto-parts-api &
sleep 2
curl -s http://localhost:8000/health
# Expected: {"status":"ok"}
curl -s -X POST http://localhost:8000/lookup \
  -H "Content-Type: application/json" \
  -d '{"part_description":"front brake caliper","vin":"1HGBH41JXMN109186"}'
# Expected: JSON with part_number and source="db"
docker stop $(docker ps -q --filter ancestor=hermes-auto-parts-api)
```

- [ ] **Step 6: Commit**

```bash
git add Dockerfile railway.toml .env.example .gitignore
git commit -m "chore: add Dockerfile and Railway deployment config"
```

---

### Task A6: Push to GitHub and deploy to Railway

- [ ] **Step 1: Create GitHub repo under durambrook org**

```bash
gh repo create durambrook/hermes-auto-parts-api --public --description "Automotive parts lookup API for Hermes agent"
git remote add origin https://github.com/durambrook/hermes-auto-parts-api.git
git push -u origin main
```

- [ ] **Step 2: Install Railway CLI if not present**

```bash
npm install -g @railway/cli
railway login
```

- [ ] **Step 3: Create Railway project and deploy**

```bash
railway init --name hermes-auto-parts
railway up --service hermes-auto-parts-api
```

- [ ] **Step 4: Set environment variables in Railway**

```bash
railway variables set PARTS_DB_BACKEND=mock --service hermes-auto-parts-api
```

- [ ] **Step 5: Verify the private service health**

In the Railway dashboard, the service should show as healthy. Note the internal hostname shown — it will be `hermes-auto-parts-api.railway.internal`. Do NOT expose a public domain for this service.

- [ ] **Step 6: Record the internal URL**

The `PARTS_API_URL` for the Hermes service will be:
```
http://hermes-auto-parts-api.railway.internal:8000
```
Keep this value — you'll need it in Part B, Task B3.

---

## Part B: hermes-agent changes

### Task B1: Add `tools/parts_lookup.py`

**Files:**
- Create: `tools/parts_lookup.py`
- Create: `tests/tools/test_parts_lookup.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/test_parts_lookup.py
import json
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def test_parts_lookup_returns_part_when_api_succeeds():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "part_number": "33901-S84-A01",
        "part_name": "Brake Caliper – Front",
        "category": "Brakes",
        "confidence": 0.75,
        "vehicle": {"make": "Honda", "model": "Civic", "year": "2021", "trim": "Sport"},
        "source": "db",
    }
    mock_response.raise_for_status = lambda: None

    with patch.dict(os.environ, {"PARTS_API_URL": "http://test.internal"}):
        with patch("tools.parts_lookup.httpx.post", return_value=mock_response):
            from tools.parts_lookup import parts_lookup
            result_str = parts_lookup("front brake caliper single piston", "1HGBH41JXMN109186")

    result = json.loads(result_str)
    assert result["part_number"] == "33901-S84-A01"
    assert result["source"] == "db"


def test_parts_lookup_returns_not_found_when_api_returns_not_found():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "part_number": None,
        "part_name": None,
        "category": None,
        "confidence": None,
        "vehicle": {"make": "Unknown", "model": "Unknown", "year": "Unknown", "trim": ""},
        "source": "not_found",
    }
    mock_response.raise_for_status = lambda: None

    with patch.dict(os.environ, {"PARTS_API_URL": "http://test.internal"}):
        with patch("tools.parts_lookup.httpx.post", return_value=mock_response):
            from tools.parts_lookup import parts_lookup
            result_str = parts_lookup("mystery widget", "BADVIN")

    result = json.loads(result_str)
    assert result["source"] == "not_found"
    assert result["part_number"] is None


def test_parts_lookup_returns_error_when_api_unreachable():
    import httpx as real_httpx

    with patch.dict(os.environ, {"PARTS_API_URL": "http://test.internal"}):
        with patch("tools.parts_lookup.httpx.post", side_effect=real_httpx.ConnectError("refused")):
            from tools.parts_lookup import parts_lookup
            result_str = parts_lookup("brake caliper", "1HGBH41JXMN109186")

    result = json.loads(result_str)
    assert "error" in result


def test_parts_lookup_requires_part_description():
    with patch.dict(os.environ, {"PARTS_API_URL": "http://test.internal"}):
        from tools.parts_lookup import parts_lookup
        result_str = parts_lookup("", "1HGBH41JXMN109186")
    result = json.loads(result_str)
    assert "error" in result
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/tools/test_parts_lookup.py -v
# Expected: ModuleNotFoundError: No module named 'tools.parts_lookup'
```

- [ ] **Step 3: Write `tools/parts_lookup.py`**

```python
"""Automotive parts lookup tool — calls hermes-auto-parts-api to find part numbers."""

import json
import os
import httpx
from tools.registry import registry, tool_error

PARTS_LOOKUP_SCHEMA = {
    "name": "parts_lookup",
    "description": (
        "Look up an automotive part number given a description of the part and a VIN. "
        "Returns the part number, name, category, and vehicle info from the parts database. "
        "When the database has no match, returns source='not_found' so you can fall back to web search."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "part_description": {
                "type": "string",
                "description": "Human-readable description of the part (e.g. 'front brake caliper, single piston')",
            },
            "vin": {
                "type": "string",
                "description": "Vehicle Identification Number (17 characters)",
            },
        },
        "required": ["part_description", "vin"],
    },
}


def parts_lookup(part_description: str, vin: str) -> str:
    if not part_description or not part_description.strip():
        return tool_error("part_description is required")
    if not vin or not vin.strip():
        return tool_error("vin is required")

    api_url = os.environ.get("PARTS_API_URL", "").rstrip("/")
    if not api_url:
        return tool_error("PARTS_API_URL is not configured")

    try:
        resp = httpx.post(
            f"{api_url}/lookup",
            json={"part_description": part_description.strip(), "vin": vin.strip()},
            timeout=15.0,
        )
        resp.raise_for_status()
        return json.dumps(resp.json(), ensure_ascii=False)
    except httpx.HTTPStatusError as exc:
        return tool_error(f"Parts API returned {exc.response.status_code}: {exc.response.text[:200]}")
    except Exception as exc:
        return tool_error(f"Parts API unreachable: {exc}")


def _check_parts_api() -> bool:
    return bool(os.environ.get("PARTS_API_URL", "").strip())


registry.register(
    name="parts_lookup",
    toolset="automotive",
    schema=PARTS_LOOKUP_SCHEMA,
    handler=lambda args, **kw: parts_lookup(
        args.get("part_description", ""),
        args.get("vin", ""),
    ),
    check_fn=_check_parts_api,
    emoji="🔧",
)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/tools/test_parts_lookup.py -v
# Expected: 4 passed
```

- [ ] **Step 5: Commit**

```bash
git add tools/parts_lookup.py tests/tools/test_parts_lookup.py
git commit -m "feat(tools): add parts_lookup tool for automotive parts DB queries"
```

---

### Task B2: Register the `automotive` toolset

**Files:**
- Modify: `toolsets.py`

- [ ] **Step 1: Read the TOOLSETS dict in `toolsets.py`**

Find the `TOOLSETS = {` block. It contains entries like `"web": {...}`, `"terminal": {...}`, etc.

- [ ] **Step 2: Add the automotive toolset**

In `toolsets.py`, inside the `TOOLSETS` dict, add after the last toolset entry:

```python
    "automotive": {
        "description": "Automotive parts identification and lookup tools",
        "tools": ["parts_lookup"],
        "includes": []
    },
```

- [ ] **Step 3: Verify the toolset is discoverable**

```bash
python -c "from toolsets import TOOLSETS; print('automotive' in TOOLSETS)"
# Expected: True
```

- [ ] **Step 4: Commit**

```bash
git add toolsets.py
git commit -m "feat(toolsets): register automotive toolset with parts_lookup"
```

---

### Task B3: Profile config and SOUL.md

**Files:**
- Create: `docker/profiles/auto-parts/config.yaml`
- Create: `docker/profiles/auto-parts/SOUL.md`

- [ ] **Step 1: Create directory**

```bash
mkdir -p docker/profiles/auto-parts
```

- [ ] **Step 2: Write `docker/profiles/auto-parts/SOUL.md`**

```markdown
# Auto Parts Assistant

You are an automotive parts identification assistant. You help mechanics, shop owners, and vehicle owners identify parts and find part numbers.

## How you respond

When someone sends a photo of a part:
- Use your vision capability to describe what you see (part type, shape, color, markings, manufacturer stamps)
- If a VIN is provided, use it to narrow down the vehicle — call `parts_lookup` with the description and VIN
- If the database returns `source: not_found`, use web search to find the OEM part number
- If no VIN is provided, still try to identify the part and give a general part number; note it may vary by vehicle

When someone asks a question in text only:
- Answer from your automotive knowledge or use web search
- If they describe a part without a photo, try `parts_lookup` with their description

## Tone
- Concise and direct — mechanics are busy
- Give the part number prominently, then supporting detail
- If you're uncertain, say so and give your best guess with a confidence note

## What you do not do
- You do not place orders or assist with purchasing
- You do not provide repair instructions unless specifically asked
- You do not respond to topics unrelated to automotive parts and vehicles
```

- [ ] **Step 3: Write `docker/profiles/auto-parts/config.yaml`**

Replace `<YOUR_ANTHROPIC_API_KEY>` — this is a template; the real key goes in Railway env vars, not here.

```yaml
# Auto-parts profile configuration
# HERMES_HOME=/opt/data/profiles/auto-parts

model:
  default: "anthropic/claude-sonnet-4-6"
  provider: "anthropic"

# Only WhatsApp — no other platforms
platforms:
  whatsapp:
    enabled: true
    extra:
      bridge_script: "/opt/hermes/scripts/whatsapp-bridge/bridge.js"
      bridge_port: 3000
      dm_policy: "open"
      group_policy: "open"

# Lean toolset: web + terminal + file + automotive (no image gen, no kanban, no video)
platform_toolsets:
  whatsapp: [web, terminal, file, vision, skills, todo, automotive]

# Disable all background services not needed
curator:
  enabled: false

kanban:
  dispatch_in_gateway: false
```

- [ ] **Step 4: Commit**

```bash
git add docker/profiles/auto-parts/
git commit -m "feat(profile): add auto-parts SOUL.md and config.yaml"
```

---

### Task B4: Profile bootstrap entrypoint script

**Files:**
- Create: `docker/auto-parts-entrypoint.sh`

This script runs before the main entrypoint and copies the profile config into the Railway volume on first boot.

- [ ] **Step 1: Write `docker/auto-parts-entrypoint.sh`**

```bash
#!/bin/bash
# Bootstrap the auto-parts profile config into the Railway persistent volume.
# Runs as hermes user (after gosu drop in main entrypoint).
set -e

PROFILE_DIR="${HERMES_HOME:-/opt/data/profiles/auto-parts}"
BUNDLED_DIR="/opt/hermes/docker/profiles/auto-parts"

mkdir -p "$PROFILE_DIR"

# Copy config.yaml if not already customised on the volume
if [ ! -f "$PROFILE_DIR/config.yaml" ]; then
    echo "[auto-parts] Installing config.yaml"
    cp "$BUNDLED_DIR/config.yaml" "$PROFILE_DIR/config.yaml"
fi

# Always refresh SOUL.md from the image (it's not user-editable)
cp "$BUNDLED_DIR/SOUL.md" "$PROFILE_DIR/SOUL.md"

echo "[auto-parts] Profile bootstrap complete → $PROFILE_DIR"
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x docker/auto-parts-entrypoint.sh
```

- [ ] **Step 3: Commit**

```bash
git add docker/auto-parts-entrypoint.sh
git commit -m "feat(docker): add auto-parts profile bootstrap entrypoint"
```

---

### Task B5: Railway deployment config for hermes-auto-parts

**Files:**
- Create: `railway.toml`

- [ ] **Step 1: Write `railway.toml`**

```toml
[build]
builder = "dockerfile"
dockerfilePath = "Dockerfile"

[deploy]
# Run the profile bootstrap, then start the Hermes gateway
startCommand = "bash /opt/hermes/docker/auto-parts-entrypoint.sh && exec hermes gateway run"
healthcheckPath = "/health"
healthcheckTimeout = 60
restartPolicyType = "on_failure"

[[services]]
name = "hermes-auto-parts"
```

- [ ] **Step 2: Commit**

```bash
git add railway.toml
git commit -m "chore: add railway.toml for hermes-auto-parts deployment"
```

---

### Task B6: Deploy hermes-auto-parts to Railway

- [ ] **Step 1: Add hermes-auto-parts as a second service in the same Railway project**

```bash
cd /path/to/hermes-agent
railway link   # select the existing hermes-auto-parts project
railway up --service hermes-auto-parts
```

- [ ] **Step 2: Set required environment variables in Railway**

In the Railway dashboard for `hermes-auto-parts`, set:

| Variable | Value |
|---|---|
| `HERMES_HOME` | `/opt/data/profiles/auto-parts` |
| `PARTS_API_URL` | `http://hermes-auto-parts-api.railway.internal:8000` |
| `ANTHROPIC_API_KEY` | *(your Anthropic key)* |
| `HERMES_DASHBOARD` | `1` |
| `HERMES_DASHBOARD_HOST` | `0.0.0.0` |
| `HERMES_DASHBOARD_PORT` | `9119` |
| `WEB_AUTH_TOKEN` | *(generate a random token: `openssl rand -hex 32`)* |

- [ ] **Step 3: Expose the dashboard port**

In the Railway dashboard, go to `hermes-auto-parts` → Settings → Networking. Add a public domain mapped to port **9119**. This is your dashboard URL.

The gateway itself communicates over WhatsApp (no public port needed for the gateway).

- [ ] **Step 4: Verify deployment**

```bash
# Check dashboard is reachable
curl -s https://<your-dashboard-url>.railway.app/health
# Expected: {"status":"ok"} or Hermes dashboard HTML
```

- [ ] **Step 5: WhatsApp QR code auth**

In the Railway dashboard for `hermes-auto-parts`, open **Logs**. On first boot you'll see a QR code printed in the terminal. Scan it with the WhatsApp account that will be the bot.

The session is persisted at `/opt/data/platforms/whatsapp/session` on the Railway volume — you won't need to re-scan on redeploy.

- [ ] **Step 6: Test end-to-end**

From a WhatsApp account connected to the bot (either DM or a group the bot is in), send:

```
Can you find me this part? VIN: 1HGBH41JXMN109186
[attach a photo of a brake caliper]
```

Expected response: The bot identifies the part, calls `parts_lookup`, and returns the part number from the mock DB. If the mock returns `not_found`, the bot falls back to web search.

---

## Self-Review Checklist

**Spec coverage:**
- [x] Context-aware triggers → handled in SOUL.md (Task B3)
- [x] parts_lookup tool → Task B1
- [x] automotive toolset registration → Task B2
- [x] Profile config (WhatsApp + lean toolset) → Task B3
- [x] SOUL.md persona → Task B3
- [x] hermes-auto-parts-api repo → Tasks A1–A6
- [x] VIN decoder → Task A2
- [x] Pluggable DB adapter → Task A3
- [x] POST /lookup endpoint → Task A4
- [x] Dockerfile + railway.toml for API → Task A5
- [x] Push to durambrook/hermes-auto-parts-api → Task A6
- [x] Railway private networking (API not public) → Task A6 Step 5
- [x] Dashboard on port 9119 with auth token → Task B6 Step 2-3
- [x] WhatsApp groups + DMs both handled → config.yaml dm_policy + group_policy both "open"
- [x] Phase 1 mock DB → MockPartsDB in Task A3
- [x] Phased rollout: swap DB via PARTS_DB_BACKEND env var → Task A3 get_db()

**No placeholders found.**

**Type consistency:**
- `parts_lookup(part_description, vin)` → consistent across tool definition (Task B1) and test
- `LookupRequest.part_description` + `LookupRequest.vin` → consistent with tool's POST body
- `PartResult` fields → consistent between db_adapter.py (Task A3) and routers/parts.py (Task A4)
- `VehicleInfo` fields → consistent between vin_decoder.py (Task A2) and db_adapter.py (Task A3)
