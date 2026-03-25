"""
Custom SQLite database backend that supports GIS fields as TEXT.
Inherits from Django's default SQLite backend and adds geo_db_type support.
"""
from django.db.backends.sqlite3.base import (
    DatabaseWrapper as SQLiteDatabaseWrapper,
)
from django.db.backends.sqlite3.operations import (
    DatabaseOperations as SQLiteOperations,
)


class DatabaseOperations(SQLiteOperations):
    """Extended SQLite operations with GIS field type support."""

    # Used by GIS field select_format() to wrap the column SQL.
    # '%s' means no transformation — read the TEXT value as-is.
    select = '%s'

    # Map GIS field types to TEXT for storage
    def geo_db_type(self, f):
        return 'TEXT'

    def get_geom_placeholder(self, f, value, compiler):
        return '%s'


class DatabaseWrapper(SQLiteDatabaseWrapper):
    ops_class = DatabaseOperations
