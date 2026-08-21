import 'package:flutter/material.dart';

import 'app_shell/app_router.dart';
import 'design_system/theme/mra_theme.dart';

void main() {
  runApp(const MraApp());
}

class MraApp extends StatelessWidget {
  const MraApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'MRA',
      debugShowCheckedModeBanner: false,
      theme: MraTheme.light(),
      darkTheme: MraTheme.dark(),
      routerConfig: appRouter,
    );
  }
}
