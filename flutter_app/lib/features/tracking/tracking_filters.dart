/// EPIC-M3.15 — the `from`/`to`/`horizon`/`sector`/`marketCap`/`regime`/
/// `symbol`/`setup` filter surface this EPIC's own API Contract names,
/// shared by all four `/tracking/*` (and `/performance/*`) endpoints
/// (`api/services/tracking.py::TrackingFilters`/`make_filters`). A single
/// immutable value object so [TrackingRepository]'s four fetch methods and
/// [TrackingScreen]'s filter-sheet state don't each carry eight separate
/// optional parameters.
class TrackingFilters {
  final DateTime? from;
  final DateTime? to;
  final int? horizon;
  final String? sector;
  final String? marketCap;
  final String? regime;
  final String? symbol;
  final String? setup;

  const TrackingFilters({
    this.from,
    this.to,
    this.horizon,
    this.sector,
    this.marketCap,
    this.regime,
    this.symbol,
    this.setup,
  });

  bool get isEmpty =>
      from == null &&
      to == null &&
      horizon == null &&
      sector == null &&
      marketCap == null &&
      regime == null &&
      symbol == null &&
      setup == null;

  /// Number of active filter dimensions -- surfaced on the "Filters"
  /// button, matching the Opportunity Explorer's `_activeFilterCount`
  /// convention (`from`/`to` count as one dimension: a date range).
  int get activeCount =>
      (from != null || to != null ? 1 : 0) +
      [
        horizon,
        sector,
        marketCap,
        regime,
        symbol,
        setup,
      ].where((v) => v != null).length;

  Map<String, String> toQuery() => {
    'from': ?from?.toIso8601String(),
    'to': ?to?.toIso8601String(),
    'horizon': ?horizon?.toString(),
    'sector': ?sector,
    'marketCap': ?marketCap,
    'regime': ?regime,
    'symbol': ?symbol,
    'setup': ?setup,
  };

  TrackingFilters copyWith({
    DateTime? from,
    DateTime? to,
    bool clearRange = false,
    int? horizon,
    bool clearHorizon = false,
    String? sector,
    bool clearSector = false,
    String? marketCap,
    bool clearMarketCap = false,
    String? regime,
    bool clearRegime = false,
    String? symbol,
    bool clearSymbol = false,
  }) {
    return TrackingFilters(
      from: clearRange ? null : (from ?? this.from),
      to: clearRange ? null : (to ?? this.to),
      horizon: clearHorizon ? null : (horizon ?? this.horizon),
      sector: clearSector ? null : (sector ?? this.sector),
      marketCap: clearMarketCap ? null : (marketCap ?? this.marketCap),
      regime: clearRegime ? null : (regime ?? this.regime),
      symbol: clearSymbol ? null : (symbol ?? this.symbol),
      setup: setup,
    );
  }
}
