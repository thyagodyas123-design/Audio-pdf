from alembic import context

from audiopdf.db.models import Base

engine = context.config.attributes.get("engine")
if engine is None:  # `alembic` direto na linha de comando
    from audiopdf.db import engine as get_engine
    engine = get_engine()

with engine.begin() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=connection.dialect.name == "sqlite")
    with context.begin_transaction():
        context.run_migrations()
