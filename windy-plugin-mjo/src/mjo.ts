/**
 * MJO data model + RMM helpers shared by the phase diagram and the map layer.
 */

/** Where the daily pipeline publishes its output (GitHub Pages of this repo). */
export const DEFAULT_DATA_URL = 'https://kauswai.github.io/MJO/mjo.json';

/** Served by `npm start` (rollup dev server) from public/mjo.json */
export const DEV_DATA_URL = 'https://localhost:9999/mjo.json';

const DATA_URL_STORAGE_KEY = 'windy-plugin-mjo:data-url';

export interface RmmDay {
    d: string; // YYYY-MM-DD
    x: number; // RMM1
    y: number; // RMM2
}

export interface MjoData {
    version: number;
    generated: string;
    analysis: { source: string; olrFilledFrom: string | null; days: RmmDay[] };
    bom: { source: string; days: RmmDay[] };
    forecast: {
        model: string;
        init: string;
        dates: string[];
        memberNames: string[];
        members: [number, number][][];
        mean: [number, number][];
    };
}

/** A single RMM state on a given day, with where it came from. */
export interface MjoState {
    date: string;
    x: number;
    y: number;
    kind: 'analysis' | 'forecast';
    /** Ensemble member positions, forecast days only */
    members?: [number, number][];
}

export const PHASE_REGIONS: Record<number, string> = {
    1: 'Western Hemisphere & Africa',
    2: 'Indian Ocean',
    3: 'Indian Ocean',
    4: 'Maritime Continent',
    5: 'Maritime Continent',
    6: 'Western Pacific',
    7: 'Western Pacific',
    8: 'Western Hemisphere & Africa',
};

export const amplitude = (x: number, y: number): number => Math.hypot(x, y);

/** RMM phase angle in degrees, -180..180 (atan2 of RMM2, RMM1) */
export const phaseAngle = (x: number, y: number): number => (Math.atan2(y, x) * 180) / Math.PI;

/** Wheeler-Hendon phase 1..8 (octants counted anticlockwise from the negative RMM1 axis) */
export const phaseOf = (x: number, y: number): number =>
    (Math.floor((phaseAngle(x, y) + 180) / 45) % 8) + 1;

export const isActive = (x: number, y: number): boolean => amplitude(x, y) >= 1;

/**
 * Approximate longitude (degrees east, may exceed 180) of the centre of enhanced convection
 * for each phase. The MJO crosses the Western Hemisphere faster, hence the wider 7 -> 8 -> 1 gaps.
 */
const PHASE_CENTRE_LON = [40, 70, 90, 110, 130, 150, 175, 290];

/** Continuous position 0..8 around the diagram; phase k is centred on k - 0.5 */
const phasePosition = (x: number, y: number): number => (phaseAngle(x, y) + 180) / 45;

export const normalizeLon = (lon: number): number => ((((lon + 180) % 360) + 360) % 360) - 180;

/** Approximate centre longitude (-180..180) of the enhanced convective envelope */
export function convectionLon(x: number, y: number): number {
    const p = phasePosition(x, y) - 0.5; // 0 at phase-1 centre ... 7 at phase-8 centre
    const centres = [...PHASE_CENTRE_LON, PHASE_CENTRE_LON[0] + 360];
    const i = Math.floor((p + 8) % 8);
    const f = ((p + 8) % 8) - i;
    return normalizeLon(centres[i] + f * (centres[i + 1] - centres[i]));
}

/** West/east edges of each phase's sector on the map (between neighbouring phase centres) */
export function phaseSector(phase: number): [number, number] {
    const c = PHASE_CENTRE_LON;
    const i = phase - 1;
    const prev = i === 0 ? c[7] - 360 : c[i - 1];
    const next = i === 7 ? c[0] + 360 : c[i + 1];
    return [(prev + c[i]) / 2, (c[i] + next) / 2];
}

export const formatDate = (iso: string): string => {
    const d = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
    return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', timeZone: 'UTC' });
};

export const isoDay = (ts: number): string => new Date(ts).toISOString().slice(0, 10);

export const dayTimestamp = (iso: string): number => Date.parse(`${iso.slice(0, 10)}T12:00:00Z`);

export function getDataUrl(): string {
    try {
        return localStorage.getItem(DATA_URL_STORAGE_KEY) || DEFAULT_DATA_URL;
    } catch {
        return DEFAULT_DATA_URL;
    }
}

export function setDataUrl(url: string | null): void {
    try {
        if (url) {
            localStorage.setItem(DATA_URL_STORAGE_KEY, url);
        } else {
            localStorage.removeItem(DATA_URL_STORAGE_KEY);
        }
    } catch {
        /* storage not available */
    }
}

/** Loads mjo.json from the configured URL, falling back to the local dev server. */
export async function loadMjoData(): Promise<{ data: MjoData; url: string }> {
    const urls = [getDataUrl()];
    if (!urls.includes(DEV_DATA_URL)) {
        urls.push(DEV_DATA_URL);
    }
    let lastError: unknown = null;
    for (const url of urls) {
        if (url.includes('YOUR-GITHUB-USER')) {
            continue;
        }
        try {
            // bust caches once an hour; the pipeline runs daily
            const bust = Math.floor(Date.now() / 3.6e6);
            const res = await fetch(`${url}${url.includes('?') ? '&' : '?'}h=${bust}`);
            if (!res.ok) {
                throw new Error(`HTTP ${res.status}`);
            }
            const data = (await res.json()) as MjoData;
            if (!data?.forecast?.members || !data?.analysis?.days) {
                throw new Error('Unexpected data format');
            }
            return { data, url };
        } catch (e) {
            lastError = new Error(`${url}: ${(e as Error).message}`);
        }
    }
    throw lastError || new Error('No MJO data URL configured');
}

/** All selectable days: analysis history followed by the forecast days. */
export function buildTimeline(data: MjoData): MjoState[] {
    const out: MjoState[] = data.analysis.days.map(({ d, x, y }) => ({
        date: d,
        x,
        y,
        kind: 'analysis',
    }));
    const lastAnalysis = out.length ? out[out.length - 1].date : '';
    data.forecast.dates.forEach((date, k) => {
        if (date <= lastAnalysis) {
            return;
        }
        const [x, y] = data.forecast.mean[k];
        out.push({
            date,
            x,
            y,
            kind: 'forecast',
            members: data.forecast.members.map(m => m[k]),
        });
    });
    return out;
}

/** Fraction of ensemble members in each phase (and weak) for one forecast day */
export function memberPhaseShares(members: [number, number][]): {
    phases: number[];
    weak: number;
} {
    const phases = new Array(9).fill(0);
    let weak = 0;
    for (const [x, y] of members) {
        if (!isActive(x, y)) {
            weak++;
        }
        phases[phaseOf(x, y)]++;
    }
    const n = members.length || 1;
    return { phases: phases.map(v => v / n), weak: weak / n };
}

/** Andrew's monotone chain convex hull, used for the ensemble spread cloud */
export function convexHull(points: [number, number][]): [number, number][] {
    const pts = [...points].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    if (pts.length < 3) {
        return pts;
    }
    const cross = (o: number[], a: number[], b: number[]) =>
        (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
    const lower: [number, number][] = [];
    for (const p of pts) {
        while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) {
            lower.pop();
        }
        lower.push(p);
    }
    const upper: [number, number][] = [];
    for (const p of pts.reverse()) {
        while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) {
            upper.pop();
        }
        upper.push(p);
    }
    return lower.slice(0, -1).concat(upper.slice(0, -1));
}
