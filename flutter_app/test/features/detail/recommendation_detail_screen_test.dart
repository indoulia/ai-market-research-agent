import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mra_app/core/api_exception.dart';
import 'package:mra_app/design_system/theme/mra_theme.dart';
import 'package:mra_app/features/detail/event_item.dart';
import 'package:mra_app/features/detail/recommendation_detail.dart';
import 'package:mra_app/features/detail/recommendation_detail_repository.dart';
import 'package:mra_app/features/detail/recommendation_detail_screen.dart';
import 'package:mra_app/features/detail/recommendation_outcome.dart';
import 'package:mra_app/features/detail/timeline_item.dart';

RecommendationDetail _detail({
  double? trustScore = 65,
  String? benchmarkRelative,
  String evidenceFreshness = 'FRESH',
}) {
  return RecommendationDetail.fromJson({
    'id': 1,
    'symbol': 'TATASTEEL',
    'exchange': 'NSE',
    'companyName': 'Tata Steel Ltd.',
    'predictionVersion': {
      'modelVersion': '1',
      'featureVersion': '1',
      'consensusContractVersion': '1',
      'horizonSelectionVersion': '1',
      'scoringContractVersion': '1',
      'rankingVersion': '1',
    },
    'createdAt': '2026-08-01T09:00:00Z',
    'updatedAt': '2026-08-21T09:00:00Z',
    'asOf': '2026-08-21T09:00:00Z',
    'entryPrice': '160.00',
    'currentPrice': '168.35',
    'targetPrice': '176.50',
    'stopLoss': '163.00',
    'horizonDays': 3,
    'expiryAt': null,
    'upsidePct': '4.8',
    'probability': '0.7',
    'score': '82',
    'confidence': '71',
    'trustScore': trustScore?.toString(),
    'uncertainty': 'LOW',
    'evidenceStrength': 'STRONG',
    'fundamental': 'Revenue growth 8% YoY.',
    'technical': 'Above 50-day moving average.',
    'market': 'NSE steel sector up 1.2%.',
    'news': null,
    'events': null,
    'benchmarkRelative': benchmarkRelative,
    'liquidity': 'HIGH',
    'providerEvidence': ['yahoo_finance'],
    'status': 'ISSUED',
    'evidenceFreshness': evidenceFreshness,
  });
}

RecommendationTimelineItem _timelineItem({
  int version = 1,
  String reason = 'INITIAL_PREDICTION',
  String changeSummary = 'Initial prediction.',
  List<String> affectedMetrics = const [],
}) {
  return RecommendationTimelineItem.fromJson({
    'timestamp': '2026-08-1${version}T09:00:00Z',
    'version': version,
    'reason': reason,
    'changeSummary': changeSummary,
    'affectedMetrics': affectedMetrics,
    'price': '165.00',
    'targetPrice': '176.50',
    'stopLoss': '163.00',
    'probability': '0.7',
    'score': '80',
    'confidence': '70',
    'trustScore': '60',
  });
}

RecommendationEventItem _eventItem() {
  return RecommendationEventItem.fromJson({
    'timestamp': '2026-08-15T09:00:00Z',
    'eventType': 'NEWS',
    'description': 'Company announces new plant.',
    'materiality': 'HIGH',
  });
}

RecommendationOutcome _pendingOutcome() {
  return RecommendationOutcome.fromJson({
    'status': 'PENDING',
    'detectedAt': null,
    'observedPrice': null,
    'realizedReturnPct': null,
    'targetHit': null,
    'stopLossHit': null,
    'horizonExpired': null,
    'benchmarkReturnPct': null,
    'evidenceId': null,
  });
}

RecommendationOutcome _targetHitOutcome() {
  return RecommendationOutcome.fromJson({
    'status': 'EVALUATED',
    'detectedAt': '2026-08-20T09:00:00Z',
    'observedPrice': '177.00',
    'realizedReturnPct': '5.2',
    'targetHit': true,
    'stopLossHit': false,
    'horizonExpired': false,
    'benchmarkReturnPct': null,
    'evidenceId': 99,
  });
}

class _FakeDetailRepository extends RecommendationDetailRepository {
  final RecommendationDetail Function()? onDetail;
  final List<RecommendationTimelineItem> timeline;
  final List<RecommendationEventItem> events;
  final RecommendationOutcome Function()? onOutcome;

  _FakeDetailRepository({
    this.onDetail,
    List<RecommendationTimelineItem>? timeline,
    this.events = const [],
    this.onOutcome,
  }) : timeline = timeline ?? [_timelineItem()];

  @override
  Future<RecommendationDetail> fetchDetail(int id) async {
    if (onDetail == null) {
      throw const ApiException(code: 'MRA_NOT_FOUND', message: 'Not found');
    }
    return onDetail!();
  }

  @override
  Future<List<RecommendationTimelineItem>> fetchTimeline(int id) async =>
      timeline;

  @override
  Future<EventsPage> fetchEvents(
    int id, {
    String? cursor,
    int pageSize = 20,
  }) async => EventsPage(items: events, nextCursor: null);

  @override
  Future<RecommendationOutcome> fetchOutcome(int id) async {
    return (onOutcome ?? _pendingOutcome)();
  }
}

Widget _wrap(Widget child) {
  return MaterialApp(theme: MraTheme.light(), home: child);
}

void main() {
  testWidgets('renders header, metrics and pending outcome', (tester) async {
    final repo = _FakeDetailRepository(onDetail: _detail);
    await tester.pumpWidget(
      _wrap(RecommendationDetailScreen(recommendationId: 1, repository: repo)),
    );
    await tester.pumpAndSettle();

    expect(find.text('TATASTEEL'), findsWidgets);
    expect(find.text('Tata Steel Ltd.'), findsOneWidget);
    expect(find.textContaining('Not evaluated yet'), findsOneWidget);
    expect(
      find.text('Benchmark-relative result not available yet.'),
      findsOneWidget,
    );
  });

  testWidgets('shows explicit N/A trust when trust score is null', (
    tester,
  ) async {
    final repo = _FakeDetailRepository(
      onDetail: () => _detail(trustScore: null),
    );
    await tester.pumpWidget(
      _wrap(RecommendationDetailScreen(recommendationId: 1, repository: repo)),
    );
    await tester.pumpAndSettle();

    expect(find.text('N/A'), findsOneWidget);
  });

  testWidgets('renders revision timeline and events from timeline/events', (
    tester,
  ) async {
    final repo = _FakeDetailRepository(
      onDetail: _detail,
      timeline: [
        _timelineItem(),
        _timelineItem(
          version: 2,
          reason: 'MATERIAL_EVIDENCE_CHANGE',
          changeSummary: 'Target raised from 170 to 176.50.',
          affectedMetrics: ['targetPrice'],
        ),
      ],
      events: [_eventItem()],
    );
    await tester.pumpWidget(
      _wrap(RecommendationDetailScreen(recommendationId: 1, repository: repo)),
    );
    await tester.pumpAndSettle();

    // Appears in both the prominent "what changed" callout and the full
    // revision timeline below — that duplication is intentional (M3.4
    // scope: a prominent callout *and* an inspectable full timeline).
    expect(find.textContaining('Target raised from 170'), findsWidgets);
    expect(find.text('Company announces new plant.'), findsOneWidget);
  });

  testWidgets('shows a stale-evidence badge only when evidence is STALE', (
    tester,
  ) async {
    final repo = _FakeDetailRepository(
      onDetail: () => _detail(evidenceFreshness: 'STALE'),
    );
    await tester.pumpWidget(
      _wrap(RecommendationDetailScreen(recommendationId: 1, repository: repo)),
    );
    await tester.pumpAndSettle();

    expect(find.text('Stale evidence'), findsOneWidget);
  });

  testWidgets('omits the stale-evidence badge when evidence is fresh', (
    tester,
  ) async {
    final repo = _FakeDetailRepository(onDetail: _detail);
    await tester.pumpWidget(
      _wrap(RecommendationDetailScreen(recommendationId: 1, repository: repo)),
    );
    await tester.pumpAndSettle();

    expect(find.text('Stale evidence'), findsNothing);
  });

  testWidgets('renders why-selected narrative from evidence fields', (
    tester,
  ) async {
    final repo = _FakeDetailRepository(onDetail: _detail);
    await tester.pumpWidget(
      _wrap(RecommendationDetailScreen(recommendationId: 1, repository: repo)),
    );
    await tester.pumpAndSettle();

    expect(find.text('Why Marksy selected this opportunity'), findsOneWidget);
    expect(find.textContaining('Probability of success'), findsOneWidget);
    // Also appears in the (separate) evidence panel below — intentional
    // duplication, not a rendering bug: this narrative is a synthesized
    // summary, the evidence panel is the raw per-category detail.
    expect(find.textContaining('Revenue growth 8% YoY.'), findsWidgets);
  });

  testWidgets(
    'what-changed shows "no revisions" for a never-revised prediction',
    (tester) async {
      final repo = _FakeDetailRepository(onDetail: _detail);
      await tester.pumpWidget(
        _wrap(
          RecommendationDetailScreen(recommendationId: 1, repository: repo),
        ),
      );
      await tester.pumpAndSettle();

      expect(
        find.text('No revisions yet — this is the original prediction.'),
        findsOneWidget,
      );
    },
  );

  testWidgets(
    'what-changed shows the latest revision summary and affected metrics',
    (tester) async {
      final repo = _FakeDetailRepository(
        onDetail: _detail,
        timeline: [
          _timelineItem(),
          _timelineItem(
            version: 2,
            reason: 'MATERIAL_EVIDENCE_CHANGE',
            changeSummary: 'Target raised from 170 to 176.50.',
            affectedMetrics: ['targetPrice', 'confidence'],
          ),
        ],
      );
      await tester.pumpWidget(
        _wrap(
          RecommendationDetailScreen(recommendationId: 1, repository: repo),
        ),
      );
      await tester.pumpAndSettle();

      expect(
        find.text('What changed since previous prediction'),
        findsOneWidget,
      );
      expect(find.textContaining('Target raised from 170'), findsWidgets);
      expect(find.text('targetPrice'), findsOneWidget);
      expect(find.text('confidence'), findsOneWidget);
    },
  );

  testWidgets(
    'evidence panel collapses and expands via progressive disclosure',
    (tester) async {
      final repo = _FakeDetailRepository(onDetail: _detail);
      await tester.pumpWidget(
        _wrap(
          RecommendationDetailScreen(recommendationId: 1, repository: repo),
        ),
      );
      await tester.pumpAndSettle();

      // One copy in the always-visible "why selected" narrative, one in the
      // collapsible evidence panel.
      expect(
        find.textContaining('Above 50-day moving average'),
        findsNWidgets(2),
      );

      final evidenceHeader = find.text('Evidence & provider summary');
      await tester.ensureVisible(evidenceHeader);
      await tester.pumpAndSettle();
      await tester.tap(evidenceHeader);
      await tester.pumpAndSettle();

      // Evidence panel's copy is gone; "why selected"'s copy remains.
      expect(
        find.textContaining('Above 50-day moving average'),
        findsOneWidget,
      );
    },
  );

  testWidgets('renders target-hit outcome chip when evaluated', (tester) async {
    final repo = _FakeDetailRepository(
      onDetail: _detail,
      onOutcome: _targetHitOutcome,
    );
    await tester.pumpWidget(
      _wrap(RecommendationDetailScreen(recommendationId: 1, repository: repo)),
    );
    await tester.pumpAndSettle();

    expect(find.text('Target hit'), findsOneWidget);
    expect(find.text('5.2% realized'), findsOneWidget);
  });

  testWidgets('shows an error state with retry when the fetch fails', (
    tester,
  ) async {
    final repo = _FakeDetailRepository();
    await tester.pumpWidget(
      _wrap(RecommendationDetailScreen(recommendationId: 1, repository: repo)),
    );
    await tester.pumpAndSettle();

    expect(find.text('Something went wrong'), findsOneWidget);
    expect(find.text('Not found'), findsOneWidget);
  });
}
