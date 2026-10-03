"""Offline latency persistence, outcome coverage and old-database migration checks."""
import json
from pathlib import Path
import sqlite3
import tempfile
from eval_support import Fixture, MESSAGES, ROOT
from run_eval import evaluate
from src.services.db import Database, SCHEMA


def main():
    # Old rows keep NULL; re-opening migration is idempotent.
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "old.db"
        connection = sqlite3.connect(path)
        connection.executescript(SCHEMA.replace("    latency_ms REAL,\n", ""))
        connection.execute("INSERT INTO audit (key_prefix, model, outcome, request_text) VALUES ('', 'fake', 'completed', 'old')")
        connection.commit(); connection.close()
        for _ in range(2):
            db = Database(path)
            assert db.read("SELECT latency_ms FROM audit")[0]["latency_ms"] is None
            db._conn.close()
    f = Fixture(requests_per_minute=2)
    try:
        first = f.call(key="retry")
        replay = f.call(key="retry")
        assert first.latency_ms is not None and first.latency_ms >= 0
        assert replay.latency_ms is not None and replay.latency_ms >= 0
        f.call()
        try:
            f.call()
        except Exception:
            pass
        try:
            f.handler.handle("bad-key", MESSAGES, "fake")
        except Exception:
            pass
        from src.app import _summary_json, _event_json, create_app
        payload = _summary_json(first)
        assert payload["handler_latency_ms"] == first.latency_ms
        assert payload["cost_usd"] == "0.015"
        app = create_app(f.db, f.llm, admin_token="offline-test")
        def endpoint(path):
            return next(r.endpoint for r in app.routes if getattr(r, "path", None) == path)
        from src.services.plans import PlanStore
        PlanStore(f.db).create(f.plan)
        usage = endpoint("/v1/usage")(authorization="Bearer " + f.keys["alpha"])
        assert all(e["handler_latency_ms"] is not None for e in usage["events"])
        events = f.handler.audit.events
        assert _event_json(events[0])["handler_latency_ms"] == events[0].latency_ms
        assert {e.outcome for e in events} == {"completed", "idempotent_replay", "rate_limited", "unauthenticated"}
        assert all(e.latency_ms is not None and e.latency_ms >= 0 for e in events)
    finally:
        f.close()
    # Instrument only the test's local AuditLog method to observe all remaining outcomes.
    from src.services.audit import AuditLog
    original = AuditLog.record
    observed = {}
    def record(self, **kwargs):
        assert kwargs["latency_ms"] is not None and kwargs["latency_ms"] >= 0
        observed[kwargs["outcome"]] = True
        return original(self, **kwargs)
    AuditLog.record = record
    try:
        for case in ("rate_handler", "input_moderation", "output_moderation", "provider_error_release", "invalid_auth", "token_boundary"):
            evaluate({"id": case})
    finally:
        AuditLog.record = original
    assert {"completed", "rate_limited", "injection", "moderated", "error", "unauthenticated", "budget_exceeded"} <= observed.keys()
    print("PASS nullable migration, historical NULL, replay, authentication, rate limit, budget, moderation, provider errors and timing reset")

if __name__ == "__main__":
    main()
