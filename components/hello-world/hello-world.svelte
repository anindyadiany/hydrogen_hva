<script>
  import { onMount } from 'svelte';
  import { Chart, registerables } from 'chart.js';

  Chart.register(...registerables);

  let canvas;

  onMount(() => {
    const monthlyData = [45, 170, 140, 250, 155, 280, 85];
    const cumulativeData = monthlyData.reduce((acc, val) => {
      acc.push((acc.length ? acc[acc.length - 1] : 0) + val);
      return acc;
    }, []);

    new Chart(canvas, {
      data: {
        labels: ['January', 'February', 'March', 'April', 'May', 'June', 'July'],
        datasets: [
          {
            type: 'bar',
            label: 'Monthly Production',
            data: monthlyData,
            backgroundColor: '#007D24',
            borderColor: '#007D24',
            borderWidth: 1,
            order: 2
          },
          {
            type: 'line',
            label: 'Cumulative Production',
            data: cumulativeData,
            borderColor: '#C6000D',
            backgroundColor: '#C6000D',
            pointBackgroundColor: '#C6000D',
            pointRadius: 6,
            pointHoverRadius: 8,
            borderWidth: 3,
            tension: 0.3,
            fill: false,
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
            text: 'Hydrogen Production (kg)',
            font: { size: 20, weight: 'bold' },
            align: 'start',
            padding: { bottom: 20 }
          },
          legend: {
            position: 'top',
            align: 'start',
            labels: {
              usePointStyle: false,
              boxWidth: 20,
              padding: 20,
              font: { size: 14 }
            }
          }
        },
        scales: {
          y: {
            beginAtZero: true,
            max: 500,
            ticks: { stepSize: 100 },
            grid: { color: '#e0e0e0' }
          },
          x: {
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
    height: 100%;
    min-height: 300px;
    padding: 1rem;
  }
</style>