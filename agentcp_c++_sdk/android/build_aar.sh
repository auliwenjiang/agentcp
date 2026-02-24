#!/bin/bash
# AgentCP Android AAR Build Script

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "AgentCP Android AAR Build"
echo "=========================================="

# Check for Android SDK
if [ -z "$ANDROID_HOME" ] && [ -z "$ANDROID_SDK_ROOT" ]; then
    echo "Error: ANDROID_HOME or ANDROID_SDK_ROOT environment variable not set"
    exit 1
fi

# Clean previous builds
echo "[1/4] Cleaning previous builds..."
./gradlew clean

# Build debug AAR
echo "[2/4] Building debug AAR..."
./gradlew assembleDebug

# Build release AAR
echo "[3/4] Building release AAR..."
./gradlew assembleRelease

# Publish to local repository
echo "[4/4] Publishing to local Maven repository..."
./gradlew publishReleasePublicationToLocalRepository

echo ""
echo "=========================================="
echo "Build completed successfully!"
echo "=========================================="
echo ""
echo "Output files:"
echo "  Debug AAR:   build/outputs/aar/agentcp-android-debug.aar"
echo "  Release AAR: build/outputs/aar/agentcp-android-release.aar"
echo "  Maven repo:  build/repo/com/agentcp/agentcp-sdk/0.1.0/"
echo ""
