"""Pull stable GitHub releases and replace the existing Docker application safely.

Installed at /opt/aki-deploy; application checkouts and metadata live separately
under /var/lib/aki-deploy. Run as root through the supplied systemd service.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any

LOG = logging.getLogger("aki-deploy")
HERE = Path(__file__).resolve().parent
TAG = re.compile(r"v[0-9]+\.[0-9]+\.[0-9]+\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]


def read_json(path: Path, default: Any = None) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        os.chmod(temporary, 0o600)
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


class Runner:
    def run(self, *args: str, check=True, timeout=180, output: Path | None = None) -> str:
        with output.open("w", encoding="utf-8") if output else open(os.devnull, "w") as stream:
            result = subprocess.run(
                args, text=True, stdout=stream if output else subprocess.PIPE,
                stderr=subprocess.STDOUT if output else subprocess.PIPE,
                timeout=timeout, check=False,
            )
        if result.returncode and check:
            detail = f"; log: {output}" if output else f": {(result.stderr or '')[-1500:]}"
            raise RuntimeError(f"{args[0]} exited {result.returncode}{detail}")
        if not check and result.returncode:
            return ""
        return (result.stdout or "").strip()


def request_json(url: str, *, headers=None):
    request = urllib.request.Request(url, headers={"User-Agent": "aki-release-deployer", **(headers or {})})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


class Deployer:
    def __init__(self, config: dict, runner=None):
        self.cfg = config
        self.run = (runner or Runner()).run
        self.state = Path(config["state_dir"])
        self.maintenance = Path(config["maintenance_file"])
        self.container = config["container"]
        self.volume = config["data_volume"]
        self.port = int(config["port"])
        self.host = config["public_host"]
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", self.container + self.volume):
            raise ValueError("Invalid Docker resource name")
        if not re.fullmatch(r"[A-Za-z0-9.-]+", self.host):
            raise ValueError("Invalid public host")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", config["repository"]):
            raise ValueError("Invalid GitHub repository")
        if not self.state.is_absolute() or not self.maintenance.is_absolute():
            raise ValueError("Deployment paths must be absolute")
        self.state.mkdir(parents=True, exist_ok=True)
        self.current_path = self.state / "current.json"
        self.journal_path = self.state / "transaction.json"
        self.failed_path = self.state / "failed.json"

    @contextmanager
    def lock(self):
        import fcntl
        with (self.state / "deploy.lock").open("a") as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore[attr-defined]  # Linux-only API
            except BlockingIOError:
                LOG.info("Another deployment is running; skipped")
                yield False
                return
            yield True

    def latest(self, tag=None) -> dict:
        if tag is not None and not TAG.fullmatch(tag):
            raise ValueError("Expected a stable vX.Y.Z release tag")
        suffix = "latest" if not tag else "tags/" + urllib.parse.quote(tag, safe="")
        url = f"https://api.github.com/repos/{self.cfg['repository']}/releases/{suffix}"
        error = None
        for attempt in range(3):
            try:
                release = request_json(url, headers={"Accept": "application/vnd.github+json"})
                if release.get("draft") or release.get("prerelease") or not TAG.fullmatch(release.get("tag_name", "")):
                    raise ValueError("Only published stable vX.Y.Z releases are deployable")
                if tag and release["tag_name"] != tag:
                    raise ValueError("GitHub returned a different release")
                return release
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                error = exc
                if attempt < 2:
                    time.sleep(2 ** (attempt + 1))
        raise RuntimeError("GitHub release API unavailable; running service was left unchanged") from error

    def inspect(self, name: str) -> Any:
        text = self.run("docker", "inspect", name, check=False)
        return json.loads(text)[0] if text else None

    def old_container(self) -> dict:
        old = self.inspect(self.container)
        if not old or not old["State"]["Running"]:
            raise RuntimeError("Expected an existing running application container")
        mounts = [m for m in old["Mounts"] if m["Destination"] == "/data"]
        if len(mounts) != 1 or mounts[0].get("Type") != "volume" or mounts[0].get("Name") != self.volume:
            raise RuntimeError("Production data volume differs from deployment configuration")
        ports = old["HostConfig"].get("PortBindings", {}).get("8000/tcp", [])
        if ports != [{"HostIp": "127.0.0.1", "HostPort": str(self.port)}]:
            raise RuntimeError("Expected the existing application to bind only to the configured loopback port")
        if old["HostConfig"].get("NetworkMode", "default") not in ("default", "bridge"):
            raise RuntimeError("Custom Docker networks require an explicit deployment configuration review")
        if any(m["Destination"] != "/data" for m in old["Mounts"]):
            raise RuntimeError("Extra container mounts require an explicit deployment configuration review")
        environment = dict(item.split("=", 1) for item in old["Config"].get("Env", []))
        for key, path in (("AKI_DB_PATH", "/data/clinical.db"), ("AKI_AUTH_CONFIG", "/data/auth_config.json")):
            if environment.get(key, path) != path:
                raise RuntimeError("Custom application data paths require a deployment configuration review")
        return old

    def fetch(self, tag: str) -> tuple[str, Path]:
        repository = self.state / "repository.git"
        remote = f"https://github.com/{self.cfg['repository']}.git"
        if not repository.exists():
            self.run("git", "init", "--bare", str(repository))
            self.run("git", "--git-dir", str(repository), "remote", "add", "origin", remote)
        actual_remote = self.run("git", "--git-dir", str(repository), "remote", "get-url", "origin")
        if actual_remote != remote:
            raise RuntimeError("Deployment Git remote changed unexpectedly")
        # No force: a previously seen release tag must not be silently replaced.
        self.run("git", "--git-dir", str(repository), "fetch", "--no-tags", "origin",
                 f"refs/tags/{tag}:refs/tags/{tag}", timeout=180)
        commit = self.run("git", "--git-dir", str(repository), "rev-parse", f"refs/tags/{tag}^{{commit}}")
        if not SHA.fullmatch(commit):
            raise RuntimeError("Invalid release commit")
        current = read_json(self.current_path, {})
        if current.get("commit") and current["commit"] != commit:
            # Prevent an older / unrelated release from replacing a newer baseline.
            common = self.run("git", "--git-dir", str(repository), "merge-base", current["commit"], commit)
            if common != current["commit"]:
                raise RuntimeError("Release is older than, or diverges from, the deployed version")
        checkout = self.state / "releases" / commit
        checkout.parent.mkdir(parents=True, exist_ok=True)
        if not checkout.exists():
            self.run("git", "--git-dir", str(repository), "worktree", "add", "--detach", str(checkout), commit)
        if self.run("git", "-C", str(checkout), "rev-parse", "HEAD") != commit:
            raise RuntimeError("Build checkout does not match the release")
        if self.run("git", "-C", str(checkout), "status", "--porcelain", "--untracked-files=no"):
            raise RuntimeError("Release checkout has tracked local modifications")
        return commit, checkout

    def build(self, tag: str, commit: str, checkout: Path) -> str:
        if shutil.disk_usage(self.state).free < 5 * 1024 ** 3:
            raise RuntimeError("Less than 5 GiB free; retain the current service and clean up old images first")
        image = "aki-system:release-" + commit[:16]
        shutil.copyfile(HERE / "runtime-constraints.txt", checkout / ".aki-runtime-constraints.txt")
        self.run(
            "docker", "build", "--pull=false", "-f", str(HERE / "Dockerfile"), "-t", image,
            "--label", f"org.opencontainers.image.revision={commit}",
            "--label", f"org.opencontainers.image.version={tag}",
            "--build-arg", f"NODE_IMAGE={self.cfg['node_image']}",
            "--build-arg", f"PYTHON_IMAGE={self.cfg['python_image']}",
            "--build-arg", f"PIP_INDEX_URL={self.cfg['pip_index_url']}",
            "--build-arg", f"NPM_CONFIG_REGISTRY={self.cfg['npm_registry']}",
            str(checkout), timeout=1800, output=self.state / f"build-{tag}.log",
        )
        return image

    def helper(self, image: str, *args: str, clone_volume=None):
        command = ["docker", "run", "--rm", "--network", "none", "--user", "0" if clone_volume else "10001",
                   "-v", f"{self.volume}:/source:ro" if clone_volume else f"{self.volume}:/data"]
        if clone_volume:
            command += ["-v", f"{clone_volume}:/data"]
        self.run(*command, "--entrypoint", "python", image, "-c",
                 (HERE / "sqlite_snapshot.py").read_text(encoding="utf-8"), *args)

    def environment(self, old: dict) -> list[str]:
        # Preserve application settings without writing or printing secret values.
        result = []
        for entry in old["Config"].get("Env", []):
            key = entry.split("=", 1)[0]
            if key.startswith("AKI_") or key in {"OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"}:
                result += ["-e", entry]
        result += ["-e", "PORT=8000"]
        return result

    def healthy(self, port: int, timeout=None) -> None:
        end = time.monotonic() + (timeout if timeout is not None else self.cfg["health_timeout_seconds"])
        error = None
        while time.monotonic() < end:
            try:
                base = f"http://127.0.0.1:{port}"
                health = request_json(base + "/api/health")
                if health.get("status") != "ok" or health.get("model_loaded") is not True or health.get("database_ok") is not True:
                    raise ValueError("Application/model/database health failed")
                schema = request_json(base + "/openapi.json")
                if not schema.get("openapi") or "/api/health" not in schema.get("paths", {}):
                    raise ValueError("OpenAPI validation failed")
                with urllib.request.urlopen(base + "/", timeout=10) as response:
                    html = response.read(1024 * 1024).decode("utf-8")
                scripts = re.findall(r'<script[^>]+src="([^"]+)"', html)
                if "<html" not in html.lower() or not scripts:
                    raise ValueError("Frontend HTML is missing its built JavaScript")
                for script in scripts:
                    if not script.startswith("/assets/") or ".." in script:
                        raise ValueError("Unexpected frontend asset URL")
                    with urllib.request.urlopen(base + script, timeout=10) as response:
                        if "javascript" not in response.headers.get("Content-Type", ""):
                            raise ValueError("Frontend JavaScript asset failed")
                return
            except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
                error = exc
                time.sleep(2)
        raise RuntimeError("Application health/OpenAPI/frontend verification timed out") from error

    def preflight(self, image: str, old: dict, snapshot: str) -> None:
        identity = uuid.uuid4().hex[:12]
        container, volume = "aki-preflight-" + identity, "aki-preflight-data-" + identity
        self.run("docker", "volume", "create", volume)
        try:
            self.helper(old["Image"], "clone", snapshot.replace("/data/", "/source/", 1), "/data", clone_volume=volume)
            self.run("docker", "run", "-d", "--name", container, "--restart", "no",
                     "--memory", "768m", "--pids-limit", "256", "-p", "127.0.0.1::8000",
                     "-v", f"{volume}:/data", *self.environment(old), image)
            inspected = self.inspect(container)
            port = int(inspected["NetworkSettings"]["Ports"]["8000/tcp"][0]["HostPort"])
            self.healthy(port)
        finally:
            self.run("docker", "rm", "-f", container, check=False)
            self.run("docker", "volume", "rm", volume, check=False)

    def maintenance_on(self):
        self.maintenance.write_text("AKI release deployment in progress\n", encoding="ascii")
        os.chmod(self.maintenance, 0o644)
        request = urllib.request.Request("http://127.0.0.1/", headers={"Host": self.host})
        try:
            with urllib.request.urlopen(request, timeout=10):
                pass
        except urllib.error.HTTPError as exc:
            if exc.code == 503:
                return
        raise RuntimeError("Nginx maintenance gate is not active; refusing to replace production")

    def rollback(self, journal: dict) -> None:
        LOG.warning("Restoring the previous container and its database snapshot")
        self.maintenance.write_text("AKI rollback in progress\n", encoding="ascii")
        os.chmod(self.maintenance, 0o644)
        old_name = journal["rollback_container"]
        renamed_old = self.inspect(old_name)
        current = self.inspect(self.container)
        if current and current["Id"] != journal["old_id"]:
            self.run("docker", "update", "--restart=no", self.container)
            self.run("docker", "stop", "--time", "120", self.container)
            self.run("docker", "rename", self.container, journal["failed_container"])
        # Restore only after a replacement container could have opened the DB.
        if journal.get("replacement_started"):
            # A previous recovery attempt may have already renamed/started the old
            # container. Stop every possible writer before repeating a restore.
            for name in (self.container, old_name):
                writer = self.inspect(name)
                if writer and writer["State"]["Running"]:
                    self.run("docker", "update", "--restart=no", name)
                    self.run("docker", "stop", "--time", "120", name)
            self.helper(journal["old_image"], "restore", journal["snapshot"], "/data/clinical.db",
                        "/data/deploy-backups/emergency-" + stamp() + ".db")
        if renamed_old:
            self.run("docker", "rename", old_name, self.container)
        policy = journal.get("old_restart_policy", {"Name": "unless-stopped"})
        restart = policy.get("Name") or "no"
        if restart == "on-failure" and policy.get("MaximumRetryCount"):
            restart += ":" + str(policy["MaximumRetryCount"])
        self.run("docker", "update", "--restart=" + restart, self.container)
        self.run("docker", "start", self.container)
        self.healthy(self.port)
        if journal.get("previous_state") is None:
            self.current_path.unlink(missing_ok=True)
        else:
            write_json(self.current_path, journal["previous_state"])
        journal["rolled_back"] = True
        write_json(self.journal_path, journal)
        self.maintenance.unlink(missing_ok=True)
        self.journal_path.unlink(missing_ok=True)
        LOG.warning("Rollback verified; public access restored")

    def replace(self, tag: str, commit: str, image: str, old: dict) -> None:
        identity = stamp()
        journal = {
            "tag": tag, "commit": commit, "old_id": old["Id"], "old_image": old["Image"],
            "rollback_container": "aki-rollback-" + identity,
            "failed_container": "aki-failed-" + identity,
            "snapshot": "/data/deploy-backups/release-" + identity + ".db",
            "replacement_started": False, "previous_state": read_json(self.current_path),
            "old_restart_policy": old["HostConfig"].get("RestartPolicy", {"Name": "unless-stopped"}),
        }
        # Journal first: a power loss at any following step is recoverable next run.
        write_json(self.journal_path, journal)
        try:
            self.maintenance_on()
            self.run("docker", "stop", "--time", "120", self.container)
            self.helper(old["Image"], "snapshot", "/data/clinical.db", journal["snapshot"])
            # A reboot must not resurrect the retained old container alongside the new one.
            self.run("docker", "update", "--restart=no", self.container)
            self.run("docker", "rename", self.container, journal["rollback_container"])
            # Record before docker run: even a timeout may have started the new process.
            journal["replacement_started"] = True
            write_json(self.journal_path, journal)
            self.run("docker", "run", "-d", "--name", self.container, "--restart", "unless-stopped",
                     "-p", f"127.0.0.1:{self.port}:8000", "-v", f"{self.volume}:/data",
                     *self.environment(old), image)
            self.healthy(self.port)
            write_json(self.current_path, {
                "tag": tag, "commit": commit, "image": image, "deployed_at": identity,
                "rollback_container": journal["rollback_container"], "snapshot": journal["snapshot"],
            })
            # A committed transaction is never rolled back after user access resumes.
            journal["committed"] = True
            write_json(self.journal_path, journal)
        except BaseException:
            try:
                self.rollback(journal)
            except BaseException:
                LOG.exception("ROLLBACK NEEDS ATTENTION; maintenance remains enabled")
            raise
        self.maintenance.unlink(missing_ok=True)
        self.journal_path.unlink(missing_ok=True)
        LOG.info("Deployed %s (%s)", tag, commit[:12])

    def deploy(self, tag=None, retry=False) -> None:
        with self.lock() as acquired:
            if not acquired:
                return
            journal = read_json(self.journal_path)
            if journal:
                if journal.get("committed") or journal.get("rolled_back"):
                    # Health was verified and state committed before a crash.
                    self.healthy(self.port)
                    self.maintenance.unlink(missing_ok=True)
                    self.journal_path.unlink()
                else:
                    self.rollback(journal)
            release = self.latest(tag)
            tag = release["tag_name"]
            failed = read_json(self.failed_path, {})
            if not retry and failed.get("tag") == tag and time.time() - failed["time"] < self.cfg["failure_cooldown_seconds"]:
                LOG.warning("Release %s failed recently; waiting before retry", tag)
                return
            current = read_json(self.current_path, {})
            # Even for the same tag, fetch verifies it has not been moved.
            commit, checkout = self.fetch(tag)
            if current.get("tag") == tag and current.get("commit") == commit:
                self.healthy(self.port, timeout=10)
                LOG.info("Already running %s; no build or restart", tag)
                return
            old = self.old_container()
            try:
                image = self.build(tag, commit, checkout)
                online_snapshot = "/data/deploy-backups/preflight-" + stamp() + ".db"
                # Online consistent snapshot; serving container remains available.
                self.run("docker", "exec", self.container, "python", "-c",
                         (HERE / "sqlite_snapshot.py").read_text(encoding="utf-8"),
                         "snapshot", "/data/clinical.db", online_snapshot)
                self.preflight(image, old, online_snapshot)
                self.replace(tag, commit, image, old)
            except BaseException:
                write_json(self.failed_path, {"tag": tag, "commit": commit, "time": time.time()})
                raise
            self.failed_path.unlink(missing_ok=True)
            # Pruning is post-commit housekeeping; it must not trigger a rollback.
            try:
                self.helper(image, "prune", "/data/deploy-backups", str(self.cfg["retain_backups"]))
            except Exception:
                LOG.exception("Release succeeded; backup retention needs attention")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("/etc/aki-deploy.json"))
    parser.add_argument("--tag", help="Deploy a specific published stable release; downgrades are refused")
    parser.add_argument("--retry", action="store_true", help="Retry a failed release without waiting one hour")
    parser.add_argument("--status", action="store_true", help="Print the last verified deployment metadata")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if sys.platform != "linux":
        parser.error("Deployment is supported only on the Linux server")
    if os.geteuid() != 0:
        parser.error("Run through systemd or sudo")
    os.umask(0o077)

    def interrupted(signum, frame):
        raise RuntimeError(f"Deployment interrupted by signal {signum}")

    signal.signal(signal.SIGTERM, interrupted)
    deployer = Deployer(read_json(args.config))
    if args.status:
        print(json.dumps(read_json(deployer.current_path, {}), indent=2))
        return 0
    try:
        deployer.deploy(args.tag, args.retry)
    except Exception:
        LOG.exception("Deployment did not complete")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
