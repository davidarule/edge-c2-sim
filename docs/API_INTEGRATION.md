# Edge C2 API Integration Guide

## Overview

The Edge C2 Simulator connects to the real Edge C2 system via its REST API.
The REST adapter is **spec-driven** — it reads an OpenAPI 3.0 specification
to determine endpoints, payload structures, and authentication.

When the real Edge C2 API spec arrives, swapping the YAML file should be the
only change needed.

## Quick Start

### 1. Dry Run (no Edge C2 needed)

```bash
edge-c2-sim --scenario config/scenarios/demo_combined.yaml \
            --transport ws,console,rest \
            --rest-dry-run
```

This generates and logs all API payloads without making HTTP requests.
Check `logs/` for the dry run output.

### 2. Connect to Edge C2

```bash
edge-c2-sim --scenario config/scenarios/demo_combined.yaml \
            --transport ws,console,rest \
            --rest-url http://edge-c2-api:9000 \
            --rest-api-key your-api-key
```

## Swapping the API Specification

When the real Edge C2 API spec arrives:

1. Save the new spec as `config/edge_c2_api.yaml`
2. Run the simulator with REST adapter (dry run first):
   ```bash
   edge-c2-sim --scenario ... --transport ws,rest --rest-dry-run
   ```
3. Check logs for any mapping warnings
4. If field names differ, create `config/field_mapping.yaml`
5. Remove `--rest-dry-run` to go live

## Field Mapping Override

If the real API uses different field names than the simulator's internal model,
create `config/field_mapping.yaml`:

```yaml
entity_to_api:
  position.latitude: lat
  position.longitude: lng
  heading_deg: bearing
  speed_knots: speed
  timestamp: time
```

The REST adapter will apply these mappings before sending payloads.

## API Endpoints Used

The adapter auto-discovers these endpoints from the OpenAPI spec:

| Function | Expected Pattern | Stub Path |
|----------|-----------------|-----------|
| Create entity | `POST /entities` | `/api/v1/entities` |
| Update entity | `PUT /entities/{id}` | `/api/v1/entities/{entity_id}` |
| Position update | `POST /entities/{id}/position` | `/api/v1/entities/{entity_id}/position` |
| Bulk update | `POST /entities/bulk` | `/api/v1/entities/bulk` |
| Push event | `POST /events` | `/api/v1/events` |
| AIS signal | `POST /signals/ais` | `/api/v1/signals/ais` |
| ADS-B signal | `POST /signals/adsb` | `/api/v1/signals/adsb` |
| Health check | `GET /health` | `/api/v1/health` |

## Authentication

The adapter supports two auth methods (auto-detected from spec):

- **API Key**: `X-API-Key` header — set via `--rest-api-key` or `EDGE_C2_API_KEY` env var
- **Bearer Token**: `Authorization: Bearer <token>` — set via `--rest-bearer-token`

## Batch Mode

By default, position updates are batched and sent every 1 second via the
bulk endpoint. This reduces HTTP overhead when tracking 50+ entities.

Disable with `--rest-no-batch` for individual position updates.

## Retry Logic

Server errors (429, 500, 502, 503, 504) are retried with exponential backoff:
- Attempt 1: immediate
- Attempt 2: after 1s
- Attempt 3: after 2s
- Attempt 4: after 4s

Client errors (400, 401, 403, 404) are not retried.

## TAK Integration

For ATAK/WinTAK integration via Cursor on Target (CoT):

```bash
# Start with TAK server
docker-compose --profile tak up

# Enable CoT adapter
edge-c2-sim --scenario ... --transport ws,cot \
            --cot-host freetakserver --cot-port 8087
```

The CoT adapter converts entities to CoT XML and sends them via TCP to
FreeTAKServer, which relays to connected ATAK/WinTAK clients.
