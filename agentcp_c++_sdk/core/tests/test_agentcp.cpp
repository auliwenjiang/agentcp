#include <gtest/gtest.h>
#include "agentcp/agentcp.h"

namespace agentcp {
namespace {

class AgentCPTest : public ::testing::Test {
protected:
    void SetUp() override {
        AgentCP::Instance().Shutdown();
    }

    void TearDown() override {
        AgentCP::Instance().Shutdown();
    }
};

TEST_F(AgentCPTest, InitializeAndShutdown) {
    EXPECT_FALSE(AgentCP::Instance().IsInitialized());

    Result r = AgentCP::Instance().Initialize();
    EXPECT_TRUE(r.ok());
    EXPECT_TRUE(AgentCP::Instance().IsInitialized());

    AgentCP::Instance().Shutdown();
    EXPECT_FALSE(AgentCP::Instance().IsInitialized());
}

TEST_F(AgentCPTest, CreateAID) {
    Result r = AgentCP::Instance().Initialize();
    ASSERT_TRUE(r.ok());

    AgentID* aid = nullptr;
    r = AgentCP::Instance().CreateAID("test-agent", "password123", &aid);
    EXPECT_TRUE(r.ok());
    EXPECT_NE(aid, nullptr);
    EXPECT_EQ(aid->GetAID(), "test-agent");
}

TEST_F(AgentCPTest, CreateAIDWithoutInit) {
    AgentID* aid = nullptr;
    Result r = AgentCP::Instance().CreateAID("test-agent", "password123", &aid);
    EXPECT_FALSE(r.ok());
    EXPECT_EQ(r.code, static_cast<int>(ErrorCode::NOT_INITIALIZED));
}

TEST_F(AgentCPTest, CreateDuplicateAID) {
    Result r = AgentCP::Instance().Initialize();
    ASSERT_TRUE(r.ok());

    AgentID* aid1 = nullptr;
    r = AgentCP::Instance().CreateAID("test-agent", "password123", &aid1);
    EXPECT_TRUE(r.ok());

    AgentID* aid2 = nullptr;
    r = AgentCP::Instance().CreateAID("test-agent", "password456", &aid2);
    EXPECT_FALSE(r.ok());
    EXPECT_EQ(r.code, static_cast<int>(ErrorCode::AID_ALREADY_EXISTS));
}

TEST_F(AgentCPTest, LoadAID) {
    Result r = AgentCP::Instance().Initialize();
    ASSERT_TRUE(r.ok());

    AgentID* aid1 = nullptr;
    r = AgentCP::Instance().CreateAID("test-agent", "password123", &aid1);
    ASSERT_TRUE(r.ok());

    AgentID* aid2 = nullptr;
    r = AgentCP::Instance().LoadAID("test-agent", "password123", &aid2);
    EXPECT_TRUE(r.ok());
    EXPECT_EQ(aid1, aid2);
}

TEST_F(AgentCPTest, LoadNonExistentAID) {
    Result r = AgentCP::Instance().Initialize();
    ASSERT_TRUE(r.ok());

    AgentID* aid = nullptr;
    r = AgentCP::Instance().LoadAID("non-existent", "password123", &aid);
    EXPECT_FALSE(r.ok());
    EXPECT_EQ(r.code, static_cast<int>(ErrorCode::AID_NOT_FOUND));
}

TEST_F(AgentCPTest, DeleteAID) {
    Result r = AgentCP::Instance().Initialize();
    ASSERT_TRUE(r.ok());

    AgentID* aid = nullptr;
    r = AgentCP::Instance().CreateAID("test-agent", "password123", &aid);
    ASSERT_TRUE(r.ok());

    r = AgentCP::Instance().DeleteAID("test-agent");
    EXPECT_TRUE(r.ok());

    AgentID* aid2 = nullptr;
    r = AgentCP::Instance().LoadAID("test-agent", "password123", &aid2);
    EXPECT_FALSE(r.ok());
    EXPECT_EQ(r.code, static_cast<int>(ErrorCode::AID_NOT_FOUND));
}

TEST_F(AgentCPTest, DeleteNonExistentAID) {
    Result r = AgentCP::Instance().Initialize();
    ASSERT_TRUE(r.ok());

    r = AgentCP::Instance().DeleteAID("non-existent");
    EXPECT_TRUE(r.ok());  // DeleteAID is idempotent
}

TEST_F(AgentCPTest, ListAIDs) {
    Result r = AgentCP::Instance().Initialize();
    ASSERT_TRUE(r.ok());

    auto ids = AgentCP::Instance().ListAIDs();
    EXPECT_TRUE(ids.empty());

    AgentID* aid1 = nullptr;
    AgentCP::Instance().CreateAID("agent-b", "pass", &aid1);
    AgentID* aid2 = nullptr;
    AgentCP::Instance().CreateAID("agent-a", "pass", &aid2);

    ids = AgentCP::Instance().ListAIDs();
    EXPECT_EQ(ids.size(), 2u);
    EXPECT_EQ(ids[0], "agent-a");
    EXPECT_EQ(ids[1], "agent-b");
}

TEST_F(AgentCPTest, SetBaseUrls) {
    Result r = AgentCP::Instance().SetBaseUrls("https://ca.example.com", "https://ap.example.com");
    EXPECT_TRUE(r.ok());

    r = AgentCP::Instance().SetBaseUrls("", "https://ap.example.com");
    EXPECT_FALSE(r.ok());
    EXPECT_EQ(r.code, static_cast<int>(ErrorCode::INVALID_ARGUMENT));
}

TEST_F(AgentCPTest, SetStoragePath) {
    Result r = AgentCP::Instance().SetStoragePath("/tmp/agentcp");
    EXPECT_TRUE(r.ok());

    r = AgentCP::Instance().SetStoragePath("");
    EXPECT_FALSE(r.ok());
    EXPECT_EQ(r.code, static_cast<int>(ErrorCode::INVALID_ARGUMENT));
}

TEST_F(AgentCPTest, GetVersion) {
    std::string version = AgentCP::GetVersion();
    EXPECT_FALSE(version.empty());
    EXPECT_NE(version.find('.'), std::string::npos);
}

TEST_F(AgentCPTest, GetBuildInfo) {
    std::string info = AgentCP::GetBuildInfo();
    EXPECT_FALSE(info.empty());
}

// AgentID Tests
class AgentIDTest : public ::testing::Test {
protected:
    void SetUp() override {
        AgentCP::Instance().Shutdown();
        AgentCP::Instance().Initialize();
        AgentCP::Instance().CreateAID("test-agent", "password", &aid_);
    }

    void TearDown() override {
        AgentCP::Instance().Shutdown();
    }

    AgentID* aid_ = nullptr;
};

TEST_F(AgentIDTest, OnlineOffline) {
    EXPECT_FALSE(aid_->IsOnline());
    EXPECT_EQ(aid_->GetState(), AgentState::Offline);

    Result r = aid_->Online();
    EXPECT_TRUE(r.ok());
    EXPECT_TRUE(aid_->IsOnline());
    EXPECT_EQ(aid_->GetState(), AgentState::Online);

    aid_->Offline();
    EXPECT_FALSE(aid_->IsOnline());
    EXPECT_EQ(aid_->GetState(), AgentState::Offline);
}

TEST_F(AgentIDTest, DoubleOnline) {
    Result r = aid_->Online();
    EXPECT_TRUE(r.ok());

    r = aid_->Online();
    EXPECT_FALSE(r.ok());
    EXPECT_EQ(r.code, static_cast<int>(ErrorCode::INVALID_ARGUMENT));
}

TEST_F(AgentIDTest, GetAID) {
    EXPECT_EQ(aid_->GetAID(), "test-agent");
}

TEST_F(AgentIDTest, IsValid) {
    EXPECT_TRUE(aid_->IsValid());
}

TEST_F(AgentIDTest, StateChangeHandler) {
    std::vector<std::pair<AgentState, AgentState>> transitions;
    aid_->SetStateChangeHandler([&](AgentState old_state, AgentState new_state) {
        transitions.push_back({old_state, new_state});
    });

    aid_->Online();
    aid_->Offline();

    ASSERT_GE(transitions.size(), 2u);
    EXPECT_EQ(transitions[0].first, AgentState::Offline);
    EXPECT_EQ(transitions[0].second, AgentState::Connecting);
}

TEST_F(AgentIDTest, SendMessageWhileOffline) {
    std::vector<Block> blocks = {Block::Text("Hello")};
    Result r = aid_->SendMessage("session-1", blocks);
    EXPECT_FALSE(r.ok());
    EXPECT_EQ(r.code, static_cast<int>(ErrorCode::NOT_INITIALIZED));
}

TEST_F(AgentIDTest, CreateStreamWhileOffline) {
    Stream* stream = nullptr;
    Result r = aid_->CreateStream("session-1", "receiver", "text/plain", &stream);
    EXPECT_FALSE(r.ok());
    EXPECT_EQ(r.code, static_cast<int>(ErrorCode::NOT_INITIALIZED));
}

TEST_F(AgentIDTest, UploadFileWhileOffline) {
    std::string url;
    Result r = aid_->UploadFile("/path/to/file", nullptr, &url);
    EXPECT_FALSE(r.ok());
    EXPECT_EQ(r.code, static_cast<int>(ErrorCode::NOT_INITIALIZED));
}

TEST_F(AgentIDTest, DownloadFileWhileOffline) {
    Result r = aid_->DownloadFile("https://example.com/file", "/tmp/file", nullptr);
    EXPECT_FALSE(r.ok());
    EXPECT_EQ(r.code, static_cast<int>(ErrorCode::NOT_INITIALIZED));
}

}  // namespace
}  // namespace agentcp
