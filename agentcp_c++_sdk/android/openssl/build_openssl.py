#!/usr/bin/env python3
"""Build OpenSSL for Android (3 ABIs) using NDK toolchain."""

import subprocess
import os
import shutil

NDK = "C:/Users/liwenjiang/AppData/Local/Android/Sdk/ndk/26.1.10909125"
OPENSSL_SRC = "H:/project/agentcp-so/android/openssl/openssl-3.0.15"
OUTPUT_DIR = "H:/project/agentcp-so/android/openssl/prebuilt"
MAKE = f"{NDK}/prebuilt/windows-x86_64/bin/make.exe"
TOOLCHAIN = f"{NDK}/toolchains/llvm/prebuilt/windows-x86_64"
API_LEVEL = "21"

# ABI -> OpenSSL target mapping
TARGETS = {
    "arm64-v8a": {
        "target": "linux-aarch64",
        "triple": f"aarch64-linux-android{API_LEVEL}",
    },
    "armeabi-v7a": {
        "target": "linux-armv4",
        "triple": f"armv7a-linux-androideabi{API_LEVEL}",
    },
    "x86_64": {
        "target": "linux-x86_64",
        "triple": f"x86_64-linux-android{API_LEVEL}",
    },
}

# PLACEHOLDER_MORE

os.makedirs(OUTPUT_DIR, exist_ok=True)

for abi, cfg in TARGETS.items():
    print(f"\n{'='*60}")
    print(f"Building OpenSSL for {abi} ({cfg['target']})")
    print(f"{'='*60}")

    build_dir = f"{OPENSSL_SRC}/build_{abi}"
    install_dir = f"{OUTPUT_DIR}/{abi}"

    # Clean previous build
    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)

    # Copy source to build dir
    shutil.copytree(OPENSSL_SRC, build_dir,
                    ignore=shutil.ignore_patterns("build_*"))

    env = os.environ.copy()
    env["ANDROID_NDK_ROOT"] = NDK
    env["ANDROID_NDK_HOME"] = NDK
    env["PATH"] = f"{TOOLCHAIN}/bin;{NDK}/prebuilt/windows-x86_64/bin;" + env["PATH"]
    # Fix MSYS2 Perl missing Locale::Maketext::Simple
    env["PERL5LIB"] = "H:\\project\\agentcp-so\\android\\openssl\\perl_lib"

    # Set CC/CXX/AR/RANLIB for the NDK toolchain
    cc = f"{TOOLCHAIN}/bin/{cfg['triple']}-clang"
    env["CC"] = cc
    env["CXX"] = f"{cc}++"
    env["AR"] = f"{TOOLCHAIN}/bin/llvm-ar"
    env["RANLIB"] = f"{TOOLCHAIN}/bin/llvm-ranlib"

    # Configure
    configure_cmd = [
        "perl", f"{build_dir}/Configure",
        cfg["target"],
        f"-D__ANDROID_API__={API_LEVEL}",
        f"--prefix={install_dir}",
        f"--sysroot={TOOLCHAIN}/sysroot",
        "-fPIC",
        "no-shared",
        "no-tests",
        "no-ui-console",
        "no-engine",
        "no-comp",
        "no-dso",
        "no-async",
    ]

    print(f"Configuring: {' '.join(configure_cmd[:5])}...")
    r = subprocess.run(configure_cmd, cwd=build_dir, env=env,
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        print(f"Configure FAILED:\n{r.stderr[-500:]}")
        continue
    print("Configure OK")

    # Build
    print("Building (this may take a while)...")
    build_cmd = [MAKE, "-j4", "build_libs"]
    r = subprocess.run(build_cmd, cwd=build_dir, env=env,
                       capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        print(f"Build FAILED:\n{r.stderr[-1000:]}")
        continue
    print("Build OK")

    # Install headers and libs
    os.makedirs(install_dir, exist_ok=True)
    os.makedirs(f"{install_dir}/lib", exist_ok=True)

    # Copy libs
    for lib in ["libssl.a", "libcrypto.a"]:
        src = f"{build_dir}/{lib}"
        dst = f"{install_dir}/lib/{lib}"
        if os.path.exists(src):
            shutil.copy2(src, dst)
            size = os.path.getsize(dst)
            print(f"  Copied {lib} ({size} bytes)")
        else:
            print(f"  WARNING: {lib} not found!")

    # Copy headers (only once, they're the same for all ABIs)
    include_dst = f"{OUTPUT_DIR}/include"
    if not os.path.exists(include_dst):
        shutil.copytree(f"{build_dir}/include/openssl",
                        f"{include_dst}/openssl")
        # Also copy generated opensslconf.h
        for gen in ["include/openssl/opensslconf.h",
                     "include/openssl/configuration.h"]:
            src = f"{build_dir}/{gen}"
            if os.path.exists(src):
                shutil.copy2(src, f"{include_dst}/openssl/")
        print(f"  Copied headers to {include_dst}")

    print(f"Done: {abi}")

# Verify
print(f"\n{'='*60}")
print("Build Summary:")
print(f"{'='*60}")
for abi in TARGETS:
    for lib in ["libssl.a", "libcrypto.a"]:
        path = f"{OUTPUT_DIR}/{abi}/lib/{lib}"
        if os.path.exists(path):
            size = os.path.getsize(path)
            print(f"  {abi}/{lib}: {size:,} bytes")
        else:
            print(f"  {abi}/{lib}: MISSING!")

print(f"\nOutput: {OUTPUT_DIR}")
print("Set OPENSSL_ROOT_DIR to this path in CMake.")
