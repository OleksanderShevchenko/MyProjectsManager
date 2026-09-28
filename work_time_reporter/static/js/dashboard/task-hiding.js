/**
 * Task row hiding and localStorage persistence per timesheet week.
 */
document.addEventListener('DOMContentLoaded', () => {
    const timesheetContainer = document.querySelector('[data-timesheet-id]');
    if (!timesheetContainer) return;

    const timesheetId = timesheetContainer.dataset.timesheetId;
    const storageKey = `hidden_tasks_ts_${timesheetId}`;
    const tableContainer = document.querySelector('.overflow-x-auto');

    let hiddenTasks = JSON.parse(localStorage.getItem(storageKey)) || [];
    let showAllBtn = null;

    function toggleShowButton() {
        if (hiddenTasks.length > 0) {
            if (!showAllBtn && tableContainer) {
                showAllBtn = document.createElement('button');
                showAllBtn.type = 'button';
                showAllBtn.className = 'mt-3 text-sm text-indigo-600 hover:text-indigo-800 font-medium flex items-center transition-colors cursor-pointer';
                showAllBtn.innerHTML = `
                    <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path>
                    </svg>
                    Show hidden tasks (${hiddenTasks.length})
                `;

                showAllBtn.addEventListener('click', function() {
                    localStorage.removeItem(storageKey);
                    hiddenTasks = [];

                    document.querySelectorAll('tr.task-row.hidden').forEach(row => {
                        row.classList.remove('hidden');
                    });

                    this.remove();
                    showAllBtn = null;
                });

                tableContainer.parentNode.insertBefore(showAllBtn, tableContainer.nextSibling);
            } else if (showAllBtn) {
                showAllBtn.innerHTML = `
                    <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path>
                    </svg>
                    Show hidden tasks (${hiddenTasks.length})
                `;
            }
        }
    }

    // Hide rows on initial page load from localStorage
    document.querySelectorAll('tr.task-row').forEach(row => {
        const hideBtn = row.querySelector('.hide-task-btn');
        if (hideBtn) {
            const taskId = hideBtn.dataset.taskId;
            if (hiddenTasks.includes(taskId)) {
                row.classList.add('hidden');
            }
        }
    });
    toggleShowButton();

    // Attach click handlers to hide eye buttons
    document.querySelectorAll('.hide-task-btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            const taskId = this.dataset.taskId;
            const row = this.closest('tr.task-row');

            if (row) {
                row.classList.add('hidden');
            }

            if (!hiddenTasks.includes(taskId)) {
                hiddenTasks.push(taskId);
                localStorage.setItem(storageKey, JSON.stringify(hiddenTasks));
            }

            toggleShowButton();
        });
    });
});
