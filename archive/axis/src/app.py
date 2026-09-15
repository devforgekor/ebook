# src/app.py
from src.handler import (
    ErrorSignatureHandler,
    ExecutionContext,
    ExecutionResult,
)
from src.store import ErrorSignatureStore
from src.notifier.slack_webhook import SlackWebhookNotifier


def main() -> None:
    # ---- Infrastructure ----
    store = ErrorSignatureStore()
    handler = ErrorSignatureHandler(store)

    slack_notifier = SlackWebhookNotifier(
        webhook_url="https://hooks.slack.com/services/XXX/YYY/ZZZ"
    )

    # ---- Execution Context (실행 단위) ----
    ctx = ExecutionContext()

    # ---- Example: execution 결과 입력 ----
    event = handler.handle_execution_result(
        ctx,
        plane="oci",
        component="collector",
        source_or_model="cnn",
        error_type="timeout",
        result=ExecutionResult.FAILURE,
    )

    # ---- Wiring: Core → Notifier ----
    if event:
        slack_notifier.notify(event)


if __name__ == "__main__":
    main()
    