<script>
  import { onMount } from 'svelte';
  import { Chart, registerables } from 'chart.js';
  import {
    buildHeaders,
    getDataSourceId,
    getTagsData,
    exportData,
    parseCSV,
    buildChartData,
    splitMonthly,
    getTimeRange
  } from './ixonApi.js';

  Chart.register(...registerables);

  export let context;

  let canvas;
  let loading = false;
  let error = null;
  let totalKg = 0;
  let period = 'day';
  let chart = null;

  async function fetchData() {
    loading = true;
    error = null;
    totalKg = 0;

    try {
      const inputs = context?.inputs || {};
      const headers = buildHeaders(inputs);
      const agentId = inputs.agentId || '';
      const dsName = inputs.dataSourceName || 'Databron-PLC';
      const slug = inputs.tagSlug || 'FT_301';

      if (!agentId) throw new Error('Agent ID not configured');

      const { startStr, endStr } = getTimeRange(period);
      const dataSource = await getDataSourceId(headers, agentId, dsName);
      const tags = await getTagsData(headers, agentId, dataSource, slug);

      if (!tags.length) throw new Error(`Tag "${slug}" not found`);

      const intervals = splitMonthly(startStr, endStr);
      let allCsv = '';

      for (const [s, e] of intervals) {
        const csv = await exportData(headers, dataSource, tags, s, e);
        if (csv) allCsv += (allCsv ? '\n' : '') + csv;
      }

      if (!allCsv.trim()) throw new Error('No data returned for this period');

      const points = parseCSV(allCsv, slug);
      if (!points.length) throw new Error('No valid data points');

      const { labels, barData, cumData } = buildChartData(points, period);
      totalKg = cumData.length ? cumData[cumData.length - 1] : 0;
      totalKg = Math.round(totalKg * 1000) / 1000;

      renderChart(labels, barData, cumData);
    } catch (e) {
      error = e.message;
    }

    loading = false;
  }

  function renderChart(labels, barData, cumData) {
    if (chart) chart.destroy();

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
