import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

import '../core/theme.dart';

/// Root page of a tab: iOS large title that collapses on scroll, pull to refresh, then content slivers.
class LargeTitlePage extends StatelessWidget {
  final String title;
  final Widget? trailing;
  final Future<void> Function()? onRefresh;
  final List<Widget> slivers;

  const LargeTitlePage({super.key, required this.title, required this.slivers, this.trailing, this.onRefresh});

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    return Scaffold(
      body: CustomScrollView(
        slivers: [
          CupertinoSliverNavigationBar(
            largeTitle: Text(title),
            trailing: trailing,
            automaticallyImplyLeading: false,
            transitionBetweenRoutes: false,
            backgroundColor: p.canvas.withValues(alpha: 0.92),
            border: Border(bottom: BorderSide(color: p.separator, width: 0.5)),
          ),
          if (onRefresh != null) CupertinoSliverRefreshControl(onRefresh: onRefresh),
          ...slivers,
          const SliverToBoxAdapter(child: SizedBox(height: 32)),
        ],
      ),
    );
  }
}

/// Inset grouped section (lists-and-tables.md › grouped style): optional header and footer,
/// rows on one rounded surface, inset hairlines between rows. No borders, no shadows.
class Section extends StatelessWidget {
  final String? header;
  final String? footer;
  final List<Widget> children;
  final double dividerIndent;

  const Section({super.key, this.header, this.footer, required this.children, this.dividerIndent = 16});

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    final t = Theme.of(context).textTheme;
    final rows = <Widget>[];
    for (var i = 0; i < children.length; i++) {
      if (i > 0) rows.add(Divider(indent: dividerIndent));
      rows.add(children[i]);
    }
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 28),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        if (header != null)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
            child: Semantics(header: true, child: Text(header!, style: t.bodySmall!.copyWith(fontWeight: FontWeight.w600))),
          ),
        ClipRRect(
          borderRadius: BorderRadius.circular(12),
          child: Material(color: p.surface, child: Column(children: rows)),
        ),
        if (footer != null)
          Padding(padding: const EdgeInsets.fromLTRB(16, 8, 16, 0), child: Text(footer!, style: t.bodySmall)),
      ]),
    );
  }
}

/// Full-width primary action. Shows a spinner in place of the label while busy.
class PrimaryButton extends StatelessWidget {
  final String label;
  final VoidCallback? onPressed;
  final bool loading;
  final IconData? icon;

  const PrimaryButton({super.key, required this.label, this.onPressed, this.loading = false, this.icon});

  @override
  Widget build(BuildContext context) {
    final child = loading
        ? const CupertinoActivityIndicator(color: Colors.white)
        : Row(mainAxisSize: MainAxisSize.min, children: [
            if (icon != null) ...[Icon(icon, size: 20), const SizedBox(width: 8)],
            Flexible(child: Text(label, overflow: TextOverflow.ellipsis)),
          ]);
    return SizedBox(
      width: double.infinity,
      child: FilledButton(onPressed: loading ? null : onPressed, child: child),
    );
  }
}

/// Full-width secondary action (tinted).
class SecondaryButton extends StatelessWidget {
  final String label;
  final VoidCallback? onPressed;
  final IconData? icon;
  final bool destructive;

  const SecondaryButton({super.key, required this.label, this.onPressed, this.icon, this.destructive = false});

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    final style = destructive
        ? OutlinedButton.styleFrom(backgroundColor: p.danger.withValues(alpha: 0.12), foregroundColor: p.danger)
        : null;
    return SizedBox(
      width: double.infinity,
      child: OutlinedButton(
        style: style,
        onPressed: onPressed,
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          if (icon != null) ...[Icon(icon, size: 20), const SizedBox(width: 8)],
          Flexible(child: Text(label, overflow: TextOverflow.ellipsis)),
        ]),
      ),
    );
  }
}

/// Sticky bottom bar for a screen's main action (one-handed reach).
class BottomActionBar extends StatelessWidget {
  final List<Widget> children;
  const BottomActionBar({super.key, required this.children});

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: p.surface,
        border: Border(top: BorderSide(color: p.separator, width: 0.5)),
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            for (var i = 0; i < children.length; i++) ...[if (i > 0) const SizedBox(height: 10), children[i]],
          ]),
        ),
      ),
    );
  }
}

/// iOS segmented control. Keys are values, labels are text.
class Segmented<T extends Object> extends StatelessWidget {
  final T value;
  final Map<T, String> options;
  final ValueChanged<T> onChanged;

  const Segmented({super.key, required this.value, required this.options, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    final style = Theme.of(context).textTheme.labelMedium;
    return SizedBox(
      width: double.infinity,
      child: CupertinoSlidingSegmentedControl<T>(
        groupValue: value,
        backgroundColor: p.fill,
        thumbColor: p.surface,
        padding: const EdgeInsets.all(3),
        children: {
          for (final e in options.entries)
            e.key: Padding(
              padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 4),
              child: Text(e.value, style: style, maxLines: 1, overflow: TextOverflow.ellipsis),
            ),
        },
        onValueChanged: (v) => v == null ? null : onChanged(v),
      ),
    );
  }
}

/// Selectable capsule (variant sizes and colours). Selected = accent wash + accent outline + check.
class OptionPill extends StatelessWidget {
  final String label;
  final bool selected;
  final VoidCallback? onTap; // null = unavailable

  const OptionPill({super.key, required this.label, required this.selected, this.onTap});

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    final t = Theme.of(context).textTheme;
    final enabled = onTap != null;
    return Semantics(
      button: true,
      selected: selected,
      enabled: enabled,
      child: Material(
        color: selected ? p.accent.withValues(alpha: 0.12) : p.surface,
        shape: StadiumBorder(side: BorderSide(color: selected ? p.accent : p.separator, width: selected ? 1.5 : 1)),
        child: InkWell(
          customBorder: const StadiumBorder(),
          onTap: onTap,
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: 44, minWidth: 56),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Row(mainAxisSize: MainAxisSize.min, mainAxisAlignment: MainAxisAlignment.center, children: [
                if (selected) ...[Icon(Icons.check_rounded, size: 16, color: p.accent), const SizedBox(width: 6)],
                Text(
                  label,
                  style: t.bodyLarge!.copyWith(
                    color: !enabled ? p.secondaryLabel : (selected ? p.accent : p.label),
                    decoration: enabled ? null : TextDecoration.lineThrough,
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

/// iOS-style quantity stepper: one rounded fill, minus and plus halves.
class QuantityStepper extends StatelessWidget {
  final int value;
  final int max;
  final ValueChanged<int> onChanged;
  const QuantityStepper({super.key, required this.value, required this.onChanged, this.max = 10});

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    return Container(
      decoration: BoxDecoration(color: p.fill, borderRadius: BorderRadius.circular(10)),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        IconButton(
          tooltip: 'Decrease quantity',
          onPressed: value > 1 ? () => onChanged(value - 1) : null,
          icon: const Icon(Icons.remove_rounded),
        ),
        SizedBox(
          width: 32,
          child: Text(
            '$value',
            textAlign: TextAlign.center,
            semanticsLabel: 'Quantity $value',
            style: Theme.of(context).textTheme.titleMedium!.copyWith(fontFeatures: tabular),
          ),
        ),
        IconButton(
          tooltip: 'Increase quantity',
          onPressed: value < max ? () => onChanged(value + 1) : null,
          icon: const Icon(Icons.add_rounded),
        ),
      ]),
    );
  }
}

/// A label/value row for summaries (subtotal, totals, details).
class ValueRow extends StatelessWidget {
  final String label;
  final String value;
  final bool emphasized;
  const ValueRow(this.label, this.value, {super.key, this.emphasized = false});

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    final style = emphasized ? t.titleMedium : t.bodyLarge;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 13),
      child: Row(children: [
        Expanded(child: Text(label, style: style)),
        Text(
          value,
          style: (emphasized ? style : style!.copyWith(color: context.palette.secondaryLabel))!
              .copyWith(fontFeatures: tabular),
        ),
      ]),
    );
  }
}

/// Neutral placeholder artwork for products without images (by type, one icon family).
class ProductArtwork extends StatelessWidget {
  final String type;
  final double iconSize;
  const ProductArtwork({super.key, required this.type, this.iconSize = 44});

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    final icon = switch (type) {
      'apparel' => Icons.checkroom_rounded,
      'digital' => Icons.image_rounded,
      _ => Icons.shopping_bag_rounded,
    };
    return ColoredBox(
      color: p.fill,
      child: Center(child: Icon(icon, size: iconSize, color: p.secondaryLabel, semanticLabel: 'Product image')),
    );
  }
}

/// Date picker in an iOS bottom popup with Cancel / Done.
Future<DateTime?> pickDate(BuildContext context, DateTime initial) {
  var chosen = initial;
  final p = context.palette;
  return showCupertinoModalPopup<DateTime>(
    context: context,
    builder: (ctx) => Container(
      height: 320,
      color: p.surface,
      child: SafeArea(
        top: false,
        child: Column(children: [
          Row(children: [
            TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
            const Spacer(),
            TextButton(
              onPressed: () => Navigator.pop(ctx, chosen),
              child: const Text('Done', style: TextStyle(fontWeight: FontWeight.w600)),
            ),
          ]),
          Expanded(
            child: CupertinoDatePicker(
              mode: CupertinoDatePickerMode.date,
              initialDateTime: initial,
              minimumYear: 2020,
              maximumYear: 2035,
              onDateTimeChanged: (d) => chosen = d,
            ),
          ),
        ]),
      ),
    ),
  );
}
