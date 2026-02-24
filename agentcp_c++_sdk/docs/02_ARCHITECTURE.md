# Architecture

## High Level View
The SDK is split into three layers:

1) Core (C++): Protocol, runtime, storage, and scheduler.
2) Platform Adapters: OS-specific services (threading, network hints, background modes).
3) Bindings: JNI for Android and ObjC++ for iOS.

```
+------------------------------+
| Android App / iOS App        |
+------------------------------+
| JNI / ObjC++ Bindings        |
+------------------------------+
| Platform Adapters            |
+------------------------------+
| Core C++ SDK                 |
+------------------------------+
| CA / AP / HB / MSG / OSS     |
+------------------------------+
```

## Core Subsystems
- Identity and Auth: CAClient, AuthClient, ApClient
- Transport: HTTP, WebSocket, UDP, Stream push
- Session and Message: SessionManager, Session, MessageClient
- Stream and File: StreamClient, FileClient
- Persistence: DBManager, local file storage
- Runtime Services: Scheduler, Metrics, Monitoring, ErrorContext

## Build and Packaging
- CMake builds the core static library and platform shared libraries.
- Android produces an AAR and native .so.
- iOS produces an XCFramework.

## Dependency Strategy
- OpenSSL for ECDSA P-384 and TLS validation
- libcurl (or platform HTTP) for REST and file transfer
- websocket-client (or platform WebSocket) for message server and stream push
- SQLite for local persistence
- zlib for stream compression
- JSON library for serialization

## Configuration Management
- Global configuration (AP base, CA base, proxy, TLS policy)
- Per-AID runtime configuration
- Runtime reload for signature refresh and endpoint update

## Logging and Telemetry
- Log levels: ERROR, WARN, INFO, DEBUG, TRACE
- Metrics: message latency, queue sizes, reconnect counts
- Optional hooks to export metrics to app analytics
