import logging

import notificator.main  # noqa: F401


def test_httpx_info_logs_are_suppressed() -> None:
    assert logging.getLogger("httpx").level == logging.WARNING
