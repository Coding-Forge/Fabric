"""Offline network guard for report contract checks."""

import socket
from unittest.mock import patch


def deny_network():
    """Block Internet sockets, preserving Unix sockets needed by asyncio."""
    original = socket.socket.connect
    original_ex = socket.socket.connect_ex

    def guard(method):
        def connect(sock, address):
            if sock.family in (socket.AF_INET, socket.AF_INET6):
                raise AssertionError("Unit tests must not access the network")
            return method(sock, address)

        return connect

    return (
        patch.object(socket.socket, "connect", guard(original)),
        patch.object(socket.socket, "connect_ex", guard(original_ex)),
        patch.object(
            socket, "getaddrinfo", side_effect=AssertionError("DNS is offline")
        ),
    )
