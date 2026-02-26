import 'dart:convert';
import 'dart:io';
import 'package:path_provider/path_provider.dart';
import 'package:path/path.dart' as path;
import 'agentcp_service.dart';

class MessageStore {
  static final MessageStore _instance = MessageStore._internal();
  factory MessageStore() => _instance;
  MessageStore._internal();

  String? _basePath;

  Future<void> init() async {
    if (_basePath != null) return;
    final dir = await getApplicationDocumentsDirectory();
    _basePath = dir.path;
  }

  String _getSessionsDir(String aid) {
    return path.join(_basePath!, 'AIDs', aid, 'sessions');
  }

  String _getIndexPath(String aid) {
    return path.join(_getSessionsDir(aid), '_index.json');
  }

  String _getSessionFilePath(String aid, String sessionId) {
    return path.join(_getSessionsDir(aid), '$sessionId.jsonl');
  }

  Future<void> _ensureDir(String dirPath) async {
    final dir = Directory(dirPath);
    if (!await dir.exists()) {
      await dir.create(recursive: true);
    }
  }

  Future<void> saveMessage(String ownerAid, ChatMessage msg) async {
    await saveMessageWithPeer(ownerAid, msg);
  }

  Future<void> saveMessageWithPeer(String ownerAid, ChatMessage msg, {String? peerAid}) async {
    if (_basePath == null) await init();

    // Update Index
    final indexFile = File(_getIndexPath(ownerAid));
    List<Map<String, dynamic>> sessions = [];
    if (await indexFile.exists()) {
      try {
        final content = await indexFile.readAsString();
        sessions = List<Map<String, dynamic>>.from(jsonDecode(content));
      } catch (e) {
        // Error reading index
      }
    } else {
        await _ensureDir(_getSessionsDir(ownerAid));
    }

    final sessionId = msg.sessionId;
    final timestamp = msg.timestamp;
    final incomingPeerAid = _normalizePeerAid(peerAid);

    int index = sessions.indexWhere((s) => s['sessionId'] == sessionId);
    if (index != -1) {
      sessions[index]['lastMessageAt'] = timestamp;
      sessions[index]['messageCount'] = (sessions[index]['messageCount'] ?? 0) + 1;
      final currentPeerAid = _normalizePeerAid(sessions[index]['peerAid']?.toString());
      if (currentPeerAid.isEmpty) {
        if (incomingPeerAid.isNotEmpty) {
          sessions[index]['peerAid'] = incomingPeerAid;
        } else if (msg.sender != ownerAid) {
          sessions[index]['peerAid'] = msg.sender;
        }
      }
      // Initialize unreadCount if not present
      if (!sessions[index].containsKey('unreadCount')) {
        sessions[index]['unreadCount'] = 0;
      }
    } else {
      final resolvedPeerAid = incomingPeerAid.isNotEmpty
          ? incomingPeerAid
          : (msg.sender == ownerAid ? '' : msg.sender);
      if (resolvedPeerAid.isEmpty) {
        return;
      }
      sessions.add({
        'sessionId': sessionId,
        'peerAid': resolvedPeerAid,
        'ownerAid': ownerAid,
        'type': msg.isMine ? 'outgoing' : 'incoming',
        'createdAt': timestamp,
        'lastMessageAt': timestamp,
        'messageCount': 1,
        'unreadCount': 0,
        'closed': false,
      });
    }

    await indexFile.writeAsString(jsonEncode(sessions));

    // Append message to JSONL
    final msgFile = File(_getSessionFilePath(ownerAid, sessionId));
    final msgMap = {
        'type': msg.isMine ? 'sent' : 'received',
        'content': msg.text,
        'from': msg.sender,
        'timestamp': msg.timestamp,
        'messageId': msg.messageId,
    };
    await msgFile.writeAsString(jsonEncode(msgMap) + '\n', mode: FileMode.append);
  }

  Future<List<SessionItem>> loadSessions(String ownerAid) async {
    if (_basePath == null) await init();
    final indexFile = File(_getIndexPath(ownerAid));
    if (!await indexFile.exists()) return [];

    try {
        final content = await indexFile.readAsString();
        final List<dynamic> jsonSessions = jsonDecode(content);
        final sessions = <SessionItem>[];

        // Sort by lastMessageAt descending
        jsonSessions.sort((a, b) => (b['lastMessageAt'] ?? 0).compareTo(a['lastMessageAt'] ?? 0));

        for (var s in jsonSessions) {
            final sessionId = s['sessionId'];
            final peerAid = _normalizePeerAid(s['peerAid']?.toString());
            final unreadCount = s['unreadCount'] as int? ?? 0;
            final sessionItem = SessionItem(sessionId: sessionId, peerAid: peerAid, unreadCount: unreadCount);
            
            // Load messages
            final msgFile = File(_getSessionFilePath(ownerAid, sessionId));
            if (await msgFile.exists()) {
              try {
                final bytes = await msgFile.readAsBytes();
                final content = utf8.decode(bytes, allowMalformed: true);
                final lines = content.split('\n');
                for (var line in lines) {
                    if (line.trim().isEmpty) continue;
                    try {
                        final m = jsonDecode(line);
                        sessionItem.messages.add(ChatMessage(
                            messageId: m['messageId'] ?? '',
                            sessionId: sessionId,
                            sender: m['from'] ?? '',
                            timestamp: m['timestamp'] ?? 0,
                            text: m['content'] ?? '',
                            isMine: m['type'] == 'sent',
                        ));
                    } catch (e) {
                        // Error parsing message line
                    }
                }
              } catch (e) {
                // Error reading session file
              }
            }
            sessions.add(sessionItem);
        }
        return sessions;
    } catch (e) {
        return [];
    }
  }

  Future<void> deleteSession(String ownerAid, String sessionId) async {
    if (_basePath == null) await init();
    
    // Remove from index
    final indexFile = File(_getIndexPath(ownerAid));
    if (await indexFile.exists()) {
      try {
        final content = await indexFile.readAsString();
        List<dynamic> sessions = jsonDecode(content);
        sessions.removeWhere((s) => s['sessionId'] == sessionId);
        await indexFile.writeAsString(jsonEncode(sessions));
      } catch (e) {
        // Error deleting session from index
      }
    }

    // Delete message file
    final msgFile = File(_getSessionFilePath(ownerAid, sessionId));
    if (await msgFile.exists()) {
      await msgFile.delete();
    }
  }

  Future<void> updateSessionPeerAid(String ownerAid, String sessionId, String peerAid) async {
    if (_basePath == null) await init();

    final normalizedPeerAid = _normalizePeerAid(peerAid);
    if (normalizedPeerAid.isEmpty) return;

    final indexFile = File(_getIndexPath(ownerAid));
    if (!await indexFile.exists()) return;

    try {
      final content = await indexFile.readAsString();
      final sessions = List<Map<String, dynamic>>.from(jsonDecode(content));
      final index = sessions.indexWhere((s) => s['sessionId'] == sessionId);
      if (index == -1) return;

      final currentPeerAid = _normalizePeerAid(sessions[index]['peerAid']?.toString());
      if (currentPeerAid == normalizedPeerAid) return;

      sessions[index]['peerAid'] = normalizedPeerAid;
      await indexFile.writeAsString(jsonEncode(sessions));
    } catch (e) {
      // Error updating peerAid
    }
  }

  String _normalizePeerAid(String? value) {
    final trimmed = (value ?? '').trim();
    if (trimmed.isEmpty) return '';
    return trimmed;
  }

  /// Increment unread count for a P2P session by 1.
  Future<void> incrementUnread(String ownerAid, String sessionId) async {
    if (_basePath == null) await init();
    await _ensureDir(_getSessionsDir(ownerAid));
    final indexFile = File(_getIndexPath(ownerAid));
    try {
      List<Map<String, dynamic>> sessions = [];
      if (await indexFile.exists()) {
        final content = await indexFile.readAsString();
        sessions = List<Map<String, dynamic>>.from(jsonDecode(content));
      }
      final idx = sessions.indexWhere((s) => s['sessionId'] == sessionId);
      if (idx == -1) {
        final now = DateTime.now().millisecondsSinceEpoch;
        sessions.add({
          'sessionId': sessionId,
          'peerAid': '',
          'ownerAid': ownerAid,
          'type': 'incoming',
          'createdAt': now,
          'lastMessageAt': now,
          'messageCount': 0,
          'unreadCount': 1,
          'closed': false,
        });
      } else {
        sessions[idx]['unreadCount'] = (sessions[idx]['unreadCount'] as int? ?? 0) + 1;
      }
      await indexFile.writeAsString(jsonEncode(sessions));
    } catch (_) {}
  }

  /// Mark all messages in a P2P session as read (reset unread count to 0).
  Future<void> markSessionRead(String ownerAid, String sessionId) async {
    if (_basePath == null) await init();
    final indexFile = File(_getIndexPath(ownerAid));
    if (!await indexFile.exists()) return;
    try {
      final content = await indexFile.readAsString();
      final sessions = List<Map<String, dynamic>>.from(jsonDecode(content));
      final idx = sessions.indexWhere((s) => s['sessionId'] == sessionId);
      if (idx == -1) return;
      if ((sessions[idx]['unreadCount'] as int? ?? 0) == 0) return;
      sessions[idx]['unreadCount'] = 0;
      await indexFile.writeAsString(jsonEncode(sessions));
    } catch (_) {}
  }

  // ── Group list cache ──

  String _getGroupsPath(String aid) {
    return path.join(_basePath!, 'AIDs', aid, 'sessions', '_groups.json');
  }

  Future<void> saveGroupList(String ownerAid, List<Map<String, dynamic>> groups) async {
    if (_basePath == null) await init();
    await _ensureDir(_getSessionsDir(ownerAid));
    final file = File(_getGroupsPath(ownerAid));
    await file.writeAsString(jsonEncode(groups));
  }

  Future<List<Map<String, dynamic>>> loadGroupList(String ownerAid) async {
    if (_basePath == null) await init();
    final file = File(_getGroupsPath(ownerAid));
    if (!await file.exists()) return [];
    try {
      final content = await file.readAsString();
      return List<Map<String, dynamic>>.from(jsonDecode(content));
    } catch (e) {
      return [];
    }
  }

  Future<void> upsertGroup(String ownerAid, Map<String, dynamic> group) async {
    final groups = await loadGroupList(ownerAid);
    final groupId = group['groupId'] ?? '';
    if (groupId.isEmpty) return;
    final idx = groups.indexWhere((g) => g['groupId'] == groupId);
    if (idx >= 0) {
      groups[idx] = {...groups[idx], ...group};
    } else {
      groups.add(group);
    }
    await saveGroupList(ownerAid, groups);
  }

  Future<void> removeGroup(String ownerAid, String groupId) async {
    final groups = await loadGroupList(ownerAid);
    groups.removeWhere((g) => g['groupId'] == groupId);
    await saveGroupList(ownerAid, groups);
  }
}
