/**
 * Yearly dashboard doughnut chart visualizing commercial vs internal project hours.
 */
document.addEventListener('DOMContentLoaded', () => {
    const canvas = document.getElementById('hoursChart');
    if (!canvas || typeof Chart === 'undefined') return;

    if (typeof ChartDataLabels !== 'undefined') {
        Chart.register(ChartDataLabels);
    }

    const totalHours = parseFloat(canvas.dataset.total) || 0;
    const commHours = parseFloat(canvas.dataset.comm) || 0;
    const nonCommHours = parseFloat(canvas.dataset.nonComm) || 0;

    if (totalHours <= 0) return;

    const ctx = canvas.getContext('2d');
    const data = {
        labels: ['Commercial', 'Internal'],
        datasets: [{
            data: [commHours, nonCommHours],
            backgroundColor: [
                '#4f46e5', // Indigo-600
                '#14b8a6', // Teal-500
            ],
            hoverOffset: 4,
            borderWidth: 0,
        }],
    };

    new Chart(ctx, {
        type: 'doughnut',
        data: data,
        options: {
            responsive: true,
            cutout: '60%',
            plugins: {
                legend: {
                    position: 'bottom',
                },
                datalabels: {
                    color: '#ffffff',
                    font: {
                        weight: 'bold',
                        size: 14,
                    },
                    formatter: (value) => {
                        if (value === 0) return '';
                        const percentage = ((value / totalHours) * 100).toFixed(1);
                        return `${percentage}%`;
                    },
                },
            },
        },
    });
});
