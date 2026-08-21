import 'package:flutter/material.dart';

import '../design_system/design_system.dart';
import 'app_destination.dart';

/// EPIC-M1.134 — honest "not built yet" placeholder for a destination whose
/// real screen belongs to a later, not-yet-implemented EPIC. Never fakes
/// data; names the owning EPIC so it's obvious what's still missing.
class DestinationPlaceholderScreen extends StatelessWidget {
  final AppDestination destination;

  const DestinationPlaceholderScreen({super.key, required this.destination});

  @override
  Widget build(BuildContext context) {
    return MraStateView.empty(
      title: destination.label,
      message: 'Built by ${destination.ownerEpic}.',
    );
  }
}
