# Evidence: acceptance test against the Docker deployment made by `setup.sh install`

2026-10-15. A fresh copy of the bundle was installed with
`ASSUME_YES=1 PORTAL_HOSTNAME=remote.bsf.local MESH_HOSTNAME=mesh.remote.bsf.local SERVER_IP=10.20.30.40 ./setup.sh install`
(images built from the repository Dockerfiles; installer-generated internal CA). `tests/e2e/run_e2e.py` was then run
against `https://remote.bsf.local` with two Linux test PCs: **44 passed, 0 failed** (`report.json`, `run.log`).
This run used the host network (not the isolated namespace; see `../linux-offline-run/` for the no-Internet proof).
`setup.sh status`, `backup`, `restart` (data persisted) and `reset-admin-password` were also exercised.
