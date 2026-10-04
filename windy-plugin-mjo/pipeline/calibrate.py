#!/usr/bin/env python3
"""
Fit the 2x2 matrix that maps raw EOF projections onto the official BoM RMM1/RMM2.

Uses NCEP/NCAR R1 daily winds + CPC blended OLR (both via PSL OPeNDAP) for a
multi-year period and least-squares fits  BoM ~ M @ pcs.  Writes calibration.json
next to this script, which mjo_pipeline.py picks up automatically.

Run once (or whenever the EOFs / climatology change):
  python calibrate.py --start 2023-01-01 --end 2025-12-31
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import numpy as np

import mjo_pipeline as mp


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--start', type=dt.date.fromisoformat, default=dt.date(2023, 1, 1))
    p.add_argument('--end', type=dt.date.fromisoformat, default=dt.date(2025, 12, 31))
    p.add_argument('--cache', type=Path, default=Path('.cache'))
    args = p.parse_args()

    projector = mp.Projector(args.cache / 'ceof.nc')
    projector.calibration = np.eye(2)
    clim = mp.load_climatology()

    first = args.start - dt.timedelta(days=mp.WINDOW)
    days = mp.daterange(first, args.end)
    winds = mp.load_r1_winds(first, args.end)
    olr = mp.load_cpc_olr(first, args.end)
    fields = {d: {'olr': olr[d], **winds[d]} for d in days}
    pcs = projector.raw_pcs(mp.anomalies_for(days, fields, clim))[mp.WINDOW:]
    days = days[mp.WINDOW:]

    bom = {d: (x, y) for d, x, y in mp.load_bom_rmm()}
    if not bom:
        raise SystemExit('BoM RMM series is required for calibration')
    keep = [i for i, d in enumerate(days) if d in bom]
    X = pcs[keep]  # (n, 2) raw
    Y = np.array([bom[days[i]] for i in keep])  # (n, 2) official

    M, *_ = np.linalg.lstsq(X, Y, rcond=None)  # Y = X @ M  ->  rmm = M.T @ pc
    M = M.T
    fit = X @ M.T
    corr = [float(np.corrcoef(fit[:, k], Y[:, k])[0, 1]) for k in range(2)]
    rmse = [float(np.sqrt(np.mean((fit[:, k] - Y[:, k]) ** 2))) for k in range(2)]

    def phase(a):
        ang = np.degrees(np.arctan2(a[:, 1], a[:, 0]))
        return (np.floor((ang + 180) / 45).astype(int) % 8) + 1

    phase_agree = float(np.mean(phase(fit) == phase(Y)))
    result = {
        'matrix': M.round(5).tolist(),
        'period': [days[keep[0]].isoformat(), days[keep[-1]].isoformat()],
        'n': len(keep),
        'corr': [round(c, 4) for c in corr],
        'rmse': [round(e, 4) for e in rmse],
        'phaseAgreement': round(phase_agree, 4),
    }
    print(json.dumps(result, indent=2))
    mp.CALIBRATION_PATH.write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
