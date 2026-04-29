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

  let agentError = null;
  let agents = [];
  let selectedAgentId = '';
  let agentsLoading = false;

  function toggleDateAdjustment() {
    adjustmentTarget = isToDate ? 'to' : 'from';
  }

  function incrementTimeRange() { adjustTimeRange(minuteAdjustment); }
  function decrementTimeRange() { adjustTimeRange(-minuteAdjustment); }

  function adjustTimeRange(minutes) {
    if (!context?.timeRange) return;
    const offsetMs = minutes * 60 * 1000;
    if (adjustmentTarget === 'from') {
      context.setTimeRange({ from: context.timeRange.from + offsetMs, to: context.timeRange.to });
    } else {
      context.setTimeRange({ from: context.timeRange.from, to: context.timeRange.to + offsetMs });
    }
  }

  function formatDisplayDate(isoString) {
    if (!isoString) return '';
    return new Date(isoString).toLocaleString('en-GB', {
      day: '2-digit', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit'
    });
  }

  async function fetchAgents() {
    if (!client) { agentError = 'No client'; return; }
    agentsLoading = true;
    agentError = null;
    try {
      const response = await client.call('functions.hydrogen_data.get_agents', {});
      console.log('get_agents raw response:', JSON.stringify(response));
      
      // CDK may wrap in data field
      agents = response?.agents 
            || response?.data?.agents 
            || [];
      
      console.log('agents parsed:', agents);
      
      if (agents.length > 0) {
        selectedAgentId = agents[0].id;
        await fetchData();
      } else {
        agentError = `No agents (raw: ${JSON.stringify(response)})`;
      }
    } catch (e) {
      agentError = String(e);
      console.error('fetchAgents error:', e);
    }
    agentsLoading = false;
  }

  async function fetchData() {
    if (!client || !context?.timeRange || !selectedAgentId) return;
    loading = true;
    error = null;
    try {
      const response = await client.call('functions.hydrogen_data.get_production', {
        agentId: selectedAgentId,
        dataSourceName: 'Databron-PLC',
        tagSlug: 'FT_301',
        startMs: context.timeRange.from,
        endMs: context.timeRange.to
      });
      const data = response?.data || response;
      if (!data || data.error) throw new Error(data?.error || 'No response');
      totalKg      = data.totalKg  || 0;
      chartLabels  = data.labels   || [];
      chartBarData = data.barData  || [];
      chartCumData = data.cumData  || [];
      renderChart();
    } catch (e) {
      error = e.message;
    }
    loading = false;
  }

  function renderChart() {
    if (chart) chart.destroy();
    if (!chartLabels.length) return;
    chart = new Chart(canvas, {
      data: {
        labels: chartLabels,
        datasets: [
          {
            type: 'bar',
            label: 'H₂ per hour (kg)',
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
          x: { grid: { display: false }, ticks: { maxTicksLimit: 12, maxRotation: 45 } },
          y: {
            type: 'linear', position: 'left', beginAtZero: true,
            title: { display: true, text: 'kg per hour' },
            grid: { color: '#e0e0e0' }
          },
          y1: {
            type: 'linear', position: 'right', beginAtZero: true,
            title: { display: true, text: 'Cumulative kg' },
            grid: { drawOnChartArea: false }
          }
        }
      }
    });
  }

  onMount(async () => {
    client = context.createBackendComponentClient();

    context.ontimerangechange = (newTimeRange) => {
      from = new Date(newTimeRange.from).toISOString();
      to   = new Date(newTimeRange.to).toISOString();
      fetchData();
    };

    if (context.timeRange?.from) {
      from = new Date(context.timeRange.from).toISOString();
      to   = new Date(context.timeRange.to).toISOString();
    }

    await fetchAgents();
  });
</script>

<div class="hydrogen-widget">
  <div class="agent-bar">
    <label for="agentSelect">Agent:</label>
    {#if agentsLoading}
      <span>Loading…</span>
    {:else if agentError}
      <span style="color:#C6000D">{agentError}</span>
    {:else if agents.length === 0}
      <span style="color:#C6000D">No agents</span>
    {:else}
      <select id="agentSelect" class="agent-select"
        bind:value={selectedAgentId}
        on:change={fetchData}>
        {#each agents as agent}
          <option value={agent.id}>{agent.name}</option>
        {/each}
      </select>
    {/if}
    <span class="time-range">{formatDisplayDate(from)} → {formatDisplayDate(to)}</span>
  </div>

  {#if loading}
    <div class="status">Loading data…</div>
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
  .agent-bar {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-bottom: 0.75rem;
    padding: 0.5rem 0.75rem;
    background: #f8f9fa;
    border: 1px solid #e0e0e0;
    border-radius: 6px;
    font-size: 0.85rem;
    font-weight: 600;
    color: #555;
  }
  .agent-select {
    height: 32px;
    border: 1px solid #ccc;
    border-radius: 4px;
    font-size: 0.85rem;
    padding: 0 0.5rem;
    background: #fff;
    color: #333;
    cursor: pointer;
    min-width: 200px;
  }
  .agent-select:focus {
    outline: none;
    border-color: #007D24;
  }
  .time-range {
    margin-left: auto;
    font-size: 0.78rem;
    font-family: monospace;
    color: #888;
    font-weight: normal;
  }
  .total { text-align: center; margin: 0.5rem 0; }
  .total .value { font-size: 2rem; font-weight: bold; color: #007D24; }
  .total .unit { font-size: 0.9rem; color: #666; margin-left: 0.25rem; }
  .status { text-align: center; padding: 1rem; color: #666; }
  .status.error { color: #C6000D; }
  .chart-container {
    width: 100%;
    height: calc(100% - 110px);
    min-height: 250px;
    position: relative;
  }
  canvas { width: 100% !important; height: 100% !important; }
</style>