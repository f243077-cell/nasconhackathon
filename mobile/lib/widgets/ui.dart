import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../core/theme.dart';
import 'sync_status_bar.dart';

// ---------------------------------------------------------------- page chrome

/// Top row of every screen: [leading] on the left, [trailing] on the right, 48 dp tall.
class ScreenHeader extends StatelessWidget {
  final Widget leading;
  final Widget? trailing;
  const ScreenHeader({super.key, required this.leading, this.trailing});

  @override
  Widget build(BuildContext context) => SizedBox(
        height: 48,
        child: Row(children: [leading, const Spacer(), ?trailing]),
      );
}

/// "← BACK". [filled] puts it on a dark translucent capsule for use over hero colour.
class BackChip extends StatelessWidget {
  final String label;
  final bool filled;
  final IconData icon;
  /// Where to go when there is nothing to pop (e.g. a deep link).
  final String fallback;
  const BackChip({super.key, this.label = 'Back', this.filled = false, this.icon = Icons.arrow_back_rounded, this.fallback = '/fixtures'});

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    final color = filled ? p.label : p.label2;
    return Semantics(
      button: true,
      label: label,
      excludeSemantics: true,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () => context.canPop() ? context.pop() : context.go(fallback),
        child: Container(
          height: 40,
          padding: EdgeInsets.only(left: filled ? 10 : 0, right: filled ? 14 : 8),
          decoration: filled
              ? BoxDecoration(color: p.canvas.withValues(alpha: 0.55), borderRadius: BorderRadius.circular(20))
              : null,
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            Icon(icon, size: 18, color: color),
            const SizedBox(width: 6),
            Text(label.toUpperCase(), style: condensed(14, weight: FontWeight.w600, tracking: 1, color: color)),
          ]),
        ),
      ),
    );
  }
}

/// Kicker line + huge condensed title ("ALPHA PREMIER LEAGUE ▾" / "FIXTURES").
class PageTitle extends StatelessWidget {
  final String title;
  final String? kicker;
  final VoidCallback? onKickerTap;
  final Widget? trailing;
  final double size;
  const PageTitle({super.key, required this.title, this.kicker, this.onKickerTap, this.trailing, this.size = 44});

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    Widget? k;
    if (kicker != null) {
      final text = Text(
        kicker!.toUpperCase() + (onKickerTap != null ? ' ▾' : ''),
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: condensed(13, weight: FontWeight.w600, tracking: 1.5, color: onKickerTap != null ? p.label2 : p.label3),
      );
      k = onKickerTap == null
          ? text
          : Semantics(
              button: true,
              hint: 'Change league',
              child: InkWell(
                onTap: onKickerTap,
                child: ConstrainedBox(constraints: const BoxConstraints(minHeight: 32), child: Align(alignment: Alignment.centerLeft, widthFactor: 1, child: text)),
              ),
            );
    }
    return Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
      Expanded(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
          ?k,
          Semantics(
            header: true,
            child: Text(title.toUpperCase(), style: condensed(size, weight: FontWeight.w800, color: p.label, height: 1)),
          ),
        ]),
      ),
      ?trailing,
    ]);
  }
}

/// Root page of a tab: status pill + [headerTrailing], title, pull to refresh, then content slivers.
/// Leaves room at the bottom for the floating pill nav.
class TabPage extends StatelessWidget {
  final String title;
  final String? kicker;
  final VoidCallback? onKickerTap;
  final Widget? headerTrailing;
  final Future<void> Function()? onRefresh;
  final List<Widget> slivers;

  const TabPage({
    super.key,
    required this.title,
    required this.slivers,
    this.kicker,
    this.onKickerTap,
    this.headerTrailing,
    this.onRefresh,
  });

  @override
  Widget build(BuildContext context) {
    final bottom = MediaQuery.paddingOf(context).bottom;
    final scroll = CustomScrollView(slivers: [
      SliverPadding(
        padding: const EdgeInsets.fromLTRB(20, 4, 20, 0),
        sliver: SliverMainAxisGroup(slivers: [
          SliverToBoxAdapter(child: ScreenHeader(leading: const StatusPill(), trailing: headerTrailing)),
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.only(top: 8, bottom: 16),
              child: PageTitle(title: title, kicker: kicker, onKickerTap: onKickerTap),
            ),
          ),
          ...slivers,
        ]),
      ),
      SliverToBoxAdapter(child: SizedBox(height: bottom + 24)),
    ]);
    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: onRefresh == null
            ? scroll
            : RefreshIndicator(
                onRefresh: onRefresh!,
                color: context.palette.onAccent,
                backgroundColor: context.palette.accent,
                child: scroll,
              ),
      ),
    );
  }
}

/// A pushed screen on the plain canvas: back chip + status pill, big title, scrolling body,
/// optional sticky actions at the bottom.
class FlatPage extends StatelessWidget {
  final String title;
  final String backLabel;
  final IconData backIcon;
  final String backFallback;
  final Widget? titleTrailing;
  final List<Widget> children;
  final List<Widget>? actions;
  final Future<void> Function()? onRefresh;
  final double titleSize;
  final bool statusLinksToQueue;

  const FlatPage({
    super.key,
    required this.title,
    required this.children,
    this.backLabel = 'Back',
    this.backIcon = Icons.arrow_back_rounded,
    this.backFallback = '/fixtures',
    this.titleTrailing,
    this.actions,
    this.onRefresh,
    this.titleSize = 40,
    this.statusLinksToQueue = true,
  });

  @override
  Widget build(BuildContext context) {
    final list = ListView(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
      children: [
        Padding(
          padding: const EdgeInsets.only(top: 4, bottom: 16),
          child: PageTitle(title: title, size: titleSize, trailing: titleTrailing),
        ),
        ...children,
      ],
    );
    return Scaffold(
      bottomNavigationBar: actions == null ? null : BottomActionBar(children: actions!),
      body: SafeArea(
        bottom: actions == null,
        child: Column(children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 4, 20, 0),
            child: ScreenHeader(
              leading: BackChip(label: backLabel, icon: backIcon, fallback: backFallback),
              trailing: StatusPill(linkToQueue: statusLinksToQueue),
            ),
          ),
          Expanded(
            child: onRefresh == null
                ? list
                : RefreshIndicator(
                    onRefresh: onRefresh!,
                    color: context.palette.onAccent,
                    backgroundColor: context.palette.accent,
                    child: list,
                  ),
          ),
        ]),
      ),
    );
  }
}

/// Sticky bottom area for a screen's main action (one-handed reach). Fades the content behind it.
class BottomActionBar extends StatelessWidget {
  final List<Widget> children;
  const BottomActionBar({super.key, required this.children});

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [p.canvas.withValues(alpha: 0), p.canvas, p.canvas],
          stops: const [0, 0.25, 1],
        ),
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 14),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            for (var i = 0; i < children.length; i++) ...[if (i > 0) const SizedBox(height: 10), children[i]],
          ]),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------- buttons

/// Full-width accent action: 56 dp, condensed caps. Shows a spinner while busy.
class PrimaryButton extends StatelessWidget {
  final String label;
  final VoidCallback? onPressed;
  final bool loading;
  final IconData? icon;
  final double height;

  const PrimaryButton({super.key, required this.label, this.onPressed, this.loading = false, this.icon, this.height = 56});

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    final enabled = onPressed != null && !loading;
    final fg = enabled || loading ? p.onAccent : p.muted;
    return Semantics(
      button: true,
      enabled: enabled,
      label: label,
      excludeSemantics: true,
      child: Material(
        color: enabled || loading ? p.accent : p.raised,
        borderRadius: BorderRadius.circular(12),
        child: InkWell(
          borderRadius: BorderRadius.circular(12),
          onTap: enabled ? onPressed : null,
          child: SizedBox(
            height: height,
            width: double.infinity,
            child: Center(
              child: loading
                  ? CupertinoActivityIndicator(color: p.onAccent)
                  : Row(mainAxisSize: MainAxisSize.min, children: [
                      if (icon != null) ...[Icon(icon, size: 20, color: fg), const SizedBox(width: 8)],
                      Flexible(
                        child: Text(
                          label.toUpperCase(),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: condensed(height >= 56 ? 20 : 17, weight: FontWeight.w800, tracking: 1.5, color: fg),
                        ),
                      ),
                    ]),
            ),
          ),
        ),
      ),
    );
  }
}

/// Full-width outline action. [strong] uses a light border (the design's "Add to cart").
class SecondaryButton extends StatelessWidget {
  final String label;
  final VoidCallback? onPressed;
  final IconData? icon;
  final bool destructive;
  final bool strong;
  final double height;

  const SecondaryButton({
    super.key,
    required this.label,
    this.onPressed,
    this.icon,
    this.destructive = false,
    this.strong = false,
    this.height = 52,
  });

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    final enabled = onPressed != null;
    final color = !enabled ? p.muted : (destructive ? p.danger : p.label);
    final border = !enabled ? p.raised : (destructive ? p.danger : (strong ? p.label : p.border));
    return Semantics(
      button: true,
      enabled: enabled,
      label: label,
      excludeSemantics: true,
      child: Material(
        color: Colors.transparent,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12), side: BorderSide(color: border)),
        child: InkWell(
          borderRadius: BorderRadius.circular(12),
          onTap: onPressed,
          child: SizedBox(
            height: height,
            width: double.infinity,
            child: Center(
              child: Row(mainAxisSize: MainAxisSize.min, children: [
                if (icon != null) ...[Icon(icon, size: 18, color: color), const SizedBox(width: 8)],
                Flexible(
                  child: Text(
                    label.toUpperCase(),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: condensed(16, weight: FontWeight.w700, tracking: 1, color: color),
                  ),
                ),
              ]),
            ),
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------- surfaces & text

/// Rounded card on the canvas.
class Panel extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry padding;
  final Color? borderColor;
  final VoidCallback? onTap;
  final Color? color;
  const Panel({super.key, required this.child, this.padding = const EdgeInsets.all(16), this.borderColor, this.onTap, this.color});

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    return Material(
      color: color ?? p.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: borderColor == null ? BorderSide.none : BorderSide(color: borderColor!),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(onTap: onTap, child: Padding(padding: padding, child: child)),
    );
  }
}

/// Small caps label above a group ("SIZE", "PAY WITH").
class SectionLabel extends StatelessWidget {
  final String text;
  final Widget? trailing;
  final EdgeInsetsGeometry padding;
  const SectionLabel(this.text, {super.key, this.trailing, this.padding = const EdgeInsets.only(bottom: 8)});

  @override
  Widget build(BuildContext context) => Padding(
        padding: padding,
        child: Row(children: [
          Expanded(
            child: Semantics(
              header: true,
              child: Text(text.toUpperCase(), style: condensed(13, weight: FontWeight.w600, tracking: 1, color: context.palette.label3)),
            ),
          ),
          ?trailing,
        ]),
      );
}

/// Caps label over a field, as in the design's forms.
class LabeledField extends StatelessWidget {
  final String label;
  final Widget child;
  const LabeledField({super.key, required this.label, required this.child});

  @override
  Widget build(BuildContext context) => Column(crossAxisAlignment: CrossAxisAlignment.stretch, mainAxisSize: MainAxisSize.min, children: [
        Text(label.toUpperCase(), style: condensed(13, weight: FontWeight.w600, tracking: 1, color: context.palette.label2)),
        const SizedBox(height: 6),
        child,
      ]);
}

/// A tappable field-looking row that opens a picker (player, club, date).
class PickerField extends StatelessWidget {
  final Widget? leading;
  final String text;
  final String? detail;
  final bool placeholder;
  final VoidCallback? onTap;
  final IconData trailingIcon;
  const PickerField({
    super.key,
    this.leading,
    required this.text,
    this.detail,
    this.placeholder = false,
    this.onTap,
    this.trailingIcon = Icons.keyboard_arrow_down_rounded,
  });

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    return Semantics(
      button: true,
      label: '$text${detail == null ? '' : ', $detail'}',
      excludeSemantics: true,
      child: Material(
        color: p.canvas,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12), side: BorderSide(color: p.border)),
        child: InkWell(
          borderRadius: BorderRadius.circular(12),
          onTap: onTap,
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: 56),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 14),
              child: Row(children: [
                if (leading != null) ...[leading!, const SizedBox(width: 12)],
                Expanded(
                  child: Text.rich(
                    TextSpan(children: [
                      TextSpan(text: text, style: TextStyle(color: placeholder ? p.muted : p.label)),
                      if (detail != null) TextSpan(text: ' · $detail', style: TextStyle(color: p.label3)),
                    ]),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 16),
                  ),
                ),
                Icon(trailingIcon, color: p.label3),
              ]),
            ),
          ),
        ),
      ),
    );
  }
}

/// Small caps badge: "3 LEFT", "C", "PENDING".
class Tag extends StatelessWidget {
  final String text;
  final Color color;
  final Color? textColor;
  final bool outlined;
  final double fontSize;
  const Tag(this.text, {super.key, required this.color, this.textColor, this.outlined = false, this.fontSize = 11});

  @override
  Widget build(BuildContext context) => Container(
        padding: EdgeInsets.symmetric(horizontal: 7, vertical: outlined ? 2 : 3),
        decoration: BoxDecoration(
          color: outlined ? null : color,
          border: outlined ? Border.all(color: color) : null,
          borderRadius: BorderRadius.circular(4),
        ),
        child: Text(
          text.toUpperCase(),
          style: condensed(fontSize, weight: FontWeight.w700, tracking: 1, color: textColor ?? (outlined ? color : context.palette.canvas)),
        ),
      );
}

/// A label/value row for summaries (subtotal, totals, details).
class ValueRow extends StatelessWidget {
  final String label;
  final String value;
  final bool emphasized;
  final Color? valueColor;
  const ValueRow(this.label, this.value, {super.key, this.emphasized = false, this.valueColor});

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    if (emphasized) {
      return Container(
        padding: const EdgeInsets.only(top: 10),
        decoration: BoxDecoration(border: Border(top: BorderSide(color: p.raised))),
        child: Row(crossAxisAlignment: CrossAxisAlignment.baseline, textBaseline: TextBaseline.alphabetic, children: [
          Expanded(child: Text(label.toUpperCase(), style: condensed(15, weight: FontWeight.w700, tracking: 1, color: p.label))),
          Text(value, style: condensed(28, weight: FontWeight.w800, color: valueColor ?? p.label)),
        ]),
      );
    }
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(children: [
        Expanded(child: Text(label, style: TextStyle(fontSize: 15, color: p.label2))),
        Text(value, style: TextStyle(fontSize: 15, color: valueColor ?? p.label, fontFeatures: tabular)),
      ]),
    );
  }
}

// ---------------------------------------------------------------- selection controls

/// Horizontal capsule filter (store categories). Selected = accent fill.
class PillChips<T> extends StatelessWidget {
  final T value;
  final Map<T, String> options;
  final ValueChanged<T> onChanged;
  const PillChips({super.key, required this.value, required this.options, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      clipBehavior: Clip.none,
      child: Row(children: [
        for (final e in options.entries) ...[
          Semantics(
            button: true,
            selected: e.key == value,
            label: e.value,
            excludeSemantics: true,
            child: GestureDetector(
              onTap: () => onChanged(e.key),
              child: Container(
                height: 40,
                padding: const EdgeInsets.symmetric(horizontal: 16),
                margin: const EdgeInsets.only(right: 8, top: 4, bottom: 4),
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: e.key == value ? p.accent : null,
                  border: e.key == value ? null : Border.all(color: p.border),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text(
                  e.value.toUpperCase(),
                  style: condensed(14, weight: FontWeight.w700, tracking: 1, color: e.key == value ? p.onAccent : p.label),
                ),
              ),
            ),
          ),
        ],
      ]),
    );
  }
}

/// Underlined text tabs ("TIMELINE  LINEUPS  STATS").
class UnderlineTabs extends StatelessWidget {
  final List<String> labels;
  final int index;
  final ValueChanged<int> onChanged;
  final EdgeInsetsGeometry padding;
  const UnderlineTabs({super.key, required this.labels, required this.index, required this.onChanged, this.padding = const EdgeInsets.symmetric(horizontal: 20)});

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    return Container(
      decoration: BoxDecoration(border: Border(bottom: BorderSide(color: p.raised))),
      padding: padding,
      child: Row(children: [
        for (var i = 0; i < labels.length; i++)
          Semantics(
            button: true,
            selected: i == index,
            label: labels[i],
            excludeSemantics: true,
            child: GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: () => onChanged(i),
              child: Container(
                margin: const EdgeInsets.only(right: 22),
                padding: const EdgeInsets.symmetric(vertical: 12),
                decoration: BoxDecoration(
                  border: Border(bottom: BorderSide(color: i == index ? p.accent : Colors.transparent, width: 3)),
                ),
                child: Text(
                  labels[i].toUpperCase(),
                  style: condensed(15, weight: FontWeight.w700, tracking: 1, color: i == index ? p.accent : p.label3),
                ),
              ),
            ),
          ),
      ]),
    );
  }
}

/// Segmented control on a dark track with an accent thumb (roster action type, team picker).
class SegmentedPills<T> extends StatelessWidget {
  final T value;
  final Map<T, String> options;
  final ValueChanged<T> onChanged;
  const SegmentedPills({super.key, required this.value, required this.options, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    return Container(
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(color: p.canvas, borderRadius: BorderRadius.circular(12)),
      child: Row(children: [
        for (final e in options.entries)
          Expanded(
            child: Semantics(
              button: true,
              selected: e.key == value,
              label: e.value,
              excludeSemantics: true,
              child: GestureDetector(
                onTap: () => onChanged(e.key),
                child: AnimatedContainer(
                  duration: MediaQuery.of(context).disableAnimations ? Duration.zero : const Duration(milliseconds: 180),
                  height: 40,
                  margin: const EdgeInsets.symmetric(horizontal: 2),
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: e.key == value ? p.accent : Colors.transparent,
                    borderRadius: BorderRadius.circular(9),
                  ),
                  child: Text(
                    e.value.toUpperCase(),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: condensed(14, weight: FontWeight.w700, tracking: 1, color: e.key == value ? p.onAccent : p.label2),
                  ),
                ),
              ),
            ),
          ),
      ]),
    );
  }
}

/// Bordered − n + stepper.
class QuantityStepper extends StatelessWidget {
  final int value;
  final int max;
  final int min;
  final ValueChanged<int> onChanged;
  final String Function(int)? format;
  const QuantityStepper({super.key, required this.value, required this.onChanged, this.max = 10, this.min = 1, this.format});

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    Widget btn(IconData icon, String tip, VoidCallback? onTap) => Semantics(
          button: true,
          enabled: onTap != null,
          label: tip,
          excludeSemantics: true,
          child: InkWell(
            onTap: onTap,
            borderRadius: BorderRadius.circular(10),
            child: SizedBox(width: 40, height: 48, child: Icon(icon, size: 18, color: onTap == null ? p.muted : p.label)),
          ),
        );
    return Container(
      decoration: BoxDecoration(border: Border.all(color: p.border), borderRadius: BorderRadius.circular(10)),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        btn(Icons.remove_rounded, 'Decrease', value > min ? () => onChanged(value - 1) : null),
        ConstrainedBox(
          constraints: const BoxConstraints(minWidth: 24),
          child: Text(
            format?.call(value) ?? '$value',
            textAlign: TextAlign.center,
            style: condensed(18, weight: FontWeight.w700, color: p.label),
          ),
        ),
        btn(Icons.add_rounded, 'Increase', value < max ? () => onChanged(value + 1) : null),
      ]),
    );
  }
}

// ---------------------------------------------------------------- media

/// Product image when the API has one, else neutral artwork by type.
class ProductArtwork extends StatelessWidget {
  final String type;
  final String? imageUrl;
  final double iconSize;
  const ProductArtwork({super.key, required this.type, this.imageUrl, this.iconSize = 44});

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    final icon = switch (type) {
      'apparel' => Icons.checkroom_rounded,
      'digital' => Icons.wallpaper_rounded,
      _ => Icons.sports_soccer_rounded,
    };
    final placeholder = DecoratedBox(
      decoration: BoxDecoration(
        gradient: RadialGradient(
          center: const Alignment(0, -0.4),
          radius: 1.1,
          colors: [p.raised, p.surface],
        ),
      ),
      child: Center(child: Icon(icon, size: iconSize, color: p.muted, semanticLabel: 'Product image')),
    );
    final url = imageUrl;
    if (url == null) return placeholder;
    // Seeded products point at /static/<name>.png; those pictures ship with the app (assets/products/).
    if (url.startsWith('/')) {
      final name = url.split('/').last;
      return Image.asset('assets/products/$name', fit: BoxFit.cover, errorBuilder: (_, _, _) => placeholder);
    }
    return Image.network(url, fit: BoxFit.cover, errorBuilder: (_, _, _) => placeholder);
  }
}

/// Night-pitch backdrop: floodlight glow over mown stripes and the centre circle.
class PitchBackdrop extends StatelessWidget {
  final Color glow;
  const PitchBackdrop({super.key, required this.glow});

  @override
  Widget build(BuildContext context) => CustomPaint(painter: _PitchPainter(glow, context.palette.canvas));
}

class _PitchPainter extends CustomPainter {
  final Color glow;
  final Color canvas;
  _PitchPainter(this.glow, this.canvas);

  @override
  void paint(Canvas c, Size s) {
    final rect = Offset.zero & s;
    c.drawRect(rect, Paint()..color = const Color(0xFF13180F));
    final stripe = Paint()..color = const Color(0xFF182012);
    for (var x = 0.0; x < s.width; x += 72) {
      c.drawRect(Rect.fromLTWH(x, 0, 36, s.height), stripe);
    }
    final line = Paint()
      ..color = Colors.white.withValues(alpha: 0.10)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2;
    c.drawLine(Offset(0, s.height * 0.62), Offset(s.width, s.height * 0.62), line);
    c.drawCircle(Offset(s.width / 2, s.height * 0.62), s.width * 0.22, line);
    for (final x in [0.08, 0.92]) {
      c.drawCircle(
        Offset(s.width * x, 0),
        s.width * 0.7,
        Paint()
          ..shader = RadialGradient(colors: [glow.withValues(alpha: 0.35), glow.withValues(alpha: 0)])
              .createShader(Rect.fromCircle(center: Offset(s.width * x, 0), radius: s.width * 0.7)),
      );
    }
  }

  @override
  bool shouldRepaint(_PitchPainter old) => old.glow != glow;
}

// ---------------------------------------------------------------- sheets & pickers

/// Bottom sheet with a caps title and a list of choices. Returns the chosen value.
Future<T?> showChoiceSheet<T>(
  BuildContext context, {
  required String title,
  String? message,
  required List<(T, String)> options,
  T? selected,
  Widget Function(T value)? leading,
}) {
  return showModalBottomSheet<T>(
    context: context,
    isScrollControlled: true,
    useSafeArea: true,
    builder: (ctx) {
      final p = ctx.palette;
      return ConstrainedBox(
        constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(ctx).height * 0.75),
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 0, 20, 8),
            child: Text(title.toUpperCase(), style: condensed(28, weight: FontWeight.w800, color: p.label)),
          ),
          if (message != null)
            Padding(padding: const EdgeInsets.fromLTRB(20, 0, 20, 8), child: Text(message, style: TextStyle(color: p.label2))),
          Flexible(
            child: ListView(shrinkWrap: true, padding: const EdgeInsets.fromLTRB(8, 4, 8, 16), children: [
              for (final (value, label) in options)
                ListTile(
                  minTileHeight: 52,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  leading: leading?.call(value),
                  title: Text(label, style: TextStyle(fontSize: 16, color: p.label)),
                  trailing: value == selected ? Icon(Icons.check_rounded, color: p.accent, semanticLabel: 'Selected') : null,
                  onTap: () => Navigator.pop(ctx, value),
                ),
            ]),
          ),
        ]),
      );
    },
  );
}

/// Date picker in a dark bottom popup with Cancel / Done.
Future<DateTime?> pickDate(BuildContext context, DateTime initial) {
  var chosen = initial;
  final p = context.palette;
  return showCupertinoModalPopup<DateTime>(
    context: context,
    builder: (ctx) => Container(
      height: 320,
      decoration: BoxDecoration(color: p.surface, borderRadius: const BorderRadius.vertical(top: Radius.circular(20))),
      child: SafeArea(
        top: false,
        child: Column(children: [
          Row(children: [
            TextButton(onPressed: () => Navigator.pop(ctx), child: Text('CANCEL', style: TextStyle(color: p.label2))),
            const Spacer(),
            TextButton(onPressed: () => Navigator.pop(ctx, chosen), child: const Text('DONE')),
          ]),
          Expanded(
            child: CupertinoTheme(
              data: CupertinoThemeData(
                brightness: Brightness.dark,
                textTheme: CupertinoTextThemeData(dateTimePickerTextStyle: TextStyle(color: p.label, fontSize: 21)),
              ),
              child: CupertinoDatePicker(
                mode: CupertinoDatePickerMode.date,
                initialDateTime: initial,
                minimumYear: 2020,
                maximumYear: 2035,
                onDateTimeChanged: (d) => chosen = d,
              ),
            ),
          ),
        ]),
      ),
    ),
  );
}
