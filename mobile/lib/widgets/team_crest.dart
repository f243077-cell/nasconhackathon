import 'package:flutter/material.dart';

import '../core/format.dart';
import '../core/theme.dart';

/// Club crest. The API has no club logos yet, so each club gets a stable shield in its own
/// colour with its initials (same club = same crest on every screen).
class TeamCrest extends StatelessWidget {
  final String teamId;
  final String name;
  final double size;
  const TeamCrest({super.key, required this.teamId, required this.name, this.size = 28});

  static const _colors = [
    Color(0xFF0A4DA2), // royal
    Color(0xFFB3261E), // crimson
    Color(0xFF1B7A3D), // pitch green
    Color(0xFF6D28D9), // violet
    Color(0xFFC2410C), // amber
    Color(0xFF0F766E), // teal
    Color(0xFF1F2937), // graphite
    Color(0xFF9D174D), // maroon
  ];

  static Color colorFor(String id) => _colors[id.codeUnits.fold<int>(7, (h, c) => (h * 31 + c) & 0x7fffffff) % _colors.length];

  String get _initials {
    final words = name.split(RegExp(r'\s+')).where((w) => w.isNotEmpty).toList();
    if (words.isEmpty) return '?';
    if (words.length == 1) return words.first.substring(0, words.first.length.clamp(1, 2)).toUpperCase();
    return (words[0][0] + words[1][0]).toUpperCase();
  }

  @override
  Widget build(BuildContext context) {
    final color = colorFor(teamId);
    return Semantics(
      label: '$name crest',
      image: true,
      excludeSemantics: true,
      child: SizedBox(
        width: size,
        height: size * 1.12,
        child: ClipPath(
          clipper: _ShieldClipper(),
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [Color.lerp(color, Colors.white, 0.12)!, color], // light from above, like stitched cloth
              ),
            ),
            child: Center(
              child: Padding(
                padding: EdgeInsets.only(bottom: size * 0.1),
                child: Text(
                  _initials,
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: size * 0.36,
                    fontWeight: FontWeight.w800,
                    letterSpacing: -0.2,
                    height: 1,
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _ShieldClipper extends CustomClipper<Path> {
  @override
  Path getClip(Size s) {
    final w = s.width, h = s.height;
    return Path()
      ..moveTo(w * 0.5, 0)
      ..cubicTo(w * 0.72, h * 0.08, w * 0.88, h * 0.1, w, h * 0.1)
      ..lineTo(w, h * 0.5)
      ..cubicTo(w, h * 0.78, w * 0.74, h * 0.92, w * 0.5, h)
      ..cubicTo(w * 0.26, h * 0.92, 0, h * 0.78, 0, h * 0.5)
      ..lineTo(0, h * 0.1)
      ..cubicTo(w * 0.12, h * 0.1, w * 0.28, h * 0.08, w * 0.5, 0)
      ..close();
  }

  @override
  bool shouldReclip(covariant CustomClipper<Path> oldClipper) => false;
}

/// Match state as text, never a pill: a breathing red dot + LIVE, "FT" for results,
/// the kick-off time for upcoming games.
class MatchStatusLabel extends StatelessWidget {
  final String status;
  final String? scheduledAt;
  final bool large;
  const MatchStatusLabel({super.key, required this.status, this.scheduledAt, this.large = false});

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    final t = Theme.of(context).textTheme;
    final base = (large ? t.labelMedium!.copyWith(fontSize: 14) : t.labelMedium!).copyWith(letterSpacing: 0.4);
    switch (status) {
      case 'in_progress':
        return Row(mainAxisSize: MainAxisSize.min, children: [
          _LiveDot(color: p.live, size: large ? 9 : 7),
          SizedBox(width: large ? 7 : 5),
          Text('LIVE', style: base.copyWith(color: p.live, fontWeight: FontWeight.w800)),
        ]);
      case 'completed':
        return Text('FT', semanticsLabel: 'Full time', style: base.copyWith(color: p.secondaryLabel, fontWeight: FontWeight.w700));
      case 'upcoming':
        final dt = scheduledAt == null ? null : DateTime.tryParse(scheduledAt!)?.toLocal();
        final time = dt == null ? 'TBC' : '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
        return Text(time, style: base.copyWith(color: p.label, fontWeight: FontWeight.w600, fontFeatures: tabular));
      default:
        return Text(humanize(status).toUpperCase(), style: base.copyWith(color: p.warning, fontWeight: FontWeight.w700));
    }
  }
}

class _LiveDot extends StatefulWidget {
  final Color color;
  final double size;
  const _LiveDot({required this.color, required this.size});

  @override
  State<_LiveDot> createState() => _LiveDotState();
}

class _LiveDotState extends State<_LiveDot> with SingleTickerProviderStateMixin {
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
