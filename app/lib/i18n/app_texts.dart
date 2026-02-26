import 'package:flutter/widgets.dart';

import 'app_language.dart';

class AppTexts {
  static String identityManagementTitle(BuildContext context) {
    return _isZh(context) ? 'ACP\u8eab\u4efd\u7ba1\u7406' : 'ACP Identity';
  }

  static String languageMenuLabel(BuildContext context) {
    return _isZh(context) ? '\u8bed\u8a00' : 'Language';
  }

  static String languageDialogTitle(BuildContext context) {
    return _isZh(context) ? '\u5207\u6362\u8bed\u8a00' : 'Switch Language';
  }

  static String languageOptionEnglish(BuildContext context) {
    return _isZh(context) ? '\u82f1\u6587' : 'English';
  }

  static String languageOptionChinese(BuildContext context) {
    return _isZh(context) ? '\u4e2d\u6587' : 'Chinese';
  }

  static String cancel(BuildContext context) {
    return _isZh(context) ? '\u53d6\u6d88' : 'Cancel';
  }

  static String save(BuildContext context) {
    return _isZh(context) ? '\u4fdd\u5b58' : 'Save';
  }

  static String languageChangedToEnglish(BuildContext context) {
    return _isZh(context)
        ? '\u5df2\u5207\u6362\u4e3a\u82f1\u6587'
        : 'Switched to English';
  }

  static String languageChangedToChinese(BuildContext context) {
    return _isZh(context)
        ? '\u5df2\u5207\u6362\u4e3a\u4e2d\u6587'
        : 'Switched to Chinese';
  }

  static String languagePersistedTip(BuildContext context, String path) {
    if (path.isEmpty) {
      return _isZh(context)
          ? '\u8bed\u8a00\u8bbe\u7f6e\u5df2\u4fdd\u5b58'
          : 'Language preference saved';
    }
    return _isZh(context)
        ? '\u8bed\u8a00\u8bbe\u7f6e\u5df2\u4fdd\u5b58: $path'
        : 'Language preference saved: $path';
  }

  static String chatsTitle(BuildContext context) {
    return _isZh(context) ? '\u804a\u5929' : 'Chats';
  }

  static String forceRefreshTooltip(BuildContext context) {
    return _isZh(context) ? '\u5f3a\u5236\u5237\u65b0' : 'Force refresh';
  }

  static String identityManagementEntry(BuildContext context) {
    return _isZh(context) ? '\u8eab\u4efd\u7ba1\u7406' : 'Identity Management';
  }

  static String appNameSubtitle(BuildContext context) {
    return 'AgentCP App';
  }

  static String copyMyAidCard(BuildContext context) {
    return _isZh(context) ? '复制我的身份证' : 'Copy My ID Card';
  }

  static String myAidCardMessage(BuildContext context, String nickname, String aid) {
    if (_isZh(context)) {
      return '我是$nickname，我加入了Agent互联网，https://$aid/agent.md 这是我的"身份证"，快来找我聊天吧！';
    } else {
      return 'I am $nickname, I joined the Agent Internet. https://$aid/agent.md is my "ID card", come chat with me!';
    }
  }

  static String aidCardCopied(BuildContext context) {
    return _isZh(context) ? '已复制到剪贴板' : 'Copied to clipboard';
  }

  static String noChatsYet(BuildContext context) {
    return _isZh(context) ? '\u6682\u65e0\u804a\u5929' : 'No chats yet.';
  }

  static String startNewChat(BuildContext context) {
    return _isZh(context) ? '\u5f00\u59cb\u65b0\u804a\u5929' : 'Start a new chat';
  }

  static String newP2PChat(BuildContext context) {
    return _isZh(context) ? '\u65b0\u5efa\u5355\u804a' : 'New P2P Chat';
  }

  static String createGroupChat(BuildContext context) {
    return _isZh(context) ? '\u521b\u5efa\u7fa4\u804a' : 'Create Group Chat';
  }

  static String joinGroupChat(BuildContext context) {
    return _isZh(context) ? '\u52a0\u5165\u7fa4\u804a' : 'Join Group Chat';
  }

  static String createGroupPageTitle(BuildContext context) {
    return _isZh(context) ? '\u521b\u5efa\u7fa4\u7ec4' : 'Create Group';
  }

  static String createGroupNameRequired(BuildContext context) {
    return _isZh(context) ? '\u8bf7\u8f93\u5165\u7fa4\u7ec4\u540d\u79f0' : 'Please enter group name';
  }

  static String createGroupDescRequired(BuildContext context) {
    return _isZh(context) ? '\u8bf7\u8f93\u5165\u7fa4\u7ec4\u63cf\u8ff0' : 'Please enter group description';
  }

  static String createGroupFailed(BuildContext context, String reason) {
    return _isZh(context) ? '\u521b\u5efa\u5931\u8d25: $reason' : 'Create failed: $reason';
  }

  static String createGroupNameHint(BuildContext context) {
    return _isZh(context) ? '\u8f93\u5165\u7fa4\u7ec4\u540d\u79f0' : 'Enter group name';
  }

  static String createGroupDescHint(BuildContext context) {
    return _isZh(context)
        ? '\u8f93\u5165\u7fa4\u7ec4\u63cf\u8ff0\uff08\u5fc5\u586b\uff09'
        : 'Enter group description (required)';
  }

  static String groupTypeTitle(BuildContext context) {
    return _isZh(context) ? '\u7fa4\u7ec4\u7c7b\u578b' : 'Group Type';
  }

  static String dutyRuleTitle(BuildContext context) {
    return _isZh(context) ? '\u503c\u73ed\u89c4\u5219' : 'Duty Rule';
  }

  static String groupTypePublicTitle(BuildContext context) {
    return _isZh(context) ? '\u516c\u5f00\u7fa4' : 'Public Group';
  }

  static String groupTypePublicDesc(BuildContext context) {
    return _isZh(context)
        ? 'Agent \u53ef\u901a\u8fc7\u7fa4\u94fe\u63a5\u76f4\u63a5\u52a0\u5165\uff0c\u65e0\u9700\u5ba1\u6838'
        : 'Agents can join directly via group link, no approval needed';
  }

  static String groupTypePrivateTitle(BuildContext context) {
    return _isZh(context) ? '\u79c1\u5bc6\u7fa4' : 'Private Group';
  }

  static String groupTypePrivateDesc(BuildContext context) {
    return _isZh(context)
        ? '\u5e26\u9080\u8bf7\u7801\u94fe\u63a5\u53ef\u76f4\u63a5\u52a0\u5165\uff1b\u65e0\u7801\u9700\u5ba1\u6838'
        : 'Invite-code links can join directly; no-code requests need approval';
  }

  static String dutyRotationTitle(BuildContext context) {
    return _isZh(context) ? '\u7fa4\u6210\u5458\u8f6e\u6d41\u503c\u73ed' : 'Rotation Duty';
  }

  static String dutyRotationDesc(BuildContext context) {
    return _isZh(context)
        ? '\u6210\u5458\u6309\u987a\u5e8f\u8f6e\u6d41\u62c5\u4efb\u503c\u73ed Agent'
        : 'Members rotate as on-duty agent in sequence';
  }

  static String dutyFixedTitle(BuildContext context) {
    return _isZh(context) ? '\u56fa\u5b9a Agent \u503c\u73ed' : 'Fixed Agent Duty';
  }

  static String dutyFixedDesc(BuildContext context) {
    return _isZh(context)
        ? '\u6307\u5b9a\u56fa\u5b9a Agent \u8d1f\u8d23\u503c\u73ed'
        : 'Assign one fixed on-duty agent';
  }

  static String dutyNoneTitle(BuildContext context) {
    return _isZh(context) ? '\u4e0d\u503c\u73ed' : 'No Duty';
  }

  static String dutyNoneDesc(BuildContext context) {
    return _isZh(context)
        ? '\u5173\u95ed\u503c\u73ed\uff0c\u6d88\u606f\u76f4\u63a5\u5e7f\u64ad\u7ed9\u6240\u6709\u6210\u5458'
        : 'Disable duty, broadcast messages to all members';
  }

  static String createButton(BuildContext context) {
    return _isZh(context) ? '\u521b\u5efa' : 'Create';
  }

  static String creatingButton(BuildContext context) {
    return _isZh(context) ? '\u521b\u5efa\u4e2d...' : 'Creating...';
  }

  static String joinGroupTitle(BuildContext context) {
    return _isZh(context) ? '\u52a0\u5165\u7fa4\u7ec4' : 'Join Group';
  }

  static String groupUrlLabel(BuildContext context) {
    return _isZh(context) ? '\u7fa4\u94fe\u63a5' : 'Group URL';
  }

  static String joinButton(BuildContext context) {
    return _isZh(context) ? '\u52a0\u5165' : 'Join';
  }

  static String groupCreated(BuildContext context) {
    return _isZh(context) ? '\u7fa4\u7ec4\u521b\u5efa\u6210\u529f' : 'Group created';
  }

  static String joinRequestSentWaiting(BuildContext context) {
    return _isZh(context)
        ? '\u5165\u7fa4\u8bf7\u6c42\u5df2\u53d1\u9001\uff0c\u7b49\u5f85\u5ba1\u6279'
        : 'Join request sent, waiting for approval';
  }

  static String joinRequestSent(BuildContext context) {
    return _isZh(context) ? '\u5165\u7fa4\u8bf7\u6c42\u5df2\u53d1\u9001' : 'Join request sent';
  }

  static String joinedGroupSuccessfully(BuildContext context) {
    return _isZh(context) ? '\u5df2\u6210\u529f\u52a0\u5165\u7fa4\u7ec4' : 'Joined group successfully';
  }

  static String joinFailed(BuildContext context, String reason) {
    return _isZh(context) ? '\u52a0\u5165\u5931\u8d25: $reason' : 'Join failed: $reason';
  }

  static String receivedGroupInvite(BuildContext context, String inviter) {
    return _isZh(context)
        ? '\u6536\u5230\u6765\u81ea $inviter \u7684\u7fa4\u9080\u8bf7'
        : 'Received group invite from $inviter';
  }

  static String joinApprovedForGroup(BuildContext context, String groupId) {
    return _isZh(context)
        ? '\u7fa4\u7ec4 $groupId \u52a0\u5165\u5ba1\u6279\u5df2\u901a\u8fc7'
        : 'Join approved for group $groupId';
  }

  static String connectToPeerTitle(BuildContext context) {
    return _isZh(context) ? '\u8fde\u63a5\u5230\u5bf9\u65b9' : 'Connect to Peer';
  }

  static String peerAidLabel(BuildContext context) {
    return _isZh(context) ? '\u5bf9\u65b9 AID' : 'Peer AID';
  }

  static String peerAidHint(BuildContext context) {
    return _isZh(context) ? '\u4f8b\u5982: alice.aid.pub' : 'e.g. alice.aid.pub';
  }

  static String connectButton(BuildContext context) {
    return _isZh(context) ? '\u8fde\u63a5' : 'Connect';
  }

  static String createSessionFailed(BuildContext context, String reason) {
    return _isZh(context) ? '\u521b\u5efa\u4f1a\u8bdd\u5931\u8d25: $reason' : 'Failed to create session: $reason';
  }

  static String leaveGroupTitle(BuildContext context) {
    return _isZh(context) ? '\u9000\u51fa\u7fa4\u7ec4' : 'Leave Group';
  }

  static String leaveGroupConfirm(BuildContext context) {
    return _isZh(context)
        ? '\u786e\u5b9a\u8981\u9000\u51fa\u8be5\u7fa4\u7ec4\u5417\uff1f'
        : 'Are you sure you want to leave this group?';
  }

  static String leftGroup(BuildContext context) {
    return _isZh(context) ? '\u5df2\u9000\u51fa\u7fa4\u7ec4' : 'Left group';
  }

  static String groupDisbanded(BuildContext context) {
    return _isZh(context) ? '\u5df2\u89e3\u6563' : 'Disbanded';
  }

  static String groupInactive(BuildContext context) {
    return _isZh(context) ? '\u5df2\u9000\u51fa' : 'Inactive';
  }

  static String cannotSendGroupDisbanded(BuildContext context) {
    return _isZh(context) ? '\u7fa4\u7ec4\u5df2\u89e3\u6563\uff0c\u65e0\u6cd5\u53d1\u9001\u6d88\u606f' : 'Group disbanded, cannot send messages';
  }

  static String leaveButton(BuildContext context) {
    return _isZh(context) ? '\u9000\u51fa' : 'Leave';
  }

  static String deleteChatTitle(BuildContext context) {
    return _isZh(context) ? '\u5220\u9664\u804a\u5929' : 'Delete Chat';
  }

  static String deleteChatConfirm(BuildContext context) {
    return _isZh(context)
        ? '\u786e\u5b9a\u5220\u9664\u8be5\u804a\u5929\u4f1a\u8bdd\u5417\uff1f'
        : 'Are you sure you want to delete this chat session?';
  }

  static String deleteButton(BuildContext context) {
    return _isZh(context) ? '\u5220\u9664' : 'Delete';
  }

  static String groupRefreshTooltip(BuildContext context) {
    return _isZh(context) ? '\u5237\u65b0\u6d88\u606f' : 'Refresh Messages';
  }

  static String groupMembersTooltip(BuildContext context) {
    return _isZh(context) ? '\u7fa4\u6210\u5458' : 'Group Members';
  }

  static String groupNoMessages(BuildContext context) {
    return _isZh(context)
        ? '\u6682\u65e0\u6d88\u606f\uff0c\u53d1\u9001\u7b2c\u4e00\u6761\u5427\uff01'
        : 'No messages yet. Send the first one!';
  }

  static String groupInputHint(BuildContext context) {
    return _isZh(context) ? '\u8f93\u5165\u6d88\u606f...' : 'Type a message...';
  }

  static String groupMembersCount(BuildContext context, int count) {
    return _isZh(context) ? '\u6210\u5458 ($count)' : 'Members ($count)';
  }

  static String close(BuildContext context) {
    return _isZh(context) ? '\u5173\u95ed' : 'Close';
  }

  static String sendFailed(BuildContext context, String reason) {
    return _isZh(context)
        ? '\u53d1\u9001\u5931\u8d25: $reason'
        : 'Send failed: $reason';
  }

  static String groupIdCopied(BuildContext context) {
    return _isZh(context) ? '群ID已复制' : 'Group ID copied';
  }

  static String groupLinkCopied(BuildContext context) {
    return _isZh(context) ? '群链接已复制' : 'Group link copied';
  }

  static String copyGroupLink(BuildContext context) {
    return _isZh(context) ? '复制群链接' : 'Copy Group Link';
  }

  static String copyWithInviteCode(BuildContext context) {
    return _isZh(context) ? '带邀请码复制' : 'Copy with invite code';
  }

  static String copyWithoutInviteCode(BuildContext context) {
    return _isZh(context) ? '不带邀请码复制' : 'Copy without invite code';
  }

  static String shareGroupMessage(BuildContext context, String myAid, String groupName, String groupLink) {
    return _isZh(context)
        ? '我加入了Agent互联网，访问https://$myAid查看我的个人信息，快来加入$groupName[$groupLink]一起聊天吧'
        : 'I joined the Agent Internet, visit https://$myAid to see my profile. Come join $groupName[$groupLink] and chat together!';
  }

  static String onlyOwnerCanCopyLink(BuildContext context) {
    return _isZh(context) ? '仅群主可以复制群链接' : 'Only the group owner can copy the group link';
  }

  static String invalidGroupUrl(BuildContext context) {
    return _isZh(context) ? '无效的群链接' : 'Invalid group URL';
  }

  static String offlineReconnecting(BuildContext context) {
    return _isZh(context) ? '离线中，正在重连...' : 'Offline, reconnecting...';
  }

  static bool _isZh(BuildContext context) {
    return AppLanguageScope.of(context).language == AppLanguage.zh;
  }
}
