import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mra_app/design_system/theme/mra_theme.dart';
import 'package:mra_app/features/feedback/feedback.dart';
import 'package:mra_app/features/feedback/feedback_history_item.dart';
import 'package:mra_app/features/feedback/feedback_history_screen.dart';
import 'package:mra_app/features/feedback/feedback_repository.dart';

class _FakeFeedbackRepository extends FeedbackRepository {
  final List<FeedbackHistoryItem> firstPage;
  final List<FeedbackHistoryItem> secondPage;
  final bool fail;

  _FakeFeedbackRepository({
    this.firstPage = const [],
    this.secondPage = const [],
    this.fail = false,
  });

  @override
  Future<FeedbackHistoryPage> fetchHistory({
    String? cursor,
    int pageSize = 20,
  }) async {
    if (fail) throw Exception('boom');
    if (cursor == null) {
      return FeedbackHistoryPage(
        items: firstPage,
        nextCursor: secondPage.isEmpty ? null : 'cursor-1',
      );
    }
    return FeedbackHistoryPage(items: secondPage, nextCursor: null);
  }
}

final _item1 = FeedbackHistoryItem(
  feedbackId: 'f1',
  recommendationId: 42,
  predictionVersionId: 'v1',
  type: FeedbackType.useful,
  reasonCode: 'AGREE',
  note: 'great call',
  learningImpact: 'informational',
  createdAt: DateTime.parse('2026-08-20T09:00:00Z'),
);

final _item2 = FeedbackHistoryItem(
  feedbackId: 'f2',
  recommendationId: 7,
  predictionVersionId: 'v2',
  type: FeedbackType.targetTooHigh,
  reasonCode: 'TOO_HIGH',
  note: null,
  learningImpact: 'queued',
  createdAt: DateTime.parse('2026-08-19T09:00:00Z'),
);

Widget _wrap(Widget child) {
  return MaterialApp(
    theme: MraTheme.light(),
    home: Scaffold(body: child),
  );
}

void main() {
  testWidgets('shows the learning disclosure and an empty state', (
    tester,
  ) async {
    await tester.pumpWidget(
      _wrap(FeedbackHistoryScreen(repository: _FakeFeedbackRepository())),
    );
    await tester.pumpAndSettle();

    expect(find.text('Feedback history'), findsOneWidget);
    expect(find.textContaining('queued for learning'), findsOneWidget);
    expect(find.textContaining("haven't submitted"), findsOneWidget);
  });

  testWidgets('lists submitted feedback newest first with reason/note', (
    tester,
  ) async {
    await tester.pumpWidget(
      _wrap(
        FeedbackHistoryScreen(
          repository: _FakeFeedbackRepository(firstPage: [_item1, _item2]),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('Recommendation #42'), findsOneWidget);
    expect(find.textContaining('Recommendation #7'), findsOneWidget);
    expect(find.textContaining('great call'), findsOneWidget);
    expect(find.textContaining('Queued for learning'), findsOneWidget);
  });

  testWidgets('load more fetches and appends the next page', (tester) async {
    await tester.pumpWidget(
      _wrap(
        FeedbackHistoryScreen(
          repository: _FakeFeedbackRepository(
            firstPage: [_item1],
            secondPage: [_item2],
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Load more'), findsOneWidget);
    expect(find.textContaining('Recommendation #7'), findsNothing);

    await tester.tap(find.text('Load more'));
    await tester.pumpAndSettle();

    expect(find.textContaining('Recommendation #7'), findsOneWidget);
    expect(find.text('Load more'), findsNothing);
  });

  testWidgets('a failed fetch shows a retry state, not a crash', (
    tester,
  ) async {
    await tester.pumpWidget(
      _wrap(
        FeedbackHistoryScreen(repository: _FakeFeedbackRepository(fail: true)),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Retry'), findsOneWidget);
  });
}
