import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../design_system/design_system.dart';

/// EPIC-M1.134 — Settings placeholder. Real preferences UI is
/// EPIC-M3.10 (User Feedback & Preferences); this keeps a working entry
/// point to the EPIC-M1.133 component gallery for QA in the meantime.
class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(MraSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text('Settings', style: Theme.of(context).textTheme.headlineSmall),
          const SizedBox(height: MraSpacing.sm),
          Text(
            'Built by EPIC-M3.10 User Feedback & Preferences.',
            style: Theme.of(context).textTheme.bodyMedium,
          ),
          const SizedBox(height: MraSpacing.xl),
          OutlinedButton.icon(
            icon: const Icon(Icons.palette_outlined),
            label: const Text('Design system gallery (QA)'),
            onPressed: () => context.push('/dev/gallery'),
          ),
        ],
      ),
    );
  }
}
