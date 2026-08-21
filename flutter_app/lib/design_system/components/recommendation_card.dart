import 'package:flutter/material.dart';

import '../tokens/mra_colors.dart';
import '../tokens/mra_spacing.dart';
import '../tokens/mra_typography.dart';
import 'mra_card.dart';
import 'score_indicator.dart';
import 'sparkline_chart.dart';
import 'target_sl_badge.dart';

/// Presentation-only view model. Screens map their API DTO into this shape;
/// this widget never talks to a repository/API directly (EPIC-M1.133 is
/// UI-only and must not invent data access).
class RecommendationCardData {
  final String symbol;

  /// Null when the reference-data company name isn't available yet — the
  /// card omits the subtitle line rather than showing an empty one.
  final String? companyName;

  /// Null when no current price is available (e.g. a stale/unpriced
  /// symbol) — the card shows "—" and omits the change-percent row rather
  /// than fabricating a value.
  final double? currentPrice;
  final double? changePercent;
  final int horizonDays;
  final double targetPrice;
  final double stopLossPrice;
  final double upsidePercent;
  final double score;
  final double confidence;

  /// Null when no trust score has been computed yet — rendered as an
  /// explicit "N/A" rather than a misleadingly low score.
  final double? trust;
  final List<double> priceHistory;
  final String lastUpdatedLabel;

  const RecommendationCardData({
    required this.symbol,
    required this.companyName,
    required this.currentPrice,
    required this.changePercent,
    required this.horizonDays,
    required this.targetPrice,
    required this.stopLossPrice,
    required this.upsidePercent,
    required this.score,
    required this.confidence,
    required this.trust,
    required this.priceHistory,
    required this.lastUpdatedLabel,
  });
}

/// EPIC-M1.133 — shared recommendation card. Real recommendation data
/// wiring happens in EPIC-M1.136 against the M1.135 API; this component
/// only defines presentation.
class RecommendationCard extends StatelessWidget {
  final RecommendationCardData data;
  final VoidCallback? onTap;

  const RecommendationCard({super.key, required this.data, this.onTap});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = MraColorScheme.of(context);
    final changePercent = data.changePercent;
    final isUp = (changePercent ?? 0) >= 0;
    final changeColor = isUp ? scheme.marketUp : scheme.marketDown;

    return MraCard(
      onTap: onTap,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(data.symbol, style: theme.textTheme.titleMedium),
                    if (data.companyName != null)
                      Text(
                        data.companyName!,
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                  ],
                ),
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    data.currentPrice?.toStringAsFixed(2) ?? '—',
                    style: MraTypography.numeric(theme.textTheme.titleMedium!),
                  ),
                  if (changePercent != null)
                    Row(
                      children: [
                        Icon(
                          isUp ? Icons.arrow_drop_up : Icons.arrow_drop_down,
                          size: 18,
                          color: changeColor,
                        ),
                        Text(
                          '${changePercent.abs().toStringAsFixed(2)}%',
                          style: MraTypography.numeric(
                            theme.textTheme.labelMedium!.copyWith(
                              color: changeColor,
                            ),
                          ),
                        ),
                      ],
                    ),
                ],
              ),
            ],
          ),
          const SizedBox(height: MraSpacing.md),
          SparklineChart(values: data.priceHistory, color: changeColor),
          const SizedBox(height: MraSpacing.md),
          Wrap(
            spacing: MraSpacing.sm,
            runSpacing: MraSpacing.sm,
            children: [
              TargetSlBadge(
                kind: MraPriceBadgeKind.target,
                formattedPrice: data.targetPrice.toStringAsFixed(2),
              ),
              TargetSlBadge(
                kind: MraPriceBadgeKind.stopLoss,
                formattedPrice: data.stopLossPrice.toStringAsFixed(2),
              ),
            ],
          ),
          const SizedBox(height: MraSpacing.md),
          Row(
            children: [
              Expanded(
                child: Text(
                  '${data.horizonDays}D horizon · +${data.upsidePercent.toStringAsFixed(1)}% upside',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              const SizedBox(width: MraSpacing.sm),
              Text(
                data.lastUpdatedLabel,
                style: theme.textTheme.labelSmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ],
          ),
          const SizedBox(height: MraSpacing.md),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            children: [
              ScoreIndicator(kind: MraScoreKind.score, value0to100: data.score),
              ScoreIndicator(
                kind: MraScoreKind.confidence,
                value0to100: data.confidence,
              ),
              if (data.trust != null)
                ScoreIndicator(
                  kind: MraScoreKind.trust,
                  value0to100: data.trust!,
                )
              else
                _UnavailableTrustIndicator(size: 44),
            ],
          ),
        ],
      ),
    );
  }
}

/// Matches [ScoreIndicator]'s circle-plus-label footprint so the row's
/// alignment doesn't shift when trust data is absent, but renders an
/// explicit "N/A" rather than a fabricated score.
class _UnavailableTrustIndicator extends StatelessWidget {
  final double size;

  const _UnavailableTrustIndicator({required this.size});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Semantics(
      label: 'Trust unavailable',
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          SizedBox(
            width: size,
            height: size,
            child: DecoratedBox(
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                border: Border.all(color: theme.colorScheme.outlineVariant),
              ),
              child: Center(
                child: Text(
                  'N/A',
                  style: theme.textTheme.labelSmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(height: MraSpacing.xs),
          Text('Trust', style: theme.textTheme.labelSmall),
        ],
      ),
    );
  }
}
