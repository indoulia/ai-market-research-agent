// EPIC-M1.142 — parsed from EPIC-M1.141's real, merged
// `PreferencesDocument`/`PreferencesUpdateRequest` (`api/schemas/
// preferences.py`, `docs/api/openapi.json`) — reconciled against the
// real contract after it merged mid-implementation of this epic.

/// The real, fixed alert-type vocabulary from `app.recommendation_alerts`
/// (`ALERT_TYPE_*` constants) that `mutedAlertTypes` mutes by string.
/// `MAJOR_NEWS_EVENT` is defined there but never triggered by any real
/// event source in this platform yet (that module's own docstring says
/// so) — omitted here rather than offering a mute toggle for an alert
/// that can never fire.
class AlertType {
  const AlertType._();

  static const String expiry = 'EXPIRY';
  static const String invalidation = 'INVALIDATION';
  static const String revalidationUpdate = 'REVALIDATION_UPDATE';
  static const String marketRegimeChange = 'MARKET_REGIME_CHANGE';
  static const String newOpportunity = 'NEW_OPPORTUNITY';

  static const List<String> all = [
    expiry,
    invalidation,
    revalidationUpdate,
    marketRegimeChange,
    newOpportunity,
  ];

  static String label(String type) => switch (type) {
    expiry => 'Prediction expiry',
    invalidation => 'Prediction invalidated',
    revalidationUpdate => 'Revalidation update',
    marketRegimeChange => 'Market regime change',
    newOpportunity => 'New opportunity',
    _ => type,
  };
}

/// Real shape: `{ mutedAlertTypes: string[] }` — an opt-out list, not
/// per-type booleans. A type's absence from the list means notifications
/// for it are enabled.
class NotificationPreferences {
  final List<String> mutedAlertTypes;

  const NotificationPreferences({required this.mutedAlertTypes});

  static const empty = NotificationPreferences(mutedAlertTypes: []);

  bool isMuted(String alertType) => mutedAlertTypes.contains(alertType);

  factory NotificationPreferences.fromJson(Map<String, dynamic> json) {
    return NotificationPreferences(
      mutedAlertTypes: ((json['mutedAlertTypes'] as List?) ?? const [])
          .cast<String>(),
    );
  }

  Map<String, dynamic> toJson() => {'mutedAlertTypes': mutedAlertTypes};

  NotificationPreferences toggleMuted(String alertType) {
    final muted = {...mutedAlertTypes};
    if (muted.contains(alertType)) {
      muted.remove(alertType);
    } else {
      muted.add(alertType);
    }
    return NotificationPreferences(mutedAlertTypes: muted.toList());
  }
}

/// Real shape: `model_config = {"extra": "allow"}` — a genuinely
/// free-form JSON object; the API validates nothing about its contents.
/// `themeMode`/`showFreshnessTimestamps` are this UI's own opaque keys,
/// confirmed compatible with that "extra: allow" contract.
enum AppThemeMode { system, light, dark }

class DisplayPreferences {
  final AppThemeMode themeMode;
  final bool showFreshnessTimestamps;

  const DisplayPreferences({
    required this.themeMode,
    required this.showFreshnessTimestamps,
  });

  factory DisplayPreferences.fromJson(Map<String, dynamic> json) {
    return DisplayPreferences(
      themeMode: AppThemeMode.values.firstWhere(
        (m) => m.name == (json['themeMode'] as String?),
        orElse: () => AppThemeMode.system,
      ),
      showFreshnessTimestamps: json['showFreshnessTimestamps'] as bool? ?? true,
    );
  }

  Map<String, dynamic> toJson() => {
    'themeMode': themeMode.name,
    'showFreshnessTimestamps': showFreshnessTimestamps,
  };

  DisplayPreferences copyWith({
    AppThemeMode? themeMode,
    bool? showFreshnessTimestamps,
  }) => DisplayPreferences(
    themeMode: themeMode ?? this.themeMode,
    showFreshnessTimestamps:
        showFreshnessTimestamps ?? this.showFreshnessTimestamps,
  );
}

class Preferences {
  final int defaultHorizon;
  final List<String> markets;
  final List<String> sectors;
  final List<String> industries;
  final List<String> marketCapBuckets;
  final List<String> watchlist;
  final NotificationPreferences notificationPreferences;
  final DisplayPreferences displayPreferences;

  /// Round-tripped but never edited by this UI — `PreferencesUpdateRequest`
  /// accepts it optionally; omitting it on every save would silently reset
  /// a value a future risk-preference UI sets.
  final String? riskPreference;

  /// Read-only: `PreferencesUpdateRequest` doesn't accept either field, so
  /// they're informational only and never sent back on `PUT`.
  final double? minConfidenceThreshold;
  final String? preferenceVersion;

  const Preferences({
    required this.defaultHorizon,
    required this.markets,
    required this.sectors,
    required this.industries,
    required this.marketCapBuckets,
    required this.watchlist,
    required this.notificationPreferences,
    required this.displayPreferences,
    this.riskPreference,
    this.minConfidenceThreshold,
    this.preferenceVersion,
  });

  static const empty = Preferences(
    defaultHorizon: 3,
    markets: [],
    sectors: [],
    industries: [],
    marketCapBuckets: [],
    watchlist: [],
    notificationPreferences: NotificationPreferences.empty,
    displayPreferences: DisplayPreferences(
      themeMode: AppThemeMode.system,
      showFreshnessTimestamps: true,
    ),
  );

  factory Preferences.fromJson(Map<String, dynamic> json) {
    return Preferences(
      defaultHorizon: json['defaultHorizon'] as int? ?? 3,
      markets: ((json['markets'] as List?) ?? const []).cast<String>(),
      sectors: ((json['sectors'] as List?) ?? const []).cast<String>(),
      industries: ((json['industries'] as List?) ?? const []).cast<String>(),
      marketCapBuckets: ((json['marketCapBuckets'] as List?) ?? const [])
          .cast<String>(),
      watchlist: ((json['watchlist'] as List?) ?? const []).cast<String>(),
      notificationPreferences: NotificationPreferences.fromJson(
        (json['notificationPreferences'] as Map<String, dynamic>?) ?? const {},
      ),
      displayPreferences: DisplayPreferences.fromJson(
        (json['displayPreferences'] as Map<String, dynamic>?) ?? const {},
      ),
      riskPreference: json['riskPreference'] as String?,
      minConfidenceThreshold: json['minConfidenceThreshold'] == null
          ? null
          : double.parse(json['minConfidenceThreshold'] as String),
      preferenceVersion: json['preferenceVersion'] as String?,
    );
  }

  /// Matches `PreferencesUpdateRequest` exactly — `minConfidenceThreshold`/
  /// `preferenceVersion` are deliberately omitted, not accepted by that
  /// schema.
  Map<String, dynamic> toJson() => {
    'defaultHorizon': defaultHorizon,
    'markets': markets,
    'sectors': sectors,
    'industries': industries,
    'marketCapBuckets': marketCapBuckets,
    'watchlist': watchlist,
    'notificationPreferences': notificationPreferences.toJson(),
    'displayPreferences': displayPreferences.toJson(),
    if (riskPreference != null) 'riskPreference': riskPreference,
  };

  Preferences copyWith({
    int? defaultHorizon,
    List<String>? markets,
    List<String>? sectors,
    List<String>? industries,
    List<String>? marketCapBuckets,
    List<String>? watchlist,
    NotificationPreferences? notificationPreferences,
    DisplayPreferences? displayPreferences,
    String? riskPreference,
  }) => Preferences(
    defaultHorizon: defaultHorizon ?? this.defaultHorizon,
    markets: markets ?? this.markets,
    sectors: sectors ?? this.sectors,
    industries: industries ?? this.industries,
    marketCapBuckets: marketCapBuckets ?? this.marketCapBuckets,
    watchlist: watchlist ?? this.watchlist,
    notificationPreferences:
        notificationPreferences ?? this.notificationPreferences,
    displayPreferences: displayPreferences ?? this.displayPreferences,
    riskPreference: riskPreference ?? this.riskPreference,
    minConfidenceThreshold: minConfidenceThreshold,
    preferenceVersion: preferenceVersion,
  );
}
