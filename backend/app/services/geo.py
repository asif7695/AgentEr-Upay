"""SYNTHETIC geography. The dataset carries no coordinates, so each division gets a depot at its (approximate) divisional headquarters
and every agent a deterministic position around it: urban agents 3-14 km out, rural ones 15-45 km. Replace this module with a real
agent/depot location table (see docs) and nothing else changes."""
from __future__ import annotations

import hashlib
import math

DEPOTS = {   # approximate divisional headquarters (lat, lon)
    "Dhaka": (23.8103, 90.4125), "Chattogram": (22.3569, 91.7832), "Sylhet": (24.8949, 91.8687), "Rajshahi": (24.3745, 88.6042),
    "Khulna": (22.8456, 89.5403), "Barishal": (22.7010, 90.3535), "Rangpur": (25.7439, 89.2752), "Mymensingh": (24.7471, 90.4203),
}
KM_PER_DEG = 111.0


def _u(seed: str, salt: str) -> float:
    return int(hashlib.sha1(f"{seed}:{salt}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def depot(division: str) -> tuple[float, float]:
    return DEPOTS.get(division, DEPOTS["Dhaka"])


def agent_position(agent_id: str, division: str, tier: str) -> tuple[float, float]:
    la, lo = depot(division)
    lo_r, hi_r = (15.0, 45.0) if tier == "rural" else (3.0, 14.0)
    r = lo_r + (hi_r - lo_r) * _u(agent_id, "r")
    th = 2 * math.pi * _u(agent_id, "t")
    return la + r * math.sin(th) / KM_PER_DEG, lo + r * math.cos(th) / (KM_PER_DEG * math.cos(math.radians(la)))
