# app/models/pricing.py
# Defines the Pricing model and database interaction functions for MySQL.

import logging
from typing import Optional, Dict, Any
from mysql.connector import Error as MySQLError
from app.database import get_db, get_cursor

def init_db_command() -> None:
    """Initializes the 'pricing' table schema."""
    cursor = get_cursor()
    log_prefix = "[DB:Schema:MySQL]"
    logging.debug(f"{log_prefix} Checking/Initializing 'pricing' table...")
    try:
        # Ensure the table exists before trying to modify it
        cursor.execute(
            '''
            CREATE TABLE IF NOT EXISTS pricing (
                id INT PRIMARY KEY AUTO_INCREMENT,
                item_key VARCHAR(255) NOT NULL,
                price DECIMAL(18, 8) NOT NULL,
                item_type ENUM('transcription', 'workflow', 'title_generation') NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uq_item_type_key (item_type, item_key),
                INDEX idx_item_key (item_key)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            '''
        )
        get_db().commit()
        logging.debug(f"{log_prefix} 'pricing' table schema verified/initialized.")

        # Drop the old problematic unique key if it exists
        try:
            cursor.execute("ALTER TABLE pricing DROP KEY item_key")
            logging.debug(f"{log_prefix} Dropped old unique key 'item_key'.")
        except MySQLError as e:
            if e.errno == 1091:  # Can't DROP '...'; check that column/key exists
                logging.debug(f"{log_prefix} Old unique key 'item_key' not found, skipping drop.")
            else:
                raise
    except MySQLError as err:
        logging.error(f"{log_prefix} Error during 'pricing' table initialization: {err}", exc_info=True)
        get_db().rollback()
        raise
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass

def get_price(item_key: str, item_type: str) -> Optional[float]:
    """Retrieves the price for a given item key and type."""
    # SWAP to ensure correct order
    if item_type not in ['transcription', 'workflow', 'title_generation']:
        item_key, item_type = item_type, item_key

    log_prefix = f"[DB:Pricing:{item_type}:{item_key}]"
    sql = "SELECT price FROM pricing WHERE item_key = %s AND item_type = %s ORDER BY updated_at DESC LIMIT 1"
    cursor = get_cursor()
    price = None
    try:
        cursor.execute(sql, (item_key, item_type))
        result = cursor.fetchone()
        if result:
            price = float(result['price'])
    except MySQLError as err:
        logging.error(f"{log_prefix} Error retrieving price: {err}", exc_info=True)
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return price


def get_all_prices() -> Dict[str, Any]:
    """Retrieves all prices from the database."""
    log_prefix = "[DB:Pricing]"
    sql = "SELECT item_key, price, item_type FROM pricing"
    cursor = get_cursor()
    prices = {}
    try:
        cursor.execute(sql)
        rows = cursor.fetchall()
        for row in rows:
            if row['item_type'] not in prices:
                prices[row['item_type']] = {}
            prices[row['item_type']][row['item_key']] = float(row['price'])
    except MySQLError as err:
        logging.error(f"{log_prefix} Error retrieving all prices: {err}", exc_info=True)
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass
    return prices

def update_prices(pricing_data: Dict[str, Dict[str, float]]) -> None:
    """
    Updates or inserts prices in the database.
    """
    log_prefix = "[DB:Pricing:Update]"
    sql = """
        INSERT INTO pricing (item_type, item_key, price)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE price = VALUES(price)
    """
    cursor = get_cursor()
    try:
        for item_type, models in pricing_data.items():
            for item_key, price in models.items():
                # --- FIX: Ensure consistency by storing all keys in uppercase ---
                cursor.execute(sql, (item_type, item_key.lower(), price))
        get_db().commit()
        logging.debug(f"{log_prefix} Database prices updated successfully.")
    except MySQLError as err:
        logging.error(f"{log_prefix} Error updating prices in database: {err}", exc_info=True)
        get_db().rollback()
        raise
    finally:
        # The cursor is managed by the application context, so we don't close it here.
        pass