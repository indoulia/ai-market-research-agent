import 'package:flutter/material.dart';

/// EPIC-M1.146 — shown only while [AuthController] is restoring a
/// persisted session at startup (a real, momentary state, not a
/// placeholder — session restoration is genuinely asynchronous).
class SplashScreen extends StatelessWidget {
  const SplashScreen({super.key});

  @override
  Widget build(BuildContext context) {
    // EPIC-M3.13 — screen-reader support: an unlabeled spinner announces
    // nothing at all; a screen reader needs to know MRA is restoring the
    // session rather than appearing frozen/silent.
    return Scaffold(
      body: Center(
        child: Semantics(
          label: 'Restoring your session',
          child: const CircularProgressIndicator(),
        ),
      ),
    );
  }
}
