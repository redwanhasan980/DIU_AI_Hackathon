"""Separate durable-event consumer and simulated HTTP connector process."""

from __future__ import annotations

import logging
import os
import signal
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from floatwise.api.main import load_env_file
from floatwise.api.persistence import Conflict, encode
from floatwise.api.store import Store
from floatwise.config import get_config
from floatwise.integration.service import now

log = logging.getLogger("floatwise.integration")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def post_event(event: dict) -> None:
    token = os.environ.get("FLOATWISE_INTEGRATION_TOKEN", "")
    if not token:
        raise Conflict("Run python run.py integration-setup to configure the connector credential")
    base = os.environ.get("FLOATWISE_INTEGRATION_API", "http://127.0.0.1:8000").rstrip("/")
    address = urlsplit(base)
    if (
        address.scheme not in {"http", "https"}
        or address.hostname not in {"127.0.0.1", "localhost", "::1"}
        or address.username
        or address.password
        or address.query
        or address.fragment
    ):
        raise Conflict("The simulated connector requires an explicitly configured loopback API URL")
    # Token travels only to the explicitly configured local API, never an external service.
    request = urllib.request.Request(
        base + "/api/v1/integration/events",
        data=encode(event).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + token},
        method="POST",
    )
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=5) as response:
        response.read()


def connector_step(integration) -> None:
    with integration.db.connect() as db:
        state = integration.control(db, "connector", {"status": "idle"})
    if state["status"] != "running":
        return
    event = integration.connector_event(state)
    try:
        post_event(event.model_dump(mode="json"))
        error = None
    except (urllib.error.URLError, TimeoutError, Conflict) as exc:
        error = str(exc)
    with integration.db.transaction() as db:
        current = integration.control(db, "connector", {})
        if (
            current.get("run_id") != state["run_id"]
            or current.get("cursor") != state["cursor"]
            or current.get("status") != "running"
        ):
            return  # Pause/replay wins; retransmission uses the same event identity.
        if error:
            current["error"] = (
                "Connector could not reach the authenticated local API; check worker/API configuration."
            )
            # Transport outages keep the cursor for retry after recovery.
        else:
            current.update(cursor=current["cursor"] + 1, error=None)
            if current["cursor"] >= current["total"]:
                current["status"] = "completed"
        integration.set_control(db, "connector", current)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    load_env_file()
    store = Store(get_config())
    integration = store.integration
    log.info("Local integration worker started; consuming durable simulated events")
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    next_connector = 0.0
    while not stop.is_set():
        with store.operations.transaction() as db:
            integration.set_control(db, "worker_heartbeat", now())
        try:
            if time.monotonic() >= next_connector:
                connector_step(integration)
                next_connector = time.monotonic() + integration.cfg.connector_interval_seconds
            processed = integration.process_one()
            if not processed:
                integration.refresh_dirty()
        except Conflict as exc:
            log.info("Waiting for consistent operational inputs: %s", exc)
        except Exception:
            log.exception("Worker iteration failed; durable queue retained")
        stop.wait(integration.cfg.poll_seconds)
    with store.operations.transaction() as db:
        integration.set_control(db, "worker_heartbeat", None)


if __name__ == "__main__":
    main()
