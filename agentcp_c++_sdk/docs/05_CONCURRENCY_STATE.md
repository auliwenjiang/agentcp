# Concurrency and State

## Thread Model

### Thread Types
```
+------------------+     +------------------+     +------------------+
|   Main Thread    |     |   WS Thread      |     |   HB Thread      |
|   (App calls)    |     |   (WebSocket)    |     |   (Heartbeat)    |
+------------------+     +------------------+     +------------------+
         |                       |                       |
         v                       v                       v
+------------------------------------------------------------------+
|                      Message Queue                                |
+------------------------------------------------------------------+
         |                       |                       |
         v                       v                       v
+------------------+     +------------------+     +------------------+
|  Worker Thread 1 |     |  Worker Thread 2 |     |  Worker Thread N |
|  (Dispatcher)    |     |  (Dispatcher)    |     |  (Dispatcher)    |
+------------------+     +------------------+     +------------------+
```

### Thread Responsibilities

| Thread | Responsibility | Lifetime |
|--------|----------------|----------|
| Main | App API calls, handler registration | App lifetime |
| WebSocket | WS connect, receive, send queue | Online lifetime |
| Heartbeat | UDP send/receive loop | Online lifetime |
| Stream (per stream) | Stream push/pull | Stream lifetime |
| Dispatcher (pool) | Message handler execution | Online lifetime |
| Metrics | Periodic snapshot | Online lifetime |
| DB | Database operations | AID lifetime |

### Thread Creation and Destruction
```cpp
// Thread lifecycle tied to AgentID state
AgentID::Online() {
    // 1. Create dispatcher thread pool
    dispatcher_pool_ = new ThreadPool(config_.worker_threads);

    // 2. Start heartbeat thread
    hb_thread_ = std::thread(&HeartbeatClient::Run, hb_client_);

    // 3. Start WebSocket thread
    ws_thread_ = std::thread(&MessageClient::Run, msg_client_);

    // 4. Start metrics thread
    metrics_thread_ = std::thread(&Metrics::Run, metrics_);
}

AgentID::Offline() {
    // Reverse order shutdown
    // 1. Signal all threads to stop
    stop_flag_ = true;

    // 2. Wait for metrics thread
    metrics_thread_.join();

    // 3. Close WebSocket (triggers thread exit)
    msg_client_->Disconnect();
    ws_thread_.join();

    // 4. Stop heartbeat
    hb_client_->Stop();
    hb_thread_.join();

    // 5. Shutdown dispatcher pool
    dispatcher_pool_->Shutdown();
    delete dispatcher_pool_;
}
```

## Message Flow

### Inbound Message Flow
```
1. WS Thread receives JSON message
   |
2. Parse and validate message
   |
3. Enqueue to dispatcher queue
   |
4. Worker thread dequeues
   |
5. Execute registered handler
   |
6. Record metrics (latency)
```

### Outbound Message Flow
```
1. App calls SendMessage()
   |
2. Serialize to JSON
   |
3. Enqueue to WS send queue
   |
4. WS thread dequeues and sends
   |
5. Wait for ack (optional)
   |
6. Return result to app
```

## Lock Hierarchy

To prevent deadlocks, locks must be acquired in this order:

```
Level 1 (highest): global_mutex_
Level 2: aid_mutex_
Level 3: session_mutex_
Level 4: queue_mutex_
Level 5: metrics_mutex_
Level 6 (lowest): db_mutex_
```

### Lock Rules
1. Never acquire a higher-level lock while holding a lower-level lock
2. Never hold locks across async boundaries
3. Use lock_guard for automatic release
4. Prefer reader-writer locks for read-heavy data

### Lock Implementation
```cpp
class AgentID {
private:
    mutable std::shared_mutex state_mutex_;      // Level 2
    mutable std::mutex session_mutex_;           // Level 3
    mutable std::mutex send_queue_mutex_;        // Level 4

    // Read state (shared lock)
    AgentState GetState() const {
        std::shared_lock lock(state_mutex_);
        return state_;
    }

    // Write state (exclusive lock)
    void SetState(AgentState state) {
        std::unique_lock lock(state_mutex_);
        state_ = state;
    }
};
```

## Queue Design

### Message Queue
```cpp
template<typename T>
class BoundedQueue {
public:
    BoundedQueue(size_t max_size) : max_size_(max_size) {}

    // Returns false if queue is full
    bool TryPush(T item) {
        std::unique_lock lock(mutex_);
        if (queue_.size() >= max_size_) {
            return false;
        }
        queue_.push(std::move(item));
        cv_.notify_one();
        return true;
    }

    // Blocking push with timeout
    bool Push(T item, std::chrono::milliseconds timeout) {
        std::unique_lock lock(mutex_);
        if (!cv_.wait_for(lock, timeout, [this] {
            return queue_.size() < max_size_ || stopped_;
        })) {
            return false;
        }
        if (stopped_) return false;
        queue_.push(std::move(item));
        cv_.notify_one();
        return true;
    }

    // Blocking pop
    std::optional<T> Pop() {
        std::unique_lock lock(mutex_);
        cv_.wait(lock, [this] { return !queue_.empty() || stopped_; });
        if (stopped_ && queue_.empty()) return std::nullopt;
        T item = std::move(queue_.front());
        queue_.pop();
        cv_.notify_one();
        return item;
    }

    void Stop() {
        std::unique_lock lock(mutex_);
        stopped_ = true;
        cv_.notify_all();
    }

private:
    std::queue<T> queue_;
    size_t max_size_;
    bool stopped_ = false;
    std::mutex mutex_;
    std::condition_variable cv_;
};
```

### Queue Overflow Handling
| Strategy | Description | Use Case |
|----------|-------------|----------|
| Drop oldest | Remove oldest item when full | Non-critical messages |
| Drop newest | Reject new item when full | Backpressure to sender |
| Block | Wait until space available | Critical messages |
| Expand | Grow queue (with limit) | Burst handling |

### Configuration
```cpp
struct QueueConfig {
    size_t max_size = 10000;
    OverflowPolicy overflow_policy = OverflowPolicy::DropOldest;
    std::chrono::milliseconds push_timeout = 5000ms;
    bool enable_priority = true;
};
```

## Reconnect Strategy

### Exponential Backoff
```cpp
class BackoffStrategy {
public:
    BackoffStrategy(
        std::chrono::milliseconds initial = 1000ms,
        std::chrono::milliseconds max = 60000ms,
        double multiplier = 2.0,
        double jitter = 0.1
    ) : initial_(initial), max_(max),
        multiplier_(multiplier), jitter_(jitter),
        current_(initial) {}

    std::chrono::milliseconds Next() {
        auto delay = current_;

        // Add jitter
        std::random_device rd;
        std::mt19937 gen(rd());
        std::uniform_real_distribution<> dis(1.0 - jitter_, 1.0 + jitter_);
        delay = std::chrono::milliseconds(
            static_cast<int64_t>(delay.count() * dis(gen))
        );

        // Increase for next time
        current_ = std::min(
            std::chrono::milliseconds(
                static_cast<int64_t>(current_.count() * multiplier_)
            ),
            max_
        );

        return delay;
    }

    void Reset() {
        current_ = initial_;
    }

private:
    std::chrono::milliseconds initial_;
    std::chrono::milliseconds max_;
    double multiplier_;
    double jitter_;
    std::chrono::milliseconds current_;
};
```

### Reconnect Flow
```
Connection Lost
      |
      v
+---> Wait (backoff delay)
|     |
|     v
|     Attempt reconnect
|     |
|     +---> Success: Reset backoff, resume
|     |
|     +---> Failure: Increment backoff
|           |
+-----------+
      |
      v (after max retries)
Report fatal error
```

## State Machines

### MessageClient State Machine
```
                    +-------------+
                    | DISCONNECTED|<-----------------+
                    +-------------+                  |
                          |                          |
                          | Connect()                | Fatal error
                          v                          |
                    +-------------+                  |
                    | CONNECTING  |------------------+
                    +-------------+                  |
                          |                          |
                          | Connected                | Connect failed
                          v                          |
                    +-------------+                  |
            +------>|  CONNECTED  |------------------+
            |       +-------------+
            |             |
            |             | Connection lost
            |             v
            |       +-------------+
            +-------|RECONNECTING |
         Reconnected+-------------+
```

### AgentID State Machine
```
+----------+     Online()     +-----------+
| Offline  |----------------->| Connecting|
+----------+                  +-----------+
     ^                              |
     |                              | AP auth success
     |                              v
     |                        +-----------+
     |                        |Authenticating|
     |                        +-----------+
     |                              |
     |                              | HB + WS success
     |                              v
     |    Offline()           +-----------+
     +------------------------|  Online   |
     |                        +-----------+
     |                              |
     |                              | Connection lost
     |                              v
     |                        +-----------+
     +------------------------|Reconnecting|
        Unrecoverable         +-----------+
```

### Stream State Machine
```
+------+   Create()   +----------+
| Idle |------------->| Creating |
+------+              +----------+
                           |
                           | Ack received
                           v
                      +----------+
                      |  Active  |
                      +----------+
                        |      |
            Close()     |      | Error
                        v      v
                      +----------+
                      |  Closed  |
                      +----------+
```

## Scheduler

### Thread Pool Configuration
```cpp
struct SchedulerConfig {
    size_t min_threads = 2;
    size_t max_threads = 8;
    size_t queue_size = 10000;
    std::chrono::milliseconds idle_timeout = 60000ms;
    bool enable_priority = true;
};
```

### Priority Levels
```cpp
enum class TaskPriority {
    Critical = 0,   // System messages (auth, heartbeat)
    High = 1,       // Invites, acks
    Normal = 2,     // Regular messages
    Low = 3,        // Metrics, background tasks
};
```

### Thread Pool Implementation
```cpp
class ThreadPool {
public:
    ThreadPool(const SchedulerConfig& config);

    template<typename F>
    void Submit(F&& task, TaskPriority priority = TaskPriority::Normal) {
        auto wrapped = [task = std::forward<F>(task)]() {
            try {
                task();
            } catch (const std::exception& e) {
                // Log error, don't crash thread
            }
        };
        queue_.Push({priority, std::move(wrapped)});
    }

    void Shutdown();

private:
    void WorkerLoop();

    struct Task {
        TaskPriority priority;
        std::function<void()> func;

        bool operator<(const Task& other) const {
            return priority > other.priority;  // Lower value = higher priority
        }
    };

    std::priority_queue<Task> queue_;
    std::vector<std::thread> workers_;
    std::atomic<bool> stopped_{false};
};
```

## Timing and Timeouts

### Configurable Timeouts
```cpp
struct TimeoutConfig {
    // AP authentication
    std::chrono::milliseconds ap_signin_timeout = 30000ms;
    std::chrono::milliseconds ap_request_timeout = 10000ms;

    // Heartbeat
    std::chrono::milliseconds hb_signin_timeout = 10000ms;
    std::chrono::milliseconds hb_interval = 30000ms;
    int hb_miss_threshold = 3;

    // WebSocket
    std::chrono::milliseconds ws_connect_timeout = 30000ms;
    std::chrono::milliseconds ws_ping_interval = 30000ms;
    std::chrono::milliseconds ws_pong_timeout = 10000ms;
    std::chrono::milliseconds ws_send_timeout = 10000ms;

    // Stream
    std::chrono::milliseconds stream_create_timeout = 30000ms;
    std::chrono::milliseconds stream_send_timeout = 10000ms;

    // File
    std::chrono::milliseconds file_upload_timeout = 300000ms;  // 5 min
    std::chrono::milliseconds file_download_timeout = 300000ms;
    int file_retry_count = 3;
    std::chrono::milliseconds file_retry_delay = 2000ms;
};
```

## Graceful Shutdown

### Shutdown Sequence
```cpp
void AgentID::Offline() {
    // 1. Set stopping flag
    stopping_ = true;

    // 2. Stop accepting new requests
    // (SendMessage etc. will return error)

    // 3. Flush pending messages (with timeout)
    msg_client_->FlushSendQueue(5000ms);

    // 4. Close streams
    for (auto& stream : active_streams_) {
        stream->Close();
    }

    // 5. Disconnect WebSocket
    msg_client_->Disconnect();

    // 6. Stop heartbeat
    hb_client_->Stop();

    // 7. Wait for worker threads to finish current tasks
    dispatcher_pool_->Shutdown(10000ms);

    // 8. Persist any pending data
    db_manager_->Flush();

    // 9. Update state
    SetState(AgentState::Offline);
}
```

### Timeout Handling
```cpp
// If graceful shutdown takes too long, force stop
bool AgentID::OfflineWithTimeout(std::chrono::milliseconds timeout) {
    auto future = std::async(std::launch::async, [this] {
        Offline();
    });

    if (future.wait_for(timeout) == std::future_status::timeout) {
        // Force stop
        ForceStop();
        return false;
    }
    return true;
}
```

## Performance Tuning

### Recommendations
| Parameter | Low-end Device | Mid-range | High-end |
|-----------|----------------|-----------|----------|
| Worker threads | 2 | 4 | 8 |
| Queue size | 1000 | 5000 | 10000 |
| WS buffer size | 64KB | 256KB | 1MB |
| HB interval | 60s | 30s | 15s |

### Monitoring Points
- Queue depth (should stay low)
- Handler execution time (p50, p95, p99)
- Reconnect frequency
- Memory usage per thread
