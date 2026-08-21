/// EPIC-M1.133 — spacing/grid tokens. All component/screen padding and gaps
/// must come from this scale; no arbitrary per-screen spacing values.
class MraSpacing {
  const MraSpacing._();

  static const double xs = 4;
  static const double sm = 8;
  static const double md = 12;
  static const double lg = 16;
  static const double xl = 24;
  static const double xxl = 32;
  static const double xxxl = 48;
}

/// EPIC-M1.133 — corner radius tokens.
class MraRadii {
  const MraRadii._();

  static const double sm = 6;
  static const double md = 10;
  static const double lg = 16;
  static const double pill = 999;
}

/// EPIC-M1.133 — elevation tokens (Material 3 surface tint levels).
class MraElevation {
  const MraElevation._();

  static const double level0 = 0;
  static const double level1 = 1;
  static const double level2 = 3;
  static const double level3 = 6;
}

/// EPIC-M1.133 — motion tokens. Durations stay short/subtle by design; callers
/// must consult [MraMotion.durationFor] so reduced-motion is respected
/// uniformly instead of every screen checking accessibility settings itself.
class MraMotion {
  const MraMotion._();

  static const Duration fast = Duration(milliseconds: 120);
  static const Duration standard = Duration(milliseconds: 200);
  static const Duration slow = Duration(milliseconds: 320);

  static Duration durationFor(Duration base, {required bool reduceMotion}) {
    return reduceMotion ? Duration.zero : base;
  }
}

/// EPIC-M1.133/M1.134 — responsive breakpoints keyed to available window
/// width, not device type, per the design-direction requirement.
class MraBreakpoints {
  const MraBreakpoints._();

  static const double compact = 600;
  static const double medium = 1024;
  static const double expanded = 1440;

  static MraWindowClass classify(double width) {
    if (width < compact) return MraWindowClass.compact;
    if (width < medium) return MraWindowClass.medium;
    if (width < expanded) return MraWindowClass.expanded;
    return MraWindowClass.large;
  }
}

enum MraWindowClass { compact, medium, expanded, large }
