import 'package:flutter/material.dart';

/// EPIC-M1.133 — shared tab bar wrapper so tab styling is consistent and
/// callers only supply labels + an index callback.
class MraTabBar extends StatelessWidget implements PreferredSizeWidget {
  final List<String> labels;
  final TabController controller;

  const MraTabBar({super.key, required this.labels, required this.controller});

  @override
  Size get preferredSize => const Size.fromHeight(48);

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return TabBar(
      controller: controller,
      isScrollable: true,
      tabAlignment: TabAlignment.start,
      labelStyle: theme.textTheme.labelLarge,
      unselectedLabelStyle: theme.textTheme.labelLarge?.copyWith(
        color: theme.colorScheme.onSurfaceVariant,
      ),
      tabs: labels.map((l) => Tab(text: l)).toList(),
    );
  }
}
