/**
 * Draws the MJO on Windy's main map: the enhanced / suppressed convective envelopes
 * along the equator, the ensemble-mean track of the envelope centre, the individual
 * ensemble members for the selected day, and (optionally) the 8 phase sectors.
 *
 * The RMM index only tells us *where along the equator* the MJO is, so positions are
 * approximate (see convectionLon in mjo.ts).
 */
import { map } from '@windy/map';

import {
    PHASE_REGIONS,
    amplitude,
    convectionLon,
    formatDate,
    isActive,
    phaseOf,
    phaseSector,
} from './mjo';

import type { MjoState } from './mjo';

export const ENHANCED_COLOR = '#2fd6a0';
export const SUPPRESSED_COLOR = '#ff8a3d';
const TRACK_COLOR = '#ffd166';
const MEMBER_COLOR = '#ffffff';

/** Draw everything at these longitude offsets so wrapped world copies show it too */
const WORLD_COPIES = [-360, 0, 360];

export interface MapRenderOptions {
    showEnvelope: boolean;
    showTrack: boolean;
    showMembers: boolean;
    showSectors: boolean;
    highlightPhase: number | null;
}

/** Shift lon so it is within 180 degrees of `ref` (keeps tracks from jumping across the map) */
const unwrapTo = (lon: number, ref: number): number => {
    let out = lon;
    while (out - ref > 180) {
        out -= 360;
    }
    while (out - ref < -180) {
        out += 360;
    }
    return out;
};

/** Single-ring polygon covering a lat/lon box */
const rect = (lat0: number, lat1: number, lon0: number, lon1: number): L.LatLngExpression[][] => [
    [
        [lat0, lon0],
        [lat1, lon0],
        [lat1, lon1],
        [lat0, lon1],
    ],
];

/** Small round HTML marker; unlike Leaflet GL circle markers these support tooltips */
const dot = (
    latlng: L.LatLngExpression,
    size: number,
    fill: string,
    border: string,
    opacity: number,
    tooltip: string,
): L.Marker =>
    new L.Marker(latlng, {
        icon: new L.DivIcon({
            className: 'mjo-map-label-icon',
            html:
                `<div class="mjo-dot" style="width:${size}px;height:${size}px;` +
                `background:${fill};border-color:${border};opacity:${opacity}"></div>`,
            iconSize: [size, size],
            iconAnchor: [size / 2, size / 2],
        }),
    }).bindTooltip(tooltip);

export class MjoMapLayer {
    private group: L.LayerGroup;

    constructor() {
        this.group = new L.LayerGroup([]);
        this.group.addTo(map);
    }

    clear(): void {
        this.group.clearLayers();
    }

    destroy(): void {
        this.group.clearLayers();
        this.group.remove();
    }

    /**
     * @param state  state to show (analysis day or forecast day)
     * @param track  ensemble-mean states from the latest analysis through the forecast
     */
    render(state: MjoState | null, track: MjoState[], opts: MapRenderOptions): void {
        try {
            this.draw(state, track, opts);
        } catch (e) {
            // a drawing problem must never break the plugin pane
            console.error('windy-plugin-mjo: map overlay failed', e);
        }
    }

    private draw(state: MjoState | null, track: MjoState[], opts: MapRenderOptions): void {
        this.clear();

        if (opts.showSectors || opts.highlightPhase) {
            this.drawSectors(opts.showSectors, opts.highlightPhase);
        }
        if (!state) {
            return;
        }
        if (opts.showEnvelope) {
            this.drawEnvelopes(state);
        }
        if (opts.showTrack && track.length > 1) {
            this.drawTrack(track, state.date);
        }
        if (opts.showMembers && state.members) {
            this.drawMembers(state.members);
        }
    }

    private add(layer: L.Layer): void {
        this.group.addLayer(layer);
    }

    private drawEnvelopes(state: MjoState): void {
        const { x, y } = state;
        const amp = amplitude(x, y);
        const active = isActive(x, y);
        const phase = phaseOf(x, y);
        const centre = convectionLon(x, y);
        // stronger MJO -> more opaque envelope
        const strength = Math.min(amp, 3) / 3;
        const base = active ? 0.08 + 0.1 * strength : 0.06;
        const dashArray = active ? undefined : '6 6';

        const tooltip =
            `<b>MJO phase ${phase}</b> – ${PHASE_REGIONS[phase]}<br>` +
            `Amplitude ${amp.toFixed(2)}${active ? '' : ' (weak)'}<br>` +
            `${formatDate(state.date)} · ${state.kind === 'forecast' ? 'GEFS ensemble mean' : 'analysis'}`;

        const envelopes: [number, string, string][] = [
            [centre, ENHANCED_COLOR, 'Enhanced convection'],
            [centre + 180, SUPPRESSED_COLOR, 'Suppressed convection'],
        ];

        for (const offset of WORLD_COPIES) {
            for (const [lon, color, label] of envelopes) {
                const c = unwrapTo(lon, 0) + offset;
                // three nested boxes give a soft-edged envelope
                [42, 28, 14].forEach((half, i) => {
                    const poly = new L.Polygon(rect(-15 + i * 2, 15 - i * 2, c - half, c + half), {
                        stroke: i === 0,
                        color,
                        weight: 1,
                        opacity: active ? 0.7 : 0.45,
                        dashArray,
                        fill: true,
                        fillColor: color,
                        fillOpacity: base,
                        interactive: i === 2,
                    });
                    if (i === 2) {
                        // Leaflet GL vector layers support popups, not tooltips
                        poly.bindPopup(`${label}<br>${tooltip}`);
                    }
                    this.add(poly);
                });
            }

            const c = unwrapTo(centre, 0) + offset;
            const label =
                `<div class="mjo-map-label${active ? '' : ' mjo-map-label--weak'}">` +
                `<b>MJO ${phase}</b> <span>${amp.toFixed(1)}</span>` +
                `<small>${PHASE_REGIONS[phase]}</small></div>`;
            this.add(
                new L.Marker([19, c], {
                    icon: new L.DivIcon({
                        className: 'mjo-map-label-icon',
                        html: label,
                        iconSize: [150, 40],
                        iconAnchor: [75, 40],
                    }),
                    interactive: false,
                }),
            );

            const s = unwrapTo(centre + 180, 0) + offset;
            this.add(
                new L.Marker([-17, s], {
                    icon: new L.DivIcon({
                        className: 'mjo-map-label-icon',
                        html: '<div class="mjo-map-label mjo-map-label--suppressed">suppressed</div>',
                        iconSize: [100, 20],
                        iconAnchor: [50, 0],
                    }),
                    interactive: false,
                }),
            );
        }
    }

    private drawTrack(track: MjoState[], selectedDate: string): void {
        const lat = -19;
        const lons: number[] = [];
        for (const s of track) {
            const lon = convectionLon(s.x, s.y);
            lons.push(lons.length ? unwrapTo(lon, lons[lons.length - 1]) : unwrapTo(lon, 0));
        }
        const firstForecast = track.findIndex(s => s.kind === 'forecast');

        for (const offset of WORLD_COPIES) {
            const pts = lons.map(lon => [lat, lon + offset] as L.LatLngExpression);
            this.add(
                new L.Polyline(pts, {
                    color: TRACK_COLOR,
                    weight: 2,
                    opacity: 0.85,
                    dashArray: '4 4',
                    interactive: false,
                }),
            );
            track.forEach((s, i) => {
                const selected = s.date === selectedDate;
                const lead = firstForecast >= 0 && i >= firstForecast ? i - firstForecast : null;
                this.add(
                    dot(
                        [lat, lons[i] + offset],
                        selected ? 12 : 8,
                        s.kind === 'forecast' ? TRACK_COLOR : ENHANCED_COLOR,
                        selected ? '#ffffff' : TRACK_COLOR,
                        1,
                        `${formatDate(s.date)}${lead !== null ? ` (day +${lead})` : ' (analysis)'}<br>` +
                            `Phase ${phaseOf(s.x, s.y)}, amplitude ${amplitude(s.x, s.y).toFixed(2)}`,
                    ),
                );
            });
        }
    }

    private drawMembers(members: [number, number][]): void {
        for (const offset of WORLD_COPIES) {
            members.forEach(([x, y], i) => {
                const lon = unwrapTo(convectionLon(x, y), 0) + offset;
                // spread the dots a little in latitude so overlapping members stay visible
                const lat = -6 + ((i * 7) % 13);
                this.add(
                    dot(
                        [lat, lon],
                        6,
                        isActive(x, y) ? ENHANCED_COLOR : '#888888',
                        MEMBER_COLOR,
                        isActive(x, y) ? 0.9 : 0.5,
                        `Member ${i === 0 ? 'control' : i}: phase ${phaseOf(x, y)}, amp ${amplitude(x, y).toFixed(2)}`,
                    ),
                );
            });
        }
    }

    private drawSectors(showAll: boolean, highlight: number | null): void {
        for (const offset of WORLD_COPIES) {
            for (let phase = 1; phase <= 8; phase++) {
                const [w, e] = phaseSector(phase);
                const isHighlighted = phase === highlight;
                if (!showAll && !isHighlighted) {
                    continue;
                }
                this.add(
                    new L.Polygon(rect(-25, 25, w + offset, e + offset), {
                        color: '#ffffff',
                        weight: isHighlighted ? 2 : 1,
                        opacity: isHighlighted ? 0.9 : 0.35,
                        dashArray: isHighlighted ? undefined : '2 6',
                        fill: isHighlighted,
                        fillColor: '#ffffff',
                        fillOpacity: 0.08,
                        interactive: false,
                    }),
                );
                this.add(
                    new L.Marker([27, (w + e) / 2 + offset], {
                        icon: new L.DivIcon({
                            className: 'mjo-map-label-icon',
                            html: `<div class="mjo-sector-label${isHighlighted ? ' mjo-sector-label--on' : ''}">${phase}</div>`,
                            iconSize: [24, 24],
                            iconAnchor: [12, 12],
                        }),
                        interactive: false,
                    }),
                );
            }
        }
    }
}
