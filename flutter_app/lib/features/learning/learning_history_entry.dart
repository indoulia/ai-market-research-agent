/// EPIC-M3.9 — domain model parsed from `GET /learning/history`
/// (`api/schemas/learning.py::LearningHistoryEntry`). `id` is a composite
/// string (e.g. `"cycle:12"`), not a numeric primary key -- this feed
/// merges rows from several distinct, independently-keyed backend tables.
library;

class LearningHistoryEventType {
  static const learningCycle = 'LEARNING_CYCLE';
  static const promotion = 'PROMOTION';
  static const rejection = 'REJECTION';
  static const rollback = 'ROLLBACK';

  const LearningHistoryEventType._();
}

class LearningHistoryEntry {
  final String id;
  final String type;
  final DateTime createdAt;
  final String status;
  final int? evidenceCount;
  final String methodologyVersion;
  final String impact;
  final String? modelVersion;
  final String? decisionReason;

  const LearningHistoryEntry({
    required this.id,
    required this.type,
    required this.createdAt,
    required this.status,
    required this.evidenceCount,
    required this.methodologyVersion,
    required this.impact,
    required this.modelVersion,
    required this.decisionReason,
  });

  factory LearningHistoryEntry.fromJson(Map<String, dynamic> json) {
    return LearningHistoryEntry(
      id: json['id'] as String,
      type: json['type'] as String,
      createdAt: DateTime.parse(json['createdAt'] as String),
      status: json['status'] as String,
      evidenceCount: json['evidenceCount'] as int?,
      methodologyVersion: json['methodologyVersion'] as String,
      impact: json['impact'] as String,
      modelVersion: json['modelVersion'] as String?,
      decisionReason: json['decisionReason'] as String?,
    );
  }
}
