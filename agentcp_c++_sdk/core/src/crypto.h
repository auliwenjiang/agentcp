#pragma once

#include <array>
#include <cstdint>
#include <string>
#include <vector>

namespace agentcp {
namespace crypto {

// SHA-256 constants
constexpr size_t SHA256_DIGEST_SIZE = 32;
constexpr size_t AES256_KEY_SIZE = 32;
constexpr size_t AES_GCM_IV_SIZE = 12;
constexpr size_t AES_GCM_TAG_SIZE = 16;

// SHA-256 hash
std::array<uint8_t, SHA256_DIGEST_SIZE> SHA256(const uint8_t* data, size_t len);
std::array<uint8_t, SHA256_DIGEST_SIZE> SHA256(const std::string& data);

// Derive key from password (SHA256)
std::array<uint8_t, AES256_KEY_SIZE> DeriveKey(const std::string& password);

// AES-256-GCM encryption
// Returns: IV (12 bytes) + ciphertext + tag (16 bytes)
std::vector<uint8_t> AES256GCMEncrypt(
    const uint8_t* plaintext, size_t plaintext_len,
    const uint8_t* key, size_t key_len,
    const uint8_t* aad = nullptr, size_t aad_len = 0);

std::vector<uint8_t> AES256GCMEncrypt(
    const std::vector<uint8_t>& plaintext,
    const std::array<uint8_t, AES256_KEY_SIZE>& key,
    const std::vector<uint8_t>& aad = {});

// AES-256-GCM decryption
// Input: IV (12 bytes) + ciphertext + tag (16 bytes)
// Returns: decrypted plaintext, empty on failure
std::vector<uint8_t> AES256GCMDecrypt(
    const uint8_t* ciphertext, size_t ciphertext_len,
    const uint8_t* key, size_t key_len,
    const uint8_t* aad = nullptr, size_t aad_len = 0);

std::vector<uint8_t> AES256GCMDecrypt(
    const std::vector<uint8_t>& ciphertext,
    const std::array<uint8_t, AES256_KEY_SIZE>& key,
    const std::vector<uint8_t>& aad = {});

// Generate random bytes
void RandomBytes(uint8_t* buffer, size_t len);
std::vector<uint8_t> RandomBytes(size_t len);

// Ed25519 key pair
constexpr size_t ED25519_PUBLIC_KEY_SIZE = 32;
constexpr size_t ED25519_PRIVATE_KEY_SIZE = 64;  // includes public key
constexpr size_t ED25519_SEED_SIZE = 32;
constexpr size_t ED25519_SIGNATURE_SIZE = 64;

struct KeyPair {
    std::array<uint8_t, ED25519_PUBLIC_KEY_SIZE> public_key;
    std::array<uint8_t, ED25519_PRIVATE_KEY_SIZE> private_key;
};

// Generate Ed25519 key pair
KeyPair GenerateKeyPair();

// Generate key pair from seed (deterministic)
KeyPair GenerateKeyPairFromSeed(const std::array<uint8_t, ED25519_SEED_SIZE>& seed);

// Ed25519 sign
std::array<uint8_t, ED25519_SIGNATURE_SIZE> Sign(
    const uint8_t* message, size_t message_len,
    const std::array<uint8_t, ED25519_PRIVATE_KEY_SIZE>& private_key);

// Ed25519 verify
bool Verify(
    const uint8_t* message, size_t message_len,
    const std::array<uint8_t, ED25519_SIGNATURE_SIZE>& signature,
    const std::array<uint8_t, ED25519_PUBLIC_KEY_SIZE>& public_key);

// Base64 encode/decode
std::string Base64Encode(const uint8_t* data, size_t len);
std::string Base64Encode(const std::vector<uint8_t>& data);
std::vector<uint8_t> Base64Decode(const std::string& encoded);

// Hex encode/decode
std::string HexEncode(const uint8_t* data, size_t len);
std::string HexEncode(const std::vector<uint8_t>& data);
template<size_t N>
std::string HexEncode(const std::array<uint8_t, N>& data) {
    return HexEncode(data.data(), data.size());
}
std::vector<uint8_t> HexDecode(const std::string& hex);

// ECDSA P-384 certificate-based functions
// Generate ECDSA P-384 private key, returns PEM string
std::string GenerateECP384Key();

// Generate X509 CSR for agent_id signed with the private key
std::string GenerateCSR(const std::string& agent_id, const std::string& private_key_pem);

// Save private key PEM encrypted with password (PKCS8, AES-256-CBC)
bool SavePrivateKeyPEM(const std::string& path, const std::string& pem, const std::string& password);

// Load private key PEM decrypted with password
std::string LoadPrivateKeyPEM(const std::string& path, const std::string& password);

// Generic PEM file I/O
bool SavePEMFile(const std::string& path, const std::string& pem);
std::string ReadPEMFile(const std::string& path);

}  // namespace crypto
}  // namespace agentcp
