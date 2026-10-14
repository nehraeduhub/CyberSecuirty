# Windows Agent — Stage 7

Stage 7 deliberately separates two functions:

* **BSF Remote management heartbeat** — device identity, health, portal enrollment and approval state.
* **MeshCentral agent** — the actual remote-control engine (desktop, terminal, files, power actions, etc.).

The Stage 7 package does not ship a fabricated remote-control binary. The MeshCentral agent must be downloaded/generated from the exact MeshCentral server/version deployed by the administrator, then distributed internally after signature/hash verification.

## Files

* `bsf_remote_agent.py` — heartbeat client.
* `config.example.json` — example configuration.
* `install-agent.ps1` — local installation helper.
* `Product.wxs` — WiX source for a future signed MSI wrapper; compile/sign it in the organization's Windows build pipeline.

## Production requirements

* Code-sign the management scripts/binaries with the organization's certificate.
* Protect the enrollment token; never place a shared token in a domain-wide script.
* Use TLS with an internal CA or publicly trusted certificate as appropriate.
* Allow only the portal's required HTTPS endpoint from endpoint networks.
* Pin and verify the MeshCentral agent version before enterprise rollout.
