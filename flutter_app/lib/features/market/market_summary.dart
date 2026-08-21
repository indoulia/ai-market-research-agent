/// EPIC-M1.140 — parsed from EPIC-M1.139's `GET /api/v1/market/summary`.
/// `marketStatus == "UNKNOWN"` and `indexes == []` are real, honest gaps
/// per M1.139's own completion report (no market-calendar/index-feed
/// module exists yet) — rendered as such, never fabricated.
class SectorMove {
  final String sector;
  final double averageChangePct;
  const SectorMove(this.sector, this.averageChangePct);

  factory SectorMove.fromJson(Map<String, dynamic> json) => SectorMove(
    json['sector'] as String,
    double.parse(json['averageChangePct'] as String),
  );
}

/// Mirrors api/schemas/market.py's `IndexQuote` -- always empty today (no
/// index feed exists yet), but typed to match the real contract so a future
/// populated response parses correctly instead of throwing a CastError.
class IndexQuote {
  final String name;
  final double value;
  final double changePct;
  const IndexQuote(this.name, this.value, this.changePct);

  factory IndexQuote.fromJson(Map<String, dynamic> json) => IndexQuote(
    json['name'] as String,
    double.parse(json['value'] as String),
    double.parse(json['changePct'] as String),
  );
}

class MarketSummary {
  final DateTime asOf;
  final String marketStatus;
  final String? regime;
  final double? advanceDecline;
  final int? volume;
  final double? volatility;
  final List<IndexQuote> indexes;
  final List<SectorMove> sectorLeaders;
  final List<SectorMove> sectorLaggards;

  const MarketSummary({
    required this.asOf,
    required this.marketStatus,
    required this.regime,
    required this.advanceDecline,
    required this.volume,
    required this.volatility,
    required this.indexes,
    required this.sectorLeaders,
    required this.sectorLaggards,
  });

  factory MarketSummary.fromJson(Map<String, dynamic> json) {
    return MarketSummary(
      asOf: DateTime.parse(json['asOf'] as String),
      marketStatus: json['marketStatus'] as String,
      regime: json['regime'] as String?,
      advanceDecline: json['advanceDecline'] == null
          ? null
          : double.parse(json['advanceDecline'] as String),
      volume: json['volume'] as int?,
      volatility: json['volatility'] == null
          ? null
          : double.parse(json['volatility'] as String),
      indexes: (json['indexes'] as List)
          .cast<Map<String, dynamic>>()
          .map(IndexQuote.fromJson)
          .toList(),
      sectorLeaders: (json['sectorLeaders'] as List)
          .cast<Map<String, dynamic>>()
          .map(SectorMove.fromJson)
          .toList(),
      sectorLaggards: (json['sectorLaggards'] as List)
          .cast<Map<String, dynamic>>()
          .map(SectorMove.fromJson)
          .toList(),
    );
  }
}
