import 'package:flutter/material.dart';

/// EPIC-M1.144 — shown instead of the whole app when `/app/bootstrap`
/// confirms the server is on a different `contractVersion` than this build
/// was written against (see `core/app_compatibility.dart`). The app must
/// never silently keep running against a confirmed-incompatible contract
/// and guess at field shapes (AC: "API/UI release compatibility is
/// explicitly versioned") — this is a hard stop, not a banner.
class ContractIncompatibleScreen extends StatelessWidget {
  final String? serverContractVersion;

  const ContractIncompatibleScreen({super.key, this.serverContractVersion});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.system_update_alt, size: 48),
              const SizedBox(height: 16),
              Text(
                'Update required',
                style: Theme.of(context).textTheme.headlineSmall,
              ),
              const SizedBox(height: 8),
              Text(
                'This app version no longer matches the server. '
                'Please update the app to continue.'
                '${serverContractVersion != null ? '\n\n(server contract: $serverContractVersion)' : ''}',
                textAlign: TextAlign.center,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
