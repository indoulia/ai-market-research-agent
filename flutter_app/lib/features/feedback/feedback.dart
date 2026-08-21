/// EPIC-M1.142 — feedback types, matching EPIC-M1.141's documented
/// `POST /recommendations/{id}/feedback` request vocabulary exactly.
enum FeedbackType {
  useful,
  notUseful,
  targetRealistic,
  targetTooHigh,
  targetTooLow,
  reason,
}

extension FeedbackTypeWire on FeedbackType {
  String get wireName => switch (this) {
    FeedbackType.useful => 'useful',
    FeedbackType.notUseful => 'not_useful',
    FeedbackType.targetRealistic => 'target_realistic',
    FeedbackType.targetTooHigh => 'target_too_high',
    FeedbackType.targetTooLow => 'target_too_low',
    FeedbackType.reason => 'reason',
  };

  String get label => switch (this) {
    FeedbackType.useful => 'Useful',
    FeedbackType.notUseful => 'Not useful',
    FeedbackType.targetRealistic => 'Target realistic',
    FeedbackType.targetTooHigh => 'Target too high',
    FeedbackType.targetTooLow => 'Target too low',
    FeedbackType.reason => 'Other reason',
  };
}

/// EPIC-M1.142 — response to a feedback submission.
/// `learningImpact` is always "queued"/"informational" per M1.141's own
/// rules (feedback never directly updates a production model) — the UI
/// surfaces whichever the server returns rather than assuming one.
class FeedbackResult {
  final String feedbackId;
  final bool accepted;
  final DateTime recordedAt;
  final String learningImpact;

  const FeedbackResult({
    required this.feedbackId,
    required this.accepted,
    required this.recordedAt,
    required this.learningImpact,
  });

  factory FeedbackResult.fromJson(Map<String, dynamic> json) {
    return FeedbackResult(
      feedbackId: json['feedbackId'] as String,
      accepted: json['accepted'] as bool,
      recordedAt: DateTime.parse(json['recordedAt'] as String),
      learningImpact: json['learningImpact'] as String,
    );
  }
}
