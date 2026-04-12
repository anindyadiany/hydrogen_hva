<script>
  import { onMount } from 'svelte';
  import { Chart, registerables } from 'chart.js';

  Chart.register(...registerables);

  export let context;

  let canvas;
  let loading = false;
  let error = null;
  let totalKg = 0;
  let period = 'day';
  let chart = null;

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

      // Deduplicate: keep last value per timestamp (matching Python's groupby.last())
      const deduped = {};
      for (const r of results) {
          deduped[r.time] = r;
      }
      return Object.values(deduped);
  }

  function buildChartData(points) {
      const SAMPLE_SECONDS = 10;

      if (!points.length) return { labels: [], barData: [], cumData: [] };

      const startTime = new Date(points[0].time).getTime();
      const endTime = new Date(points[points.length - 1].time).getTime();

      // Align to clean 10-second boundaries like pandas does
      const alignedStart = Math.floor(startTime / (SAMPLE_SECONDS * 1000)) * (SAMPLE_SECONDS * 1000);

      // Build 10-second resampled series with forward fill
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

      // Group into display buckets based on period
      let bucketFormat;
      if (period === 'hour') bucketFormat = (t) => new Date(t).toISOString().slice(11, 16);
      else if (period === 'day') bucketFormat = (t) => new Date(t).toISOString().slice(11, 13) + ':00';
      else bucketFormat = (t) => new Date(t).toISOString().slice(0, 10);

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

  async function fetchData() {
    loading = true;
    error = null;
    totalKg = 0;

    try {
      const agentId = getAgentId();
      const dsName = getDataSourceName();
      const slug = getTagSlug();

      if (!agentId) throw new Error('Agent ID not configured');

      // const now = new Date();
      // let start;
      // if (period === 'hour') start = new Date(now - 3600 * 1000);
      // else if (period === 'day') start = new Date(now - 86400 * 1000);
      // else if (period === 'week') start = new Date(now - 7 * 86400 * 1000);
      // else start = new Date(now - 30 * 86400 * 1000);

      // const fmt = (d) => d.toISOString().replace(/\.\d+Z$/, 'Z');
      // const startStr = fmt(start);
      // const endStr = fmt(now);

      const now = new Date();
      let start, end;

      if (period === 'day') {
          // Yesterday 00:00:00 to 23:59:59 UTC
          const yesterday = new Date(now);
          yesterday.setUTCDate(yesterday.getUTCDate() - 1);
          start = new Date(Date.UTC(yesterday.getUTCFullYear(), yesterday.getUTCMonth(), yesterday.getUTCDate(), 0, 0, 0));
          end = new Date(Date.UTC(yesterday.getUTCFullYear(), yesterday.getUTCMonth(), yesterday.getUTCDate(), 23, 59, 59));
      } else if (period === 'hour') {
          start = new Date(now - 3600 * 1000);
          end = now;
      } else if (period === 'week') {
          start = new Date(now - 7 * 86400 * 1000);
          end = now;
      } else {
          start = new Date(now - 30 * 86400 * 1000);
          end = now;
      }

      const fmt = (d) => d.toISOString().replace(/\.\d+Z$/, 'Z');
      const startStr = fmt(start);
      const endStr = fmt(end);

      const dataSource = await getDataSourceId(agentId, dsName);
      const tags = await getTagsData(agentId, dataSource, slug);

      if (!tags.length) throw new Error(`Tag "${slug}" not found`);

      // Split into monthly intervals (for large ranges)
      const intervals = splitMonthly(startStr, endStr);
      let allCsv = '';

      for (const [s, e] of intervals) {
        const csv = await exportData(dataSource, tags, s, e);
        if (csv) allCsv += (allCsv ? '\n' : '') + csv;
      }

      if (!allCsv.trim()) throw new Error('No data returned for this period');

      console.log('Raw CSV (first 500 chars):', allCsv.slice(0, 500));
      console.log('Tag slug looking for:', slug);

      const points = parseCSV(allCsv, slug);
      console.log('Parsed points:', points.length);
      if (!points.length) throw new Error('No valid data points');

      const { labels, barData, cumData } = buildChartData(points);
      totalKg = cumData.length ? cumData[cumData.length - 1] : 0;
      totalKg = Math.round(totalKg * 1000) / 1000;

      renderChart(labels, barData, cumData);
    } catch (e) {
      error = e.message;
    }

    loading = false;
  }

  function splitMonthly(startStr, endStr) {
    const start = new Date(startStr);
    const end = new Date(endStr);
    const intervals = [];
    let current = new Date(start);

    while (current < end) {
      let monthEnd = new Date(current.getFullYear(), current.getMonth() + 1, 1);
      monthEnd = new Date(monthEnd - 1000); // last second of month
      if (monthEnd > end) monthEnd = end;
      const fmt = (d) => d.toISOString().replace(/\.\d+Z$/, 'Z');
      intervals.push([fmt(current), fmt(monthEnd)]);
      current = new Date(monthEnd.getTime() + 1000);
    }

    return intervals;
  }

  function renderChart(labels, barData, cumData) {
    if (chart) chart.destroy();

    const maxBar = Math.max(...barData, 1);
    const maxCum = Math.max(...cumData, 1);

    chart = new Chart(canvas, {
      data: {
        labels,
        datasets: [
          {
            type: 'bar',
            label: `H₂ per ${period === 'hour' ? 'minute' : period === 'day' ? 'hour' : 'day'} (kg)`,
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
            text: `Hydrogen Production — ${period}`,
            font: { size: 18, weight: 'bold' },
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

  function selectPeriod(p) {
    period = p;
    fetchData();
  }

  onMount(() => {
    fetchData();
  });
</script>

<div class="hydrogen-widget">
  <div class="controls">
    {#each ['hour', 'day', 'week', 'month'] as p}
      <button
        class:active={period === p}
        on:click={() => selectPeriod(p)}
      >
        {p.charAt(0).toUpperCase() + p.slice(1)}
      </button>
    {/each}
  </div>

  {#if loading}
    <div class="status">Loading data...</div>
  {:else if error}
    <div class="status error">{error}</div>
  {:else}
    <div class="total">
      <span class="value">{totalKg}</span>
      <span class="unit">kg H₂ / {period}</span>
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
  .controls {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 0.75rem;
  }
  .controls button {
    padding: 0.4rem 0.8rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    background: #fff;
    cursor: pointer;
    font-size: 0.85rem;
  }
  .controls button.active {
    background: #007D24;
    color: #fff;
    border-color: #007D24;
  }
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
  .status {
    text-align: center;
    padding: 1rem;
    color: #666;
  }
  .status.error {
    color: #C6000D;
  }
  .chart-container {
    width: 100%;
    height: calc(100% - 120px);
    min-height: 250px;
    position: relative;
  }
  canvas {
    width: 100% !important;
    height: 100% !important;
  }
</style>