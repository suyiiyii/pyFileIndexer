from pathlib import Path
from datetime import datetime
import pytest


from fastapi.testclient import TestClient
from pyFileIndexer.database import db_manager
from pyFileIndexer.web_server import create_app
from pyFileIndexer.models import FileMeta, FileHash


@pytest.fixture
def tmp_db(tmp_path):
    db_path = tmp_path / "test.db"
    db_manager.init(f"sqlite:///{db_path}")
    return db_path


@pytest.fixture
def client(tmp_db):
    app = create_app()
    return TestClient(app)


def add_files(files):
    batch = []
    for meta, hash_obj in files:
        batch.append({"file_meta": meta, "file_hash": hash_obj, "operation": "ADD"})
    db_manager.add_files_batch(batch)


def make_meta(name, path, machine, size, ts):
    return (
        FileMeta(
            name=name,
            path=path,
            machine=machine,
            created=ts,
            modified=ts,
            scanned=ts,
            operation="ADD",
            hash_id=None,
        ),
        FileHash(size=size, md5=f"md5-{name}", sha1=f"sha1-{name}", sha256=f"sha256-{name}")
    )


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "healthy"}


def test_files_pagination_and_filters(client):
    ts = datetime(2024, 1, 1, 12, 0, 0)
    f1 = make_meta("a.txt", "/root/a.txt", "M1", 100, ts)
    f2 = make_meta("b.log", "/root/b.log", "M1", 200, ts)
    f3 = make_meta("c.txt", "/root/sub/c.txt", "M2", 300, ts)
    add_files([f1, f2, f3])

    r = client.get("/api/files", params={"page": 1, "per_page": 2})
    j = r.json()
    assert r.status_code == 200
    assert j["page"] == 1
    assert j["per_page"] == 2
    assert j["total"] == 3

    r2 = client.get(
        "/api/files",
        params={"name": ".txt", "machine": "M1", "min_size": 50, "max_size": 150},
    )
    j2 = r2.json()
    assert r2.status_code == 200
    assert j2["total"] == 1


def test_search(client):
    ts = datetime(2024, 1, 1, 12, 0, 0)
    f1 = make_meta("doc.pdf", "/docs/doc.pdf", "M", 1000, ts)
    add_files([f1])

    r1 = client.get("/api/search", params={"query": "doc.pdf", "search_type": "name"})
    assert r1.status_code == 200
    assert len(r1.json()) == 1

    r2 = client.get("/api/search", params={"query": "/docs", "search_type": "path"})
    assert r2.status_code == 200
    assert len(r2.json()) == 1

    md5 = f1[1].md5
    r3 = client.get("/api/search", params={"query": md5, "search_type": "hash"})
    assert r3.status_code == 200
    assert len(r3.json()) == 1


def test_statistics(client):
    ts = datetime(2024, 1, 1, 12, 0, 0)
    f1 = make_meta("x.bin", "/p/x.bin", "A", 1024, ts)
    f2 = make_meta("y.bin", "/p/y.bin", "A", 2048, ts)
    f3 = make_meta("z.bin", "/p/z.bin", "B", 4096, ts)
    add_files([f1, f2, f3])

    r = client.get("/api/statistics")
    j = r.json()
    assert r.status_code == 200
    assert j["total_files"] == 3
    assert j["total_size"] == 1024 + 2048 + 4096
    assert j["machine_stats"]["A"] == 2
    assert j["machine_stats"]["B"] == 1


def test_duplicates(client):
    ts = datetime(2024, 1, 1, 12, 0, 0)
    h = FileHash(size=2_000_000, md5="dupe", sha1="s", sha256="t")
    m1 = FileMeta(name="a.bin", path="/d/a.bin", machine="M", created=ts, modified=ts, scanned=ts, operation="ADD")
    m2 = FileMeta(name="b.bin", path="/d/b.bin", machine="M", created=ts, modified=ts, scanned=ts, operation="ADD")
    db_manager.add_files_batch([
        {"file_meta": m1, "file_hash": h, "operation": "ADD"},
        {"file_meta": m2, "file_hash": h, "operation": "ADD"},
    ])

    r = client.get(
        "/api/duplicates",
        params={"min_size": 0, "min_count": 2, "page": 1, "per_page": 10},
    )
    j = r.json()
    assert r.status_code == 200
    assert j["total_groups"] >= 1
    assert j["total_files"] >= 2


def test_tree(client):
    ts = datetime(2024, 1, 1, 12, 0, 0)
    f1 = make_meta("a.txt", "/root/a.txt", "TM", 100, ts)
    f2 = make_meta("b.txt", "/root/dir/b.txt", "TM", 200, ts)
    add_files([f1, f2])

    r_root = client.get("/api/tree", params={"path": ""})
    assert r_root.status_code == 200

    r_tm = client.get("/api/tree", params={"path": "/TM"})
    assert r_tm.status_code == 200
