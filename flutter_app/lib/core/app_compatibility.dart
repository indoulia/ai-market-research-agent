/// EPIC-M1.144 — the API contract version (`api/versioning.py::
/// CONTRACT_VERSION`) this build of the Flutter app was written against.
///
/// Bump this deliberately, in the same change that adapts the app to a new
/// contract shape — never as a reflex to make a compatibility check pass.
/// `tests/test_openapi_contract_freshness.py::
/// test_bootstrap_contract_version_matches_the_flutter_pin` fails CI if this
/// drifts from the backend's own `CONTRACT_VERSION` silently, so the two
/// sides of "API/UI release compatibility is explicitly versioned" (this
/// EPIC's AC) can never quietly disagree.
const String kSupportedContractVersion = '2026-08-21';

enum AppCompatibilityStatus {
  /// The server's `contractVersion` matches [kSupportedContractVersion].
  compatible,

  /// The server reported a different `contractVersion` than this build was
  /// written against — real, breaking drift, not something the UI should
  /// paper over by guessing at field shapes.
  incompatible,
}

/// Pure comparison, no I/O — the network call lives in
/// [AppBootstrapRepository] so this stays trivially testable.
AppCompatibilityStatus checkContractCompatibility(
  String serverContractVersion,
) {
  return serverContractVersion == kSupportedContractVersion
      ? AppCompatibilityStatus.compatible
      : AppCompatibilityStatus.incompatible;
}
