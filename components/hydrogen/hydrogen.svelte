<script>
  import { onMount, afterUpdate } from 'svelte';
  import { Chart, registerables } from 'chart.js';

  Chart.register(...registerables);

  export let context;

  let canvas;
  let loading = false;
  let error = null;
  let totalKg = 0;
  let chart = null;
  let period = 'day'; // internal, determined from time range span

  // Time adjustment variables
  let from = '';
  let to = '';
  let isToDate = false;
  let minuteAdjustment = 15;
  let adjustmentTarget = 'from';

  function toggleDateAdjustment() {
    adjustmentTarget = isToDate ? 'to' : 'from';
  }

  function incrementTimeRange() {
    adjustTimeRange(minuteAdjustment);
  }

  function decrementTimeRange() {
    adjustTimeRange(-minuteAdjustment);
  }

  function adjustTimeRange(minutes) {
    const newFrom = new Date(context.timeRange.from);
    const newTo = new Date(context.timeRange.to);

    if (adjustmentTarget === 'from') {
      newFrom.setMinutes(newFrom.getMinutes() + minutes);
    } else {
      newTo.setMinutes(newTo.getMinutes() + minutes);
    }
    context.setTimeRange({ from: newFrom.getTime(), to: newTo.getTime() });
  }


  function formatDisplayDate(isoString) {
    if (!isoString) return '';
    const d = new Date(isoString);
    return d.toLocaleString('en-GB', {
      day: '2-digit', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit'
    });
  }

  const API_BASE = 'https://portal.ixon.cloud:443/api';

  function getHeaders() {
    const inputs = context?.inputs || {};
    return {
      'Content-Type': 'application/json',
      'Api-Version': inputs.apiVersion || '2',
      'Api-Application': inputs.apiApplication || '',
      'Authorization': `Bearer ${inputs.bearerToken || ''}`,
      'Api-Company': inputs.companyId || ''
    };
  }

  function getAgentId() {
    return context?.inputs?.agentId || '';
  }

  function getDataSourceName() {
    return context?.inputs?.dataSourceName || 'Databron-PLC';
  }

  function getTagSlug() {
    return context?.inputs?.tagSlug || 'FT_301';
  }

  async function getDataSourceId(agentId, name) {
    const headers = getHeaders();
    const res = await fetch(
      `${API_BASE}/agents/${agentId}/data-sources?fields=name,publicId`,
      { headers }
    );
    if (!res.ok) throw new Error(`Data source fetch failed: ${res.status}`);
    const data = await res.json();
    const ds = data.data.find(d => d.name === name);
    if (!ds) throw new Error(`Data source "${name}" not found`);
    return ds;
  }

  async function getTagsData(agentId, dataSource, slug) {
    const headers = getHeaders();
    const filter = `eq(source.publicId,"${dataSource.publicId}")`;
    const res = await fetch(
      `${API_BASE}/agents/${agentId}/data-tags?fields=tagId,name,slug&filters=${filter}`,
      { headers }
    );
    if (!res.ok) throw new Error(`Tags fetch failed: ${res.status}`);
    const data = await res.json();
    return data.data.filter(tag => tag.slug === slug);
  }

  async function exportData(dataSource, tags, start, end) {
    const headers = getHeaders();
    const slug = getTagSlug();
    const body = {
      source: { publicId: dataSource.publicId },
      tags: tags.map(tag => ({
        id: tag.tagId,
        preAggr: 'raw',
        queries: [{ ref: tag.slug, offset: 0, order: 'desc' }]
      })),
      start,
      end,
      timeZone: 'UTC'
    };

    const res = await fetch(`${API_BASE}/data-export`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body)
    });

    if (!res.ok) return null;
    return await res.text();
  }

  function parseCSV(csvText, tagSlug) {
      const lines = csvText.trim().split('\n');
      if (lines.length < 2) return [];
      const headers = lines[0].split(',').map(h => h.trim());
      const timeIdx = headers.indexOf('time');
      const ftIdx = headers.indexOf(tagSlug);
      if (timeIdx === -1 || ftIdx === -1) return [];

      const results = [];
      for (let i = 1; i < lines.length; i++) {
          const line = lines[i].trim();
          if (!line) continue;
          const lastComma = line.lastIndexOf(',');
          if (lastComma === -1) continue;
          const time = line.slice(0, lastComma).trim();
          const val = line.slice(lastComma + 1).trim();
          if (time === 'time') continue;
          const flow = parseFloat(val);
          if (isNaN(flow)) continue;
          results.push({ time, flow });
      }

      results.sort((a, b) => new Date(a.time) - new Date(b.time));

      const deduped = {};
      for (const r of results) {
          deduped[r.time] = r;
      }
      return Object.values(deduped);
  }

  function buildChartData(points, startMs, endMs) {
      const SAMPLE_SECONDS = 10;

      if (!points.length) return { labels: [], barData: [], cumData: [] };

      const startTime = new Date(points[0].time).getTime();
      const endTime = new Date(points[points.length - 1].time).getTime();
      const spanMs = endMs - startMs;

      // Align to clean 10-second boundaries
      const alignedStart = Math.floor(startTime / (SAMPLE_SECONDS * 1000)) * (SAMPLE_SECONDS * 1000);

      const resampled = [];
      let ptIdx = 0;
      let lastFlow = 0;

      for (let t = alignedStart; t <= endTime; t += SAMPLE_SECONDS * 1000) {
          while (ptIdx < points.length - 1 && new Date(points[ptIdx + 1].time).getTime() <= t) {
              ptIdx++;
          }
          if (new Date(points[ptIdx].time).getTime() <= t) {
              lastFlow = points[ptIdx].flow;
          }
          resampled.push({ time: t, flow: lastFlow });
      }

      // Determine bucket format based on time span
      let bucketFormat;
      if (spanMs <= 3600 * 1000) {
        // ≤ 1 hour: per minute
        bucketFormat = (t) => new Date(t).toISOString().slice(11, 16);
      } else if (spanMs <= 86400 * 1000) {
        // ≤ 1 day: per hour
        bucketFormat = (t) => new Date(t).toISOString().slice(11, 13) + ':00';
      } else {
        // > 1 day: per day
        bucketFormat = (t) => new Date(t).toISOString().slice(0, 10);
      }

      const barBuckets = {};
      for (const r of resampled) {
          const label = bucketFormat(r.time);
          if (!barBuckets[label]) barBuckets[label] = 0;
          barBuckets[label] += r.flow * SAMPLE_SECONDS / 1000;
      }

      const labels = Object.keys(barBuckets);
      const barData = labels.map(l => Math.round(barBuckets[l] * 1000) / 1000);
      const cumData = barData.reduce((acc, val) => {
          acc.push((acc.length ? acc[acc.length - 1] : 0) + val);
          return acc;
      }, []);

      return { labels, barData, cumData };
  }

  // Fetch using context.timeRange instead of period buttons
  async function fetchDataFromTimeRange() {
    if (!context || !context.timeRange) return;

    loading = true;
    error = null;
    totalKg = 0;

    try {
      const agentId = getAgentId();
      const dsName = getDataSourceName();
      const slug = getTagSlug();

      if (!agentId) throw new Error('Agent ID not configured');

      const startMs = context.timeRange.from;
      const endMs = context.timeRange.to;
      const fmt = (ms) => new Date(ms).toISOString().replace(/\.\d+Z$/, 'Z');
      const startStr = fmt(startMs);
      const endStr = fmt(endMs);

      // Determine period label from span
      const spanMs = endMs - startMs;
      if (spanMs <= 3600 * 1000) period = 'hour';
      else if (spanMs <= 86400 * 1000) period = 'day';
      else if (spanMs <= 7 * 86400 * 1000) period = 'week';
      else period = 'month';

      const dataSource = await getDataSourceId(agentId, dsName);
      const tags = await getTagsData(agentId, dataSource, slug);

      if (!tags.length) throw new Error(`Tag "${slug}" not found`);

      const intervals = splitMonthly(startStr, endStr);
      let allCsv = '';

      for (const [s, e] of intervals) {
        const csv = await exportData(dataSource, tags, s, e);
        if (csv) allCsv += (allCsv ? '\n' : '') + csv;
      }

      if (!allCsv.trim()) throw new Error('No data returned for this period');

      const points = parseCSV(allCsv, slug);
      if (!points.length) throw new Error('No valid data points');

      const { labels, barData, cumData } = buildChartData(points, startMs, endMs);
      totalKg = cumData.length ? cumData[cumData.length - 1] : 0;
      totalKg = Math.round(totalKg * 1000) / 1000;

      renderChart(labels, barData, cumData);
    } catch (e) {
      error = e.message;
    }

    loading = false;
  }

  // Set default time range to last 24 hours on init
  function initTimeRange() {
    const now = new Date();
    const start = new Date(now - 86400 * 1000);
    if (context && context.setTimeRange) {
      context.setTimeRange({ from: start.getTime(), to: now.getTime() });
    }
  }

  function splitMonthly(startStr, endStr) {
    const start = new Date(startStr);
    const end = new Date(endStr);
    const intervals = [];
    let current = new Date(start);

    while (current < end) {
      let monthEnd = new Date(current.getFullYear(), current.getMonth() + 1, 1);
      monthEnd = new Date(monthEnd - 1000);
      if (monthEnd > end) monthEnd = end;
      const fmt = (d) => d.toISOString().replace(/\.\d+Z$/, 'Z');
      intervals.push([fmt(current), fmt(monthEnd)]);
      current = new Date(monthEnd.getTime() + 1000);
    }

    return intervals;
  }

  function renderChart(labels, barData, cumData) {
    if (chart) chart.destroy();

    const spanLabel = period === 'hour' ? 'minute' : period === 'day' ? 'hour' : 'day';

    chart = new Chart(canvas, {
      data: {
        labels,
        datasets: [
          {
            type: 'bar',
            label: `H₂ per ${spanLabel} (kg)`,
            data: barData,
            backgroundColor: '#007D24',
            borderColor: '#007D24',
            borderWidth: 1,
            yAxisID: 'y',
            order: 2
          },
          {
            type: 'line',
            label: 'Cumulative H₂ (kg)',
            data: cumData,
            borderColor: '#C6000D',
            backgroundColor: '#C6000D',
            pointBackgroundColor: '#C6000D',
            pointRadius: labels.length > 50 ? 0 : 4,
            borderWidth: 2,
            tension: 0.3,
            fill: false,
            yAxisID: 'y1',
            order: 1
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          title: {
            display: true,
            text: `Hydrogen Production — ${formatDisplayDate(from)} to ${formatDisplayDate(to)}`,
            font: { size: 14, weight: 'bold' },
            align: 'start',
            padding: { bottom: 16 }
          },
          legend: {
            position: 'top',
            align: 'start',
            labels: {
              boxWidth: 16,
              padding: 16,
              font: { size: 12 }
            }
          }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: {
              maxTicksLimit: 12,
              maxRotation: 45
            }
          },
          y: {
            type: 'linear',
            position: 'left',
            beginAtZero: true,
            title: { display: true, text: 'kg per interval' },
            grid: { color: '#e0e0e0' }
          },
          y1: {
            type: 'linear',
            position: 'right',
            beginAtZero: true,
            title: { display: true, text: 'Cumulative kg' },
            grid: { drawOnChartArea: false }
          }
        }
      }
    });
  }

  onMount(() => {
    // Listen for nav bar time range changes
    context.ontimerangechange = (newTimeRange) => {
      from = new Date(newTimeRange.from).toISOString();
      to = new Date(newTimeRange.to).toISOString();
      fetchDataFromTimeRange();
    };

    initTimeRange();
  });
</script>

<div class="hydrogen-widget">
  <!-- Time adjustment controls -->
  <div class="time-controls">
    <div class="time-display">
      <span class="time-label">From:</span>
      <span class="time-value">{formatDisplayDate(from)}</span>
      <span class="time-label">To:</span>
      <span class="time-value">{formatDisplayDate(to)}</span>
    </div>
    <div class="time-adjustment">
      <div class="input-switch">
        <label for="toggleTarget" class="switch-label">Start</label>
        <input
          type="checkbox"
          id="toggleTarget"
          class="toggle-input"
          bind:checked={isToDate}
          on:change={toggleDateAdjustment}
        />
        <label for="toggleTarget" class="switch"></label>
        <label for="toggleTarget" class="switch-label">End</label>
      </div>
      <div class="button-group">
        <button on:click={decrementTimeRange} class="adj-btn" aria-label="Decrease time range">
          <svg xmlns="http://www.w3.org/2000/svg" height="20px" viewBox="0 -960 960 960" width="20px" fill="currentColor">
            <path d="M480-120q-138 0-240.5-91.5T122-440h82q14 104 92.5 172T480-200q117 0 198.5-81.5T760-480q0-117-81.5-198.5T480-760q-69 0-129 32t-101 88h110v80H120v-240h80v94q51-64 124.5-99T480-840q75 0 140.5 28.5t114 77q48.5 48.5 77 114T840-480q0 75-28.5 140.5t-77 114q-48.5 48.5-114 77T480-120Zm112-192L440-464v-216h80v184l128 128-56 56Z"/>
          </svg>
        </button>
        <input
          type="number"
          class="minute-input"
          bind:value={minuteAdjustment}
          min="1"
          aria-label="Minutes to adjust"
        />
        <span class="min-label">min</span>
        <button on:click={incrementTimeRange} class="adj-btn" aria-label="Increase time range">
          <svg xmlns="http://www.w3.org/2000/svg" height="20px" viewBox="0 -960 960 960" width="20px" fill="currentColor">
            <path d="M480-120q-75 0-140.5-28.5t-114-77q-48.5-48.5-77-114T120-480q0-75 28.5-140.5t77-114q48.5-48.5 114-77T480-840q82 0 155.5 35T760-706v-94h80v240H600v-80h110q-41-56-101-88t-129-32q-117 0-198.5 81.5T200-480q0 117 81.5 198.5T480-200q105 0 183.5-68T756-440h82q-15 137-117.5 228.5T480-120Zm112-192L440-464v-216h80v184l128 128-56 56Z"/>
          </svg>
        </button>
      </div>
    </div>
  </div>

  {#if loading}
    <div class="status">Loading data...</div>
  {:else if error}
    <div class="status error">{error}</div>
  {:else}
    <div class="total">
      <span class="value">{totalKg}</span>
      <span class="unit">kg H₂</span>
    </div>
  {/if}

  <div class="chart-container">
    <canvas bind:this={canvas}></canvas>
  </div>
</div>

<style>
  .hydrogen-widget {
    width: 100%;
    height: 100%;
    padding: 1rem;
    box-sizing: border-box;
    font-family: sans-serif;
  }

  /* Time controls */
  .time-controls {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-bottom: 0.75rem;
    flex-wrap: wrap;
    padding: 0.5rem 0.75rem;
    background: #f8f9fa;
    border: 1px solid #e0e0e0;
    border-radius: 6px;
  }

  .time-display {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    flex-wrap: wrap;
    font-size: 0.8rem;
  }
  .time-label {
    color: #888;
    font-weight: 600;
  }
  .time-value {
    color: #333;
    font-family: monospace;
    font-size: 0.78rem;
    background: #fff;
    padding: 0.15rem 0.4rem;
    border-radius: 3px;
    border: 1px solid #e0e0e0;
  }

  .time-adjustment {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-left: auto;
  }

  /* Toggle switch */
  .input-switch {
    display: flex;
    align-items: center;
    gap: 0.35rem;
  }
  .switch-label {
    font-size: 0.75rem;
    color: #666;
    cursor: pointer;
    user-select: none;
  }
  .toggle-input {
    display: none;
  }
  .switch {
    position: relative;
    display: inline-block;
    width: 36px;
    height: 20px;
    background: #007D24;
    border-radius: 10px;
    cursor: pointer;
    transition: background 0.2s;
  }
  .switch::after {
    content: '';
    position: absolute;
    top: 2px;
    left: 2px;
    width: 16px;
    height: 16px;
    background: white;
    border-radius: 50%;
    transition: transform 0.2s;
  }
  .toggle-input:checked ~ .switch {
    background: #C6000D;
  }
  .toggle-input:checked ~ .switch::after {
    transform: translateX(16px);
  }

  /* Button group */
  .button-group {
    display: flex;
    align-items: center;
    gap: 0.25rem;
  }
  .adj-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    border: 1px solid #ccc;
    border-radius: 4px;
    background: #fff;
    cursor: pointer;
    color: #555;
    padding: 0;
  }
  .adj-btn:hover {
    background: #f0f0f0;
    border-color: #999;
  }
  .minute-input {
    width: 48px;
    height: 32px;
    text-align: center;
    border: 1px solid #ccc;
    border-radius: 4px;
    font-size: 0.85rem;
    font-family: monospace;
  }
  .min-label {
    font-size: 0.75rem;
    color: #888;
  }

  /* Total */
  .total {
    text-align: center;
    margin: 0.5rem 0;
  }
  .total .value {
    font-size: 2rem;
    font-weight: bold;
    color: #007D24;
  }
  .total .unit {
    font-size: 0.9rem;
    color: #666;
    margin-left: 0.25rem;
  }

  /* Status */
  .status {
    text-align: center;
    padding: 1rem;
    color: #666;
  }
  .status.error {
    color: #C6000D;
  }

  /* Chart */
  .chart-container {
    width: 100%;
    height: calc(100% - 180px);
    min-height: 250px;
    position: relative;
  }
  canvas {
    width: 100% !important;
    height: 100% !important;
  }
</style>
