#include "crypto.h"

#include <cstring>
#include <fstream>
#include <sstream>
#include <stdexcept>

#if AGENTCP_USE_OPENSSL

#include <openssl/evp.h>
#include <openssl/rand.h>
#include <openssl/sha.h>
#include <openssl/err.h>
#include <openssl/pem.h>
#include <openssl/x509.h>
#include <openssl/x509v3.h>
#include <openssl/bio.h>
#include <openssl/ec.h>

#endif

namespace agentcp {
namespace crypto {

#if AGENTCP_USE_OPENSSL

// ============== OpenSSL implementation ==============

// SHA-256 implementation
std::array<uint8_t, SHA256_DIGEST_SIZE> SHA256(const uint8_t* data, size_t len) {
    std::array<uint8_t, SHA256_DIGEST_SIZE> digest;
    ::SHA256(data, len, digest.data());
    return digest;
}

// Generate random bytes
void RandomBytes(uint8_t* buffer, size_t len) {
    if (RAND_bytes(buffer, static_cast<int>(len)) != 1) {
        throw std::runtime_error("RAND_bytes failed");
    }
}

// AES-256-GCM encryption
std::vector<uint8_t> AES256GCMEncrypt(
    const uint8_t* plaintext, size_t plaintext_len,
    const uint8_t* key, size_t key_len,
    const uint8_t* aad, size_t aad_len) {

    if (key_len != AES256_KEY_SIZE) {
        return {};
    }

    // Generate random IV
    std::vector<uint8_t> iv(AES_GCM_IV_SIZE);
    RandomBytes(iv.data(), AES_GCM_IV_SIZE);

    EVP_CIPHER_CTX* ctx = EVP_CIPHER_CTX_new();
    if (!ctx) {
        return {};
    }

    std::vector<uint8_t> result;
    result.reserve(AES_GCM_IV_SIZE + plaintext_len + AES_GCM_TAG_SIZE);

    // Append IV to output
    result.insert(result.end(), iv.begin(), iv.end());

    int len = 0;
    int ciphertext_len = 0;
    std::vector<uint8_t> ciphertext(plaintext_len + AES_GCM_TAG_SIZE);

    // Initialize encryption
    if (EVP_EncryptInit_ex(ctx, EVP_aes_256_gcm(), nullptr, nullptr, nullptr) != 1) {
        EVP_CIPHER_CTX_free(ctx);
        return {};
    }

    // Set IV length
    if (EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_SET_IVLEN, AES_GCM_IV_SIZE, nullptr) != 1) {
        EVP_CIPHER_CTX_free(ctx);
        return {};
    }

    // Set key and IV
    if (EVP_EncryptInit_ex(ctx, nullptr, nullptr, key, iv.data()) != 1) {
        EVP_CIPHER_CTX_free(ctx);
        return {};
    }

    // Add AAD (if present)
    if (aad && aad_len > 0) {
        if (EVP_EncryptUpdate(ctx, nullptr, &len, aad, static_cast<int>(aad_len)) != 1) {
            EVP_CIPHER_CTX_free(ctx);
            return {};
        }
    }

    // Encrypt data
    if (EVP_EncryptUpdate(ctx, ciphertext.data(), &len, plaintext, static_cast<int>(plaintext_len)) != 1) {
        EVP_CIPHER_CTX_free(ctx);
        return {};
    }
    ciphertext_len = len;

    // Finalize encryption
    if (EVP_EncryptFinal_ex(ctx, ciphertext.data() + len, &len) != 1) {
        EVP_CIPHER_CTX_free(ctx);
        return {};
    }
    ciphertext_len += len;

    // Get authentication tag
    std::vector<uint8_t> tag(AES_GCM_TAG_SIZE);
    if (EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_GET_TAG, AES_GCM_TAG_SIZE, tag.data()) != 1) {
        EVP_CIPHER_CTX_free(ctx);
        return {};
    }

    EVP_CIPHER_CTX_free(ctx);

    // Combine result: IV + ciphertext + tag
    result.insert(result.end(), ciphertext.begin(), ciphertext.begin() + ciphertext_len);
    result.insert(result.end(), tag.begin(), tag.end());

    return result;
}

// AES-256-GCM decryption
std::vector<uint8_t> AES256GCMDecrypt(
    const uint8_t* ciphertext, size_t ciphertext_len,
    const uint8_t* key, size_t key_len,
    const uint8_t* aad, size_t aad_len) {

    if (key_len != AES256_KEY_SIZE) {
        return {};
    }

    // Minimum length: IV + tag
    if (ciphertext_len < AES_GCM_IV_SIZE + AES_GCM_TAG_SIZE) {
        return {};
    }

    // Extract IV
    const uint8_t* iv = ciphertext;

    // Extract ciphertext and tag
    const uint8_t* encrypted_data = ciphertext + AES_GCM_IV_SIZE;
    size_t encrypted_len = ciphertext_len - AES_GCM_IV_SIZE - AES_GCM_TAG_SIZE;
    const uint8_t* tag = ciphertext + ciphertext_len - AES_GCM_TAG_SIZE;

    EVP_CIPHER_CTX* ctx = EVP_CIPHER_CTX_new();
    if (!ctx) {
        return {};
    }

    std::vector<uint8_t> plaintext(encrypted_len);
    int len = 0;
    int plaintext_len = 0;

    // Initialize decryption
    if (EVP_DecryptInit_ex(ctx, EVP_aes_256_gcm(), nullptr, nullptr, nullptr) != 1) {
        EVP_CIPHER_CTX_free(ctx);
        return {};
    }

    // Set IV length
    if (EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_SET_IVLEN, AES_GCM_IV_SIZE, nullptr) != 1) {
        EVP_CIPHER_CTX_free(ctx);
        return {};
    }

    // Set key and IV
    if (EVP_DecryptInit_ex(ctx, nullptr, nullptr, key, iv) != 1) {
        EVP_CIPHER_CTX_free(ctx);
        return {};
    }

    // Add AAD (if present)
    if (aad && aad_len > 0) {
        if (EVP_DecryptUpdate(ctx, nullptr, &len, aad, static_cast<int>(aad_len)) != 1) {
            EVP_CIPHER_CTX_free(ctx);
            return {};
        }
    }

    // Decrypt data
    if (EVP_DecryptUpdate(ctx, plaintext.data(), &len, encrypted_data, static_cast<int>(encrypted_len)) != 1) {
        EVP_CIPHER_CTX_free(ctx);
        return {};
    }
    plaintext_len = len;

    // Set authentication tag
    if (EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_SET_TAG, AES_GCM_TAG_SIZE, const_cast<uint8_t*>(tag)) != 1) {
        EVP_CIPHER_CTX_free(ctx);
        return {};
    }

    // Verify and finalize decryption
    if (EVP_DecryptFinal_ex(ctx, plaintext.data() + len, &len) != 1) {
        // Authentication failed
        EVP_CIPHER_CTX_free(ctx);
        return {};
    }
    plaintext_len += len;

    EVP_CIPHER_CTX_free(ctx);

    plaintext.resize(plaintext_len);
    return plaintext;
}

// Ed25519 key pair generation
KeyPair GenerateKeyPair() {
    KeyPair kp;

    EVP_PKEY* pkey = nullptr;
    EVP_PKEY_CTX* ctx = EVP_PKEY_CTX_new_id(EVP_PKEY_ED25519, nullptr);

    if (!ctx) {
        throw std::runtime_error("EVP_PKEY_CTX_new_id failed");
    }

    if (EVP_PKEY_keygen_init(ctx) <= 0) {
        EVP_PKEY_CTX_free(ctx);
        throw std::runtime_error("EVP_PKEY_keygen_init failed");
    }

    if (EVP_PKEY_keygen(ctx, &pkey) <= 0) {
        EVP_PKEY_CTX_free(ctx);
        throw std::runtime_error("EVP_PKEY_keygen failed");
    }

    EVP_PKEY_CTX_free(ctx);

    // Extract public key
    size_t pub_len = ED25519_PUBLIC_KEY_SIZE;
    if (EVP_PKEY_get_raw_public_key(pkey, kp.public_key.data(), &pub_len) != 1) {
        EVP_PKEY_free(pkey);
        throw std::runtime_error("EVP_PKEY_get_raw_public_key failed");
    }

    // Extract private key (seed)
    size_t priv_len = ED25519_SEED_SIZE;
    std::array<uint8_t, ED25519_SEED_SIZE> seed;
    if (EVP_PKEY_get_raw_private_key(pkey, seed.data(), &priv_len) != 1) {
        EVP_PKEY_free(pkey);
        throw std::runtime_error("EVP_PKEY_get_raw_private_key failed");
    }

    // Construct full private key (seed + public_key)
    std::memcpy(kp.private_key.data(), seed.data(), ED25519_SEED_SIZE);
    std::memcpy(kp.private_key.data() + ED25519_SEED_SIZE, kp.public_key.data(), ED25519_PUBLIC_KEY_SIZE);

    EVP_PKEY_free(pkey);
    return kp;
}

// Generate key pair from seed
KeyPair GenerateKeyPairFromSeed(const std::array<uint8_t, ED25519_SEED_SIZE>& seed) {
    KeyPair kp;

    EVP_PKEY* pkey = EVP_PKEY_new_raw_private_key(EVP_PKEY_ED25519, nullptr, seed.data(), ED25519_SEED_SIZE);
    if (!pkey) {
        throw std::runtime_error("EVP_PKEY_new_raw_private_key failed");
    }

    // Extract public key
    size_t pub_len = ED25519_PUBLIC_KEY_SIZE;
    if (EVP_PKEY_get_raw_public_key(pkey, kp.public_key.data(), &pub_len) != 1) {
        EVP_PKEY_free(pkey);
        throw std::runtime_error("EVP_PKEY_get_raw_public_key failed");
    }

    // Construct full private key
    std::memcpy(kp.private_key.data(), seed.data(), ED25519_SEED_SIZE);
    std::memcpy(kp.private_key.data() + ED25519_SEED_SIZE, kp.public_key.data(), ED25519_PUBLIC_KEY_SIZE);

    EVP_PKEY_free(pkey);
    return kp;
}

// Ed25519 sign
std::array<uint8_t, ED25519_SIGNATURE_SIZE> Sign(
    const uint8_t* message, size_t message_len,
    const std::array<uint8_t, ED25519_PRIVATE_KEY_SIZE>& private_key) {

    std::array<uint8_t, ED25519_SIGNATURE_SIZE> signature;

    // Create key from seed part
    EVP_PKEY* pkey = EVP_PKEY_new_raw_private_key(
        EVP_PKEY_ED25519, nullptr, private_key.data(), ED25519_SEED_SIZE);
    if (!pkey) {
        throw std::runtime_error("EVP_PKEY_new_raw_private_key failed");
    }

    EVP_MD_CTX* ctx = EVP_MD_CTX_new();
    if (!ctx) {
        EVP_PKEY_free(pkey);
        throw std::runtime_error("EVP_MD_CTX_new failed");
    }

    if (EVP_DigestSignInit(ctx, nullptr, nullptr, nullptr, pkey) != 1) {
        EVP_MD_CTX_free(ctx);
        EVP_PKEY_free(pkey);
        throw std::runtime_error("EVP_DigestSignInit failed");
    }

    size_t sig_len = ED25519_SIGNATURE_SIZE;
    if (EVP_DigestSign(ctx, signature.data(), &sig_len, message, message_len) != 1) {
        EVP_MD_CTX_free(ctx);
        EVP_PKEY_free(pkey);
        throw std::runtime_error("EVP_DigestSign failed");
    }

    EVP_MD_CTX_free(ctx);
    EVP_PKEY_free(pkey);
    return signature;
}

// Ed25519 verify
bool Verify(
    const uint8_t* message, size_t message_len,
    const std::array<uint8_t, ED25519_SIGNATURE_SIZE>& signature,
    const std::array<uint8_t, ED25519_PUBLIC_KEY_SIZE>& public_key) {

    EVP_PKEY* pkey = EVP_PKEY_new_raw_public_key(
        EVP_PKEY_ED25519, nullptr, public_key.data(), ED25519_PUBLIC_KEY_SIZE);
    if (!pkey) {
        return false;
    }

    EVP_MD_CTX* ctx = EVP_MD_CTX_new();
    if (!ctx) {
        EVP_PKEY_free(pkey);
        return false;
    }

    if (EVP_DigestVerifyInit(ctx, nullptr, nullptr, nullptr, pkey) != 1) {
        EVP_MD_CTX_free(ctx);
        EVP_PKEY_free(pkey);
        return false;
    }

    int result = EVP_DigestVerify(ctx, signature.data(), signature.size(), message, message_len);

    EVP_MD_CTX_free(ctx);
    EVP_PKEY_free(pkey);
    return result == 1;
}

// ECDSA P-384 key generation
std::string GenerateECP384Key() {
    EVP_PKEY* pkey = EVP_EC_gen("P-384");
    if (!pkey) {
        return {};
    }

    BIO* bio = BIO_new(BIO_s_mem());
    if (!bio) {
        EVP_PKEY_free(pkey);
        return {};
    }

    if (PEM_write_bio_PrivateKey(bio, pkey, nullptr, nullptr, 0, nullptr, nullptr) != 1) {
        BIO_free(bio);
        EVP_PKEY_free(pkey);
        return {};
    }

    char* pem_data = nullptr;
    long pem_len = BIO_get_mem_data(bio, &pem_data);
    std::string result(pem_data, pem_len);

    BIO_free(bio);
    EVP_PKEY_free(pkey);
    return result;
}

// Generate X509 CSR
std::string GenerateCSR(const std::string& agent_id, const std::string& private_key_pem) {
    // Load private key from PEM string
    BIO* key_bio = BIO_new_mem_buf(private_key_pem.data(), (int)private_key_pem.size());
    if (!key_bio) return {};

    EVP_PKEY* pkey = PEM_read_bio_PrivateKey(key_bio, nullptr, nullptr, nullptr);
    BIO_free(key_bio);
    if (!pkey) return {};

    X509_REQ* req = X509_REQ_new();
    if (!req) {
        EVP_PKEY_free(pkey);
        return {};
    }

    // Set version
    X509_REQ_set_version(req, 0);  // v1

    // Set subject (order matches Python SDK: C, ST, L, O, CN)
    X509_NAME* name = X509_REQ_get_subject_name(req);
    X509_NAME_add_entry_by_txt(name, "C", MBSTRING_ASC,
        (const unsigned char*)"CN", -1, -1, 0);
    X509_NAME_add_entry_by_txt(name, "ST", MBSTRING_ASC,
        (const unsigned char*)"SomeState", -1, -1, 0);
    X509_NAME_add_entry_by_txt(name, "L", MBSTRING_ASC,
        (const unsigned char*)"SomeCity", -1, -1, 0);
    X509_NAME_add_entry_by_txt(name, "O", MBSTRING_ASC,
        (const unsigned char*)"SomeOrganization", -1, -1, 0);
    X509_NAME_add_entry_by_txt(name, "CN", MBSTRING_ASC,
        (const unsigned char*)agent_id.c_str(), -1, -1, 0);

    // Set public key
    X509_REQ_set_pubkey(req, pkey);

    // Add BasicConstraints extension (ca=false, critical)
    STACK_OF(X509_EXTENSION)* exts = sk_X509_EXTENSION_new_null();
    X509_EXTENSION* ext = X509V3_EXT_nconf_nid(nullptr, nullptr,
        NID_basic_constraints, const_cast<char*>("critical,CA:FALSE"));
    if (ext) {
        sk_X509_EXTENSION_push(exts, ext);
        X509_REQ_add_extensions(req, exts);
    }
    sk_X509_EXTENSION_pop_free(exts, X509_EXTENSION_free);

    // Sign with SHA-256
    if (X509_REQ_sign(req, pkey, EVP_sha256()) <= 0) {
        X509_REQ_free(req);
        EVP_PKEY_free(pkey);
        return {};
    }

    // Serialize to PEM
    BIO* out_bio = BIO_new(BIO_s_mem());
    PEM_write_bio_X509_REQ(out_bio, req);

    char* pem_data = nullptr;
    long pem_len = BIO_get_mem_data(out_bio, &pem_data);
    std::string result(pem_data, pem_len);

    BIO_free(out_bio);
    X509_REQ_free(req);
    EVP_PKEY_free(pkey);
    return result;
}

// Save private key PEM encrypted with PKCS8 + AES-256-CBC
bool SavePrivateKeyPEM(const std::string& path, const std::string& pem, const std::string& password) {
    // Load key from PEM string
    BIO* in_bio = BIO_new_mem_buf(pem.data(), (int)pem.size());
    if (!in_bio) return false;

    EVP_PKEY* pkey = PEM_read_bio_PrivateKey(in_bio, nullptr, nullptr, nullptr);
    BIO_free(in_bio);
    if (!pkey) return false;

    FILE* fp = nullptr;
#if defined(_WIN32)
    fopen_s(&fp, path.c_str(), "wb");
#else
    fp = fopen(path.c_str(), "wb");
#endif
    if (!fp) {
        EVP_PKEY_free(pkey);
        return false;
    }

    int ret = PEM_write_PKCS8PrivateKey(fp, pkey, EVP_aes_256_cbc(),
        nullptr, 0, nullptr, const_cast<char*>(password.c_str()));

    fclose(fp);
    EVP_PKEY_free(pkey);
    return ret == 1;
}

// Load private key PEM decrypted with password
std::string LoadPrivateKeyPEM(const std::string& path, const std::string& password) {
    FILE* fp = nullptr;
#if defined(_WIN32)
    fopen_s(&fp, path.c_str(), "rb");
#else
    fp = fopen(path.c_str(), "rb");
#endif
    if (!fp) return {};

    EVP_PKEY* pkey = PEM_read_PrivateKey(fp, nullptr, nullptr,
        const_cast<char*>(password.c_str()));
    fclose(fp);
    if (!pkey) return {};

    BIO* bio = BIO_new(BIO_s_mem());
    PEM_write_bio_PrivateKey(bio, pkey, nullptr, nullptr, 0, nullptr, nullptr);
    EVP_PKEY_free(pkey);

    char* pem_data = nullptr;
    long pem_len = BIO_get_mem_data(bio, &pem_data);
    std::string result(pem_data, pem_len);
    BIO_free(bio);
    return result;
}

// Save PEM file
bool SavePEMFile(const std::string& path, const std::string& pem) {
    std::ofstream f(path, std::ios::binary);
    if (!f.is_open()) return false;
    f << pem;
    return f.good();
}

// Read PEM file
std::string ReadPEMFile(const std::string& path) {
    std::ifstream f(path, std::ios::binary);
    if (!f.is_open()) return {};
    std::ostringstream ss;
    ss << f.rdbuf();
    return ss.str();
}

#else

// ============== Stub implementation (no OpenSSL) ==============
// For development/testing only, does not provide real cryptographic security

// Simple SHA-256 substitute (uses fixed transform, for testing only)
std::array<uint8_t, SHA256_DIGEST_SIZE> SHA256(const uint8_t* data, size_t len) {
    std::array<uint8_t, SHA256_DIGEST_SIZE> digest{};
    // Simple hash simulation - for development testing only
    for (size_t i = 0; i < len; ++i) {
        digest[i % SHA256_DIGEST_SIZE] ^= data[i];
        digest[(i + 1) % SHA256_DIGEST_SIZE] = (digest[(i + 1) % SHA256_DIGEST_SIZE] + data[i]) & 0xFF;
    }
    return digest;
}

// Generate pseudo-random bytes
void RandomBytes(uint8_t* buffer, size_t len) {
    static uint32_t seed = 12345;
    for (size_t i = 0; i < len; ++i) {
        seed = seed * 1103515245 + 12345;
        buffer[i] = static_cast<uint8_t>((seed >> 16) & 0xFF);
    }
}

// Simple XOR "encryption" - for testing only
std::vector<uint8_t> AES256GCMEncrypt(
    const uint8_t* plaintext, size_t plaintext_len,
    const uint8_t* key, size_t key_len,
    const uint8_t* /*aad*/, size_t /*aad_len*/) {

    if (key_len != AES256_KEY_SIZE) {
        return {};
    }

    std::vector<uint8_t> result;
    // IV (12 bytes) + ciphertext + tag (16 bytes)
    result.resize(AES_GCM_IV_SIZE + plaintext_len + AES_GCM_TAG_SIZE);

    // Generate pseudo-random IV
    RandomBytes(result.data(), AES_GCM_IV_SIZE);

    // Simple XOR "encryption"
    for (size_t i = 0; i < plaintext_len; ++i) {
        result[AES_GCM_IV_SIZE + i] = plaintext[i] ^ key[i % key_len];
    }

    // Fill pseudo tag
    for (size_t i = 0; i < AES_GCM_TAG_SIZE; ++i) {
        result[AES_GCM_IV_SIZE + plaintext_len + i] = static_cast<uint8_t>(i);
    }

    return result;
}

std::vector<uint8_t> AES256GCMDecrypt(
    const uint8_t* ciphertext, size_t ciphertext_len,
    const uint8_t* key, size_t key_len,
    const uint8_t* /*aad*/, size_t /*aad_len*/) {

    if (key_len != AES256_KEY_SIZE) {
        return {};
    }

    if (ciphertext_len < AES_GCM_IV_SIZE + AES_GCM_TAG_SIZE) {
        return {};
    }

    size_t plaintext_len = ciphertext_len - AES_GCM_IV_SIZE - AES_GCM_TAG_SIZE;
    std::vector<uint8_t> result(plaintext_len);

    // Simple XOR "decryption"
    for (size_t i = 0; i < plaintext_len; ++i) {
        result[i] = ciphertext[AES_GCM_IV_SIZE + i] ^ key[i % key_len];
    }

    return result;
}

KeyPair GenerateKeyPair() {
    KeyPair kp;
    RandomBytes(kp.private_key.data(), ED25519_PRIVATE_KEY_SIZE);
    // Public key is last 32 bytes of private key
    std::memcpy(kp.public_key.data(), kp.private_key.data() + ED25519_SEED_SIZE, ED25519_PUBLIC_KEY_SIZE);
    return kp;
}

KeyPair GenerateKeyPairFromSeed(const std::array<uint8_t, ED25519_SEED_SIZE>& seed) {
    KeyPair kp;
    // Copy seed to first 32 bytes of private key
    std::memcpy(kp.private_key.data(), seed.data(), ED25519_SEED_SIZE);
    // Derive public key from seed (simple approach)
    auto hash = SHA256(seed.data(), seed.size());
    std::memcpy(kp.public_key.data(), hash.data(), ED25519_PUBLIC_KEY_SIZE);
    std::memcpy(kp.private_key.data() + ED25519_SEED_SIZE, kp.public_key.data(), ED25519_PUBLIC_KEY_SIZE);
    return kp;
}

std::array<uint8_t, ED25519_SIGNATURE_SIZE> Sign(
    const uint8_t* message, size_t message_len,
    const std::array<uint8_t, ED25519_PRIVATE_KEY_SIZE>& private_key) {

    std::array<uint8_t, ED25519_SIGNATURE_SIZE> signature{};
    // Simple pseudo-signature
    auto hash = SHA256(message, message_len);
    for (size_t i = 0; i < ED25519_SIGNATURE_SIZE; ++i) {
        signature[i] = hash[i % SHA256_DIGEST_SIZE] ^ private_key[i % ED25519_PRIVATE_KEY_SIZE];
    }
    return signature;
}

bool Verify(
    const uint8_t* /*message*/, size_t /*message_len*/,
    const std::array<uint8_t, ED25519_SIGNATURE_SIZE>& /*signature*/,
    const std::array<uint8_t, ED25519_PUBLIC_KEY_SIZE>& /*public_key*/) {
    // Stub implementation always returns true
    return true;
}

// Stub ECDSA P-384 functions (no OpenSSL)
std::string GenerateECP384Key() { return {}; }
std::string GenerateCSR(const std::string&, const std::string&) { return {}; }
bool SavePrivateKeyPEM(const std::string&, const std::string&, const std::string&) { return false; }
std::string LoadPrivateKeyPEM(const std::string&, const std::string&) { return {}; }

bool SavePEMFile(const std::string& path, const std::string& pem) {
    std::ofstream f(path, std::ios::binary);
    if (!f.is_open()) return false;
    f << pem;
    return f.good();
}

std::string ReadPEMFile(const std::string& path) {
    std::ifstream f(path, std::ios::binary);
    if (!f.is_open()) return {};
    std::ostringstream ss;
    ss << f.rdbuf();
    return ss.str();
}

#endif  // AGENTCP_USE_OPENSSL

// ============== Common implementation (no OpenSSL dependency) ==============

std::array<uint8_t, SHA256_DIGEST_SIZE> SHA256(const std::string& data) {
    return SHA256(reinterpret_cast<const uint8_t*>(data.data()), data.size());
}

std::array<uint8_t, AES256_KEY_SIZE> DeriveKey(const std::string& password) {
    return SHA256(password);
}

std::vector<uint8_t> RandomBytes(size_t len) {
    std::vector<uint8_t> result(len);
    RandomBytes(result.data(), len);
    return result;
}

std::vector<uint8_t> AES256GCMEncrypt(
    const std::vector<uint8_t>& plaintext,
    const std::array<uint8_t, AES256_KEY_SIZE>& key,
    const std::vector<uint8_t>& aad) {
    return AES256GCMEncrypt(
        plaintext.data(), plaintext.size(),
        key.data(), key.size(),
        aad.empty() ? nullptr : aad.data(), aad.size());
}

std::vector<uint8_t> AES256GCMDecrypt(
    const std::vector<uint8_t>& ciphertext,
    const std::array<uint8_t, AES256_KEY_SIZE>& key,
    const std::vector<uint8_t>& aad) {
    return AES256GCMDecrypt(
        ciphertext.data(), ciphertext.size(),
        key.data(), key.size(),
        aad.empty() ? nullptr : aad.data(), aad.size());
}

// Base64 encode
static const char base64_chars[] =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

std::string Base64Encode(const uint8_t* data, size_t len) {
    std::string result;
    result.reserve(((len + 2) / 3) * 4);

    for (size_t i = 0; i < len; i += 3) {
        uint32_t n = static_cast<uint32_t>(data[i]) << 16;
        if (i + 1 < len) n |= static_cast<uint32_t>(data[i + 1]) << 8;
        if (i + 2 < len) n |= static_cast<uint32_t>(data[i + 2]);

        result.push_back(base64_chars[(n >> 18) & 0x3F]);
        result.push_back(base64_chars[(n >> 12) & 0x3F]);
        result.push_back((i + 1 < len) ? base64_chars[(n >> 6) & 0x3F] : '=');
        result.push_back((i + 2 < len) ? base64_chars[n & 0x3F] : '=');
    }

    return result;
}

std::string Base64Encode(const std::vector<uint8_t>& data) {
    return Base64Encode(data.data(), data.size());
}

// Base64 decode
std::vector<uint8_t> Base64Decode(const std::string& encoded) {
    static const int decode_table[256] = {
        -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
        -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
        -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,62,-1,-1,-1,63,
        52,53,54,55,56,57,58,59,60,61,-1,-1,-1,-1,-1,-1,
        -1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9,10,11,12,13,14,
        15,16,17,18,19,20,21,22,23,24,25,-1,-1,-1,-1,-1,
        -1,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,
        41,42,43,44,45,46,47,48,49,50,51,-1,-1,-1,-1,-1,
        -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
        -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
        -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
        -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
        -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
        -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
        -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
        -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1
    };

    std::vector<uint8_t> result;
    result.reserve((encoded.size() / 4) * 3);

    uint32_t val = 0;
    int valb = -8;

    for (char c : encoded) {
        if (c == '=') break;
        int v = decode_table[static_cast<uint8_t>(c)];
        if (v < 0) continue;
        val = (val << 6) | v;
        valb += 6;
        if (valb >= 0) {
            result.push_back(static_cast<uint8_t>((val >> valb) & 0xFF));
            valb -= 8;
        }
    }

    return result;
}

// Hex encode
std::string HexEncode(const uint8_t* data, size_t len) {
    static const char hex_chars[] = "0123456789abcdef";
    std::string result;
    result.reserve(len * 2);
    for (size_t i = 0; i < len; ++i) {
        result.push_back(hex_chars[(data[i] >> 4) & 0x0F]);
        result.push_back(hex_chars[data[i] & 0x0F]);
    }
    return result;
}

std::string HexEncode(const std::vector<uint8_t>& data) {
    return HexEncode(data.data(), data.size());
}

// Hex decode
std::vector<uint8_t> HexDecode(const std::string& hex) {
    std::vector<uint8_t> result;
    result.reserve(hex.size() / 2);

    for (size_t i = 0; i + 1 < hex.size(); i += 2) {
        char hi = hex[i];
        char lo = hex[i + 1];

        uint8_t byte = 0;
        if (hi >= '0' && hi <= '9') byte = (hi - '0') << 4;
        else if (hi >= 'a' && hi <= 'f') byte = (hi - 'a' + 10) << 4;
        else if (hi >= 'A' && hi <= 'F') byte = (hi - 'A' + 10) << 4;

        if (lo >= '0' && lo <= '9') byte |= (lo - '0');
        else if (lo >= 'a' && lo <= 'f') byte |= (lo - 'a' + 10);
        else if (lo >= 'A' && lo <= 'F') byte |= (lo - 'A' + 10);

        result.push_back(byte);
    }

    return result;
}

}  // namespace crypto
}  // namespace agentcp
