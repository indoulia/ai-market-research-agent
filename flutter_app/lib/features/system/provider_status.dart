/// EPIC-M3.11 — one row of `GET /api/v1/system/providers`
/// (`api/schemas/system.py::ProviderStatus`). `status` reuses M1.93's own
/// `OK`/`WEAK`/`INSUFFICIENT_SAMPLE` verdict vocabulary rather than a new,
/// UI-invented one.
class Freshness {
  final int? ageSeconds;
  final int thresholdSeconds;
  final bool isFresh;

  const Freshness({
    required this.ageSeconds,
    required this.thresholdSeconds,
    required this.isFresh,
  });

  factory Freshness.fromJson(Map<String, dynamic> json) => Freshness(
    ageSeconds: json['ageSeconds'] as int?,
    thresholdSeconds: json['thresholdSeconds'] as int,
    isFresh: json['isFresh'] as bool,
  );
}

class ProviderStatus {
  final String providerId;
  final String capability;
  final String status;
  final DateTime? lastSuccessAt;
  final int? latencyMs;
  final Freshness freshness;
  final double? failureRate;
  final bool fallbackActive;
  final double? qualityScore;

  const ProviderStatus({
    required this.providerId,
    required this.capability,
    required this.status,
    required this.lastSuccessAt,
    required this.latencyMs,
    required this.freshness,
    required this.failureRate,
    required this.fallbackActive,
    required this.qualityScore,
  });

  factory ProviderStatus.fromJson(Map<String, dynamic> json) => ProviderStatus(
    providerId: json['providerId'] as String,
    capability: json['capability'] as String,
    status: json['status'] as String,
    lastSuccessAt: json['lastSuccessAt'] == null
        ? null
        : DateTime.parse(json['lastSuccessAt'] as String),
    latencyMs: json['latencyMs'] as int?,
    freshness: Freshness.fromJson(json['freshness'] as Map<String, dynamic>),
    failureRate: json['failureRate'] == null
        ? null
        : double.parse(json['failureRate'] as String),
    fallbackActive: json['fallbackActive'] as bool,
    qualityScore: json['qualityScore'] == null
        ? null
        : double.parse(json['qualityScore'] as String),
  );
}
