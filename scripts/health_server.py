"""
Health check HTTP endpoint for the simulator.

Runs a lightweight HTTP server on port 8766 that returns
simulator status as JSON. Used by Docker health checks and
monitoring tools.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone

from aiohttp import web

logger = logging.getLogger(__name__)


class HealthServer:
    """Simple HTTP health check server."""

    def __init__(self, port: int = 8766):
        self._port = port
        self._app = web.Application()
        self._runner = None
        self._start_time = time.time()

        # Mutable state set by simulator
        self.scenario_name = ""
        self.sim_time = ""
        self.speed = 1.0
        self.entity_count = 0
        self.events_fired = 0
        self.events_total = 0
        self.transports = {}

        self._app.router.add_get("/health", self._handle_health)

    async def start(self):
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", self._port)
        await site.start()
        logger.info(f"Health server on http://0.0.0.0:{self._port}/health")

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()

    async def _handle_health(self, request):
        uptime = int(time.time() - self._start_time)
        data = {
            "status": "running",
            "scenario": self.scenario_name,
            "sim_time": self.sim_time,
            "speed": self.speed,
            "entities": self.entity_count,
            "events_fired": self.events_fired,
            "events_total": self.events_total,
            "uptime_seconds": uptime,
            "transports": self.transports,
        }
        return web.json_response(data)
