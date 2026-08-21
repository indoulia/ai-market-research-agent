import 'package:flutter/material.dart';

import '../../design_system/design_system.dart';
import 'news_events_repository.dart';

/// EPIC-M1.140 — one row in the News & Events chronological stream. Reuses
/// EPIC-M1.133's `NewsCard`, adding a materiality badge and a symbol chip
/// so a dense feed still shows what moved.
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
      onTap: onTap,
    );
  }

  static String _relativeLabel(DateTime time) {
    final diff = DateTime.now().difference(time);
    if (diff.inHours < 24) return '${diff.inHours}h ago';
    return '${diff.inDays}d ago';
  }
}
