# Building and transferring images for an offline (MPLS-only) server

The server never pulls from the Internet. Images are built once on a connected **build host**, saved to a
tar file, checked, carried in, and loaded.

## On the build host (Internet access, Docker)

```bash
git clone <this repository> && cd bsf-remote-assist
docker compose build            # web, frontend (npm ci from package-lock.json), meshcentral (meshcentral@1.2.5 + modules)
docker pull postgres:17-alpine redis:7-alpine nginx:1.29-alpine
docker save -o bsf-remote-images.tar \
  bsf-remote/web:2.0.0 bsf-remote/frontend:2.0.0 bsf-remote/meshcentral:1.2.5 \
  postgres:17-alpine redis:7-alpine nginx:1.29-alpine
sha256sum bsf-remote-images.tar > bsf-remote-images.tar.sha256
```

The MeshCentral image installs, at build time, the extra npm modules MeshCentral would otherwise try to
download on first start (`image-size`, `https-proxy-agent`), and the rendered configuration sets
`npmPath` to `/bin/false` so it can never attempt a download at run time. Code-signing of agents uses
MeshCentral's own certificate with `agentTimeStampServer: false` (no Internet timestamp server).

Scan the tar with the organisation's malware/vulnerability tooling before transfer.

## On the BSF Remote server (no Internet)

```bash
sha256sum -c bsf-remote-images.tar.sha256
docker load -i bsf-remote-images.tar
```

Then follow DEPLOYMENT.md. `deploy/preflight.sh` fails if any image is missing; `deploy/install.sh`
starts with `--no-build`, so nothing is fetched.

## Upgrades

Never `docker compose pull` on the server. Rebuild with the new pinned version on the build host,
validate it in the pilot environment (run `tests/` and the Windows acceptance), back up
(`deploy/backup-postgres.sh` also archives MeshCentral data), then load and restart.
