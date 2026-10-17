import 'package:dio/dio.dart';
import 'package:flutter/material.dart';

import '../../core/config.dart';
import '../../widgets/async_view.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  final _url = TextEditingController();
  bool _testing = false;

  @override
  void initState() {
    super.initState();
    ServerConfig.load().then((u) => _url.text = u);
  }

  @override
  void dispose() {
    _url.dispose();
    super.dispose();
  }

  Future<void> _test() async {
    setState(() => _testing = true);
    try {
      await Dio(BaseOptions(connectTimeout: const Duration(seconds: 3), receiveTimeout: const Duration(seconds: 3)))
          .get('${_url.text.trim()}/api/v1/ping');
      if (mounted) showSuccess(context, 'Connected to the server.');
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text("Can't reach the server. Check the address and that you're on the same Wi-Fi.")),
        );
      }
    } finally {
      if (mounted) setState(() => _testing = false);
    }
  }

  Future<void> _save() async {
    await ServerConfig.save(_url.text);
    if (mounted) showSuccess(context, 'Server address saved.');
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          TextField(
            controller: _url,
            keyboardType: TextInputType.url,
            decoration: const InputDecoration(
              labelText: 'Server address',
              helperText: 'Emulator: http://10.0.2.2:8080 · Phone: http://<laptop-IP>:8080',
            ),
          ),
          const SizedBox(height: 16),
          OutlinedButton.icon(
            onPressed: _testing ? null : _test,
            icon: const Icon(Icons.network_check),
            label: Text(_testing ? 'Testing…' : 'Test connection'),
          ),
          const SizedBox(height: 12),
          FilledButton.icon(onPressed: _save, icon: const Icon(Icons.save), label: const Text('Save')),
        ]),
      ),
    );
  }
}
