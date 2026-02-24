# Milestones and Risks

## Milestones
M1: Core protocol path
- CA key/CSR generation and certificate storage
- AP sign_in and get_accesspoint_config
- Heartbeat HTTP + UDP loop
- Message WebSocket connect and basic session_message

M2: Streams and files
- session_create_stream_req
- Text stream push
- Binary stream with MU header
- File upload/download via OSS

M3: Persistence and resiliency
- SQLite schema and message persistence
- Reconnect/backoff logic
- Metrics collection and snapshots

M4: Mobile SDKs
- Android JNI binding, AAR packaging
- iOS ObjC++ binding, XCFramework packaging
- Example apps

M5: Stabilization
- Performance tuning and long running tests
- Documentation and release notes

## Risks and Mitigations
- Protocol mismatch: add verbose logging and capture raw traffic for debug.
- TLS issues: provide configurable CA root and test with staging certs.
- Network variability: aggressive backoff and offline queue.
- Resource leaks: strict lifecycle management and leak tests.
- Performance regressions: profiling on low end devices.
