<div class="plugin__mobile-header">
    {title}
</div>
<section class="plugin__content mjo">
    <div
        class="plugin__title plugin__title--chevron-back"
        on:click={() => bcast.emit('rqstOpen', 'menu')}
    >
        {title}
    </div>

    {#if loading}
        <div class="mjo-msg">Loading MJO data…</div>
    {:else if error}
        <div class="mjo-msg mjo-msg--error">
            Could not load MJO data.<br />
            <small>{error}</small>
        </div>
    {/if}

    {#if data && latest}
        <!-- current state -->
        <div class="status">
            <div class="status__phase" class:status__phase--weak={!isActive(latest.x, latest.y)}>
                <span class="status__num">{phaseOf(latest.x, latest.y)}</span>
                <span class="status__lbl">phase</span>
            </div>
            <div class="status__text">
                <div class="size-l">
                    {PHASE_REGIONS[phaseOf(latest.x, latest.y)]}
                </div>
                <div class="size-s">
                    Amplitude <b>{amplitude(latest.x, latest.y).toFixed(2)}</b>
                    {isActive(latest.x, latest.y) ? '· active MJO' : '· weak / inactive'}
                </div>
                <div class="size-xs muted">Analysis for {formatDate(latest.date)}</div>
            </div>
        </div>

        {#if lastForecast}
            {@const share = memberPhaseShares(lastForecast.members || [])}
            {@const top = share.phases.indexOf(Math.max(...share.phases))}
            <div class="outlook size-s">
                Day +{data.forecast.dates.length - 1} ({formatDate(lastForecast.date)}): ensemble mean phase
                <b>{phaseOf(lastForecast.x, lastForecast.y)}</b>,
                amp {amplitude(lastForecast.x, lastForecast.y).toFixed(1)} ·
                {Math.round(share.phases[top] * 100)}% of members in phase {top}
                {#if share.weak > 0.05}· {Math.round(share.weak * 100)}% weak{/if}
            </div>
        {/if}

        <PhaseDiagram
            {data}
            {timeline}
            selectedDate={selected?.date || null}
            {historyDays}
            {showMembers}
            showMean={showTrack}
            {showSpread}
            {showBom}
            {highlightPhase}
            on:select={e => selectDate(e.detail, true)}
            on:phase={e => (highlightPhase = e.detail)}
        />

        <!-- day selector -->
        {#if selected}
            <div class="day">
                <button class="day__btn" on:click={() => step(-1)} disabled={selectedIndex <= firstSliderIndex}>‹</button>
                <div class="day__mid">
                    <input
                        type="range"
                        min={firstSliderIndex}
                        max={timeline.length - 1}
                        value={selectedIndex}
                        on:input={e => selectIndex(+e.currentTarget.value, true)}
                    />
                    <div class="day__label size-s">
                        <b>{formatDate(selected.date)}</b>
                        {#if selected.kind === 'forecast'}
                            · GEFS day +{data.forecast.dates.indexOf(selected.date)}
                        {:else}
                            · analysis
                        {/if}
                        · phase {phaseOf(selected.x, selected.y)}, amp {amplitude(selected.x, selected.y).toFixed(2)}
                    </div>
                </div>
                <button class="day__btn" on:click={() => step(1)} disabled={selectedIndex >= timeline.length - 1}>›</button>
            </div>

            {#if selected.members}
                {@const share = memberPhaseShares(selected.members)}
                <div class="probs" title="Share of the {selected.members.length} ensemble members in each phase">
                    {#each [1, 2, 3, 4, 5, 6, 7, 8] as p}
                        <div class="probs__cell" class:probs__cell--hl={p === highlightPhase}>
                            <div class="probs__bar" style:height="{Math.round(share.phases[p] * 100)}%" />
                            <span>{p}</span>
                        </div>
                    {/each}
                    <div class="probs__weak size-xxs">
                        {Math.round(share.weak * 100)}%<br />weak
                    </div>
                </div>
            {/if}
        {/if}

        <!-- options -->
        <div class="opts size-s">
            <label><input type="checkbox" bind:checked={syncTimeline} /> Follow Windy timeline</label>
            <label><input type="checkbox" bind:checked={showEnvelope} /> Envelope on map</label>
            <label><input type="checkbox" bind:checked={showTrack} /> Ensemble mean</label>
            <label><input type="checkbox" bind:checked={showMembers} /> Ensemble members</label>
            <label><input type="checkbox" bind:checked={showSpread} /> Spread cloud</label>
            <label><input type="checkbox" bind:checked={showSectors} /> Phase regions on map</label>
            <label>
                <input type="checkbox" bind:checked={showBom} disabled={!data.bom.days.length} /> BoM official RMM
            </label>
            <label>
                History
                <select bind:value={historyDays}>
                    {#each [20, 40, 60, 90] as n}
                        <option value={n}>{n} days</option>
                    {/each}
                </select>
            </label>
        </div>

        <div class="legend size-xs">
            <span><i style:background={ENHANCED_COLOR} /> enhanced convection / analysis</span>
            <span><i style:background={SUPPRESSED_COLOR} /> suppressed convection</span>
            <span><i style:background="#ffd166" /> ensemble mean (numbers = day)</span>
            <span><i style:background="#ff9f43" style:opacity="0.6" /> ensemble members</span>
        </div>

        <div class="foot size-xxs">
            GEFS {data.forecast.memberNames.length}-member run {data.forecast.init.replace('T', ' ')} ·
            updated {data.generated.replace('T', ' ')}<br />
            Analysis: {data.analysis.source}{#if data.analysis.olrFilledFrom}
                (OLR from {formatDate(data.analysis.olrFilledFrom)} is a GEFS 0–24 h estimate){/if}.
            {#if data.bom.days.length}
                BoM official series ends {formatDate(data.bom.days[data.bom.days.length - 1].d)}.
            {/if}
            Map envelope positions are approximate (derived from the RMM phase angle).
            Click an octant to highlight its region on the map; scroll / drag the diagram to zoom / pan.
        </div>
    {/if}

    <details class="settings size-xs">
        <summary>Data source</summary>
        <input type="text" bind:value={urlInput} placeholder="https://…/mjo.json" />
        <div class="settings__row">
            <button class="button button--variant-orange size-xs" on:click={saveUrl}>Save &amp; reload</button>
            <button class="button size-xs" on:click={resetUrl}>Default</button>
        </div>
        {#if loadedFrom}<div class="muted">Loaded from {loadedFrom}</div>{/if}
    </details>
</section>

<script lang="ts">
    import bcast from '@windy/broadcast';
    import store from '@windy/store';
    import { onDestroy, onMount } from 'svelte';

    import { ENHANCED_COLOR, MjoMapLayer, SUPPRESSED_COLOR } from './mapLayer';
    import {
        PHASE_REGIONS,
        amplitude,
        buildTimeline,
        dayTimestamp,
        formatDate,
        getDataUrl,
        isActive,
        isoDay,
        loadMjoData,
        memberPhaseShares,
        phaseOf,
        setDataUrl,
    } from './mjo';
    import PhaseDiagram from './PhaseDiagram.svelte';
    import config from './pluginConfig';

    import type { MjoData, MjoState } from './mjo';

    const { title } = config;

    let data: MjoData | null = null;
    let timeline: MjoState[] = [];
    let loading = true;
    let error: string | null = null;
    let loadedFrom: string | null = null;
    let urlInput = getDataUrl();

    let selectedIndex = -1;
    let highlightPhase: number | null = null;
    let historyDays = 40;
    let syncTimeline = true;
    let showEnvelope = true;
    let showTrack = true;
    let showMembers = true;
    let showSpread = true;
    let showSectors = false;
    let showBom = false;

    let layer: MjoMapLayer | null = null;
    let timestampListener: number | null = null;

    $: selected = timeline[selectedIndex] || null;
    $: analysis = timeline.filter(s => s.kind === 'analysis');
    $: latest = analysis.length ? analysis[analysis.length - 1] : null;
    $: forecasts = timeline.filter(s => s.kind === 'forecast');
    $: lastForecast = forecasts.length ? forecasts[forecasts.length - 1] : null;
    $: firstSliderIndex = Math.max(0, analysis.length - historyDays);
    $: track = latest ? [latest, ...forecasts] : forecasts;

    // redraw the main-map overlay whenever something relevant changes
    $: if (layer) {
        layer.render(selected, track, {
            showEnvelope,
            showTrack,
            showMembers,
            showSectors,
            highlightPhase,
        });
    }

    // when (re)enabling timeline sync, jump to the timeline's day right away
    $: if (syncTimeline && timeline.length) {
        onTimestamp(store.get('timestamp'));
    }

    async function load() {
        loading = true;
        error = null;
        try {
            const res = await loadMjoData();
            data = res.data;
            loadedFrom = res.url;
            timeline = buildTimeline(data);
            const latestIdx = timeline.findIndex(s => s.kind === 'forecast') - 1;
            selectedIndex = latestIdx >= 0 ? latestIdx : timeline.length - 1;
            if (syncTimeline) {
                onTimestamp(store.get('timestamp'));
            }
        } catch (e) {
            error = (e as Error).message;
        } finally {
            loading = false;
        }
    }

    function selectIndex(i: number, fromUser: boolean) {
        selectedIndex = Math.max(0, Math.min(timeline.length - 1, i));
        const s = timeline[selectedIndex];
        // move Windy's timeline to forecast days (it cannot show past days)
        if (fromUser && syncTimeline && s && s.date >= isoDay(Date.now())) {
            store.set('timestamp', dayTimestamp(s.date));
        }
    }

    function selectDate(date: string, fromUser: boolean) {
        const i = timeline.findIndex(s => s.date === date);
        if (i >= 0) {
            selectIndex(i, fromUser);
        }
    }

    function step(delta: number) {
        selectIndex(selectedIndex + delta, true);
    }

    /** Windy timeline moved: show the MJO state for that (UTC) day */
    function onTimestamp(ts: number) {
        if (!syncTimeline || !timeline.length || !ts) {
            return;
        }
        const day = isoDay(ts);
        let i = timeline.findIndex(s => s.date === day);
        if (i < 0) {
            // beyond the MJO forecast -> last day; before the history -> latest analysis
            i = day > timeline[timeline.length - 1].date ? timeline.length - 1 : selectedIndex;
        }
        if (i !== selectedIndex) {
            selectedIndex = i;
        }
    }

    function saveUrl() {
        setDataUrl(urlInput.trim() || null);
        load();
    }

    function resetUrl() {
        setDataUrl(null);
        urlInput = getDataUrl();
        load();
    }

    export const onopen = (_params: unknown) => {
        if (!data && !loading) {
            load();
        }
    };

    onMount(() => {
        layer = new MjoMapLayer();
        timestampListener = store.on('timestamp', onTimestamp);
        load();
    });

    onDestroy(() => {
        if (timestampListener !== null) {
            store.off(timestampListener);
        }
        layer?.destroy();
        layer = null;
    });
</script>

<style lang="less">
    .mjo {
        .muted {
            opacity: 0.6;
        }
        button:disabled {
            opacity: 0.3;
        }
    }
    .mjo-msg {
        padding: 12px 0;
        &--error {
            color: #ff8a80;
            small {
                display: block;
                margin-top: 4px;
                opacity: 0.8;
                word-break: break-all;
            }
        }
    }
    .status {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 8px;
        &__phase {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            width: 58px;
            height: 58px;
            flex: 0 0 58px;
            border-radius: 50%;
            background: #2fd6a0;
            color: #0d1a14;
            &--weak {
                background: #6b7480;
                color: #fff;
            }
        }
        &__num {
            font-size: 26px;
            font-weight: bold;
            line-height: 1;
        }
        &__lbl {
            font-size: 9px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        &__text {
            line-height: 1.5;
        }
    }
    .outlook {
        margin-bottom: 10px;
        padding: 6px 8px;
        border-left: 3px solid #ffd166;
        background: rgba(255, 209, 102, 0.08);
        line-height: 1.5;
    }
    .day {
        display: flex;
        align-items: center;
        gap: 6px;
        margin: 10px 0 6px;
        &__mid {
            flex: 1;
            input {
                width: 100%;
            }
        }
        &__label {
            text-align: center;
        }
        &__btn {
            width: 28px;
            height: 28px;
            border: 1px solid rgba(255, 255, 255, 0.3);
            border-radius: 4px;
            background: transparent;
            color: inherit;
            font-size: 18px;
            line-height: 24px;
            cursor: pointer;
        }
    }
    .probs {
        display: flex;
        align-items: flex-end;
        gap: 3px;
        height: 54px;
        margin: 4px 0 10px;
        &__cell {
            position: relative;
            flex: 1;
            height: 100%;
            display: flex;
            flex-direction: column;
            justify-content: flex-end;
            align-items: center;
            span {
                font-size: 10px;
                opacity: 0.7;
            }
            &--hl span {
                opacity: 1;
                font-weight: bold;
            }
        }
        &__bar {
            width: 100%;
            min-height: 1px;
            max-height: calc(100% - 14px);
            background: #ff9f43;
            border-radius: 2px 2px 0 0;
        }
        &__weak {
            width: 36px;
            text-align: center;
            opacity: 0.7;
        }
    }
    .opts {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 4px 10px;
        margin: 8px 0;
        label {
            cursor: pointer;
            white-space: nowrap;
        }
        select {
            margin-left: 4px;
        }
    }
    .legend {
        display: flex;
        flex-wrap: wrap;
        gap: 4px 12px;
        margin: 8px 0;
        opacity: 0.85;
        i {
            display: inline-block;
            width: 10px;
            height: 10px;
            margin-right: 4px;
            border-radius: 2px;
            vertical-align: -1px;
        }
    }
    .foot {
        margin-top: 8px;
        line-height: 1.5;
        opacity: 0.6;
    }
    .settings {
        margin-top: 10px;
        summary {
            cursor: pointer;
            opacity: 0.7;
        }
        input {
            width: 100%;
            margin: 6px 0;
        }
        &__row {
            display: flex;
            gap: 6px;
            margin-bottom: 4px;
        }
    }

    /* labels drawn on the main Windy map (outside this component's DOM) */
    :global(.mjo-map-label-icon) {
        background: none;
        border: none;
    }
    :global(.mjo-map-label) {
        display: inline-block;
        position: relative;
        left: 50%;
        transform: translateX(-50%);
        padding: 3px 7px;
        border-radius: 4px;
        background: rgba(13, 26, 20, 0.85);
        border: 1px solid #2fd6a0;
        color: #fff;
        font-size: 12px;
        line-height: 1.3;
        text-align: center;
        white-space: nowrap;
        text-shadow: none;
    }
    :global(.mjo-map-label span) {
        color: #2fd6a0;
    }
    :global(.mjo-map-label small) {
        display: block;
        font-size: 10px;
        opacity: 0.8;
    }
    :global(.mjo-map-label--weak) {
        border-style: dashed;
        border-color: #9aa3ad;
    }
    :global(.mjo-map-label--suppressed) {
        border-color: #ff8a3d;
        color: #ffcfae;
        font-size: 10px;
        padding: 1px 6px;
    }
    :global(.mjo-sector-label) {
        width: 24px;
        height: 24px;
        border-radius: 50%;
        background: rgba(0, 0, 0, 0.55);
        border: 1px solid rgba(255, 255, 255, 0.5);
        color: #fff;
        font-size: 13px;
        font-weight: bold;
        line-height: 22px;
        text-align: center;
    }
    :global(.mjo-sector-label--on) {
        background: #fff;
        color: #000;
    }
</style>
