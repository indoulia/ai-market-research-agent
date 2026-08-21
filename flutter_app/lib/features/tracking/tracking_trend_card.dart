import 'package:flutter/material.dart';

import '../../design_system/design_system.dart';
import 'tracking_timeseries.dart';

/// EPIC-M1.148 — one trend chart card (Layout: "Main Trust Score trend
/// chart", "Secondary outcome trend chart"). Reuses the shared
/// [SparklineChart] for the line itself rather than a new chart painter;
/// this card adds the axis min/max labels, a per-metric tooltip (UX Rule:
/// "use tooltips for statistical terms"), and the total evaluated sample
/// count across buckets (UX Rule: "show sample size alongside rates") —
/// none of which the bare sparkline provides on its own.
class TrackingTrendCard extends StatelessWidget {
  final String title;
  final String tooltip;
  final TrackingTimeseries series;
  final String Function(double) formatValue;
  final Color? color;

  const TrackingTrendCard({
    super.key,
    required this.title,
    required this.tooltip,
    required this.series,
    required this.formatValue,
    this.color,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final evaluable = series.points.where((p) => p.value != null).toList();
    final totalSamples = series.points.fold<int>(
      0,
      (sum, p) => sum + p.sampleCount,
    );

    return MraCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  title,
                  style: theme.textTheme.titleMedium,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              Tooltip(
                message: tooltip,
                child: Icon(
                  Icons.info_outline,
                  size: 16,
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ],
          ),
          const SizedBox(height: MraSpacing.xs),
          Text(
            'n=$totalSamples evaluated over ${series.range}',
            style: theme.textTheme.labelSmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(height: MraSpacing.md),
          if (evaluable.length < 2)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: MraSpacing.lg),
              child: Text(
                'Not enough evaluated data yet to plot a trend.',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            )
          else ...[
            SparklineChart(
              values: evaluable.map((p) => p.value!).toList(),
              color: color,
              height: 48,
            ),
            const SizedBox(height: MraSpacing.xs),
            Row(
              children: [
                Expanded(
                  child: Text(
                    formatValue(evaluable.first.value!),
                    style: theme.textTheme.labelSmall,
                  ),
                ),
                Text(
                  formatValue(evaluable.last.value!),
                  style: theme.textTheme.labelSmall,
                  textAlign: TextAlign.end,
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}
