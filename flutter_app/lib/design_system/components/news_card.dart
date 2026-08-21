import 'package:flutter/material.dart';

import '../tokens/mra_spacing.dart';
import 'mra_card.dart';
import 'mra_chip.dart';

/// EPIC-M1.133 — compact news/event card used on market/news screens.
///
/// EPIC-M3.5 added [icon] (a leading glyph distinguishing news from
/// corporate-action cards) and [affectedSymbols] (rendered as chips when
/// more than one security is linked to the same story) — both optional so
/// every pre-existing caller (recommendation timeline, gallery) is
/// unaffected.
class NewsCard extends StatelessWidget {
  final String headline;
  final String source;
  final String publishedLabel;
  final String? tag;
  final MraChipTone tagTone;
  final VoidCallback? onTap;
  final IconData? icon;
  final List<String> affectedSymbols;

  const NewsCard({
    super.key,
    required this.headline,
    required this.source,
    required this.publishedLabel,
    this.tag,
    this.tagTone = MraChipTone.info,
    this.onTap,
    this.icon,
    this.affectedSymbols = const [],
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
            MraChip(label: tag!, tone: tagTone),
            const SizedBox(height: MraSpacing.sm),
          ],
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (icon != null) ...[
                Icon(icon, size: 18, color: theme.colorScheme.onSurfaceVariant),
                const SizedBox(width: MraSpacing.sm),
              ],
              Expanded(
                child: Text(
                  headline,
                  style: theme.textTheme.bodyLarge,
                  maxLines: 3,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
          const SizedBox(height: MraSpacing.sm),
          Text(
            '$source · $publishedLabel',
            style: theme.textTheme.labelSmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
          if (affectedSymbols.length > 1) ...[
            const SizedBox(height: MraSpacing.sm),
            Wrap(
              spacing: MraSpacing.xs,
              runSpacing: MraSpacing.xs,
              children: [
                for (final symbol in affectedSymbols)
                  MraChip(label: symbol, tone: MraChipTone.neutral),
              ],
            ),
          ],
        ],
      ),
    );
  }
}
