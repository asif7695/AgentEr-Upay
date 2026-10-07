from __future__ import annotations

import numpy as np

TAUS = np.array([0.10, 0.25, 0.50, 0.75, 0.90])


def wape(p, t):
    p, t = np.asarray(p, float), np.asarray(t, float)
    return float(np.abs(p - t).sum() / max(np.abs(t).sum(), 1e-9))


def pinball_rel(Q_rel, y_rel):
    """Mean pinball loss over the 5 quantiles, in relative units (comparable across agents)."""
    d = y_rel[:, None] - Q_rel
    return float(np.mean(np.maximum(TAUS * d, (TAUS - 1) * d)))


def evaluate_flow(Q, scale, y, keep):
    """Q (N,5) in BDT on rows `keep`; returns the standard metric block for one flow."""
    Q, scale, y = Q[keep], np.asarray(scale)[keep], np.asarray(y)[keep]
    yr, Qr = y / scale, Q / scale[:, None]
    return dict(
        n=int(keep.sum()), wape=wape(Q[:, 2], y), pinball=pinball_rel(Qr, yr),
        coverage80=float(((y >= Q[:, 0]) & (y <= Q[:, 4])).mean()), coverage50=float(((y >= Q[:, 1]) & (y <= Q[:, 3])).mean()),
        width80=float(((Q[:, 4] - Q[:, 0]) / scale).mean()),
    )
