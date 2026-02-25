"""
REST API transport adapter for Edge C2.

Reads an OpenAPI 3.0 spec to determine endpoints, maps entity updates
to API payloads, handles authentication and retries. Supports both
individual entity updates (high-frequency) and batch mode (efficient).

Design principle: The spec is the contract. When the real Edge C2 API
spec arrives, swap the YAML and everything regenerates.
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, Optional

import yaml

from simulator.core.entity import Entity
from simulator.transport.base import TransportAdapter

logger = logging.getLogger(__name__)

# Optional aiohttp import — only required when not in dry-run mode
try:
    import aiohttp
except ImportError:
    aiohttp = None  # type: ignore[assignment]


class BatchBuffer:
    """Accumulates payloads and flushes periodically."""

    def __init__(self, interval_s: float, flush_callback):
        self.buffer: list[dict] = []
        self.interval = interval_s
        self.flush_callback = flush_callback
        self._task: Optional[asyncio.Task] = None

    def add(self, payload: dict):
        self.buffer.append(payload)

    async def start(self):
        self._task = asyncio.create_task(self._run())

    async def _run(self):
        while True:
            await asyncio.sleep(self.interval)
            if self.buffer:
                batch = self.buffer.copy()
                self.buffer.clear()
                try:
                    await self.flush_callback(batch)
                except Exception as e:
                    logger.warning(f"Batch flush error: {e}")

    async def flush_now(self):
        if self.buffer:
            batch = self.buffer.copy()
            self.buffer.clear()
            await self.flush_callback(batch)

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass


class RESTAdapter(TransportAdapter):
    """
    Spec-driven REST API transport adapter.

    Reads an OpenAPI 3.0 spec, maps entity updates to HTTP API calls.
    Supports batch mode, dry run, and exponential backoff retries.
    """

    def __init__(
        self,
        api_spec_path: str = "config/edge_c2_api.yaml",
        base_url: str = "http://localhost:9000",
        api_key: Optional[str] = None,
        bearer_token: Optional[str] = None,
        batch_mode: bool = True,
        batch_interval_s: float = 1.0,
        dry_run: bool = False,
        max_retries: int = 3,
        field_mapping_path: Optional[str] = None,
    ):
        self._spec_path = api_spec_path
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._bearer_token = bearer_token
        self._batch_mode = batch_mode
        self._batch_interval_s = batch_interval_s
        self._dry_run = dry_run
        self._max_retries = max_retries
        self._field_mapping_path = field_mapping_path

        self._spec: dict = {}
        self._endpoints: dict[str, tuple[str, str]] = {}
        self._base_path: str = ""
        self._session: Any = None
        self._batch_buffer: Optional[BatchBuffer] = None
        self._field_mapping: dict[str, str] = {}
        self._dry_run_log: list[dict] = []
        self._created_entities: set[str] = set()

    @property
    def name(self) -> str:
        return "rest"

    async def connect(self) -> None:
        """Load spec, create HTTP session, start batch buffer."""
        self._load_spec()
        self._build_endpoint_map()
        self._load_field_mapping()

        if not self._dry_run:
            if aiohttp is None:
                raise RuntimeError("aiohttp required for REST adapter (install with: pip install aiohttp)")
            headers = self._build_auth_headers()
            headers["Content-Type"] = "application/json"
            self._session = aiohttp.ClientSession(
                base_url=self._base_url,
                headers=headers,
            )

        if self._batch_mode:
            self._batch_buffer = BatchBuffer(
                self._batch_interval_s,
                self._flush_batch,
            )
            await self._batch_buffer.start()

        logger.info(
            f"REST adapter initialized: {self._base_url} "
            f"(dry_run={self._dry_run}, batch={self._batch_mode})"
        )

    async def disconnect(self) -> None:
        """Close HTTP session and flush remaining batch."""
        if self._batch_buffer:
            await self._batch_buffer.flush_now()
            await self._batch_buffer.stop()
        if self._session:
            await self._session.close()
        logger.info(f"REST adapter disconnected (dry_run log: {len(self._dry_run_log)} entries)")

    async def push_entity_update(self, entity: Entity) -> None:
        """Push a single entity position update."""
        entity_dict = entity.to_dict()
        entity_id = entity_dict["entity_id"]

        # Create entity if first time seen
        if entity_id not in self._created_entities:
            await self._push_entity_create(entity_dict)
            self._created_entities.add(entity_id)

        # Position update
        payload = self._entity_to_position_payload(entity_dict)

        if self._batch_mode and self._batch_buffer:
            self._batch_buffer.add({"entity_id": entity_id, **payload})
        else:
            endpoint = self._endpoints.get("position_update")
            if endpoint:
                method, path_template = endpoint
                path = path_template.replace("{entity_id}", entity_id)
                await self._send(method, path, payload)

    async def push_bulk_update(self, entities: list[Entity]) -> None:
        """Push multiple entity updates."""
        for entity in entities:
            await self.push_entity_update(entity)

    async def push_event(self, event: dict) -> None:
        """Push a scenario event."""
        payload = self._event_to_payload(event)
        endpoint = self._endpoints.get("event_create")
        if endpoint:
            method, path = endpoint
            await self._send(method, path, payload)
        else:
            logger.debug("No event endpoint found in spec")

    async def push_ais_signal(self, nmea_sentences: list[str], timestamp: str = "") -> None:
        """Push raw AIS NMEA sentences."""
        endpoint = self._endpoints.get("ais_signal")
        if not endpoint:
            return
        payload = {
            "sentences": [
                {"nmea": s, "timestamp": timestamp, "source": "simulator"}
                for s in nmea_sentences
            ]
        }
        method, path = endpoint
        await self._send(method, path, payload)

    async def push_adsb_signal(self, messages: list[dict]) -> None:
        """Push ADS-B SBS messages."""
        endpoint = self._endpoints.get("adsb_signal")
        if not endpoint:
            return
        payload = {"messages": messages}
        method, path = endpoint
        await self._send(method, path, payload)

    async def health_check(self) -> bool:
        """Check if Edge C2 API is reachable."""
        endpoint = self._endpoints.get("health")
        if not endpoint:
            return False
        if self._dry_run:
            return True
        method, path = endpoint
        try:
            async with self._session.request(method, path) as resp:
                return resp.status == 200
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return False

    # === SPEC PARSING ===

    def _load_spec(self):
        """Load and parse OpenAPI spec."""
        spec_path = Path(self._spec_path)
        if not spec_path.exists():
            logger.warning(f"API spec not found: {self._spec_path}")
            return
        with open(spec_path) as f:
            self._spec = yaml.safe_load(f)

        # Extract base path from servers
        servers = self._spec.get("servers", [])
        if servers:
            url = servers[0].get("url", "")
            # Extract path portion (e.g., "/api/v1" from "http://localhost:8080/api/v1")
            if "://" in url:
                parts = url.split("://", 1)[1]
                idx = parts.find("/")
                self._base_path = parts[idx:] if idx >= 0 else ""
            else:
                self._base_path = url

        logger.info(f"Loaded API spec: {self._spec.get('info', {}).get('title', 'Unknown')}")

    def _build_endpoint_map(self):
        """Scan spec paths for known operation patterns."""
        self._endpoints = {}
        for path, methods in self._spec.get("paths", {}).items():
            full_path = self._base_path + path
            for method, operation in methods.items():
                if not isinstance(operation, dict):
                    continue
                op_id = operation.get("operationId", "")

                # Match by operationId first, then path patterns
                if op_id == "updateEntityPosition" or ("position" in path and method == "post" and "{entity_id}" in path):
                    self._endpoints["position_update"] = (method, full_path)
                elif op_id == "bulkPositionUpdate" or ("bulk" in path and method == "post"):
                    self._endpoints["bulk_update"] = (method, full_path)
                elif op_id == "createEntity" or (path.endswith("/entities") and method == "post"):
                    self._endpoints["entity_create"] = (method, full_path)
                elif op_id == "updateEntity" or ("{entity_id}" in path and method == "put" and "position" not in path):
                    self._endpoints["entity_update"] = (method, full_path)
                elif op_id == "createEvent" or (path.endswith("/events") and method == "post"):
                    self._endpoints["event_create"] = (method, full_path)
                elif op_id == "pushAisSignal" or ("signals" in path and "ais" in path and method == "post"):
                    self._endpoints["ais_signal"] = (method, full_path)
                elif op_id == "pushAdsbSignal" or ("signals" in path and "adsb" in path and method == "post"):
                    self._endpoints["adsb_signal"] = (method, full_path)
                elif op_id == "healthCheck" or ("health" in path and method == "get"):
                    self._endpoints["health"] = (method, full_path)

        logger.info(f"Mapped endpoints: {list(self._endpoints.keys())}")

    def _load_field_mapping(self):
        """Load optional field mapping overrides."""
        if not self._field_mapping_path:
            return
        path = Path(self._field_mapping_path)
        if path.exists():
            with open(path) as f:
                data = yaml.safe_load(f)
            self._field_mapping = data.get("entity_to_api", {})
            logger.info(f"Loaded {len(self._field_mapping)} field mappings")

    # === PAYLOAD GENERATION ===

    def _entity_to_position_payload(self, entity: dict) -> dict:
        """Generate PositionUpdate payload from entity dict."""
        pos = entity.get("position", {})
        payload = {
            "position": {
                "latitude": pos.get("latitude", 0),
                "longitude": pos.get("longitude", 0),
                "altitude_m": pos.get("altitude_m", 0),
            },
            "heading_deg": entity.get("heading_deg", 0),
            "speed_knots": entity.get("speed_knots", 0),
            "course_deg": entity.get("course_deg", 0),
            "timestamp": entity.get("timestamp", ""),
            "status": entity.get("status", "ACTIVE"),
        }
        return self._apply_field_mapping(payload)

    def _entity_to_full_payload(self, entity: dict) -> dict:
        """Generate full EntityCreate payload."""
        pos = entity.get("position", {})
        payload = {
            "entity_id": entity.get("entity_id"),
            "entity_type": entity.get("entity_type"),
            "domain": entity.get("domain"),
            "agency": entity.get("agency"),
            "callsign": entity.get("callsign", ""),
            "position": {
                "latitude": pos.get("latitude", 0),
                "longitude": pos.get("longitude", 0),
                "altitude_m": pos.get("altitude_m", 0),
            },
            "heading_deg": entity.get("heading_deg", 0),
            "speed_knots": entity.get("speed_knots", 0),
            "status": entity.get("status", "ACTIVE"),
            "sidc": entity.get("sidc", ""),
            "metadata": entity.get("metadata", {}),
        }
        return self._apply_field_mapping(payload)

    def _event_to_payload(self, event: dict) -> dict:
        """Map scenario event to API Event schema."""
        payload = {
            "event_type": event.get("event_type", "ALERT"),
            "description": event.get("description", ""),
            "timestamp": event.get("time", event.get("timestamp", "")),
            "severity": event.get("severity", "INFO"),
        }
        if "position" in event:
            payload["position"] = event["position"]
        if "target" in event:
            payload["target_entity_id"] = event["target"]
        if "alert_agencies" in event:
            payload["agencies_involved"] = event["alert_agencies"]
        return payload

    def _apply_field_mapping(self, payload: dict) -> dict:
        """Apply field name overrides from field_mapping.yaml."""
        if not self._field_mapping:
            return payload
        result = {}
        for key, value in payload.items():
            mapped_key = self._field_mapping.get(key, key)
            if isinstance(value, dict):
                result[mapped_key] = {}
                for k2, v2 in value.items():
                    full_key = f"{key}.{k2}"
                    mk = self._field_mapping.get(full_key, k2)
                    result[mapped_key][mk] = v2
            else:
                result[mapped_key] = value
        return result

    # === HTTP ===

    async def _push_entity_create(self, entity_dict: dict) -> None:
        """Create entity in Edge C2 (first time only)."""
        endpoint = self._endpoints.get("entity_create")
        if not endpoint:
            return
        payload = self._entity_to_full_payload(entity_dict)
        method, path = endpoint
        await self._send(method, path, payload)

    async def _flush_batch(self, items: list[dict]) -> None:
        """Flush accumulated batch items."""
        endpoint = self._endpoints.get("bulk_update")
        if endpoint:
            method, path = endpoint
            payload = {"updates": items}
            await self._send(method, path, payload)
        else:
            # Fall back to individual position updates
            for item in items:
                entity_id = item.pop("entity_id", "")
                endpoint = self._endpoints.get("position_update")
                if endpoint:
                    method, path_template = endpoint
                    path = path_template.replace("{entity_id}", entity_id)
                    await self._send(method, path, item)

    async def _send(self, method: str, path: str, payload: dict) -> bool:
        """Send HTTP request with retry logic."""
        if self._dry_run:
            entry = {
                "method": method.upper(),
                "path": path,
                "payload": payload,
                "timestamp": time.time(),
            }
            self._dry_run_log.append(entry)
            logger.debug(f"[DRY RUN] {method.upper()} {path}: {json.dumps(payload)[:200]}")
            return True

        return await self._send_with_retry(method, path, payload)

    async def _send_with_retry(self, method: str, path: str, payload: dict) -> bool:
        """Send with exponential backoff retry on server errors."""
        for attempt in range(self._max_retries):
            try:
                async with self._session.request(method, path, json=payload) as resp:
                    if resp.status < 400:
                        return True
                    if resp.status in (429, 500, 502, 503, 504):
                        wait = (2 ** attempt)
                        logger.warning(
                            f"REST {method.upper()} {path} returned {resp.status}, "
                            f"retrying in {wait}s (attempt {attempt + 1}/{self._max_retries})"
                        )
                        await asyncio.sleep(wait)
                        continue
                    else:
                        body = await resp.text()
                        logger.warning(f"REST {method.upper()} {path} returned {resp.status}: {body[:200]}")
                        return False
            except Exception as e:
                wait = (2 ** attempt)
                logger.warning(f"REST request error: {e}, retrying in {wait}s")
                await asyncio.sleep(wait)

        logger.error(f"REST {method.upper()} {path} failed after {self._max_retries} retries")
        return False

    def _build_auth_headers(self) -> dict:
        """Build authentication headers from config."""
        headers = {}
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        if self._bearer_token:
            headers["Authorization"] = f"Bearer {self._bearer_token}"
        return headers

    # === ACCESSORS ===

    @property
    def endpoints(self) -> dict:
        return self._endpoints

    @property
    def dry_run_log(self) -> list[dict]:
        return self._dry_run_log
