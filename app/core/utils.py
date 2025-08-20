# app/core/utils.py
# Contains core utility functions for the application.

def format_currency(value: float) -> str:
    """
    Formats a float value into a currency string with a dollar sign
    and two decimal places.
    """
    if value is None:
        return "$0.00"
    return f"${value:,.2f}"
