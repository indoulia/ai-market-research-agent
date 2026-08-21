import 'package:flutter_test/flutter_test.dart';
import 'package:mra_app/core/app_compatibility.dart';

void main() {
  test('a matching contract version is compatible', () {
    expect(
      checkContractCompatibility(kSupportedContractVersion),
      AppCompatibilityStatus.compatible,
    );
  });

  test('a mismatched contract version is incompatible', () {
    expect(
      checkContractCompatibility('1999-01-01'),
      AppCompatibilityStatus.incompatible,
    );
  });
}
