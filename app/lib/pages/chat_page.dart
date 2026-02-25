import 'dart:convert';
import 'package:flutter/material.dart';
import '../i18n/app_language.dart';
import '../i18n/app_texts.dart';
import '../services/app_lifecycle_service.dart';
import '../services/agentcp_service.dart';
import '../services/agent_info_service.dart';
import '../services/message_store.dart';
import '../widgets/group_avatar_widget.dart';
import 'agentcp_page.dart';
import 'chat_detail_page.dart';
import 'group_chat_detail_page.dart';
import 'create_group_page.dart';

enum ChatType {
  p2p,
  group,
}

class UnifiedChatListItem {
  final ChatType type;
  final String id;
  final String name;
  final int lastMsgTime;
  final String lastMsgText;
  final int unreadCount;
  final dynamic data; // Holds SessionItem or GroupItem

  UnifiedChatListItem({
    required this.type,
    required this.id,
    required this.name,
    required this.lastMsgTime,
    required this.lastMsgText,
    required this.unreadCount,
    required this.data,
  });
}

class ChatPage extends StatefulWidget {
  const ChatPage({super.key});

  @override
  State<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends State<ChatPage> {
  final _scaffoldKey = GlobalKey<ScaffoldState>();

  List<SessionItem> _p2pSessions = [];
  List<GroupItem> _groupSessions = [];
  
  String? _currentAid;
  bool _isSyncing = false;
  
  AgentInfo? _currentAgentInfo;
  final Map<String, AgentInfo> _peerAgentInfoCache = {};

  @override
  void initState() {
    super.initState();
    _init();
  }

  @override
  void dispose() {
    AgentCPService.onMessageReceived = null;
    AgentCPService.onInviteReceived = null;
    AgentCPService.onStateChanged = null;
    AgentCPService.onGroupMessageBatch = null;
    AgentCPService.onGroupNewMessage = null;
    AgentCPService.onGroupInvite = null;
    AgentCPService.onGroupJoinApproved = null;
    super.dispose();
  }

  Future<void> _init() async {
    final aid = await AgentCPService.getCurrentAID();
    setState(() {
      _currentAid = aid;
    });

    if (aid != null) {
      // Set SDK handlers for both P2P and Group
      await AgentCPService.setGroupHandlers();

      // Load from local cache first (fast)
      await Future.wait([
        _loadP2PSessions(),
        _loadGroupSessionsFromCache(),
      ]);

      // Then sync from server (login scenario)
      _syncGroupSessionsFromServer();

      final agentInfo = await AgentInfoService().getAgentInfo(aid);
      setState(() {
        _currentAgentInfo = agentInfo;
      });
      _loadPeerAgentInfos();
    }

    // P2P Listeners
    AgentCPService.onMessageReceived = (msg) async {
      setState(() {
        var session = _findOrCreateSession(msg.sessionId, msg.sender);
        session.addMessage(msg);
      });
    };

    AgentCPService.onInviteReceived = (sessionId, inviterId) async {
      debugPrint('[ChatList] Invite received: session=$sessionId, inviter=$inviterId');
      await AgentCPService.joinSession(sessionId);
      setState(() {
        _findOrCreateSession(sessionId, inviterId);
      });
    };

    AgentCPService.onStateChanged = (oldState, newState) {
      // Auto-reconnect: if state changed from Online(3) to Offline(0),
      // attempt to reconnect after a short delay
      if (oldState == 3 && newState == 0) {
        debugPrint('[ChatPage] Connection lost, attempting auto-reconnect...');
        Future.delayed(const Duration(seconds: 2), () async {
          final stillOffline = !(await AgentCPService.isOnline());
          if (stillOffline && _currentAid != null) {
            debugPrint('[ChatPage] Still offline, calling online()...');
            await AgentCPService.online();
          }
        });
      }
    };

    // Group Listeners
    AgentCPService.onGroupMessageBatch = (groupId, batchJson) {
      _loadGroupSessionsFromCache();
    };

    AgentCPService.onGroupNewMessage = (groupId, latestMsgId, sender, preview) {
      _loadGroupSessionsFromCache();
    };

    AgentCPService.onGroupInvite = (groupId, groupAddress, invitedBy) {
      _showSnack(AppTexts.receivedGroupInvite(context, invitedBy));
      _syncGroupSessionsFromServer();
    };

    AgentCPService.onGroupJoinApproved = (groupId, groupAddress) {
      _showSnack(AppTexts.joinApprovedForGroup(context, groupId));
      // Finalize: join group session for real-time messages
      AgentCPService.joinGroupSession(groupId).then((_) {
        _syncGroupSessionsFromServer();
      }).catchError((_) {
        _syncGroupSessionsFromServer();
      });
    };

    final sessResult = await AgentCPService.getActiveSessions();
    if (sessResult['success'] == true && sessResult['sessions'] != null) {
      final sessionIds = List<String>.from(sessResult['sessions']);
      for (final sid in sessionIds) {
        final existing = _p2pSessions.where((s) => s.sessionId == sid);
        if (existing.isNotEmpty) continue;
        _findOrCreateSession(sid, '');
      }
    }
  }

  Future<void> _loadP2PSessions() async {
    final convResult = await AgentCPService.getAllConversations();
    if (convResult['success'] != true) return;

    final conversations = convResult['conversations'];
    if (conversations == null || conversations is! List) return;

    final loadedSessions = <SessionItem>[];
    for (final conv in conversations) {
      final map = Map<String, dynamic>.from(conv);
      final sessionId = map['sessionId'] as String? ?? '';
      var peerAid = _normalizePeerAid(map['peerAid'] as String? ?? '');
      if (sessionId.isEmpty) continue;

      final session = SessionItem(sessionId: sessionId, peerAid: peerAid);

      final msgResult = await AgentCPService.getMessages(sessionId, limit: 200);
      if (msgResult['success'] == true && msgResult['messages'] != null) {
        final messages = msgResult['messages'] as List;
        final List<ChatMessage> initialMsgs = [];
        for (final m in messages.reversed) {
          final msgMap = Map<String, dynamic>.from(m);
          final text = AgentCPService.parseBlocksJson(msgMap['blocksJson'] as String?);
          final direction = msgMap['direction'] as int? ?? 0;
          final sender = _normalizePeerAid(msgMap['sender'] as String? ?? '');
          if (peerAid.isEmpty && direction != 1 && sender.isNotEmpty && sender != _currentAid) {
            peerAid = sender;
            session.peerAid = peerAid;
          }
          initialMsgs.add(ChatMessage(
            messageId: msgMap['messageId'] as String? ?? '',
            sessionId: sessionId,
            sender: sender,
            timestamp: msgMap['timestamp'] as int? ?? 0,
            text: text,
            isMine: direction == 1,
          ));
        }
        session.addAllMessages(initialMsgs);
      }

      if (session.peerAid.isNotEmpty) {
        loadedSessions.add(session);
      }
    }

    if (mounted) {
      setState(() {
        _p2pSessions = loadedSessions;
      });
    }
  }
  
  /// Load group list from local cache only (fast, no network).
  Future<void> _loadGroupSessionsFromCache() async {
    if (_currentAid == null) return;
    final cached = await MessageStore().loadGroupList(_currentAid!);
    if (cached.isEmpty) return;
    final groups = cached.map((g) => GroupItem(
      groupId: g['groupId'] ?? '',
      groupName: g['groupName'] ?? '',
      lastMsgTime: g['lastMsgTime'] ?? 0,
      unreadCount: g['unreadCount'] ?? 0,
      lastMsgPreview: g['lastMsgPreview'] ?? '',
      memberAids: List<String>.from(g['memberAids'] ?? []),
    )).where((g) => g.groupId.isNotEmpty).toList();
    if (mounted) {
      setState(() { _groupSessions = groups; });
    }
  }

  /// Sync group list from server, update local cache. Called on login and force refresh.
  Future<void> _syncGroupSessionsFromServer() async {
    if (_currentAid == null) return;
    if (_isSyncing) return;
    setState(() => _isSyncing = true);

    final localGroupIds = <String>{};
    final allGroups = <GroupItem>[];

    // 1. Load from local message store (has message history)
    final result = await AgentCPService.groupGetGroupList();
    if (result['success'] == true && result['groups'] != null) {
      for (final g in (result['groups'] as List)) {
        final map = Map<String, dynamic>.from(g);
        final groupId = map['groupId'] ?? '';
        if (groupId.isNotEmpty) {
          localGroupIds.add(groupId);
          allGroups.add(GroupItem(
            groupId: groupId,
            groupName: map['groupName'] ?? '',
            lastMsgTime: map['lastMsgTime'] ?? 0,
            unreadCount: map['unreadCount'] ?? 0,
          ));
        }
      }
    }

    // 2. Merge server-side groups (catches groups with no local messages yet)
    try {
      final serverResult = await AgentCPService.groupListMyGroups();
      if (serverResult['success'] == true && serverResult['data'] != null) {
        final groupsList = _extractList(
          serverResult['data'],
          listKeys: const ['groups'],
        );
        if (groupsList.isNotEmpty) {
          for (final g in groupsList) {
            final map = Map<String, dynamic>.from(g);
            final groupId = _firstNonEmptyValue(
              map,
              const ['group_id', 'groupId'],
            );
            if (groupId.isEmpty) continue;
            final serverName = _firstNonEmptyValue(
              map,
              const ['name', 'group_name', 'groupName'],
            );
            if (localGroupIds.contains(groupId)) {
              final idx = allGroups.indexWhere((item) => item.groupId == groupId);
              if (idx >= 0 &&
                  _shouldResolveGroupName(allGroups[idx].groupName, groupId) &&
                  serverName.isNotEmpty) {
                final old = allGroups[idx];
                allGroups[idx] = GroupItem(
                  groupId: old.groupId,
                  groupName: serverName,
                  lastMsgTime: old.lastMsgTime,
                  unreadCount: old.unreadCount,
                );
              }
            } else {
              allGroups.add(GroupItem(
                groupId: groupId,
                groupName: serverName,
                lastMsgTime: 0,
                unreadCount: 0,
              ));
            }
          }
        }
      }
    } catch (e) {
      debugPrint('[ChatList] groupListMyGroups failed: $e');
    }

    // 3. Fetch last message preview and member avatars for each group
    final groupsWithPreview = <GroupItem>[];
    for (final g in allGroups) {
      String preview = '';
      int lastTime = g.lastMsgTime;
      List<String> memberAids = [];
      try {
        final msgResult = await AgentCPService.groupGetMessages(g.groupId, limit: 1);
        if (msgResult['success'] == true && msgResult['messages'] != null) {
          final messages = msgResult['messages'] as List;
          if (messages.isNotEmpty) {
            final lastMsg = Map<String, dynamic>.from(messages.last);
            preview = lastMsg['content'] as String? ?? '';
            final msgTime = lastMsg['timestamp'] as int? ?? 0;
            if (msgTime > lastTime) lastTime = msgTime;
          }
        }
      } catch (e) {
        debugPrint('[ChatList] fetch group last msg failed for ${g.groupId}: $e');
      }
      try {
        final membersResult = await AgentCPService.groupGetMembers(g.groupId);
        if (membersResult['success'] == true && membersResult['data'] != null) {
          final membersList = _extractList(
            membersResult['data'],
            listKeys: const ['members'],
          );
          for (final m in membersList) {
            if (memberAids.length >= 9) break;
            final aid = m is Map
                ? _firstNonEmptyValue(
                    m,
                    const ['aid', 'agent_id', 'agentId'],
                  )
                : m.toString();
            if (aid.isNotEmpty) memberAids.add(aid);
          }
        }
      } catch (e) {
        debugPrint('[ChatList] fetch group members failed for ${g.groupId}: $e');
      }
      String groupName = g.groupName;
      if (_shouldResolveGroupName(groupName, g.groupId)) {
        try {
          final infoResult = await AgentCPService.groupGetInfo(g.groupId);
          if (infoResult['success'] == true && infoResult['data'] != null) {
            final info = _extractMap(infoResult['data']);
            final name = _firstNonEmptyValue(
              info,
              const ['name', 'group_name', 'groupName'],
            );
            if (name.isNotEmpty) groupName = name;
          }
        } catch (e) {
          debugPrint('[ChatList] groupGetInfo failed for ${g.groupId}: $e');
        }
      }
      groupsWithPreview.add(GroupItem(
        groupId: g.groupId,
        groupName: groupName,
        lastMsgTime: lastTime,
        unreadCount: g.unreadCount,
        lastMsgPreview: preview,
        memberAids: memberAids,
      ));
    }

    // 4. Save to local cache
    final cacheList = groupsWithPreview.map((g) => {
      'groupId': g.groupId,
      'groupName': g.groupName,
      'lastMsgTime': g.lastMsgTime,
      'unreadCount': g.unreadCount,
      'lastMsgPreview': g.lastMsgPreview,
      'memberAids': g.memberAids,
    }).toList();
    await MessageStore().saveGroupList(_currentAid!, cacheList);

    if (mounted) {
      setState(() {
        _groupSessions = groupsWithPreview;
        _isSyncing = false;
      });
    }
  }

  SessionItem _findOrCreateSession(String sessionId, String peerAid) {
    final existing = _p2pSessions.where((s) => s.sessionId == sessionId);
    final normalizedPeerAid = _normalizePeerAid(peerAid);
    if (existing.isNotEmpty) {
      final current = existing.first;
      if (current.peerAid.isEmpty && normalizedPeerAid.isNotEmpty) {
        current.peerAid = normalizedPeerAid;
      }
      return current;
    }
    final session = SessionItem(sessionId: sessionId, peerAid: normalizedPeerAid);
    _p2pSessions.add(session);
    if (normalizedPeerAid.isNotEmpty && !_peerAgentInfoCache.containsKey(normalizedPeerAid)) {
      AgentInfoService().getAgentInfo(normalizedPeerAid).then((info) {
        if (mounted) {
          setState(() {
            _peerAgentInfoCache[normalizedPeerAid] = info;
          });
        }
      });
    }
    return session;
  }

  void _loadPeerAgentInfos() {
    for (var s in _p2pSessions) {
      final peer = s.peerAid;
      if (peer.isEmpty || peer == 'Unknown' || _peerAgentInfoCache.containsKey(peer)) continue;
      AgentInfoService().getAgentInfo(peer).then((info) {
        if (mounted) {
          setState(() {
            _peerAgentInfoCache[peer] = info;
          });
        }
      });
    }
  }

  void _showNewChatMenu() {
    showModalBottomSheet(
      context: context,
      builder: (ctx) {
        return SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              ListTile(
                leading: const Icon(Icons.person),
                title: Text(AppTexts.newP2PChat(context)),
                onTap: () {
                  Navigator.pop(ctx);
                  _showConnectDialog();
                },
              ),
              ListTile(
                leading: const Icon(Icons.group_add),
                title: Text(AppTexts.createGroupChat(context)),
                onTap: () {
                  Navigator.pop(ctx);
                  _showCreateGroupDialog();
                },
              ),
              ListTile(
                leading: const Icon(Icons.login),
                title: Text(AppTexts.joinGroupChat(context)),
                onTap: () {
                  Navigator.pop(ctx);
                  _showJoinGroupDialog();
                },
              ),
            ],
          ),
        );
      },
    );
  }

  void _showConnectDialog() {
    final peerController = TextEditingController();
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(AppTexts.connectToPeerTitle(context)),
        content: TextField(
          controller: peerController,
          decoration: InputDecoration(
            labelText: AppTexts.peerAidLabel(context),
            hintText: AppTexts.peerAidHint(context),
            border: const OutlineInputBorder(),
          ),
          autofocus: true,
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: Text(AppTexts.cancel(context)),
          ),
          ElevatedButton(
            onPressed: () async {
              final peerAid = peerController.text.trim();
              if (peerAid.isEmpty) return;
              Navigator.pop(ctx);
              await _connectToPeer(peerAid);
            },
            child: Text(AppTexts.connectButton(context)),
          ),
        ],
      ),
    );
  }

  Future<void> _connectToPeer(String peerAid) async {
    final createResult = await AgentCPService.createSession([peerAid]);
    if (createResult['success'] != true) {
      _showSnack(AppTexts.createSessionFailed(context, '${createResult['message']}'));
      return;
    }
    final sessionId = createResult['sessionId'] as String;
    setState(() {
      _findOrCreateSession(sessionId, peerAid);
    });
    
    final session = _p2pSessions.firstWhere((s) => s.sessionId == sessionId);
    _navigateToChatDetail(session);
  }
  
  void _showCreateGroupDialog() async {
    final created = await Navigator.push<bool>(
      context,
      MaterialPageRoute(builder: (_) => const CreateGroupPage()),
    );
    if (created == true) {
      _showSnack(AppTexts.groupCreated(context));
      await _syncGroupSessionsFromServer();
    }
  }

  void _showJoinGroupDialog() {
    final urlCtrl = TextEditingController();
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(AppTexts.joinGroupTitle(context)),
        content: TextField(
          controller: urlCtrl,
          decoration: InputDecoration(
            labelText: AppTexts.groupUrlLabel(context),
            border: const OutlineInputBorder(),
          ),
          autofocus: true,
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: Text(AppTexts.cancel(context))),
          ElevatedButton(
            onPressed: () async {
              final url = urlCtrl.text.trim();
              if (url.isEmpty) return;
              Navigator.pop(ctx);
              final result = await AgentCPService.groupJoinByUrl(groupUrl: url);
              if (result['success'] == true) {
                final groupId = result['groupId'] ?? '';
                final groupName = result['groupName'] ?? groupId;
                final pending = result['pending'] == true;
                _showSnack(
                  pending
                      ? AppTexts.joinRequestSentWaiting(context)
                      : AppTexts.joinedGroupSuccessfully(context),
                );
                await _syncGroupSessionsFromServer();
                // If group not in list yet (server propagation delay), add it manually
                if (!pending && groupId.isNotEmpty && !_groupSessions.any((g) => g.groupId == groupId)) {
                  setState(() {
                    _groupSessions.add(GroupItem(
                      groupId: groupId,
                      groupName: groupName,
                      lastMsgTime: DateTime.now().millisecondsSinceEpoch,
                      unreadCount: 0,
                    ));
                  });
                }
                // Navigate to group chat
                if (!pending && groupId.isNotEmpty) {
                  final group = _groupSessions.where((g) => g.groupId == groupId);
                  if (group.isNotEmpty) {
                    _navigateToGroupChatDetail(group.first);
                  }
                }
              } else {
                _showSnack(AppTexts.joinFailed(context, '${result['message']}'));
              }
            },
            child: Text(AppTexts.joinButton(context)),
          ),
        ],
      ),
    );
  }
  
  void _showSnack(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message), duration: const Duration(seconds: 2)),
    );
  }

  void _deleteSession(String sessionId) async {
    await AgentCPService.clearSession(sessionId);
    setState(() {
      _p2pSessions.removeWhere((s) => s.sessionId == sessionId);
    });
  }
  
  void _confirmLeaveGroup(String groupId) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(AppTexts.leaveGroupTitle(context)),
        content: Text(AppTexts.leaveGroupConfirm(context)),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: Text(AppTexts.cancel(context))),
          TextButton(
            onPressed: () async {
              Navigator.pop(ctx);
              await AgentCPService.groupLeaveGroup(groupId);
              await _syncGroupSessionsFromServer();
              _showSnack(AppTexts.leftGroup(context));
            },
            style: TextButton.styleFrom(foregroundColor: Colors.red),
            child: Text(AppTexts.leaveButton(context)),
          ),
        ],
      ),
    );
  }

  String _normalizePeerAid(String value) {
    final trimmed = value.trim();
    if (trimmed.isEmpty) return '';
    if (trimmed.toLowerCase() == 'unknown') return '';
    if (trimmed.toLowerCase() == 'unknow') return '';
    return trimmed;
  }

  bool _shouldResolveGroupName(String groupName, String groupId) {
    final name = groupName.trim();
    if (name.isEmpty) return true;
    return name == groupId;
  }

  dynamic _decodeJsonLike(dynamic value) {
    if (value is String) {
      final trimmed = value.trim();
      if (trimmed.isEmpty) return value;
      if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
        try {
          return jsonDecode(trimmed);
        } catch (_) {
          return value;
        }
      }
    }
    return value;
  }

  Map<String, dynamic> _extractMap(dynamic value) {
    final decoded = _decodeJsonLike(value);
    if (decoded is Map) {
      return Map<String, dynamic>.from(decoded);
    }
    return {};
  }

  List<dynamic> _extractList(dynamic value, {List<String> listKeys = const []}) {
    final decoded = _decodeJsonLike(value);
    if (decoded is List) return decoded;
    if (decoded is Map) {
      for (final key in listKeys) {
        final nested = _decodeJsonLike(decoded[key]);
        if (nested is List) return nested;
      }
    }
    return const [];
  }

  String _firstNonEmptyValue(Map map, List<String> keys) {
    for (final key in keys) {
      final value = map[key];
      if (value == null) continue;
      final text = value.toString().trim();
      if (text.isNotEmpty) return text;
    }
    return '';
  }

  void _navigateToChatDetail(SessionItem session) async {
    final result = await Navigator.push<Map<String, dynamic>>(
      context,
      MaterialPageRoute(
        builder: (_) => ChatDetailPage(
          session: session,
          currentAid: _currentAid ?? '',
        ),
      ),
    );

    if (!mounted) return;

    if (result != null) {
      final action = result['action'] as String?;
      final newSession = result['session'] as SessionItem?;

      if (action == 'new_session' && newSession != null) {
        // Add the new session to the list and navigate to it
        setState(() {
          _findOrCreateSession(newSession.sessionId, newSession.peerAid);
        });
        _navigateToChatDetail(
          _p2pSessions.firstWhere((s) => s.sessionId == newSession.sessionId),
        );
        return;
      }

      if (action == 'switch_session' && newSession != null) {
        // Add/update the session in the list and navigate to it
        setState(() {
          final existing = _p2pSessions.where((s) => s.sessionId == newSession.sessionId);
          if (existing.isEmpty) {
            _p2pSessions.add(newSession);
          }
        });
        _navigateToChatDetail(
          _p2pSessions.firstWhere((s) => s.sessionId == newSession.sessionId),
        );
        return;
      }
    }

    setState(() {});
  }
  
  void _navigateToGroupChatDetail(GroupItem group) {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => GroupChatDetailPage(
          group: group,
          currentAid: _currentAid ?? '',
        ),
      ),
    ).then((_) {
      _loadGroupSessionsFromCache(); // Refresh group state when popping back
    });
  }

  List<UnifiedChatListItem> _getUnifiedList() {
    final list = <UnifiedChatListItem>[];

    // Map P2P Sessions
    for (final s in _p2pSessions) {
      final peer = _normalizePeerAid(s.peerAid);
      if (peer.isEmpty) continue; // Hide dirty sessions (Unknown/empty peer).
      final info = _peerAgentInfoCache[peer];
      final displayName = (info?.name.isNotEmpty == true) ? info!.name : (peer.isNotEmpty ? peer : 'Unknown');
      
      final lastMsgTime = s.messages.isNotEmpty ? s.messages.last.timestamp : 0;
      final lastMsgText = s.messages.isNotEmpty ? s.messages.last.text : '';

      list.add(UnifiedChatListItem(
        type: ChatType.p2p,
        id: s.sessionId,
        name: displayName,
        lastMsgTime: lastMsgTime,
        lastMsgText: lastMsgText,
        unreadCount: 0, // Unread count logic not fully implemented for P2P yet
        data: s,
      ));
    }

    // Map Group Sessions
    for (final g in _groupSessions) {
      list.add(UnifiedChatListItem(
        type: ChatType.group,
        id: g.groupId,
        name: g.groupName.isNotEmpty ? g.groupName : g.groupId.substring(0, 8),
        lastMsgTime: g.lastMsgTime,
        lastMsgText: g.lastMsgPreview,
        unreadCount: g.unreadCount,
        data: g,
      ));
    }

    // Sort by last message time descending
    list.sort((a, b) => b.lastMsgTime.compareTo(a.lastMsgTime));
    return list;
  }

  @override
  Widget build(BuildContext context) {
    final unifiedSessions = _getUnifiedList();

    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, result) async {
        if (didPop) return;
        await AppLifecycleService.moveTaskToBack();
      },
      child: Scaffold(
        key: _scaffoldKey,
        appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.menu),
          onPressed: () => _scaffoldKey.currentState?.openDrawer(),
        ),
        title: Text(AppTexts.chatsTitle(context)),
        backgroundColor: Theme.of(context).colorScheme.inversePrimary,
        actions: [
          IconButton(
            icon: const Icon(Icons.language),
            onPressed: _showLanguageDialog,
            tooltip: AppTexts.languageMenuLabel(context),
          ),
          IconButton(
            icon: _isSyncing
                ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.refresh),
            tooltip: AppTexts.forceRefreshTooltip(context),
            onPressed: _isSyncing ? null : _syncGroupSessionsFromServer,
          ),
          IconButton(
            icon: const Icon(Icons.add),
            onPressed: _showNewChatMenu,
            tooltip: AppTexts.startNewChat(context),
          ),
        ],
      ),
      drawer: _buildDrawer(),
      body: _buildSessionList(unifiedSessions),
      ),
    );
  }

  Future<void> _showLanguageDialog() async {
    final languageController = AppLanguageScope.of(context);
    var selected = languageController.language;

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialogState) => AlertDialog(
          title: Text(AppTexts.languageDialogTitle(context)),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              RadioListTile<AppLanguage>(
                value: AppLanguage.en,
                groupValue: selected,
                title: Text(AppTexts.languageOptionEnglish(context)),
                onChanged: (value) {
                  if (value == null) return;
                  setDialogState(() => selected = value);
                },
              ),
              RadioListTile<AppLanguage>(
                value: AppLanguage.zh,
                groupValue: selected,
                title: Text(AppTexts.languageOptionChinese(context)),
                onChanged: (value) {
                  if (value == null) return;
                  setDialogState(() => selected = value);
                },
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: Text(AppTexts.cancel(context)),
            ),
            ElevatedButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: Text(AppTexts.save(context)),
            ),
          ],
        ),
      ),
    );

    if (confirmed != true) return;
    await languageController.setLanguage(selected);
    if (!mounted) return;

    final switchedMsg = selected == AppLanguage.zh
        ? AppTexts.languageChangedToChinese(context)
        : AppTexts.languageChangedToEnglish(context);
    final path = languageController.getPersistedLocationLabel();
    final persistedMsg = AppTexts.languagePersistedTip(context, path);
    _showSnack('$switchedMsg\n$persistedMsg');
  }

  Widget _buildDrawer() {
    return Drawer(
      child: Column(
        children: [
          Container(
            width: double.infinity,
            padding: EdgeInsets.only(
              top: MediaQuery.of(context).padding.top + 16,
              left: 16, right: 16, bottom: 16,
            ),
            decoration: BoxDecoration(
              color: Theme.of(context).colorScheme.inversePrimary,
            ),
            child: Row(
              children: [
                CircleAvatar(
                  backgroundImage: AssetImage(
                    AgentInfoService().getAvatarAssetPath(_currentAgentInfo?.type ?? ''),
                  ),
                  backgroundColor: Colors.white,
                  radius: 28,
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        (_currentAgentInfo?.name.isNotEmpty == true)
                            ? _currentAgentInfo!.name
                            : (_currentAid ?? 'Not Logged In'),
                        style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Colors.white),
                      ),
                      if (_currentAid != null)
                        Text(_currentAid!,
                            style: const TextStyle(fontSize: 12, color: Colors.white70)),
                      const SizedBox(height: 4),
                    ],
                  ),
                ),
              ],
            ),
          ),
          ListTile(
            leading: const Icon(Icons.manage_accounts),
            title: Text(AppTexts.identityManagementEntry(context)),
            onTap: () {
              Navigator.pop(context);
              Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => const AgentCPPage()),
              );
            },
          ),
          const Spacer(),
          const Divider(),
          Padding(
            padding: const EdgeInsets.all(16.0),
            child: Text(AppTexts.appNameSubtitle(context), style: TextStyle(color: Colors.grey[400])),
          )
        ],
      ),
    );
  }

  Widget _buildSessionList(List<UnifiedChatListItem> items) {
    if (items.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.chat_bubble_outline, size: 64, color: Colors.grey[300]),
            const SizedBox(height: 16),
            Text(AppTexts.noChatsYet(context), style: TextStyle(color: Colors.grey[500])),
            TextButton(
              onPressed: _showNewChatMenu,
              child: Text(AppTexts.startNewChat(context)),
            ),
          ],
        ),
      );
    }

    return ListView.builder(
      itemCount: items.length,
      itemBuilder: (context, index) {
        final item = items[index];
        
        // Formulate last message time display
        final lastTimeStr = item.lastMsgTime > 0 
            ? DateTime.fromMillisecondsSinceEpoch(item.lastMsgTime).toString().substring(11, 16)
            : '';

        // Avatar logic based on type
        Widget avatar;
        if (item.type == ChatType.group) {
          final group = item.data as GroupItem;
          avatar = GroupAvatarWidget(
            memberAids: group.memberAids,
            size: 48,
          );
        } else {
          final session = item.data as SessionItem;
          final peer = session.peerAid;
          final info = _peerAgentInfoCache[peer];
          final avatarPath = AgentInfoService().getAvatarAssetPath(info?.type ?? '');
          avatar = CircleAvatar(
            backgroundImage: AssetImage(avatarPath),
            radius: 24,
          );
        }

        return ListTile(
          leading: Stack(
            clipBehavior: Clip.none,
            children: [
              avatar,
              if (item.unreadCount > 0)
                Positioned(
                  right: -2,
                  top: -2,
                  child: Container(
                    padding: const EdgeInsets.all(4),
                    decoration: const BoxDecoration(
                      color: Colors.red,
                      shape: BoxShape.circle,
                    ),
                    constraints: const BoxConstraints(
                      minWidth: 16,
                      minHeight: 16,
                    ),
                    child: Center(
                      child: Text(
                        '${item.unreadCount}',
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 10,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                  ),
                ),
            ],
          ),
          title: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Expanded(
                child: Text(
                  item.name,
                  style: const TextStyle(fontWeight: FontWeight.bold),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              if (lastTimeStr.isNotEmpty)
                Text(
                  lastTimeStr,
                  style: TextStyle(fontSize: 12, color: Colors.grey[500]),
                ),
            ],
          ),
          subtitle: Text(
            item.lastMsgText.isEmpty ? '(No messages)' : item.lastMsgText,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(color: Colors.grey[600]),
          ),
          onTap: () {
            if (item.type == ChatType.group) {
              _navigateToGroupChatDetail(item.data as GroupItem);
            } else {
              _navigateToChatDetail(item.data as SessionItem);
            }
          },
          onLongPress: () {
            if (item.type == ChatType.group) {
              _confirmLeaveGroup(item.id);
            } else {
              showDialog(
                context: context,
                builder: (ctx) => AlertDialog(
                  title: Text(AppTexts.deleteChatTitle(context)),
                  content: Text(AppTexts.deleteChatConfirm(context)),
                  actions: [
                    TextButton(
                      onPressed: () => Navigator.pop(ctx),
                      child: Text(AppTexts.cancel(context)),
                    ),
                    TextButton(
                      onPressed: () {
                        Navigator.pop(ctx);
                        _deleteSession(item.id);
                      },
                      style: TextButton.styleFrom(foregroundColor: Colors.red),
                      child: Text(AppTexts.deleteButton(context)),
                    ),
                  ],
                ),
              );
            }
          },
        );
      },
    );
  }
}
