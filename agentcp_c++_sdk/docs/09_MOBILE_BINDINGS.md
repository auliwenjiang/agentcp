# Mobile Bindings

## Android
- Build: CMake + Gradle
- Output: AAR with native .so (armeabi-v7a, arm64-v8a, x86_64)
- JNI layer exposes C++ API to Kotlin/Java
- Threading: callbacks from native thread; provide dispatcher helper to main thread

Android API Guidelines
- Use Kotlin data classes for message blocks.
- Provide suspend functions or callback-based APIs.
- Ensure lifecycle integration with foreground/background.

## iOS
- Build: CMake -> static lib -> XCFramework
- ObjC++ bridge exposes C++ API to Swift
- Provide Swift-friendly async APIs and delegate callbacks

iOS API Guidelines
- Use Swift structs for message blocks.
- Keep ObjC++ minimal and move logic to C++ core.
- Handle background execution constraints (voip or background tasks as needed).

## Platform Services
- Network reachability watchers for reconnect hints.
- Persistent storage path mapping to app sandbox.
- Secure storage integration for private keys (optional).

## Example Binding Map
C++ AgentID::Online -> Android AgentID.online() / iOS AgentID.online()
C++ Session::SendMessage -> Android Session.sendMessage() / iOS Session.sendMessage()
