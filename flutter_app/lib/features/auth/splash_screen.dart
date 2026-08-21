import 'package:flutter/material.dart';

/// EPIC-M1.146 — shown only while [AuthController] is restoring a
/// persisted session at startup (a real, momentary state, not a
/// placeholder — session restoration is genuinely asynchronous).
class SplashScreen extends StatelessWidget {
  const SplashScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const Scaffold(body: Center(child: CircularProgressIndicator()));
  }
}
