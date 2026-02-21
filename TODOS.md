# TODOs

This file tracks operational and deployment tasks in a format that can be copied into GitHub Issues, Linear, or any ticketing system.

## Immediate

- [ ] Investigate intermittent `500 Internal Server Error` seen from WAN clients after app-wrapper LaunchAgent switch; capture failing `gateway_request` lines and confirm backend health during incidents.
- [ ] Verify poke.com transport mode and lock server mode to one endpoint (`/mcp` stream or `/sse` SSE).
- [ ] Re-enable API key auth after poke transport is confirmed, then re-test from WAN and LAN.
- [ ] Add one canonical "poke setup" section to `README.md` with exact URL, transport, and header fields.

## Reliability

- [ ] Add `scripts/deploy.sh` to run `git pull`, `uv sync`, `./scripts/restart.sh`, and `./scripts/status.sh`.
- [ ] Add `launchctl` helper script for `start|stop|restart|status`.
- [ ] Rotate old logs or add basic log retention notes to avoid noisy historical errors.

## Deployment Workflow (Deferred)

- [ ] Introduce a dedicated deploy branch (`production`) and deploy only from that branch.
- [ ] Run service from a clean deploy checkout (separate from local dev workspace).
- [ ] Add commit-hash tracking in status output from deploy checkout.
- [ ] Define rollback procedure (checkout previous commit + restart + verify).

## CI/CD (Deferred)

- [ ] Add GitHub Actions workflow for deploy on push to `production`.
- [ ] Configure self-hosted runner on mac mini for deployment jobs.
- [ ] Record deployed commit SHA and timestamp to a local `DEPLOYED_VERSION` file.
- [ ] Add post-deploy smoke tests (`/mcp` and/or `/sse`) in CI log output.

## Security (Deferred)

- [ ] Decide on long-term auth strategy (header API key vs HTTPS tunnel auth).
- [ ] If exposing over public internet, enforce TLS endpoint (tunnel or reverse proxy) and document it.
- [ ] Rotate API keys periodically and document key rotation runbook.

