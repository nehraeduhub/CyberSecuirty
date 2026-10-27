# Tests

* `local-stack/` — starts the complete stack on one Ubuntu 24.04 host from the same templates as
  production, and `run-offline.sh` runs stack + acceptance test inside an isolated network namespace.
  Host prerequisites: root, `postgresql-16`, `redis-server`, `nginx`, Node.js 22, `xvfb`, `zenity`,
  `xdotool`, `imagemagick`, `libnss3-tools`, `capsh`, a Python venv with `backend/requirements.txt` and
  `e2e/requirements.txt`, Playwright's Chromium, `npm install meshcentral@1.2.5`, `npm ci` in
  `frontend/`, and a test CA/certificate for both host names (`/etc/hosts` entries pointing to 127.0.0.1).
  Copy `stack.env.example` to `stack.env`, then: `sudo tests/local-stack/run-offline.sh`.
  Each run uses a fresh work directory; stop a run's processes with `WORK=<dir> stop-stack.sh`.
* `e2e/run_e2e.py` — the acceptance scenario (see docs/ACCEPTANCE-TEST.md §1). It can also be pointed
  at a deployed pilot (`PORTAL_URL`, `CA_BUNDLE`, …) for the parts that do not depend on the local test PCs.
* `local-stack/fake-session/` — test-only shims that give headless X displays a logged-in user.
  Never install them on real endpoints.
