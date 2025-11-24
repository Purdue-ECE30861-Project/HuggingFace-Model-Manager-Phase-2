from sqlalchemy import Engine, create_engine
from sqlmodel import SQLModel, Session
from typing_extensions import Literal


def db_reset(engine: Engine) -> bool:
    """
    Reset the database by deleting all data from all tables.
    Returns True if successful, False if an error occurred.
    """
    try:
        with Session(engine) as session:
            # Get all table objects from SQLModel metadata
            tables = SQLModel.metadata.tables.values()

            # Delete all data from each table in reverse dependency order
            # This helps avoid foreign key constraint issues
            for table in reversed(list(tables)):
                session.exec(table.delete())

            session.commit()
            return True

    except Exception as e:
        # Log the error if you have logging set up
        # logger.error(f"Failed to reset database: {e}")
        return False