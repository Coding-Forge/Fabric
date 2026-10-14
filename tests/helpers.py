"""Shared test helpers (no network, no storage)."""
from unittest.mock import AsyncMock, MagicMock

from env.context import Context


def make_context(state=None, invoke=None):
    """Return a real ``Context`` whose I/O is replaced with mocks.

    :param state: Value for ``current_state``.
    :param invoke: Optional ``invokeAPI`` replacement (AsyncMock or coroutine function).
    """
    ctx = Context()
    ctx.current_state = state
    ctx.invokeAPI = invoke if invoke is not None else AsyncMock()
    ctx.fm = MagicMock()
    ctx.fm.save = AsyncMock()
    ctx.logger = MagicMock()
    pbi = MagicMock()
    pbi.get_headers.return_value = {"Authorization": "Bearer x"}
    ctx.clients = {"pbi": pbi}
    return ctx
