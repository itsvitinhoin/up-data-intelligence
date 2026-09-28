import socket

import pytest


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("Network forbidden in test suite")

    monkeypatch.setattr(socket.socket, "connect", deny)


@pytest.fixture(autouse=True)
def close_local_databases(monkeypatch):
    from src.bigquery.repository import SQLiteRepository

    instances = []
    original = SQLiteRepository.__init__

    def init(self, path):
        original(self, path)
        instances.append(self)

    monkeypatch.setattr(SQLiteRepository, "__init__", init)
    yield
    for instance in instances:
        instance.close()
