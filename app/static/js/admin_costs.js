document.addEventListener('DOMContentLoaded', function() {
    const pricingForm = document.getElementById('pricing-form');

    // Fetch initial prices and populate the form
    fetch('/api/admin/pricing')
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                console.error('Error fetching prices:', data.error);
                return;
            }
            for (const type in data) {
                for (const key in data[type]) {
                    const inputId = `${type}-${key.toUpperCase()}`;
                    const input = document.getElementById(inputId);
                    if (input) {
                        input.value = data[type][key];
                    } else {
                        // Fallback for case inconsistency
                        const lowerCaseInput = document.getElementById(`${type}-${key.toLowerCase()}`);
                        if (lowerCaseInput) {
                            lowerCaseInput.value = data[type][key];
                        }
                    }
                }
            }
        })
        .catch(error => console.error('Error fetching prices:', error));

    // Handle form submission
    pricingForm.addEventListener('submit', function(event) {
        event.preventDefault();
        const formData = new FormData(pricingForm);
        const payload = {};
        // Iterate over all input elements in the form to build the data payload
        pricingForm.querySelectorAll('input[type="number"]').forEach(input => {
            const name = input.name; // e.g., "workflow-openai"
            const value = input.value;
            const type = input.dataset.type; // e.g., "workflow"
            const modelId = name.substring(name.indexOf('-') + 1); // e.g., "gemini-1.5-flash"

            if (value) {
                if (!payload[type]) {
                    payload[type] = {};
                }
                // Use the full modelId as the key
                payload[type][modelId] = parseLocaleNumber(value);
            }
        });

        const csrfToken = document.querySelector('input[name="csrf_token"]').value;

        fetch('/api/admin/pricing', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify(payload),
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showNotification('Prices updated successfully!', 'success', 3000, false);
            } else {
                showNotification(`Error updating prices: ${data.error}`, 'error', 5000, true);
            }
        })
        .catch(error => {
            console.error('Error updating prices:', error);
            showNotification('An unexpected error occurred.', 'error', 5000, true);
        });
    });
});