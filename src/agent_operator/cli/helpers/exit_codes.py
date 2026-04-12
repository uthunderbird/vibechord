from __future__ import annotations

import typer

from agent_operator.domain import OperationStatus

EXIT_COMPLETED = 0
EXIT_FAILED = 1
EXIT_NEEDS_HUMAN = 2
EXIT_CANCELLED = 3
EXIT_INTERNAL_ERROR = 4


def operation_exit_code(status: OperationStatus) -> int:
    """Map an operation status to the stable CLI exit code contract."""
    if status is OperationStatus.COMPLETED:
        return EXIT_COMPLETED
    if status is OperationStatus.FAILED:
        return EXIT_FAILED
    if status is OperationStatus.NEEDS_HUMAN:
        return EXIT_NEEDS_HUMAN
    if status is OperationStatus.CANCELLED:
        return EXIT_CANCELLED
    return EXIT_INTERNAL_ERROR


def raise_for_operation_status(status: OperationStatus) -> None:
    """Exit with the semantic code for a terminal or attention-gated status."""
    raise typer.Exit(code=operation_exit_code(status))
