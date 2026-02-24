# Scope and Goals

## Objectives
- Build a C++ cross-platform IM client SDK based on the AP AID system.
- Support Android and iOS with thin platform bindings (JNI / ObjC++).
- Implement end-to-end flows: AID creation, AP authentication, heartbeat, message, stream, file transfer, and local persistence.
- Provide a stable API surface with clear error handling, metrics, and logging.

## In Scope
- Client side protocol implementation for CA, AP, Heartbeat, Message, and OSS file servers.
- Session management, message dispatch, stream push, and file upload/download.
- Local storage layout and SQLite persistence.
- Reconnect, retry, and lifecycle management.
- Android and iOS SDK packaging with example usage.

## Out of Scope
- Server side development (CA/AP/HB/MSG/OSS).
- UI implementation.
- LLM proxy or workflow engine beyond stubs.

## Target Platforms
- Android: NDK (C++17), Java/Kotlin API, AAR packaging.
- iOS: C++17 core, ObjC++ bridge, Swift-friendly API, XCFramework packaging.

## Constraints
- Must be compatible with existing AP AID protocol and message format.
- Must support TLS verification by default with a configurable override.
- Must operate under mobile network variability (background, reconnect, NAT).
- Keep dependencies minimal and portable.

## Assumptions
- CA/AP/HB/MSG/OSS endpoints are available and stable.
- The AP sign_in flow uses ECDSA P-384 keys and certificates.
- Message server uses WebSocket with the documented JSON envelope.

## Success Criteria
- Can log in and establish a WebSocket session on both Android and iOS.
- Can send and receive session messages reliably.
- Can create and push streams, including file streams.
- Can upload/download files via OSS using signature token.
- Can survive network loss and recover without data loss.
