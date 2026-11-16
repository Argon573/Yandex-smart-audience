from threading import Lock

_lock = Lock()
_provider_actions_total = 0
_provider_actions_failed = 0


def record_provider_action() -> None:
    global _provider_actions_total
    with _lock:
        _provider_actions_total += 1


def record_failed_provider_action() -> None:
    global _provider_actions_failed
    with _lock:
        _provider_actions_failed += 1


def provider_actions_total() -> int:
    with _lock:
        return _provider_actions_total


def provider_action_success_rate() -> float:
    with _lock:
        total = _provider_actions_total + _provider_actions_failed
        return (_provider_actions_total / total) if total else 0.0


def reset_provider_actions() -> None:
    global _provider_actions_total, _provider_actions_failed
    with _lock:
        _provider_actions_total = 0
        _provider_actions_failed = 0


def render_metrics() -> str:
    total = provider_actions_total()
    return (
        "# HELP provider_actions_total Successful Yandex provider device actions.\n"
        "# TYPE provider_actions_total counter\n"
        f"provider_actions_total {total}\n"
    )
