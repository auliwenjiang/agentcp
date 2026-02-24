#include <gtest/gtest.h>
#include "agentcp/agentcp.h"

namespace agentcp {
namespace {

class LifecycleTest : public ::testing::Test {
protected:
    void SetUp() override {
        AgentCP::Instance().Shutdown();
        AgentCP::Instance().Initialize();
    }

    void TearDown() override {
        AgentCP::Instance().Shutdown();
    }
};

TEST_F(LifecycleTest, UseAfterDelete) {
    AgentID* aid = nullptr;
    AgentCP::Instance().CreateAID("test-agent", "password", &aid);
    ASSERT_NE(aid, nullptr);

    EXPECT_TRUE(aid->IsValid());

    Result r = AgentCP::Instance().DeleteAID("test-agent");
    EXPECT_TRUE(r.ok());

    EXPECT_FALSE(aid->IsValid());

    r = aid->Online();
    EXPECT_FALSE(r.ok());
    EXPECT_EQ(r.code, static_cast<int>(ErrorCode::AID_INVALID));

    EXPECT_FALSE(aid->IsOnline());
    EXPECT_EQ(aid->GetState(), AgentState::Error);
}

TEST_F(LifecycleTest, UseAfterShutdown) {
    AgentID* aid = nullptr;
    AgentCP::Instance().CreateAID("test-agent", "password", &aid);
    ASSERT_NE(aid, nullptr);

    EXPECT_TRUE(aid->IsValid());

    AgentCP::Instance().Shutdown();

    EXPECT_FALSE(aid->IsValid());

    Result r = aid->Online();
    EXPECT_FALSE(r.ok());
    EXPECT_EQ(r.code, static_cast<int>(ErrorCode::AID_INVALID));
}

TEST_F(LifecycleTest, MultipleAgentsShutdown) {
    AgentID* aid1 = nullptr;
    AgentID* aid2 = nullptr;
    AgentID* aid3 = nullptr;

    AgentCP::Instance().CreateAID("agent-1", "pass", &aid1);
    AgentCP::Instance().CreateAID("agent-2", "pass", &aid2);
    AgentCP::Instance().CreateAID("agent-3", "pass", &aid3);

    EXPECT_TRUE(aid1->IsValid());
    EXPECT_TRUE(aid2->IsValid());
    EXPECT_TRUE(aid3->IsValid());

    AgentCP::Instance().Shutdown();

    EXPECT_FALSE(aid1->IsValid());
    EXPECT_FALSE(aid2->IsValid());
    EXPECT_FALSE(aid3->IsValid());
}

TEST_F(LifecycleTest, DeleteAndRecreate) {
    AgentID* aid1 = nullptr;
    AgentCP::Instance().CreateAID("test-agent", "password", &aid1);
    ASSERT_NE(aid1, nullptr);

    AgentCP::Instance().DeleteAID("test-agent");
    EXPECT_FALSE(aid1->IsValid());

    AgentID* aid2 = nullptr;
    Result r = AgentCP::Instance().CreateAID("test-agent", "password", &aid2);
    EXPECT_TRUE(r.ok());
    EXPECT_NE(aid2, nullptr);
    EXPECT_TRUE(aid2->IsValid());
    EXPECT_NE(aid1, aid2);
}

TEST_F(LifecycleTest, SessionAfterAgentDelete) {
    AgentID* aid = nullptr;
    AgentCP::Instance().CreateAID("test-agent", "password", &aid);
    aid->Online();

    std::string session_id;
    aid->Sessions().CreateSession({}, &session_id);

    Session* session = aid->Sessions().GetSession(session_id);
    ASSERT_NE(session, nullptr);

    AgentCP::Instance().DeleteAID("test-agent");

    std::vector<Block> blocks = {Block::Text("Hello")};
    Result r = session->SendMessage(blocks);
    EXPECT_FALSE(r.ok());
}

TEST_F(LifecycleTest, OnlineAfterOffline) {
    AgentID* aid = nullptr;
    AgentCP::Instance().CreateAID("test-agent", "password", &aid);

    Result r = aid->Online();
    EXPECT_TRUE(r.ok());

    aid->Offline();
    EXPECT_FALSE(aid->IsOnline());

    r = aid->Online();
    EXPECT_TRUE(r.ok());
    EXPECT_TRUE(aid->IsOnline());
}

TEST_F(LifecycleTest, MultipleOffline) {
    AgentID* aid = nullptr;
    AgentCP::Instance().CreateAID("test-agent", "password", &aid);

    aid->Online();
    aid->Offline();
    aid->Offline();
    aid->Offline();

    EXPECT_FALSE(aid->IsOnline());
}

TEST_F(LifecycleTest, InvalidArgumentsCreateAID) {
    AgentID* aid = nullptr;

    Result r = AgentCP::Instance().CreateAID("", "password", &aid);
    EXPECT_FALSE(r.ok());
    EXPECT_EQ(r.code, static_cast<int>(ErrorCode::INVALID_ARGUMENT));

    r = AgentCP::Instance().CreateAID("test", "", &aid);
    EXPECT_FALSE(r.ok());
    EXPECT_EQ(r.code, static_cast<int>(ErrorCode::INVALID_ARGUMENT));

    r = AgentCP::Instance().CreateAID("test", "pass", nullptr);
    EXPECT_FALSE(r.ok());
    EXPECT_EQ(r.code, static_cast<int>(ErrorCode::INVALID_ARGUMENT));
}

TEST_F(LifecycleTest, InvalidArgumentsLoadAID) {
    AgentID* aid = nullptr;

    Result r = AgentCP::Instance().LoadAID("", "pw", &aid);
    EXPECT_FALSE(r.ok());
    EXPECT_EQ(r.code, static_cast<int>(ErrorCode::INVALID_ARGUMENT));

    r = AgentCP::Instance().LoadAID("test", "pw", nullptr);
    EXPECT_FALSE(r.ok());
    EXPECT_EQ(r.code, static_cast<int>(ErrorCode::INVALID_ARGUMENT));
}

TEST_F(LifecycleTest, InvalidArgumentsDeleteAID) {
    Result r = AgentCP::Instance().DeleteAID("");
    EXPECT_FALSE(r.ok());
    EXPECT_EQ(r.code, static_cast<int>(ErrorCode::INVALID_ARGUMENT));
}

TEST_F(LifecycleTest, InvalidArgumentsSession) {
    AgentID* aid = nullptr;
    AgentCP::Instance().CreateAID("test-agent", "password", &aid);
    aid->Online();

    Result r = aid->Sessions().CreateSession({}, nullptr);
    EXPECT_FALSE(r.ok());
    EXPECT_EQ(r.code, static_cast<int>(ErrorCode::INVALID_ARGUMENT));

    r = aid->Sessions().InviteAgent("", "agent-2");
    EXPECT_FALSE(r.ok());
    EXPECT_EQ(r.code, static_cast<int>(ErrorCode::INVALID_ARGUMENT));

    r = aid->Sessions().InviteAgent("session-1", "");
    EXPECT_FALSE(r.ok());
    EXPECT_EQ(r.code, static_cast<int>(ErrorCode::INVALID_ARGUMENT));

    r = aid->Sessions().JoinSession("");
    EXPECT_FALSE(r.ok());
    EXPECT_EQ(r.code, static_cast<int>(ErrorCode::INVALID_ARGUMENT));

    r = aid->Sessions().LeaveSession("");
    EXPECT_FALSE(r.ok());
    EXPECT_EQ(r.code, static_cast<int>(ErrorCode::INVALID_ARGUMENT));

    r = aid->Sessions().CloseSession("");
    EXPECT_FALSE(r.ok());
    EXPECT_EQ(r.code, static_cast<int>(ErrorCode::INVALID_ARGUMENT));

    r = aid->Sessions().EjectAgent("", "agent-2");
    EXPECT_FALSE(r.ok());
    EXPECT_EQ(r.code, static_cast<int>(ErrorCode::INVALID_ARGUMENT));

    r = aid->Sessions().EjectAgent("session-1", "");
    EXPECT_FALSE(r.ok());
    EXPECT_EQ(r.code, static_cast<int>(ErrorCode::INVALID_ARGUMENT));
}

TEST_F(LifecycleTest, CreateSessionWhileOffline) {
    AgentID* aid = nullptr;
    AgentCP::Instance().CreateAID("test-agent", "password", &aid);

    std::string session_id;
    Result r = aid->Sessions().CreateSession({}, &session_id);
    EXPECT_FALSE(r.ok());
    EXPECT_EQ(r.code, static_cast<int>(ErrorCode::NOT_INITIALIZED));
}

}  // namespace
}  // namespace agentcp
