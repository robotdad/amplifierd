"""Port availability utilities for amplifierd."""

from __future__ import annotations

import socket


def find_available_port(preferred: int, max_attempts: int = 10) -> tuple[int, bool]:
    """Return ``(port, was_incremented)``.

    Tries *preferred* first.  If it is already bound, increments by one until a
    free port is found or *max_attempts* is exhausted.

    Only auto-increments when the caller did not explicitly request a specific
    port — callers should pass the default port here and handle ``was_incremented``
    to announce the change to the user.

    Raises ``OSError`` when no port in the range is available, with a message
    that suggests ``--port`` as the fix.
    """
    for candidate in range(preferred, preferred + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", candidate))
                return candidate, candidate != preferred
            except OSError:
                continue

    raise OSError(
        f"No available port found in range {preferred}–{preferred + max_attempts - 1}. "
        f"Use --port to specify a different port."
    )
