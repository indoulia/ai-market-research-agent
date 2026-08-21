import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mra_app/design_system/theme/mra_theme.dart';
import 'package:mra_app/features/learning/learning_experiment.dart';
import 'package:mra_app/features/learning/learning_history_entry.dart';
import 'package:mra_app/features/learning/learning_repository.dart';
import 'package:mra_app/features/learning/learning_screen.dart';
import 'package:mra_app/features/learning/learning_summary.dart';

class _FakeLearningRepository extends LearningRepository {
  final LearningSummary Function() summaryFor;
  final List<LearningHistoryEntry> Function() historyFor;
  final List<LearningExperiment> Function() experimentsFor;

  _FakeLearningRepository({
    required this.summaryFor,
    required this.historyFor,
    required this.experimentsFor,
  });

  @override
  Future<LearningSummary> fetchSummary() async => summaryFor();

  @override
  Future<List<LearningHistoryEntry>> fetchHistory({int limit = 50}) async =>
      historyFor();

  @override
  Future<List<LearningExperiment>> fetchExperiments() async => experimentsFor();
}

LearningSummary _summary({
  String? currentModelVersion = 'model-v1',
  int promoted = 2,
  int rejected = 1,
  int rollbackCount = 1,
  int failurePatternCount = 1,
  List<Map<String, dynamic>> recentSignals = const [],
  Map<String, dynamic>? championChallenger,
}) {
  return LearningSummary.fromJson({
    'asOf': '2026-08-22T09:00:00Z',
    'currentModelVersion': currentModelVersion,
    'lastCycle': null,
    'promotionCounts': {'promoted': promoted, 'rejected': rejected},
    'rollbackCount': rollbackCount,
    'latestRollback': null,
    'experimentCounts': {
      'total': 3,
      'ready': 1,
      'insufficientSample': 1,
      'pending': 1,
    },
    'failurePatternCount': failurePatternCount,
    'recentSignals': recentSignals,
    'championChallenger': championChallenger,
    'methodologyVersion': 'LSI-001',
  });
}

Map<String, dynamic> _signal({
  String category = 'TARGET',
  String reasonCode = 'TOO_HIGH',
  String verdict = 'WEAK',
}) {
  return {
    'category': category,
    'reasonCode': reasonCode,
    'verdict': verdict,
    'totalFeedbackCount': 40,
    'distinctPredictionCount': 40,
    'distinctUserCount': 40,
    'repeatedPredictionCount': 0,
    'evaluatedCount': 40,
    'successRate': '0.10',
  };
}

Widget _wrap(Widget child) {
  return MaterialApp(
    theme: MraTheme.light(),
    home: Scaffold(body: child),
  );
}

void main() {
  testWidgets('renders KPI grid and current model from the real contract', (
    tester,
  ) async {
    final repo = _FakeLearningRepository(
      summaryFor: () => _summary(),
      historyFor: () => const [],
      experimentsFor: () => const [],
    );

    await tester.pumpWidget(_wrap(LearningScreen(repository: repo)));
    await tester.pumpAndSettle();

    expect(find.text('Learning & Self-Improvement'), findsOneWidget);
    expect(find.text('model-v1'), findsOneWidget);
    expect(find.text('2 promoted / 1 rejected'), findsOneWidget);
    expect(find.text('1'), findsWidgets); // rollback count / failure patterns
  });

  testWidgets('shows champion/challenger status when present', (tester) async {
    final repo = _FakeLearningRepository(
      summaryFor: () => _summary(
        championChallenger: {
          'challengerModelVersion': 'model-v2',
          'championModelVersion': 'model-v1',
          'verdict': 'VALIDATED',
          'sampleCount': 40,
          'championSuccessRate': '0.55',
          'challengerSuccessRate': '0.62',
          'successRateDelta': '0.07',
          'computedAt': '2026-08-22T09:00:00Z',
          'comparisonRuleVersion': 'SCC-001',
        },
      ),
      historyFor: () => const [],
      experimentsFor: () => const [],
    );

    await tester.pumpWidget(_wrap(LearningScreen(repository: repo)));
    await tester.pumpAndSettle();

    expect(find.text('Champion / challenger status'), findsOneWidget);
    expect(find.textContaining('model-v2'), findsWidgets);
  });

  testWidgets('shows an empty state when there are no failure patterns', (
    tester,
  ) async {
    final repo = _FakeLearningRepository(
      summaryFor: () => _summary(failurePatternCount: 0, recentSignals: []),
      historyFor: () => const [],
      experimentsFor: () => const [],
    );

    await tester.pumpWidget(_wrap(LearningScreen(repository: repo)));
    await tester.pumpAndSettle();

    expect(
      find.text('No recurring feedback patterns found yet.'),
      findsOneWidget,
    );
  });

  testWidgets('renders a failure-pattern signal from the real contract', (
    tester,
  ) async {
    final repo = _FakeLearningRepository(
      summaryFor: () =>
          _summary(failurePatternCount: 1, recentSignals: [_signal()]),
      historyFor: () => const [],
      experimentsFor: () => const [],
    );

    await tester.pumpWidget(_wrap(LearningScreen(repository: repo)));
    await tester.pumpAndSettle();

    expect(find.text('TARGET / TOO_HIGH'), findsOneWidget);
    expect(find.text('WEAK'), findsWidgets);
  });

  testWidgets('shows an error state and retries on demand', (tester) async {
    var attempts = 0;
    final repo = _FakeLearningRepository(
      summaryFor: () {
        attempts++;
        if (attempts == 1) throw Exception('boom');
        return _summary();
      },
      historyFor: () => const [],
      experimentsFor: () => const [],
    );

    await tester.pumpWidget(_wrap(LearningScreen(repository: repo)));
    await tester.pumpAndSettle();

    expect(find.text('Something went wrong'), findsOneWidget);

    await tester.tap(find.text('Retry'));
    await tester.pumpAndSettle();

    expect(find.text('Learning & Self-Improvement'), findsOneWidget);
  });
}
