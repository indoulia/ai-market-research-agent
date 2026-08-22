import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mra_app/design_system/design_system.dart';

void main() {
  test('light and dark themes both build without throwing', () {
    final light = MraTheme.light();
    final dark = MraTheme.dark();

    expect(light.brightness, Brightness.light);
    expect(dark.brightness, Brightness.dark);
    expect(light.useMaterial3, isTrue);
    expect(dark.useMaterial3, isTrue);
  });

  test('MraColorScheme resolves distinct tones per brightness', () {
    const light = MraColorScheme(Brightness.light);
    const dark = MraColorScheme(Brightness.dark);

    expect(light.positive, isNot(equals(dark.positive)));
    expect(light.error, isNot(equals(dark.error)));
  });

  test('primary/onPrimary are pinned to the literal Marksy brand tokens, '
      'not a Material-derived tonal approximation', () {
    final light = MraTheme.light();
    final dark = MraTheme.dark();

    expect(light.colorScheme.primary, MraColors.brandPrimary);
    expect(light.colorScheme.onPrimary, MraColors.neutral0);
    expect(dark.colorScheme.primary, MraColors.brandPrimaryLight);
    expect(dark.colorScheme.onPrimary, MraColors.brandDeepNavy);
  });

  test('MraMotion.durationFor returns zero under reduced motion', () {
    expect(
      MraMotion.durationFor(MraMotion.standard, reduceMotion: true),
      Duration.zero,
    );
    expect(
      MraMotion.durationFor(MraMotion.standard, reduceMotion: false),
      MraMotion.standard,
    );
  });
}
