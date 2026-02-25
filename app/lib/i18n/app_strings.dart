import 'package:flutter/widgets.dart';

import 'app_language.dart';

class AppStrings {
  static String identityManagementTitle(BuildContext context) {
    return _isZh(context) ? 'ACP身份管理' : 'ACP Identity';
  }

  static String languageMenuLabel(BuildContext context) {
    return _isZh(context) ? '语言' : 'Language';
  }

  static String languageDialogTitle(BuildContext context) {
    return _isZh(context) ? '切换语言' : 'Switch Language';
  }

  static String languageOptionEnglish(BuildContext context) {
    return _isZh(context) ? '英文' : 'English';
  }

  static String languageOptionChinese(BuildContext context) {
    return _isZh(context) ? '中文' : 'Chinese';
  }

  static String cancel(BuildContext context) {
    return _isZh(context) ? '取消' : 'Cancel';
  }

  static String save(BuildContext context) {
    return _isZh(context) ? '保存' : 'Save';
  }

  static String languageChangedToEnglish(BuildContext context) {
    return _isZh(context) ? '已切换为英文' : 'Switched to English';
  }

  static String languageChangedToChinese(BuildContext context) {
    return _isZh(context) ? '已切换为中文' : 'Switched to Chinese';
  }

  static String languagePersistedTip(BuildContext context, String path) {
    if (path.isEmpty) {
      return _isZh(context) ? '语言设置已保存' : 'Language preference saved';
    }
    return _isZh(context)
        ? '语言设置已保存: $path'
        : 'Language preference saved: $path';
  }

  static String chatsTitle(BuildContext context) {
    return _isZh(context) ? '聊天' : 'Chats';
  }

  static String forceRefreshTooltip(BuildContext context) {
    return _isZh(context) ? '强制刷新' : 'Force refresh';
  }

  static String identityManagementEntry(BuildContext context) {
    return _isZh(context) ? '身份管理' : 'Identity Management';
  }

  static String appNameSubtitle(BuildContext context) {
    return 'AgentCP App';
  }

  static String noChatsYet(BuildContext context) {
    return _isZh(context) ? '暂无聊天' : 'No chats yet.';
  }

  static String startNewChat(BuildContext context) {
    return _isZh(context) ? '开始新聊天' : 'Start a new chat';
  }

  static String groupRefreshTooltip(BuildContext context) {
    return _isZh(context) ? '刷新消息' : 'Refresh Messages';
  }

  static String groupMembersTooltip(BuildContext context) {
    return _isZh(context) ? '群成员' : 'Group Members';
  }

  static String groupNoMessages(BuildContext context) {
    return _isZh(context) ? '暂无消息，发送第一条吧！' : 'No messages yet. Send the first one!';
  }

  static String groupInputHint(BuildContext context) {
    return _isZh(context) ? '输入消息...' : 'Type a message...';
  }

  static String groupMembersCount(BuildContext context, int count) {
    return _isZh(context) ? '成员 ($count)' : 'Members ($count)';
  }

  static String close(BuildContext context) {
    return _isZh(context) ? '关闭' : 'Close';
  }

  static String sendFailed(BuildContext context, String reason) {
    return _isZh(context) ? '发送失败: $reason' : 'Send failed: $reason';
  }

  static bool _isZh(BuildContext context) {
    return AppLanguageScope.of(context).language == AppLanguage.zh;
  }
}
