import 'dart:math' as math;

import 'package:flutter/cupertino.dart';
import 'package:flutter/gestures.dart' show PointerDeviceKind;
import 'package:flutter/material.dart';

/// "Floodlight" design: a night-match dark UI, one bright accent, condensed sports type.
/// The accent is the tenant's primary colour (white-label); floodlight lime until the tenant is known.
const Color floodlightLime = Color(0xFFC6F432);

Color parseHexColor(String? hex, {Color fallback = floodlightLime}) {
  if (hex == null) return fallback;
  final clean = hex.replaceFirst('#', '');
  final value = int.tryParse(clean.length == 6 ? 'FF$clean' : clean, radix: 16);
  return value == null ? fallback : Color(value);
}

double contrastRatio(Color a, Color b) {
  final la = a.computeLuminance(), lb = b.computeLuminance();
  return (math.max(la, lb) + 0.05) / (math.min(la, lb) + 0.05);
}

/// Lifts a tenant colour toward white until it reads on the night canvas (WCAG AA, 4.5:1).
Color readableOn(Color c, Color background) {
  var out = c;
  for (var i = 0; i < 12 && contrastRatio(out, background) < 4.5; i++) {
    out = Color.lerp(out, Colors.white, 0.12)!;
  }
  return out;
}

/// Semantic colour roles. Contrast on the canvas (#0E0F0C):
///   label   #F2F1EA 17.4:1 · label2 #B5B5AB 9.5:1 · label3 #9A9A90 6.8:1
///   live    #FF6B5E  6.9:1 · warning #F5C451 12.0:1 · success #4CC764 8.6:1
/// Status colour is never used alone: every status pairs it with a symbol and text.
@immutable
class AppPalette extends ThemeExtension<AppPalette> {
  final Color canvas; // page background
  final Color surface; // cards, fields, sheets
  final Color raised; // dividers between rows, chips on cards
  final Color hairline; // list row separators
  final Color border; // field and outline-button borders
  final Color nav; // floating tab bar
  final Color navEdge;
  final Color label;
  final Color label2; // secondary text
  final Color label3; // kickers, captions
  final Color muted; // ranks out of the places, disabled
  final Color accent; // tenant colour: primary actions, selection
  final Color onAccent;
  final Color accentDeep; // second stop of the tenant crest
  final Color live;
  final Color liveFill;
  final Color success;
  final Color warning;
  final Color warningFill;
  final Color danger;
  final Color dangerSoft;

  const AppPalette({
    required this.canvas,
    required this.surface,
    required this.raised,
    required this.hairline,
    required this.border,
    required this.nav,
    required this.navEdge,
    required this.label,
    required this.label2,
    required this.label3,
    required this.muted,
    required this.accent,
    required this.onAccent,
    required this.accentDeep,
    required this.live,
    required this.liveFill,
    required this.success,
    required this.warning,
    required this.warningFill,
    required this.danger,
    required this.dangerSoft,
  });

  factory AppPalette.night(Color tenantColor) {
    const canvas = Color(0xFF0E0F0C);
    final accent = readableOn(tenantColor, canvas);
    final onAccent = contrastRatio(canvas, accent) >= contrastRatio(Colors.white, accent) ? canvas : Colors.white;
    return AppPalette(
      canvas: canvas,
      surface: const Color(0xFF1A1B17),
      raised: const Color(0xFF26271F),
      hairline: const Color(0xFF1F201B),
      border: const Color(0xFF3A3B33),
      nav: const Color(0xFF1C1D18),
      navEdge: const Color(0xFF2E2F28),
      label: const Color(0xFFF2F1EA),
      label2: const Color(0xFFB5B5AB),
      label3: const Color(0xFF9A9A90),
      muted: const Color(0xFF6E6E66),
      accent: accent,
      onAccent: onAccent,
      accentDeep: Color.lerp(accent, Colors.black, 0.28)!,
      live: const Color(0xFFFF6B5E),
      liveFill: const Color(0xFFD93A2E),
      success: const Color(0xFF4CC764),
      warning: const Color(0xFFF5C451),
      warningFill: const Color(0xFF2A2410),
      danger: const Color(0xFFFF6B5E),
      dangerSoft: const Color(0xFFFFB4AE),
    );
  }

  @override
  AppPalette copyWith() => this;

  @override
  AppPalette lerp(AppPalette? other, double t) => (other == null || t < 0.5) ? this : other;
}

extension PaletteX on BuildContext {
  AppPalette get palette => Theme.of(this).extension<AppPalette>()!;
}

/// Tabular figures so scores and table columns don't jitter as digits change.
const List<FontFeature> tabular = [FontFeature.tabularFigures()];

const String bodyFont = 'Barlow';
const String displayFont = 'BarlowCondensed';

/// Barlow Condensed: headlines, scores, kickers, button labels. Pass text already upper-cased
/// where the design is all caps (Flutter has no text-transform).
TextStyle condensed(double size, {FontWeight weight = FontWeight.w700, double tracking = 0, Color? color, double? height}) =>
    TextStyle(
      fontFamily: displayFont,
      fontSize: size,
      fontWeight: weight,
      letterSpacing: tracking,
      color: color,
      height: height,
      fontFeatures: tabular,
    );

TextTheme _textTheme(AppPalette p) {
  TextStyle b(double size, FontWeight w, {Color? color, double height = 1.3}) =>
      TextStyle(fontFamily: bodyFont, fontSize: size, fontWeight: w, height: height, color: color ?? p.label);
  return TextTheme(
    displayLarge: condensed(84, weight: FontWeight.w800, tracking: -2, height: 0.9, color: p.label),
    headlineLarge: condensed(44, weight: FontWeight.w800, height: 1, color: p.label),
    headlineMedium: condensed(36, weight: FontWeight.w800, height: 1, color: p.label),
    headlineSmall: condensed(30, weight: FontWeight.w800, height: 1, color: p.label),
    titleLarge: condensed(22, weight: FontWeight.w800, color: p.label),
    titleMedium: condensed(18, weight: FontWeight.w700, color: p.label),
    titleSmall: b(15, FontWeight.w600),
    bodyLarge: b(16, FontWeight.w400),
    bodyMedium: b(15, FontWeight.w400),
    bodySmall: b(13, FontWeight.w400, color: p.label3),
    labelLarge: condensed(19, weight: FontWeight.w800, tracking: 1.5),
    labelMedium: condensed(13, weight: FontWeight.w600, tracking: 1, color: p.label3),
    labelSmall: b(11, FontWeight.w600),
  );
}

/// Platform push (with edge swipe back). Collapses to no motion when the system asks for reduced motion.
class _AdaptivePageTransitions extends PageTransitionsBuilder {
  const _AdaptivePageTransitions();

  @override
  Widget buildTransitions<T>(
    PageRoute<T> route,
    BuildContext context,
    Animation<double> animation,
    Animation<double> secondaryAnimation,
    Widget child,
  ) {
    if (MediaQuery.of(context).disableAnimations) return child;
    return const CupertinoPageTransitionsBuilder()
        .buildTransitions(route, context, animation, secondaryAnimation, child);
  }
}

/// Rubber-band scrolling everywhere, no Material glow, mouse drag allowed (web testing).
class AppScrollBehavior extends MaterialScrollBehavior {
  const AppScrollBehavior();

  @override
  ScrollPhysics getScrollPhysics(BuildContext context) =>
      const BouncingScrollPhysics(parent: AlwaysScrollableScrollPhysics());

  @override
  Widget buildOverscrollIndicator(BuildContext context, Widget child, ScrollableDetails details) => child;

  @override
  Set<PointerDeviceKind> get dragDevices => {...super.dragDevices, PointerDeviceKind.mouse};
}

/// One dark ThemeData for the whole app, accent from the tenant's colour (white-label).
/// Every control keeps a 48 dp minimum tap target.
ThemeData buildTheme(Color tenantColor) {
  final p = AppPalette.night(tenantColor);
  final text = _textTheme(p);
  final radius12 = RoundedRectangleBorder(borderRadius: BorderRadius.circular(12));
  OutlineInputBorder field(Color c, double w) =>
      OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide(color: c, width: w));

  return ThemeData(
    useMaterial3: true,
    brightness: Brightness.dark,
    fontFamily: bodyFont,
    colorScheme: ColorScheme.dark(
      primary: p.accent,
      onPrimary: p.onAccent,
      secondary: p.accent,
      onSecondary: p.onAccent,
      surface: p.surface,
      onSurface: p.label,
      error: p.danger,
    ),
    extensions: [p],
    scaffoldBackgroundColor: p.canvas,
    canvasColor: p.canvas,
    textTheme: text,
    splashFactory: NoSplash.splashFactory,
    highlightColor: p.label.withValues(alpha: 0.06),
    hoverColor: p.label.withValues(alpha: 0.04),
    iconTheme: IconThemeData(color: p.label, size: 22),
    dividerTheme: DividerThemeData(color: p.hairline, thickness: 1, space: 1),
    textSelectionTheme: TextSelectionThemeData(
      cursorColor: p.accent,
      selectionColor: p.accent.withValues(alpha: 0.35),
      selectionHandleColor: p.accent,
    ),
    pageTransitionsTheme: const PageTransitionsTheme(builders: {
      TargetPlatform.android: _AdaptivePageTransitions(),
      TargetPlatform.iOS: _AdaptivePageTransitions(),
      TargetPlatform.windows: _AdaptivePageTransitions(),
      TargetPlatform.macOS: _AdaptivePageTransitions(),
      TargetPlatform.linux: _AdaptivePageTransitions(),
    }),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: p.accent,
        minimumSize: const Size(48, 48),
        textStyle: condensed(15, weight: FontWeight.w700, tracking: 1),
      ),
    ),
    iconButtonTheme: IconButtonThemeData(
      style: IconButton.styleFrom(foregroundColor: p.label, minimumSize: const Size(48, 48)),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: p.accent,
        foregroundColor: p.onAccent,
        minimumSize: const Size(64, 48),
        shape: radius12,
        textStyle: text.labelLarge,
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: p.surface,
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 15),
      hintStyle: text.bodyLarge!.copyWith(color: p.muted),
      helperStyle: text.bodySmall,
      errorStyle: text.bodySmall!.copyWith(color: p.danger),
      border: field(p.border, 1),
      enabledBorder: field(p.border, 1),
      focusedBorder: field(p.accent, 2),
      errorBorder: field(p.danger, 1.5),
      focusedErrorBorder: field(p.danger, 2),
    ),
    bottomSheetTheme: BottomSheetThemeData(
      backgroundColor: p.surface,
      surfaceTintColor: Colors.transparent,
      showDragHandle: true,
      dragHandleColor: p.border,
      dragHandleSize: const Size(40, 5),
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(28))),
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: p.surface,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
    ),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      backgroundColor: p.label,
      contentTextStyle: text.bodyMedium!.copyWith(color: p.canvas, fontWeight: FontWeight.w600),
      actionTextColor: p.canvas,
      elevation: 0,
      shape: radius12,
    ),
    progressIndicatorTheme: ProgressIndicatorThemeData(color: p.accent, linearTrackColor: p.raised),
    switchTheme: SwitchThemeData(
      thumbColor: WidgetStateProperty.resolveWith((s) => s.contains(WidgetState.selected) ? p.canvas : p.label3),
      trackColor: WidgetStateProperty.resolveWith((s) => s.contains(WidgetState.selected) ? p.accent : p.raised),
    ),
    cupertinoOverrideTheme: CupertinoThemeData(
      brightness: Brightness.dark,
      primaryColor: p.accent,
      scaffoldBackgroundColor: p.canvas,
      barBackgroundColor: p.surface,
      textTheme: CupertinoTextThemeData(
        primaryColor: p.accent,
        textStyle: text.bodyLarge,
        pickerTextStyle: text.bodyLarge!.copyWith(fontSize: 21),
        dateTimePickerTextStyle: text.bodyLarge!.copyWith(fontSize: 21),
      ),
    ),
  );
}
