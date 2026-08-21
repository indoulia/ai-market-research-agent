/// EPIC-M3.9 — domain model parsed from `GET /learning/experiments`
/// (`api/schemas/learning.py::LearningExperiment`).
library;

class LearningExperimentStatus {
  static const pending = 'PENDING';
  static const ready = 'READY';
  static const insufficientSample = 'INSUFFICIENT_SAMPLE';

  const LearningExperimentStatus._();
}

class LearningExperimentArm {
  final String armName;
  final String modelVersion;
  final String windowLabel;
  final int? horizonDaysFilter;
  final int? sampleCount;
  final double? accuracy;
  final String? verdict;

  const LearningExperimentArm({
    required this.armName,
    required this.modelVersion,
    required this.windowLabel,
    required this.horizonDaysFilter,
    required this.sampleCount,
    required this.accuracy,
    required this.verdict,
  });

  factory LearningExperimentArm.fromJson(Map<String, dynamic> json) {
    return LearningExperimentArm(
      armName: json['armName'] as String,
      modelVersion: json['modelVersion'] as String,
      windowLabel: json['windowLabel'] as String,
      horizonDaysFilter: json['horizonDaysFilter'] as int?,
      sampleCount: json['sampleCount'] as int?,
      accuracy: json['accuracy'] == null
          ? null
          : double.parse(json['accuracy'] as String),
      verdict: json['verdict'] as String?,
    );
  }
}

class LearningExperiment {
  final int id;
  final String name;
  final String hypothesis;
  final String status;
  final DateTime createdAt;
  final List<LearningExperimentArm> arms;
  final String? bestArmName;
  final bool feedbackDriven;
  final String? feedbackCategory;
  final String? feedbackReasonCode;
  final String methodologyVersion;

  const LearningExperiment({
    required this.id,
    required this.name,
    required this.hypothesis,
    required this.status,
    required this.createdAt,
    required this.arms,
    required this.bestArmName,
    required this.feedbackDriven,
    required this.feedbackCategory,
    required this.feedbackReasonCode,
    required this.methodologyVersion,
  });

  factory LearningExperiment.fromJson(Map<String, dynamic> json) {
    return LearningExperiment(
      id: json['id'] as int,
      name: json['name'] as String,
      hypothesis: json['hypothesis'] as String,
      status: json['status'] as String,
      createdAt: DateTime.parse(json['createdAt'] as String),
      arms: (json['arms'] as List)
          .cast<Map<String, dynamic>>()
          .map(LearningExperimentArm.fromJson)
          .toList(),
      bestArmName: json['bestArmName'] as String?,
      feedbackDriven: json['feedbackDriven'] as bool,
      feedbackCategory: json['feedbackCategory'] as String?,
      feedbackReasonCode: json['feedbackReasonCode'] as String?,
      methodologyVersion: json['methodologyVersion'] as String,
    );
  }
}
