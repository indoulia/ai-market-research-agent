import 'package:flutter/material.dart';

import '../tokens/mra_colors.dart';
import '../tokens/mra_spacing.dart';
import '../tokens/mra_typography.dart';

enum MraPriceBadgeKind { target, stopLoss }

/// EPIC-M1.133 — target/stop-loss badge. Always renders a text label
/// ("Target"/"Stop loss") beside the number, never relying on color alone.
class TargetSlBadge extends StatelessWidget {
  final MraPriceBadgeKind kind;
  final String formattedPrice;

  const TargetSlBadge({
    super.key,
    required this.kind,
    required this.formattedPrice,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = MraColorScheme.of(context);
    final isTarget = kind == MraPriceBadgeKind.target;
    final color = isTarget ? scheme.positive : scheme.error;
    final background = isTarget
        ? scheme.positiveContainer
        : scheme.errorContainer;
    final label = isTarget ? 'Target' : 'Stop loss';
    final icon = isTarget ? Icons.flag_outlined : Icons.shield_outlined;

    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: MraSpacing.sm,
        vertical: MraSpacing.xs,
      ),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: color),
          const SizedBox(width: MraSpacing.xs),
          Text(
            '$label ',
            style: theme.textTheme.labelSmall?.copyWith(color: color),
          ),
          Text(
            formattedPrice,
            style: MraTypography.numeric(
              theme.textTheme.labelSmall!.copyWith(color: color),
            ),
          ),
        ],
      ),
    );
  }
}
