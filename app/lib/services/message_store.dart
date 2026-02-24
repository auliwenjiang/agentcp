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
        print('[MessageStore] Error reading index: $e');
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
    } else {
      final resolvedPeerAid = incomingPeerAid.isNotEmpty
          ? incomingPeerAid
          : (msg.sender == ownerAid ? '' : msg.sender);
      if (resolvedPeerAid.isEmpty) {
        print('[MessageStore] Abort: cannot create session without valid peerAid (sessionId=$sessionId)');
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
            final sessionItem = SessionItem(sessionId: sessionId, peerAid: peerAid);
            
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
                        print('[MessageStore] Error parsing message line: $e');
                    }
                }
              } catch (e) {
                print('[MessageStore] Error reading session file $sessionId: $e');
              }
            }
            sessions.add(sessionItem);
        }
        return sessions;
    } catch (e) {
        print('[MessageStore] Error loading sessions: $e');
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
        print('[MessageStore] Error deleting session from index: $e');
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
      print('[MessageStore] Error updating peerAid: $e');
    }
  }

  String _normalizePeerAid(String? value) {
    final trimmed = (value ?? '').trim();
    if (trimmed.isEmpty) return '';
    return trimmed;
  }
}
