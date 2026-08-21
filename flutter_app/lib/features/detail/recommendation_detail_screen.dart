import 'package:flutter/material.dart';

import '../../core/api_exception.dart';
import '../../design_system/design_system.dart';
import 'event_item.dart';
import 'history_item.dart';
import 'price_target_chart.dart';
import 'recommendation_detail.dart';
import 'recommendation_detail_repository.dart';
import 'recommendation_outcome.dart';

enum _LoadState { loading, error, loaded }

/// EPIC-M1.138 — recommendation detail & longitudinal history screen.
/// Consumes EPIC-M1.137's four contracts exactly (detail/history/events/
/// outcome) — no client-side re-derivation of any historical value.
class RecommendationDetailScreen extends StatefulWidget {
  final int recommendationId;
  final RecommendationDetailRepository? repository;

  const RecommendationDetailScreen({
    super.key,
    required this.recommendationId,
    this.repository,
  });

  @override
  State<RecommendationDetailScreen> createState() =>
      _RecommendationDetailScreenState();
}

class _RecommendationDetailScreenState
    extends State<RecommendationDetailScreen> {
  late final RecommendationDetailRepository _repository;

  _LoadState _state = _LoadState.loading;
  RecommendationDetail? _detail;
  List<RecommendationHistoryItem> _history = const [];
  List<RecommendationEventItem> _events = const [];
  RecommendationOutcome? _outcome;
  ApiException? _error;

  @override
  void initState() {
    super.initState();
    _repository = widget.repository ?? RecommendationDetailRepository();
    _load();
  }

  Future<void> _load() async {
    setState(() => _state = _LoadState.loading);
    try {
      final results = await Future.wait([
        _repository.fetchDetail(widget.recommendationId),
        _repository.fetchHistory(widget.recommendationId, pageSize: 50),
        _repository.fetchEvents(widget.recommendationId, pageSize: 20),
        _repository.fetchOutcome(widget.recommendationId),
      ]);
      setState(() {
        _detail = results[0] as RecommendationDetail;
        _history = (results[1] as HistoryPage).items;
        _events = (results[2] as EventsPage).items;
        _outcome = results[3] as RecommendationOutcome;
        _state = _LoadState.loaded;
      });
    } catch (e) {
      setState(() {
        _error = e is ApiException ? e : ApiException.network(e);
        _state = _LoadState.error;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(_detail?.symbol ?? 'Recommendation')),
      body: switch (_state) {
        _LoadState.loading => const _LoadingBody(),
        _LoadState.error => MraStateView.error(
          message: _error?.message,
          onAction: _load,
        ),
        _LoadState.loaded => _DetailBody(
          detail: _detail!,
          history: _history,
          events: _events,
          outcome: _outcome!,
        ),
      },
    );
  }
}

class _LoadingBody extends StatelessWidget {
  const _LoadingBody();

  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.all(MraSpacing.lg),
      child: Column(
        children: [
          MraCard(child: SkeletonCard()),
          SizedBox(height: MraSpacing.md),
          MraCard(child: SkeletonCard()),
        ],
      ),
    );
  }
}

class _DetailBody extends StatelessWidget {
  final RecommendationDetail detail;
  final List<RecommendationHistoryItem> history;
  final List<RecommendationEventItem> events;
  final RecommendationOutcome outcome;

  const _DetailBody({
    required this.detail,
    required this.history,
    required this.events,
    required this.outcome,
  });

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final wide = constraints.maxWidth >= 900;
        final primary = Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _HeaderSection(detail: detail),
            const SizedBox(height: MraSpacing.lg),
            _MetricGrid(detail: detail),
            const SizedBox(height: MraSpacing.lg),
            _ChartSection(detail: detail, history: history),
            const SizedBox(height: MraSpacing.lg),
            _OutcomeSection(outcome: outcome, detail: detail),
          ],
        );
        final secondary = Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _EvidencePanel(detail: detail),
            const SizedBox(height: MraSpacing.lg),
            _EventsSection(events: events),
            const SizedBox(height: MraSpacing.lg),
            _RevisionTimeline(history: history),
          ],
        );

        if (!wide) {
          return SingleChildScrollView(
            padding: const EdgeInsets.all(MraSpacing.lg),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                primary,
                const SizedBox(height: MraSpacing.xxl),
                secondary,
              ],
            ),
          );
        }

        return SingleChildScrollView(
          padding: const EdgeInsets.all(MraSpacing.lg),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(flex: 2, child: primary),
              const SizedBox(width: MraSpacing.xl),
              Expanded(flex: 1, child: secondary),
            ],
          ),
        );
      },
    );
  }
}

class _HeaderSection extends StatelessWidget {
  final RecommendationDetail detail;
  const _HeaderSection({required this.detail});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(detail.symbol, style: theme.textTheme.headlineSmall),
              if (detail.companyName != null)
                Text(
                  detail.companyName!,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
            ],
          ),
        ),
        Column(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Text(
              detail.currentPrice?.toStringAsFixed(2) ?? '—',
              style: MraTypography.numeric(theme.textTheme.headlineSmall!),
            ),
            MraChip(label: detail.status, tone: MraChipTone.info),
          ],
        ),
      ],
    );
  }
}

class _MetricGrid extends StatelessWidget {
  final RecommendationDetail detail;
  const _MetricGrid({required this.detail});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(
          spacing: MraSpacing.sm,
          runSpacing: MraSpacing.sm,
          children: [
            TargetSlBadge(
              kind: MraPriceBadgeKind.target,
              formattedPrice: detail.targetPrice.toStringAsFixed(2),
            ),
            TargetSlBadge(
              kind: MraPriceBadgeKind.stopLoss,
              formattedPrice: detail.stopLoss.toStringAsFixed(2),
            ),
            MraChip(
              label: '${detail.horizonDays}D horizon',
              icon: Icons.schedule,
            ),
            MraChip(
              label: '+${detail.upsidePct.toStringAsFixed(1)}% upside',
              tone: MraChipTone.positive,
            ),
          ],
        ),
        const SizedBox(height: MraSpacing.lg),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceAround,
          children: [
            ScoreIndicator(
              kind: MraScoreKind.score,
              value0to100: detail.score ?? 0,
            ),
            ScoreIndicator(
              kind: MraScoreKind.confidence,
              value0to100: detail.confidence,
            ),
            if (detail.trustScore != null)
              ScoreIndicator(
                kind: MraScoreKind.trust,
                value0to100: detail.trustScore!,
              )
            else
              Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const SizedBox(height: 44, child: Center(child: Text('N/A'))),
                  Text('Trust', style: theme.textTheme.labelSmall),
                ],
              ),
          ],
        ),
      ],
    );
  }
}

class _ChartSection extends StatelessWidget {
  final RecommendationDetail detail;
  final List<RecommendationHistoryItem> history;
  const _ChartSection({required this.detail, required this.history});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final sorted = [...history]
      ..sort((a, b) => a.timestamp.compareTo(b.timestamp));
    final points = [
      ...sorted.map((h) => PricePoint(h.timestamp, h.price)),
      if (detail.currentPrice != null)
        PricePoint(detail.updatedAt, detail.currentPrice!),
    ];

    return MraCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Price vs target/stop-loss', style: theme.textTheme.titleMedium),
          const SizedBox(height: MraSpacing.md),
          PriceTargetChart(
            points: points,
            targetPrice: detail.targetPrice,
            stopLoss: detail.stopLoss,
          ),
        ],
      ),
    );
  }
}

class _OutcomeSection extends StatelessWidget {
  final RecommendationOutcome outcome;
  final RecommendationDetail detail;
  const _OutcomeSection({required this.outcome, required this.detail});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return MraCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Outcome', style: theme.textTheme.titleMedium),
          const SizedBox(height: MraSpacing.md),
          if (outcome.isPending)
            Text(
              'Not evaluated yet — outcome is recorded once the horizon '
              'resolves.',
              style: theme.textTheme.bodyMedium,
            )
          else
            Wrap(
              spacing: MraSpacing.sm,
              runSpacing: MraSpacing.sm,
              children: [
                if (outcome.targetHit == true)
                  const MraChip(
                    label: 'Target hit',
                    tone: MraChipTone.positive,
                    icon: Icons.check_circle,
                  ),
                if (outcome.stopLossHit == true)
                  const MraChip(
                    label: 'Stop-loss hit',
                    tone: MraChipTone.error,
                    icon: Icons.warning,
                  ),
                if (outcome.horizonExpired == true &&
                    outcome.targetHit != true &&
                    outcome.stopLossHit != true)
                  const MraChip(label: 'Horizon expired'),
                if (outcome.realizedReturnPct != null)
                  MraChip(
                    label:
                        '${outcome.realizedReturnPct!.toStringAsFixed(1)}% realized',
                  ),
              ],
            ),
          const SizedBox(height: MraSpacing.md),
          Text(
            detail.benchmarkRelative ??
                'Benchmark-relative result not available yet.',
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ],
      ),
    );
  }
}

class _EvidencePanel extends StatelessWidget {
  final RecommendationDetail detail;
  const _EvidencePanel({required this.detail});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final sections = <String, String?>{
      'Fundamentals': detail.fundamental,
      'Technical': detail.technical,
      'Market': detail.market,
      'News': detail.news,
      'Evidence strength': detail.evidenceStrength,
    };
    return MraCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Evidence & provider summary',
            style: theme.textTheme.titleMedium,
          ),
          const SizedBox(height: MraSpacing.md),
          for (final entry in sections.entries)
            if (entry.value != null) ...[
              Text(entry.key, style: theme.textTheme.labelLarge),
              const SizedBox(height: MraSpacing.xs),
              Text(entry.value!, style: theme.textTheme.bodySmall),
              const SizedBox(height: MraSpacing.md),
            ],
          if (detail.providerEvidence.isNotEmpty) ...[
            Text('Providers', style: theme.textTheme.labelLarge),
            const SizedBox(height: MraSpacing.xs),
            Wrap(
              spacing: MraSpacing.sm,
              runSpacing: MraSpacing.sm,
              children: detail.providerEvidence
                  .map((p) => MraChip(label: p, tone: MraChipTone.neutral))
                  .toList(),
            ),
          ],
        ],
      ),
    );
  }
}

class _EventsSection extends StatelessWidget {
  final List<RecommendationEventItem> events;
  const _EventsSection({required this.events});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    if (events.isEmpty) {
      return MraCard(
        child: Text(
          'No news/events recorded for this prediction yet.',
          style: theme.textTheme.bodySmall,
        ),
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('News & events', style: theme.textTheme.titleMedium),
        const SizedBox(height: MraSpacing.md),
        for (final event in events) ...[
          NewsCard(
            headline: event.description,
            source: event.eventType,
            publishedLabel: _dateLabel(event.timestamp),
            tag: event.materiality,
          ),
          const SizedBox(height: MraSpacing.sm),
        ],
      ],
    );
  }
}

class _RevisionTimeline extends StatelessWidget {
  final List<RecommendationHistoryItem> history;
  const _RevisionTimeline({required this.history});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    if (history.isEmpty) {
      return MraCard(
        child: Text(
          'No revisions yet — this is the original prediction.',
          style: theme.textTheme.bodySmall,
        ),
      );
    }
    final sorted = [...history]
      ..sort((a, b) => b.timestamp.compareTo(a.timestamp));
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Revision history', style: theme.textTheme.titleMedium),
        const SizedBox(height: MraSpacing.md),
        for (var i = 0; i < sorted.length; i++)
          TimelineEventRow(
            title: 'v${sorted[i].version} · ${sorted[i].triggerType}',
            subtitle: sorted[i].changeSummary,
            timestampLabel: _dateLabel(sorted[i].timestamp),
            isLast: i == sorted.length - 1,
          ),
      ],
    );
  }
}

String _dateLabel(DateTime t) =>
    '${t.year}-${t.month.toString().padLeft(2, '0')}-${t.day.toString().padLeft(2, '0')}';
