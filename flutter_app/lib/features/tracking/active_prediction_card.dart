import 'package:flutter/material.dart';

import '../../design_system/design_system.dart';
import 'active_prediction.dart';

/// EPIC-M3.8 — one compact "active prediction monitoring" row: current
/// price, target/SL distances, a compact progress bar between stop-loss
/// and target, horizon remaining, Trust/freshness and the M1.119-sourced
/// status (never recomputed here from raw price -- see
/// `ActivePredictionStatus`'s own doc comment).
class ActivePredictionCard extends StatelessWidget {
  final ActivePrediction prediction;
  final VoidCallback? onTap;

  const ActivePredictionCard({super.key, required this.prediction, this.onTap});

  static ({String label, MraChipTone tone}) _statusPresentation(String status) {
    switch (status) {
      case ActivePredictionStatus.targetHit:
        return (label: 'Target hit', tone: MraChipTone.positive);
      case ActivePredictionStatus.stopLossHit:
        return (label: 'Stop-loss hit', tone: MraChipTone.error);
      case ActivePredictionStatus.horizonExpired:
        return (label: 'Horizon expired', tone: MraChipTone.neutral);
      case ActivePredictionStatus.invalidated:
        return (label: 'Invalidated', tone: MraChipTone.warning);
      case ActivePredictionStatus.dataUnresolved:
        return (label: 'Price data stale', tone: MraChipTone.warning);
      default:
        return (label: 'Active', tone: MraChipTone.info);
    }
  }

  static String _fmtPrice(double? v) => v == null ? '—' : v.toStringAsFixed(2);

  static String _fmtPct(double? v) =>
      v == null ? '—' : '${v >= 0 ? '+' : ''}${v.toStringAsFixed(1)}%';

  /// Public so the section header ("Updated Xm ago", server-freshness per
  /// the AC) can reuse the identical relative-time formatting.
  static String formatRelativeTime(DateTime? at) {
    if (at == null) return 'unknown';
    final diff = DateTime.now().toUtc().difference(at.toUtc());
    if (diff.inMinutes < 1) return 'just now';
    if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
    if (diff.inHours < 24) return '${diff.inHours}h ago';
    return '${diff.inDays}d ago';
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = MraColorScheme.of(context);
    final status = _statusPresentation(prediction.status);

    return MraCard(
      onTap: onTap,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      prediction.symbol,
                      style: theme.textTheme.titleMedium,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    if (prediction.companyName != null)
                      Text(
                        prediction.companyName!,
                        style: theme.textTheme.labelSmall?.copyWith(
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                  ],
                ),
              ),
              MraChip(label: status.label, tone: status.tone),
            ],
          ),
          const SizedBox(height: MraSpacing.sm),
          Text(
            _fmtPrice(prediction.price),
            style: MraTypography.numeric(theme.textTheme.headlineSmall!),
          ),
          const SizedBox(height: MraSpacing.sm),
          _ProgressBar(prediction: prediction, scheme: scheme),
          const SizedBox(height: MraSpacing.xs),
          Row(
            children: [
              Expanded(
                child: Text(
                  'SL ${_fmtPrice(prediction.stopLoss)} (${_fmtPct(prediction.distanceToStopLossPercent)})',
                  style: theme.textTheme.labelSmall?.copyWith(
                    color: scheme.error,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              const SizedBox(width: MraSpacing.xs),
              Expanded(
                child: Text(
                  'Target ${_fmtPrice(prediction.targetPrice)} (${_fmtPct(prediction.distanceToTargetPercent)})',
                  style: theme.textTheme.labelSmall?.copyWith(
                    color: scheme.positive,
                  ),
                  textAlign: TextAlign.right,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
          const SizedBox(height: MraSpacing.sm),
          Wrap(
            spacing: MraSpacing.md,
            runSpacing: MraSpacing.xs,
            children: [
              Text(
                prediction.remainingTradingDays == null
                    ? '${prediction.horizon}D horizon'
                    : '${prediction.remainingTradingDays}/${prediction.horizon}D remaining',
                style: theme.textTheme.labelSmall,
              ),
              Text(
                prediction.trustScore == null
                    ? 'Trust N/A'
                    : 'Trust ${(prediction.trustScore! * 100).toStringAsFixed(0)}',
                style: theme.textTheme.labelSmall,
              ),
              Text(
                'Priced ${formatRelativeTime(prediction.lastPriceAt)}',
                style: theme.textTheme.labelSmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
              Text(
                prediction.lastRevisionAt == null
                    ? 'No revisions'
                    : 'Revised ${formatRelativeTime(prediction.lastRevisionAt)}',
                style: theme.textTheme.labelSmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

/// Compact visualization of where the current price sits between
/// stop-loss (left edge) and target (right edge). Deliberately a plain
/// filled bar (not a custom painter) to stay cheap to render in a long
/// scrolling list; color reflects the same status tone as the chip so
/// meaning is never conveyed by position alone.
class _ProgressBar extends StatelessWidget {
  final ActivePrediction prediction;
  final MraColorScheme scheme;

  const _ProgressBar({required this.prediction, required this.scheme});

  @override
  Widget build(BuildContext context) {
    final fraction = prediction.progressFraction;
    final color = switch (prediction.status) {
      ActivePredictionStatus.targetHit => scheme.positive,
      ActivePredictionStatus.stopLossHit => scheme.error,
      ActivePredictionStatus.invalidated ||
      ActivePredictionStatus.dataUnresolved => scheme.warning,
      _ => scheme.info,
    };

    return Semantics(
      label:
          'Progress toward target: ${(fraction * 100).toStringAsFixed(0)} percent of the way from stop-loss to target',
      child: ClipRRect(
        borderRadius: BorderRadius.circular(4),
        child: LinearProgressIndicator(
          value: fraction,
          minHeight: 8,
          backgroundColor: Theme.of(context).colorScheme.surfaceContainerHigh,
          valueColor: AlwaysStoppedAnimation(color),
        ),
      ),
    );
  }
}
