/// EPIC-M3.11 — `GET /api/v1/system/health`
/// (`api/schemas/system.py::SystemHealthResponse`): a compact overall
/// snapshot so a viewer can distinguish a market condition from an
/// information-system degradation at a glance.
class SystemHealthSummary {
  final String status;
  final DateTime checkedAt;
  final String apiVersion;
  final bool databaseOk;
  final Map<String, int> providerStatusCounts;
  final int activeOutageCount;
  final String marketSession;

  const SystemHealthSummary({
    required this.status,
    required this.checkedAt,
    required this.apiVersion,
    required this.databaseOk,
    required this.providerStatusCounts,
    required this.activeOutageCount,
    required this.marketSession,
  });

  factory SystemHealthSummary.fromJson(Map<String, dynamic> json) =>
      SystemHealthSummary(
        status: json['status'] as String,
        checkedAt: DateTime.parse(json['checkedAt'] as String),
        apiVersion: json['apiVersion'] as String,
        databaseOk: json['databaseOk'] as bool,
        providerStatusCounts: (json['providerStatusCounts'] as Map).map(
          (key, value) => MapEntry(key as String, value as int),
        ),
        activeOutageCount: json['activeOutageCount'] as int,
        marketSession: json['marketSession'] as String,
      );
}
