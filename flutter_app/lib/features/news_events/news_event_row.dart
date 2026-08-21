import 'package:flutter/material.dart';

import '../../design_system/design_system.dart';
import 'news_events_repository.dart';

/// EPIC-M1.140 — one row in the News & Events chronological stream. Reuses
/// EPIC-M1.133's `NewsCard`, adding a materiality badge and a symbol chip
/// so a dense feed still shows what moved.
///
/// EPIC-M3.5 added a leading icon distinguishing news from corporate-action
/// entries, a materiality-driven chip tone (HIGH reads as a warning, not
/// just an info-colored label) and affected-symbol chips.
class NewsEventRowCard extends StatelessWidget {
  final FeedEntry entry;
  final VoidCallback? onTap;

  const NewsEventRowCard({super.key, required this.entry, this.onTap});

  @override
  Widget build(BuildContext context) {
    return NewsCard(
      headline: entry.headline,
      source: '${entry.symbol} · ${entry.source}',
      publishedLabel: _relativeLabel(entry.timestamp),
      tag: entry.materiality,
      tagTone: entry.materiality == 'HIGH'
          ? MraChipTone.warning
          : MraChipTone.info,
      icon: entry.kind == FeedEntryKind.corporateAction
          ? Icons.event_note_outlined
          : Icons.article_outlined,
      affectedSymbols: entry.affectedSecurities,
      onTap: onTap,
    );
  }

  static String _relativeLabel(DateTime time) {
    final diff = DateTime.now().difference(time);
    if (diff.inHours < 24) return '${diff.inHours}h ago';
    return '${diff.inDays}d ago';
  }
}
