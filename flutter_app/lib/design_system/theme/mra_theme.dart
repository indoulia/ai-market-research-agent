import 'package:flutter/material.dart';

import '../tokens/mra_colors.dart';
import '../tokens/mra_spacing.dart';
import '../tokens/mra_typography.dart';

/// EPIC-M1.133 — builds the light/dark [ThemeData] every screen must consume.
/// No screen should construct its own [ThemeData] or override tokens ad hoc.
class MraTheme {
  const MraTheme._();

  static ThemeData light() => _build(Brightness.light);
  static ThemeData dark() => _build(Brightness.dark);

  static ThemeData _build(Brightness brightness) {
    final seeded = ColorScheme.fromSeed(
      seedColor: MraColors.brandPrimary,
      brightness: brightness,
    );
    // ColorScheme.fromSeed's tonal-palette algorithm picks a fixed-tone
    // primary from the seed's hue, which visibly diverges from the literal
    // Marksy brand blue it started from (EPIC-M3.17's reference swatch) --
    // pin primary/onPrimary to the actual brand tokens so every button,
    // selected-nav icon and link reads as real Marksy blue rather than a
    // muted Material approximation; everything else stays seed-derived.
    final colorScheme = brightness == Brightness.light
        ? seeded.copyWith(
            primary: MraColors.brandPrimary,
            onPrimary: MraColors.neutral0,
          )
        : seeded.copyWith(
            primary: MraColors.brandPrimaryLight,
            onPrimary: MraColors.brandDeepNavy,
          );
    final onSurface = colorScheme.onSurface;

    return ThemeData(
      useMaterial3: true,
      brightness: brightness,
      colorScheme: colorScheme,
      scaffoldBackgroundColor: colorScheme.surface,
      textTheme: MraTypography.textTheme(onSurface),
      visualDensity: VisualDensity.standard,
      splashFactory: InkSparkle.splashFactory,
      cardTheme: CardThemeData(
        elevation: 0,
        color: colorScheme.surfaceContainerLow,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: BorderSide(color: colorScheme.outlineVariant, width: 1),
        ),
      ),
      chipTheme: ChipThemeData(
        backgroundColor: colorScheme.surfaceContainerHigh,
        labelStyle: MraTypography.textTheme(onSurface).labelMedium,
        padding: const EdgeInsets.symmetric(
          horizontal: MraSpacing.sm,
          vertical: MraSpacing.xs,
        ),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(999)),
      ),
      navigationRailTheme: NavigationRailThemeData(
        backgroundColor: colorScheme.surface,
        selectedIconTheme: IconThemeData(color: colorScheme.primary),
        unselectedIconTheme: IconThemeData(color: colorScheme.onSurfaceVariant),
      ),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: colorScheme.surface,
        indicatorColor: colorScheme.secondaryContainer,
      ),
      snackBarTheme: SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        backgroundColor: colorScheme.inverseSurface,
        contentTextStyle: TextStyle(color: colorScheme.onInverseSurface),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(MraSpacing.sm),
        ),
      ),
      pageTransitionsTheme: const PageTransitionsTheme(
        builders: {
          TargetPlatform.android: FadeUpwardsPageTransitionsBuilder(),
          TargetPlatform.iOS: CupertinoPageTransitionsBuilder(),
          TargetPlatform.windows: FadeUpwardsPageTransitionsBuilder(),
          TargetPlatform.macOS: CupertinoPageTransitionsBuilder(),
          TargetPlatform.linux: FadeUpwardsPageTransitionsBuilder(),
        },
      ),
    );
  }
}
