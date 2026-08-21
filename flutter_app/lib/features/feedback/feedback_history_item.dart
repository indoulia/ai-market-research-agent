import 'feedback.dart';

/// EPIC-M3.10 — one row of `GET /api/v1/feedback/history`
/// (`api/schemas/feedback.py::FeedbackHistoryItem`). `type` reuses the
/// exact submission vocabulary from [FeedbackType] rather than a separate
/// "rating" concept — see that schema's own docstring for why.
class FeedbackHistoryItem {
  final String feedbackId;
  final int recommendationId;
  final String predictionVersionId;
  final FeedbackType type;
  final String reasonCode;
  final String? note;
  final String learningImpact;
  final DateTime createdAt;

  const FeedbackHistoryItem({
    required this.feedbackId,
    required this.recommendationId,
    required this.predictionVersionId,
    required this.type,
    required this.reasonCode,
    required this.note,
    required this.learningImpact,
    required this.createdAt,
  });

  factory FeedbackHistoryItem.fromJson(Map<String, dynamic> json) {
    final wireType = json['type'] as String;
    return FeedbackHistoryItem(
      feedbackId: json['feedbackId'] as String,
      recommendationId: json['recommendationId'] as int,
      predictionVersionId: json['predictionVersionId'] as String,
      type: FeedbackType.values.firstWhere(
        (t) => t.wireName == wireType,
        orElse: () => FeedbackType.reason,
      ),
      reasonCode: json['reasonCode'] as String,
      note: json['note'] as String?,
      learningImpact: json['learningImpact'] as String,
      createdAt: DateTime.parse(json['createdAt'] as String),
    );
  }
}
