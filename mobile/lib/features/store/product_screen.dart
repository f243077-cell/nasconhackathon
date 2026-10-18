import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/format.dart';
import '../../core/theme.dart';
import '../../data/models.dart';
import '../../data/repository.dart';
import '../../widgets/async_view.dart';
import '../../widgets/sync_status_bar.dart';
import '../../widgets/ui.dart';
import 'cart.dart';

/// Full-bleed artwork, name, price, size grid and colour swatches; Add to cart / Buy now
/// stay within thumb reach at the bottom.
class ProductScreen extends ConsumerStatefulWidget {
  final String productId;
  const ProductScreen({super.key, required this.productId});

  @override
  ConsumerState<ProductScreen> createState() => _ProductScreenState();
}

class _ProductScreenState extends ConsumerState<ProductScreen> {
  String? _size;
  String? _color;
  String? _variantId; // only for products whose options have neither size nor colour
  bool _initialised = false;

  static const _typeLabels = {'apparel': 'Apparel', 'accessory': 'Gear', 'digital': 'Digital'};

  void _init(Product prod) {
    if (_initialised) return;
    _initialised = true;
    final first = prod.variants.where((v) => v.stock > 0).firstOrNull ?? prod.variants.firstOrNull;
    _size = first?.size;
    _color = first?.color;
    _variantId = first?.variantId;
  }

  Variant? _selected(Product prod) {
    final hasAttrs = prod.variants.any((v) => v.size != null || v.color != null);
    if (!hasAttrs) return prod.variants.where((v) => v.variantId == _variantId).firstOrNull;
    return prod.variants.where((v) => v.size == _size && v.color == _color).firstOrNull;
  }

  /// When a size/colour pair doesn't exist, keep the tap and snap the other attribute to one that does.
  void _pickSize(Product prod, String size) => setState(() {
        _size = size;
        if (!prod.variants.any((v) => v.size == size && v.color == _color)) {
          _color = (prod.variants.where((v) => v.size == size && v.stock > 0).firstOrNull ??
                  prod.variants.firstWhere((v) => v.size == size))
              .color;
        }
      });

  void _pickColor(Product prod, String color) => setState(() {
        _color = color;
        if (!prod.variants.any((v) => v.color == color && v.size == _size)) {
          _size = (prod.variants.where((v) => v.color == color && v.stock > 0).firstOrNull ??
                  prod.variants.firstWhere((v) => v.color == color))
              .size;
        }
      });

  @override
  Widget build(BuildContext context) {
    final product = ref.watch(productProvider(widget.productId));
    final prod = product.value;
    if (prod != null) _init(prod);
    final variant = prod == null ? null : _selected(prod);
    final inStock = variant != null && variant.stock > 0;

    return Scaffold(
      bottomNavigationBar: prod == null
          ? null
          : BottomActionBar(children: [
              Row(children: [
                Expanded(
                  flex: 10,
                  child: SecondaryButton(
                    label: 'Add to cart',
                    strong: true,
                    height: 56,
                    onPressed: !inStock
                        ? null
                        : () {
                            ref.read(cartProvider.notifier).add(prod, variant, 1);
                            showSuccess(context, 'Added to cart.');
                          },
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  flex: 14,
                  child: PrimaryButton(
                    label: inStock ? 'Buy now' : 'Sold out',
                    onPressed: !inStock
                        ? null
                        : () {
                            ref.read(cartProvider.notifier).add(prod, variant, 1);
                            context.push('/cart');
                          },
                  ),
                ),
              ]),
            ]),
      body: AsyncView<Product>(
        value: product,
        onRetry: () => ref.invalidate(productsProvider),
        builder: (prod) => ListView(padding: EdgeInsets.zero, children: [
          _Hero(product: prod),
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 4, 20, 24),
            child: _Details(
              product: prod,
              variant: variant,
              size: _size,
              color: _color,
              typeLabel: _typeLabels[prod.type] ?? humanize(prod.type),
              onSize: (s) => _pickSize(prod, s),
              onColor: (c) => _pickColor(prod, c),
              onVariant: (id) => setState(() => _variantId = id),
            ),
          ),
        ]),
      ),
    );
  }
}

class _Hero extends StatelessWidget {
  final Product product;
  const _Hero({required this.product});

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    return SizedBox(
      height: 340,
      child: Stack(fit: StackFit.expand, children: [
        ProductArtwork(type: product.type, imageUrl: product.imageUrl, iconSize: 96),
        DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [p.canvas.withValues(alpha: 0.55), p.canvas.withValues(alpha: 0), p.canvas.withValues(alpha: 0), p.canvas],
              stops: const [0, 0.3, 0.7, 1],
            ),
          ),
        ),
        const Align(
          alignment: Alignment.topCenter,
          child: SafeArea(
            bottom: false,
            child: Padding(
              padding: EdgeInsets.fromLTRB(20, 4, 20, 0),
              child: ScreenHeader(leading: BackChip(label: 'Store', filled: true, fallback: '/store'), trailing: StatusPill()),
            ),
          ),
        ),
      ]),
    );
  }
}

class _Details extends StatelessWidget {
  final Product product;
  final Variant? variant;
  final String? size;
  final String? color;
  final String typeLabel;
  final ValueChanged<String> onSize;
  final ValueChanged<String> onColor;
  final ValueChanged<String> onVariant;

  const _Details({
    required this.product,
    required this.variant,
    required this.size,
    required this.color,
    required this.typeLabel,
    required this.onSize,
    required this.onColor,
    required this.onVariant,
  });

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    final prod = product;
    final sizes = <String>{for (final v in prod.variants) ?v.size}.toList();
    final colors = <String>{for (final v in prod.variants) ?v.color}.toList();
    final plain = sizes.isEmpty && colors.isEmpty && prod.variants.length > 1;
    final low = variant != null && variant!.stock > 0 && variant!.stock <= 3 && prod.type != 'digital';
    // In stock in the chosen colour, or (when that colour doesn't come in this size) in any colour.
    bool sizeAvailable(String s) {
      final inColour = prod.variants.where((v) => v.size == s && v.color == color);
      return inColour.isNotEmpty ? inColour.any((v) => v.stock > 0) : prod.variants.any((v) => v.size == s && v.stock > 0);
    }

    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Text(typeLabel.toUpperCase(), style: condensed(13, weight: FontWeight.w600, tracking: 1.5, color: p.label3)),
      const SizedBox(height: 4),
      Semantics(header: true, child: Text(prod.name.toUpperCase(), style: condensed(32, weight: FontWeight.w800, color: p.label, height: 1.05))),
      const SizedBox(height: 2),
      Text(
        variant == null ? 'Sold out' : formatMoney(variant!.priceMinor),
        style: condensed(24, weight: FontWeight.w700, color: variant == null ? p.label3 : p.accent),
      ),
      if (sizes.isNotEmpty) ...[
        const SizedBox(height: 18),
        SectionLabel(
          'Size',
          trailing: low
              ? Text('ONLY ${variant!.stock} LEFT IN ${variant!.size ?? ''}'.trim(),
                  style: condensed(13, weight: FontWeight.w600, tracking: 1, color: p.warning))
              : null,
        ),
        GridView.count(
          crossAxisCount: 5,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          mainAxisSpacing: 6,
          crossAxisSpacing: 6,
          childAspectRatio: 1.2,
          children: [
            for (final s in sizes)
              _OptionBox(
                label: s,
                selected: s == size,
                available: sizeAvailable(s),
                onTap: () => onSize(s),
              ),
          ],
        ),
      ],
      if (colors.isNotEmpty) ...[
        const SizedBox(height: 16),
        Row(children: [
          SizedBox(width: 56, child: Text('COLOR', style: condensed(13, weight: FontWeight.w600, tracking: 1, color: p.label3))),
          for (final c in colors)
            Semantics(
              button: true,
              selected: c == color,
              label: c,
              excludeSemantics: true,
              child: GestureDetector(
                onTap: () => onColor(c),
                child: Container(
                  width: 44,
                  height: 44,
                  margin: const EdgeInsets.only(right: 6),
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    border: Border.all(color: c == color ? p.accent : Colors.transparent, width: 2),
                  ),
                  child: Container(
                    width: 32,
                    height: 32,
                    decoration: BoxDecoration(shape: BoxShape.circle, color: _swatch(c, p), border: Border.all(color: p.border)),
                  ),
                ),
              ),
            ),
          const SizedBox(width: 4),
          Expanded(child: Text(color ?? '', overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 14, color: p.label2))),
        ]),
      ],
      if (plain) ...[
        const SizedBox(height: 18),
        const SectionLabel('Option'),
        Wrap(spacing: 6, runSpacing: 6, children: [
          for (final v in prod.variants)
            SizedBox(
              height: 48,
              child: _OptionBox(
                label: v.label.isEmpty ? 'Standard' : v.label,
                selected: v.variantId == variant?.variantId,
                available: v.stock > 0,
                onTap: () => onVariant(v.variantId),
                padded: true,
              ),
            ),
        ]),
      ],
      if (prod.variants.any((v) => v.stock <= 0) && (sizes.isNotEmpty || plain)) ...[
        const SizedBox(height: 10),
        Text('Crossed-out options are out of stock.', style: TextStyle(fontSize: 13, color: p.label3)),
      ],
    ]);
  }

  static Color _swatch(String name, AppPalette p) => switch (name.toLowerCase().trim()) {
        'blue' || 'royal' || 'royal blue' => const Color(0xFF1D3F8F),
        'navy' => const Color(0xFF14213D),
        'red' || 'crimson' => const Color(0xFFB8322A),
        'green' => const Color(0xFF2F7D3A),
        'teal' => const Color(0xFF1F7A6B),
        'gold' || 'yellow' => const Color(0xFFE0B43A),
        'orange' => const Color(0xFFC9542A),
        'white' => const Color(0xFFF2F1EA),
        'black' => const Color(0xFF111111),
        'grey' || 'gray' || 'silver' => const Color(0xFF9CA3AF),
        'purple' || 'violet' => const Color(0xFF6D28D9),
        _ => p.raised,
      };
}

/// Size box: accent outline when selected, dashed-looking and struck through when out of stock.
class _OptionBox extends StatelessWidget {
  final String label;
  final bool selected;
  final bool available;
  final VoidCallback onTap;
  final bool padded;
  const _OptionBox({required this.label, required this.selected, required this.available, required this.onTap, this.padded = false});

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    return Semantics(
      button: true,
      selected: selected,
      enabled: available,
      label: '$label${available ? '' : ', out of stock'}',
      excludeSemantics: true,
      child: GestureDetector(
        onTap: available ? onTap : null,
        child: Container(
          padding: padded ? const EdgeInsets.symmetric(horizontal: 16) : null,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(10),
            border: Border.all(color: selected ? p.accent : p.border, width: selected ? 2 : 1),
          ),
          child: Text(
            label,
            style: condensed(17, weight: FontWeight.w700, color: !available ? p.muted : (selected ? p.accent : p.label)).copyWith(
              decoration: available ? null : TextDecoration.lineThrough,
              decorationColor: p.muted,
            ),
          ),
        ),
      ),
    );
  }
}
