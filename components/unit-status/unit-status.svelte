<script>
  import { onMount } from 'svelte';
  import { Chart, registerables } from 'chart.js';

  Chart.register(...registerables);

  export let context;

  let canvas;

  onMount(() => {
    new Chart(canvas, {
      type: 'bar',
      data: {
        labels: ['January', 'February', 'March', 'April', 'May', 'June', 'July'],
        datasets: [
          {
            label: 'Commissioned',
            data: [4, 3, 4, 5, 4, 4, 5],
            backgroundColor: '#007D24'
          },
          {
            label: 'Serviced',
            data: [2, 2, 3, 2, 3, 3, 1],
            backgroundColor: '#8BBF9F'
          },
          {
            label: 'Maintenance',
            data: [2, 2, 1, 1, 2, 2, 1],
            backgroundColor: '#C8E6CF'
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          title: {
            display: true,
            text: 'Unit Status Count (#)',
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
            stacked: true,
            grid: { display: false }
          },
          y: {
            stacked: true,
            beginAtZero: true,
            ticks: { stepSize: 2 },
            grid: { color: '#e0e0e0' }
          }
        }
      }
    });
  });
</script>

<div class="chart-container">
  <canvas bind:this={canvas}></canvas>
</div>

<style>
  .chart-container {
    width: 100%;
    height: 400px;
    padding: 1rem;
    box-sizing: border-box;
    position: relative;
  }
  canvas {
    width: 100% !important;
    height: 100% !important;
  }
</style>