<script>
  import { onMount } from 'svelte';
  import { Chart, registerables } from 'chart.js';

  Chart.register(...registerables);

  export let context;

  let canvas;
  let client;
  let loading = false;
  let error = null;
  let totalKg = 0;
  let chart = null;

  let from = '';
  let to = '';
  let isToDate = false;
  let minuteAdjustment = 15;
  let adjustmentTarget = 'from';

  let chartLabels = [];
  let chartBarData = [];
  let chartCumData = [];

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
    if (!context || !context.timeRange) return;
    const fromMs = context.timeRange.from;
    const toMs = context.timeRange.to;
    const offsetMs = minutes * 60 * 1000;

    if (adjustmentTarget === 'from') {
      context.setTimeRange({ from: fromMs + offsetMs, to: toMs });
    } else {
      context.setTimeRange({ from: fromMs, to: toMs + offsetMs });
    }
  }

  function formatDisplayDate(isoString) {
    if (!isoString) return '';
    const d = new Date(isoString);
    return d.toLocaleString('en-GB', {
      day: '2-digit', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit'
    });
  }

  async function fetchData() {
    if (!client || !context.timeRange) return;
    loading = true;
    error = null;

try {
      const response = await client.call(
        'functions.hydrogen_data.get_production',
        {
          agentId: context.inputs.agentId,
          dataSourceName: context.inputs.dataSourceName || 'Databron-PLC',
          tagSlug: context.inputs.tagSlug || 'FT_301',
          startMs: context.timeRange.from,
          endMs: context.timeRange.to
        }
      );

      if (!response) throw new Error('No response from Cloud Function');

      const data = response.data || response;
      if (data.error) throw new Error(data.error);

      totalKg = data.totalKg || 0;
      chartLabels = data.labels || [];
      chartBarData = data.barData || [];
      chartCumData = data.cumData || [];
      renderChart();
    } catch (e) {
      error = e.message;
    }

    loading = false;
  }

  function renderChart() {
    if (chart) chart.destroy();
    if (!chartLabels.length) return;

    const spanLabel = chartLabels.length <= 60 ? 'minute' : chartLabels.length <= 24 ? 'hour' : 'day';

    chart = new Chart(canvas, {
      data: {
        labels: chartLabels,
        datasets: [
          {
            type: 'bar',
            label: `H₂ per ${spanLabel} (kg)`,
            data: chartBarData,
            backgroundColor: '#007D24',
            borderColor: '#007D24',
            borderWidth: 1,
            yAxisID: 'y',
            order: 2
          },
          {
            type: 'line',
            label: 'Cumulative H₂ (kg)',
            data: chartCumData,
            borderColor: '#C6000D',
            backgroundColor: '#C6000D',
            pointBackgroundColor: '#C6000D',
            pointRadius: chartLabels.length > 50 ? 0 : 4,
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
            font: { size: 18, weight: 'bold' },
            align: 'start',
            padding: { bottom: 16 }
          },
          legend: {
            position: 'top',
            align: 'start',
            labels: { boxWidth: 16, padding: 16, font: { size: 12 } }
          }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { maxTicksLimit: 12, maxRotation: 45 }
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
    client = context.createBackendComponentClient();

    context.ontimerangechange = (newTimeRange) => {
      from = new Date(newTimeRange.from).toISOString();
      to = new Date(newTimeRange.to).toISOString();
      fetchData();
    };

    if (context.timeRange && context.timeRange.from) {
      from = new Date(context.timeRange.from).toISOString();
      to = new Date(context.timeRange.to).toISOString();
      fetchData();
    }
  });
</script>

<div class="hydrogen-widget">
  <div class="controls">
    <div class="time-display">
      <span class="time-label">From:</span>
      <span class="time-value">{formatDisplayDate(from)}</span>
      <span class="time-label">To:</span>
      <span class="time-value">{formatDisplayDate(to)}</span>
    </div>
    <div class="time-adjustment">
      <div class="input-switch">
        <label for="toggleTarget" class="switch-label">Start</label>
        <input type="checkbox" id="toggleTarget" class="toggle-input"
          bind:checked={isToDate} on:change={toggleDateAdjustment} />
        <label for="toggleTarget" class="switch"></label>
        <label for="toggleTarget" class="switch-label">End</label>
      </div>
      <div class="button-group">
        <button on:click={() => decrementTimeRange()} class="adj-btn">−</button>
        <input type="number" class="minute-input" bind:value={minuteAdjustment} min="1" />
        <span class="min-label">min</span>
        <button on:click={() => incrementTimeRange()} class="adj-btn">+</button>
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
  .controls {
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
    font-size: 1.1rem;
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
    height: calc(100% - 140px);
    min-height: 250px;
    position: relative;
  }
  canvas {
    width: 100% !important;
    height: 100% !important;
  }
</style>
