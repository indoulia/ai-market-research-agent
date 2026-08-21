import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mra_app/design_system/theme/mra_theme.dart';
import 'package:mra_app/features/feedback/feedback.dart';
import 'package:mra_app/features/feedback/feedback_repository.dart';
import 'package:mra_app/features/feedback/recommendation_feedback_section.dart';

class _FakeFeedbackRepository extends FeedbackRepository {
  FeedbackType? lastType;
  String? lastComment;
  final bool fail;
  _FakeFeedbackRepository({this.fail = false});

  @override
  Future<FeedbackResult> submit({
    required int recommendationId,
    required FeedbackType type,
    required String predictionVersion,
    String? comment,
    String? idempotencyKey,
  }) async {
    if (fail) throw Exception('boom');
    lastType = type;
    lastComment = comment;
    return FeedbackResult(
      feedbackId: 'f1',
      accepted: true,
      recordedAt: DateTime.parse('2026-08-21T09:00:00Z'),
      learningImpact: 'queued',
    );
  }
}

Widget _wrap(Widget child) {
  return MaterialApp(
    theme: MraTheme.light(),
    home: Scaffold(body: child),
  );
}

void main() {
  testWidgets('tapping Useful submits feedback and shows acknowledgement', (
    tester,
  ) async {
    final repo = _FakeFeedbackRepository();
    await tester.pumpWidget(
      _wrap(
        RecommendationFeedbackSection(
          recommendationId: 1,
          predictionVersion: '1',
          repository: repo,
        ),
      ),
    );

    await tester.tap(find.text('Useful'));
    await tester.pumpAndSettle();

    expect(repo.lastType, FeedbackType.useful);
    expect(find.textContaining('queued for learning'), findsOneWidget);
    // Never claims the model changed instantly.
    expect(find.textContaining('instant'), findsNothing);
  });

  testWidgets('tapping a reason chip submits that reason', (tester) async {
    final repo = _FakeFeedbackRepository();
    await tester.pumpWidget(
      _wrap(
        RecommendationFeedbackSection(
          recommendationId: 1,
          predictionVersion: '1',
          repository: repo,
        ),
      ),
    );

    await tester.tap(find.text('Target too high'));
    await tester.pumpAndSettle();

    expect(repo.lastType, FeedbackType.targetTooHigh);
  });

  testWidgets('a failed submission shows a retry message, not a crash', (
    tester,
  ) async {
    final repo = _FakeFeedbackRepository(fail: true);
    await tester.pumpWidget(
      _wrap(
        RecommendationFeedbackSection(
          recommendationId: 1,
          predictionVersion: '1',
          repository: repo,
        ),
      ),
    );

    await tester.tap(find.text('Not useful'));
    await tester.pumpAndSettle();

    expect(find.textContaining('could not be submitted'), findsOneWidget);
  });

  testWidgets('never uses a modal dialog for feedback', (tester) async {
    await tester.pumpWidget(
      _wrap(
        RecommendationFeedbackSection(
          recommendationId: 1,
          predictionVersion: '1',
          repository: _FakeFeedbackRepository(),
        ),
      ),
    );

    expect(find.byType(Dialog), findsNothing);
    expect(find.byType(AlertDialog), findsNothing);
  });
}
