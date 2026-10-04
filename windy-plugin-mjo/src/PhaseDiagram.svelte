<div class="diagram" bind:this={wrapper}>
    <svg
        viewBox="0 0 {S} {S}"
        class:dragging
        on:wheel|preventDefault={onWheel}
        on:pointerdown={onPointerDown}
        on:pointermove={onPointerMove}
        on:pointerup={onPointerUp}
        on:pointercancel={onPointerUp}
        on:pointerleave={() => (hover = null)}
        on:dblclick={resetView}
        role="img"
        aria-label="MJO RMM phase diagram"
    >
        <defs>
            <clipPath id="mjo-clip">
                <rect x="0" y="0" width={S} height={S} rx="6" />
            </clipPath>
        </defs>
        <rect class="bg" x="0" y="0" width={S} height={S} rx="6" />

        <g clip-path="url(#mjo-clip)">
            <!-- phase octants (hover / click to highlight on the map) -->
            {#each PHASES as phase}
                <path
                    class="octant"
                    class:octant--hl={phase === highlightPhase}
                    class:octant--sel={selected && phase === phaseOf(selected.x, selected.y) && isActive(selected.x, selected.y)}
                    d={octantPath(phase, view)}
                    on:click={() => !moved && dispatch('phase', phase === highlightPhase ? null : phase)}
                    on:pointerenter={() => (hoverPhase = phase)}
                    on:pointerleave={() => (hoverPhase = null)}
                />
            {/each}

            <!-- grid -->
            {#each xTicks as t}
                <line class="grid" x1={px(t)} y1="0" x2={px(t)} y2={S} />
            {/each}
            {#each yTicks as t}
                <line class="grid" x1="0" y1={py(t)} x2={S} y2={py(t)} />
            {/each}

            <!-- weak-MJO circle -->
            <circle class="unit" cx={px(0)} cy={py(0)} r={k} />
            <text class="weak-label" x={px(0)} y={py(-1) - 5}>Weak MJO</text>

            <!-- octant boundaries, from the unit circle outwards -->
            {#each [0, 45, 90, 135, 180, 225, 270, 315] as a}
                {@const c = Math.cos((a * Math.PI) / 180)}
                {@const s = Math.sin((a * Math.PI) / 180)}
                <line class="spoke" x1={px(c)} y1={py(s)} x2={px(c * 40)} y2={py(s * 40)} />
            {/each}

            <!-- phase numbers -->
            {#each PHASES as phase}
                {@const a = ((-180 + 45 * (phase - 0.5)) * Math.PI) / 180}
                <text
                    class="phase-num"
                    class:phase-num--hl={phase === highlightPhase || phase === hoverPhase}
                    x={px(Math.cos(a) * labelRadius)}
                    y={py(Math.sin(a) * labelRadius) + 6}
                >
                    {phase}
                </text>
            {/each}

            <!-- official BoM series -->
            {#if showBom && bomTrack.length > 1}
                <polyline class="bom" points={pointsAttr(bomTrack)} />
            {/if}

            <!-- ensemble members -->
            {#if showMembers}
                {#each memberTracks as track, m}
                    <polyline class="member" points={pointsAttr(track)} />
                    {#if selectedForecastIdx !== null && track[selectedForecastIdx + 1]}
                        {@const p = track[selectedForecastIdx + 1]}
                        <circle
                            class="member-dot"
                            cx={px(p[0])}
                            cy={py(p[1])}
                            r="3"
                            on:pointerenter={e => showTip(e, memberTip(m, selectedForecastIdx, p))}
                            on:pointerleave={() => (hover = null)}
                        />
                    {/if}
                {/each}
            {/if}

            <!-- spread cloud for the selected (or last) forecast day -->
            {#if showSpread && spreadHull.length > 2}
                <polygon class="spread" points={pointsAttr(spreadHull)} />
            {/if}

            <!-- analysis history -->
            {#each historySegments as seg}
                <line
                    class="hist"
                    x1={px(seg.a.x)}
                    y1={py(seg.a.y)}
                    x2={px(seg.b.x)}
                    y2={py(seg.b.y)}
                    style:opacity={seg.opacity}
                />
            {/each}
            {#each history as s, i}
                {@const isMonthStart = s.date.endsWith('-01')}
                <circle
                    class="hist-dot"
                    class:hist-dot--month={isMonthStart}
                    cx={px(s.x)}
                    cy={py(s.y)}
                    r={isMonthStart ? 4 : 2.5}
                    style:opacity={0.35 + (0.65 * (i + 1)) / history.length}
                    on:pointerenter={e => showTip(e, stateTip(s))}
                    on:pointerleave={() => (hover = null)}
                    on:click={() => !moved && dispatch('select', s.date)}
                />
                {#if isMonthStart || i === 0}
                    <text class="date-label" x={px(s.x) + 6} y={py(s.y) - 6}>{formatDate(s.date)}</text>
                {/if}
            {/each}

            <!-- ensemble mean -->
            {#if showMean && meanTrack.length > 1}
                <polyline class="mean" points={pointsAttr(meanTrack.map(s => [s.x, s.y]))} />
                {#each meanTrack.slice(1) as s, i}
                    <g
                        class="mean-dot"
                        on:pointerenter={e => showTip(e, stateTip(s))}
                        on:pointerleave={() => (hover = null)}
                        on:click={() => !moved && dispatch('select', s.date)}
                    >
                        <circle cx={px(s.x)} cy={py(s.y)} r="7" />
                        <text x={px(s.x)} y={py(s.y) + 3.5}>{leadOf(s.date) ?? i}</text>
                    </g>
                {/each}
            {/if}

            <!-- latest analysis ("now") -->
            {#if latest}
                <circle class="now-halo" cx={px(latest.x)} cy={py(latest.y)} r="11" />
                <circle
                    class="now"
                    cx={px(latest.x)}
                    cy={py(latest.y)}
                    r="6"
                    on:pointerenter={e => showTip(e, stateTip(latest))}
                    on:pointerleave={() => (hover = null)}
                    on:click={() => !moved && latest && dispatch('select', latest.date)}
                />
            {/if}

            <!-- selected day -->
            {#if selected && selected !== latest}
                <circle class="selected-ring" cx={px(selected.x)} cy={py(selected.y)} r="11" />
            {/if}
        </g>

        <!-- region labels (screen space) -->
        <text class="region" x={S / 2} y="16">Western Pacific</text>
        <text class="region" x={S / 2} y={S - 8}>Indian Ocean</text>
        <text class="region" transform="translate(14 {S / 2}) rotate(-90)">West. Hem. &amp; Africa</text>
        <text class="region" transform="translate({S - 10} {S / 2}) rotate(90)">Maritime Continent</text>
        <text class="axis" x={S - 34} y={py(0) - 5}>RMM1</text>
        <text class="axis" x={px(0) + 5} y="34">RMM2</text>
    </svg>

    <div class="zoom">
        <button on:click={() => zoom(0.8)} title="Zoom in">+</button>
        <button on:click={() => zoom(1.25)} title="Zoom out">−</button>
        <button on:click={resetView} title="Reset view">⟲</button>
    </div>

    {#if hover}
        <div class="tip" style:left="{hover.left}px" style:top="{hover.top}px">
            {@html hover.html}
        </div>
    {/if}
</div>

<script lang="ts">
    import { createEventDispatcher } from 'svelte';

    import {
        PHASE_REGIONS,
        amplitude,
        convexHull,
        formatDate,
        isActive,
        phaseOf,
    } from './mjo';

    import type { MjoData, MjoState, RmmDay } from './mjo';

    export let data: MjoData;
    export let timeline: MjoState[];
    export let selectedDate: string | null = null;
    export let historyDays = 40;
    export let showMembers = true;
    export let showMean = true;
    export let showSpread = true;
    export let showBom = false;
    export let highlightPhase: number | null = null;

    const dispatch = createEventDispatcher<{ select: string; phase: number | null }>();

    const S = 400; // svg user units
    const PHASES = [1, 2, 3, 4, 5, 6, 7, 8];
    let wrapper: HTMLDivElement;
    let view = { cx: 0, cy: 0, r: 4 };
    let userMovedView = false;
    let hover: { left: number; top: number; html: string } | null = null;
    let hoverPhase: number | null = null;

    // ---- coordinate transforms (data units -> svg units)
    $: k = S / 2 / view.r;
    $: px = (x: number) => S / 2 + (x - view.cx) * k;
    $: py = (y: number) => S / 2 - (y - view.cy) * k;
    $: labelRadius = Math.max(1.6, Math.min(3.4, view.r * 0.82));
    $: xTicks = ticks(view.cx - view.r, view.cx + view.r);
    $: yTicks = ticks(view.cy - view.r, view.cy + view.r);
    $: pointsAttr = (pts: [number, number][]) => pts.map(([x, y]) => `${px(x)},${py(y)}`).join(' ');

    function ticks(a: number, b: number): number[] {
        const out = [];
        for (let t = Math.ceil(a); t <= Math.floor(b); t++) {
            if (t !== 0) {
                out.push(t);
            }
        }
        return out;
    }

    // ---- derived data
    $: analysis = timeline.filter(s => s.kind === 'analysis');
    $: latest = analysis.length ? analysis[analysis.length - 1] : null;
    $: history = analysis.slice(-historyDays);
    $: historySegments = history.slice(1).map((b, i) => ({
        a: history[i],
        b,
        opacity: 0.25 + (0.75 * (i + 1)) / history.length,
    }));
    $: forecastStates = timeline.filter(s => s.kind === 'forecast');
    $: meanTrack = latest ? [latest, ...forecastStates] : forecastStates;
    $: memberTracks = buildMemberTracks(data, latest);
    $: selected = timeline.find(s => s.date === selectedDate) || latest;
    $: selectedForecastIdx = selected && selected.kind === 'forecast' ? forecastStates.indexOf(selected) : null;
    $: spreadHull = forecastStates.length
        ? convexHull(
              (selectedForecastIdx !== null
                  ? forecastStates[selectedForecastIdx]
                  : forecastStates[forecastStates.length - 1]
              ).members || [],
          )
        : [];
    $: bomTrack = bomPoints(data.bom.days, history[0]?.date);

    // fit the default view to what is drawn (classic +-4 square when the MJO is strong)
    $: defaultView = fitView(history, memberTracks);
    $: if (!userMovedView) {
        view = { ...defaultView };
    }

    function fitView(hist: MjoState[], tracks: [number, number][][]) {
        let m = 1;
        for (const s of hist) {
            m = Math.max(m, Math.abs(s.x), Math.abs(s.y));
        }
        for (const t of tracks) {
            for (const [x, y] of t) {
                m = Math.max(m, Math.abs(x), Math.abs(y));
            }
        }
        return { cx: 0, cy: 0, r: Math.min(4.5, Math.max(2.2, Math.ceil((m + 0.4) * 2) / 2)) };
    }

    function buildMemberTracks(d: MjoData, last: MjoState | null): [number, number][][] {
        const lastDate = last?.date || '';
        const keep = d.forecast.dates.map((date, i) => (date > lastDate ? i : -1)).filter(i => i >= 0);
        return d.forecast.members.map(m => {
            const pts = keep.map(i => m[i]);
            return last ? [[last.x, last.y] as [number, number], ...pts] : pts;
        });
    }

    function bomPoints(days: RmmDay[], from: string | undefined): [number, number][] {
        return days.filter(d => !from || d.d >= from).map(d => [d.x, d.y]);
    }

    function octantPath(phase: number, _v: typeof view): string {
        const a0 = -180 + 45 * (phase - 1);
        const pts: string[] = [];
        for (let a = a0; a <= a0 + 45; a += 5) {
            const r = (a * Math.PI) / 180;
            pts.push(`${px(Math.cos(r))},${py(Math.sin(r))}`);
        }
        for (const a of [a0 + 45, a0]) {
            const r = (a * Math.PI) / 180;
            pts.push(`${px(Math.cos(r) * 60)},${py(Math.sin(r) * 60)}`);
        }
        return `M${pts.join('L')}Z`;
    }

    function leadOf(date: string): number | null {
        const i = data.forecast.dates.indexOf(date);
        return i >= 0 ? i : null;
    }

    function stateTip(s: MjoState): string {
        const amp = amplitude(s.x, s.y);
        const phase = phaseOf(s.x, s.y);
        const lead = leadOf(s.date);
        const kind = s.kind === 'forecast' ? `GEFS mean, day +${lead}` : 'Analysis';
        return (
            `<b>${formatDate(s.date)}</b> · ${kind}<br>` +
            `Phase <b>${phase}</b> ${isActive(s.x, s.y) ? '' : '(weak)'}<br>` +
            `<small>${PHASE_REGIONS[phase]}</small><br>` +
            `Amplitude ${amp.toFixed(2)}<br>` +
            `RMM1 ${s.x.toFixed(2)} · RMM2 ${s.y.toFixed(2)}`
        );
    }

    function memberTip(m: number, idx: number, p: [number, number]): string {
        const name = data.forecast.memberNames[m] || `m${m}`;
        return (
            `<b>${name === 'gec00' ? 'Control' : `Member ${name.slice(3)}`}</b> · ${formatDate(forecastStates[idx].date)}<br>` +
            `Phase ${phaseOf(p[0], p[1])}, amp ${amplitude(p[0], p[1]).toFixed(2)}`
        );
    }

    function showTip(e: PointerEvent, html: string) {
        const box = wrapper.getBoundingClientRect();
        const left = Math.min(e.clientX - box.left + 12, box.width - 170);
        const top = Math.max(e.clientY - box.top - 10, 0);
        hover = { left, top, html };
    }

    // ---- zoom & pan
    let dragging = false;
    let moved = false;
    let dragStart: { x: number; y: number; cx: number; cy: number } | null = null;

    const clampR = (r: number) => Math.max(0.8, Math.min(8, r));

    function zoom(f: number) {
        userMovedView = true;
        view = { ...view, r: clampR(view.r * f) };
    }

    function resetView() {
        userMovedView = false;
        view = { ...defaultView };
    }

    function svgScale(): number {
        return S / wrapper.getBoundingClientRect().width;
    }

    function onWheel(e: WheelEvent) {
        const box = wrapper.getBoundingClientRect();
        const sx = (e.clientX - box.left) * svgScale();
        const sy = (e.clientY - box.top) * svgScale();
        // keep the data point under the cursor fixed
        const dx = view.cx + (sx - S / 2) / k;
        const dy = view.cy - (sy - S / 2) / k;
        userMovedView = true;
        const r = clampR(view.r * (e.deltaY > 0 ? 1.15 : 1 / 1.15));
        const nk = S / 2 / r;
        view = { r, cx: dx - (sx - S / 2) / nk, cy: dy + (sy - S / 2) / nk };
    }

    function onPointerDown(e: PointerEvent) {
        dragStart = { x: e.clientX, y: e.clientY, cx: view.cx, cy: view.cy };
        moved = false;
    }

    function onPointerMove(e: PointerEvent) {
        if (!dragStart) {
            return;
        }
        const dx = (e.clientX - dragStart.x) * svgScale();
        const dy = (e.clientY - dragStart.y) * svgScale();
        if (!moved && Math.hypot(dx, dy) < 4) {
            return;
        }
        moved = true;
        dragging = true;
        userMovedView = true;
        hover = null;
        view = { ...view, cx: dragStart.cx - dx / k, cy: dragStart.cy + dy / k };
    }

    function onPointerUp() {
        dragStart = null;
        dragging = false;
        // `moved` stays true until the click event that follows this pointerup has fired
        setTimeout(() => (moved = false), 0);
    }
</script>

<style lang="less">
    .diagram {
        position: relative;
        width: 100%;
        max-width: 420px;
        margin: 0 auto;
        user-select: none;
    }
    svg {
        display: block;
        width: 100%;
        height: auto;
        touch-action: none;
        cursor: grab;
        &.dragging {
            cursor: grabbing;
        }
    }
    .bg {
        fill: #10151c;
        stroke: rgba(255, 255, 255, 0.15);
    }
    .octant {
        fill: transparent;
        cursor: pointer;
        &:hover {
            fill: rgba(255, 255, 255, 0.05);
        }
        &--sel {
            fill: rgba(47, 214, 160, 0.08);
        }
        &--hl {
            fill: rgba(255, 255, 255, 0.13);
        }
    }
    .grid {
        stroke: rgba(255, 255, 255, 0.05);
        stroke-width: 1;
    }
    .unit {
        fill: rgba(255, 255, 255, 0.06);
        stroke: rgba(255, 255, 255, 0.45);
        stroke-width: 1;
        pointer-events: none;
    }
    .weak-label {
        fill: rgba(255, 255, 255, 0.35);
        font-size: 10px;
        text-anchor: middle;
        pointer-events: none;
    }
    .spoke {
        stroke: rgba(255, 255, 255, 0.35);
        stroke-width: 1;
        stroke-dasharray: 3 4;
        pointer-events: none;
    }
    .phase-num {
        fill: rgba(255, 255, 255, 0.45);
        font-size: 18px;
        font-weight: bold;
        text-anchor: middle;
        pointer-events: none;
        &--hl {
            fill: #fff;
        }
    }
    .region,
    .axis {
        fill: rgba(255, 255, 255, 0.6);
        font-size: 11px;
        text-anchor: middle;
        pointer-events: none;
    }
    .axis {
        font-size: 9px;
        fill: rgba(255, 255, 255, 0.35);
        text-anchor: start;
    }
    .bom {
        fill: none;
        stroke: #b9c4d0;
        stroke-width: 1.5;
        stroke-dasharray: 5 4;
        opacity: 0.7;
        pointer-events: none;
    }
    .member {
        fill: none;
        stroke: #ff9f43;
        stroke-width: 1;
        opacity: 0.35;
        pointer-events: none;
    }
    .member-dot {
        fill: #ff9f43;
        stroke: #10151c;
        stroke-width: 0.5;
        opacity: 0.9;
    }
    .spread {
        fill: rgba(255, 159, 67, 0.12);
        stroke: rgba(255, 159, 67, 0.5);
        stroke-width: 1;
        pointer-events: none;
    }
    .hist {
        stroke: #2fd6a0;
        stroke-width: 2.5;
        stroke-linecap: round;
        pointer-events: none;
    }
    .hist-dot {
        fill: #2fd6a0;
        cursor: pointer;
        &--month {
            fill: #fff;
            stroke: #2fd6a0;
            stroke-width: 1.5;
        }
    }
    .date-label {
        fill: rgba(255, 255, 255, 0.7);
        font-size: 10px;
        pointer-events: none;
    }
    .mean {
        fill: none;
        stroke: #ffd166;
        stroke-width: 3;
        stroke-linejoin: round;
        pointer-events: none;
    }
    .mean-dot {
        cursor: pointer;
        circle {
            fill: #ffd166;
            stroke: #10151c;
            stroke-width: 1;
        }
        text {
            fill: #10151c;
            font-size: 9px;
            font-weight: bold;
            text-anchor: middle;
            pointer-events: none;
        }
    }
    .now-halo {
        fill: rgba(47, 214, 160, 0.25);
        pointer-events: none;
    }
    .now {
        fill: #fff;
        stroke: #2fd6a0;
        stroke-width: 3;
        cursor: pointer;
    }
    .selected-ring {
        fill: none;
        stroke: #fff;
        stroke-width: 2;
        pointer-events: none;
    }
    .zoom {
        position: absolute;
        right: 6px;
        bottom: 22px;
        display: flex;
        flex-direction: column;
        gap: 3px;
        button {
            width: 24px;
            height: 24px;
            padding: 0;
            border: 1px solid rgba(255, 255, 255, 0.25);
            border-radius: 4px;
            background: rgba(16, 21, 28, 0.85);
            color: #fff;
            font-size: 14px;
            line-height: 20px;
            cursor: pointer;
            &:hover {
                background: rgba(255, 255, 255, 0.15);
            }
        }
    }
    .tip {
        position: absolute;
        z-index: 2;
        min-width: 150px;
        padding: 6px 8px;
        border-radius: 4px;
        background: rgba(0, 0, 0, 0.88);
        color: #fff;
        font-size: 11px;
        line-height: 1.45;
        pointer-events: none;
        :global(small) {
            opacity: 0.7;
        }
    }
</style>
