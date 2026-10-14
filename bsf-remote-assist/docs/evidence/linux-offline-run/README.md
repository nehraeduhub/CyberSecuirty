# Evidence: automated acceptance run (Linux test endpoints, no Internet)

Produced by `tests/local-stack/run-offline.sh` on 2026-10-14. The whole stack ran in a network namespace
with only a loopback interface (`routes: 0`, see `run.log`). `report.json` lists all 44 checks (all passed)
and the session records. Screenshots are numbered in workflow order; `remote-consent-prompt-5.jpg` is the
attended PC's own screen showing the agent's Yes/No prompt, `08-pc2-…` and `21-pc1-…` are the endpoint screens.
The TOTP secret in `05-…` is redacted. Host names are the test names `remote.bsf.test` / `mesh.remote.bsf.test`;
both test PCs report the container host name `vm`.

This is **not** the Windows acceptance; see docs/ACCEPTANCE-TEST.md §2.
