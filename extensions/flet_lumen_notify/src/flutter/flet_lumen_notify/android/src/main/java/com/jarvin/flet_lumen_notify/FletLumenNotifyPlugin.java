package com.jarvin.flet_lumen_notify;

import io.flutter.embedding.engine.plugins.FlutterPlugin;

/**
 * No-op plugin class. flet_lumen_notify is registered as an Android plugin only
 * so that this module's AndroidManifest.xml (notification receivers) is merged
 * into the app. All notification work is done by flutter_local_notifications,
 * driven from Dart (lib/src/lumen_notify.dart).
 */
public class FletLumenNotifyPlugin implements FlutterPlugin {
    @Override
    public void onAttachedToEngine(FlutterPluginBinding binding) {}

    @Override
    public void onDetachedFromEngine(FlutterPluginBinding binding) {}
}
