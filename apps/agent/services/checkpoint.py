"""Checkpointer: Postgres (bền, dùng chung giữa các worker); test thay bằng bộ nhớ."""

from django.conf import settings
from langgraph.checkpoint.memory import InMemorySaver

_override = None
_pg = None


def set_checkpointer(c) -> None:
    global _override
    _override = c


def get_checkpointer():
    global _pg
    if _override is not None:
        return _override
    if _pg is None:
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        cfg = settings.DATABASES["default"]
        conninfo = f"postgresql://{cfg['USER']}:{cfg['PASSWORD']}@{cfg['HOST']}:{cfg['PORT']}/{cfg['NAME']}"
        pool = ConnectionPool(
            conninfo, kwargs={"autocommit": True, "row_factory": dict_row}, open=True
        )
        _pg = PostgresSaver(pool)
        _pg.setup()  # tạo bảng checkpoint nếu chưa có (idempotent)
    return _pg


__all__ = ["InMemorySaver", "get_checkpointer", "set_checkpointer"]
