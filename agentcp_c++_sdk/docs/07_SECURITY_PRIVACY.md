# Security and Privacy

## Key and Certificate Management

### Key Generation
```cpp
// Generate ECDSA P-384 key pair
Result GenerateKeyPair(const std::string& aid) {
    // 1. Generate private key
    EVP_PKEY* pkey = EVP_EC_KEY_new_by_curve_name(NID_secp384r1);
    EVP_PKEY_keygen_init(ctx);
    EVP_PKEY_keygen(ctx, &pkey);

    // 2. Save private key (PEM format, encrypted)
    BIO* bio = BIO_new_file(key_path.c_str(), "w");
    PEM_write_bio_PrivateKey(bio, pkey, EVP_aes_256_cbc(),
                              password, password_len, NULL, NULL);

    // 3. Extract public key
    EVP_PKEY_get_raw_public_key(pkey, pubkey, &pubkey_len);

    return Result::OK();
}
```

### Certificate Storage
```
AIDs/{aid}/private/certs/
├── {aid}.key      # Private key (PEM, AES-256-CBC encrypted)
├── {aid}.crt      # Certificate (PEM)
└── {aid}.csr      # Certificate signing request (PEM)
```

### Platform Secure Storage Integration

#### Android Keystore
```cpp
#ifdef __ANDROID__
// Store private key in Android Keystore
Result StoreKeyInKeystore(const std::string& alias,
                           const std::vector<uint8_t>& key) {
    // Use JNI to call Android KeyStore API
    JNIEnv* env = GetJNIEnv();
    jclass keystore_class = env->FindClass("android/security/keystore/KeyStore");

    // Generate key in hardware-backed keystore
    KeyGenParameterSpec spec = new KeyGenParameterSpec.Builder(
        alias,
        KeyProperties.PURPOSE_SIGN | KeyProperties.PURPOSE_VERIFY
    )
    .setDigests(KeyProperties.DIGEST_SHA256, KeyProperties.DIGEST_SHA512)
    .setUserAuthenticationRequired(false)
    .build();

    KeyPairGenerator generator = KeyPairGenerator.getInstance(
        KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore"
    );
    generator.initialize(spec);
    generator.generateKeyPair();

    return Result::OK();
}
#endif
```

#### iOS Keychain
```cpp
#ifdef __APPLE__
// Store private key in iOS Keychain
Result StoreKeyInKeychain(const std::string& service,
                           const std::string& account,
                           const std::vector<uint8_t>& key) {
    NSDictionary* query = @{
        (__bridge id)kSecClass: (__bridge id)kSecClassKey,
        (__bridge id)kSecAttrService: @(service.c_str()),
        (__bridge id)kSecAttrAccount: @(account.c_str()),
        (__bridge id)kSecValueData: [NSData dataWithBytes:key.data()
                                                    length:key.size()],
        (__bridge id)kSecAttrAccessible: (__bridge id)kSecAttrAccessibleAfterFirstUnlock
    };

    OSStatus status = SecItemAdd((__bridge CFDictionaryRef)query, NULL);
    return status == errSecSuccess ? Result::OK() : Result::Error();
}
#endif
```

## TLS Verification

### Certificate Validation Chain
```cpp
struct TLSValidator {
    // Validate server certificate
    Result ValidateCertificate(X509* cert, const std::string& hostname) {
        // 1. Check certificate validity period
        if (!CheckValidity(cert)) {
            return Result::Error(TLS_CERT_EXPIRED);
        }

        // 2. Verify certificate chain
        X509_STORE* store = X509_STORE_new();
        X509_STORE_CTX* ctx = X509_STORE_CTX_new();
        X509_STORE_CTX_init(ctx, store, cert, NULL);

        if (X509_verify_cert(ctx) != 1) {
            return Result::Error(TLS_CERT_INVALID);
        }

        // 3. Check hostname
        if (!CheckHostname(cert, hostname)) {
            return Result::Error(TLS_HOSTNAME_MISMATCH);
        }

        // 4. Check revocation (OCSP or CRL)
        if (config_.check_revocation) {
            if (!CheckRevocation(cert)) {
                return Result::Error(TLS_CERT_REVOKED);
            }
        }

        return Result::OK();
    }
};
```

### Certificate Pinning
```cpp
struct PinningConfig {
    bool enabled = false;
    std::vector<std::string> pinned_certs;  // SHA256 fingerprints
    bool allow_backup_pins = true;
};

Result ValidatePinning(X509* cert, const PinningConfig& config) {
    if (!config.enabled) return Result::OK();

    // Calculate certificate fingerprint
    unsigned char md[SHA256_DIGEST_LENGTH];
    X509_digest(cert, EVP_sha256(), md, NULL);
    std::string fingerprint = HexEncode(md, SHA256_DIGEST_LENGTH);

    // Check against pinned certificates
    for (const auto& pin : config.pinned_certs) {
        if (fingerprint == pin) {
            return Result::OK();
        }
    }

    return Result::Error(TLS_PIN_MISMATCH);
}
```

## Signature Token Handling

### Token Lifecycle
```cpp
class TokenManager {
public:
    struct Token {
        std::string value;
        uint64_t issued_at;
        uint64_t expires_at;
        bool is_valid() const {
            return GetCurrentTimeMs() < expires_at;
        }
    };

    // Get current token, refresh if needed
    Result GetToken(std::string* token_out) {
        std::lock_guard lock(mutex_);

        if (!current_token_.is_valid()) {
            Result r = RefreshToken();
            if (!r) return r;
        }

        *token_out = current_token_.value;
        return Result::OK();
    }

private:
    Result RefreshToken() {
        // Re-authenticate with AP
        Result r = ap_client_->SignIn(aid_, &new_token);
        if (!r) return r;

        current_token_.value = new_token;
        current_token_.issued_at = GetCurrentTimeMs();
        current_token_.expires_at = current_token_.issued_at + 3600000;  // 1 hour

        return Result::OK();
    }

    Token current_token_;
    std::mutex mutex_;
};
```

### Secure Token Storage
```cpp
// Never log tokens
void LogRequest(const std::string& url, const std::string& body) {
    std::string sanitized_url = RedactToken(url);
    std::string sanitized_body = RedactSensitiveFields(body);
    Logger::Info("Request: {} {}", sanitized_url, sanitized_body);
}

std::string RedactToken(const std::string& url) {
    // Replace signature=xxx with signature=***
    std::regex pattern(R"(signature=[^&]+)");
    return std::regex_replace(url, pattern, "signature=***");
}
```

## Data Privacy

### PII Handling
```cpp
// Redact PII from logs
struct PIIRedactor {
    std::string Redact(const std::string& text) {
        std::string result = text;

        // Email addresses
        result = std::regex_replace(result,
            std::regex(R"(\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b)"),
            "***@***.***");

        // Phone numbers
        result = std::regex_replace(result,
            std::regex(R"(\b\d{3}[-.]?\d{3}[-.]?\d{4}\b)"),
            "***-***-****");

        // Credit card numbers
        result = std::regex_replace(result,
            std::regex(R"(\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b)"),
            "****-****-****-****");

        return result;
    }
};
```

### Message Content Encryption (App Layer)
```cpp
// SDK provides hooks for app-layer encryption
struct MessageEncryptionHook {
    virtual std::string Encrypt(const std::string& plaintext) = 0;
    virtual std::string Decrypt(const std::string& ciphertext) = 0;
};

// App implements end-to-end encryption
class E2EEncryption : public MessageEncryptionHook {
    std::string Encrypt(const std::string& plaintext) override {
        // Use recipient's public key
        return RSA_encrypt(recipient_pubkey, plaintext);
    }

    std::string Decrypt(const std::string& ciphertext) override {
        // Use own private key
        return RSA_decrypt(my_privkey, ciphertext);
    }
};
```

## Secure Deletion

### Memory Clearing
```cpp
// Securely clear sensitive data from memory
template<typename T>
void SecureClear(T& data) {
    volatile unsigned char* p = reinterpret_cast<volatile unsigned char*>(&data);
    size_t size = sizeof(T);
    while (size--) {
        *p++ = 0;
    }
    std::atomic_thread_fence(std::memory_order_seq_cst);
}

// For containers
void SecureClear(std::string& str) {
    volatile char* p = const_cast<volatile char*>(str.data());
    for (size_t i = 0; i < str.size(); ++i) {
        p[i] = 0;
    }
    str.clear();
    str.shrink_to_fit();
}
```

### File Overwrite
```cpp
// Securely delete file (overwrite before delete)
Result SecureDeleteFile(const std::string& path) {
    std::fstream file(path, std::ios::in | std::ios::out | std::ios::binary);
    if (!file) return Result::Error(FILE_NOT_FOUND);

    // Get file size
    file.seekg(0, std::ios::end);
    size_t size = file.tellg();
    file.seekg(0, std::ios::beg);

    // Overwrite with random data (3 passes)
    std::vector<uint8_t> random_data(4096);
    for (int pass = 0; pass < 3; ++pass) {
        file.seekp(0, std::ios::beg);
        for (size_t written = 0; written < size; ) {
            RAND_bytes(random_data.data(), random_data.size());
            size_t to_write = std::min(random_data.size(), size - written);
            file.write(reinterpret_cast<char*>(random_data.data()), to_write);
            written += to_write;
        }
        file.flush();
    }

    file.close();
    std::filesystem::remove(path);

    return Result::OK();
}
```

## Audit Logging

### Audit Event Types
```cpp
enum class AuditEventType {
    AUTH_SUCCESS,
    AUTH_FAILURE,
    SESSION_CREATE,
    SESSION_JOIN,
    SESSION_LEAVE,
    MESSAGE_SEND,
    MESSAGE_RECEIVE,
    FILE_UPLOAD,
    FILE_DOWNLOAD,
    KEY_GENERATED,
    CERT_RENEWED,
    CONFIG_CHANGED,
    ERROR_OCCURRED,
};

struct AuditEvent {
    AuditEventType type;
    uint64_t timestamp;
    std::string aid;
    std::string action;
    std::string resource;
    std::string result;  // success, failure
    std::map<std::string, std::string> metadata;
};
```

### Audit Logger
```cpp
class AuditLogger {
public:
    void Log(const AuditEvent& event) {
        std::lock_guard lock(mutex_);

        // Format: timestamp|type|aid|action|resource|result|metadata
        std::ostringstream oss;
        oss << event.timestamp << "|"
            << static_cast<int>(event.type) << "|"
            << event.aid << "|"
            << event.action << "|"
            << event.resource << "|"
            << event.result << "|"
            << SerializeMetadata(event.metadata);

        audit_file_ << oss.str() << std::endl;

        // Rotate if needed
        if (GetFileSize(audit_path_) > max_size_) {
            RotateLog();
        }
    }

private:
    void RotateLog() {
        audit_file_.close();
        std::filesystem::rename(audit_path_, audit_path_ + ".1");
        audit_file_.open(audit_path_, std::ios::app);
    }

    std::ofstream audit_file_;
    std::mutex mutex_;
    size_t max_size_ = 10 * 1024 * 1024;  // 10MB
};
```

## Threat Model

### Identified Threats
| Threat | Mitigation |
|--------|------------|
| Man-in-the-middle | TLS 1.2+, certificate pinning |
| Token theft | Short-lived tokens, secure storage |
| Local file access | File permissions, optional encryption |
| Memory dump | Secure memory clearing |
| Log leakage | PII redaction, token sanitization |
| Replay attack | Nonce in auth, timestamp validation |
| Brute force | Rate limiting on server side |

### Security Checklist
- [ ] TLS verification enabled by default
- [ ] Certificate pinning configured for production
- [ ] Private keys stored in platform secure storage
- [ ] Tokens never logged or persisted in plaintext
- [ ] PII redacted from all logs
- [ ] Sensitive data cleared from memory after use
- [ ] File permissions set to owner-only (0600)
- [ ] Audit logging enabled for security events
- [ ] Input validation on all external data
- [ ] SQL injection prevention (parameterized queries)
- [ ] XSS prevention (output encoding)
- [ ] CSRF protection (not applicable for native SDK)

## Compliance Considerations

### GDPR
- User data minimization
- Right to erasure (SecureDeleteFile)
- Data portability (export functions)
- Consent management (app responsibility)

### Data Retention
```cpp
struct DataRetentionPolicy {
    int64_t message_retention_days = 90;
    int64_t audit_log_retention_days = 365;
    int64_t file_cache_retention_days = 30;

    void ApplyPolicy() {
        // Delete old messages
        DeleteMessagesOlderThan(message_retention_days);

        // Delete old audit logs
        DeleteAuditLogsOlderThan(audit_log_retention_days);

        // Clear file cache
        ClearFileCacheOlderThan(file_cache_retention_days);
    }
};
```

## Security Updates

### Vulnerability Response
1. Security issues reported to security@example.com
2. Triage within 24 hours
3. Patch developed and tested
4. Security advisory published
5. Patch released with version bump
6. Users notified via release notes

### Dependency Management
```cpp
// Track dependency versions
struct Dependency {
    std::string name;
    std::string version;
    std::string license;
    std::vector<std::string> known_vulnerabilities;
};

// Check for known vulnerabilities
void CheckDependencies() {
    for (const auto& dep : dependencies) {
        if (!dep.known_vulnerabilities.empty()) {
            Logger::Warn("Dependency {} has known vulnerabilities: {}",
                         dep.name, Join(dep.known_vulnerabilities));
        }
    }
}
```
