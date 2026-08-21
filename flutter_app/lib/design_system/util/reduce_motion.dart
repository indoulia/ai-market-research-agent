import 'package:flutter/material.dart';

/// EPIC-M1.133 — single place components check reduced-motion so every
/// animated component behaves consistently instead of each one reading
/// platform accessibility flags itself.
bool mraReduceMotion(BuildContext context) {
  return MediaQuery.of(context).disableAnimations;
}
