"""Run the shared conformance fixture against the Python implementation.

The fixture is the acceptance gate for every language binding, so this module
loads `conformance/envelope-cases.json` from the repo root rather than restating
the cases. A case added there must pass here without editing this file.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from rtech_obs import ConfigError, init_observability, load_config, logger


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _fixture() -> dict[str, Any]:
    text = (_repo_root() / "conformance/envelope-cases.json").read_text(
        encoding="utf-8"
    )
    return json.loads(text)


FIXTURE = _fixture()
CASES = {case["name"]: case for case in FIXTURE["cases"]}


def _emit(case: dict[str, Any], tmp_path: Path) -> list[dict[str, Any]]:
    """Run one case through the real file sink and return the envelopes produced.

    Reads back the configured log file rather than attaching a bespoke sink: the
    file path is the sink the contract actually specifies, so exercising it keeps
    the test honest about what a deployed service writes.
    """
    destination = tmp_path / "out.jsonl"
    config = dict(case.get("config", {}))
    config["LOG_FILE"] = str(destination)
    config.setdefault("LOG_LEVEL", "debug")

    init_observability(env=config, stdout=False)

    call = case.get("call")
    if call:
        payload = {
            key: value for key, value in call.items() if key not in {"level", "message"}
        }
        logger.log(str(call["level"]).upper(), str(call["message"]), **payload)

    # enqueue=True writes on a background thread; complete() flushes it.
    logger.complete()
    logger.remove()

    if not destination.exists():
        return []
    envelopes: list[dict[str, Any]] = []
    for line in destination.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        envelopes.append(json.loads(line))
    return envelopes


def test_fixture_matches_contract_version() -> None:
    """The fixture and the package implement the same contract revision."""
    assert FIXTURE["contract_version"] == "1.0.0"


def test_missing_service_name_fails_closed() -> None:
    """Contract 5.1: an unattributable record cannot be correlated."""
    assert "missing-service-name-fails-closed" in CASES
    with pytest.raises(ConfigError):
        load_config(env={})


@pytest.mark.parametrize("bad_level", ["chatty", "warn", "err", "crit"])
def test_invalid_or_abbreviated_level_fails_closed(bad_level: str) -> None:
    """Contract 1.3/5.1: Loki matches level literally, so abbreviations are errors."""
    with pytest.raises(ConfigError):
        load_config(env={"SERVICE_NAME": "widget", "LOG_LEVEL": bad_level})


def test_default_log_file_follows_share_convention() -> None:
    """Contract 6: a per-service default is what makes collection zero-config."""
    config = load_config(env={"SERVICE_NAME": "widget"})
    pattern = CASES["default-log-file-follows-share-convention"]["match"][
        "resolved_config_pattern"
    ]["LOG_FILE"]
    assert config.log_file is not None
    assert re.match(pattern, str(config.log_file)), config.log_file


def test_minimal_record_stamps_required_fields(tmp_path: Path) -> None:
    """Contract 1.1: all five required fields are present on a bare message."""
    envelopes = _emit(CASES["minimal-info-record"], tmp_path)
    record = next(item for item in envelopes if item["message"] == "started")

    assert record["level"] == "info"
    assert record["service"] == "widget"
    assert re.match(FIXTURE["patterns"]["timestamp"], record["timestamp"])
    assert re.match(FIXTURE["patterns"]["host"], record["host"])
    for absent in CASES["minimal-info-record"]["match"]["absent"]:
        assert absent not in record


def test_record_is_single_line_json(tmp_path: Path) -> None:
    """Contract 1: a multi-line record breaks line-oriented collection."""
    envelopes = _emit(CASES["single-line-json"], tmp_path)
    assert envelopes
    rendered = json.dumps(envelopes[0], separators=(",", ":"))
    assert "\n" not in rendered


def test_caller_cannot_override_service(tmp_path: Path) -> None:
    """Contract 1.3: a caller-supplied service name would fracture every query."""
    envelopes = _emit(CASES["caller-cannot-override-service"], tmp_path)
    record = next(item for item in envelopes if item["message"] == "x")

    assert record["service"] == "widget"
    assert record["context"]["service"] == "impostor"


def test_unknown_top_level_field_moves_into_context(tmp_path: Path) -> None:
    """Contract 1.3: an extensible flat namespace is how field names diverge."""
    envelopes = _emit(CASES["unknown-top-level-field-moves-into-context"], tmp_path)
    record = next(item for item in envelopes if item["message"] == "x")

    assert "user_id" not in record
    assert record["context"]["user_id"] == 42


def test_secret_valued_keys_are_redacted(tmp_path: Path) -> None:
    """Contract 4: key retained, value replaced, audit trail preserved."""
    envelopes = _emit(CASES["redacts-secret-valued-keys"], tmp_path)
    context = next(item for item in envelopes if item["message"] == "auth attempt")[
        "context"
    ]

    expected = CASES["redacts-secret-valued-keys"]["match"]["context_exact"]
    for key, value in expected.items():
        assert context[key] == value


def test_redaction_recurses(tmp_path: Path) -> None:
    """Contract 4: a nested secret is still a secret."""
    envelopes = _emit(
        CASES["redaction-recurses-into-nested-objects-and-arrays"], tmp_path
    )
    context = next(item for item in envelopes if item["message"] == "nested")["context"]

    expected = CASES["redaction-recurses-into-nested-objects-and-arrays"]["match"][
        "context_json"
    ]
    assert context == expected


def test_correlation_id_stays_in_body(tmp_path: Path) -> None:
    """Contract 2: promoting it to a label creates unbounded Loki streams."""
    from rtech_obs import LABEL_FIELDS

    envelopes = _emit(CASES["correlation-id-stays-in-body"], tmp_path)
    record = next(item for item in envelopes if item["message"] == "x")

    assert record["correlation_id"] == "7f3c9a12"
    assert LABEL_FIELDS == ("service", "host")


def test_duration_is_numeric(tmp_path: Path) -> None:
    """Contract 1.2: duration_ms is a number so Loki/Grafana can aggregate it."""
    envelopes = _emit(CASES["duration-is-numeric-not-string"], tmp_path)
    record = next(item for item in envelopes if item["message"] == "done")

    assert isinstance(record["duration_ms"], (int, float))
    assert not isinstance(record["duration_ms"], str)


def test_unwritable_log_file_degrades_loudly(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Contract 5.1 + 3: degrade to stdout rather than refusing to boot, but say so."""
    case = CASES["unwritable-log-file-degrades-to-stdout-with-warning"]
    unwritable = case["config"]["LOG_FILE"]

    # Must NOT raise: a missing log mount cannot stop a service starting.
    config = init_observability(env=dict(case["config"]), stdout=True)
    logger.complete()
    logger.remove()

    assert config.log_file is not None
    emitted = capsys.readouterr().out
    warnings = [
        json.loads(line)
        for line in emitted.splitlines()
        if line.strip().startswith("{") and '"warning"' in line
    ]
    assert warnings, f"expected a fail-loud degradation warning, got: {emitted!r}"
    assert any(unwritable in record["message"] for record in warnings)
    assert any(
        record.get("event") == "observability.log_file_degraded" for record in warnings
    )


def test_level_below_threshold_is_dropped(tmp_path: Path) -> None:
    """Contract 5: LOG_LEVEL is a floor, not a hint."""
    case = dict(CASES["level-below-threshold-is-dropped"])
    case["config"] = dict(case["config"])
    destination = tmp_path / "out.jsonl"
    init_observability(
        env={**case["config"], "LOG_FILE": str(destination)},
        stdout=False,
    )
    logger.info("not emitted")
    logger.complete()
    logger.remove()

    lines = (
        destination.read_text(encoding="utf-8").splitlines()
        if destination.exists()
        else []
    )
    assert not any('"not emitted"' in line for line in lines)


def test_level_at_threshold_is_emitted(tmp_path: Path) -> None:
    """Contract 5: a record at the configured level passes the floor."""
    destination = tmp_path / "out.jsonl"
    init_observability(
        env={
            "SERVICE_NAME": "widget",
            "LOG_LEVEL": "warning",
            "LOG_FILE": str(destination),
        },
        stdout=False,
    )
    logger.warning("emitted")
    logger.complete()
    logger.remove()

    records = [
        json.loads(line)
        for line in destination.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert any(
        item["message"] == "emitted" and item["level"] == "warning" for item in records
    )
