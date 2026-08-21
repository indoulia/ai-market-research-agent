import 'package:flutter/material.dart';

import '../../design_system/design_system.dart';
import 'discoveries_repository.dart';
import 'discovery_history_point.dart';
import 'discovery_summary.dart';

/// EPIC-M3.6 — "Discovery summary", "Discovery timeline" and "Discovery
/// effectiveness summary" (UI Scope). A best-effort, self-contained panel:
/// if either request fails it simply omits that section rather than
/// blocking or erroring the whole Discover screen, since this is
/// explanatory/secondary content, not the screen's primary job (browsing
/// candidates).
class DiscoveryPipelinePanel extends StatefulWidget {
  final DiscoveriesRepository repository;

  const DiscoveryPipelinePanel({super.key, required this.repository});

  @override
  State<DiscoveryPipelinePanel> createState() => _DiscoveryPipelinePanelState();
}

class _DiscoveryPipelinePanelState extends State<DiscoveryPipelinePanel> {
  DiscoverySummary? _summary;
  List<DiscoveryHistoryPoint> _history = const [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    DiscoverySummary? summary;
    List<DiscoveryHistoryPoint> history = const [];
    try {
      summary = await widget.repository.fetchSummary();
    } catch (_) {
      // Best-effort: the candidate list above remains fully usable.
    }
    try {
      history = await widget.repository.fetchHistory(days: 14);
    } catch (_) {
      // Best-effort, see above.
    }
    if (!mounted) return;
    setState(() {
      _summary = summary;
      _history = history;
      _loading = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Padding(
        padding: EdgeInsets.symmetric(horizontal: MraSpacing.lg),
        child: MraCard(child: SkeletonCard()),
      );
    }
    final summary = _summary;
    if (summary == null && _history.isEmpty) {
      return const SizedBox.shrink();
    }
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: MraSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (summary != null) _FunnelRow(counts: summary.counts),
          if (_history.isNotEmpty) ...[
            const SizedBox(height: MraSpacing.md),
            _TimelineStrip(points: _history),
          ],
          if (summary != null && summary.effectivenessBySource.isNotEmpty) ...[
            const SizedBox(height: MraSpacing.md),
            _EffectivenessRow(sources: summary.effectivenessBySource),
          ],
          const SizedBox(height: MraSpacing.md),
        ],
      ),
    );
  }
}

class _FunnelRow extends StatelessWidget {
  final DiscoveryFunnelCounts counts;
  const _FunnelRow({required this.counts});

  @override
  Widget build(BuildContext context) {
    return MraCard(
      child: Row(
        children: [
          Expanded(
            child: _FunnelStat(label: 'Discovered', value: counts.discovered),
          ),
          Expanded(
            child: _FunnelStat(label: 'Analyzed', value: counts.analyzed),
          ),
          Expanded(
            child: _FunnelStat(label: 'Qualified', value: counts.qualified),
          ),
          Expanded(
            child: _FunnelStat(label: 'Published', value: counts.published),
          ),
        ],
      ),
    );
  }
}

class _FunnelStat extends StatelessWidget {
  final String label;
  final int value;
  const _FunnelStat({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      children: [
        Text('$value', style: theme.textTheme.titleLarge),
        Text(
          label,
          style: theme.textTheme.labelSmall?.copyWith(
            color: theme.colorScheme.onSurfaceVariant,
          ),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
      ],
    );
  }
}

class _TimelineStrip extends StatelessWidget {
  final List<DiscoveryHistoryPoint> points;
  const _TimelineStrip({required this.points});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final maxDiscovered = points
        .map((p) => p.discoveredCount)
        .fold<int>(0, (a, b) => a > b ? a : b);
    return SizedBox(
      height: 84,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: points.length,
        separatorBuilder: (_, _) => const SizedBox(width: MraSpacing.xs),
        itemBuilder: (context, index) {
          final point = points[index];
          final barHeight = maxDiscovered == 0
              ? 4.0
              : 4.0 + 32.0 * (point.discoveredCount / maxDiscovered);
          return SizedBox(
            width: 44,
            child: Column(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                Text(
                  '${point.discoveredCount}',
                  style: theme.textTheme.labelSmall,
                ),
                const SizedBox(height: 2),
                Container(
                  height: barHeight,
                  decoration: BoxDecoration(
                    color: theme.colorScheme.primaryContainer,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  '${point.scanDate.month}/${point.scanDate.day}',
                  style: theme.textTheme.labelSmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}

class _EffectivenessRow extends StatelessWidget {
  final List<DiscoverySourceEffectiveness> sources;
  const _EffectivenessRow({required this.sources});

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: MraSpacing.xs,
      runSpacing: MraSpacing.xs,
      children: sources.map((s) {
        final rate = s.successRate;
        final label = rate == null
            ? '${s.source.replaceAll('_', ' ')}: n/a'
            : '${s.source.replaceAll('_', ' ')}: ${(rate * 100).round()}%';
        final tone = switch (s.verdict) {
          'WEAK' => MraChipTone.warning,
          'OK' => MraChipTone.positive,
          _ => MraChipTone.neutral, // INSUFFICIENT_SAMPLE
        };
        return MraChip(label: label, tone: tone);
      }).toList(),
    );
  }
}
