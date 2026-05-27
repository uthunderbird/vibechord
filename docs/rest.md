# REST API Reference

Status: `verified`

The local REST surface uses `/v1` paths and shared application contracts.

## Endpoints

- `GET /v1/health`
- `GET /v1/agents`
- `GET /v1/fleet`
- `POST /v1/operations`
- `GET /v1/operations/{operation_id}`
- `POST /v1/operations/{operation_id}/commands`
- `POST /v1/operations/{operation_id}/messages`
- `POST /v1/operations/{operation_id}/attention`
- `GET /v1/operations/{operation_id}/events?after=N`
- `GET /v1/operations/{operation_id}/live?after=N`

Mutating requests require `Idempotency-Key`.

When REST auth is configured, requests require:

```text
Authorization: Bearer TOKEN
```

Token options:

- `--token TOKEN`: admin token; can read and mutate.
- `--read-token TOKEN`: read-only token; can call `GET` endpoints.
- `--control-token TOKEN`: control token; can call `GET` and mutating `POST`
  endpoints.

Read-only tokens receive `403 forbidden` for mutating requests. Missing or
unknown bearer tokens receive `401 unauthorized`.

Configured tokens are hashed in memory before request comparison; request
authorization uses constant-time digest comparison.

## Safety

Default binding is loopback. Non-loopback binding requires at least one
configured token or `--unsafe`.

`--unsafe` is for development only.

Production mode:

```sh
uv run vibechord serve --host 0.0.0.0 --production --tls-cert cert.pem --token TOKEN
```

In production mode, non-loopback REST:

- rejects `--unsafe`;
- requires configured bearer-token auth;
- requires a TLS certificate;
- sends `Cache-Control: no-store`;
- sends `X-Content-Type-Options: nosniff`.
