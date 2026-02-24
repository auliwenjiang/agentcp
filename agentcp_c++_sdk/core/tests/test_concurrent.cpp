#include <gtest/gtest.h>
#include <thread>
#include <vector>
#include <atomic>
#include "agentcp/agentcp.h"

namespace agentcp {
namespace {

class ConcurrentTest : public ::testing::Test {
protected:
    void SetUp() override {
        AgentCP::Instance().Shutdown();
        AgentCP::Instance().Initialize();
    }

    void TearDown() override {
        AgentCP::Instance().Shutdown();
    }
};

TEST_F(ConcurrentTest, ConcurrentCreateAID) {
    const int num_threads = 10;
    std::vector<std::thread> threads;
    std::atomic<int> success_count{0};

    for (int i = 0; i < num_threads; ++i) {
        threads.emplace_back([i, &success_count]() {
            AgentID* aid = nullptr;
            std::string aid_name = "agent-" + std::to_string(i);
            Result r = AgentCP::Instance().CreateAID(aid_name, "password", &aid);
            if (r.ok()) {
                success_count++;
            }
        });
    }

    for (auto& t : threads) {
        t.join();
    }

    EXPECT_EQ(success_count.load(), num_threads);
    EXPECT_EQ(AgentCP::Instance().ListAIDs().size(), static_cast<size_t>(num_threads));
}

TEST_F(ConcurrentTest, ConcurrentDeleteAID) {
    const int num_agents = 10;
    for (int i = 0; i < num_agents; ++i) {
        AgentID* aid = nullptr;
        AgentCP::Instance().CreateAID("agent-" + std::to_string(i), "password", &aid);
    }

    std::vector<std::thread> threads;
    std::atomic<int> success_count{0};

    for (int i = 0; i < num_agents; ++i) {
        threads.emplace_back([i, &success_count]() {
            Result r = AgentCP::Instance().DeleteAID("agent-" + std::to_string(i));
            if (r.ok()) {
                success_count++;
            }
        });
    }

    for (auto& t : threads) {
        t.join();
    }

    EXPECT_EQ(success_count.load(), num_agents);
    EXPECT_TRUE(AgentCP::Instance().ListAIDs().empty());
}

TEST_F(ConcurrentTest, ConcurrentOnlineOffline) {
    AgentID* aid = nullptr;
    AgentCP::Instance().CreateAID("test-agent", "password", &aid);

    const int num_threads = 20;
    std::vector<std::thread> threads;

    for (int i = 0; i < num_threads; ++i) {
        threads.emplace_back([aid, i]() {
            if (i % 2 == 0) {
                aid->Online();
            } else {
                aid->Offline();
            }
        });
    }

    for (auto& t : threads) {
        t.join();
    }

    EXPECT_TRUE(aid->IsValid());
}

TEST_F(ConcurrentTest, ConcurrentSessionCreation) {
    AgentID* aid = nullptr;
    AgentCP::Instance().CreateAID("test-agent", "password", &aid);
    aid->Online();

    const int num_threads = 10;
    std::vector<std::thread> threads;
    std::atomic<int> success_count{0};

    for (int i = 0; i < num_threads; ++i) {
        threads.emplace_back([aid, &success_count]() {
            std::string session_id;
            Result r = aid->Sessions().CreateSession({}, &session_id);
            if (r.ok()) {
                success_count++;
            }
        });
    }

    for (auto& t : threads) {
        t.join();
    }

    EXPECT_EQ(success_count.load(), num_threads);
    EXPECT_EQ(aid->Sessions().GetActiveSessions().size(), static_cast<size_t>(num_threads));
}

TEST_F(ConcurrentTest, ConcurrentInviteAgent) {
    AgentID* aid = nullptr;
    AgentCP::Instance().CreateAID("test-agent", "password", &aid);
    aid->Online();

    std::string session_id;
    aid->Sessions().CreateSession({}, &session_id);

    const int num_threads = 10;
    std::vector<std::thread> threads;

    for (int i = 0; i < num_threads; ++i) {
        threads.emplace_back([aid, &session_id, i]() {
            std::string agent_name = "agent-" + std::to_string(i);
            aid->Sessions().InviteAgent(session_id, agent_name);
        });
    }

    for (auto& t : threads) {
        t.join();
    }

    std::vector<SessionMember> members;
    aid->Sessions().GetMemberList(session_id, &members);
    EXPECT_EQ(members.size(), static_cast<size_t>(num_threads + 1));
}

TEST_F(ConcurrentTest, ConcurrentEjectAgent) {
    AgentID* aid = nullptr;
    AgentCP::Instance().CreateAID("test-agent", "password", &aid);
    aid->Online();

    std::vector<std::string> agent_names;
    for (int i = 0; i < 10; ++i) {
        agent_names.push_back("agent-" + std::to_string(i));
    }

    std::string session_id;
    aid->Sessions().CreateSession(agent_names, &session_id);

    std::vector<std::thread> threads;

    for (int i = 0; i < 10; ++i) {
        threads.emplace_back([aid, &session_id, i]() {
            std::string agent_name = "agent-" + std::to_string(i);
            aid->Sessions().EjectAgent(session_id, agent_name);
        });
    }

    for (auto& t : threads) {
        t.join();
    }

    std::vector<SessionMember> members;
    aid->Sessions().GetMemberList(session_id, &members);
    EXPECT_EQ(members.size(), 1u);
    EXPECT_EQ(members[0].agent_id, "test-agent");
}

TEST_F(ConcurrentTest, ConcurrentReadWriteMembers) {
    AgentID* aid = nullptr;
    AgentCP::Instance().CreateAID("test-agent", "password", &aid);
    aid->Online();

    std::string session_id;
    aid->Sessions().CreateSession({}, &session_id);

    const int num_threads = 20;
    std::vector<std::thread> threads;
    std::atomic<int> read_count{0};
    std::atomic<int> write_count{0};

    for (int i = 0; i < num_threads; ++i) {
        threads.emplace_back([aid, &session_id, i, &read_count, &write_count]() {
            if (i % 2 == 0) {
                std::vector<SessionMember> members;
                Result r = aid->Sessions().GetMemberList(session_id, &members);
                if (r.ok()) {
                    read_count++;
                }
            } else {
                std::string agent_name = "agent-" + std::to_string(i);
                Result r = aid->Sessions().InviteAgent(session_id, agent_name);
                if (r.ok()) {
                    write_count++;
                }
            }
        });
    }

    for (auto& t : threads) {
        t.join();
    }

    EXPECT_EQ(read_count.load(), num_threads / 2);
    EXPECT_EQ(write_count.load(), num_threads / 2);
}

TEST_F(ConcurrentTest, ConcurrentSessionOperations) {
    AgentID* aid = nullptr;
    AgentCP::Instance().CreateAID("test-agent", "password", &aid);
    aid->Online();

    std::string session_id;
    aid->Sessions().CreateSession({"agent-2", "agent-3"}, &session_id);

    const int num_threads = 30;
    std::vector<std::thread> threads;

    for (int i = 0; i < num_threads; ++i) {
        threads.emplace_back([aid, &session_id, i]() {
            int op = i % 3;
            if (op == 0) {
                std::vector<SessionMember> members;
                aid->Sessions().GetMemberList(session_id, &members);
            } else if (op == 1) {
                std::string agent_name = "agent-" + std::to_string(i);
                aid->Sessions().InviteAgent(session_id, agent_name);
            } else {
                Session* session = aid->Sessions().GetSession(session_id);
                if (session) {
                    session->IsMember("agent-2");
                }
            }
        });
    }

    for (auto& t : threads) {
        t.join();
    }

    Session* session = aid->Sessions().GetSession(session_id);
    ASSERT_NE(session, nullptr);
    EXPECT_TRUE(session->IsMember("test-agent"));
}

TEST_F(ConcurrentTest, ConcurrentCloseAndAccess) {
    AgentID* aid = nullptr;
    AgentCP::Instance().CreateAID("test-agent", "password", &aid);
    aid->Online();

    std::string session_id;
    aid->Sessions().CreateSession({}, &session_id);

    std::vector<std::thread> threads;

    threads.emplace_back([aid, &session_id]() {
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
        aid->Sessions().CloseSession(session_id);
    });

    for (int i = 0; i < 10; ++i) {
        threads.emplace_back([aid, &session_id]() {
            Session* session = aid->Sessions().GetSession(session_id);
            if (session) {
                std::vector<Block> blocks = {Block::Text("Hello")};
                session->SendMessage(blocks);
            }
        });
    }

    for (auto& t : threads) {
        t.join();
    }
}

TEST_F(ConcurrentTest, ConcurrentDeleteAndAccess) {
    AgentID* aid = nullptr;
    AgentCP::Instance().CreateAID("test-agent", "password", &aid);

    std::vector<std::thread> threads;

    threads.emplace_back([]() {
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
        AgentCP::Instance().DeleteAID("test-agent");
    });

    for (int i = 0; i < 10; ++i) {
        threads.emplace_back([aid]() {
            for (int j = 0; j < 100; ++j) {
                aid->IsValid();
                aid->IsOnline();
                aid->GetState();
            }
        });
    }

    for (auto& t : threads) {
        t.join();
    }

    EXPECT_FALSE(aid->IsValid());
}

}  // namespace
}  // namespace agentcp
