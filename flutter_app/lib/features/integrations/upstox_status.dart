/// EPIC-MARKSY-0001 (fast-follow) — `GET /api/v1/integrations/upstox/status`
/// (`api/schemas/integrations_upstox.py::UpstoxStatusResponse`). Per that
/// service's own `get_status`: `connected` is only true for a token that
/// exists AND is still valid — an expired token reports `connected: false`,
/// `isExpired: true` with `obtainedAt`/`expiresAt` still populated, distinct
/// from never having connected at all (`obtainedAt: null`).
class UpstoxStatus {
  final bool connected;
  final bool isExpired;
  final DateTime? obtainedAt;
  final DateTime? expiresAt;
  final String environment;

  const UpstoxStatus({
    required this.connected,
    required this.isExpired,
    required this.obtainedAt,
    required this.expiresAt,
    required this.environment,
  });

  bool get everConnected => obtainedAt != null;

  factory UpstoxStatus.fromJson(Map<String, dynamic> json) => UpstoxStatus(
    connected: json['connected'] as bool,
    isExpired: json['isExpired'] as bool,
    obtainedAt: json['obtainedAt'] == null
        ? null
        : DateTime.parse(json['obtainedAt'] as String),
    expiresAt: json['expiresAt'] == null
        ? null
        : DateTime.parse(json['expiresAt'] as String),
    environment: json['environment'] as String,
  );
}

/// `GET /api/v1/integrations/upstox/authorize`
/// (`UpstoxAuthorizeResponse`) — `authorizationUrl` is opened in an external
/// browser; the app never touches `code`/`state` itself (Upstox redirects
/// the browser straight to the backend's own `/callback`, not back into
/// this app).
class UpstoxAuthorization {
  final String authorizationUrl;
  final String state;
  final DateTime expiresAt;

  const UpstoxAuthorization({
    required this.authorizationUrl,
    required this.state,
    required this.expiresAt,
  });

  factory UpstoxAuthorization.fromJson(Map<String, dynamic> json) =>
      UpstoxAuthorization(
        authorizationUrl: json['authorizationUrl'] as String,
        state: json['state'] as String,
        expiresAt: DateTime.parse(json['expiresAt'] as String),
      );
}
