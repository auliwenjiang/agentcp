import 'package:flutter/material.dart';
import '../services/agent_info_service.dart';

/// WeChat-style composite group avatar.
/// Arranges up to 9 member avatars in a grid layout.
class GroupAvatarWidget extends StatelessWidget {
  final List<String> memberAids;
  final double size;

  const GroupAvatarWidget({
    super.key,
    required this.memberAids,
    this.size = 48,
  });

  @override
  Widget build(BuildContext context) {
    if (memberAids.isEmpty) {
      return _placeholder();
    }

    final aids = memberAids.length > 9 ? memberAids.sublist(0, 9) : memberAids;
    final rows = _buildRows(aids.length);

    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: Colors.grey[300],
        borderRadius: BorderRadius.circular(size * 0.16),
      ),
      clipBehavior: Clip.antiAlias,
      child: Padding(
        padding: EdgeInsets.all(size * 0.06),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: _buildRowWidgets(rows, aids),
        ),
      ),
    );
  }

  Widget _placeholder() {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: Colors.deepPurple,
        borderRadius: BorderRadius.circular(size * 0.16),
      ),
      child: Icon(Icons.group, color: Colors.white, size: size * 0.5),
    );
  }

  /// Returns row sizes based on member count, matching WeChat layout.
  /// e.g. 5 members => [2, 3] (top row 2, bottom row 3)
  List<int> _buildRows(int count) {
    switch (count) {
      case 1: return [1];
      case 2: return [2];
      case 3: return [1, 2];
      case 4: return [2, 2];
      case 5: return [2, 3];
      case 6: return [3, 3];
      case 7: return [1, 3, 3];
      case 8: return [2, 3, 3];
      case 9: return [3, 3, 3];
      default: return [1];
    }
  }

  List<Widget> _buildRowWidgets(List<int> rows, List<String> aids) {
    final gap = size * 0.04;
    final padding = size * 0.06;
    final totalGapV = gap * (rows.length - 1);
    final availableH = size - padding * 2 - totalGapV;
    final cellH = availableH / rows.length;

    final widgets = <Widget>[];
    int aidIndex = 0;

    for (int r = 0; r < rows.length; r++) {
      final rowCount = rows[r];
      final totalGapH = gap * (rowCount - 1);
      final availableW = size - padding * 2 - totalGapH;
      final cellW = availableW / rowCount;
      final cellSize = cellH < cellW ? cellH : cellW;

      final rowChildren = <Widget>[];
      for (int c = 0; c < rowCount; c++) {
        if (aidIndex < aids.length) {
          rowChildren.add(_AvatarCell(aid: aids[aidIndex], size: cellSize));
          aidIndex++;
        }
        if (c < rowCount - 1) {
          rowChildren.add(SizedBox(width: gap));
        }
      }

      if (r > 0) widgets.add(SizedBox(height: gap));
      widgets.add(Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: rowChildren,
      ));
    }

    return widgets;
  }
}

class _AvatarCell extends StatelessWidget {
  final String aid;
  final double size;

  const _AvatarCell({required this.aid, required this.size});

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<AgentInfo>(
      future: AgentInfoService().getAgentInfo(aid),
      builder: (context, snapshot) {
        final info = snapshot.data;
        final path = AgentInfoService().getAvatarAssetPath(info?.type ?? '');
        return ClipOval(
          child: Image.asset(
            path,
            width: size,
            height: size,
            fit: BoxFit.cover,
          ),
        );
      },
    );
  }
}