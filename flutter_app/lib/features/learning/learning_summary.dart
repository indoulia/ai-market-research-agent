/// EPIC-M3.9 — domain model parsed from `GET /learning/summary`
/// (`api/schemas/learning.py::LearningSummary`). Numeric fields arrive as
/// decimal strings and are parsed here once, matching the existing
/// `TrackingSummary`/`DiscoverySummary` convention.
library;

class LastLearningCycle {
  final int id;
  final DateTime startedAt;
  final String outcome;
  final int newOutcomesCount;
  final String? skipReason;
  final int? modelPromotionId;
  final String cycleRuleVersion;

  const LastLearningCycle({
    required this.id,
    required this.startedAt,
    required this.outcome,
    required this.newOutcomesCount,
    required this.skipReason,
    required this.modelPromotionId,
    required this.cycleRuleVersion,
  });

  bool get ran => outcome == 'RAN';

  factory LastLearningCycle.fromJson(Map<String, dynamic> json) {
    return LastLearningCycle(
      id: json['id'] as int,
      startedAt: DateTime.parse(json['startedAt'] as String),
      outcome: json['outcome'] as String,
      newOutcomesCount: json['newOutcomesCount'] as int,
      skipReason: json['skipReason'] as String?,
      modelPromotionId: json['modelPromotionId'] as int?,
      cycleRuleVersion: json['cycleRuleVersion'] as String,
    );
  }
}

class PromotionCounts {
  final int promoted;
  final int rejected;

  const PromotionCounts({required this.promoted, required this.rejected});

  factory PromotionCounts.fromJson(Map<String, dynamic> json) {
    return PromotionCounts(
      promoted: json['promoted'] as int,
      rejected: json['rejected'] as int,
    );
  }
}

class ExperimentCounts {
  final int total;
  final int ready;
  final int insufficientSample;
  final int pending;

  const ExperimentCounts({
    required this.total,
    required this.ready,
    required this.insufficientSample,
    required this.pending,
  });

  factory ExperimentCounts.fromJson(Map<String, dynamic> json) {
    return ExperimentCounts(
      total: json['total'] as int,
      ready: json['ready'] as int,
      insufficientSample: json['insufficientSample'] as int,
      pending: json['pending'] as int,
    );
  }
}

class LearningSignalSummary {
  final String category;
  final String reasonCode;
  final String verdict;
  final int totalFeedbackCount;
  final int distinctPredictionCount;
  final int distinctUserCount;
  final int repeatedPredictionCount;
  final int evaluatedCount;
  final double? successRate;

  const LearningSignalSummary({
    required this.category,
    required this.reasonCode,
    required this.verdict,
    required this.totalFeedbackCount,
    required this.distinctPredictionCount,
    required this.distinctUserCount,
    required this.repeatedPredictionCount,
    required this.evaluatedCount,
    required this.successRate,
  });

  bool get isWeak => verdict == 'WEAK';

  factory LearningSignalSummary.fromJson(Map<String, dynamic> json) {
    return LearningSignalSummary(
      category: json['category'] as String,
      reasonCode: json['reasonCode'] as String,
      verdict: json['verdict'] as String,
      totalFeedbackCount: json['totalFeedbackCount'] as int,
      distinctPredictionCount: json['distinctPredictionCount'] as int,
      distinctUserCount: json['distinctUserCount'] as int,
      repeatedPredictionCount: json['repeatedPredictionCount'] as int,
      evaluatedCount: json['evaluatedCount'] as int,
      successRate: json['successRate'] == null
          ? null
          : double.parse(json['successRate'] as String),
    );
  }
}

class ChampionChallengerStatus {
  final String challengerModelVersion;
  final String championModelVersion;
  final String verdict;
  final int sampleCount;
  final double? championSuccessRate;
  final double? challengerSuccessRate;
  final double? successRateDelta;
  final DateTime computedAt;
  final String comparisonRuleVersion;

  const ChampionChallengerStatus({
    required this.challengerModelVersion,
    required this.championModelVersion,
    required this.verdict,
    required this.sampleCount,
    required this.championSuccessRate,
    required this.challengerSuccessRate,
    required this.successRateDelta,
    required this.computedAt,
    required this.comparisonRuleVersion,
  });

  factory ChampionChallengerStatus.fromJson(Map<String, dynamic> json) {
    double? dec(dynamic v) => v == null ? null : double.parse(v as String);
    return ChampionChallengerStatus(
      challengerModelVersion: json['challengerModelVersion'] as String,
      championModelVersion: json['championModelVersion'] as String,
      verdict: json['verdict'] as String,
      sampleCount: json['sampleCount'] as int,
      championSuccessRate: dec(json['championSuccessRate']),
      challengerSuccessRate: dec(json['challengerSuccessRate']),
      successRateDelta: dec(json['successRateDelta']),
      computedAt: DateTime.parse(json['computedAt'] as String),
      comparisonRuleVersion: json['comparisonRuleVersion'] as String,
    );
  }
}

class LatestRollback {
  final String rolledBackModelVersion;
  final String restoredModelVersion;
  final DateTime decidedAt;
  final String rollbackRuleVersion;

  const LatestRollback({
    required this.rolledBackModelVersion,
    required this.restoredModelVersion,
    required this.decidedAt,
    required this.rollbackRuleVersion,
  });

  factory LatestRollback.fromJson(Map<String, dynamic> json) {
    return LatestRollback(
      rolledBackModelVersion: json['rolledBackModelVersion'] as String,
      restoredModelVersion: json['restoredModelVersion'] as String,
      decidedAt: DateTime.parse(json['decidedAt'] as String),
      rollbackRuleVersion: json['rollbackRuleVersion'] as String,
    );
  }
}

class LearningSummary {
  final DateTime asOf;
  final String? currentModelVersion;
  final LastLearningCycle? lastCycle;
  final PromotionCounts promotionCounts;
  final int rollbackCount;
  final LatestRollback? latestRollback;
  final ExperimentCounts experimentCounts;
  final int failurePatternCount;
  final List<LearningSignalSummary> recentSignals;
  final ChampionChallengerStatus? championChallenger;
  final String methodologyVersion;

  const LearningSummary({
    required this.asOf,
    required this.currentModelVersion,
    required this.lastCycle,
    required this.promotionCounts,
    required this.rollbackCount,
    required this.latestRollback,
    required this.experimentCounts,
    required this.failurePatternCount,
    required this.recentSignals,
    required this.championChallenger,
    required this.methodologyVersion,
  });

  factory LearningSummary.fromJson(Map<String, dynamic> json) {
    return LearningSummary(
      asOf: DateTime.parse(json['asOf'] as String),
      currentModelVersion: json['currentModelVersion'] as String?,
      lastCycle: json['lastCycle'] == null
          ? null
          : LastLearningCycle.fromJson(
              json['lastCycle'] as Map<String, dynamic>,
            ),
      promotionCounts: PromotionCounts.fromJson(
        json['promotionCounts'] as Map<String, dynamic>,
      ),
      rollbackCount: json['rollbackCount'] as int,
      latestRollback: json['latestRollback'] == null
          ? null
          : LatestRollback.fromJson(
              json['latestRollback'] as Map<String, dynamic>,
            ),
      experimentCounts: ExperimentCounts.fromJson(
        json['experimentCounts'] as Map<String, dynamic>,
      ),
      failurePatternCount: json['failurePatternCount'] as int,
      recentSignals: (json['recentSignals'] as List)
          .cast<Map<String, dynamic>>()
          .map(LearningSignalSummary.fromJson)
          .toList(),
      championChallenger: json['championChallenger'] == null
          ? null
          : ChampionChallengerStatus.fromJson(
              json['championChallenger'] as Map<String, dynamic>,
            ),
      methodologyVersion: json['methodologyVersion'] as String,
    );
  }
}
