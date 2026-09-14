/**
 * Live timesheet row, column, and weekly total calculation.
 */
function updateTotals() {
    let weeklyTotal = 0;
    const dailyTotals = [0, 0, 0, 0, 0, 0, 0];
    const rows = document.querySelectorAll('tbody tr.task-row');
    const footerTotalElement = document.getElementById('footer-total');

    rows.forEach(row => {
        let rowTotal = 0;
        const rowInputs = row.querySelectorAll('input[type="number"]');

        rowInputs.forEach((input, index) => {
            const val = parseFloat(input.value) || 0;
            rowTotal += val;
            if (index < 7) {
                dailyTotals[index] += val;
            }
        });

        const rowTotalCell = row.querySelector('.row-total');
        if (rowTotalCell) {
            rowTotalCell.textContent = rowTotal.toFixed(1);
        }

        weeklyTotal += rowTotal;
    });

    const dailyTotalCells = document.querySelectorAll('.daily-total');
    dailyTotalCells.forEach((cell, index) => {
        const val = dailyTotals[index];
        cell.textContent = val.toFixed(1);

        cell.classList.remove('text-red-600', 'text-green-600', 'text-orange-600', 'text-gray-700');
        if (index < 5) {
            if (val > 8) {
                cell.classList.add('text-red-600');
            } else if (val === 8) {
                cell.classList.add('text-green-600');
            } else if (val < 8) {
                cell.classList.add('text-orange-600');
            }
        } else {
            if (val > 0) {
                cell.classList.add('text-red-600');
            } else {
                cell.classList.add('text-gray-700');
            }
        }
    });

    if (footerTotalElement) {
        footerTotalElement.textContent = weeklyTotal.toFixed(1);
        footerTotalElement.classList.remove('text-gray-900', 'text-green-600', 'text-red-600');
        if (weeklyTotal === 40) {
            footerTotalElement.classList.add('text-green-600');
        } else if (weeklyTotal > 40) {
            footerTotalElement.classList.add('text-red-600');
        } else {
            footerTotalElement.classList.add('text-gray-900');
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const inputs = document.querySelectorAll('input[type="number"]');
    inputs.forEach(input => {
        input.addEventListener('input', () => {
            updateTotals();
        });
    });
    updateTotals();
});
