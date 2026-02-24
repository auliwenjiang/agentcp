import 'package:flutter/material.dart';
import '../services/agent_info_service.dart';
import 'chat_detail_page.dart';

class GroupMembersPage extends StatelessWidget {
  final String groupName;
  final List<String> memberAids;

  const GroupMembersPage({
    super.key,
    required this.groupName,
    required this.memberAids,
  });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('$groupName (${memberAids.length})',
            style: const TextStyle(fontSize: 16)),
        backgroundColor: Theme.of(context).colorScheme.inversePrimary,
      ),
      body: ListView.builder(
        padding: const EdgeInsets.symmetric(vertical: 8),
        itemCount: memberAids.length,
        itemBuilder: (context, index) {
          final aid = memberAids[index];
          return _MemberTile(aid: aid);
        },
      ),
    );
  }
}

class _MemberTile extends StatelessWidget {
  final String aid;
  const _MemberTile({required this.aid});

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<AgentInfo>(
      future: AgentInfoService().getAgentInfo(aid),
      builder: (context, snapshot) {
        final info = snapshot.data;
        final avatarPath =
            AgentInfoService().getAvatarAssetPath(info?.type ?? '');
        final displayName =
            (info?.name.isNotEmpty == true) ? info!.name : aid;
        final description = info?.description ?? '';

        return ListTile(
          leading: CircleAvatar(
            backgroundImage: AssetImage(avatarPath),
            radius: 22,
          ),
          title: Text(displayName,
              style:
                  const TextStyle(fontSize: 15, fontWeight: FontWeight.w500)),
          subtitle: description.isNotEmpty
              ? Text(description,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(fontSize: 13, color: Colors.grey[600]))
              : Text(aid,
                  style: TextStyle(fontSize: 12, color: Colors.grey[400])),
          trailing:
              Icon(Icons.chevron_right, size: 20, color: Colors.grey[400]),
          onTap: () {
            Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => AgentMdPage(aid: aid)),
            );
          },
        );
      },
    );
  }
}
