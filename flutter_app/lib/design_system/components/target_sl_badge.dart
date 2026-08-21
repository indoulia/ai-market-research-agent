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

    // EPIC-M1.143: one combined semantics node ("Target 176.50") rather
    // than letting a screen reader step through the icon and two Text
    // widgets as separate stops.
    return Semantics(
      label: '$label $formattedPrice',
      child: ExcludeSemantics(
        child: Container(
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
              // EPIC-M1.143: one Flexible+ellipsis span rather than two
              // unconstrained Text widgets — at extreme text-scale/narrow-
              // width combinations the two independent Texts could overflow
              // this Row (which has no available-width ceiling of its own
              // beyond what its parent Wrap/Column provides).
              Flexible(
                child: Text.rich(
                  TextSpan(
                    children: [
                      TextSpan(
                        text: '$label ',
                        style: theme.textTheme.labelSmall?.copyWith(
                          color: color,
                        ),
                      ),
                      TextSpan(
                        text: formattedPrice,
                        style: MraTypography.numeric(
                          theme.textTheme.labelSmall!.copyWith(color: color),
                        ),
                      ),
                    ],
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
