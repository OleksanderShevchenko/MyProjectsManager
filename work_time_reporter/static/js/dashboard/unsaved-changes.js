/**
 * Tracks unsaved timesheet input changes and warns before tab or page navigation.
 */
window.isTimesheetDirty = false;

document.addEventListener('DOMContentLoaded', () => {
    // Mark dirty when user types into any number input
    document.querySelectorAll('input[type="number"]').forEach(input => {
        input.addEventListener('input', () => {
            window.isTimesheetDirty = true;
        });
    });

    // Clear dirty flag when user submits form (Save Draft or Submit)
    document.querySelectorAll('button[type="submit"]').forEach(btn => {
        btn.addEventListener('click', () => {
            window.isTimesheetDirty = false;
        });
    });

    // Warn user before navigating away with unsaved changes
    window.addEventListener('beforeunload', (e) => {
        if (window.isTimesheetDirty) {
            e.preventDefault();
            e.returnValue = '';
        }
    });
});
