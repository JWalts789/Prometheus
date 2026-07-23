#!/usr/bin/env bash
# PROMETHEUS — two-plane user setup.  RUN AS AN ADMIN (uses sudo).
# Creates `keeper` (admin = the leash) and `prom` (standard = the body), and the
# filesystem boundary between them.  If you're unsure, create the users in the GUI
# instead (System Settings > Users & Groups) and run only the chmod/mkdir parts.
# VERIFY before running.
set -euo pipefail

echo "==> creating users (sysadminctl; macOS 10.13+)"
sudo sysadminctl -addUser keeper -fullName "Keeper" -admin     || echo "  (keeper may already exist)"
sudo sysadminctl -addUser prom   -fullName "Prometheus"        || echo "  (prom may already exist)"

echo "==> keeper home is PRIVATE — prom must not read it"
sudo chmod 700 /Users/keeper

echo "==> shared dir for the append-only journal SOCKET (the only cross-user channel)"
sudo mkdir -p /Users/Shared/prometheus
sudo chmod 1777 /Users/Shared/prometheus     # sticky + world-usable, for the socket + logs

echo "==> keeper-owned dirs: journal, frozen probes, adapters, sandbox profiles"
sudo -u keeper mkdir -p /Users/keeper/prometheus/adapters \
                         /Users/keeper/prometheus/probes \
                         /Users/keeper/prometheus/profiles
sudo chmod -R 700 /Users/keeper/prometheus

echo "==> prom workspace (the agent's writable world)"
sudo -u prom mkdir -p /Users/prom/workspace

echo
echo "VERIFY NOW:  su - prom -c 'ls /Users/keeper'   # MUST print 'Permission denied'"
echo "Then copy sandbox/prom.sb to /Users/keeper/prometheus/profiles/ and launch OpenClaw wrapped:"
echo "  sandbox-exec -f /Users/keeper/prometheus/profiles/prom.sb openclaw gateway run --bind loopback"
