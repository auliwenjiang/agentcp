import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';
import '../services/agentcp_service.dart';
import '../services/agent_info_service.dart';

/// AgentCP 管理页面
///
/// 简化的 AID 管理流程：
/// 1. 检查本地是否有 AID
/// 2. 有 AID 则显示列表，可选择登录
/// 3. 无 AID 则显示创建界面
class AgentCPPage extends StatefulWidget {
  const AgentCPPage({super.key});

  @override
  State<AgentCPPage> createState() => _AgentCPPageState();
}

class _AgentCPPageState extends State<AgentCPPage> {
  static const String _defaultAP = 'agentcp.io';
  static const List<String> _apOptions = ['agentcp.io', 'agentid.pub'];

  final _nameController = TextEditingController();
  final _apController = TextEditingController(text: _defaultAP);
  final _nicknameController = TextEditingController();
  final _descController = TextEditingController();
  String _selectedAP = _defaultAP;
  bool _isCustomAP = false;

  bool _isLoading = true;
  bool _isCreating = false;
  String? _currentAid;
  String _currentState = 'Offline';
  List<String> _aidList = [];
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _initSDKAndLoadAIDs();
  }

  @override
  void dispose() {
    _nameController.dispose();
    _apController.dispose();
    _nicknameController.dispose();
    _descController.dispose();
    super.dispose();
  }

  /// 初始化 SDK 并加载本地 AID 列表
  Future<void> _initSDKAndLoadAIDs() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      // 设置日志级别为 trace，输出最详细的日志
      debugPrint('[ACP] Setting log level to trace...');
      await AgentCPService.setLogLevel('trace');

      // 设置默认服务器地址
      debugPrint('[ACP] Setting base URLs: CA=https://ca.$_defaultAP, AP=https://ap.$_defaultAP');
      await AgentCPService.setBaseUrls(
        caBaseUrl: 'https://ca.$_defaultAP',
        apBaseUrl: 'https://ap.$_defaultAP',
      );

      // 设置存储路径
      debugPrint('[ACP] Setting storage path...');
      final appDocDir = await getApplicationDocumentsDirectory();
      await AgentCPService.setStoragePath(path: appDocDir.path);

      // 初始化 SDK
      debugPrint('[ACP] Initializing SDK...');
      final initResult = await AgentCPService.initialize();
      debugPrint('[ACP] Init result: $initResult');
      if (initResult['success'] != true) {
        setState(() {
          _errorMessage = '初始化失败: ${initResult['message']}';
        });
        return;
      }

      // 加载本地 AID 列表
      await _refreshAIDList();

      // 获取当前状态
      await _refreshState();
    } catch (e) {
      setState(() {
        _errorMessage = '初始化异常: $e';
      });
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
  }

  /// 刷新 AID 列表
  Future<void> _refreshAIDList() async {
    final result = await AgentCPService.listAIDs();
    if (result['success'] == true && result['aids'] != null) {
      setState(() {
        _aidList = List<String>.from(result['aids']);
      });
    }
  }

  /// 刷新状态
  Future<void> _refreshState() async {
    final state = await AgentCPService.getState();
    final currentAid = await AgentCPService.getCurrentAID();
    setState(() {
      _currentState = state;
      _currentAid = currentAid;
    });
  }

  /// 根据 AP 域名设置 SDK 的 base URLs
  Future<void> _setBaseUrlsForAP(String ap) async {
    debugPrint('[ACP] Setting base URLs for AP: $ap');
    await AgentCPService.setBaseUrls(
      caBaseUrl: 'https://ca.$ap',
      apBaseUrl: 'https://ap.$ap',
    );
  }

  /// 从 AID 中提取 AP 域名 (e.g. "alice.agentcp.io" → "agentcp.io")
  String _extractAP(String aid) {
    final dotIndex = aid.indexOf('.');
    if (dotIndex < 0) return _defaultAP;
    return aid.substring(dotIndex + 1);
  }

  /// 一键创建 AID
  Future<void> _createAID() async {
    final name = _nameController.text.trim();
    final ap = _apController.text.trim();

    if (name.isEmpty) {
      _showMessage('请输入名称', isError: true);
      return;
    }

    // 验证名称格式（只允许英文字母和数字）
    if (!RegExp(r'^[a-zA-Z0-9]+$').hasMatch(name)) {
      _showMessage('名称只能包含英文字母和数字', isError: true);
      return;
    }

    final aid = '$name.$ap';

    setState(() {
      _isCreating = true;
      _errorMessage = null;
    });

    try {
      // 根据 AP 域名设置 base URLs
      await _setBaseUrlsForAP(ap);

      // 创建 AID（SDK 内部会自动生成密钥对）
      debugPrint('[ACP] Creating AID: $aid with password');
      final result = await AgentCPService.createAID(
        aid: aid,
        password: '123456',
      );
      debugPrint('[ACP] Create result: $result');

      if (result['success'] == true) {
        _showMessage('AID 创建成功: $aid');

        // Generate complete agent.md and save locally
        final nickname = _nicknameController.text.trim();
        final description = _descController.text.trim();
        final mdContent = await AgentInfoService.createDefaultHumanAgentMd(
          aid: aid,
          name: nickname.isNotEmpty ? nickname : null,
          description: description,
        );

        // Load + online, then force upload agent.md
        try {
          await AgentCPService.loadAID(aid, password: '123456');
          await AgentCPService.online();
          await AgentCPService.setHandlers();
          // Force upload on first creation (bypass sync check)
          AgentInfoService.forceUploadAgentMd(aid, mdContent);
          // Initialize group client
          _initGroupClient(aid);
        } catch (e) {
          debugPrint('[ACP] auto-login after create failed: $e');
        }

        _nameController.clear();
        _nicknameController.clear();
        _descController.clear();
        await _refreshAIDList();
        await _refreshState();
      } else {
        _showMessage('创建失败: ${result['message']}', isError: true);
      }
    } catch (e) {
      _showMessage('创建异常: $e', isError: true);
    } finally {
      setState(() {
        _isCreating = false;
      });
    }
  }

  /// 选择并登录 AID
  Future<void> _loginWithAID(String aid) async {
    debugPrint('[ACP] loginWithAID: $aid');
    
    // 如果已经是当前在线的 AID，直接进入聊天
    if (_currentAid == aid && _currentState == 'Online') {
      Navigator.pushNamed(context, '/chat');
      return;
    }

    setState(() {
      _isLoading = true;
    });

    try {
      // 如果当前有在线的，先下线
      if (_currentState == 'Online') {
        debugPrint('[ACP] Switching AID, going offline first...');
        await AgentCPService.offline();
      }

      // 根据 AID 的 AP 域名设置 base URLs
      await _setBaseUrlsForAP(_extractAP(aid));

      // 加载 AID
      debugPrint('[ACP] Loading AID: $aid');
      final loadResult = await AgentCPService.loadAID(aid, password: '123456');
      debugPrint('[ACP] Load result: $loadResult');
      if (loadResult['success'] != true) {
        _showMessage('加载失败: ${loadResult['message']}', isError: true);
        return;
      }

      // 上线
      debugPrint('[ACP] Going online...');
      final onlineResult = await AgentCPService.online();
      debugPrint('[ACP] Online result: $onlineResult');
      await _refreshState();
      debugPrint('[ACP] After refresh: state=$_currentState, aid=$_currentAid');
      if (onlineResult['success'] == true) {
        // Register native callbacks for messages/invites/state changes
        await AgentCPService.setHandlers();
        AgentInfoService.syncOnOnline(aid); // fire-and-forget
        // Initialize group client
        _initGroupClient(aid);
        _showMessage('登录成功');
      } else {
        _showMessage('上线失败: ${onlineResult['message']}', isError: true);
      }
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
  }

  /// 下线
  Future<void> _logout() async {
    setState(() {
      _isLoading = true;
    });

    try {
      await AgentCPService.offline();
      _showMessage('已下线');
      await _refreshState();
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
  }

  /// 删除 AID
  Future<void> _deleteAID(String aid) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('确认删除'),
        content: Text('确定要删除 "$aid" 吗？\n\n删除后将无法恢复，私钥将被永久删除。'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('取消'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            style: TextButton.styleFrom(foregroundColor: Colors.red),
            child: const Text('删除'),
          ),
        ],
      ),
    );

    if (confirmed != true) return;

    setState(() {
      _isLoading = true;
    });

    try {
      // 如果是当前登录的 AID，先下线
      if (_currentAid == aid && _currentState == 'Online') {
        await AgentCPService.offline();
      }

      final result = await AgentCPService.deleteAID(aid);
      if (result['success'] == true) {
        _showMessage('已删除');
        await _refreshAIDList();
        await _refreshState();
      } else {
        _showMessage('删除失败: ${result['message']}', isError: true);
      }
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
  }

  /// 显示消息
  void _showMessage(String message, {bool isError = false}) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: isError ? Colors.red : Colors.green,
        duration: const Duration(seconds: 2),
      ),
    );
  }

  /// 初始化群组客户端
  void _initGroupClient(String aid) async {
    try {
      // Extract issuer from AID: e.g. "alice.aid.pub" → issuer = "aid.pub" → target = "group.aid.pub"
      final dotIndex = aid.indexOf('.');
      if (dotIndex < 0) return;
      final issuer = aid.substring(dotIndex + 1);
      final groupTarget = 'group.$issuer';

      debugPrint('[ACP] Initializing group client: target=$groupTarget');
      final sessionResult = await AgentCPService.createSession([groupTarget]);
      if (sessionResult['success'] == true) {
        final sessionId = sessionResult['sessionId'] as String;
        await AgentCPService.initGroupClient(sessionId: sessionId, targetAid: groupTarget);
        debugPrint('[ACP] Group client initialized: session=$sessionId');
      } else {
        debugPrint('[ACP] Failed to create group session: ${sessionResult['message']}');
      }
    } catch (e) {
      debugPrint('[ACP] initGroupClient failed: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('ACP身份管理'),
        backgroundColor: Theme.of(context).colorScheme.inversePrimary,
        actions: [
          if (_currentState == 'Online')
            IconButton(
              icon: const Icon(Icons.chat),
              onPressed: () => Navigator.pushNamed(context, '/chat'),
              tooltip: '进入聊天',
            ),
          if (_aidList.length < 10)
            IconButton(
              icon: const Icon(Icons.add),
              onPressed: _showCreateDialog,
              tooltip: '创建新身份',
            ),
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _initSDKAndLoadAIDs,
            tooltip: '刷新',
          ),
        ],
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    // 加载中
    if (_isLoading) {
      return const Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            CircularProgressIndicator(),
            SizedBox(height: 16),
            Text('加载中...'),
          ],
        ),
      );
    }

    // 错误状态
    if (_errorMessage != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(Icons.error_outline, size: 64, color: Colors.red),
              const SizedBox(height: 16),
              Text(
                _errorMessage!,
                textAlign: TextAlign.center,
                style: const TextStyle(color: Colors.red),
              ),
              const SizedBox(height: 24),
              ElevatedButton.icon(
                onPressed: _initSDKAndLoadAIDs,
                icon: const Icon(Icons.refresh),
                label: const Text('重试'),
              ),
            ],
          ),
        ),
      );
    }

    // 无本地 AID，显示创建界面
    if (_aidList.isEmpty) {
      return _buildCreateView();
    }

    // 显示列表
    return _buildAIDListView();
  }

  /// AID 列表视图
  Widget _buildAIDListView() {
    return Column(
      children: [
        if (_currentState == 'Online' && _currentAid != null)
          Container(
            color: Colors.green.shade50,
            padding: const EdgeInsets.all(12),
            child: Row(
              children: [
                const Icon(Icons.check_circle, color: Colors.green),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('当前在线: $_currentAid',
                          style: const TextStyle(
                              fontWeight: FontWeight.bold,
                              color: Colors.green)),
                      const Text('点击下方列表切换身份',
                          style: TextStyle(fontSize: 12, color: Colors.grey)),
                    ],
                  ),
                ),
                TextButton(
                  onPressed: _logout,
                  child: const Text('下线'),
                ),
              ],
            ),
          ),
        Expanded(
          child: ListView.builder(
            padding: const EdgeInsets.all(16),
            itemCount: _aidList.length,
            itemBuilder: (context, index) {
              final aid = _aidList[index];
              final isCurrent = aid == _currentAid;
              final isOnline = isCurrent && _currentState == 'Online';

              return Card(
                elevation: isCurrent ? 4 : 1,
                margin: const EdgeInsets.only(bottom: 12),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                  side: isCurrent
                      ? BorderSide(color: Theme.of(context).primaryColor, width: 2)
                      : BorderSide.none,
                ),
                child: ListTile(
                  leading: CircleAvatar(
                    backgroundColor: isOnline ? Colors.green : Colors.grey,
                    child: const Icon(Icons.person, color: Colors.white),
                  ),
                  title: Text(
                    aid,
                    style: TextStyle(
                      fontFamily: 'monospace',
                      fontWeight: isCurrent ? FontWeight.bold : FontWeight.normal,
                    ),
                  ),
                  subtitle: Text(isOnline ? '在线' : '离线'),
                  trailing: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      if (!isOnline)
                        IconButton(
                          icon: const Icon(Icons.delete_outline),
                          onPressed: () => _deleteAID(aid),
                          tooltip: '删除',
                        ),
                      if (isOnline)
                        IconButton(
                          icon: const Icon(Icons.chat),
                          onPressed: () => Navigator.pushNamed(context, '/chat'),
                          color: Theme.of(context).primaryColor,
                          tooltip: '聊天',
                        ),
                    ],
                  ),
                  onTap: () => _loginWithAID(aid),
                ),
              );
            },
          ),
        ),
        // 底部提示
        Padding(
          padding: const EdgeInsets.all(16.0),
          child: Text(
            '已注册 ${_aidList.length}/10 个身份',
            style: const TextStyle(color: Colors.grey),
          ),
        ),
      ],
    );
  }

  /// 创建 AID 视图（无本地 AID 时显示）
  Widget _buildCreateView() {
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(
              Icons.person_add,
              size: 80,
              color: Colors.deepPurple,
            ),
            const SizedBox(height: 24),
            const Text(
              '创建你的 AID',
              style: TextStyle(
                fontSize: 24,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 8),
            const Text(
              '输入名称，一键创建你的 Agent ID',
              style: TextStyle(color: Colors.grey),
            ),
            const SizedBox(height: 32),
            _buildCreateForm(),
          ],
        ),
      ),
    );
  }

  /// 创建表单
  Widget _buildCreateForm() {
    return Column(
      children: [
        // 名称输入
        TextField(
          controller: _nameController,
          decoration: const InputDecoration(
            labelText: 'AID 名称',
            hintText: '只能输入英文和数字',
            border: OutlineInputBorder(),
            prefixIcon: Icon(Icons.person),
            prefixText: 'AID: ',
          ),
          textInputAction: TextInputAction.next,
          enabled: !_isCreating,
          onChanged: (_) => setState(() {}),
        ),
        const SizedBox(height: 16),

        // 昵称输入
        TextField(
          controller: _nicknameController,
          decoration: const InputDecoration(
            labelText: '昵称 (可选)',
            hintText: '例如: Alice Wang',
            border: OutlineInputBorder(),
            prefixIcon: Icon(Icons.badge),
          ),
          textInputAction: TextInputAction.next,
          enabled: !_isCreating,
        ),
        const SizedBox(height: 16),

        // 描述输入
        TextField(
          controller: _descController,
          decoration: const InputDecoration(
            labelText: '描述 (可选)',
            hintText: '简单介绍自己',
            border: OutlineInputBorder(),
            prefixIcon: Icon(Icons.description),
          ),
          textInputAction: TextInputAction.next,
          enabled: !_isCreating,
          maxLines: 2,
        ),
        const SizedBox(height: 16),

        // AP 服务器选择
        _buildAPSelector(),
        const SizedBox(height: 12),

        // 预览 AID
        if (_nameController.text.isNotEmpty)
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Colors.grey[100],
              borderRadius: BorderRadius.circular(8),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  '你的 AID 将是:',
                  style: TextStyle(fontSize: 12, color: Colors.grey),
                ),
                const SizedBox(height: 4),
                Text(
                  '${_nameController.text}.${_apController.text}',
                  style: const TextStyle(
                    fontSize: 16,
                    fontFamily: 'monospace',
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ],
            ),
          ),
        const SizedBox(height: 24),

        // 创建按钮
        SizedBox(
          width: double.infinity,
          child: ElevatedButton.icon(
            onPressed: _isCreating ? null : _createAID,
            icon: _isCreating
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.add),
            label: Text(_isCreating ? '创建中...' : '一键创建'),
            style: ElevatedButton.styleFrom(
              padding: const EdgeInsets.symmetric(vertical: 16),
              backgroundColor: Colors.deepPurple,
              foregroundColor: Colors.white,
            ),
          ),
        ),
      ],
    );
  }

  /// AP 服务器选择器
  Widget _buildAPSelector() {
    return Column(
      children: [
        DropdownButtonFormField<String>(
          value: _isCustomAP ? 'custom' : _selectedAP,
          decoration: const InputDecoration(
            labelText: 'AP 服务器',
            border: OutlineInputBorder(),
            prefixIcon: Icon(Icons.cloud),
          ),
          items: [
            ..._apOptions.map((ap) => DropdownMenuItem(
                  value: ap,
                  child: Text(ap),
                )),
            const DropdownMenuItem(
              value: 'custom',
              child: Text('手动输入'),
            ),
          ],
          onChanged: _isCreating
              ? null
              : (value) {
                  setState(() {
                    if (value == 'custom') {
                      _isCustomAP = true;
                      _apController.text = '';
                    } else {
                      _isCustomAP = false;
                      _selectedAP = value!;
                      _apController.text = value;
                    }
                  });
                },
        ),
        if (_isCustomAP) ...[
          const SizedBox(height: 12),
          TextField(
            controller: _apController,
            decoration: const InputDecoration(
              labelText: '自定义 AP 服务器',
              hintText: '例如: example.com',
              border: OutlineInputBorder(),
              prefixIcon: Icon(Icons.edit),
            ),
            enabled: !_isCreating,
            onChanged: (_) => setState(() {}),
          ),
        ],
      ],
    );
  }

  /// 显示创建对话框（有 AID 时点击创建按钮）
  void _showCreateDialog() {
    _nameController.clear();
    _selectedAP = _defaultAP;
    _apController.text = _defaultAP;
    _isCustomAP = false;
    _nicknameController.clear();
    _descController.clear();

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (context) => StatefulBuilder(
        builder: (context, setModalState) {
          return Padding(
            padding: EdgeInsets.only(
              left: 24,
              right: 24,
              top: 24,
              bottom: MediaQuery.of(context).viewInsets.bottom + 24,
            ),
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    '创建新 AID',
                    style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 24),
                  TextField(
                    controller: _nameController,
                    decoration: const InputDecoration(
                      labelText: 'AID 名称',
                      hintText: '只能输入英文和数字',
                      border: OutlineInputBorder(),
                      prefixIcon: Icon(Icons.person),
                      prefixText: 'AID: ',
                    ),
                    autofocus: true,
                    onChanged: (_) => setModalState(() {}),
                  ),
                  const SizedBox(height: 16),
                  TextField(
                    controller: _nicknameController,
                    decoration: const InputDecoration(
                      labelText: '昵称 (可选)',
                      hintText: '例如: Alice Wang',
                      border: OutlineInputBorder(),
                      prefixIcon: Icon(Icons.badge),
                    ),
                  ),
                  const SizedBox(height: 16),
                  TextField(
                    controller: _descController,
                    decoration: const InputDecoration(
                      labelText: '描述 (可选)',
                      hintText: '简单介绍自己',
                      border: OutlineInputBorder(),
                      prefixIcon: Icon(Icons.description),
                    ),
                    maxLines: 2,
                  ),
                  const SizedBox(height: 16),
                  DropdownButtonFormField<String>(
                    value: _isCustomAP ? 'custom' : _selectedAP,
                    decoration: const InputDecoration(
                      labelText: 'AP 服务器',
                      border: OutlineInputBorder(),
                      prefixIcon: Icon(Icons.cloud),
                    ),
                    items: [
                      ..._apOptions.map((ap) => DropdownMenuItem(
                            value: ap,
                            child: Text(ap),
                          )),
                      const DropdownMenuItem(
                        value: 'custom',
                        child: Text('手动输入'),
                      ),
                    ],
                    onChanged: (value) {
                      setModalState(() {
                        if (value == 'custom') {
                          _isCustomAP = true;
                          _apController.text = '';
                        } else {
                          _isCustomAP = false;
                          _selectedAP = value!;
                          _apController.text = value;
                        }
                      });
                      setState(() {});
                    },
                  ),
                  if (_isCustomAP) ...[
                    const SizedBox(height: 12),
                    TextField(
                      controller: _apController,
                      decoration: const InputDecoration(
                        labelText: '自定义 AP 服务器',
                        hintText: '例如: example.com',
                        border: OutlineInputBorder(),
                        prefixIcon: Icon(Icons.edit),
                      ),
                      onChanged: (_) => setModalState(() {}),
                    ),
                  ],
                  const SizedBox(height: 12),
                  if (_nameController.text.isNotEmpty)
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: Colors.grey[100],
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Text(
                        '${_nameController.text}.${_apController.text}',
                        style: const TextStyle(
                          fontFamily: 'monospace',
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                  const SizedBox(height: 24),
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton(
                      onPressed: () {
                        Navigator.pop(context);
                        _createAID();
                      },
                      style: ElevatedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(vertical: 16),
                        backgroundColor: Colors.deepPurple,
                        foregroundColor: Colors.white,
                      ),
                      child: const Text('创建'),
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}
