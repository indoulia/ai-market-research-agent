/// EPIC-M3.2 — domain models parsed from `GET /api/v1/dashboard/snapshot`'s
/// `DashboardSnapshot` JSON shape (`docs/api/openapi.json`). A deliberately
/// leaner sibling of `Recommendation` (EPIC-M1.135) -- `DashboardOpportunity`
/// only carries the fields the snapshot endpoint returns.
class DashboardOpportunity {
  final int id;
  final String symbol;
  final String name;
  final double? price;
  final double targetPrice;
  final double stopLoss;
  final int horizon;
  final double upsidePercent;
  final double score;
  final double confidence;
  final double? trustScore;
  final String status;
  final DateTime updatedAt;

  const DashboardOpportunity({
    required this.id,
    required this.symbol,
    required this.name,
    required this.price,
    required this.targetPrice,
    required this.stopLoss,
    required this.horizon,
    required this.upsidePercent,
    required this.score,
    required this.confidence,
    required this.trustScore,
    required this.status,
    required this.updatedAt,
  });

  static double? _nullableDecimal(dynamic value) =>
      value == null ? null : double.parse(value as String);
  static double _decimal(dynamic value) => double.parse(value as String);

  factory DashboardOpportunity.fromJson(Map<String, dynamic> json) {
    return DashboardOpportunity(
      id: json['id'] as int,
      symbol: json['symbol'] as String,
      name: json['name'] as String,
      price: _nullableDecimal(json['price']),
      targetPrice: _decimal(json['targetPrice']),
      stopLoss: _decimal(json['stopLoss']),
      horizon: json['horizon'] as int,
      upsidePercent: _decimal(json['upsidePercent']),
      score: _decimal(json['score']),
      confidence: _decimal(json['confidence']),
      trustScore: _nullableDecimal(json['trustScore']),
      status: json['status'] as String,
      updatedAt: DateTime.parse(json['updatedAt'] as String),
    );
  }
}

class DashboardEvent {
  final String kind; // 'NEWS' | 'CORPORATE_ACTION'
  final String symbol;
  final String title;
  final DateTime occurredAt;
  final String source;
  final String? materiality;

  const DashboardEvent({
    required this.kind,
    required this.symbol,
    required this.title,
    required this.occurredAt,
    required this.source,
    required this.materiality,
  });

  factory DashboardEvent.fromJson(Map<String, dynamic> json) {
    return DashboardEvent(
      kind: json['kind'] as String,
      symbol: json['symbol'] as String,
      title: json['title'] as String,
      occurredAt: DateTime.parse(json['occurredAt'] as String),
      source: json['source'] as String,
      materiality: json['materiality'] as String?,
    );
  }
}

class DashboardTrustSummary {
  final double? trustScore;
  final double? trustDelta;
  final int sampleSize;
  final bool smallSample;

  const DashboardTrustSummary({
    required this.trustScore,
    required this.trustDelta,
    required this.sampleSize,
    required this.smallSample,
  });

  factory DashboardTrustSummary.fromJson(Map<String, dynamic> json) {
    return DashboardTrustSummary(
      trustScore: json['trustScore'] == null
          ? null
          : double.parse(json['trustScore'] as String),
      trustDelta: json['trustDelta'] == null
          ? null
          : double.parse(json['trustDelta'] as String),
      sampleSize: json['sampleSize'] as int,
      smallSample: json['smallSample'] as bool,
    );
  }
}

/// EPIC-M3.2 — the dashboard's single "core content" request. `indices` is
/// intentionally not modelled beyond presence/absence: M1.139's `indexes`
/// is always `[]` today (no index-level price feed exists), so there is
/// nothing real to render yet -- same honest gap the M1.140 Market screen
/// already documents.
class DashboardSnapshot {
  final String marketStatus;
  final String? marketRegime;
  final List<DashboardOpportunity> topOpportunities;
  final List<DashboardEvent> importantEvents;
  final List<DashboardOpportunity> recentChanges;
  final DashboardTrustSummary trustSummary;
  final DateTime marketAsOf;

  const DashboardSnapshot({
    required this.marketStatus,
    required this.marketRegime,
    required this.topOpportunities,
    required this.importantEvents,
    required this.recentChanges,
    required this.trustSummary,
    required this.marketAsOf,
  });

  factory DashboardSnapshot.fromJson(Map<String, dynamic> json) {
    return DashboardSnapshot(
      marketStatus: json['marketStatus'] as String,
      marketRegime: json['marketRegime'] as String?,
      topOpportunities: (json['topOpportunities'] as List)
          .cast<Map<String, dynamic>>()
          .map(DashboardOpportunity.fromJson)
          .toList(),
      importantEvents: (json['importantEvents'] as List)
          .cast<Map<String, dynamic>>()
          .map(DashboardEvent.fromJson)
          .toList(),
      recentChanges: (json['recentChanges'] as List)
          .cast<Map<String, dynamic>>()
          .map(DashboardOpportunity.fromJson)
          .toList(),
      trustSummary: DashboardTrustSummary.fromJson(
        json['trustSummary'] as Map<String, dynamic>,
      ),
      marketAsOf: DateTime.parse(
        (json['dataFreshness'] as Map<String, dynamic>)['marketAsOf'] as String,
      ),
    );
  }
}
