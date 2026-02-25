import 'dart:convert';

import 'package:flutter/material.dart';

import '../i18n/app_texts.dart';
import '../services/agentcp_service.dart';

class CreateGroupPage extends StatefulWidget {
  const CreateGroupPage({super.key});

  @override
  State<CreateGroupPage> createState() => _CreateGroupPageState();
}

class _CreateGroupPageState extends State<CreateGroupPage> {
  final _nameCtrl = TextEditingController();
  final _descCtrl = TextEditingController();

  String _visibility = 'public';
  String _dutyRule = 'rotation';
  bool _isCreating = false;

  @override
  void dispose() {
    _nameCtrl.dispose();
    _descCtrl.dispose();
    super.dispose();
  }

  Future<void> _onCreate() async {
    final name = _nameCtrl.text.trim();
    final desc = _descCtrl.text.trim();

    if (name.isEmpty) {
      _showSnack(AppTexts.createGroupNameRequired(context));
      return;
    }
    if (desc.isEmpty) {
      _showSnack(AppTexts.createGroupDescRequired(context));
      return;
    }

    setState(() => _isCreating = true);

    final result = await AgentCPService.groupCreateGroup(
      name: name,
      description: desc,
      visibility: _visibility,
      tags: jsonEncode([_dutyRule]),
    );

    if (!mounted) return;
    setState(() => _isCreating = false);

    if (result['success'] == true) {
      final groupId = result['groupId'] ?? '';
      if (groupId.isNotEmpty) {
        await AgentCPService.joinGroupSession(groupId);
      }
      if (mounted) {
        Navigator.pop(context, true);
      }
    } else {
      _showSnack(AppTexts.createGroupFailed(context, '${result['message']}'));
    }
  }

  void _showSnack(String msg) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(msg), duration: const Duration(seconds: 2)),
    );
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () => FocusManager.instance.primaryFocus?.unfocus(),
      child: Scaffold(
        appBar: AppBar(
          title: Text(AppTexts.createGroupPageTitle(context)),
          backgroundColor: Theme.of(context).colorScheme.inversePrimary,
        ),
        body: SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 90),
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 760),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _buildTextField(
                      controller: _nameCtrl,
                      label: AppTexts.createGroupNameHint(context),
                      icon: Icons.group,
                    ),
                    const SizedBox(height: 12),
                    _buildTextField(
                      controller: _descCtrl,
                      label: AppTexts.createGroupDescHint(context),
                      icon: Icons.description,
                      maxLines: 3,
                    ),
                    const SizedBox(height: 20),
                    _buildSectionTitle(AppTexts.groupTypeTitle(context)),
                    const SizedBox(height: 10),
                    Wrap(
                      spacing: 10,
                      runSpacing: 10,
                      children: [
                        _buildChoiceChip(
                          selected: _visibility == 'public',
                          icon: Icons.public,
                          title: AppTexts.groupTypePublicTitle(context),
                          subtitle: AppTexts.groupTypePublicDesc(context),
                          onTap: () => setState(() => _visibility = 'public'),
                        ),
                        _buildChoiceChip(
                          selected: _visibility == 'private',
                          icon: Icons.lock,
                          title: AppTexts.groupTypePrivateTitle(context),
                          subtitle: AppTexts.groupTypePrivateDesc(context),
                          onTap: () => setState(() => _visibility = 'private'),
                        ),
                      ],
                    ),
                    const SizedBox(height: 20),
                    _buildSectionTitle(AppTexts.dutyRuleTitle(context)),
                    const SizedBox(height: 10),
                    _buildDutyCard(
                      value: 'rotation',
                      icon: Icons.swap_horiz,
                      title: AppTexts.dutyRotationTitle(context),
                      subtitle: AppTexts.dutyRotationDesc(context),
                    ),
                    const SizedBox(height: 10),
                    _buildDutyCard(
                      value: 'fixed',
                      icon: Icons.star,
                      title: AppTexts.dutyFixedTitle(context),
                      subtitle: AppTexts.dutyFixedDesc(context),
                    ),
                    const SizedBox(height: 10),
                    _buildDutyCard(
                      value: 'none',
                      icon: Icons.remove_circle_outline,
                      title: AppTexts.dutyNoneTitle(context),
                      subtitle: AppTexts.dutyNoneDesc(context),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
        bottomNavigationBar: SafeArea(
          top: false,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
            child: Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: _isCreating ? null : () => Navigator.pop(context),
                    child: Text(AppTexts.cancel(context)),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: FilledButton(
                    onPressed: _isCreating ? null : _onCreate,
                    child: _isCreating
                        ? Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              const SizedBox(
                                width: 16,
                                height: 16,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              ),
                              const SizedBox(width: 8),
                              Text(AppTexts.creatingButton(context)),
                            ],
                          )
                        : Text(AppTexts.createButton(context)),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildTextField({
    required TextEditingController controller,
    required String label,
    required IconData icon,
    int maxLines = 1,
  }) {
    return TextField(
      controller: controller,
      maxLines: maxLines,
      decoration: InputDecoration(
        labelText: label,
        prefixIcon: Icon(icon),
        border: const OutlineInputBorder(),
      ),
    );
  }

  Widget _buildSectionTitle(String text) {
    return Text(
      text,
      style: const TextStyle(
        fontSize: 15,
        fontWeight: FontWeight.w600,
      ),
    );
  }

  Widget _buildChoiceChip({
    required bool selected,
    required IconData icon,
    required String title,
    required String subtitle,
    required VoidCallback onTap,
  }) {
    return SizedBox(
      width: 360,
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: selected
                  ? Theme.of(context).colorScheme.primary
                  : Colors.grey.shade300,
              width: selected ? 2 : 1,
            ),
            color: selected
                ? Theme.of(context).colorScheme.primary.withValues(alpha: 0.06)
                : Colors.white,
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(icon, size: 22),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title, style: const TextStyle(fontWeight: FontWeight.w600)),
                    const SizedBox(height: 2),
                    Text(
                      subtitle,
                      style: TextStyle(fontSize: 12, color: Colors.grey.shade700),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildDutyCard({
    required String value,
    required IconData icon,
    required String title,
    required String subtitle,
  }) {
    final selected = _dutyRule == value;
    return InkWell(
      borderRadius: BorderRadius.circular(12),
      onTap: () => setState(() => _dutyRule = value),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: selected
                ? Theme.of(context).colorScheme.primary
                : Colors.grey.shade300,
            width: selected ? 2 : 1,
          ),
          color: selected
              ? Theme.of(context).colorScheme.primary.withValues(alpha: 0.06)
              : Colors.white,
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, size: 22),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: const TextStyle(fontWeight: FontWeight.w600)),
                  const SizedBox(height: 2),
                  Text(
                    subtitle,
                    style: TextStyle(fontSize: 12, color: Colors.grey.shade700),
                  ),
                ],
              ),
            ),
            Radio<String>(
              value: value,
              groupValue: _dutyRule,
              onChanged: (_) => setState(() => _dutyRule = value),
            ),
          ],
        ),
      ),
    );
  }
}
