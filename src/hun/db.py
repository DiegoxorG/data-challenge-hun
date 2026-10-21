"""Conexión a la BD del HUN (PostgreSQL, por la VPN que da el hospital)."""
from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine

from . import config


def engine() -> Engine:
    p = config.pg_params()
    url = URL.create(
        "postgresql+psycopg2",
        username=p["user"], password=p["password"],
        host=p["host"], port=p["port"], database=p["dbname"],
    )
    return create_engine(
        url,
        connect_args={"options": f"-csearch_path={config.schema()}"},
        hide_parameters=True,  # que los errores no impriman valores de los datos
    )


def ping() -> None:
    """Prueba de conexión que no toca datos de pacientes."""
    with engine().connect() as con:
        version = con.execute(text("select version()")).scalar()
    print("Conexión OK:", version.split(",")[0])
