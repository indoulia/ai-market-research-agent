import 'package:flutter/material.dart';

import '../tokens/mra_spacing.dart';

/// EPIC-M1.133 — the single card container every dense-content surface
/// (KPI cards, recommendation cards, news cards) is built on top of, so
/// elevation/border/radius stay consistent everywhere.
class MraCard extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry padding;
  final VoidCallback? onTap;
  final bool selected;

  const MraCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(MraSpacing.lg),
    this.onTap,
    this.selected = false,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cardTheme = theme.cardTheme;
    final shape = cardTheme.shape as RoundedRectangleBorder?;

    final border = selected
        ? shape?.copyWith(
            side: BorderSide(color: theme.colorScheme.primary, width: 1.5),
          )
        : shape;

    return Material(
      color: cardTheme.color,
      shape: border,
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        customBorder: border,
        child: Padding(padding: padding, child: child),
      ),
    );
  }
}
