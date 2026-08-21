import 'package:flutter/material.dart';

import '../../design_system/design_system.dart';
import 'discovery_item.dart';

/// EPIC-M1.140 — one discovery candidate. Feature-local (not promoted to
/// the shared design system) since its shape (discovery reasons, sector/
/// industry, eligibility) is specific to this screen.
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
              _StatusChip(status: item.status),
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
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: [
              ScoreIndicator(
                kind: MraScoreKind.score,
                value0to100: item.score ?? 0,
                size: 36,
              ),
              ScoreIndicator(
                kind: MraScoreKind.trust,
                value0to100: item.trustScore ?? 0,
                size: 36,
              ),
              if (item.eligibility != null)
                MraChip(
                  label: item.eligibility! ? 'Eligible' : 'Not eligible',
                  tone: item.eligibility!
                      ? MraChipTone.positive
                      : MraChipTone.neutral,
                ),
            ],
          ),
        ],
      ),
    );
  }
}

class _StatusChip extends StatelessWidget {
  final String status;
  const _StatusChip({required this.status});

  @override
  Widget build(BuildContext context) {
    final tone = switch (status) {
      'PENDING_ANALYSIS' => MraChipTone.neutral,
      'NOT_QUALIFIED' => MraChipTone.warning,
      _ => MraChipTone.positive,
    };
    return MraChip(label: status.replaceAll('_', ' '), tone: tone);
  }
}
