/// EPIC-M3.11 — one row of `GET /api/v1/system/events`
/// (`api/schemas/system.py::SystemEventItem`): the merged provider-outage/
/// unexpected-closure/latency-degradation incident history feed.
class SystemEvent {
  final String id;
  final String type;
  final String severity;
  final String? capability;
  final String? exchange;
  final String description;
  final DateTime occurredAt;

  const SystemEvent({
    required this.id,
    required this.type,
    required this.severity,
    required this.capability,
    required this.exchange,
    required this.description,
    required this.occurredAt,
  });

  factory SystemEvent.fromJson(Map<String, dynamic> json) => SystemEvent(
    id: json['id'] as String,
    type: json['type'] as String,
    severity: json['severity'] as String,
    capability: json['capability'] as String?,
    exchange: json['exchange'] as String?,
    description: json['description'] as String,
    occurredAt: DateTime.parse(json['occurredAt'] as String),
  );
}
