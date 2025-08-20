// app/static/js/admin_formatters.js
// This file contains client-side formatting logic for the admin panel.

document.addEventListener('DOMContentLoaded', function() {
    // Format numbers with the 'format-number' class
    document.querySelectorAll('.format-number').forEach(element => {
        const value = parseFloat(element.dataset.value);
        if (isNaN(value)) {
            return; // Skip if the value is not a valid number
        }

        const formatType = element.dataset.format;
        let options;

        switch (formatType) {
            case 'cost':
                options = { minimumFractionDigits: 2, maximumFractionDigits: 5 };
                element.textContent = `$${formatLocaleNumber(value, options)}`;
                return;
            case 'percent':
                // The value for percentages is expected to be the raw number (e.g., 25 for 25%)
                options = { style: 'percent', maximumFractionDigits: 0 };
                element.textContent = formatLocaleNumber(value / 100, options);
                return; // Return early as we've set the text content
            case 'decimal':
                options = { maximumFractionDigits: 1 };
                break;
            case 'integer':
                options = { maximumFractionDigits: 0 };
                break;
            default:
                // If no format is specified, let localization.js handle the default
                options = {};
                break;
        }
    });
});