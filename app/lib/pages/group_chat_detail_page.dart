import 'dart:convert';
import 'package:flutter/material.dart';
import '../services/agentcp_service.dart';
import '../services/agent_info_service.dart';
import '../widgets/group_avatar_widget.dart';
import 'group_members_page.dart';

class GroupChatDetailPage extends StatefulWidget {
  final GroupItem group;
  final String currentAid;

  const GroupChatDetailPage({
    super.key,
    required this.group,
    required this.currentAid,
  });

  @override
  State<GroupChatDetailPage> createState() => _GroupChatDetailPageState();
}

class _GroupChatDetailPageState extends State<GroupChatDetailPage> {
  final _messageController = TextEditingController();
  final _scrollController = ScrollController();

  List<GroupChatMessage> _messages = [];
  bool _isLoading = true;
  bool _isSending = false;

  // Save original callbacks so we can restore them on dispose
  Function(String, String)? _prevOnGroupMessageBatch;
  Function(String, int, String, String)? _prevOnGroupNewMessage;

  @override
  void initState() {
    super.initState();
    _setupCallbacks();
    _init();
  }

  void _setupCallbacks() {
    _prevOnGroupMessageBatch = AgentCPService.onGroupMessageBatch;
    _prevOnGroupNewMessage = AgentCPService.onGroupNewMessage;

    AgentCPService.onGroupMessageBatch = (groupId, batchJson) {
      _prevOnGroupMessageBatch?.call(groupId, batchJson);
      if (groupId == widget.group.groupId && mounted && !_isSending) {
        _loadMessages();
        AgentCPService.groupMarkRead(widget.group.groupId);
      }
    };

    AgentCPService.onGroupNewMessage = (groupId, latestMsgId, sender, preview) {
      _prevOnGroupNewMessage?.call(groupId, latestMsgId, sender, preview);
      if (groupId == widget.group.groupId && mounted && !_isSending) {
        _loadMessages();
        AgentCPService.groupMarkRead(widget.group.groupId);
      }
    };
  }

  @override
  void dispose() {
    // Restore original callbacks for ChatPage
    AgentCPService.onGroupMessageBatch = _prevOnGroupMessageBatch;
    AgentCPService.onGroupNewMessage = _prevOnGroupNewMessage;
    _messageController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  Future<void> _init() async {
    await AgentCPService.joinGroupSession(widget.group.groupId);
    await AgentCPService.groupMarkRead(widget.group.groupId);
    await _loadMessages();
  }

  Future<void> _loadMessages() async {
    final result = await AgentCPService.groupGetMessages(widget.group.groupId, limit: 200);
    if (result['success'] == true && result['messages'] != null) {
      final messages = (result['messages'] as List).map((m) {
        final map = Map<String, dynamic>.from(m);
        return GroupChatMessage(
          msgId: (map['msgId'] ?? '').toString(),
          groupId: (map['groupId'] ?? '').toString(),
          sender: (map['sender'] ?? '').toString(),
          content: (map['content'] ?? '').toString(),
          contentType: (map['contentType'] ?? 'text').toString(),
          timestamp: map['timestamp'] is int ? map['timestamp'] : int.tryParse(map['timestamp']?.toString() ?? '0') ?? 0,
          isMine: (map['sender'] ?? '').toString() == widget.currentAid,
        );
      }).toList();
      
      if (mounted) {
        setState(() { 
          _messages = messages; 
          _isLoading = false;
        });
        _scrollToBottom();
      }
    }
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 200),
          curve: Curves.easeOut,
        );
      }
    });
  }

  Future<void> _sendMessage() async {
    final text = _messageController.text.trim();
    if (text.isEmpty) return;
    _messageController.clear();

    final msg = GroupChatMessage(
      msgId: DateTime.now().millisecondsSinceEpoch.toString(),
      groupId: widget.group.groupId,
      sender: widget.currentAid,
      content: text,
      contentType: 'text',
      timestamp: DateTime.now().millisecondsSinceEpoch,
      isMine: true,
    );

    setState(() { _messages.add(msg); });
    _scrollToBottom();

    _isSending = true;
    final result = await AgentCPService.groupSendMessage(
      groupId: widget.group.groupId,
      content: text,
    );
    _isSending = false;

    if (result['success'] != true) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Send failed: ${result['message']}')),
        );
      }
    }

    // Reload to get the confirmed message from server
    if (mounted) {
      await _loadMessages();
    }
  }

  void _showGroupInfoDialog() async {
    final infoResult = await AgentCPService.groupGetInfo(widget.group.groupId);
    final membersResult = await AgentCPService.groupGetMembers(widget.group.groupId);

    Map<String, dynamic> info = {};
    List<dynamic> members = [];
    try {
      if (infoResult['success'] == true && infoResult['data'] != null) {
        info = _extractMap(infoResult['data']);
      }
      if (membersResult['success'] == true && membersResult['data'] != null) {
        members = _extractList(
          membersResult['data'],
          listKeys: const ['members'],
        );
      }
    } catch (_) {}

    if (!mounted) return;
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(info['name'] ?? widget.group.groupName),
        content: SizedBox(
          width: double.maxFinite,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (info['description'] != null && (info['description'] as String).isNotEmpty)
                Padding(padding: const EdgeInsets.only(bottom: 12), child: Text(info['description'])),
              Text('Members (${members.length})', style: const TextStyle(fontWeight: FontWeight.bold)),
              const SizedBox(height: 8),
              SizedBox(
                height: 200,
                child: ListView.builder(
                  shrinkWrap: true,
                  itemCount: members.length,
                  itemBuilder: (_, i) {
                    final m = members[i] is Map ? Map<String, dynamic>.from(members[i]) : {'aid': members[i].toString()};
                    return ListTile(
                      dense: true,
                      leading: const Icon(Icons.person, size: 20),
                      title: Text(
                        (m['alias'] ?? m['aid'] ?? m['agent_id'] ?? '').toString(),
                        style: const TextStyle(fontSize: 13),
                      ),
                    );
                  },
                ),
              ),
            ],
          ),
        ),
        actions: [TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Close'))],
      ),
    );
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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: GestureDetector(
          onTap: _showGroupInfoDialog,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(widget.group.groupName.isNotEmpty ? widget.group.groupName : 'Group Chat', style: const TextStyle(fontSize: 16)),
              Text(widget.group.groupId.substring(0, 8) + '...', 
                  style: const TextStyle(fontSize: 10, color: Colors.black54)),
            ],
          ),
        ),
        backgroundColor: Theme.of(context).colorScheme.inversePrimary,
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loadMessages,
            tooltip: 'Refresh Messages',
          ),
          IconButton(
            icon: const Icon(Icons.group),
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (_) => GroupMembersPage(
                    groupName: widget.group.groupName,
                    memberAids: widget.group.memberAids,
                  ),
                ),
              );
            },
            tooltip: 'Group Members',
          ),
        ],
      ),
      body: Column(
        children: [
          Expanded(child: _buildChatArea()),
          _buildMessageInput(),
        ],
      ),
    );
  }

  Widget _buildChatArea() {
    if (_isLoading) {
      return const Center(child: CircularProgressIndicator());
    }
    
    if (_messages.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            GroupAvatarWidget(
              memberAids: widget.group.memberAids,
              size: 72,
            ),
            const SizedBox(height: 12),
            const Text('No messages yet. Send the first one!', style: TextStyle(color: Colors.grey)),
          ],
        ),
      );
    }
    
    return ListView.builder(
      controller: _scrollController,
      padding: const EdgeInsets.all(16),
      itemCount: _messages.length,
      itemBuilder: (context, index) => _buildMessageBubble(_messages[index]),
    );
  }

  Widget _buildMessageBubble(GroupChatMessage msg) {
    final isMine = msg.isMine;
    return FutureBuilder<AgentInfo>(
      future: AgentInfoService().getAgentInfo(msg.sender),
      builder: (context, snapshot) {
        final info = snapshot.data;
        final avatarPath = AgentInfoService().getAvatarAssetPath(info?.type ?? '');
        final displayName = (info?.name.isNotEmpty == true) ? info!.name : msg.sender;

        return Row(
          mainAxisAlignment: isMine ? MainAxisAlignment.end : MainAxisAlignment.start,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (!isMine)
              Padding(
                padding: const EdgeInsets.only(right: 8.0, top: 8.0),
                child: CircleAvatar(backgroundImage: AssetImage(avatarPath), radius: 16),
              ),
            Flexible(
              child: Column(
                crossAxisAlignment: isMine ? CrossAxisAlignment.end : CrossAxisAlignment.start,
                children: [
                  if (!isMine)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 2, left: 4, right: 4),
                      child: Text(displayName,
                          style: TextStyle(fontSize: 11, color: Colors.grey[600], fontWeight: FontWeight.bold)),
                    ),
                  Container(
                    margin: const EdgeInsets.only(bottom: 8),
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                    decoration: BoxDecoration(
                      color: isMine ? Colors.blue[600] : Colors.white,
                      borderRadius: BorderRadius.circular(16),
                      border: isMine ? null : Border.all(color: Colors.grey[300]!),
                      boxShadow: [
                        BoxShadow(color: Colors.black.withValues(alpha: 0.05), blurRadius: 2, offset: const Offset(0, 1)),
                      ],
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(msg.content, style: TextStyle(color: isMine ? Colors.white : Colors.black87, fontSize: 15)),
                        const SizedBox(height: 2),
                        Text(
                          DateTime.fromMillisecondsSinceEpoch(msg.timestamp).toString().substring(11, 16),
                          style: TextStyle(fontSize: 10, color: isMine ? Colors.white70 : Colors.grey[400]),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            if (isMine)
              Padding(
                padding: const EdgeInsets.only(left: 8.0, top: 8.0),
                child: CircleAvatar(backgroundImage: AssetImage(AgentInfoService().getAvatarAssetPath('human')), radius: 16),
              ),
          ],
        );
      },
    );
  }

  Widget _buildMessageInput() {
    return SafeArea(
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
        decoration: BoxDecoration(
          color: Colors.white,
          boxShadow: [
            BoxShadow(color: Colors.grey.withValues(alpha: 0.2), blurRadius: 4, offset: const Offset(0, -1)),
          ],
        ),
        child: Row(
          children: [
            Expanded(
              child: TextField(
                controller: _messageController,
                decoration: const InputDecoration(
                  hintText: 'Type a message...',
                  border: OutlineInputBorder(borderRadius: BorderRadius.all(Radius.circular(24))),
                  contentPadding: EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                ),
                textInputAction: TextInputAction.send,
                onSubmitted: (_) => _sendMessage(),
              ),
            ),
            const SizedBox(width: 8),
            IconButton(onPressed: _sendMessage, icon: const Icon(Icons.send), color: Colors.deepPurple),
          ],
        ),
      ),
    );
  }
}
