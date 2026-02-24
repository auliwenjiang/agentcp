# Integration Guide

This document explains how to build Android and iOS artifacts from this repo and
how to consume them from host applications.

## Output Artifacts
- Android: AAR containing JNI shared libraries and Java API.
- iOS: XCFramework containing static libraries and Objective-C headers.

## Android

### Build AAR
Prerequisites:
- Android SDK + NDK installed
- CMake (3.18+)
- Gradle

Build command:
```
cd android
./gradlew assembleRelease
```

Output:
- android/build/outputs/aar/agentcp-release.aar

### Integrate into an Android app
1) Copy the AAR into your app module (for example: app/libs/agentcp-release.aar).
2) Add the dependency in your app build.gradle:
```
dependencies {
    implementation files('libs/agentcp-release.aar')
}
```
3) Ensure the app ABI filters match the AAR:
```
android {
    defaultConfig {
        ndk { abiFilters 'armeabi-v7a', 'arm64-v8a', 'x86_64' }
    }
}
```

### Minimal usage
```
AgentCP acp = AgentCP.getInstance();
Result r = acp.initialize();
if (!r.ok()) { /* handle error */ }

AgentID aid = acp.createAID("alice.ap.example.com", "password123");
Result online = aid.online();
```

## iOS

### Build XCFramework
Prerequisites:
- Xcode (for iphoneos/iphonesimulator SDKs)
- CMake (3.18+)

Build command:
```
./ios/build_xcframework.sh
```

Output:
- build/AgentCP.xcframework

### Integrate into an iOS app
1) Drag build/AgentCP.xcframework into your Xcode project.
2) In the app target, add AgentCP.xcframework to "Frameworks, Libraries, and Embedded Content".
3) Import headers where needed:
```
#import <AgentCP/AgentCP.h>
```

### Minimal usage
```
ACPAgentCP *acp = [ACPAgentCP shared];
ACPResult *result = [acp initialize];
if (![result ok]) { /* handle error */ }

ACPResult *error = nil;
ACPAgentID *aid = [acp createAID:@"alice.ap.example.com"
                    seedPassword:@"password123"
                           error:&error];
```

## Notes
- Current implementation is a compile-ready skeleton. Networking, storage,
  and protocol logic are not implemented yet.
- JNI and ObjC++ layers currently expose core lifecycle methods only.
