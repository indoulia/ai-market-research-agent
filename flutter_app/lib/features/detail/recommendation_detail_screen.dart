import 'package:flutter/material.dart';

import '../../core/api_exception.dart';
import '../../design_system/design_system.dart';
import '../feedback/recommendation_feedback_section.dart';
import 'event_item.dart';
import 'price_target_chart.dart';
import 'recommendation_detail.dart';
import 'recommendation_detail_repository.dart';
import 'recommendation_outcome.dart';
import 'timeline_item.dart';

enum _LoadState { loading, error, loaded }

/// EPIC-M3.4 — recommendation detail, evidence & prediction-version
/// timeline screen. Consumes EPIC-M1.137's detail/events/outcome
/// contracts plus EPIC-M3.4's own `/timeline` contract — no client-side
/// re-derivation of any historical value.
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
  List<RecommendationTimelineItem> _timeline = const [];
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
        _repository.fetchTimeline(widget.recommendationId),
        _repository.fetchEvents(widget.recommendationId, pageSize: 20),
        _repository.fetchOutcome(widget.recommendationId),
      ]);
      setState(() {
        _detail = results[0] as RecommendationDetail;
        _timeline = results[1] as List<RecommendationTimelineItem>;
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
          timeline: _timeline,
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
  final List<RecommendationTimelineItem> timeline;
  final List<RecommendationEventItem> events;
  final RecommendationOutcome outcome;

  const _DetailBody({
    required this.detail,
    required this.timeline,
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
            _WhySelectedSection(detail: detail),
            const SizedBox(height: MraSpacing.lg),
            _WhatChangedSection(timeline: timeline),
            const SizedBox(height: MraSpacing.lg),
            _ChartSection(detail: detail, timeline: timeline),
            const SizedBox(height: MraSpacing.lg),
            _OutcomeSection(outcome: outcome, detail: detail),
            const SizedBox(height: MraSpacing.lg),
            RecommendationFeedbackSection(
              recommendationId: detail.id,
              predictionVersion:
                  detail.predictionVersion['modelVersion'] as String,
            ),
          ],
        );
        final secondary = Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            MraExpandableSection(
              title: 'Evidence & provider summary',
              child: _EvidencePanel(detail: detail),
            ),
            const SizedBox(height: MraSpacing.lg),
            MraExpandableSection(
              title: 'News & events',
              child: _EventsSection(events: events),
            ),
            const SizedBox(height: MraSpacing.lg),
            MraExpandableSection(
              title: 'Prediction-version timeline',
              child: _RevisionTimeline(timeline: timeline),
            ),
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
            Wrap(
              spacing: MraSpacing.xs,
              children: [
                MraChip(label: detail.status, tone: MraChipTone.info),
                // EPIC-M3.4 — freshness indicator, "visibly but
                // unobtrusively" (M1.138's own UX rule): only a confirmed
                // "STALE" evidence state renders a badge, matching
                // `RecommendationCard.evidenceFreshness`'s established
                // convention (M1.144) — never claims freshness it can't
                // confirm, never hides a stale prediction's numbers.
                if (detail.evidenceFreshness == 'STALE')
                  const MraChip(
                    label: 'Stale evidence',
                    tone: MraChipTone.warning,
                    icon: Icons.schedule,
                  ),
              ],
            ),
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

/// EPIC-M3.4 — "Why MRA selected this opportunity": a short, synthesized
/// narrative distinct from the raw evidence panel, composed entirely from
/// fields the detail endpoint already returns (score/probability/
/// confidence/evidenceStrength/fundamental/technical/market/provider
/// evidence) — no new backend field, since this platform already expresses
/// "why" as those structured, human-readable summaries.
class _WhySelectedSection extends StatelessWidget {
  final RecommendationDetail detail;
  const _WhySelectedSection({required this.detail});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final bullets = <String>[
      'Probability of success ${(detail.probability * 100).toStringAsFixed(0)}%'
          ' with a composite score of ${detail.score?.toStringAsFixed(0) ?? 'N/A'}'
          ' and ${detail.confidence.toStringAsFixed(0)}% confidence.',
      if (detail.evidenceStrength != null)
        'Evidence strength: ${detail.evidenceStrength}.',
      if (detail.fundamental != null) detail.fundamental!,
      if (detail.technical != null) detail.technical!,
      if (detail.market != null) detail.market!,
      if (detail.providerEvidence.isNotEmpty)
        'Corroborated by: ${detail.providerEvidence.join(', ')}.',
    ];
    return MraCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Why MRA selected this opportunity',
            style: theme.textTheme.titleMedium,
          ),
          const SizedBox(height: MraSpacing.sm),
          for (final bullet in bullets)
            Padding(
              padding: const EdgeInsets.only(bottom: MraSpacing.xs),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('•  '),
                  Expanded(
                    child: Text(bullet, style: theme.textTheme.bodySmall),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

/// EPIC-M3.4 — "What changed since previous prediction": a prominent,
/// above-the-fold callout distinct from the full revision timeline
/// (which stays in the secondary/progressive-disclosure panel). Reads the
/// latest `/timeline` entry rather than re-deriving a diff client-side.
class _WhatChangedSection extends StatelessWidget {
  final List<RecommendationTimelineItem> timeline;
  const _WhatChangedSection({required this.timeline});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final hasRevisions = timeline.length > 1;
    final latest = hasRevisions ? timeline.last : null;
    return MraCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'What changed since previous prediction',
            style: theme.textTheme.titleMedium,
          ),
          const SizedBox(height: MraSpacing.sm),
          if (latest == null)
            Text(
              'No revisions yet — this is the original prediction.',
              style: theme.textTheme.bodySmall,
            )
          else ...[
            Text(latest.changeSummary, style: theme.textTheme.bodySmall),
            const SizedBox(height: MraSpacing.sm),
            Wrap(
              spacing: MraSpacing.sm,
              runSpacing: MraSpacing.sm,
              children: [
                for (final metric in latest.affectedMetrics)
                  MraChip(label: metric, tone: MraChipTone.info),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

class _ChartSection extends StatelessWidget {
  final RecommendationDetail detail;
  final List<RecommendationTimelineItem> timeline;
  const _ChartSection({required this.detail, required this.timeline});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final sorted = [...timeline]
      ..sort((a, b) => a.timestamp.compareTo(b.timestamp));
    final points = [
      ...sorted.map((t) => PricePoint(t.timestamp, t.price)),
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
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
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
    );
  }
}

class _EventsSection extends StatelessWidget {
  final List<RecommendationEventItem> events;
  const _EventsSection({required this.events});

  @override
  Widget build(BuildContext context) {
    if (events.isEmpty) {
      return Text(
        'No news/events recorded for this prediction yet.',
        style: Theme.of(context).textTheme.bodySmall,
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
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

/// EPIC-M3.4 — the full prediction-version timeline (original + every
/// revision), newest first, each with its reason, change summary and the
/// specific metrics it affected.
class _RevisionTimeline extends StatelessWidget {
  final List<RecommendationTimelineItem> timeline;
  const _RevisionTimeline({required this.timeline});

  @override
  Widget build(BuildContext context) {
    final sorted = [...timeline]
      ..sort((a, b) => b.timestamp.compareTo(a.timestamp));
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        for (var i = 0; i < sorted.length; i++)
          TimelineEventRow(
            title: 'v${sorted[i].version} · ${sorted[i].reason}',
            subtitle: sorted[i].affectedMetrics.isEmpty
                ? sorted[i].changeSummary
                : '${sorted[i].changeSummary} (affected: ${sorted[i].affectedMetrics.join(', ')})',
            timestampLabel: _dateLabel(sorted[i].timestamp),
            isLast: i == sorted.length - 1,
          ),
      ],
    );
  }
}

String _dateLabel(DateTime t) =>
    '${t.year}-${t.month.toString().padLeft(2, '0')}-${t.day.toString().padLeft(2, '0')}';
