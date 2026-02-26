import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:url_launcher/url_launcher.dart';
import '../i18n/app_texts.dart';
import '../services/agentcp_service.dart';
import '../services/agent_info_service.dart';
import '../widgets/group_avatar_widget.dart';
import 'group_members_page.dart';
import 'chat_detail_page.dart';

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
  static const int _pageSize = 30;
  static const double _topRefreshTolerance = 8;

  final _messageController = TextEditingController();
  final _inputFocusNode = FocusNode();
  final _scrollController = ScrollController();

  List<GroupChatMessage> _messages = [];
  final List<GroupChatMessage> _optimisticMessages = [];
  int _currentFetchLimit = _pageSize;
  int _lastStoreMessageCount = 0;
  bool _hasMoreHistory = true;
  bool _isLoadingMoreHistory = false;
  bool _didInitialAutoScroll = false;
  double _lastKeyboardInset = 0;
  bool _isLoading = true;
  bool _isSending = false;
  Timer? _refreshTimer;

  int _memberCount = 0;
  String _visibility = '';
  String _ownerAid = '';
  String _groupAddress = '';

  String get _groupName => widget.group.groupName.isNotEmpty ? widget.group.groupName : widget.group.groupId;

  // Save original callbacks so we can restore them on dispose
  Function(String, String)? _prevOnGroupMessageBatch;
  Function(String, int, String, String)? _prevOnGroupNewMessage;

  @override
  void initState() {
    super.initState();
    _inputFocusNode.addListener(() {
      if (_inputFocusNode.hasFocus) {
        _scrollToBottom();
      }
    });
    _setupCallbacks();
    _init();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final inset = MediaQuery.viewInsetsOf(context).bottom;
    if (inset > _lastKeyboardInset && inset > 0) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _scrollToBottom();
      });
    }
    _lastKeyboardInset = inset;
  }

  void _setupCallbacks() {
    _prevOnGroupMessageBatch = AgentCPService.onGroupMessageBatch;
    _prevOnGroupNewMessage = AgentCPService.onGroupNewMessage;

    AgentCPService.onGroupMessageBatch = (groupId, batchJson) {
      _prevOnGroupMessageBatch?.call(groupId, batchJson);
      if (groupId == widget.group.groupId && mounted && !_isSending) {
        _scheduleRefresh();
      }
    };

    AgentCPService.onGroupNewMessage = (groupId, latestMsgId, sender, preview) {
      _prevOnGroupNewMessage?.call(groupId, latestMsgId, sender, preview);
      if (groupId == widget.group.groupId && mounted && !_isSending) {
        _scheduleRefresh();
      }
    };
  }

  @override
  void dispose() {
    // Restore original callbacks for ChatPage
    AgentCPService.onGroupMessageBatch = _prevOnGroupMessageBatch;
    AgentCPService.onGroupNewMessage = _prevOnGroupNewMessage;
    _refreshTimer?.cancel();
    _messageController.dispose();
    _inputFocusNode.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  Future<void> _init() async {
    if (widget.group.isActive) {
      await AgentCPService.joinGroupSession(widget.group.groupId);
      await AgentCPService.groupMarkRead(widget.group.groupId);
      await _loadGroupMeta();
    }
    await _loadMessages(scrollToBottom: false);
    await _autoScrollToLatestOnEnter();
  }

  Future<void> _loadGroupMeta() async {
    try {
      final infoResult = await AgentCPService.groupGetInfo(widget.group.groupId);
      if (infoResult['success'] == true && infoResult['data'] != null) {
        final info = _extractMap(infoResult['data']);
        final membersResult = await AgentCPService.groupGetMembers(widget.group.groupId);
        List<dynamic> members = [];
        if (membersResult['success'] == true && membersResult['data'] != null) {
          members = _extractList(membersResult['data'], listKeys: const ['members']);
        }
        if (mounted) {
          setState(() {
            _memberCount = members.length;
            _visibility = (info['visibility'] ?? '').toString();
            _ownerAid = (info['owner'] ?? info['owner_aid'] ?? info['ownerAid'] ?? info['created_by'] ?? '').toString();
            _groupAddress = (info['group_address'] ?? info['groupAddress'] ?? info['address'] ?? info['url'] ?? '').toString();
          });
        }
      }
    } catch (_) {}
  }

  Future<void> _autoScrollToLatestOnEnter() async {
    if (_didInitialAutoScroll || !mounted) return;
    _didInitialAutoScroll = true;

    // Retry a few times to ensure list layout is complete before jumping.
    for (int i = 0; i < 4; i++) {
      _scrollToBottom(animated: false);
      await Future.delayed(const Duration(milliseconds: 60));
      if (!mounted) return;
    }
  }

  void _scheduleRefresh({Duration delay = const Duration(milliseconds: 150)}) {
    _refreshTimer?.cancel();
    _refreshTimer = Timer(delay, () async {
      if (!mounted) return;
      await _loadMessages();
      await Future.delayed(const Duration(milliseconds: 800));
      if (!mounted) return;
      await _loadMessages();
      AgentCPService.groupMarkRead(widget.group.groupId);
    });
  }

  Future<void> _loadMessages({int? limit, bool scrollToBottom = true}) async {
    final fetchLimit = limit ?? _currentFetchLimit;
    final result = await AgentCPService.groupGetMessages(
      widget.group.groupId,
      limit: fetchLimit,
    );
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

      // If we have optimistic messages and the store returned fewer messages
      // than what we currently display, the store hasn't persisted yet.
      // Skip this refresh to avoid flicker — keep the in-memory state.
      if (_optimisticMessages.isNotEmpty &&
          fetchLimit == _currentFetchLimit &&
          messages.length < _messages.length) {
        return;
      }

      final mergedMessages = _mergeMessagesWithOptimistic(messages);

      if (mounted) {
        setState(() {
          _messages = mergedMessages;
          _currentFetchLimit = fetchLimit;
          _lastStoreMessageCount = messages.length;
          _isLoading = false;
          if (messages.length < fetchLimit) {
            _hasMoreHistory = false;
          }
        });
        if (scrollToBottom) {
          _scrollToBottom();
        }
      }
    }
  }

  Future<void> _loadMoreHistory() async {
    if (_isLoading || _isLoadingMoreHistory || !_hasMoreHistory) return;
    if (_isSending) return;
    if (_scrollController.hasClients) {
      final position = _scrollController.position;
      final isAtTop = position.pixels <= position.minScrollExtent + _topRefreshTolerance;
      if (!isAtTop) return;
    }

    _isLoadingMoreHistory = true;
    final beforeStoreCount = _lastStoreMessageCount;
    final beforePixels = _scrollController.hasClients ? _scrollController.position.pixels : 0.0;
    final beforeMaxScrollExtent =
        _scrollController.hasClients ? _scrollController.position.maxScrollExtent : 0.0;

    await _loadMessages(
      limit: _currentFetchLimit + _pageSize,
      scrollToBottom: false,
    );

    if (!mounted) {
      _isLoadingMoreHistory = false;
      return;
    }

    if (_scrollController.hasClients) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!_scrollController.hasClients) return;
        final position = _scrollController.position;
        final extentDelta = position.maxScrollExtent - beforeMaxScrollExtent;
        final target = (beforePixels + (extentDelta > 0 ? extentDelta : 0.0))
            .clamp(position.minScrollExtent, position.maxScrollExtent)
            .toDouble();
        position.jumpTo(target);
      });
    }

    final didLoadMore = _lastStoreMessageCount > beforeStoreCount;
    if (!didLoadMore && mounted) {
      setState(() {
        _hasMoreHistory = false;
      });
    }
    _isLoadingMoreHistory = false;
  }

  bool _isSameMessage(GroupChatMessage a, GroupChatMessage b) {
    if (a.msgId.isNotEmpty && b.msgId.isNotEmpty && a.msgId == b.msgId) {
      return true;
    }
    if (a.sender != b.sender || a.content != b.content) {
      return false;
    }
    return (a.timestamp - b.timestamp).abs() <= 15000;
  }

  List<GroupChatMessage> _mergeMessagesWithOptimistic(List<GroupChatMessage> storeMessages) {
    final merged = List<GroupChatMessage>.from(storeMessages);
    final unmatchedStore = List<GroupChatMessage>.from(storeMessages);
    final stillPending = <GroupChatMessage>[];
    final now = DateTime.now().millisecondsSinceEpoch;

    for (final pending in _optimisticMessages) {
      final matchedIdx = unmatchedStore.indexWhere((stored) => _isSameMessage(pending, stored));
      if (matchedIdx >= 0) {
        unmatchedStore.removeAt(matchedIdx);
        continue;
      }

      // Keep optimistic messages briefly to avoid flicker before store persistence.
      if (now - pending.timestamp <= 30000) {
        merged.add(pending);
        stillPending.add(pending);
      }
    }

    _optimisticMessages
      ..clear()
      ..addAll(stillPending);

    merged.sort((a, b) {
      final tsCmp = a.timestamp.compareTo(b.timestamp);
      if (tsCmp != 0) return tsCmp;
      return a.msgId.compareTo(b.msgId);
    });
    return merged;
  }

  void _scrollToBottom({bool animated = true}) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        if (animated) {
          _scrollController.animateTo(
            _scrollController.position.maxScrollExtent,
            duration: const Duration(milliseconds: 200),
            curve: Curves.easeOut,
          );
        } else {
          _scrollController.jumpTo(_scrollController.position.maxScrollExtent);
        }
      }
    });
  }

  void _dismissKeyboard() {
    FocusManager.instance.primaryFocus?.unfocus();
  }

  Future<void> _sendMessage() async {
    final text = _messageController.text.trim();
    if (text.isEmpty) return;
    _messageController.clear();

    final now = DateTime.now().millisecondsSinceEpoch;
    final msg = GroupChatMessage(
      msgId: 'local-$now',
      groupId: widget.group.groupId,
      sender: widget.currentAid,
      content: text,
      contentType: 'text',
      timestamp: now,
      isMine: true,
    );

    setState(() {
      _optimisticMessages.add(msg);
      _messages.add(msg);
    });
    _scrollToBottom();

    _isSending = true;
    final result = await AgentCPService.groupSendMessage(
      groupId: widget.group.groupId,
      content: text,
    );
    _isSending = false;

    if (result['success'] != true) {
      setState(() {
        _optimisticMessages.removeWhere((m) => m.msgId == msg.msgId);
        _messages.removeWhere((m) => m.msgId == msg.msgId);
      });
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(AppTexts.sendFailed(context, '${result['message']}'))),
        );
      }
    }

    // Delay refresh to avoid reading store before native layer persists new message.
    if (mounted) _scheduleRefresh(delay: const Duration(milliseconds: 500));
  }

  Future<void> _copyGroupLink() async {
    final isPrivate = _visibility == 'private';
    final isOwner = _ownerAid.isNotEmpty && _ownerAid == widget.currentAid;

    // Private group: only owner can copy
    if (isPrivate && !isOwner) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(AppTexts.onlyOwnerCanCopyLink(context)), duration: const Duration(seconds: 2)),
      );
      return;
    }

    // Build group link: https://group.{owner_ap}/{group_id}
    String groupLink;
    if (_groupAddress.isNotEmpty) {
      groupLink = _groupAddress;
    } else if (_ownerAid.isNotEmpty) {
      // Extract AP from owner AID (e.g., "alice.agentcp.io" -> "agentcp.io")
      final parts = _ownerAid.split('.');
      final ownerAp = parts.length >= 2 ? parts.sublist(1).join('.') : _ownerAid;
      groupLink = 'https://group.$ownerAp/${widget.group.groupId}';
    } else {
      groupLink = widget.group.groupId;
    }

    if (isPrivate) {
      // Owner of private group: choose with or without invite code
      final choice = await showDialog<String>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: Text(AppTexts.copyGroupLink(context)),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              ListTile(
                leading: const Icon(Icons.link),
                title: Text(AppTexts.copyWithoutInviteCode(context)),
                onTap: () => Navigator.pop(ctx, 'no_code'),
              ),
              ListTile(
                leading: const Icon(Icons.vpn_key),
                title: Text(AppTexts.copyWithInviteCode(context)),
                onTap: () => Navigator.pop(ctx, 'with_code'),
              ),
            ],
          ),
        ),
      );
      if (choice == null || !mounted) return;

      if (choice == 'with_code') {
        final codeResult = await AgentCPService.groupGenerateInviteCode(widget.group.groupId);
        final inviteCode = (codeResult['inviteCode'] ?? codeResult['invite_code'] ?? '').toString();
        final linkWithCode = inviteCode.isNotEmpty ? '$groupLink?invite_code=$inviteCode' : groupLink;
        final text = AppTexts.shareGroupMessage(context, widget.currentAid, _groupName, linkWithCode);
        await Clipboard.setData(ClipboardData(text: text));
      } else {
        final text = AppTexts.shareGroupMessage(context, widget.currentAid, _groupName, groupLink);
        await Clipboard.setData(ClipboardData(text: text));
      }
    } else {
      // Public group: copy directly without invite code
      final text = AppTexts.shareGroupMessage(context, widget.currentAid, _groupName, groupLink);
      await Clipboard.setData(ClipboardData(text: text));
    }

    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(AppTexts.groupLinkCopied(context)), duration: const Duration(seconds: 1)),
      );
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
              Text(AppTexts.groupMembersCount(context, members.length), style: const TextStyle(fontWeight: FontWeight.bold)),
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
        actions: [TextButton(onPressed: () => Navigator.pop(ctx), child: Text(AppTexts.close(context)))],
      ),
    );
  }

  Future<void> _openMembersPage() async {
    // Fetch latest member list from server
    final membersResult = await AgentCPService.groupGetMembers(widget.group.groupId);
    List<String> memberAids = [];

    if (membersResult['success'] == true && membersResult['data'] != null) {
      final members = _extractList(membersResult['data'], listKeys: const ['members']);
      for (final m in members) {
        final aid = m is Map
            ? (m['aid'] ?? m['agent_id'] ?? m['agentId'] ?? '').toString()
            : m.toString();
        if (aid.isNotEmpty) {
          memberAids.add(aid);
        }
      }
    }

    if (!mounted) return;

    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => GroupMembersPage(
          groupName: widget.group.groupName,
          memberAids: memberAids,
        ),
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
      resizeToAvoidBottomInset: true,
      appBar: AppBar(
        title: GestureDetector(
          onTap: _showGroupInfoDialog,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Flexible(
                    child: Text(
                      widget.group.groupName.isNotEmpty ? widget.group.groupName : 'Group Chat',
                      style: const TextStyle(fontSize: 16),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  if (_memberCount > 0)
                    Text(
                      ' ($_memberCount)',
                      style: const TextStyle(fontSize: 13, color: Colors.black54),
                    ),
                ],
              ),
              GestureDetector(
                onTap: () {
                  Clipboard.setData(ClipboardData(text: widget.group.groupId));
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(content: Text(AppTexts.groupIdCopied(context)), duration: const Duration(seconds: 1)),
                  );
                },
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Flexible(
                      child: Text(
                        widget.group.groupId,
                        style: const TextStyle(fontSize: 10, color: Colors.black54),
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    const SizedBox(width: 4),
                    const Icon(Icons.copy, size: 10, color: Colors.black54),
                  ],
                ),
              ),
            ],
          ),
        ),
        backgroundColor: Theme.of(context).colorScheme.inversePrimary,
        actions: [
          if (widget.group.isActive) ...[
            IconButton(
              icon: const Icon(Icons.link),
              onPressed: _copyGroupLink,
              tooltip: AppTexts.copyGroupLink(context),
            ),
            IconButton(
              icon: const Icon(Icons.refresh),
              onPressed: _loadMessages,
              tooltip: AppTexts.groupRefreshTooltip(context),
            ),
            IconButton(
              icon: const Icon(Icons.group),
              onPressed: _openMembersPage,
              tooltip: AppTexts.groupMembersTooltip(context),
            ),
          ],
        ],
      ),
      body: GestureDetector(
        onTap: _dismissKeyboard,
        behavior: HitTestBehavior.translucent,
        child: Column(
          children: [
            if (!widget.group.isActive)
              Container(
                width: double.infinity,
                padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 16),
                color: Colors.grey[200],
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(Icons.info_outline, size: 14, color: Colors.grey[600]),
                    const SizedBox(width: 6),
                    Text(
                      AppTexts.groupDisbanded(context),
                      style: TextStyle(fontSize: 13, color: Colors.grey[600]),
                    ),
                  ],
                ),
              ),
            Expanded(child: _buildChatArea()),
            if (widget.group.isActive) _buildMessageInput(),
          ],
        ),
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
            Text(AppTexts.groupNoMessages(context), style: const TextStyle(color: Colors.grey)),
          ],
        ),
      );
    }
    
    final listView = ListView.builder(
      controller: _scrollController,
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.all(16),
      itemCount: _messages.length,
      itemBuilder: (context, index) => _buildMessageBubble(_messages[index]),
    );

    if (!_hasMoreHistory) {
      return listView;
    }

    return RefreshIndicator(
      onRefresh: _loadMoreHistory,
      child: listView,
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
                child: GestureDetector(
                  onTap: () {
                    Navigator.push(
                      context,
                      MaterialPageRoute(builder: (_) => AgentMdPage(aid: msg.sender)),
                    );
                  },
                  child: CircleAvatar(backgroundImage: AssetImage(avatarPath), radius: 16),
                ),
              ),
            Flexible(
              child: Column(
                crossAxisAlignment: isMine ? CrossAxisAlignment.end : CrossAxisAlignment.start,
                children: [
                  GestureDetector(
                    onTap: !isMine ? () {
                      Navigator.push(
                        context,
                        MaterialPageRoute(builder: (_) => AgentMdPage(aid: msg.sender)),
                      );
                    } : null,
                    child: Padding(
                      padding: const EdgeInsets.only(bottom: 2, left: 4, right: 4),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          if (!isMine)
                            Text(displayName,
                                style: TextStyle(fontSize: 11, color: Colors.grey[600], fontWeight: FontWeight.bold)),
                          if (!isMine)
                            const SizedBox(width: 6),
                          Text(
                            DateTime.fromMillisecondsSinceEpoch(msg.timestamp).toString().substring(11, 16),
                            style: TextStyle(fontSize: 10, color: Colors.grey[400]),
                          ),
                        ],
                      ),
                    ),
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
                    child: MarkdownBody(
                      data: msg.content,
                      onTapLink: (text, href, title) {
                        if (href != null) {
                          launchUrl(Uri.parse(href), mode: LaunchMode.externalApplication);
                        }
                      },
                      styleSheet: MarkdownStyleSheet(
                        p: TextStyle(color: isMine ? Colors.white : Colors.black87, fontSize: 15),
                        a: TextStyle(
                          color: isMine ? Colors.lightBlueAccent : Colors.blue,
                          decoration: TextDecoration.underline,
                        ),
                        code: TextStyle(
                          backgroundColor: isMine ? Colors.white.withValues(alpha: 0.2) : Colors.grey[200],
                          color: isMine ? Colors.white : Colors.black87,
                        ),
                        codeblockDecoration: BoxDecoration(
                          color: isMine ? Colors.white.withValues(alpha: 0.1) : Colors.grey[100],
                          borderRadius: BorderRadius.circular(4),
                        ),
                      ),
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
      top: false,
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
                focusNode: _inputFocusNode,
                controller: _messageController,
                decoration: InputDecoration(
                  hintText: AppTexts.groupInputHint(context),
                  border: const OutlineInputBorder(borderRadius: BorderRadius.all(Radius.circular(24))),
                  contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                ),
                onTapOutside: (_) => _dismissKeyboard(),
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
