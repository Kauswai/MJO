#!/usr/bin/env python3
"""
MJO / RMM data pipeline for windy-plugin-mjo.

Produces a small JSON file (mjo.json) that the Windy plugin loads. It contains:

  * analysis  - daily RMM1/RMM2 computed here, up to yesterday (no lag), from
                CPC blended OLR (NOAA) + GEFS control analysis winds (U850/U200).
                The few most recent days that CPC OLR does not cover yet are
                filled with bias-corrected GEFS 0-24 h OLR.
  * bom       - the official BoM RMM series (lagged ~1-2 weeks), when reachable.
  * forecast  - GEFS 31-member ensemble RMM forecast, from the latest 00Z run,
                for the init day and the following 7 days.

Method (Wheeler & Hendon 2004, Gottschalck et al. 2010 for forecasts):
  1. 15S-15N mean of OLR, U850, U200 on a 2.5 degree longitude grid (144 points)
  2. anomalies w.r.t. a 1991-2020 daily climatology (mean + 3 annual harmonics)
  3. subtract the mean anomaly of the previous 120 days (forecast days use the
     analysis + forecast anomalies of the 120 days before them)
  4. normalise each field and project onto the two leading combined EOFs
  5. linear calibration (2x2 matrix) of the projections to the official BoM
     RMM scale, fitted by calibrate.py

Usage:
  python mjo_pipeline.py --out ../dist-data/mjo.json [--cache .cache]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import threading
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import requests

# --------------------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------------------

PSL = 'https://psl.noaa.gov/thredds/dodsC/Datasets'
# PSL's plain file server. Its THREDDS/OPeNDAP service rate-limits (HTTP 429) cloud
# runners, so the daily job reads the netCDF4/HDF5 files here with HTTP range requests.
PSL_FILES = 'https://downloads.psl.noaa.gov/Datasets'
OLR_DAILY = f'{PSL_FILES}/cpc_blended_olr-2.5deg/olr.cbo-2.5deg.day.mean.nc'
OLR_LTM = f'{PSL_FILES}/cpc_blended_olr-2.5deg/olr.cbo-2.5deg.day.ltm.1991-2020.nc'
UWND_LTM = f'{PSL_FILES}/ncep.reanalysis.derived/pressure/uwnd.day.ltm.1991-2020.nc'
UWND_R1 = f'{PSL}/ncep.reanalysis/Dailies/pressure/uwnd.{{year}}.nc'
# NCEP level axis: 1000,925,850,700,600,500,400,300,250,200,... hPa
UWND_LEVELS = {'u850': 2, 'u200': 9}

# Combined EOFs of 15S-15N OLR/U850/U200 (144 longitudes each), WH04 style.
# Downloaded at run time (pinned commit) instead of being redistributed here.
EOF_URL = (
    'https://raw.githubusercontent.com/MJO-Teleconnection-Diagnostics/pyMTDG/'
    '05b310445741542369f95f58f5a96f8d9bb83856/MJO/ceof.nc'
)

BOM_RMM_URL = 'https://www.bom.gov.au/clim_data/IDCKGEM000/rmm.74toRealtime.txt'
BROWSER_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/130.0 Safari/537.36'
    ),
    'Accept': '*/*',
    'Accept-Language': 'en-US,en;q=0.9',
}

GEFS = 'https://noaa-gefs-pds.s3.amazonaws.com'
GEFS_MEMBERS = ['gec00'] + [f'gep{i:02d}' for i in range(1, 31)]

# 2.5 degree grids with latitude running 90 -> -90: 15N..15S = rows 30..42
LAT_ROWS_2P5 = slice(30, 43)
# GEFS 0.5 degree grid (361 x 720, 90 -> -90, 0 -> 359.5): 15N..15S = rows 150..210
LAT_ROWS_0P5 = slice(150, 211)

VARS = ('olr', 'u850', 'u200')
GRIB_MATCH = {
    'u850': ':UGRD:850 mb:',
    'u200': ':UGRD:200 mb:',
    'olr': ':ULWRF:top of atmosphere:',
}

WINDOW = 120  # days, mean removed before projection
ANALYSIS_DAYS_OUT = 90  # days of analysis written to the json
FORECAST_DAYS = 7  # days after the init day
OLR_BIAS_DAYS = 21  # days used to estimate the GEFS-vs-CPC OLR bias

# Linear map from raw EOF projections to the official BoM RMM scale (the EOF file
# stores the two modes in the opposite order, hence the mostly off-diagonal matrix).
# Fitted with calibrate.py (NCEP R1 winds + CPC OLR vs BoM, 2023-2025: r = 0.97 / 0.98);
# calibration.json, when present, overrides this.
CALIBRATION = np.array(
    [
        [0.00884, 0.12422],
        [0.1376, -0.01157],
    ]
)
CALIBRATION_PATH = Path(__file__).with_name('calibration.json')

_tls = threading.local()


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def log(*args):
    print(f'[{utcnow():%H:%M:%S}]', *args, file=sys.stderr, flush=True)


def session() -> requests.Session:
    if not hasattr(_tls, 's'):
        s = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=4, max_retries=3)
        s.mount('https://', adapter)
        _tls.s = s
    return _tls.s


def http_get(url: str, headers: dict | None = None, timeout: int = 120, tries: int = 6) -> requests.Response:
    """GET with retries. Rate limits (429) and server errors back off exponentially
    (10, 20, 40, 80 ... s, or the server's Retry-After), since NOAA PSL throttles
    busy cloud IP ranges such as GitHub's runners."""
    last = None
    for attempt in range(tries):
        wait = min(300, 10 * 2**attempt)
        try:
            r = session().get(url, headers=headers, timeout=timeout)
            if r.status_code in (200, 206):
                return r
            if r.status_code == 404:
                r.raise_for_status()
            last = requests.HTTPError(f'{r.status_code} for {url}')
            retry_after = r.headers.get('Retry-After', '')
            if retry_after.isdigit():
                wait = min(600, int(retry_after))
        except requests.HTTPError:
            raise
        except requests.RequestException as e:  # network hiccup, retry
            last = e
        if attempt < tries - 1:
            log(f'retry in {wait}s: {last}')
            time.sleep(wait)
    raise RuntimeError(f'GET failed: {url}: {last}')


# --------------------------------------------------------------------------------------
# OPeNDAP ascii helper (no netCDF/DAP client library needed)
# --------------------------------------------------------------------------------------

def opendap_ascii(url: str, constraint: str) -> np.ndarray:
    """Fetch `var[a:s:b][..]` through the OPeNDAP .ascii service and return the array."""
    text = http_get(f'{url}.ascii?{constraint}', timeout=300).text
    body = text.split('-' * 45, 1)[1]
    m = re.search(r'^\s*([\w.]+)((?:\[\d+\])+)\s*$', body, re.M)
    if not m:
        raise ValueError(f'Unexpected OPeNDAP response for {constraint}: {text[:300]}')
    shape = [int(n) for n in re.findall(r'\[(\d+)\]', m.group(2))]
    values: list[float] = []
    for line in body[m.end():].splitlines():
        line = line.strip()
        if not line:
            if values:
                break
            continue
        if line.startswith('['):
            line = line.split(',', 1)[1] if ',' in line else ''
        elif len(shape) > 1:
            break
        values.extend(float(v) for v in line.split(',') if v.strip())
    arr = np.array(values, dtype=np.float64)
    arr[np.abs(arr) > 1e20] = np.nan  # _FillValue / missing_value
    return arr.reshape(shape)


# --------------------------------------------------------------------------------------
# Climatology
# --------------------------------------------------------------------------------------

def smooth_annual_cycle(clim: np.ndarray, nharm: int = 3) -> np.ndarray:
    """Keep the mean and first `nharm` harmonics along axis 0 (365 days)."""
    spec = np.fft.rfft(clim, axis=0)
    spec[nharm + 1:] = 0
    return np.fft.irfft(spec, n=clim.shape[0], axis=0)


CLIMATOLOGY_PATH = Path(__file__).with_name('climatology.npz')


def load_climatology() -> dict[str, np.ndarray]:
    """(365, 144) smoothed daily climatology of each variable, 15S-15N mean.

    The 1991-2020 climatology never changes, so it is stored next to this script
    (climatology.npz, committed) and only downloaded when that file is missing."""
    if CLIMATOLOGY_PATH.exists():
        with np.load(CLIMATOLOGY_PATH) as z:
            return {v: z[v].astype(np.float64) for v in VARS}
    clim = download_climatology()
    np.savez_compressed(CLIMATOLOGY_PATH, **{v: clim[v].astype(np.float32) for v in VARS})
    return clim


@contextmanager
def remote_h5(url: str):
    """Open a remote netCDF4/HDF5 file; h5py then fetches only the chunks it reads."""
    import fsspec
    import h5py

    fs = fsspec.filesystem('https', block_size=2**20)
    for attempt in range(5):
        try:
            f = fs.open(url, 'rb', cache_type='blockcache')
            break
        except Exception as e:  # transient network / server errors
            if attempt == 4:
                raise
            log(f'retry open in {10 * 2**attempt}s: {e}')
            time.sleep(10 * 2**attempt)
    try:
        with h5py.File(f, 'r') as h:
            yield h
    finally:
        f.close()


def h5_band(var, t0: int, t1: int, *index) -> np.ndarray:
    """var[t0:t1, *index, 15N..15S, :] as float64 with missing values -> NaN."""
    arr = np.asarray(var[(slice(t0, t1), *index, LAT_ROWS_2P5, slice(None))], dtype=np.float64)
    arr[np.abs(arr) > 1e20] = np.nan
    return arr


def download_climatology() -> dict[str, np.ndarray]:
    log('climatology: OLR')
    with remote_h5(OLR_LTM) as h:
        olr = np.nanmean(h5_band(h['olr'], 0, 365), axis=1)
    out = {'olr': smooth_annual_cycle(olr)}
    log('climatology: U850/U200')
    with remote_h5(UWND_LTM) as h:
        for var, lev in UWND_LEVELS.items():
            out[var] = smooth_annual_cycle(np.nanmean(h5_band(h['uwnd'], 0, 365, lev), axis=1))
    return out


def clim_index(d: dt.date) -> int:
    """Index into a 365-day climatology (Feb 29 shares Feb 28)."""
    doy = d.timetuple().tm_yday
    if d.year % 4 == 0 and (d.year % 100 != 0 or d.year % 400 == 0) and doy >= 60:
        doy -= 1
    return doy - 1


# --------------------------------------------------------------------------------------
# Observations
# --------------------------------------------------------------------------------------

OLR_EPOCH = dt.date(1991, 1, 1)  # first day of the CPC blended OLR record


def cpc_olr_last_date() -> dt.date:
    with remote_h5(OLR_DAILY) as h:
        hours = float(h['time'][-1])
    return (dt.datetime(1800, 1, 1) + dt.timedelta(hours=hours)).date()


def load_cpc_olr(start: dt.date, end: dt.date) -> dict[dt.date, np.ndarray]:
    """15S-15N mean CPC blended OLR (144 lons) for each day in [start, end]."""
    return fill_gaps(load_cpc_olr_raw(start, end))


def load_cpc_olr_raw(start: dt.date, end: dt.date) -> dict[dt.date, np.ndarray]:
    """As load_cpc_olr, but missing grid points stay NaN."""
    log(f'CPC OLR {start}..{end}')
    first = (start - OLR_EPOCH).days
    last = (end - OLR_EPOCH).days
    with remote_h5(OLR_DAILY) as h:
        band = h5_band(h['olr'], first, last + 1)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)  # all-missing days -> NaN
        arr = np.nanmean(band, axis=1)
    return {OLR_EPOCH + dt.timedelta(days=first + k): arr[k] for k in range(arr.shape[0])}


def cpc_olr_with_cache(start: dt.date, end: dt.date, cache: Path | None) -> tuple[dict, dt.date]:
    """CPC OLR for [start, last available day <= end], fetching only days missing from
    the on-disk cache. If PSL is unreachable, the cached days are used as they are and
    the caller fills the remaining days with GEFS. Returns (series, last observed day)."""
    cache_file = cache / 'cpc_olr.npz' if cache else None
    raw: dict[dt.date, np.ndarray] = {}
    if cache_file and cache_file.exists():
        with np.load(cache_file) as z:
            raw = {dt.date.fromordinal(int(o)): v for o, v in zip(z['days'], z['olr'])}
    try:
        last = min(cpc_olr_last_date(), end)
        # refetch the newest few cached days too: CPC sometimes fills them in late
        have = [d for d in raw if start <= d <= last]
        first_missing = start if not have else min(
            max(have) - dt.timedelta(days=3),
            min((d for d in daterange(start, last) if d not in raw), default=last),
        )
        if first_missing <= last:
            raw.update(load_cpc_olr_raw(max(first_missing, start), last))
    except Exception as e:
        cached = [d for d in raw if d >= start]
        if not cached:
            raise
        last = min(max(cached), end)
        log(f'CPC OLR unavailable ({e}); using cached days through {last}')
    if cache_file:
        keep = {d: v for d, v in raw.items() if d >= end - dt.timedelta(days=400)}
        days = sorted(keep)
        np.savez_compressed(
            cache_file,
            days=np.array([d.toordinal() for d in days]),
            olr=np.array([keep[d] for d in days], dtype=np.float32),
        )
    missing = [d for d in daterange(start, last) if d not in raw]
    if missing:
        raise RuntimeError(f'CPC OLR missing {len(missing)} days, e.g. {missing[0]}')
    series = fill_gaps({d: raw[d].astype(np.float64) for d in daterange(start, last)})
    return series, last


def fill_gaps(series: dict[dt.date, np.ndarray]) -> dict[dt.date, np.ndarray]:
    """Linearly interpolate missing (NaN) values in time, per longitude."""
    days = sorted(series)
    arr = np.array([series[d] for d in days])
    t = np.arange(len(days))
    for j in range(arr.shape[1]):
        bad = np.isnan(arr[:, j])
        if bad.any() and not bad.all():
            arr[bad, j] = np.interp(t[bad], t[~bad], arr[~bad, j])
    return {d: arr[k] for k, d in enumerate(days)}


def load_r1_winds(start: dt.date, end: dt.date) -> dict[dt.date, dict[str, np.ndarray]]:
    """NCEP/NCAR R1 daily U850/U200 (15S-15N mean). Used for calibration only."""
    out = {}
    for year in range(start.year, end.year + 1):
        y0 = max(start, dt.date(year, 1, 1))
        y1 = min(end, dt.date(year, 12, 31))
        i0 = (y0 - dt.date(year, 1, 1)).days
        i1 = (y1 - dt.date(year, 1, 1)).days
        log(f'R1 winds {y0}..{y1}')
        levels = {
            var: opendap_ascii(
                UWND_R1.format(year=year), f'uwnd[{i0}:1:{i1}][{lev}:1:{lev}][30:1:42][0:1:143]'
            )[:, 0].mean(axis=1)
            for var, lev in UWND_LEVELS.items()
        }
        for k in range(i1 - i0 + 1):
            out[y0 + dt.timedelta(days=k)] = {var: levels[var][k] for var in UWND_LEVELS}
    return out


def load_bom_rmm() -> list[tuple[dt.date, float, float]]:
    """Official BoM RMM series; empty list when the BoM server refuses us."""
    try:
        r = http_get(BOM_RMM_URL, headers=BROWSER_HEADERS, timeout=60, tries=2)
    except Exception as e:  # BoM blocks some networks; that's fine
        log(f'BoM RMM not available: {e}')
        return []
    rows = []
    for line in r.text.splitlines()[2:]:
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
            x1, x2 = float(parts[3]), float(parts[4])
        except ValueError:
            continue
        if abs(x1) > 100 or abs(x2) > 100:  # missing value 1e36 / 999
            continue
        rows.append((dt.date(y, m, d), x1, x2))
    log(f'BoM RMM: {len(rows)} rows, last {rows[-1][0] if rows else None}')
    return rows


# --------------------------------------------------------------------------------------
# GEFS (AWS open data, byte-range reads guided by the .idx files)
# --------------------------------------------------------------------------------------

def gefs_url(init: dt.datetime, member: str, fhour: int) -> str:
    d = init.strftime('%Y%m%d')
    h = init.strftime('%H')
    return f'{GEFS}/gefs.{d}/{h}/atmos/pgrb2ap5/{member}.t{h}z.pgrb2a.0p50.f{fhour:03d}'


def reduce_0p5(values: np.ndarray) -> np.ndarray:
    """(361, 720) global 0.5deg field -> 15S-15N mean on 144 x 2.5deg longitudes."""
    band = values[LAT_ROWS_0P5].mean(axis=0)  # (720,)
    # box mean of the 5 x 0.5deg points centred on each 2.5deg longitude
    padded = np.concatenate([band[-2:], band, band[:2]])
    return np.convolve(padded, np.ones(5) / 5, mode='valid')[::5]


_grib_lock = threading.Lock()  # ecCodes' message parser is not thread-safe


def decode_grib(buf: bytes) -> np.ndarray:
    import eccodes

    with _grib_lock:
        gid = eccodes.codes_new_from_message(buf)
        try:
            ni = eccodes.codes_get(gid, 'Ni')
            nj = eccodes.codes_get(gid, 'Nj')
            vals = eccodes.codes_get_values(gid).reshape(nj, ni)
            if eccodes.codes_get(gid, 'jScansPositively'):
                vals = vals[::-1]
        finally:
            eccodes.codes_release(gid)
    return vals


def fetch_grib_message(url: str, start: int, end: int | str) -> bytes:
    """Byte-range read of one GRIB2 message, verified before it reaches ecCodes."""
    for _ in range(4):
        buf = http_get(url, headers={'Range': f'bytes={start}-{end}'}).content
        if buf[:4] == b'GRIB' and buf[-4:] == b'7777':
            return buf
        time.sleep(2)
    raise RuntimeError(f'Incomplete GRIB message {url} @ {start}')


class GefsReader:
    """Reads selected records of GEFS pgrb2a files with an on-disk cache."""

    def __init__(self, cache_dir: Path | None):
        self.cache_dir = cache_dir
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_file(self, init: dt.datetime, member: str, fhour: int) -> Path | None:
        if not self.cache_dir:
            return None
        return self.cache_dir / f'{init:%Y%m%d%H}_{member}_f{fhour:03d}.npz'

    def exists(self, init: dt.datetime, member: str, fhour: int) -> bool:
        try:
            r = session().head(gefs_url(init, member, fhour) + '.idx', timeout=30)
            return r.status_code == 200
        except requests.RequestException:
            return False

    def read(self, init: dt.datetime, member: str, fhour: int, variables: tuple[str, ...]) -> dict:
        cf = self._cache_file(init, member, fhour)
        cached: dict[str, np.ndarray] = {}
        if cf and cf.exists():
            with np.load(cf) as z:
                cached = {k: z[k] for k in z.files}
        missing = [v for v in variables if v not in cached]
        if not missing:
            return {v: cached[v] for v in variables}

        url = gefs_url(init, member, fhour)
        idx = http_get(url + '.idx').text.splitlines()
        offsets = []
        for line in idx:
            parts = line.split(':')
            offsets.append(int(parts[1]))
        for var in missing:
            pos = next((i for i, line in enumerate(idx) if GRIB_MATCH[var] in line), None)
            if pos is None:
                raise KeyError(f'{var} not in {url}')
            start = offsets[pos]
            end = offsets[pos + 1] - 1 if pos + 1 < len(offsets) else ''
            buf = fetch_grib_message(url, start, end)
            cached[var] = reduce_0p5(decode_grib(buf)).astype(np.float32)
        if cf:
            tmp = cf.with_suffix('.tmp.npz')
            np.savez(tmp, **cached)
            os.replace(tmp, cf)
        return {v: cached[v] for v in variables}

    def prune(self, keep_days: int = 260):
        if not self.cache_dir:
            return
        cutoff = utcnow() - dt.timedelta(days=keep_days)
        for f in self.cache_dir.glob('*.npz'):
            try:
                if dt.datetime.strptime(f.name[:10], '%Y%m%d%H') < cutoff:
                    f.unlink()
            except ValueError:
                pass


def latest_gefs_init(reader: GefsReader, max_lead: int) -> dt.datetime:
    """Most recent 00Z GEFS run whose last member has reached `max_lead`."""
    now = utcnow()
    day = dt.datetime(now.year, now.month, now.day)
    for back in range(0, 4):
        init = day - dt.timedelta(days=back)
        if reader.exists(init, GEFS_MEMBERS[-1], max_lead):
            return init
    raise RuntimeError('No complete GEFS 00Z run found in the last 4 days')


def gefs_analysis_winds(reader: GefsReader, days: list[dt.date], pool: ThreadPoolExecutor) -> dict:
    """Daily mean U850/U200 from the 00/06/12/18Z GEFS control analyses."""
    jobs = {}
    for d in days:
        for h in (0, 6, 12, 18):
            init = dt.datetime(d.year, d.month, d.day, h)
            jobs[(d, h)] = pool.submit(reader.read, init, 'gec00', 0, ('u850', 'u200'))
    out = {}
    for d in days:
        parts = [jobs[(d, h)].result() for h in (0, 6, 12, 18)]
        out[d] = {v: np.mean([p[v] for p in parts], axis=0) for v in ('u850', 'u200')}
    return out


def gefs_day_olr(reader: GefsReader, init: dt.datetime, member: str, day: int, pool=None):
    """Mean OLR over forecast day `day` (leads 24*day+6 .. 24*day+24, 6 h averages)."""
    leads = [24 * day + h for h in (6, 12, 18, 24)]
    if pool:
        futs = [pool.submit(reader.read, init, member, fh, ('olr',)) for fh in leads]
        parts = [f.result() for f in futs]
    else:
        parts = [reader.read(init, member, fh, ('olr',)) for fh in leads]
    return np.mean([p['olr'] for p in parts], axis=0)


def gefs_member_forecast(reader: GefsReader, init: dt.datetime, member: str, ndays: int):
    """Daily means of all three fields for forecast days 0..ndays-1 of one member."""
    out = []
    for day in range(ndays):
        winds = [reader.read(init, member, 24 * day + h, ('u850', 'u200')) for h in (0, 6, 12, 18)]
        out.append(
            {
                'u850': np.mean([w['u850'] for w in winds], axis=0),
                'u200': np.mean([w['u200'] for w in winds], axis=0),
                'olr': gefs_day_olr(reader, init, member, day),
            }
        )
    return out


# --------------------------------------------------------------------------------------
# RMM
# --------------------------------------------------------------------------------------

class Projector:
    def __init__(self, eof_path: Path | None = None):
        import netCDF4

        if eof_path is None or not eof_path.exists():
            data = http_get(EOF_URL).content
            ds = netCDF4.Dataset('ceof.nc', memory=data)
        else:
            ds = netCDF4.Dataset(eof_path)
        self.eof = np.concatenate(
            [np.asarray(ds[v][:2, :], dtype=np.float64) for v in VARS], axis=1
        )  # (2, 432)
        self.norm = {v: float(ds[f'norm_{v}'][()]) for v in VARS}
        ds.close()
        self.calibration = CALIBRATION
        if CALIBRATION_PATH.exists():
            self.calibration = np.array(json.loads(CALIBRATION_PATH.read_text())['matrix'])

    def raw_pcs(self, anomalies: dict[str, np.ndarray]) -> np.ndarray:
        """anomalies: var -> (N, 144) daily anomalies (contiguous days).
        Returns (N, 2) raw projections; the first WINDOW rows are NaN."""
        n = anomalies['olr'].shape[0]
        out = np.full((n, 2), np.nan)
        for i in range(WINDOW, n):
            vec = np.concatenate(
                [
                    (anomalies[v][i] - anomalies[v][i - WINDOW:i].mean(axis=0)) / self.norm[v]
                    for v in VARS
                ]
            )
            out[i] = self.eof @ vec
        return out

    def rmm(self, anomalies: dict[str, np.ndarray]) -> np.ndarray:
        pcs = self.raw_pcs(anomalies)
        return pcs @ self.calibration.T


def anomalies_for(days: list[dt.date], fields: dict[dt.date, dict], clim: dict) -> dict:
    return {
        v: np.array([fields[d][v] - clim[v][clim_index(d)] for d in days]) for v in VARS
    }


# --------------------------------------------------------------------------------------
# Main pipeline
# --------------------------------------------------------------------------------------

def daterange(a: dt.date, b: dt.date) -> list[dt.date]:
    return [a + dt.timedelta(days=k) for k in range((b - a).days + 1)]


def run(out_path: Path, cache: Path | None, workers: int = 24) -> dict:
    reader = GefsReader(cache / 'gefs' if cache else None)
    projector = Projector(cache / 'ceof.nc' if cache else None)
    clim = load_climatology()
    nfc = FORECAST_DAYS + 1

    init = latest_gefs_init(reader, 24 * nfc)
    d0 = init.date()
    log(f'GEFS init {init:%Y-%m-%d %HZ}')

    hist_days = daterange(d0 - dt.timedelta(days=WINDOW + ANALYSIS_DAYS_OUT), d0 - dt.timedelta(days=1))

    with ThreadPoolExecutor(workers) as pool:
        # ---- winds: GEFS control analyses
        log(f'analysis winds for {len(hist_days)} days')
        winds = gefs_analysis_winds(reader, hist_days, pool)

        # ---- OLR: CPC blended + bias-corrected GEFS control 0-24 h for the latest days
        olr, cpc_last = cpc_olr_with_cache(hist_days[0], d0 - dt.timedelta(days=1), cache)
        gap_days = daterange(cpc_last + dt.timedelta(days=1), d0 - dt.timedelta(days=1))
        bias_days = daterange(cpc_last - dt.timedelta(days=OLR_BIAS_DAYS - 1), cpc_last)
        log(f'OLR: CPC through {cpc_last}, GEFS fill {len(gap_days)} days, bias from {len(bias_days)} days')
        gefs_olr = {
            d: pool.submit(gefs_day_olr, reader, dt.datetime(d.year, d.month, d.day), 'gec00', 0)
            for d in bias_days + gap_days
        }
        gefs_olr = {d: f.result() for d, f in gefs_olr.items()}
        olr_bias = np.mean([gefs_olr[d] - olr[d] for d in bias_days], axis=0)
        for d in gap_days:
            olr[d] = gefs_olr[d] - olr_bias

        fields = {d: {'olr': olr[d], **winds[d]} for d in hist_days}
        anom_hist = anomalies_for(hist_days, fields, clim)
        rmm_hist = projector.rmm(anom_hist)

        # ---- ensemble forecast
        log(f'forecast: {len(GEFS_MEMBERS)} members x {nfc} days')
        futs = {m: pool.submit(gefs_member_forecast, reader, init, m, nfc) for m in GEFS_MEMBERS}
        fc_days = daterange(d0, d0 + dt.timedelta(days=nfc - 1))
        members = []
        for m in GEFS_MEMBERS:
            days_fields = futs[m].result()
            for f in days_fields:
                f['olr'] = f['olr'] - olr_bias
            anom_fc = {
                v: np.array([days_fields[k][v] - clim[v][clim_index(d)] for k, d in enumerate(fc_days)])
                for v in VARS
            }
            # the 120-day mean for forecast days spans the analysis + earlier forecast days
            tail = {v: np.concatenate([anom_hist[v][-WINDOW:], anom_fc[v]]) for v in VARS}
            members.append(projector.rmm(tail)[WINDOW:])

    reader.prune()
    members = np.array(members)  # (31, nfc, 2)
    mean = members.mean(axis=0)

    analysis_days = hist_days[WINDOW:]
    bom = load_bom_rmm()
    bom_cut = d0 - dt.timedelta(days=ANALYSIS_DAYS_OUT + 30)

    def r(x):
        return round(float(x), 3)

    data = {
        'version': 1,
        'generated': utcnow().strftime('%Y-%m-%dT%H:%MZ'),
        'analysis': {
            'source': 'CPC blended OLR + GEFS control analysis U850/U200',
            'olrFilledFrom': gap_days[0].isoformat() if gap_days else None,
            'days': [
                {'d': d.isoformat(), 'x': r(v[0]), 'y': r(v[1])}
                for d, v in zip(analysis_days, rmm_hist[WINDOW:])
            ],
        },
        'bom': {
            'source': 'Australian Bureau of Meteorology RMM (official)',
            'days': [{'d': d.isoformat(), 'x': r(x), 'y': r(y)} for d, x, y in bom if d >= bom_cut],
        },
        'forecast': {
            'model': 'GEFS',
            'init': init.strftime('%Y-%m-%dT%H:%MZ'),
            'dates': [d.isoformat() for d in fc_days],
            'memberNames': GEFS_MEMBERS,
            'members': [[[r(p[0]), r(p[1])] for p in m] for m in members],
            'mean': [[r(p[0]), r(p[1])] for p in mean],
        },
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, separators=(',', ':')))
    log(f'wrote {out_path} ({out_path.stat().st_size / 1024:.1f} kB)')
    return data


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--out', type=Path, default=Path('public/mjo.json'))
    p.add_argument('--cache', type=Path, default=Path('.cache'))
    p.add_argument('--workers', type=int, default=24)
    args = p.parse_args()
    run(args.out, args.cache, args.workers)


if __name__ == '__main__':
    main()
