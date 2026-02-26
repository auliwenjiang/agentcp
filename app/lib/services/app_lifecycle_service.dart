import 'package:flutter/services.dart';

class AppLifecycleService {
  static const MethodChannel _channel =
      MethodChannel('com.agent.acp/app_lifecycle');

  static Future<void> moveTaskToBack() async {
    try {
      await _channel.invokeMethod('moveTaskToBack');
    } on PlatformException catch (e) {
      await SystemNavigator.pop();
    }
  }
}
