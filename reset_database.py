# reset_database.py
import sys
import os
import logging

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.database import get_db
from app.initialization import initialize_database_schema

logging.basicConfig(level=logging.INFO)

def reset_db():
    """
    Drops all tables and re-initializes the database schema and default data.
    """
    app = create_app()
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        try:
            logging.warning("--- STARTING DATABASE RESET ---")
            
            # Disable foreign key checks to allow dropping tables in any order
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
            
            # Get all table names
            cursor.execute("SHOW TABLES")
            tables = [row[0] for row in cursor.fetchall()]
            
            if not tables:
                logging.info("No tables found to drop.")
            else:
                logging.info(f"Found tables to drop: {tables}")
                for table in tables:
                    logging.info(f"Dropping table: {table}")
                    cursor.execute(f"DROP TABLE IF EXISTS `{table}`")
            
            # Re-enable foreign key checks
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
            db.commit()
            logging.info("All tables dropped successfully.")

            # Re-initialize the schema and default data
            logging.info("Re-initializing database schema and default roles/admin...")
            initialize_database_schema(create_roles=True)
            logging.info("--- DATABASE RESET COMPLETE ---")

        except Exception as e:
            logging.error(f"An error occurred during database reset: {e}", exc_info=True)
            db.rollback()
        finally:
            cursor.close()

if __name__ == "__main__":
    reset_db()