import 'package:flutter/material.dart';

import '../tokens/mra_spacing.dart';
import 'mra_card.dart';
import 'mra_chip.dart';

/// EPIC-M1.133 — compact news/event card used on market/news screens.
class NewsCard extends StatelessWidget {
  final String headline;
  final String source;
  final String publishedLabel;
  final String? tag;
  final VoidCallback? onTap;

  const NewsCard({
    super.key,
    required this.headline,
    required this.source,
    required this.publishedLabel,
    this.tag,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return MraCard(
      onTap: onTap,
      padding: const EdgeInsets.all(MraSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          if (tag != null) ...[
            MraChip(label: tag!, tone: MraChipTone.info),
            const SizedBox(height: MraSpacing.sm),
          ],
          Text(
            headline,
            style: theme.textTheme.bodyLarge,
            maxLines: 3,
            overflow: TextOverflow.ellipsis,
          ),
          const SizedBox(height: MraSpacing.sm),
          Text(
            '$source · $publishedLabel',
            style: theme.textTheme.labelSmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ],
      ),
    );
  }
}
