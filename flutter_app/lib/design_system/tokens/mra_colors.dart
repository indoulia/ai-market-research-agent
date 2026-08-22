import 'package:flutter/material.dart';

/// EPIC-M1.133 — semantic color roles for the MRA design system.
///
/// Colors are grouped by meaning (positive/warning/error/neutral/market-state),
/// not by raw hue, so screens never hardcode ad-hoc colors. Positive emphasis
/// pairs an icon/shape cue with color so meaning never depends on color alone.
class MraColors {
  const MraColors._();

  // Brand / neutral scale.
  static const Color brandPrimary = Color(0xFF1B3A63);
  static const Color brandPrimaryLight = Color(0xFF3E6BA6);

  static const Color neutral0 = Color(0xFFFFFFFF);
  static const Color neutral50 = Color(0xFFF6F7F9);
  static const Color neutral100 = Color(0xFFEDEFF2);
  static const Color neutral200 = Color(0xFFDBDFE5);
  static const Color neutral400 = Color(0xFF9AA3AF);
  static const Color neutral600 = Color(0xFF5B6472);
  static const Color neutral800 = Color(0xFF2A2F37);
  static const Color neutral900 = Color(0xFF15181D);

  // Semantic roles — light theme.
  static const Color positive = Color(0xFF157A4A);
  static const Color positiveContainer = Color(0xFFDCF4E6);
  static const Color warning = Color(0xFF9A6400);
  static const Color warningContainer = Color(0xFFFCEBC7);
  static const Color error = Color(0xFFB3261E);
  static const Color errorContainer = Color(0xFFF9DEDC);
  static const Color infoContainer = Color(0xFFDDEAFB);
  static const Color info = Color(0xFF1B5FA6);

  // Semantic roles — dark theme.
  static const Color positiveDark = Color(0xFF6FDDA0);
  static const Color positiveContainerDark = Color(0xFF14432B);
  static const Color warningDark = Color(0xFFF2C46A);
  static const Color warningContainerDark = Color(0xFF4A3600);
  static const Color errorDark = Color(0xFFF2B8B5);
  static const Color errorContainerDark = Color(0xFF601410);
  static const Color infoDark = Color(0xFF9CC8F5);
  static const Color infoContainerDark = Color(0xFF11365C);

  // Market-state colors (distinct from generic positive/error so a "market up"
  // chip never reads as a general success/failure signal).
  static const Color marketUp = Color(0xFF0F7A5C);
  static const Color marketDown = Color(0xFF9A3A2E);
  static const Color marketFlat = Color(0xFF6B7280);

  // Market-state chip containers (EPIC-M3.16) — distinct tints from
  // positiveContainer/errorContainer so a market up/down chip never reads
  // as a generic success/failure signal.
  static const Color marketUpContainer = Color(0xFFD8F3E9);
  static const Color marketDownContainer = Color(0xFFF4E1DD);
}

/// Resolves semantic colors against the active [Brightness] so components
/// never branch on `Theme.of(context).brightness` themselves.
class MraColorScheme {
  final Brightness brightness;
  const MraColorScheme(this.brightness);

  bool get _dark => brightness == Brightness.dark;

  Color get positive => _dark ? MraColors.positiveDark : MraColors.positive;
  Color get positiveContainer =>
      _dark ? MraColors.positiveContainerDark : MraColors.positiveContainer;
  Color get warning => _dark ? MraColors.warningDark : MraColors.warning;
  Color get warningContainer =>
      _dark ? MraColors.warningContainerDark : MraColors.warningContainer;
  Color get error => _dark ? MraColors.errorDark : MraColors.error;
  Color get errorContainer =>
      _dark ? MraColors.errorContainerDark : MraColors.errorContainer;
  Color get info => _dark ? MraColors.infoDark : MraColors.info;
  Color get infoContainer =>
      _dark ? MraColors.infoContainerDark : MraColors.infoContainer;

  Color get marketUp => MraColors.marketUp;
  Color get marketDown => MraColors.marketDown;
  Color get marketFlat => MraColors.marketFlat;
  Color get marketUpContainer => MraColors.marketUpContainer;
  Color get marketDownContainer => MraColors.marketDownContainer;

  static MraColorScheme of(BuildContext context) =>
      MraColorScheme(Theme.of(context).brightness);
}
