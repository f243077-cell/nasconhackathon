import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/models.dart';

class CartLine {
  final Product product;
  final Variant variant;
  final int quantity;
  const CartLine(this.product, this.variant, this.quantity);

  int get totalMinor => variant.priceMinor * quantity;
}

class CartController extends Notifier<List<CartLine>> {
  @override
  List<CartLine> build() => const [];

  void add(Product product, Variant variant, int quantity) {
    final i = state.indexWhere((l) => l.variant.variantId == variant.variantId);
    if (i == -1) {
      state = [...state, CartLine(product, variant, quantity)];
    } else {
      setQuantity(variant.variantId, (state[i].quantity + quantity).clamp(1, 10));
    }
  }

  void setQuantity(String variantId, int quantity) => state = [
        for (final l in state) l.variant.variantId == variantId ? CartLine(l.product, l.variant, quantity) : l,
      ];

  void remove(String variantId) => state = state.where((l) => l.variant.variantId != variantId).toList();

  void clear() => state = const [];
}

final cartProvider = NotifierProvider<CartController, List<CartLine>>(CartController.new);
