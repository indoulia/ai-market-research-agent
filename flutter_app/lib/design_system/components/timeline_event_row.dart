import 'package:flutter/material.dart';

import '../tokens/mra_colors.dart';
import '../tokens/mra_spacing.dart';

enum MraTimelineTone { neutral, positive, warning, error }

/// EPIC-M1.133 — single row in an event/history timeline (used by
/// recommendation history and event feeds).
class TimelineEventRow extends StatelessWidget {
  final String title;
  final String? subtitle;
  final String timestampLabel;
  final MraTimelineTone tone;
  final bool isLast;

  const TimelineEventRow({
    super.key,
    required this.title,
    required this.timestampLabel,
    this.subtitle,
    this.tone = MraTimelineTone.neutral,
    this.isLast = false,
  });

  Color _dotColor(MraColorScheme scheme, ColorScheme material) {
    switch (tone) {
      case MraTimelineTone.positive:
        return scheme.positive;
      case MraTimelineTone.warning:
        return scheme.warning;
      case MraTimelineTone.error:
        return scheme.error;
      case MraTimelineTone.neutral:
        return material.onSurfaceVariant;
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = MraColorScheme.of(context);
    final dotColor = _dotColor(scheme, theme.colorScheme);

    return Semantics(
      label: '$title, $timestampLabel${subtitle != null ? ', $subtitle' : ''}',
      // IntrinsicHeight gives the Row a bounded height so the connector
      // Column's Expanded can fill "the rest of this row" rather than an
      // unbounded height (this widget is used inside scrolling lists).
      child: IntrinsicHeight(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Column(
              children: [
                Container(
                  width: 10,
                  height: 10,
                  margin: const EdgeInsets.only(top: 4),
                  decoration: BoxDecoration(
                    color: dotColor,
                    shape: BoxShape.circle,
                  ),
                ),
                if (!isLast)
                  Expanded(
                    child: Container(
                      width: 2,
                      margin: const EdgeInsets.symmetric(vertical: 2),
                      color: theme.colorScheme.outlineVariant,
                    ),
                  ),
              ],
            ),
            const SizedBox(width: MraSpacing.md),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.only(bottom: MraSpacing.lg),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(title, style: theme.textTheme.bodyMedium),
                        ),
                        Text(
                          timestampLabel,
                          style: theme.textTheme.labelSmall?.copyWith(
                            color: theme.colorScheme.onSurfaceVariant,
                          ),
                        ),
                      ],
                    ),
                    if (subtitle != null) ...[
                      const SizedBox(height: MraSpacing.xs),
                      Text(
                        subtitle!,
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
