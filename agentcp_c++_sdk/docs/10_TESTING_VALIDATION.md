# Testing and Validation

## Test Layers
- Unit tests: serialization, crypto signing, header parsing, DB layer.
- Integration tests: AP sign_in, HB sign_in, WS connect.
- End-to-end: message send/receive, stream push, file upload/download.
- Stress tests: high concurrency, long running sessions, reconnect loops.

## Test Environments
- Local dev environment with real servers.
- Staging environment for release validation.

## Coverage Goals
- Core protocol paths: 100 percent happy path coverage.
- Error handling: token expiry, WS disconnect, HB NextBeat 401.
- Storage: schema migration and recovery.

## Tooling
- Mock servers for AP and HB.
- WebSocket test harness for message and stream.
- OSS test bucket with predictable data.

## Validation Checklist
- Android and iOS both complete login and message flow.
- File upload and download success.
- Stream text and binary both work.
- Reconnect after network loss without crash or message loss.
- TLS verification passes with real certs.
