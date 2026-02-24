#include <gtest/gtest.h>
#include "agentcp/agentcp.h"

namespace agentcp {
namespace {

class SessionTest : public ::testing::Test {
protected:
    void SetUp() override {
        AgentCP::Instance().Shutdown();
        AgentCP::Instance().Initialize();
        AgentCP::Instance().CreateAID("test-agent", "password", &aid_);
        aid_->Online();
    }

    void TearDown() override {
        AgentCP::Instance().Shutdown();
    }

    AgentID* aid_ = nullptr;
};

TEST_F(SessionTest, CreateSession) {
    std::string session_id;
    Result r = aid_->Sessions().CreateSession({}, &session_id);
    EXPECT_TRUE(r.ok());
    EXPECT_FALSE(session_id.empty());
}

TEST_F(SessionTest, CreateSessionWithMembers) {
    std::string session_id;
    Result r = aid_->Sessions().CreateSession({"agent-2", "agent-3"}, &session_id);
    EXPECT_TRUE(r.ok());

    std::vector<SessionMember> members;
    r = aid_->Sessions().GetMemberList(session_id, &members);
    EXPECT_TRUE(r.ok());
    EXPECT_EQ(members.size(), 3u);
    EXPECT_EQ(members[0].agent_id, "test-agent");
    EXPECT_EQ(members[0].role, "owner");
    EXPECT_EQ(members[1].agent_id, "agent-2");
    EXPECT_EQ(members[2].agent_id, "agent-3");
}

TEST_F(SessionTest, CreateSessionWithDuplicateMembers) {
    std::string session_id;
    Result r = aid_->Sessions().CreateSession({"agent-2", "agent-2", "test-agent"}, &session_id);
    EXPECT_TRUE(r.ok());

    std::vector<SessionMember> members;
    r = aid_->Sessions().GetMemberList(session_id, &members);
    EXPECT_TRUE(r.ok());
    EXPECT_EQ(members.size(), 2u);
}

TEST_F(SessionTest, InviteAgent) {
    std::string session_id;
    aid_->Sessions().CreateSession({}, &session_id);

    Result r = aid_->Sessions().InviteAgent(session_id, "agent-2");
    EXPECT_TRUE(r.ok());

    std::vector<SessionMember> members;
    r = aid_->Sessions().GetMemberList(session_id, &members);
    EXPECT_TRUE(r.ok());
    EXPECT_EQ(members.size(), 2u);
    EXPECT_EQ(members[1].agent_id, "agent-2");
}

TEST_F(SessionTest, InviteAgentTwice) {
    std::string session_id;
    aid_->Sessions().CreateSession({}, &session_id);

    aid_->Sessions().InviteAgent(session_id, "agent-2");
    Result r = aid_->Sessions().InviteAgent(session_id, "agent-2");
    EXPECT_TRUE(r.ok());

    std::vector<SessionMember> members;
    aid_->Sessions().GetMemberList(session_id, &members);
    EXPECT_EQ(members.size(), 2u);
}

TEST_F(SessionTest, InviteToNonExistentSession) {
    Result r = aid_->Sessions().InviteAgent("non-existent", "agent-2");
    EXPECT_FALSE(r.ok());
    EXPECT_EQ(r.code, static_cast<int>(ErrorCode::SESSION_NOT_FOUND));
}

TEST_F(SessionTest, JoinSession) {
    std::string session_id;
    aid_->Sessions().CreateSession({}, &session_id);

    Result r = aid_->Sessions().JoinSession(session_id);
    EXPECT_TRUE(r.ok());
}

TEST_F(SessionTest, JoinNonExistentSession) {
    Result r = aid_->Sessions().JoinSession("non-existent");
    EXPECT_FALSE(r.ok());
    EXPECT_EQ(r.code, static_cast<int>(ErrorCode::SESSION_NOT_FOUND));
}

TEST_F(SessionTest, LeaveSession) {
    std::string session_id;
    aid_->Sessions().CreateSession({"agent-2"}, &session_id);

    Result r = aid_->Sessions().LeaveSession(session_id);
    EXPECT_TRUE(r.ok());

    std::vector<SessionMember> members;
    aid_->Sessions().GetMemberList(session_id, &members);
    EXPECT_EQ(members.size(), 1u);
    EXPECT_EQ(members[0].agent_id, "agent-2");
}

TEST_F(SessionTest, LeaveNonExistentSession) {
    Result r = aid_->Sessions().LeaveSession("non-existent");
    EXPECT_FALSE(r.ok());
    EXPECT_EQ(r.code, static_cast<int>(ErrorCode::SESSION_NOT_FOUND));
}

TEST_F(SessionTest, CloseSession) {
    std::string session_id;
    aid_->Sessions().CreateSession({}, &session_id);

    Result r = aid_->Sessions().CloseSession(session_id);
    EXPECT_TRUE(r.ok());

    Session* session = aid_->Sessions().GetSession(session_id);
    ASSERT_NE(session, nullptr);

    std::vector<Block> blocks = {Block::Text("Hello")};
    r = session->SendMessage(blocks);
    EXPECT_FALSE(r.ok());
    EXPECT_EQ(r.code, static_cast<int>(ErrorCode::SESSION_CLOSED));
}

TEST_F(SessionTest, CloseNonExistentSession) {
    Result r = aid_->Sessions().CloseSession("non-existent");
    EXPECT_FALSE(r.ok());
    EXPECT_EQ(r.code, static_cast<int>(ErrorCode::SESSION_NOT_FOUND));
}

TEST_F(SessionTest, EjectAgent) {
    std::string session_id;
    aid_->Sessions().CreateSession({"agent-2", "agent-3"}, &session_id);

    Result r = aid_->Sessions().EjectAgent(session_id, "agent-2");
    EXPECT_TRUE(r.ok());

    std::vector<SessionMember> members;
    aid_->Sessions().GetMemberList(session_id, &members);
    EXPECT_EQ(members.size(), 2u);
    EXPECT_EQ(members[0].agent_id, "test-agent");
    EXPECT_EQ(members[1].agent_id, "agent-3");
}

TEST_F(SessionTest, EjectNonExistentAgent) {
    std::string session_id;
    aid_->Sessions().CreateSession({}, &session_id);

    Result r = aid_->Sessions().EjectAgent(session_id, "non-existent");
    EXPECT_TRUE(r.ok());
}

TEST_F(SessionTest, GetSession) {
    std::string session_id;
    aid_->Sessions().CreateSession({}, &session_id);

    Session* session = aid_->Sessions().GetSession(session_id);
    EXPECT_NE(session, nullptr);
    EXPECT_EQ(session->GetSessionId(), session_id);
}

TEST_F(SessionTest, GetNonExistentSession) {
    Session* session = aid_->Sessions().GetSession("non-existent");
    EXPECT_EQ(session, nullptr);
}

TEST_F(SessionTest, GetActiveSessions) {
    auto sessions = aid_->Sessions().GetActiveSessions();
    EXPECT_TRUE(sessions.empty());

    std::string sid1, sid2;
    aid_->Sessions().CreateSession({}, &sid1);
    aid_->Sessions().CreateSession({}, &sid2);

    sessions = aid_->Sessions().GetActiveSessions();
    EXPECT_EQ(sessions.size(), 2u);
}

TEST_F(SessionTest, GetSessionInfo) {
    std::string session_id;
    aid_->Sessions().CreateSession({"agent-2"}, &session_id);

    SessionInfo info;
    Result r = aid_->Sessions().GetSessionInfo(session_id, &info);
    EXPECT_TRUE(r.ok());
    EXPECT_EQ(info.session_id, session_id);
    EXPECT_EQ(info.members.size(), 2u);
}

TEST_F(SessionTest, GetMemberList) {
    std::string session_id;
    aid_->Sessions().CreateSession({"agent-2", "agent-3"}, &session_id);

    std::vector<SessionMember> members;
    Result r = aid_->Sessions().GetMemberList(session_id, &members);
    EXPECT_TRUE(r.ok());
    EXPECT_EQ(members.size(), 3u);
}

TEST_F(SessionTest, GetMemberListNullOutput) {
    std::string session_id;
    aid_->Sessions().CreateSession({}, &session_id);

    Result r = aid_->Sessions().GetMemberList(session_id, nullptr);
    EXPECT_FALSE(r.ok());
    EXPECT_EQ(r.code, static_cast<int>(ErrorCode::INVALID_ARGUMENT));
}

TEST_F(SessionTest, SessionIsMember) {
    std::string session_id;
    aid_->Sessions().CreateSession({"agent-2"}, &session_id);

    Session* session = aid_->Sessions().GetSession(session_id);
    ASSERT_NE(session, nullptr);

    EXPECT_TRUE(session->IsMember("test-agent"));
    EXPECT_TRUE(session->IsMember("agent-2"));
    EXPECT_FALSE(session->IsMember("agent-3"));
}

TEST_F(SessionTest, SessionGetMembers) {
    std::string session_id;
    aid_->Sessions().CreateSession({"agent-2"}, &session_id);

    Session* session = aid_->Sessions().GetSession(session_id);
    ASSERT_NE(session, nullptr);

    auto members = session->GetMembers();
    EXPECT_EQ(members.size(), 2u);
}

TEST_F(SessionTest, SendMessageOnClosedSession) {
    std::string session_id;
    aid_->Sessions().CreateSession({}, &session_id);
    aid_->Sessions().CloseSession(session_id);

    Session* session = aid_->Sessions().GetSession(session_id);
    ASSERT_NE(session, nullptr);

    std::vector<Block> blocks = {Block::Text("Hello")};
    Result r = session->SendMessage(blocks);
    EXPECT_FALSE(r.ok());
    EXPECT_EQ(r.code, static_cast<int>(ErrorCode::SESSION_CLOSED));
}

TEST_F(SessionTest, CreateStreamOnClosedSession) {
    std::string session_id;
    aid_->Sessions().CreateSession({}, &session_id);
    aid_->Sessions().CloseSession(session_id);

    Session* session = aid_->Sessions().GetSession(session_id);
    ASSERT_NE(session, nullptr);

    Stream* stream = nullptr;
    Result r = session->CreateStream("receiver", "text/plain", &stream);
    EXPECT_FALSE(r.ok());
    EXPECT_EQ(r.code, static_cast<int>(ErrorCode::SESSION_CLOSED));
}

}  // namespace
}  // namespace agentcp
