import 'dart:convert';
import 'dart:io';
import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:path/path.dart' as path;
import 'agentcp_service.dart';

class AgentInfo {
  final String type;
  final String name;
  final String description;
  final int cachedAt;

  AgentInfo({
    this.type = '',
    this.name = '',
    this.description = '',
    this.cachedAt = 0,
  });

  Map<String, dynamic> toJson() => {
    'type': type,
    'name': name,
    'description': description,
    'cachedAt': cachedAt,
  };

  factory AgentInfo.fromJson(Map<String, dynamic> json) => AgentInfo(
    type: json['type'] ?? '',
    name: json['name'] ?? '',
    description: json['description'] ?? '',
    cachedAt: json['cachedAt'] ?? 0,
  );
}

class AgentInfoService {
  static final AgentInfoService _instance = AgentInfoService._internal();
  factory AgentInfoService() => _instance;
  AgentInfoService._internal();

  static const int _cacheTtl = 24 * 60 * 60 * 1000; // 24 hours
  final Map<String, AgentInfo> _cache = {};
  String? _cacheFilePath;

  Future<void> init() async {
    if (_cacheFilePath != null) return;
    final dir = await getApplicationDocumentsDirectory();
    _cacheFilePath = path.join(dir.path, 'agent_info_cache.json');
    await _loadCache();
  }

  Future<void> _loadCache() async {
    if (_cacheFilePath == null) return;
    final file = File(_cacheFilePath!);
    if (await file.exists()) {
      try {
        final content = await file.readAsString();
        final Map<String, dynamic> data = jsonDecode(content);
        final now = DateTime.now().millisecondsSinceEpoch;
        data.forEach((key, value) {
          final info = AgentInfo.fromJson(value);
          if (now - info.cachedAt < _cacheTtl) {
            _cache[key] = info;
          }
        });
      } catch (e) {
        print('[AgentInfo] Error loading cache: $e');
      }
    }
  }

  Future<void> _saveCache() async {
    if (_cacheFilePath == null) return;
    try {
      final file = File(_cacheFilePath!);
      await file.writeAsString(jsonEncode(_cache));
    } catch (e) {
      print('[AgentInfo] Error saving cache: $e');
    }
  }

  Future<AgentInfo> getAgentInfo(String aid) async {
    await init();
    
    if (_cache.containsKey(aid)) {
      final info = _cache[aid]!;
      if (DateTime.now().millisecondsSinceEpoch - info.cachedAt < _cacheTtl) {
        return info;
      }
    }

    try {
      final info = await _fetchAgentMd(aid);
      _cache[aid] = info;
      await _saveCache();
      return info;
    } catch (e) {
      print('[AgentInfo] Fetch failed for $aid: $e');
      final fallback = _cache[aid] ?? AgentInfo(name: aid, cachedAt: DateTime.now().millisecondsSinceEpoch);
      _cache[aid] = fallback;
      await _saveCache();
      return fallback;
    }
  }

  Future<AgentInfo> _fetchAgentMd(String aid) async {
    final url = Uri.parse('https://$aid/agent.md');
    final response = await http.get(url).timeout(const Duration(seconds: 5));

    if (response.statusCode == 200) {
      return _parseAgentMd(response.body);
    } else {
      throw Exception('HTTP ${response.statusCode}');
    }
  }

  AgentInfo _parseAgentMd(String content) {
    String type = '';
    String name = '';
    String description = '';

    // Simple Frontmatter parser using Regex
    final match = RegExp(r'^---\s*\n([\s\S]*?)\n---', multiLine: true).firstMatch(content);
    if (match != null) {
      final yaml = match.group(1)!;
      final typeMatch = RegExp(r'^type:\s*"?([^"\n]*)"?\s*$', multiLine: true).firstMatch(yaml);
      final nameMatch = RegExp(r'^name:\s*"?([^"\n]*)"?\s*$', multiLine: true).firstMatch(yaml);
      final descMatch = RegExp(r'^description:\s*"?([^"\n]*)"?\s*$', multiLine: true).firstMatch(yaml);

      if (typeMatch != null) type = typeMatch.group(1)!.trim();
      if (nameMatch != null) name = nameMatch.group(1)!.trim();
      if (descMatch != null) description = descMatch.group(1)!.trim();
    }

    return AgentInfo(
      type: type,
      name: name,
      description: description,
      cachedAt: DateTime.now().millisecondsSinceEpoch,
    );
  }
  
  String getAvatarAssetPath(String type) {
    if (type == 'openclaw') return 'assets/openclaw.png';
    if (type == 'human') return 'assets/human.png';
    return 'assets/agent.png';
  }

  /// Save agent.md content locally for the given AID
  static Future<void> saveLocalAgentMd(String aid, String mdContent) async {
    try {
      final dir = await getApplicationDocumentsDirectory();
      final agentMdDir = Directory(path.join(dir.path, 'agent_md'));
      if (!await agentMdDir.exists()) {
        await agentMdDir.create(recursive: true);
      }
      final file = File(path.join(agentMdDir.path, '$aid.md'));
      await file.writeAsString(mdContent);
      debugPrint('[AgentInfo] saveLocalAgentMd: saved for $aid');
    } catch (e) {
      debugPrint('[AgentInfo] saveLocalAgentMd error: $e');
    }
  }

  /// Read local agent.md for the given AID, returns null if not exists
  static Future<String?> getLocalAgentMd(String aid) async {
    try {
      final dir = await getApplicationDocumentsDirectory();
      final file = File(path.join(dir.path, 'agent_md', '$aid.md'));
      if (await file.exists()) {
        return await file.readAsString();
      }
    } catch (e) {
      debugPrint('[AgentInfo] getLocalAgentMd error: $e');
    }
    return null;
  }

  /// Sync local agent.md to AP after going online. Fire-and-forget.
  static void syncOnOnline(String aid) {
    () async {
      try {
        final mdContent = await getLocalAgentMd(aid);
        if (mdContent == null) {
          debugPrint('[AgentInfo] syncOnOnline: no local agent.md for $aid');
          return;
        }
        await syncAgentMd(aid, mdContent);
      } catch (e) {
        debugPrint('[AgentInfo] syncOnOnline error: $e');
      }
    }();
  }

  /// Sync agent.md content to the AP server
  static Future<bool> syncAgentMd(String aid, String mdContent) async {
    try {
      final signature = await AgentCPService.getSignature();
      if (signature == null || signature.isEmpty) {
        print('[AgentInfo] syncAgentMd: no signature available');
        return false;
      }

      // Extract AP domain from AID (e.g., "alice.aid.pub" -> "aid.pub")
      final dotIndex = aid.indexOf('.');
      if (dotIndex < 0) {
        print('[AgentInfo] syncAgentMd: invalid AID format');
        return false;
      }
      final domain = aid.substring(dotIndex + 1);

      final contentBytes = utf8.encode(mdContent);
      final contentHash = sha256.convert(contentBytes).toString();

      // Step 1: sync_public_files to check what needs uploading
      final syncUrl = Uri.parse('https://ap.$domain/api/accesspoint/sync_public_files');
      final fileList = [
        {
          'file_name': 'agent.md',
          'hash': contentHash,
          'size': contentBytes.length,
        }
      ];
      final syncResponse = await http.post(
        syncUrl,
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'agent_id': aid,
          'signature': signature,
          'file_list': fileList,
        }),
      ).timeout(const Duration(seconds: 10));

      if (syncResponse.statusCode != 200) {
        print('[AgentInfo] syncAgentMd: sync_public_files failed HTTP ${syncResponse.statusCode}');
        return false;
      }

      final syncData = jsonDecode(syncResponse.body);
      final needUpload = List<String>.from(syncData['need_upload_files'] ?? []);

      if (!needUpload.contains('agent.md')) {
        print('[AgentInfo] syncAgentMd: agent.md already up to date');
        return true;
      }

      // Step 2: upload the file
      final uploadUrl = Uri.parse('https://ap.$domain/api/accesspoint/upload_file');
      final uploadResponse = await http.post(
        uploadUrl,
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'agent_id': aid,
          'signature': signature,
          'file_name': 'agent.md',
          'content': base64Encode(contentBytes),
        }),
      ).timeout(const Duration(seconds: 10));

      if (uploadResponse.statusCode != 200) {
        print('[AgentInfo] syncAgentMd: upload_file failed HTTP ${uploadResponse.statusCode}');
        return false;
      }

      print('[AgentInfo] syncAgentMd: agent.md synced successfully');
      return true;
    } catch (e) {
      print('[AgentInfo] syncAgentMd error: $e');
      return false;
    }
  }
}
