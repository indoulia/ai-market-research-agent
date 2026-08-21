/// EPIC-M1.138 — result of EPIC-M1.137's
/// `GET /recommendations/{id}/outcome`. `status == "PENDING"` (with every
/// other field null) is a real, honest state — not evaluated yet, not a
/// 404 — and must be rendered as such, never as a fabricated result.
class RecommendationOutcome {
  final String status;
  final DateTime? detectedAt;
  final double? observedPrice;
  final double? realizedReturnPct;
  final bool? targetHit;
  final bool? stopLossHit;
  final bool? horizonExpired;

  /// Always null until EPIC-M1.129 exists.
  final double? benchmarkReturnPct;
  final int? evidenceId;

  const RecommendationOutcome({
    required this.status,
    required this.detectedAt,
    required this.observedPrice,
    required this.realizedReturnPct,
    required this.targetHit,
    required this.stopLossHit,
    required this.horizonExpired,
    required this.benchmarkReturnPct,
    required this.evidenceId,
  });

  bool get isPending => status == 'PENDING';

  static double? _decimalOrNull(dynamic v) =>
      v == null ? null : double.parse(v as String);

  factory RecommendationOutcome.fromJson(Map<String, dynamic> json) {
    return RecommendationOutcome(
      status: json['status'] as String,
      detectedAt: json['detectedAt'] == null
          ? null
          : DateTime.parse(json['detectedAt'] as String),
      observedPrice: _decimalOrNull(json['observedPrice']),
      realizedReturnPct: _decimalOrNull(json['realizedReturnPct']),
      targetHit: json['targetHit'] as bool?,
      stopLossHit: json['stopLossHit'] as bool?,
      horizonExpired: json['horizonExpired'] as bool?,
      benchmarkReturnPct: _decimalOrNull(json['benchmarkReturnPct']),
      evidenceId: json['evidenceId'] as int?,
    );
  }
}
