"""Artifact lifecycle and structurally gated operator approval workflow."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Callable, Iterator, Protocol

from eod_pipeline.approval.config import (
    ApprovalError,
    approved_config,
    build_candidate_config,
    file_sha256,
    load_sweep_result,
    pretty_json,
    validate_sweep_result,
)
from eod_pipeline.approval.review import (
    build_approval_report,
    report_markdown,
    resolve_review_thresholds,
    review_winner,
)
from eod_pipeline.settings import load_settings


OPERATOR_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


class Sender(Protocol):
    def send(self, approved_config_path: Path) -> dict[str, Any]:
        """Transmit an approved config and return an audit-safe receipt."""


@dataclass(frozen=True)
class WorkflowOutcome:
    run_id: str
    run_directory: Path
    approval_status: str
    candidate_config_path: Path
    approved_config_path: Path | None
    rejection_record_path: Path | None
    report_json_path: Path
    report_markdown_path: Path
    dispatch_status: str


def utc_timestamp(moment: datetime) -> str:
    value = moment.astimezone(timezone.utc).isoformat(timespec="milliseconds")
    return value.replace("+00:00", "Z")


def _default_clock() -> datetime:
    return datetime.now(timezone.utc)


def validate_operator_id(operator_id: str) -> None:
    if not OPERATOR_ID_PATTERN.fullmatch(operator_id):
        raise ApprovalError(
            "operator_id must contain only letters, numbers, '.', '_', or '-'"
        )


def _atomic_write_text(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


class StageLogger:
    def __init__(self, path: Path, clock: Callable[[], datetime]) -> None:
        self.path = path
        self.clock = clock

    def _write(self, stage: str, status: str, details: dict[str, Any]) -> None:
        entry = {
            "timestamp": utc_timestamp(self.clock()),
            "stage": stage,
            "status": status,
            "details": details,
        }
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(
                    entry,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
                + "\n"
            )

    @contextmanager
    def stage(
        self,
        name: str,
        *,
        start: dict[str, Any] | None = None,
    ) -> Iterator[dict[str, Any]]:
        self._write(name, "ENTERED", start or {})
        completion: dict[str, Any] = {}
        try:
            yield completion
        except Exception as error:
            self._write(
                name,
                "FAILED",
                {"error_type": type(error).__name__, "message": str(error)},
            )
            raise
        else:
            self._write(name, "SUCCEEDED", completion)


def _rejection_reason(
    input_fn: Callable[[str], str],
) -> tuple[str, str]:
    while True:
        try:
            reason = input_fn("Rejection reason (required): ")
        except EOFError:
            return "NO_APPROVAL", "EOF while collecting required rejection reason"
        if reason.strip():
            return "REJECTED", reason.strip()


def _read_gate(
    prompt: str,
    input_fn: Callable[[str], str],
) -> tuple[str | None, str | None]:
    try:
        answer = input_fn(prompt)
    except EOFError:
        return "NO_APPROVAL", "EOF before approval"
    if answer == "REJECT":
        return _rejection_reason(input_fn)
    if not answer:
        return "NO_APPROVAL", "Empty approval input"
    return None, answer


def _approval_decision(
    *,
    selection_status: str,
    has_warnings: bool,
    input_fn: Callable[[str], str],
) -> tuple[str, str | None]:
    if selection_status == "NOT_OPTIMIZED":
        status, answer = _read_gate(
            "Type exactly 'OVERRIDE NOT_OPTIMIZED' or 'REJECT': ",
            input_fn,
        )
        if status is not None:
            return status, answer
        if answer != "OVERRIDE NOT_OPTIMIZED":
            return "NO_APPROVAL", "Required NOT_OPTIMIZED override was not provided"
    elif has_warnings:
        status, answer = _read_gate(
            "Type exactly 'ACKNOWLEDGE WARNINGS' or 'REJECT': ",
            input_fn,
        )
        if status is not None:
            return status, answer
        if answer != "ACKNOWLEDGE WARNINGS":
            return "NO_APPROVAL", "Required warning acknowledgement was not provided"

    status, answer = _read_gate(
        "Type exactly 'APPROVE' or 'REJECT': ",
        input_fn,
    )
    if status is not None:
        return status, answer
    if answer == "APPROVE":
        return "APPROVED", None
    return "NO_APPROVAL", "Exact APPROVE phrase was not provided"


def run_approval_workflow(
    *,
    sweep_result_path: str | Path,
    settings_path: str | Path,
    output_root: str | Path,
    operator_id: str,
    max_drawdown_warning_cad: float | None = None,
    min_trades: int | None = None,
    sender: Sender | None = None,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
    clock: Callable[[], datetime] = _default_clock,
) -> WorkflowOutcome:
    validate_operator_id(operator_id)
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    started_at = clock()
    run_id = started_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_directory = output_root / run_id
    run_directory.mkdir()
    logger = StageLogger(run_directory / "stage_log.jsonl", clock)

    with logger.stage("load") as details:
        settings = load_settings(settings_path)
        result = load_sweep_result(sweep_result_path)
        thresholds = resolve_review_thresholds(
            settings,
            max_drawdown_warning_cad=max_drawdown_warning_cad,
            min_trades=min_trades,
        )
        sweep_hash = file_sha256(sweep_result_path)
        details.update(
            {
                "sweep_result_sha256": sweep_hash,
                "settings_sha256": settings.sha256(),
            }
        )

    with logger.stage("validate") as details:
        validate_sweep_result(result, settings)
        details.update(
            {
                "regime": result["regime"],
                "selection_status": result["selection_status"],
                "strategy_id": result["strategy_id"],
            }
        )

    candidate_path = run_directory / "candidate_config.json"
    with logger.stage("candidate") as details:
        candidate = build_candidate_config(
            result,
            settings,
            sweep_result_sha256=sweep_hash,
            review_thresholds=thresholds.to_dict(),
        )
        _atomic_write_text(candidate_path, pretty_json(candidate))
        details["candidate_config_sha256"] = file_sha256(candidate_path)

    report_json_path = run_directory / "approval_report.json"
    report_md_path = run_directory / "approval_report.md"
    with logger.stage("report") as details:
        findings = review_winner(result, settings, thresholds)
        report = build_approval_report(
            result,
            candidate,
            thresholds,
            findings,
            run_id=run_id,
            operator_id=operator_id,
            approval_status="PENDING",
        )
        _atomic_write_text(report_json_path, pretty_json(report))
        _atomic_write_text(report_md_path, report_markdown(report))
        output_fn(report_markdown(report))
        details.update(
            {
                "finding_codes": [finding["code"] for finding in findings],
                "has_warnings": bool(findings),
            }
        )

    with logger.stage("approval") as details:
        status, rejection_reason = _approval_decision(
            selection_status=result["selection_status"],
            has_warnings=bool(findings),
            input_fn=input_fn,
        )
        decision_time = utc_timestamp(clock())
        details["approval_status"] = status

    approved_path: Path | None = None
    rejection_path: Path | None = None
    dispatch_status = "NOT_ATTEMPTED"
    if status == "APPROVED":
        approved_path = run_directory / "approved_config.json"
        approved = approved_config(
            candidate,
            operator_id=operator_id,
            timestamp=decision_time,
        )
        _atomic_write_text(approved_path, pretty_json(approved))
    else:
        rejection_path = run_directory / "rejection_record.json"
        rejection = {
            "schema_version": 1,
            "run_id": run_id,
            "operator_id": operator_id,
            "status": status,
            "reason": rejection_reason,
            "timestamp": decision_time,
            "candidate_config_sha256": file_sha256(candidate_path),
        }
        _atomic_write_text(rejection_path, pretty_json(rejection))

    with logger.stage("dispatch") as details:
        receipt: dict[str, Any] | None = None
        if status != "APPROVED":
            dispatch_status = "SKIPPED_NOT_APPROVED"
        elif sender is None:
            dispatch_status = "LOCAL_ONLY"
        else:
            # The sender's only call site is structurally inside this branch.
            receipt = sender.send(approved_path)
            dispatch_status = "SENT"
        details["dispatch_status"] = dispatch_status
        if receipt is not None:
            details["receipt"] = receipt

    final_report = build_approval_report(
        result,
        candidate,
        thresholds,
        findings,
        run_id=run_id,
        operator_id=operator_id,
        approval_status=status,
        rejection_reason=rejection_reason,
        dispatch_status=dispatch_status,
    )
    _atomic_write_text(report_json_path, pretty_json(final_report))
    _atomic_write_text(report_md_path, report_markdown(final_report))
    latest = {
        "run_id": run_id,
        "run_directory": str(run_directory),
        "approval_status": status,
        "dispatch_status": dispatch_status,
    }
    _atomic_write_text(output_root / "latest_run.json", pretty_json(latest))

    return WorkflowOutcome(
        run_id=run_id,
        run_directory=run_directory,
        approval_status=status,
        candidate_config_path=candidate_path,
        approved_config_path=approved_path,
        rejection_record_path=rejection_path,
        report_json_path=report_json_path,
        report_markdown_path=report_md_path,
        dispatch_status=dispatch_status,
    )
