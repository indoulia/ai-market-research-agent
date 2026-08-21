import 'package:flutter/material.dart';

import '../../design_system/design_system.dart';
import 'discovery_item.dart';

/// EPIC-M1.140 / EPIC-M3.6 — one discovery candidate. Feature-local (not
/// promoted to the shared design system) since its shape (discovery
/// reasons/sources, sector/industry, lifecycle stage) is specific to this
/// screen.
class DiscoveryCard extends StatelessWidget {
  final DiscoveryItem item;
  final VoidCallback? onTap;

  const DiscoveryCard({super.key, required this.item, this.onTap});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return MraCard(
      onTap: onTap,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(item.symbol, style: theme.textTheme.titleMedium),
                    if (item.companyName != null)
                      Text(
                        item.companyName!,
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                  ],
                ),
              ),
              _LifecycleChip(stage: item.lifecycleStage),
            ],
          ),
          const SizedBox(height: MraSpacing.sm),
          Text(
            '${item.sector} · ${item.industry} · ${item.marketCapBucket}',
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
          if (item.suppressionReason != null) ...[
            const SizedBox(height: MraSpacing.sm),
            // EPIC-M3.6: the reason a candidate did not qualify/publish --
            // never a bearish call, just why the positive bar wasn't met.
            Text(
              'Not selected: ${item.suppressionReason!.replaceAll('_', ' ').toLowerCase()}',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
                fontStyle: FontStyle.italic,
              ),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ],
          const SizedBox(height: MraSpacing.md),
          if (item.discoveryReasons.isNotEmpty)
            Wrap(
              spacing: MraSpacing.xs,
              runSpacing: MraSpacing.xs,
              children: item.discoveryReasons
                  .map((r) => MraChip(label: r, tone: MraChipTone.info))
                  .toList(),
            ),
          const SizedBox(height: MraSpacing.md),
          Row(
            children: [
              // EPIC-M1.143: Flexible (not a bare spaceAround Row) — the
              // same unguarded pattern in RecommendationCard overflowed at
              // 2x text scale/narrow width, since ScoreIndicator's label
              // has no width ceiling without one.
              Expanded(
                child: ScoreIndicator(
                  kind: MraScoreKind.score,
                  value0to100: item.score ?? 0,
                  size: 36,
                ),
              ),
              Expanded(
                child: ScoreIndicator(
                  kind: MraScoreKind.trust,
                  value0to100: item.trustScore ?? 0,
                  size: 36,
                ),
              ),
            ],
          ),
          if (item.discoverySources.isNotEmpty) ...[
            const SizedBox(height: MraSpacing.sm),
            Wrap(
              spacing: MraSpacing.xs,
              runSpacing: MraSpacing.xs,
              children: item.discoverySources
                  .map(
                    (s) => MraChip(
                      label: s.replaceAll('_', ' '),
                      tone: MraChipTone.neutral,
                    ),
                  )
                  .toList(),
            ),
          ],
        ],
      ),
    );
  }
}

class _LifecycleChip extends StatelessWidget {
  final String stage;
  const _LifecycleChip({required this.stage});

  @override
  Widget build(BuildContext context) {
    final tone = switch (stage) {
      'DISCOVERED' => MraChipTone.neutral,
      'SUPPRESSED' => MraChipTone.warning,
      'PUBLISHED' => MraChipTone.positive,
      _ => MraChipTone.info, // QUALIFIED
    };
    return MraChip(label: stage, tone: tone);
  }
}
