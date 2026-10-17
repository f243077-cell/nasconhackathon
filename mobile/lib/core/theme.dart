import 'package:flutter/cupertino.dart';
import 'package:flutter/gestures.dart' show PointerDeviceKind;
import 'package:flutter/material.dart';

/// Fallback brand colour until the tenant is known (after login).
const Color defaultPrimary = Color(0xFF0B5FFF);

Color parseHexColor(String? hex, {Color fallback = defaultPrimary}) {
  if (hex == null) return fallback;
  final clean = hex.replaceFirst('#', '');
  final value = int.tryParse(clean.length == 6 ? 'FF$clean' : clean, radix: 16);
  return value == null ? fallback : Color(value);
}

/// Semantic colour roles (Apple's grouped-list system, white-labelled by the tenant accent).
/// Contrast on its own surface, light / dark:
///   label        #111111 on #FFFFFF 18.9:1 · #F2F2F7 on #1C1C1E 15.1:1
///   secondary    #6C6C70 on #FFFFFF  5.1:1 · #AEAEB2 on #1C1C1E  7.6:1
///   live/danger  #D70015 on #FFFFFF  5.6:1 · #FF6961 on #1C1C1E  5.9:1
///   success      #1E7D34 on #FFFFFF  5.3:1 · #30D158 on #1C1C1E  8.4:1
///   warning      #B25000 on #FFFFFF  5.0:1 · #FF9F0A on #1C1C1E  8.0:1
/// Status colour is never used alone: every status pairs it with an icon and text.
@immutable
class AppPalette extends ThemeExtension<AppPalette> {
  final Color canvas; // page background behind grouped sections
  final Color surface; // grouped section / sheet background
  final Color fill; // text fields, steppers, segmented track
  final Color label;
  final Color secondaryLabel;
  final Color separator;
  final Color accent; // tenant colour: primary actions, selection, links
  final Color live;
  final Color success;
  final Color warning;
  final Color danger;

  const AppPalette({
    required this.canvas,
    required this.surface,
    required this.fill,
    required this.label,
    required this.secondaryLabel,
    required this.separator,
    required this.accent,
    required this.live,
    required this.success,
    required this.warning,
    required this.danger,
  });

  factory AppPalette.light(Color accent) => AppPalette(
        canvas: const Color(0xFFF2F2F7),
        surface: Colors.white,
        fill: const Color(0xFFE9E9EE),
        label: const Color(0xFF111111),
        secondaryLabel: const Color(0xFF6C6C70),
        separator: const Color(0x2E3C3C43),
        accent: accent,
        live: const Color(0xFFD70015),
        success: const Color(0xFF1E7D34),
        warning: const Color(0xFFB25000),
        danger: const Color(0xFFD70015),
      );

  // Dark accent is lifted toward white so tenant blues stay legible on black.
  factory AppPalette.dark(Color accent) => AppPalette(
        canvas: Colors.black,
        surface: const Color(0xFF1C1C1E),
        fill: const Color(0xFF2C2C2E),
        label: const Color(0xFFF2F2F7),
        secondaryLabel: const Color(0xFFAEAEB2),
        separator: const Color(0x4D545458),
        accent: Color.lerp(accent, Colors.white, 0.28)!,
        live: const Color(0xFFFF6961),
        success: const Color(0xFF30D158),
        warning: const Color(0xFFFF9F0A),
        danger: const Color(0xFFFF6961),
      );

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

/// iOS text styles (typography.md › Specifications, Large size) mapped onto Material roles.
TextTheme _textTheme(AppPalette p) {
  TextStyle s(double size, FontWeight w, double height, {double tracking = 0, Color? color}) => TextStyle(
        fontSize: size,
        fontWeight: w,
        height: height / size,
        letterSpacing: tracking,
        color: color ?? p.label,
      );
  return TextTheme(
    displayLarge: s(76, FontWeight.w700, 80, tracking: -2), // the scoreboard
    headlineLarge: s(34, FontWeight.w700, 41, tracking: -0.4), // large title
    headlineMedium: s(28, FontWeight.w700, 34, tracking: -0.4), // title 1
    headlineSmall: s(22, FontWeight.w700, 28, tracking: -0.3), // title 2
    titleLarge: s(20, FontWeight.w600, 25, tracking: -0.3), // title 3
    titleMedium: s(17, FontWeight.w600, 22, tracking: -0.4), // headline
    titleSmall: s(15, FontWeight.w600, 20, tracking: -0.2),
    bodyLarge: s(17, FontWeight.w400, 22, tracking: -0.4), // body
    bodyMedium: s(15, FontWeight.w400, 20, tracking: -0.2, color: p.secondaryLabel), // subhead
    bodySmall: s(13, FontWeight.w400, 18, color: p.secondaryLabel), // footnote
    labelLarge: s(17, FontWeight.w600, 22, tracking: -0.4), // buttons
    labelMedium: s(13, FontWeight.w600, 18),
    labelSmall: s(12, FontWeight.w500, 16),
  );
}

/// iOS-style push (with edge swipe back). Collapses to no motion when the system asks for reduced motion.
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

/// One ThemeData for the whole app, built from the tenant's colour (white-label).
/// Every button keeps a 48 dp minimum tap target.
ThemeData buildTheme(Color accent, Brightness brightness) {
  final p = brightness == Brightness.light ? AppPalette.light(accent) : AppPalette.dark(accent);
  final text = _textTheme(p);
  final radius12 = RoundedRectangleBorder(borderRadius: BorderRadius.circular(12));
  final scheme = ColorScheme.fromSeed(seedColor: accent, brightness: brightness).copyWith(
    primary: p.accent,
    onPrimary: Colors.white,
    surface: p.surface,
    onSurface: p.label,
    error: p.danger,
  );

  return ThemeData(
    useMaterial3: true,
    brightness: brightness,
    colorScheme: scheme,
    extensions: [p],
    scaffoldBackgroundColor: p.canvas,
    canvasColor: p.surface,
    textTheme: text,
    splashFactory: NoSplash.splashFactory,
    highlightColor: p.label.withValues(alpha: 0.06),
    hoverColor: p.label.withValues(alpha: 0.04),
    iconTheme: IconThemeData(color: p.accent, size: 24),
    dividerTheme: DividerThemeData(color: p.separator, thickness: 0.5, space: 0.5),
    pageTransitionsTheme: const PageTransitionsTheme(builders: {
      TargetPlatform.android: _AdaptivePageTransitions(),
      TargetPlatform.iOS: _AdaptivePageTransitions(),
      TargetPlatform.windows: _AdaptivePageTransitions(),
      TargetPlatform.macOS: _AdaptivePageTransitions(),
      TargetPlatform.linux: _AdaptivePageTransitions(),
    }),
    actionIconTheme: ActionIconThemeData(
      backButtonIconBuilder: (_) => const Icon(Icons.arrow_back_ios_new_rounded, size: 22),
    ),
    appBarTheme: AppBarTheme(
      backgroundColor: p.canvas,
      foregroundColor: p.accent,
      elevation: 0,
      scrolledUnderElevation: 0,
      surfaceTintColor: Colors.transparent,
      centerTitle: true,
      titleTextStyle: text.titleMedium,
      iconTheme: IconThemeData(color: p.accent),
      actionsIconTheme: IconThemeData(color: p.accent),
    ),
    navigationBarTheme: NavigationBarThemeData(
      height: 64,
      backgroundColor: p.surface,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      indicatorColor: Colors.transparent,
      labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
      iconTheme: WidgetStateProperty.resolveWith(
        (s) => IconThemeData(size: 26, color: s.contains(WidgetState.selected) ? p.accent : p.secondaryLabel),
      ),
      labelTextStyle: WidgetStateProperty.resolveWith(
        (s) => text.labelSmall!.copyWith(color: s.contains(WidgetState.selected) ? p.accent : p.secondaryLabel),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: p.accent,
        foregroundColor: Colors.white,
        disabledBackgroundColor: p.fill,
        disabledForegroundColor: p.secondaryLabel,
        minimumSize: const Size(64, 50),
        shape: radius12,
        textStyle: text.labelLarge,
        elevation: 0,
      ),
    ),
    // "Tinted" secondary button: accent text on a light accent wash, no border.
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        backgroundColor: p.accent.withValues(alpha: 0.12),
        foregroundColor: p.accent,
        disabledForegroundColor: p.secondaryLabel,
        side: BorderSide.none,
        minimumSize: const Size(64, 50),
        shape: radius12,
        textStyle: text.labelLarge,
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: p.accent,
        minimumSize: const Size(48, 48),
        textStyle: text.bodyLarge,
      ),
    ),
    iconButtonTheme: IconButtonThemeData(
      style: IconButton.styleFrom(foregroundColor: p.accent, minimumSize: const Size(48, 48)),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: p.fill,
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      labelStyle: text.bodyLarge!.copyWith(color: p.secondaryLabel),
      floatingLabelStyle: text.bodySmall!.copyWith(color: p.accent),
      hintStyle: text.bodyLarge!.copyWith(color: p.secondaryLabel),
      helperStyle: text.bodySmall,
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide.none),
      enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide.none),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: BorderSide(color: p.accent, width: 1.5),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: BorderSide(color: p.danger, width: 1.5),
      ),
    ),
    listTileTheme: ListTileThemeData(
      contentPadding: const EdgeInsets.symmetric(horizontal: 16),
      minVerticalPadding: 11,
      minTileHeight: 50,
      iconColor: p.accent,
      titleTextStyle: text.bodyLarge,
      subtitleTextStyle: text.bodyMedium,
      leadingAndTrailingTextStyle: text.bodyLarge!.copyWith(color: p.secondaryLabel),
    ),
    bottomSheetTheme: BottomSheetThemeData(
      backgroundColor: p.surface,
      surfaceTintColor: Colors.transparent,
      showDragHandle: true,
      dragHandleColor: p.secondaryLabel.withValues(alpha: 0.4),
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(16))),
    ),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      backgroundColor: p.label,
      contentTextStyle: text.bodyMedium!.copyWith(color: p.surface),
      actionTextColor: p.accent,
      elevation: 0,
      shape: radius12,
    ),
    progressIndicatorTheme: ProgressIndicatorThemeData(color: p.accent, linearTrackColor: p.fill),
    badgeTheme: BadgeThemeData(backgroundColor: p.danger, textColor: Colors.white),
    cupertinoOverrideTheme: CupertinoThemeData(
      brightness: brightness,
      primaryColor: p.accent,
      barBackgroundColor: p.canvas.withValues(alpha: 0.92),
      scaffoldBackgroundColor: p.canvas,
      textTheme: CupertinoTextThemeData(
        primaryColor: p.accent,
        textStyle: text.bodyLarge,
        navLargeTitleTextStyle: text.headlineLarge,
        navTitleTextStyle: text.titleMedium,
        actionTextStyle: text.bodyLarge!.copyWith(color: p.accent),
        pickerTextStyle: text.bodyLarge!.copyWith(fontSize: 21),
        dateTimePickerTextStyle: text.bodyLarge!.copyWith(fontSize: 21),
      ),
    ),
  );
}
