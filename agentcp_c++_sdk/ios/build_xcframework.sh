#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_DIR="$ROOT_DIR/build/ios"
OUTPUT_DIR="$ROOT_DIR/build"

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

cmake -S "$ROOT_DIR/ios" -B "$BUILD_DIR/device" -G Xcode \
  -DCMAKE_SYSTEM_NAME=iOS \
  -DCMAKE_OSX_ARCHITECTURES=arm64 \
  -DCMAKE_OSX_DEPLOYMENT_TARGET=12.0

cmake --build "$BUILD_DIR/device" --config Release

cmake -S "$ROOT_DIR/ios" -B "$BUILD_DIR/sim" -G Xcode \
  -DCMAKE_SYSTEM_NAME=iOS \
  -DCMAKE_OSX_ARCHITECTURES="arm64;x86_64" \
  -DCMAKE_OSX_DEPLOYMENT_TARGET=12.0 \
  -DCMAKE_OSX_SYSROOT=iphonesimulator

cmake --build "$BUILD_DIR/sim" --config Release

xcodebuild -create-xcframework \
  -library "$BUILD_DIR/device/Release-iphoneos/libagentcp_ios.a" -headers "$ROOT_DIR/ios/include" \
  -library "$BUILD_DIR/sim/Release-iphonesimulator/libagentcp_ios.a" -headers "$ROOT_DIR/ios/include" \
  -output "$OUTPUT_DIR/AgentCP.xcframework"

echo "XCFramework created at $OUTPUT_DIR/AgentCP.xcframework"
