/**
 * Timesheet cell comment modal dialog interactions.
 */
document.addEventListener('DOMContentLoaded', () => {
    const modal = document.getElementById('commentModal');
    const modalTextarea = document.getElementById('modalTextarea');
    const modalSave = document.getElementById('modalSave');
    const modalCancel = document.getElementById('modalCancel');
    const closeModalIcon = document.getElementById('closeModalIcon');
    const modalDateInfo = document.getElementById('modalDateInfo');

    if (!modal) return;

    let currentInputCell = null;

    function closeModal() {
        modal.classList.add('hidden');
        modal.classList.remove('flex');
        currentInputCell = null;
    }

    document.querySelectorAll('.day-input').forEach(input => {
        input.addEventListener('dblclick', function() {
            if (this.disabled) return;

            const taskId = this.dataset.taskId;
            const dateStr = this.dataset.date;
            const hiddenComment = document.getElementById(`comment_${taskId}_${dateStr}`);

            currentInputCell = {
                taskId: taskId,
                dateStr: dateStr,
                hiddenInput: hiddenComment,
                visibleInput: this,
            };

            if (modalDateInfo) {
                modalDateInfo.innerText = `Adding details for ${dateStr}`;
            }
            if (modalTextarea && hiddenComment) {
                modalTextarea.value = hiddenComment.value;
            }

            modal.classList.remove('hidden');
            modal.classList.add('flex');
            if (modalTextarea) {
                modalTextarea.focus();
            }
        });
    });

    if (modalCancel) modalCancel.addEventListener('click', closeModal);
    if (closeModalIcon) closeModalIcon.addEventListener('click', closeModal);

    if (modalSave) {
        modalSave.addEventListener('click', () => {
            if (currentInputCell && modalTextarea) {
                const text = modalTextarea.value;
                if (currentInputCell.hiddenInput) {
                    currentInputCell.hiddenInput.value = text;
                }

                const indicator = document.getElementById(
                    `indicator_${currentInputCell.taskId}_${currentInputCell.dateStr}`
                );

                if (text.trim() !== '') {
                    if (indicator) indicator.classList.remove('hidden');
                    currentInputCell.visibleInput.classList.add('bg-blue-50');
                } else {
                    if (indicator) indicator.classList.add('hidden');
                    currentInputCell.visibleInput.classList.remove('bg-blue-50');
                }

                window.isTimesheetDirty = true;
            }
            closeModal();
        });
    }
});
