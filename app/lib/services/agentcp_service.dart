import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

class ChatMessage {
  final String messageId;
  final String sessionId;
  final String sender;
  final int timestamp;
  final String text;
  final bool isMine;

  ChatMessage({
    required this.messageId,
    required this.sessionId,
    required this.sender,
    required this.timestamp,
    required this.text,
    required this.isMine,
  });
}

class SessionItem extends ChangeNotifier {
  final String sessionId;
  String peerAid;
  final List<ChatMessage> _messages = [];

  List<ChatMessage> get messages => _messages;

  SessionItem({required this.sessionId, required this.peerAid});

  void addMessage(ChatMessage msg) {
    _messages.add(msg);
    notifyListeners();
  }

  void addAllMessages(List<ChatMessage> msgs) {
    _messages.addAll(msgs);
    notifyListeners();
  }
}

class GroupChatMessage {
  final String msgId;
  final String groupId;
  final String sender;
  final String content;
  final String contentType;
  final int timestamp;
  final bool isMine;

  GroupChatMessage({
    required this.msgId,
    required this.groupId,
    required this.sender,
    required this.content,
    required this.contentType,
    required this.timestamp,
    required this.isMine,
  });
}

class GroupItem {
  final String groupId;
  final String groupName;
  final int lastMsgTime;
  final int unreadCount;
  final String lastMsgPreview;
  final List<String> memberAids;

  GroupItem({
    required this.groupId,
    required this.groupName,
    required this.lastMsgTime,
    required this.unreadCount,
    this.lastMsgPreview = '',
    this.memberAids = const [],
  });
}

/// AgentCP SDK 服务类
///
/// 提供 AgentCP SDK 的 Flutter 接口，封装与原生平台的通信
class AgentCPService {
  static const MethodChannel _channel =
      MethodChannel('com.agent.acp/agentcp');

  // Callback holders for native → Dart events
  static Function(ChatMessage)? onMessageReceived;
  static Function(String sessionId, String inviterId)? onInviteReceived;
  static Function(int oldState, int newState)? onStateChanged;

  // Group callback holders
  static Function(String groupId, String batchJson)? onGroupMessageBatch;
  static Function(String groupId, int latestMsgId, String sender, String preview)? onGroupNewMessage;
  static Function(String groupId, int latestEventId, String eventType, String summary)? onGroupNewEvent;
  static Function(String groupId, String groupAddress, String invitedBy)? onGroupInvite;
  static Function(String groupId, String groupAddress)? onGroupJoinApproved;
  static Function(String groupId, String reason)? onGroupJoinRejected;
  static Function(String groupId, String agentId, String message)? onGroupJoinRequestReceived;
  static Function(String groupId, String eventJson)? onGroupEvent;

  /// Initialize the reverse MethodCallHandler for native → Dart callbacks.
  /// Must be called before runApp.
  static void initCallbackHandler() {
    _channel.setMethodCallHandler((call) async {
      switch (call.method) {
        case 'onMessage':
          final args = Map<String, dynamic>.from(call.arguments);
          String text = '';
          try {
            final blocks = jsonDecode(args['blocksJson'] ?? '[]') as List;
            if (blocks.isNotEmpty) {
              text = blocks.first['text'] ?? '';
            }
          } catch (_) {
            text = args['blocksJson'] ?? '';
          }
          final msg = ChatMessage(
            messageId: args['messageId'] ?? '',
            sessionId: args['sessionId'] ?? '',
            sender: args['sender'] ?? '',
            timestamp: args['timestamp'] ?? 0,
            text: text,
            isMine: false,
          );
          debugPrint('[ACP] onMessage: session=${msg.sessionId}, sender=${msg.sender}, text=${msg.text}');
          onMessageReceived?.call(msg);
          break;
        case 'onInvite':
          final args = Map<String, dynamic>.from(call.arguments);
          final sessionId = args['sessionId'] ?? '';
          final inviterId = args['inviterId'] ?? '';
          debugPrint('[ACP] onInvite: session=$sessionId, inviter=$inviterId');
          onInviteReceived?.call(sessionId, inviterId);
          break;
        case 'onStateChange':
          final args = Map<String, dynamic>.from(call.arguments);
          final oldState = args['oldState'] ?? 0;
          final newState = args['newState'] ?? 0;
          debugPrint('[ACP] onStateChange: $oldState -> $newState');
          onStateChanged?.call(oldState, newState);
          break;
        case 'onGroupMessageBatch':
          final args = Map<String, dynamic>.from(call.arguments);
          final groupId = args['groupId'] ?? '';
          final batchJson = args['batchJson'] ?? '';
          debugPrint('[ACP] onGroupMessageBatch: group=$groupId');
          onGroupMessageBatch?.call(groupId, batchJson);
          break;
        case 'onGroupNewMessage':
          final args = Map<String, dynamic>.from(call.arguments);
          debugPrint('[ACP] onGroupNewMessage: group=${args['groupId']}, sender=${args['sender']}');
          onGroupNewMessage?.call(
            args['groupId'] ?? '',
            args['latestMsgId'] ?? 0,
            args['sender'] ?? '',
            args['preview'] ?? '',
          );
          break;
        case 'onGroupNewEvent':
          final args = Map<String, dynamic>.from(call.arguments);
          debugPrint('[ACP] onGroupNewEvent: group=${args['groupId']}, type=${args['eventType']}');
          onGroupNewEvent?.call(
            args['groupId'] ?? '',
            args['latestEventId'] ?? 0,
            args['eventType'] ?? '',
            args['summary'] ?? '',
          );
          break;
        case 'onGroupInvite':
          final args = Map<String, dynamic>.from(call.arguments);
          debugPrint('[ACP] onGroupInvite: group=${args['groupId']}, invitedBy=${args['invitedBy']}');
          onGroupInvite?.call(
            args['groupId'] ?? '',
            args['groupAddress'] ?? '',
            args['invitedBy'] ?? '',
          );
          break;
        case 'onGroupJoinApproved':
          final args = Map<String, dynamic>.from(call.arguments);
          debugPrint('[ACP] onGroupJoinApproved: group=${args['groupId']}');
          onGroupJoinApproved?.call(args['groupId'] ?? '', args['groupAddress'] ?? '');
          break;
        case 'onGroupJoinRejected':
          final args = Map<String, dynamic>.from(call.arguments);
          debugPrint('[ACP] onGroupJoinRejected: group=${args['groupId']}, reason=${args['reason']}');
          onGroupJoinRejected?.call(args['groupId'] ?? '', args['reason'] ?? '');
          break;
        case 'onGroupJoinRequestReceived':
          final args = Map<String, dynamic>.from(call.arguments);
          debugPrint('[ACP] onGroupJoinRequestReceived: group=${args['groupId']}, agent=${args['agentId']}');
          onGroupJoinRequestReceived?.call(
            args['groupId'] ?? '',
            args['agentId'] ?? '',
            args['message'] ?? '',
          );
          break;
        case 'onGroupEvent':
          final args = Map<String, dynamic>.from(call.arguments);
          debugPrint('[ACP] onGroupEvent: group=${args['groupId']}');
          onGroupEvent?.call(args['groupId'] ?? '', args['eventJson'] ?? '');
          break;
      }
    });
  }

  /// 初始化 SDK
  ///
  /// 必须在使用其他方法之前调用
  static Future<Map<String, dynamic>> initialize() async {
    try {
      final result = await _channel.invokeMethod('initialize');
      return Map<String, dynamic>.from(result);
    } on PlatformException catch (e) {
      return {
        'success': false,
        'error': e.code,
        'message': e.message ?? 'Unknown error',
      };
    }
  }

  /// 设置服务器地址
  ///
  /// [caBaseUrl] CA 服务器地址
  /// [apBaseUrl] AP 服务器地址
  static Future<Map<String, dynamic>> setBaseUrls({
    required String caBaseUrl,
    required String apBaseUrl,
  }) async {
    try {
      final result = await _channel.invokeMethod('setBaseUrls', {
        'caBaseUrl': caBaseUrl,
        'apBaseUrl': apBaseUrl,
      });
      return Map<String, dynamic>.from(result);
    } on PlatformException catch (e) {
      return {
        'success': false,
        'error': e.code,
        'message': e.message ?? 'Unknown error',
      };
    }
  }

  /// 设置存储路径
  ///
  /// [path] 本地存储路径，如果不指定则使用默认路径
  static Future<Map<String, dynamic>> setStoragePath({String? path}) async {
    try {
      final result = await _channel.invokeMethod('setStoragePath', {
        'path': path,
      });
      return Map<String, dynamic>.from(result);
    } on PlatformException catch (e) {
      return {
        'success': false,
        'error': e.code,
        'message': e.message ?? 'Unknown error',
      };
    }
  }

  /// 设置日志级别
  ///
  /// [level] 日志级别: error, warn, info, debug, trace
  static Future<Map<String, dynamic>> setLogLevel(String level) async {
    try {
      final result = await _channel.invokeMethod('setLogLevel', {
        'level': level,
      });
      return Map<String, dynamic>.from(result);
    } on PlatformException catch (e) {
      return {
        'success': false,
        'error': e.code,
        'message': e.message ?? 'Unknown error',
      };
    }
  }

  /// 创建新的 Agent ID
  ///
  /// [aid] Agent ID 字符串，格式为 name.ap（如 alice.aid.pub）
  /// [password] 可选的本地密钥保护密码，为空则使用默认保护
  static Future<Map<String, dynamic>> createAID({
    required String aid,
    String password = '',
  }) async {
    try {
      final result = await _channel.invokeMethod('createAID', {
        'aid': aid,
        'password': password,
      });
      return Map<String, dynamic>.from(result);
    } on PlatformException catch (e) {
      return {
        'success': false,
        'error': e.code,
        'message': e.message ?? 'Unknown error',
      };
    }
  }

  /// 加载已有的 Agent ID
  ///
  /// [aid] Agent ID 字符串
  /// [password] 可选的本地密钥保护密码
  static Future<Map<String, dynamic>> loadAID(String aid, {String password = ''}) async {
    try {
      final result = await _channel.invokeMethod('loadAID', {
        'aid': aid,
        'password': password,
      });
      return Map<String, dynamic>.from(result);
    } on PlatformException catch (e) {
      return {
        'success': false,
        'error': e.code,
        'message': e.message ?? 'Unknown error',
      };
    }
  }

  /// 删除 Agent ID
  ///
  /// [aid] Agent ID 字符串
  static Future<Map<String, dynamic>> deleteAID(String aid) async {
    try {
      final result = await _channel.invokeMethod('deleteAID', {
        'aid': aid,
      });
      return Map<String, dynamic>.from(result);
    } on PlatformException catch (e) {
      return {
        'success': false,
        'error': e.code,
        'message': e.message ?? 'Unknown error',
      };
    }
  }

  /// 列出所有 Agent ID
  static Future<Map<String, dynamic>> listAIDs() async {
    try {
      final result = await _channel.invokeMethod('listAIDs');
      return Map<String, dynamic>.from(result);
    } on PlatformException catch (e) {
      return {
        'success': false,
        'error': e.code,
        'message': e.message ?? 'Unknown error',
      };
    }
  }

  /// 上线
  static Future<Map<String, dynamic>> online() async {
    try {
      final result = await _channel.invokeMethod('online');
      return Map<String, dynamic>.from(result);
    } on PlatformException catch (e) {
      return {
        'success': false,
        'error': e.code,
        'message': e.message ?? 'Unknown error',
      };
    }
  }

  /// 下线
  static Future<Map<String, dynamic>> offline() async {
    try {
      final result = await _channel.invokeMethod('offline');
      return Map<String, dynamic>.from(result);
    } on PlatformException catch (e) {
      return {
        'success': false,
        'error': e.code,
        'message': e.message ?? 'Unknown error',
      };
    }
  }

  /// 检查是否在线
  static Future<bool> isOnline() async {
    try {
      final result = await _channel.invokeMethod('isOnline');
      final data = Map<String, dynamic>.from(result);
      return data['isOnline'] ?? false;
    } on PlatformException catch (e) {
      return false;
    }
  }

  /// 获取当前状态
  ///
  /// 返回状态: Offline, Connecting, Authenticating, Online, Reconnecting, Error
  static Future<String> getState() async {
    try {
      final result = await _channel.invokeMethod('getState');
      final data = Map<String, dynamic>.from(result);
      return data['state'] ?? 'Offline';
    } on PlatformException catch (e) {
      return 'Error';
    }
  }

  /// 获取当前 AID
  static Future<String?> getCurrentAID() async {
    try {
      final result = await _channel.invokeMethod('getCurrentAID');
      final data = Map<String, dynamic>.from(result);
      return data['aid'];
    } on PlatformException catch (e) {
      return null;
    }
  }

  /// 获取 SDK 版本
  static Future<String> getVersion() async {
    try {
      final result = await _channel.invokeMethod('getVersion');
      final data = Map<String, dynamic>.from(result);
      return data['version'] ?? 'Unknown';
    } on PlatformException catch (e) {
      return 'Unknown';
    }
  }

  /// 获取当前 Agent 的签名
  static Future<String?> getSignature() async {
    try {
      final result = await _channel.invokeMethod('getSignature');
      final data = Map<String, dynamic>.from(result);
      return data['signature'];
    } on PlatformException catch (e) {
      return null;
    }
  }

  /// 关闭 SDK
  static Future<Map<String, dynamic>> shutdown() async {
    try {
      final result = await _channel.invokeMethod('shutdown');
      return Map<String, dynamic>.from(result);
    } on PlatformException catch (e) {
      return {
        'success': false,
        'error': e.code,
        'message': e.message ?? 'Unknown error',
      };
    }
  }

  /// Register native callbacks (message, invite, state change)
  static Future<Map<String, dynamic>> setHandlers() async {
    try {
      final result = await _channel.invokeMethod('setHandlers');
      return Map<String, dynamic>.from(result);
    } on PlatformException catch (e) {
      return {
        'success': false,
        'error': e.code,
        'message': e.message ?? 'Unknown error',
      };
    }
  }

  /// Create a new session with given members
  static Future<Map<String, dynamic>> createSession(List<String> members) async {
    try {
      final result = await _channel.invokeMethod('createSession', {
        'members': members,
      });
      return Map<String, dynamic>.from(result);
    } on PlatformException catch (e) {
      return {
        'success': false,
        'error': e.code,
        'message': e.message ?? 'Unknown error',
      };
    }
  }

  /// Invite an agent to a session
  static Future<Map<String, dynamic>> inviteAgent(String sessionId, String agentId) async {
    try {
      final result = await _channel.invokeMethod('inviteAgent', {
        'sessionId': sessionId,
        'agentId': agentId,
      });
      return Map<String, dynamic>.from(result);
    } on PlatformException catch (e) {
      return {
        'success': false,
        'error': e.code,
        'message': e.message ?? 'Unknown error',
      };
    }
  }

  /// Join a session
  static Future<Map<String, dynamic>> joinSession(String sessionId) async {
    try {
      final result = await _channel.invokeMethod('joinSession', {
        'sessionId': sessionId,
      });
      return Map<String, dynamic>.from(result);
    } on PlatformException catch (e) {
      return {
        'success': false,
        'error': e.code,
        'message': e.message ?? 'Unknown error',
      };
    }
  }

  /// Get active session IDs
  static Future<Map<String, dynamic>> getActiveSessions() async {
    try {
      final result = await _channel.invokeMethod('getActiveSessions');
      return Map<String, dynamic>.from(result);
    } on PlatformException catch (e) {
      return {
        'success': false,
        'error': e.code,
        'message': e.message ?? 'Unknown error',
      };
    }
  }

  /// Get session info as JSON string
  static Future<Map<String, dynamic>> getSessionInfo(String sessionId) async {
    try {
      final result = await _channel.invokeMethod('getSessionInfo', {
        'sessionId': sessionId,
      });
      return Map<String, dynamic>.from(result);
    } on PlatformException catch (e) {
      return {
        'success': false,
        'error': e.code,
        'message': e.message ?? 'Unknown error',
      };
    }
  }

  /// Send a text message to a session
  static Future<Map<String, dynamic>> sendMessage(String sessionId, String peerAid, String text) async {
    try {
      final blocksJson = jsonEncode([
        {'type': 'content', 'text': text}
      ]);
      final result = await _channel.invokeMethod('sendMessage', {
        'sessionId': sessionId,
        'peerAid': peerAid,
        'blocksJson': blocksJson,
      });
      return Map<String, dynamic>.from(result);
    } on PlatformException catch (e) {
      return {
        'success': false,
        'error': e.code,
        'message': e.message ?? 'Unknown error',
      };
    }
  }

  // ===== SDK MessageStore methods =====

  /// 启用 SDK 消息持久化
  static Future<Map<String, dynamic>> enableMessageStore() async {
    try {
      final result = await _channel.invokeMethod('enableMessageStore');
      return Map<String, dynamic>.from(result);
    } on PlatformException catch (e) {
      return {
        'success': false,
        'error': e.code,
        'message': e.message ?? 'Unknown error',
      };
    }
  }

  /// 从 SDK 获取所有会话列表
  static Future<Map<String, dynamic>> getAllConversations() async {
    try {
      final result = await _channel.invokeMethod('getAllConversations');
      return Map<String, dynamic>.from(result);
    } on PlatformException catch (e) {
      return {
        'success': false,
        'error': e.code,
        'message': e.message ?? 'Unknown error',
      };
    }
  }

  /// 从 SDK 获取指定会话的消息
  static Future<Map<String, dynamic>> getMessages(String sessionId, {int limit = 100, int offset = 0}) async {
    try {
      final result = await _channel.invokeMethod('getMessages', {
        'sessionId': sessionId,
        'limit': limit,
        'offset': offset,
      });
      return Map<String, dynamic>.from(result);
    } on PlatformException catch (e) {
      return {
        'success': false,
        'error': e.code,
        'message': e.message ?? 'Unknown error',
      };
    }
  }

  /// 从 SDK 删除单条消息
  static Future<Map<String, dynamic>> deleteMessageFromStore(String messageId) async {
    try {
      final result = await _channel.invokeMethod('deleteMessage', {
        'messageId': messageId,
      });
      return Map<String, dynamic>.from(result);
    } on PlatformException catch (e) {
      return {
        'success': false,
        'error': e.code,
        'message': e.message ?? 'Unknown error',
      };
    }
  }

  /// 从 SDK 清空指定会话
  static Future<Map<String, dynamic>> clearSession(String sessionId) async {
    try {
      final result = await _channel.invokeMethod('clearSession', {
        'sessionId': sessionId,
      });
      return Map<String, dynamic>.from(result);
    } on PlatformException catch (e) {
      return {
        'success': false,
        'error': e.code,
        'message': e.message ?? 'Unknown error',
      };
    }
  }

  // ===== Group methods =====

  static Future<Map<String, dynamic>> enableGroupMessageStore() async {
    try {
      final result = await _channel.invokeMethod('enableGroupMessageStore');
      return Map<String, dynamic>.from(result);
    } on PlatformException catch (e) {
      return {'success': false, 'error': e.code, 'message': e.message ?? 'Unknown error'};
    }
  }

  static Future<Map<String, dynamic>> initGroupClient({required String sessionId, required String targetAid}) async {
    try {
      final result = await _channel.invokeMethod('initGroupClient', {
        'sessionId': sessionId,
        'targetAid': targetAid,
      });
      return Map<String, dynamic>.from(result);
    } on PlatformException catch (e) {
      return {'success': false, 'error': e.code, 'message': e.message ?? 'Unknown error'};
    }
  }

  static Future<Map<String, dynamic>> groupCreateGroup({
    required String name,
    String alias = '',
    String subject = '',
    String visibility = 'public',
    String description = '',
    String tags = '',
  }) async {
    try {
      final result = await _channel.invokeMethod('groupCreateGroup', {
        'name': name,
        'alias': alias,
        'subject': subject,
        'visibility': visibility,
        'description': description,
        'tags': tags,
      });
      return Map<String, dynamic>.from(result);
    } on PlatformException catch (e) {
      return {'success': false, 'error': e.code, 'message': e.message ?? 'Unknown error'};
    }
  }

  static Future<Map<String, dynamic>> groupJoinByUrl({
    required String groupUrl,
    String inviteCode = '',
    String message = '',
  }) async {
    try {
      final result = await _channel.invokeMethod('groupJoinByUrl', {
        'groupUrl': groupUrl,
        'inviteCode': inviteCode,
        'message': message,
      });
      return Map<String, dynamic>.from(result);
    } on PlatformException catch (e) {
      return {'success': false, 'error': e.code, 'message': e.message ?? 'Unknown error'};
    }
  }

  static Future<Map<String, dynamic>> groupListMyGroups({String status = ''}) async {
    try {
      final result = await _channel.invokeMethod('groupListMyGroups', {'status': status});
      return Map<String, dynamic>.from(result);
    } on PlatformException catch (e) {
      return {'success': false, 'error': e.code, 'message': e.message ?? 'Unknown error'};
    }
  }

  static Future<Map<String, dynamic>> groupGetInfo(String groupId) async {
    try {
      final result = await _channel.invokeMethod('groupGetInfo', {'groupId': groupId});
      return Map<String, dynamic>.from(result);
    } on PlatformException catch (e) {
      return {'success': false, 'error': e.code, 'message': e.message ?? 'Unknown error'};
    }
  }

  static Future<Map<String, dynamic>> groupGetMembers(String groupId) async {
    try {
      final result = await _channel.invokeMethod('groupGetMembers', {'groupId': groupId});
      return Map<String, dynamic>.from(result);
    } on PlatformException catch (e) {
      return {'success': false, 'error': e.code, 'message': e.message ?? 'Unknown error'};
    }
  }

  static Future<Map<String, dynamic>> groupLeaveGroup(String groupId) async {
    try {
      final result = await _channel.invokeMethod('groupLeaveGroup', {'groupId': groupId});
      return Map<String, dynamic>.from(result);
    } on PlatformException catch (e) {
      return {'success': false, 'error': e.code, 'message': e.message ?? 'Unknown error'};
    }
  }

  static Future<Map<String, dynamic>> groupSearchGroups({
    String keyword = '',
    String tags = '',
    int limit = 20,
    int offset = 0,
  }) async {
    try {
      final result = await _channel.invokeMethod('groupSearchGroups', {
        'keyword': keyword,
        'tags': tags,
        'limit': limit,
        'offset': offset,
      });
      return Map<String, dynamic>.from(result);
    } on PlatformException catch (e) {
      return {'success': false, 'error': e.code, 'message': e.message ?? 'Unknown error'};
    }
  }

  static Future<Map<String, dynamic>> groupSendMessage({
    required String groupId,
    required String content,
    String contentType = 'text',
    String metadataJson = '',
  }) async {
    try {
      final result = await _channel.invokeMethod('groupSendMessage', {
        'groupId': groupId,
        'content': content,
        'contentType': contentType,
        'metadataJson': metadataJson,
      });
      return Map<String, dynamic>.from(result);
    } on PlatformException catch (e) {
      return {'success': false, 'error': e.code, 'message': e.message ?? 'Unknown error'};
    }
  }

  static Future<Map<String, dynamic>> groupGetGroupList() async {
    try {
      final result = await _channel.invokeMethod('groupGetGroupList');
      return Map<String, dynamic>.from(result);
    } on PlatformException catch (e) {
      return {'success': false, 'error': e.code, 'message': e.message ?? 'Unknown error'};
    }
  }

  static Future<Map<String, dynamic>> groupGetMessages(String groupId, {int limit = 100, int offset = 0}) async {
    try {
      final result = await _channel.invokeMethod('groupGetMessages', {
        'groupId': groupId,
        'limit': limit,
        'offset': offset,
      });
      return Map<String, dynamic>.from(result);
    } on PlatformException catch (e) {
      return {'success': false, 'error': e.code, 'message': e.message ?? 'Unknown error'};
    }
  }

  static Future<Map<String, dynamic>> groupMarkRead(String groupId) async {
    try {
      final result = await _channel.invokeMethod('groupMarkRead', {'groupId': groupId});
      return Map<String, dynamic>.from(result);
    } on PlatformException catch (e) {
      return {'success': false, 'error': e.code, 'message': e.message ?? 'Unknown error'};
    }
  }

  static Future<Map<String, dynamic>> joinGroupSession(String groupId) async {
    try {
      final result = await _channel.invokeMethod('joinGroupSession', {'groupId': groupId});
      return Map<String, dynamic>.from(result);
    } on PlatformException catch (e) {
      return {'success': false, 'error': e.code, 'message': e.message ?? 'Unknown error'};
    }
  }

  static Future<Map<String, dynamic>> leaveGroupSession(String groupId) async {
    try {
      final result = await _channel.invokeMethod('leaveGroupSession', {'groupId': groupId});
      return Map<String, dynamic>.from(result);
    } on PlatformException catch (e) {
      return {'success': false, 'error': e.code, 'message': e.message ?? 'Unknown error'};
    }
  }

  static Future<Map<String, dynamic>> setGroupHandlers() async {
    try {
      final result = await _channel.invokeMethod('setGroupHandlers');
      return Map<String, dynamic>.from(result);
    } on PlatformException catch (e) {
      return {'success': false, 'error': e.code, 'message': e.message ?? 'Unknown error'};
    }
  }

  /// 解析 SDK 消息的 blocksJson 为文本
  static String parseBlocksJson(String? blocksJson) {
    if (blocksJson == null || blocksJson.isEmpty) return '';
    try {
      final blocks = jsonDecode(blocksJson) as List;
      if (blocks.isNotEmpty) {
        return blocks.first['text'] ?? '';
      }
    } catch (_) {
      return blocksJson;
    }
    return '';
  }
}
