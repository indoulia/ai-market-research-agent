import 'package:flutter/material.dart';

import '../tokens/mra_spacing.dart';
import '../tokens/mra_typography.dart';
import 'mra_card.dart';

/// EPIC-M1.133 — compact KPI/stat card used in dashboard header strips
/// (e.g. "Opportunities", "Avg Trust", "Avg Confidence", "Market Regime").
class KpiStatCard extends StatelessWidget {
  final String label;
  final String value;
  final IconData? icon;
  final String? delta;
  final bool deltaPositive;

  const KpiStatCard({
    super.key,
    required this.label,
    required this.value,
    this.icon,
    this.delta,
    this.deltaPositive = true,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final valueStyle = MraTypography.numeric(theme.textTheme.headlineSmall!);

    return MraCard(
      padding: const EdgeInsets.symmetric(
        horizontal: MraSpacing.lg,
        vertical: MraSpacing.md,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              if (icon != null) ...[
                Icon(icon, size: 16, color: theme.colorScheme.onSurfaceVariant),
                const SizedBox(width: MraSpacing.xs),
              ],
              Expanded(
                child: Text(
                  label,
                  style: theme.textTheme.labelMedium?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
          const SizedBox(height: MraSpacing.xs),
          Row(
            crossAxisAlignment: CrossAxisAlignment.baseline,
            textBaseline: TextBaseline.alphabetic,
            children: [
              Flexible(
                child: Text(
                  value,
                  style: valueStyle,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              if (delta != null) ...[
                const SizedBox(width: MraSpacing.xs),
                Text(
                  delta!,
                  style: theme.textTheme.labelSmall?.copyWith(
                    color: deltaPositive
                        ? theme.colorScheme.primary
                        : theme.colorScheme.error,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }
}
