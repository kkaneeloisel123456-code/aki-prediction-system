#!/bin/bash
set -euo pipefail
if [[ $EUID -ne 0 ]]; then
    echo 'Run with sudo bash deploy/install.sh' >&2
    exit 1
fi
source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
for program in docker git python3 nginx systemctl flock; do
    command -v "$program" >/dev/null
done
nginx_site=${1:-/etc/nginx/conf.d/aki.conf}
if [[ ! -f "$nginx_site" ]]; then
    echo "Nginx site does not exist: $nginx_site" >&2
    exit 1
fi
# Refuse installation while an update is running. The same file is used by Python.
install -d -m 0755 /opt/aki-deploy /var/lib/aki-deploy /etc/nginx/snippets
exec 9>/var/lib/aki-deploy/deploy.lock
flock -n 9
for file in deploy.sh release_deploy.py sqlite_snapshot.py Dockerfile runtime-constraints.txt; do
    install -m 0644 "$source_dir/$file" "/opt/aki-deploy/$file"
done
chmod 0755 /opt/aki-deploy/deploy.sh
if [[ ! -e /etc/aki-deploy.json ]]; then
    install -m 0600 "$source_dir/config.example.json" /etc/aki-deploy.json
fi
printf '%s\n' 'if (-f /var/lib/aki-deploy/maintenance) { return 503; }' \
    > /etc/nginx/snippets/aki-release-maintenance.conf
chmod 0644 /etc/nginx/snippets/aki-release-maintenance.conf

# Add just one managed include to the existing application server block.
python3 - "$nginx_site" <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil
import subprocess
import sys

site = Path(sys.argv[1])
text = site.read_text(encoding="utf-8")
include = "include /etc/nginx/snippets/aki-release-maintenance.conf;"
if include not in text:
    if len(re.findall(r"\bserver\s*\{", text)) != 1 or "127.0.0.1:8000" not in text:
        raise SystemExit("Expected exactly one existing AKI reverse-proxy server block")
    updated = re.sub(r"(\bserver\s*\{)", r"\1\n    " + include, text, count=1)
    backup = site.with_name(site.name + ".before-release-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    shutil.copy2(site, backup)
    site.write_text(updated, encoding="utf-8")
    if subprocess.run(["nginx", "-t"]).returncode:
        shutil.copy2(backup, site)
        raise SystemExit("Nginx check failed; original site configuration restored")
else:
    subprocess.run(["nginx", "-t"], check=True)
PY
systemctl reload nginx
install -m 0644 "$source_dir/aki-release.service" /etc/systemd/system/aki-release.service
install -m 0644 "$source_dir/aki-release.timer" /etc/systemd/system/aki-release.timer
systemctl daemon-reload
# Start the first deployment explicitly after reviewing the installed configuration.
# Enabling a timer here could otherwise race that first deployment.
echo 'Installed. First run: sudo systemctl start aki-release.service'
echo 'After verification: sudo systemctl enable --now aki-release.timer'
