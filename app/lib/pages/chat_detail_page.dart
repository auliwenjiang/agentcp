import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:http/http.dart' as http;
import '../services/agentcp_service.dart';
import '../services/agent_info_service.dart';

class ChatDetailPage extends StatefulWidget {
  final SessionItem session;
  final String currentAid;

  const ChatDetailPage({
    super.key,
    required this.session,
    required this.currentAid,
  });

  @override
  State<ChatDetailPage> createState() => _ChatDetailPageState();
}

class _ChatDetailPageState extends State<ChatDetailPage> {
  final _messageController = TextEditingController();
  final _scrollController = ScrollController();
  AgentInfo? _peerAgentInfo;
  bool _showSlashMenu = false;
  List<Map<String, dynamic>> _filteredCommands = [];
  int _selectedCommandIndex = 0;

  static const List<Map<String, dynamic>> _allCommands = [
    {'cmd': '/new', 'icon': Icons.add_circle_outline, 'label': 'New Session', 'desc': 'Create a new session with this peer'},
    {'cmd': '/session', 'icon': Icons.history, 'label': 'Switch Session', 'desc': 'Browse historical sessions'},
  ];

  @override
  void initState() {
    super.initState();
    _loadPeerAgentInfo();
    // Scroll to bottom after layout
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _scrollToBottom();
    });
    // Add listener to scroll when new messages arrive
    widget.session.addListener(_onSessionUpdated);
    // Listen for '/' input to show command menu
    _messageController.addListener(_onInputChanged);
  }

  @override
  void dispose() {
    widget.session.removeListener(_onSessionUpdated);
    _messageController.removeListener(_onInputChanged);
    _messageController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _onInputChanged() {
    final text = _messageController.text;
    if (text.startsWith('/')) {
      final query = text.toLowerCase();
      final filtered = _allCommands
          .where((c) => (c['cmd'] as String).toLowerCase().startsWith(query))
          .toList();
      setState(() {
        _filteredCommands = filtered;
        _showSlashMenu = filtered.isNotEmpty;
        _selectedCommandIndex = 0;
      });
    } else {
      if (_showSlashMenu) {
        setState(() {
          _showSlashMenu = false;
          _filteredCommands = [];
        });
      }
    }
  }

  void _onSessionUpdated() {
    if (mounted) {
      setState(() {});
      _scrollToBottom();
    }
  }

  void _loadPeerAgentInfo() async {
    final info = await AgentInfoService().getAgentInfo(widget.session.peerAid);
    if (mounted) {
      setState(() {
        _peerAgentInfo = info;
      });
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

    // If slash menu is showing, execute the selected command
    if (_showSlashMenu && _filteredCommands.isNotEmpty) {
      final cmd = _filteredCommands[_selectedCommandIndex]['cmd'] as String;
      _messageController.clear();
      setState(() {
        _showSlashMenu = false;
        _filteredCommands = [];
      });
      await _executeCommand(cmd);
      return;
    }

    // Handle slash commands typed exactly
    if (text.startsWith('/')) {
      final matched = _allCommands.where((c) => c['cmd'] == text).toList();
      if (matched.isNotEmpty) {
        _messageController.clear();
        await _executeCommand(matched.first['cmd'] as String);
        return;
      }
    }

    _messageController.clear();

    // Optimistic UI update
    final msg = ChatMessage(
      messageId: DateTime.now().millisecondsSinceEpoch.toString(),
      sessionId: widget.session.sessionId,
      sender: widget.currentAid,
      timestamp: DateTime.now().millisecondsSinceEpoch,
      text: text,
      isMine: true,
    );

    widget.session.addMessage(msg);

    // Ensure peer is invited to this session before sending
    debugPrint('[Chat] Inviting ${widget.session.peerAid} to session ${widget.session.sessionId}');
    final inviteResult = await AgentCPService.inviteAgent(widget.session.sessionId, widget.session.peerAid);
    debugPrint('[Chat] Invite result: $inviteResult');

    debugPrint('[Chat] Sending message to session=${widget.session.sessionId}, peer=${widget.session.peerAid}');
    final result = await AgentCPService.sendMessage(
      widget.session.sessionId,
      widget.session.peerAid,
      text,
    );

    if (result['success'] != true) {
      debugPrint('[Chat] Send failed: ${result['message']}');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Send failed: ${result['message']}')),
        );
      }
    }
  }

  Future<void> _executeCommand(String cmd) async {
    switch (cmd) {
      case '/new':
        await _handleNewSession();
      case '/session':
        await _handleSwitchSession();
    }
  }

  /// /new - Create a new session with the same peer and switch to it
  Future<void> _handleNewSession() async {
    final peerAid = widget.session.peerAid;
    if (peerAid.isEmpty) {
      _showSnack('No peer AID to create session with');
      return;
    }

    final result = await AgentCPService.createSession([peerAid]);
    if (result['success'] != true) {
      _showSnack('Failed to create session: ${result['message']}');
      return;
    }

    final newSessionId = result['sessionId'] as String;
    final newSession = SessionItem(sessionId: newSessionId, peerAid: peerAid);

    if (mounted) {
      // Pop current page and push new one via callback
      Navigator.pop(context, {'action': 'new_session', 'session': newSession});
    }
  }

  /// /session - Show a list of historical sessions with the same peer to switch to
  Future<void> _handleSwitchSession() async {
    final peerAid = widget.session.peerAid;
    if (peerAid.isEmpty) {
      _showSnack('No peer AID');
      return;
    }

    // Load all conversations from SDK
    final convResult = await AgentCPService.getAllConversations();
    if (convResult['success'] != true) {
      _showSnack('Failed to load conversations');
      return;
    }

    final conversations = convResult['conversations'] as List? ?? [];
    // Filter sessions with the same peer
    final peerSessions = <Map<String, dynamic>>[];
    for (final conv in conversations) {
      final map = Map<String, dynamic>.from(conv);
      final convPeer = map['peerAid'] as String? ?? '';
      if (convPeer == peerAid) {
        peerSessions.add(map);
      }
    }

    // Also check active sessions
    final activeResult = await AgentCPService.getActiveSessions();
    final activeSessions = <String>{};
    if (activeResult['success'] == true && activeResult['sessions'] != null) {
      activeSessions.addAll(List<String>.from(activeResult['sessions']));
    }

    if (peerSessions.isEmpty && activeSessions.isEmpty) {
      _showSnack('No historical sessions found');
      return;
    }

    // Add active sessions that might not be in conversation list yet
    final knownIds = peerSessions.map((s) => s['sessionId'] as String).toSet();
    for (final sid in activeSessions) {
      if (!knownIds.contains(sid)) {
        peerSessions.add({'sessionId': sid, 'peerAid': peerAid, 'isActive': true});
      }
    }

    if (!mounted) return;

    // Show bottom sheet with session list
    final selected = await showModalBottomSheet<Map<String, dynamic>>(
      context: context,
      builder: (ctx) {
        return SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Padding(
                padding: const EdgeInsets.all(16),
                child: Text('Sessions with $peerAid',
                    style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
              ),
              const Divider(height: 1),
              Flexible(
                child: ListView.builder(
                  shrinkWrap: true,
                  itemCount: peerSessions.length,
                  itemBuilder: (_, index) {
                    final s = peerSessions[index];
                    final sid = s['sessionId'] as String;
                    final isCurrent = sid == widget.session.sessionId;
                    final isActive = activeSessions.contains(sid);
                    final lastTime = s['lastMsgTime'] as int? ?? 0;
                    final preview = s['lastMsgPreview'] as String? ?? '';
                    final timeStr = lastTime > 0
                        ? DateTime.fromMillisecondsSinceEpoch(lastTime).toString().substring(0, 16)
                        : '';

                    return ListTile(
                      leading: Icon(
                        isActive ? Icons.circle : Icons.circle_outlined,
                        size: 12,
                        color: isActive ? Colors.green : Colors.grey,
                      ),
                      title: Row(
                        children: [
                          Expanded(
                            child: Text(
                              '${sid.substring(0, 8)}...',
                              style: TextStyle(
                                fontWeight: isCurrent ? FontWeight.bold : FontWeight.normal,
                                fontSize: 14,
                              ),
                            ),
                          ),
                          if (isCurrent)
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                              decoration: BoxDecoration(
                                color: Colors.blue[100],
                                borderRadius: BorderRadius.circular(8),
                              ),
                              child: const Text('current', style: TextStyle(fontSize: 10, color: Colors.blue)),
                            ),
                          if (isActive && !isCurrent)
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                              decoration: BoxDecoration(
                                color: Colors.green[100],
                                borderRadius: BorderRadius.circular(8),
                              ),
                              child: const Text('active', style: TextStyle(fontSize: 10, color: Colors.green)),
                            ),
                        ],
                      ),
                      subtitle: Text(
                        preview.isNotEmpty ? '$timeStr  $preview' : timeStr,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(fontSize: 12, color: Colors.grey[500]),
                      ),
                      onTap: isCurrent ? null : () => Navigator.pop(ctx, s),
                    );
                  },
                ),
              ),
            ],
          ),
        );
      },
    );

    if (selected != null && mounted) {
      final sid = selected['sessionId'] as String;
      final session = SessionItem(sessionId: sid, peerAid: peerAid);

      // Load messages for this session
      final msgResult = await AgentCPService.getMessages(sid, limit: 200);
      if (msgResult['success'] == true && msgResult['messages'] != null) {
        final messages = msgResult['messages'] as List;
        final msgs = <ChatMessage>[];
        for (final m in messages.reversed) {
          final msgMap = Map<String, dynamic>.from(m);
          final text = AgentCPService.parseBlocksJson(msgMap['blocksJson'] as String?);
          final direction = msgMap['direction'] as int? ?? 0;
          msgs.add(ChatMessage(
            messageId: msgMap['messageId'] as String? ?? '',
            sessionId: sid,
            sender: msgMap['sender'] as String? ?? '',
            timestamp: msgMap['timestamp'] as int? ?? 0,
            text: text,
            isMine: direction == 1,
          ));
        }
        session.addAllMessages(msgs);
      }

      Navigator.pop(context, {'action': 'switch_session', 'session': session});
    }
  }

  void _showSnack(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message), duration: const Duration(seconds: 2)),
    );
  }

  void _openAgentMdPage() {
    Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => AgentMdPage(aid: widget.session.peerAid)),
    );
  }

  @override
  Widget build(BuildContext context) {
    final displayName = (_peerAgentInfo?.name.isNotEmpty == true)
        ? _peerAgentInfo!.name
        : (widget.session.peerAid.isNotEmpty ? widget.session.peerAid : 'Chat');

    return Scaffold(
      appBar: AppBar(
        title: GestureDetector(
          onTap: _openAgentMdPage,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(displayName, style: const TextStyle(fontSize: 16)),
              Text(widget.session.sessionId.substring(0, 8) + '...', 
                  style: const TextStyle(fontSize: 10, color: Colors.black54)),
            ],
          ),
        ),
        backgroundColor: Theme.of(context).colorScheme.inversePrimary,
      ),
      body: Column(
        children: [
          Expanded(child: _buildChatArea()),
          _buildSlashCommandMenu(),
          _buildMessageInput(),
        ],
      ),
    );
  }

  Widget _buildChatArea() {
    final messages = widget.session.messages;
    
    if (messages.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            CircleAvatar(
              backgroundImage: AssetImage(
                AgentInfoService().getAvatarAssetPath(_peerAgentInfo?.type ?? ''),
              ),
              radius: 36,
            ),
            const SizedBox(height: 12),
            Text('Say hi to ${widget.session.peerAid}!',
                style: const TextStyle(color: Colors.grey)),
          ],
        ),
      );
    }
    
    return ListView.builder(
      controller: _scrollController,
      padding: const EdgeInsets.all(16),
      itemCount: messages.length,
      itemBuilder: (context, index) => _buildMessageBubble(messages[index]),
    );
  }

  Widget _buildMessageBubble(ChatMessage msg) {
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
                child: GestureDetector(
                  onTap: _openAgentMdPage,
                  child: CircleAvatar(
                    backgroundImage: AssetImage(avatarPath),
                    radius: 16,
                  ),
                ),
              ),
            Flexible(
              child: Column(
                crossAxisAlignment: isMine ? CrossAxisAlignment.end : CrossAxisAlignment.start,
                children: [
                  if (!isMine)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 2, left: 4),
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
                        BoxShadow(
                          color: Colors.black.withValues(alpha: 0.05),
                          blurRadius: 2,
                          offset: const Offset(0, 1),
                        )
                      ],
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(msg.text,
                            style: TextStyle(
                                color: isMine ? Colors.white : Colors.black87,
                                fontSize: 15)),
                        const SizedBox(height: 2),
                        Text(
                          DateTime.fromMillisecondsSinceEpoch(msg.timestamp).toString().substring(11, 16),
                          style: TextStyle(
                            fontSize: 10, 
                            color: isMine ? Colors.white70 : Colors.grey[400]
                          ),
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
                child: CircleAvatar(
                  backgroundImage: AssetImage(AgentInfoService().getAvatarAssetPath('human')), 
                  radius: 16,
                ),
              ),
          ],
        );
      },
    );
  }

  Widget _buildSlashCommandMenu() {
    if (!_showSlashMenu || _filteredCommands.isEmpty) return const SizedBox.shrink();

    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        border: Border(top: BorderSide(color: Colors.grey[200]!)),
        boxShadow: [
          BoxShadow(color: Colors.black.withValues(alpha: 0.06), blurRadius: 6, offset: const Offset(0, -2)),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: _filteredCommands.asMap().entries.map((entry) {
          final index = entry.key;
          final c = entry.value;
          final isSelected = index == _selectedCommandIndex;
          return InkWell(
            onTap: () {
              final cmd = c['cmd'] as String;
              _messageController.clear();
              setState(() {
                _showSlashMenu = false;
                _filteredCommands = [];
              });
              _executeCommand(cmd);
            },
            child: Container(
              color: isSelected ? Colors.deepPurple.withValues(alpha: 0.08) : null,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
              child: Row(
                children: [
                  Icon(c['icon'] as IconData, size: 20, color: Colors.deepPurple),
                  const SizedBox(width: 12),
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(c['cmd'] as String,
                          style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
                      Text(c['desc'] as String,
                          style: TextStyle(fontSize: 12, color: Colors.grey[500])),
                    ],
                  ),
                ],
              ),
            ),
          );
        }).toList(),
      ),
    );
  }

  Widget _buildMessageInput() {
    return SafeArea(
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
        decoration: BoxDecoration(
          color: Colors.white,
          boxShadow: [
            BoxShadow(color: Colors.grey.withValues(alpha: 0.2), blurRadius: 4,
                offset: const Offset(0, -1)),
          ],
        ),
        child: Row(
          children: [
            Expanded(
              child: TextField(
                controller: _messageController,
                decoration: const InputDecoration(
                  hintText: 'Type / for commands...',
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.all(Radius.circular(24)),
                  ),
                  contentPadding:
                      EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                ),
                textInputAction: TextInputAction.send,
                onSubmitted: (_) => _sendMessage(),
              ),
            ),
            const SizedBox(width: 8),
            IconButton(
              onPressed: _sendMessage,
              icon: const Icon(Icons.send),
              color: Colors.deepPurple,
            ),
          ],
        ),
      ),
    );
  }
}

// AgentMdPage goes here, identical to the one in chat_page.dart
class AgentMdPage extends StatefulWidget {
  final String aid;
  const AgentMdPage({super.key, required this.aid});

  @override
  State<AgentMdPage> createState() => _AgentMdPageState();
}

class _AgentMdPageState extends State<AgentMdPage> {
  String? _rawContent;
  Map<String, dynamic>? _frontmatter;
  String? _bodyMarkdown;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _fetchMd();
  }

  Future<void> _fetchMd() async {
    try {
      final url = Uri.parse('https://${widget.aid}/agent.md');
      final response = await http.get(url).timeout(const Duration(seconds: 10));
      if (response.statusCode == 200) {
        _parseMd(response.body);
      } else {
        setState(() {
          _error = 'HTTP ${response.statusCode}';
          _loading = false;
        });
      }
    } catch (e) {
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  void _parseMd(String content) {
    final match = RegExp(r'^---\s*\n([\s\S]*?)\n---', multiLine: true).firstMatch(content);
    if (match != null) {
      final yamlStr = match.group(1)!;
      _frontmatter = _parseYaml(yamlStr);
      _bodyMarkdown = content.substring(match.end).trim();
    } else {
      _frontmatter = null;
      _bodyMarkdown = content.trim();
    }
    setState(() {
      _rawContent = content;
      _loading = false;
    });
  }

  Map<String, dynamic> _parseYaml(String yaml) {
    final result = <String, dynamic>{};
    String? currentKey;
    List<String>? currentList;

    for (final line in yaml.split('\n')) {
      final listItemMatch = RegExp(r'^\s+-\s+(.*)$').firstMatch(line);
      if (listItemMatch != null && currentKey != null) {
        currentList ??= [];
        currentList.add(listItemMatch.group(1)!.trim());
        continue;
      }
      if (currentKey != null && currentList != null) {
        result[currentKey] = currentList;
        currentList = null;
        currentKey = null;
      }
      final kvMatch = RegExp(r'^(\w[\w\s]*):\s*(.*)$').firstMatch(line);
      if (kvMatch != null) {
        final key = kvMatch.group(1)!.trim();
        final value = kvMatch.group(2)!.trim();
        if (value.isEmpty) {
          currentKey = key;
          currentList = null;
        } else {
          final unquoted = value.startsWith('"') && value.endsWith('"')
              ? value.substring(1, value.length - 1)
              : value;
          result[key] = unquoted;
        }
      }
    }
    if (currentKey != null && currentList != null) {
      result[currentKey] = currentList;
    }
    return result;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.aid, style: const TextStyle(fontSize: 14)),
        backgroundColor: Theme.of(context).colorScheme.inversePrimary,
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.error_outline, size: 48, color: Colors.grey[400]),
            const SizedBox(height: 12),
            Text(_error!, style: TextStyle(color: Colors.grey[500])),
          ],
        ),
      );
    }
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (_frontmatter != null) _buildFrontmatterCard(),
          if (_bodyMarkdown != null && _bodyMarkdown!.isNotEmpty) ...[
            const SizedBox(height: 16),
            MarkdownBody(data: _bodyMarkdown!, selectable: true),
          ],
        ],
      ),
    );
  }

  Widget _buildFrontmatterCard() {
    final fm = _frontmatter!;
    final avatarPath = AgentInfoService().getAvatarAssetPath(fm['type'] ?? '');
    final name = fm['name'] ?? widget.aid;
    final desc = fm['description'] ?? '';
    final extraKeys = fm.keys.where((k) => !{'name', 'type', 'description'}.contains(k)).toList();

    return Card(
      elevation: 2,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                CircleAvatar(backgroundImage: AssetImage(avatarPath), radius: 28),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(name, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                      const SizedBox(height: 2),
                      Text(fm['type'] ?? '', style: TextStyle(fontSize: 12, color: Colors.grey[500])),
                    ],
                  ),
                ),
              ],
            ),
            if (desc.isNotEmpty) ...[
              const SizedBox(height: 12),
              Text(desc, style: const TextStyle(fontSize: 14)),
            ],
            if (extraKeys.isNotEmpty) ...[
              const Divider(height: 24),
              ...extraKeys.map((key) {
                final value = fm[key];
                if (value is List) {
                  return Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        SizedBox(
                          width: 80,
                          child: Text(key, style: TextStyle(fontSize: 13, color: Colors.grey[600], fontWeight: FontWeight.w500)),
                        ),
                        Expanded(
                          child: Wrap(
                            spacing: 6,
                            runSpacing: 4,
                            children: value.map<Widget>((t) => Chip(
                              label: Text(t.toString(), style: const TextStyle(fontSize: 12)),
                              materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                              visualDensity: VisualDensity.compact,
                            )).toList(),
                          ),
                        ),
                      ],
                    ),
                  );
                }
                return Padding(
                  padding: const EdgeInsets.only(bottom: 6),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      SizedBox(
                        width: 80,
                        child: Text(key, style: TextStyle(fontSize: 13, color: Colors.grey[600], fontWeight: FontWeight.w500)),
                      ),
                      Expanded(child: Text(value.toString(), style: const TextStyle(fontSize: 13))),
                    ],
                  ),
                );
              }),
            ],
          ],
        ),
      ),
    );
  }
}
