import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../../core/errors.dart';
import '../../core/theme.dart';
import '../../widgets/async_view.dart';
import '../../widgets/ui.dart';
import 'live_feed.dart';

/// QR scanner (FR-4.1): reads stadium / poster codes (`/q/{code}` short links, `nascon://` links,
/// `/web/` URLs) and opens the matching screen. Short links follow the server's live target, so a
/// printed code for a finished match opens the result, not a dead stream.
class QrScannerScreen extends StatefulWidget {
  const QrScannerScreen({super.key});

  @override
  State<QrScannerScreen> createState() => _QrScannerScreenState();
}

class _QrScannerScreenState extends State<QrScannerScreen> {
  final _controller = MobileScannerController(formats: const [BarcodeFormat.qrCode], detectionSpeed: DetectionSpeed.noDuplicates);
  bool _busy = false;
  String? _message;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _onDetect(BarcodeCapture capture) async {
    if (_busy) return;
    final raw = capture.barcodes.map((b) => b.rawValue).whereType<String>().firstOrNull;
    if (raw == null) return;
    setState(() {
      _busy = true;
      _message = 'Opening…';
    });
    try {
      final route = await resolveScannedCode(raw);
      if (!mounted) return;
      if (route == null) {
        setState(() => _message = "That code isn't a NaSCon match, club or stream.");
      } else {
        context.push(route);
        setState(() => _message = null);
      }
    } on ApiException catch (e) {
      if (mounted) setState(() => _message = friendlyError(e));
    } finally {
      await Future.delayed(const Duration(milliseconds: 900));
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final p = context.palette;
    return Semantics(
      identifier: 'qr-scanner-screen',
      container: true,
      child: FlatPage(
        title: 'Scan QR',
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(20),
            child: AspectRatio(
              aspectRatio: 1,
              child: Stack(fit: StackFit.expand, children: [
                MobileScanner(
                  controller: _controller,
                  onDetect: _onDetect,
                  errorBuilder: (context, error) => ColoredBox(
                    color: Colors.black,
                    child: Center(
                      child: Padding(
                        padding: const EdgeInsets.all(24),
                        child: Text(
                          error.errorCode == MobileScannerErrorCode.permissionDenied
                              ? 'Camera access is off. Allow it in Settings to scan codes.'
                              : "The camera couldn't start. Try again.",
                          textAlign: TextAlign.center,
                          style: TextStyle(color: p.label2, fontSize: 15),
                        ),
                      ),
                    ),
                  ),
                ),
                // Viewfinder frame: shows where to hold the code.
                IgnorePointer(
                  child: Center(
                    child: FractionallySizedBox(
                      widthFactor: 0.66,
                      heightFactor: 0.66,
                      child: DecoratedBox(
                        decoration: BoxDecoration(
                          border: Border.all(color: p.accent, width: 3),
                          borderRadius: BorderRadius.circular(18),
                        ),
                      ),
                    ),
                  ),
                ),
              ]),
            ),
          ),
          const SizedBox(height: 16),
          Row(children: [
            Expanded(
              child: SecondaryButton(
                label: 'Torch',
                icon: Icons.flashlight_on_rounded,
                onPressed: () => _controller.toggleTorch(),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: SecondaryButton(
                label: 'Flip',
                icon: Icons.cameraswitch_rounded,
                onPressed: () => _controller.switchCamera(),
              ),
            ),
          ]),
          const SizedBox(height: 16),
          Text(
            _message ?? 'Point the camera at a match, club or stream QR code.',
            textAlign: TextAlign.center,
            style: TextStyle(color: _message == null ? p.label2 : p.label, fontSize: 15),
          ),
          if (_busy) const Padding(padding: EdgeInsets.only(top: 12), child: LoadingView(label: 'Opening')),
        ],
      ),
    );
  }
}
