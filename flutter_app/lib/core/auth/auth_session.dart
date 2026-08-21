/// EPIC-M1.146 — parsed from EPIC-M1.145's real, merged
/// `SessionResponse`/`UserContext` (`api/schemas/auth.py`).
class AuthSession {
  final String sessionToken;
  final String userId;
  final DateTime issuedAt;
  final DateTime expiresAt;

  const AuthSession({
    required this.sessionToken,
    required this.userId,
    required this.issuedAt,
    required this.expiresAt,
  });

  bool get isExpired => DateTime.now().isAfter(expiresAt);

  factory AuthSession.fromJson(Map<String, dynamic> json) {
    return AuthSession(
      sessionToken: json['sessionToken'] as String,
      userId: json['userId'] as String,
      issuedAt: DateTime.parse(json['issuedAt'] as String),
      expiresAt: DateTime.parse(json['expiresAt'] as String),
    );
  }

  Map<String, dynamic> toStorageJson() => {
    'sessionToken': sessionToken,
    'userId': userId,
    'issuedAt': issuedAt.toIso8601String(),
    'expiresAt': expiresAt.toIso8601String(),
  };
}
