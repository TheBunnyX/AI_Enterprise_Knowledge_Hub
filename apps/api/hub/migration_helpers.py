"""Schema changes that are safe to repeat.

Migration 0001 creates the tables from the models as they are *today*, so on a new database the columns and tables that
later migrations add are already there. These helpers apply a change only when it is still missing; on a database that
has grown step by step they behave exactly like the plain alembic operations.
"""
import sqlalchemy as sa
from alembic import op


def _inspector(): return sa.inspect(op.get_bind())

def has_table(table): return table in _inspector().get_table_names()

def has_column(table, column): return has_table(table) and column in {c['name'] for c in _inspector().get_columns(table)}

def add_column(table, column):
    if not has_column(table, column.name): op.add_column(table, column)

def drop_column(table, column):
    if has_column(table, column): op.drop_column(table, column)

def create_table(name, *columns, **options):
    if not has_table(name): op.create_table(name, *columns, **options)

def create_index(name, table, columns, **options):
    if has_table(table) and name not in {i['name'] for i in _inspector().get_indexes(table)}: op.create_index(name, table, columns, **options)
