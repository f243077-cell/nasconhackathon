import 'package:flutter/material.dart';

import '../core/format.dart';
import '../core/theme.dart';

/// Shield silhouette from the design: soft top corners, round bottom.
BorderRadius crestRadius(double w, double h) => BorderRadius.only(
      topLeft: Radius.elliptical(w * 0.2, h * 0.16),
      topRight: Radius.elliptical(w * 0.2, h * 0.16),
      bottomLeft: Radius.elliptical(w * 0.5, h * 0.5),
      bottomRight: Radius.elliptical(w * 0.5, h * 0.5),
    );

/// A two-tone shield with initials: a diagonal hard split between [primary] and [secondary].
class CrestShape extends StatelessWidget {
  final String initials;
  final Color primary;
  final Color secondary;
  final Color textColor;
  final double size;
  const CrestShape({
    super.key,
    required this.initials,
    required this.primary,
    required this.secondary,
    this.textColor = Colors.white,
    required this.size,
  });

  @override
  Widget build(BuildContext context) {
    final w = size, h = size * 1.12;
    final radius = crestRadius(w, h);
    return Container(
      width: w,
      height: h,
      padding: EdgeInsets.only(bottom: h * 0.06),
      alignment: Alignment.center,
      decoration: BoxDecoration(
        borderRadius: radius,
        // CSS linear-gradient(155deg, a 0 58%, b 58% 100%)
        gradient: LinearGradient(
          begin: const Alignment(-0.42, -0.91),
          end: const Alignment(0.42, 0.91),
          colors: [primary, primary, secondary, secondary],
          stops: const [0, 0.58, 0.58, 1],
        ),
      ),
      foregroundDecoration: BoxDecoration(
        borderRadius: radius,
        border: Border.all(color: Colors.white.withValues(alpha: 0.3), width: size < 30 ? 1 : 1.5),
      ),
      child: Text(
        initials,
        maxLines: 1,
        style: condensed(size * 0.36, weight: FontWeight.w800, tracking: 0.5, color: textColor, height: 1),
      ),
    );
  }
}

/// Club crest. Uses `assets/crests/<team_id>.png` when bundled; otherwise each club gets a stable
/// two-tone shield with its initials (same club = same crest on every screen).
class TeamCrest extends StatelessWidget {
  final String teamId;
  final String name;
  final double size;
  const TeamCrest({super.key, required this.teamId, required this.name, this.size = 28});

  static const _pairs = [
    (Color(0xFF1D3F8F), Color(0xFFE0B43A)), // royal / gold
    (Color(0xFF2F7D3A), Color(0xFFB8322A)), // pitch / red
    (Color(0xFF1F7A6B), Color(0xFF0E3F37)), // teal
    (Color(0xFFC9542A), Color(0xFF5A1E0E)), // rust
    (Color(0xFF6D28D9), Color(0xFF2E1065)), // violet
    (Color(0xFF9D174D), Color(0xFFF2C14E)), // maroon / amber
    (Color(0xFF0E7490), Color(0xFF082F49)), // ocean
    (Color(0xFF374151), Color(0xFFD1D5DB)), // graphite / silver
  ];

  static (Color, Color) pairFor(String id) =>
      _pairs[id.codeUnits.fold<int>(7, (h, c) => (h * 31 + c) & 0x7fffffff) % _pairs.length];

  /// The club's main colour (headers, avatars).
  static Color colorFor(String id) => pairFor(id).$1;

  /// Real club logos bundled with the app (seeded clubs). Others try `<team_id>.png`.
  static const _logos = {
    'club-alpha-1': 'assets/crests/club-alpha-1.jpg', // Karachi Kings
    'club-alpha-2': 'assets/crests/club-alpha-2.jpg', // Lahore Lions
  };

  @override
  Widget build(BuildContext context) {
    final (a, b) = pairFor(teamId);
    final shield = CrestShape(initials: initialsOf(name), primary: a, secondary: b, size: size);
    return Semantics(
      label: '$name crest',
      image: true,
      excludeSemantics: true,
      child: SizedBox(
        width: size,
        height: size * 1.12,
        child: Image.asset(
          _logos[teamId] ?? 'assets/crests/$teamId.png',
          fit: BoxFit.contain,
          errorBuilder: (_, _, _) => shield,
        ),
      ),
    );
  }
}

/// Match state as text: a breathing dot + LIVE, "FT" for results, the kick-off time for
/// upcoming games, POSTPONED in amber.
class MatchStatusLabel extends StatelessWidget {
  final String status;
  final String? scheduledAt;
  final double fontSize;
  const MatchStatusLabel({super.key, required this.status, this.scheduledAt, this.fontSize = 13});

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    final base = condensed(fontSize, weight: FontWeight.w700, tracking: 1);
    switch (status) {
      case 'in_progress':
        return Row(mainAxisSize: MainAxisSize.min, children: [
          LiveDot(color: p.live, size: fontSize * 0.6),
          SizedBox(width: fontSize * 0.4),
          Text('LIVE', style: base.copyWith(color: p.live)),
        ]);
      case 'completed':
        return Text('FULL TIME', semanticsLabel: 'Full time', style: base.copyWith(color: p.label3));
      case 'upcoming':
        return Text('KICK-OFF ${formatClock(scheduledAt)}', style: base.copyWith(color: p.label3));
      case 'postponed':
        return Text('⏸ POSTPONED', semanticsLabel: 'Postponed', style: base.copyWith(color: p.warning));
      default:
        return Text(humanize(status).toUpperCase(), style: base.copyWith(color: p.warning));
    }
  }
}

class LiveDot extends StatefulWidget {
  final Color color;
  final double size;
  const LiveDot({super.key, required this.color, this.size = 8});

  @override
  State<LiveDot> createState() => _LiveDotState();
}

class _LiveDotState extends State<LiveDot> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(vsync: this, duration: const Duration(milliseconds: 1400));

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (MediaQuery.of(context).disableAnimations) {
      _c.stop();
      _c.value = 1;
    } else if (!_c.isAnimating) {
      _c.repeat(reverse: true);
    }
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => FadeTransition(
        opacity: Tween(begin: 0.35, end: 1.0).animate(CurvedAnimation(parent: _c, curve: Curves.easeInOut)),
        child: Container(
          width: widget.size,
          height: widget.size,
          decoration: BoxDecoration(color: widget.color, shape: BoxShape.circle),
        ),
      );
}
