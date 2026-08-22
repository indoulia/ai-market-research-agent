import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mra_app/core/auth/auth_controller.dart';
import 'package:mra_app/core/auth/auth_repository.dart';
import 'package:mra_app/core/auth/auth_session.dart';
import 'package:mra_app/design_system/theme/mra_theme.dart';
import 'package:mra_app/features/auth/sign_in_screen.dart';
import 'package:mra_app/features/dashboard/dashboard_repository.dart';
import 'package:mra_app/features/dashboard/dashboard_screen.dart';
import 'package:mra_app/features/dashboard/dashboard_snapshot.dart';
import 'package:mra_app/features/dashboard/recommendation.dart';
import 'package:mra_app/features/dashboard/recommendations_repository.dart';
import 'package:mra_app/features/detail/recommendation_detail.dart';
import 'package:mra_app/features/detail/recommendation_detail_repository.dart';
import 'package:mra_app/features/detail/recommendation_detail_screen.dart';
import 'package:mra_app/features/detail/recommendation_outcome.dart';
import 'package:mra_app/features/detail/timeline_item.dart';
import 'package:mra_app/features/opportunities/opportunities_repository.dart';
import 'package:mra_app/features/opportunities/opportunity_explorer_screen.dart';

/// EPIC-M3.14 — accessibility smoke tests. No prior EPIC (including
/// M1.144's E2E suite and M3.13's `accessibility_and_responsive_test.dart`,
/// which only covers text-scaling overflow and breakpoint classification)
/// runs `flutter_test`'s built-in Accessibility Guidelines API
/// (`meetsGuideline`) against a real, populated screen. These tests do:
/// tap targets are large enough and labeled, and text contrast meets WCAG
/// AA, on the screens the Required Journeys actually pass through.
class _NeverSignsInAuthRepository extends AuthRepository {
  @override
  Future<AuthSession> signIn(String userId) => Completer<AuthSession>().future;
}

class _FakeDashboardRepository extends DashboardRepository {
  @override
  Future<DashboardSnapshot> fetchSnapshot({
    String? market,
    int? horizonDays,
    String? sector,
    String? marketCapBucket,
    int limit = 10,
  }) async => DashboardSnapshot.fromJson(_snapshotJson());
}

class _FakeRecommendationsRepository extends RecommendationsRepository {
  @override
  Future<RecommendationsPage> fetchPage({
    int? horizonDays,
    String? market,
    String? sector,
    String? marketCapBucket,
    RecommendationSort sort = RecommendationSort.score,
    bool descending = true,
    int pageSize = 20,
    String? cursor,
  }) async => RecommendationsPage(
    items: const [],
    nextCursor: null,
    asOfServerTime: DateTime.parse('2026-08-21T09:00:00Z'),
  );
}

class _FakeOpportunitiesRepository extends OpportunitiesRepository {
  @override
  Future<OpportunitiesPage> fetchPage({
    String? market,
    int? horizon,
    String? sector,
    String? industry,
    String? marketCap,
    double? minTrust,
    double? minScore,
    double? minUpside,
    String? liquidityBucket,
    String? status,
    String? search,
    OpportunitySort sort = OpportunitySort.score,
    bool descending = true,
    int page = 1,
    int pageSize = 20,
  }) async => OpportunitiesPage(
    items: [Recommendation.fromJson(_recommendationSummary())],
    page: 1,
    pageSize: 20,
    total: 1,
    asOf: DateTime.parse('2026-08-21T09:00:00Z'),
  );
}

/// The canonical `RecommendationSummary` contract, shared by `/opportunities`
/// (EPIC-M3.3) and `/recommendations` — distinct from `_dashboardOpportunity`
/// below, which is `DashboardOpportunity`'s deliberately leaner shape
/// (EPIC-M3.2). Mixing the two up (e.g. `name`/`horizon` vs.
/// `companyName`/`horizonDays`) throws in `fromJson`, not a silent gap.
Map<String, dynamic> _recommendationSummary() => {
  'id': 1,
  'symbol': 'TATASTEEL',
  'exchange': 'NSE',
  'companyName': 'Tata Steel Ltd.',
  'asOf': '2026-08-21T09:00:00Z',
  'price': '168.35',
  'changePct': '1.42',
  'recommendation': 'POSITIVE_OPPORTUNITY',
  'horizonDays': 3,
  'targetPrice': '176.50',
  'stopLoss': '163.00',
  'upsidePct': '4.8',
  'probability': '0.7',
  'score': '82',
  'confidence': '71',
  'trustScore': '65',
  'uncertaintyLevel': 'LOW',
  'fundamentalSummary': null,
  'newsSummary': null,
  'eventSummary': null,
  'marketSummary': null,
  'evidenceFreshness': 'FRESH',
  'status': 'ISSUED',
  'predictionVersion': {'modelVersion': 'v1'},
  'updatedAt': '2026-08-21T09:00:00Z',
};

Map<String, dynamic> _dashboardOpportunity() => {
  'id': 1,
  'symbol': 'TATASTEEL',
  'name': 'Tata Steel Ltd.',
  'price': '168.35',
  'targetPrice': '176.50',
  'stopLoss': '163.00',
  'horizon': 3,
  'upsidePercent': '4.8',
  'score': '82',
  'confidence': '71',
  'trustScore': '65',
  'status': 'ISSUED',
  'updatedAt': '2026-08-21T09:00:00Z',
};

Map<String, dynamic> _snapshotJson() => {
  'marketStatus': 'OPEN',
  'asOf': '2026-08-21T09:00:00Z',
  'marketRegime': 'RISK_ON',
  'indices': [],
  'topOpportunities': [_dashboardOpportunity()],
  'importantEvents': [],
  'recentChanges': [_dashboardOpportunity()],
  'trustSummary': {
    'trustScore': '0.7',
    'trustDelta': null,
    'calibrationScore': null,
    'sampleSize': 12,
    'smallSample': false,
    'modelVersion': null,
  },
  'dataFreshness': {
    'opportunitiesAsOf': '2026-08-21T09:00:00Z',
    'marketAsOf': '2026-08-21T09:00:00Z',
    'newsAsOf': null,
  },
};

class _FakeDetailRepository extends RecommendationDetailRepository {
  @override
  Future<RecommendationDetail> fetchDetail(int id) async =>
      RecommendationDetail.fromJson(_detailJson());

  @override
  Future<List<RecommendationTimelineItem>> fetchTimeline(int id) async =>
      const [];

  @override
  Future<EventsPage> fetchEvents(
    int id, {
    String? cursor,
    int pageSize = 20,
  }) async => const EventsPage(items: [], nextCursor: null);

  @override
  Future<RecommendationOutcome> fetchOutcome(int id) async =>
      RecommendationOutcome.fromJson({
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

Map<String, dynamic> _detailJson() => {
  'id': 1,
  'symbol': 'TATASTEEL',
  'exchange': 'NSE',
  'companyName': 'Tata Steel Ltd.',
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
  'trustScore': '65',
  'uncertainty': 'LOW',
  'evidenceStrength': 'STRONG',
  'fundamental': 'Revenue growth 8% YoY.',
  'technical': null,
  'market': null,
  'news': null,
  'events': null,
  'benchmarkRelative': null,
  'liquidity': 'HIGH',
  'providerEvidence': ['yahoo_finance'],
  'status': 'ISSUED',
  'evidenceFreshness': 'FRESH',
  'predictionVersion': {
    'modelVersion': '1',
    'featureVersion': '1',
    'consensusContractVersion': '1',
    'horizonSelectionVersion': '1',
    'scoringContractVersion': '1',
    'rankingVersion': '1',
  },
};

Widget _harness(Widget child) => MaterialApp(
  theme: MraTheme.light(),
  home: Scaffold(body: child),
);

void main() {
  testWidgets(
    'sign-in screen meets tap-target, label and contrast guidelines',
    (tester) async {
      final handle = tester.ensureSemantics();
      final controller = AuthController(
        repository: _NeverSignsInAuthRepository(),
      );
      await tester.pumpWidget(_harness(SignInScreen(controller: controller)));
      await tester.pumpAndSettle();

      await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
      await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
      await expectLater(tester, meetsGuideline(textContrastGuideline));
      handle.dispose();
    },
  );

  testWidgets(
    'dashboard (Home, populated) meets tap-target, label and contrast '
    'guidelines',
    (tester) async {
      final handle = tester.ensureSemantics();
      await tester.pumpWidget(
        _harness(
          DashboardScreen(
            dashboardRepository: _FakeDashboardRepository(),
            repository: _FakeRecommendationsRepository(),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('TATASTEEL'), findsWidgets);

      await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
      await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
      await expectLater(tester, meetsGuideline(textContrastGuideline));
      handle.dispose();
    },
  );

  testWidgets(
    'opportunity explorer (populated) meets tap-target, label and contrast '
    'guidelines',
    (tester) async {
      final handle = tester.ensureSemantics();
      await tester.pumpWidget(
        _harness(
          OpportunityExplorerScreen(repository: _FakeOpportunitiesRepository()),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('TATASTEEL'), findsWidgets);

      await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
      await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
      await expectLater(tester, meetsGuideline(textContrastGuideline));
      handle.dispose();
    },
  );

  testWidgets(
    'recommendation detail (populated) meets tap-target, label and contrast '
    'guidelines',
    (tester) async {
      final handle = tester.ensureSemantics();
      await tester.pumpWidget(
        _harness(
          RecommendationDetailScreen(
            recommendationId: 1,
            repository: _FakeDetailRepository(),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Tata Steel Ltd.'), findsOneWidget);

      await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
      await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
      await expectLater(tester, meetsGuideline(textContrastGuideline));
      handle.dispose();
    },
  );
}
