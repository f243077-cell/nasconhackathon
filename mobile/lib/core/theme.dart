import 'package:flutter/material.dart';

/// Fallback brand colour until the tenant is known (after login).
const Color defaultPrimary = Color(0xFF0B5FFF);

Color parseHexColor(String? hex, {Color fallback = defaultPrimary}) {
  if (hex == null) return fallback;
  final clean = hex.replaceFirst('#', '');
  final value = int.tryParse(clean.length == 6 ? 'FF$clean' : clean, radix: 16);
  return value == null ? fallback : Color(value);
}

/// One ThemeData for the whole app, built from the tenant's colour (white-label).
/// Every button gets a 48 dp minimum tap target.
ThemeData buildTheme(Color primary) {
  final scheme = ColorScheme.fromSeed(seedColor: primary);
  const minSize = Size(64, 48);
  return ThemeData(
    colorScheme: scheme,
    useMaterial3: true,
    filledButtonTheme: FilledButtonThemeData(style: FilledButton.styleFrom(minimumSize: minSize)),
    outlinedButtonTheme:
        OutlinedButtonThemeData(style: OutlinedButton.styleFrom(minimumSize: minSize)),
    textButtonTheme: TextButtonThemeData(style: TextButton.styleFrom(minimumSize: minSize)),
    iconButtonTheme: IconButtonThemeData(style: IconButton.styleFrom(minimumSize: const Size(48, 48))),
    inputDecorationTheme: const InputDecorationTheme(border: OutlineInputBorder()),
    appBarTheme: AppBarTheme(backgroundColor: scheme.primary, foregroundColor: scheme.onPrimary),
  );
}
