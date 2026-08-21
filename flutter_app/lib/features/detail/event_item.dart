/// EPIC-M1.138 — one entry from EPIC-M1.137's
/// `GET /recommendations/{id}/events` (news/corporate-action/reanalysis
/// triggers that changed or could change the prediction).
class RecommendationEventItem {
  final DateTime timestamp;
  final String eventType;
  final String description;
  final String? materiality;

  const RecommendationEventItem({
    required this.timestamp,
    required this.eventType,
    required this.description,
    required this.materiality,
  });

  factory RecommendationEventItem.fromJson(Map<String, dynamic> json) {
    return RecommendationEventItem(
      timestamp: DateTime.parse(json['timestamp'] as String),
      eventType: json['eventType'] as String,
      description: json['description'] as String,
      materiality: json['materiality'] as String?,
    );
  }
}
