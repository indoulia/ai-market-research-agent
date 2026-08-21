import '../../core/api_client.dart';
import 'feedback.dart';

/// EPIC-M1.142 — repository boundary over EPIC-M1.141's real, merged
/// `POST /api/v1/recommendations/{id}/feedback`
/// (`api/schemas/feedback.py::FeedbackRequest`).
///
/// `predictionVersion` is a plain string, matched server-side against
/// `get_active_version(...).model_version` (`api/services/feedback.py`)
/// — callers must pass that exact string (e.g.
/// `detail.predictionVersion['modelVersion']`), not the whole version
/// bundle.
class FeedbackRepository {
  final ApiClient _client;

  FeedbackRepository({ApiClient? client}) : _client = client ?? ApiClient();

  Future<FeedbackResult> submit({
    required int recommendationId,
    required FeedbackType type,
    required String predictionVersion,
    String? comment,

    /// Reused across a manual retry of the *same* feedback intent so the
    /// server's idempotency mechanism (`FeedbackIdempotencyKey`) returns
    /// the original record instead of creating a duplicate one. A fresh
    /// key must be used for a genuinely new, distinct feedback submission.
    String? idempotencyKey,
  }) async {
    final response = await _client.post(
      '/recommendations/$recommendationId/feedback',
      body: {
        'type': type.wireName,
        'predictionVersion': predictionVersion,
        if (comment != null && comment.isNotEmpty) 'comment': comment,
      },
      headers: idempotencyKey == null
          ? null
          : {'Idempotency-Key': idempotencyKey},
    );
    return FeedbackResult.fromJson(response.data as Map<String, dynamic>);
  }
}
