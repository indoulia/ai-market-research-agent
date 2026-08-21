import 'package:flutter/material.dart';

/// EPIC-M1.133 — typography scale, including numeric/financial typography
/// rules (tabular figures so prices/percentages align in dense grids).
class MraTypography {
  const MraTypography._();

  static const String fontFamily = 'Roboto';

  static const FontFeature _tabularFigures = FontFeature.tabularFigures();

  static TextTheme textTheme(Color onSurface) {
    return TextTheme(
      displaySmall: TextStyle(
        fontSize: 32,
        height: 1.2,
        fontWeight: FontWeight.w600,
        color: onSurface,
      ),
      headlineSmall: TextStyle(
        fontSize: 24,
        height: 1.25,
        fontWeight: FontWeight.w600,
        color: onSurface,
      ),
      titleLarge: TextStyle(
        fontSize: 20,
        height: 1.3,
        fontWeight: FontWeight.w600,
        color: onSurface,
      ),
      titleMedium: TextStyle(
        fontSize: 16,
        height: 1.3,
        fontWeight: FontWeight.w600,
        color: onSurface,
      ),
      bodyLarge: TextStyle(fontSize: 16, height: 1.4, color: onSurface),
      bodyMedium: TextStyle(fontSize: 14, height: 1.4, color: onSurface),
      bodySmall: TextStyle(fontSize: 12, height: 1.35, color: onSurface),
      labelLarge: TextStyle(
        fontSize: 14,
        height: 1.2,
        fontWeight: FontWeight.w600,
        color: onSurface,
      ),
      labelMedium: TextStyle(
        fontSize: 12,
        height: 1.2,
        fontWeight: FontWeight.w600,
        color: onSurface,
      ),
      labelSmall: TextStyle(
        fontSize: 11,
        height: 1.2,
        fontWeight: FontWeight.w600,
        color: onSurface,
      ),
    );
  }

  /// Numeric style for prices/targets/percentages: tabular figures keep
  /// digits aligned column-to-column in dense recommendation grids.
  static TextStyle numeric(
    TextStyle base, {
    FontWeight weight = FontWeight.w600,
  }) {
    return base.copyWith(
      fontWeight: weight,
      fontFeatures: const [_tabularFigures],
    );
  }
}
