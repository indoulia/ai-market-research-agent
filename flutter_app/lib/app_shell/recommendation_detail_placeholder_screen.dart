import 'package:flutter/material.dart';

import '../design_system/design_system.dart';

/// EPIC-M1.134 — deep-linkable placeholder proving the route shape works
/// (e.g. `/home/recommendation/TATASTEEL`) ahead of the real detail screen,
/// which is EPIC-M3.4 (Recommendation Detail & Prediction Timeline).
class RecommendationDetailPlaceholderScreen extends StatelessWidget {
  final String recommendationId;

  const RecommendationDetailPlaceholderScreen({
    super.key,
    required this.recommendationId,
  });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(recommendationId)),
      body: MraStateView.empty(
        title: recommendationId,
        message:
            'Built by EPIC-M3.4 Recommendation Detail & Prediction '
            'Timeline.',
      ),
    );
  }
}
