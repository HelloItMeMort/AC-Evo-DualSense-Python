"""UDP listener for Forza Horizon 5 telemetry.

Packet = 324 bytes; offsets verified against FH5 Data Out spec.
Always returns the *latest* packet (drains queued ones) so we never react
to stale telemetry.
"""
import logging
import socket
import struct

log = logging.getLogger("fh5ds.udp")


def parse_packet(p: bytes) -> dict:
    if len(p) < 323:
        raise ValueError(f"Packet too short: {len(p)}")
    f = lambda o: struct.unpack_from("<f", p, o)[0]  # noqa: E731
    i = lambda o: struct.unpack_from("<i", p, o)[0]  # noqa: E731
    b = lambda o: struct.unpack_from("<b", p, o)[0]  # noqa: E731
    return {
        "on": i(0) != 0,
        "max_rpm": f(8), "idle_rpm": f(12), "rpm": f(16),
        "accel_x": f(20), "accel_z": f(28),
        "drive_train": i(224),
        "speed": f(256) * 3.6,
        "power": f(260), "torque": f(264), "boost": f(284),
        "accel": p[315], "brake": p[316], "clutch": p[317],
        "handbrake": p[318], "gear": p[319], "steer": b(320),
    }


class UDPListener:
    """UDP listener that always returns the most recent packet."""

    def __init__(self, host: str, port: int, timeout: float = 0.5):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock = None

    def __enter__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Small recv buffer keeps the OS from queueing many stale packets.
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
        self.sock.bind((self.host, self.port))
        self.sock.settimeout(self.timeout)
        return self

    def __exit__(self, *args):
        if self.sock:
            self.sock.close()
            self.sock = None

    def recv_latest(self):
        """Block up to ``timeout`` for at least one packet, then drain the
        socket and return only the most recent one. Returns ``(pkt, addr)``
        or ``(None, None)`` on timeout."""
        try:
            pkt, addr = self.sock.recvfrom(1500)
        except socket.timeout:
            return None, None
        # Drain whatever else is already queued — we only care about the newest.
        self.sock.setblocking(False)
        try:
            while True:
                pkt, addr = self.sock.recvfrom(1500)
        except (BlockingIOError, OSError):
            pass
        finally:
            self.sock.setblocking(True)
        return pkt, addr
