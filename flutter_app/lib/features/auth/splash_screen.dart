import 'package:flutter/material.dart';

import '../../design_system/components/marksy_logo.dart';
import '../../design_system/tokens/mra_spacing.dart';

/// EPIC-M1.146 — shown only while [AuthController] is restoring a
/// persisted session at startup (a real, momentary state, not a
/// placeholder — session restoration is genuinely asynchronous).
class SplashScreen extends StatelessWidget {
  const SplashScreen({super.key});

  @override
  Widget build(BuildContext context) {
    // EPIC-M3.13 — screen-reader support: an unlabeled spinner announces
    // nothing at all; a screen reader needs to know Marksy is restoring
    // the session rather than appearing frozen/silent.
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const MarksyLogo(iconSize: 40, fontSize: 28),
            const SizedBox(height: MraSpacing.xl),
            Semantics(
              label: 'Restoring your session',
              child: const CircularProgressIndicator(),
            ),
          ],
        ),
      ),
    );
  }
}
