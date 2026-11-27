"""Exercise release transactions without accessing Docker, GitHub or patient data."""
from contextlib import closing, contextmanager
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import urllib.error

import pytest

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "deploy" / (name + ".py"))
    assert spec is not None and spec.loader is not None
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


deploy = module("release_deploy")
sqlite_helper = module("sqlite_snapshot")
COMMIT = "b" * 40
OLD_COMMIT = "a" * 40


@pytest.fixture
def config(tmp_path):
    result = json.loads((ROOT / "deploy/config.example.json").read_text(encoding="utf-8"))
    result["state_dir"] = str(tmp_path / "state")
    result["maintenance_file"] = str(tmp_path / "maintenance")
    result["health_timeout_seconds"] = 0.01
    return result


def old_container():
    return {
        "Id": "old-id", "Image": "old-image", "State": {"Running": True},
        "Config": {"Env": ["AKI_DB_PATH=/data/clinical.db", "AKI_AUTH_CONFIG=/data/auth_config.json", "AKI_CUSTOM=preserved"]},
        "Mounts": [{"Destination": "/data", "Type": "volume", "Name": "aki-data"}],
        "HostConfig": {"NetworkMode": "bridge", "PortBindings": {
            "8000/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8000"}],
        }},
    }


class Docker:
    def __init__(self):
        self.containers = {"aki-system": old_container()}
        self.commands = []

    def run(self, *args, **kwargs):
        self.commands.append(args)
        command = args[1]
        if command == "inspect":
            return json.dumps([self.containers[args[2]]]) if args[2] in self.containers else ""
        if command == "stop":
            self.containers[args[-1]]["State"]["Running"] = False
        elif command == "rename":
            self.containers[args[3]] = self.containers.pop(args[2])
        elif command == "run" and "--name" in args:
            name = args[args.index("--name") + 1]
            container = old_container()
            container.update(Id="new-id", Image=args[-1])
            container["NetworkSettings"] = {"Ports": {"8000/tcp": [{"HostPort": "9876"}]}}
            self.containers[name] = container
        elif command == "start":
            self.containers[args[2]]["State"]["Running"] = True
        elif command == "rm":
            self.containers.pop(args[-1], None)
        return ""


class Harness(deploy.Deployer):
    def __init__(self, config):
        self.docker = Docker()
        super().__init__(config, self.docker)
        self.events = []
        self.fail_candidate = False
        self.fail_preflight = False

    @contextmanager
    def lock(self):
        yield True

    def latest(self, tag=None):
        return {"tag_name": tag or "v1.1.2"}

    def fetch(self, tag):
        return COMMIT, self.state

    def build(self, *args):
        self.events.append(("build",))
        return "candidate-image"

    def helper(self, image, *args, **kwargs):
        self.events.append(("helper", image, *args))

    def maintenance_on(self):
        self.maintenance.write_text("maintenance", encoding="ascii")
        self.events.append(("maintenance",))

    def preflight(self, *args):
        self.events.append(("preflight",))
        if self.fail_preflight:
            raise RuntimeError("candidate rejected")

    def healthy(self, port, timeout=None):
        self.events.append(("health", port))
        current = self.docker.containers.get(self.container)
        if self.fail_candidate and current and current["Image"] == "candidate-image":
            raise RuntimeError("new model failed")


def test_success_keeps_data_volume_and_records_exact_version(config):
    app = Harness(config)
    app.deploy()
    state = deploy.read_json(app.current_path)
    assert state["tag"] == "v1.1.2" and state["commit"] == COMMIT
    commands = app.docker.commands
    launch = next(c for c in commands if c[:2] == ("docker", "run") and "--name" in c)
    assert "aki-data:/data" in launch and "127.0.0.1:8000:8000" in launch
    assert "AKI_CUSTOM=preserved" in launch
    assert app.docker.containers[state["rollback_container"]]["State"]["Running"] is False
    assert not app.journal_path.exists() and not app.maintenance.exists()
    final_snapshot = next(e for e in app.events if e[:3] == ("helper", "old-image", "snapshot"))
    assert final_snapshot[-1] == state["snapshot"]


def test_failed_candidate_restores_snapshot_and_original_container(config):
    app = Harness(config)
    previous = {"tag": "v1.1.1", "commit": OLD_COMMIT}
    deploy.write_json(app.current_path, previous)
    app.fail_candidate = True
    with pytest.raises(RuntimeError, match="new model"):
        app.deploy()
    assert app.docker.containers[app.container]["Id"] == "old-id"
    assert app.docker.containers[app.container]["State"]["Running"] is True
    restores = [e for e in app.events if e[:3] == ("helper", "old-image", "restore")]
    assert len(restores) == 1 and "/release-" in restores[0][3]
    assert restores[0][4] == "/data/clinical.db"
    assert deploy.read_json(app.current_path) == previous
    assert not app.journal_path.exists() and not app.maintenance.exists()
    assert deploy.read_json(app.failed_path)["tag"] == "v1.1.2"
    assert any(name.startswith("aki-failed-") for name in app.docker.containers)


def test_preflight_failure_never_stops_production(config):
    app = Harness(config)
    app.fail_preflight = True
    with pytest.raises(RuntimeError, match="candidate rejected"):
        app.deploy()
    assert not any(c[:2] == ("docker", "stop") for c in app.docker.commands)
    assert not app.maintenance.exists() and not app.journal_path.exists()
    assert app.docker.containers[app.container]["Id"] == "old-id"


def test_failed_rollback_keeps_maintenance_and_recovery_journal(config):
    app = Harness(config)
    def no_health(*args, **kwargs):
        raise RuntimeError("health unavailable")
    app.healthy = no_health
    with pytest.raises(RuntimeError, match="health unavailable"):
        app.deploy()
    assert app.maintenance.exists() and app.journal_path.exists()
    assert app.docker.containers[app.container]["Id"] == "old-id"


def test_missing_nginx_gate_refuses_cutover(config, monkeypatch):
    app = Harness(config)
    app.maintenance_on = lambda: deploy.Deployer.maintenance_on(app)
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
    monkeypatch.setattr(deploy.urllib.request, "urlopen", lambda *a, **k: Response())
    with pytest.raises(RuntimeError, match="maintenance gate"):
        app.deploy()
    assert not any(c[:2] == ("docker", "stop") for c in app.docker.commands)
    assert app.docker.containers[app.container]["Id"] == "old-id"
    assert not app.maintenance.exists()


def test_same_release_does_not_build_or_restart(config):
    app = Harness(config)
    deploy.write_json(app.current_path, {"tag": "v1.1.2", "commit": COMMIT})
    app.deploy()
    assert app.events == [("health", 8000)]
    assert not app.docker.commands


def test_failed_release_is_cooled_down(config):
    app = Harness(config)
    deploy.write_json(app.failed_path, {"tag": "v1.1.2", "time": deploy.time.time()})
    app.deploy()
    assert app.events == [] and app.docker.commands == []
    app.deploy(retry=True)
    assert deploy.read_json(app.current_path)["tag"] == "v1.1.2"


def test_interrupted_cutover_recovers_before_contacting_github(config):
    app = Harness(config)
    old = app.docker.containers.pop("aki-system")
    old["State"]["Running"] = False
    app.docker.containers["aki-rollback-interrupted"] = old
    app.docker.containers["aki-system"] = {**deepcopy(old), "Id": "new-id", "Image": "candidate-image"}
    deploy.write_json(app.journal_path, {
        "old_id": "old-id", "old_image": "old-image", "replacement_started": True,
        "rollback_container": "aki-rollback-interrupted", "failed_container": "aki-failed-interrupted",
        "snapshot": "/data/deploy-backups/release-interrupted.db", "previous_state": None,
    })
    def unavailable(tag=None):
        assert app.docker.containers["aki-system"]["Id"] == "old-id"
        raise RuntimeError("API down")
    app.latest = unavailable
    with pytest.raises(RuntimeError, match="API down"):
        app.deploy()
    assert not app.journal_path.exists() and not app.maintenance.exists()


def test_repeated_recovery_stops_old_writer_before_database_restore(config):
    app = Harness(config)
    journal = {
        "old_id": "old-id", "old_image": "old-image", "replacement_started": True,
        "rollback_container": "aki-rollback-interrupted", "failed_container": "aki-failed-interrupted",
        "snapshot": "/data/deploy-backups/release-interrupted.db", "previous_state": None,
    }
    def assert_stopped(image, *args, **kwargs):
        assert not app.docker.containers["aki-system"]["State"]["Running"]
        app.events.append(("restore",))
    app.helper = assert_stopped
    app.rollback(journal)
    assert app.events[0] == ("restore",)
    assert app.docker.containers["aki-system"]["State"]["Running"]


def test_completed_rollback_journal_never_restores_database_again(config):
    app = Harness(config)
    deploy.write_json(app.journal_path, {"rolled_back": True})
    def unavailable(tag=None):
        raise RuntimeError("API down")
    app.latest = unavailable
    with pytest.raises(RuntimeError, match="API down"):
        app.deploy()
    assert app.events == [("health", 8000)]
    assert not app.journal_path.exists()
    assert not app.docker.commands


def test_preflight_uses_separate_volume_and_loopback_ephemeral_port(config):
    app = Harness(config)
    deploy.Deployer.preflight(app, "candidate-image", old_container(), "/data/deploy-backups/preflight-test.db")
    launch = next(c for c in app.docker.commands if c[:2] == ("docker", "run"))
    assert "127.0.0.1::8000" in launch
    assert "aki-data:/data" not in launch
    assert any(value.startswith("aki-preflight-data-") and value.endswith(":/data") for value in launch)
    assert app.events[0][2:] == ("clone", "/source/deploy-backups/preflight-test.db", "/data")
    assert any(c[:3] == ("docker", "volume", "rm") for c in app.docker.commands)


@pytest.mark.parametrize("release", [
    {"tag_name": "v1.2.0", "draft": True},
    {"tag_name": "v1.2.0", "prerelease": True},
    {"tag_name": "main"}, {"tag_name": "v1.2.0-rc1"}, {"tag_name": "../../etc"},
])
def test_unpublished_or_unsafe_release_is_rejected(config, monkeypatch, release):
    app = deploy.Deployer(config, Docker())
    monkeypatch.setattr(deploy, "request_json", lambda *a, **k: release)
    with pytest.raises(ValueError):
        app.latest()


def test_api_failure_keeps_running_service(config, monkeypatch):
    app = Harness(config)
    app.latest = lambda tag=None: deploy.Deployer.latest(app, tag)
    def unavailable(*a, **k):
        raise urllib.error.URLError("offline")
    monkeypatch.setattr(deploy, "request_json", unavailable)
    monkeypatch.setattr(deploy.time, "sleep", lambda *a: None)
    with pytest.raises(RuntimeError, match="left unchanged"):
        app.deploy()
    assert app.docker.commands == [] and not app.maintenance.exists()


@pytest.mark.parametrize("bad_part", ["health", "schema", "frontend"])
def test_unhealthy_model_invalid_openapi_or_missing_frontend_is_rejected(config, monkeypatch, bad_part):
    app = deploy.Deployer(config, Docker())
    def json_response(url, **kwargs):
        if url.endswith("/api/health"):
            return {"status": "ok", "model_loaded": bad_part != "health", "database_ok": True}
        return {"openapi": "3.1.0", "paths": {} if bad_part == "schema" else {"/api/health": {}}}
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self, *args):
            return b"<html>nginx welcome</html>"
    monkeypatch.setattr(deploy, "request_json", json_response)
    monkeypatch.setattr(deploy.urllib.request, "urlopen", lambda *a, **k: Response())
    monkeypatch.setattr(deploy.time, "sleep", lambda *a: None)
    with pytest.raises(RuntimeError, match="verification timed out"):
        app.healthy(8000)


@pytest.mark.parametrize("mutation", ["volume", "public_port", "custom_database"])
def test_unexpected_production_configuration_is_rejected(config, mutation):
    app = Harness(config)
    current = app.docker.containers["aki-system"]
    if mutation == "volume":
        current["Mounts"][0]["Name"] = "another-volume"
    elif mutation == "public_port":
        current["HostConfig"]["PortBindings"]["8000/tcp"][0]["HostIp"] = "0.0.0.0"
    else:
        current["Config"]["Env"] = ["AKI_DB_PATH=/data/other.db"]
    with pytest.raises(RuntimeError):
        app.old_container()


def test_snapshot_restore_includes_uncheckpointed_wal(tmp_path):
    database = tmp_path / "clinical.db"
    writer = sqlite3.connect(database)
    try:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("CREATE TABLE markers (name TEXT)")
        writer.execute("INSERT INTO markers VALUES ('before-release')")
        writer.commit()
        snapshot = tmp_path / "release-test.db"
        sqlite_helper.snapshot(database, snapshot)
        writer.execute("INSERT INTO markers VALUES ('failed-migration')")
        writer.commit()
        assert Path(str(database) + "-wal").stat().st_size > 0
    finally:
        writer.close()
    emergency = tmp_path / "emergency.db"
    sqlite_helper.restore(snapshot, database, emergency)
    assert not Path(str(database) + "-wal").exists()
    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute("SELECT name FROM markers").fetchall() == [("before-release",)]
    with closing(sqlite3.connect(emergency)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM markers").fetchone()[0] == 2
    assert not Path(str(database) + "-wal").exists()


def test_corrupt_migration_can_restore_verified_snapshot(tmp_path):
    source = tmp_path / "source.db"
    with closing(sqlite3.connect(source)) as connection:
        connection.execute("CREATE TABLE markers (name TEXT)")
    snapshot = tmp_path / "release-test.db"
    sqlite_helper.snapshot(source, snapshot)
    source.write_bytes(b"a failed migration destroyed the database")
    sqlite_helper.restore(snapshot, source, tmp_path / "emergency.db")
    sqlite_helper.validate(source)
    assert (tmp_path / "emergency.corrupt").exists()


def test_checksum_failure_never_replaces_production_database(tmp_path):
    source = tmp_path / "source.db"
    with closing(sqlite3.connect(source)) as connection:
        connection.execute("CREATE TABLE markers (name TEXT)")
    snapshot = tmp_path / "release-test.db"
    sqlite_helper.snapshot(source, snapshot)
    snapshot.with_suffix(".sha256").write_text("bad checksum")
    before = source.read_bytes()
    with pytest.raises(RuntimeError, match="SHA-256"):
        sqlite_helper.restore(snapshot, source, tmp_path / "emergency.db")
    assert source.read_bytes() == before


def test_retention_leaves_application_and_emergency_backups(tmp_path):
    for kind, count in (("release", 7), ("preflight", 4), ("clinical", 4), ("emergency", 2)):
        for index in range(count):
            path = tmp_path / f"{kind}-{index:02}.db"
            path.touch()
            path.with_suffix(".sha256").touch()
    sqlite_helper.prune(tmp_path, 5)
    assert len(list(tmp_path.glob("release-*.db"))) == 5
    assert len(list(tmp_path.glob("preflight-*.db"))) == 2
    assert len(list(tmp_path.glob("clinical-*.db"))) == 4
    assert len(list(tmp_path.glob("emergency-*.db"))) == 2
