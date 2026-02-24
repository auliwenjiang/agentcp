package com.agentcp.store;

import android.Manifest;
import android.app.Activity;
import android.content.Context;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Environment;

public final class StoragePermissionHelper {

    public static final int REQUEST_CODE_STORAGE = 10001;

    private StoragePermissionHelper() {}

    public static boolean needsPermission(Context context, StorageConfig config) {
        if (config == null || config.getMode() != StorageMode.CUSTOM) {
            return false;
        }
        return !isAppPrivatePath(context, config.getCustomPath());
    }

    public static boolean hasPermission(Context context, StorageConfig config) {
        if (!needsPermission(context, config)) {
            return true;
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            return Environment.isExternalStorageManager();
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            return context.checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE)
                    == PackageManager.PERMISSION_GRANTED;
        }
        return true;
    }

    public static void requestPermission(Activity activity, int requestCode) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            try {
                android.content.Intent intent = new android.content.Intent(
                        android.provider.Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION);
                intent.setData(android.net.Uri.parse("package:" + activity.getPackageName()));
                activity.startActivityForResult(intent, requestCode);
            } catch (Exception e) {
                android.content.Intent intent = new android.content.Intent(
                        android.provider.Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION);
                activity.startActivityForResult(intent, requestCode);
            }
        } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            activity.requestPermissions(
                    new String[]{
                            Manifest.permission.WRITE_EXTERNAL_STORAGE,
                            Manifest.permission.READ_EXTERNAL_STORAGE
                    },
                    requestCode);
        }
    }
    public static boolean onRequestPermissionsResult(int requestCode,
                                                       String[] permissions,
                                                       int[] grantResults) {
        if (requestCode != REQUEST_CODE_STORAGE) {
            return false;
        }
        for (int result : grantResults) {
            if (result != PackageManager.PERMISSION_GRANTED) {
                return false;
            }
        }
        return grantResults.length > 0;
    }

    private static boolean isAppPrivatePath(Context context, String path) {
        if (path == null) {
            return false;
        }
        // Internal storage: /data/data/<pkg>/ or /data/user/<n>/<pkg>/
        java.io.File filesDir = context.getFilesDir();
        if (filesDir != null && path.startsWith(filesDir.getParent())) {
            return true;
        }
        // App-specific external storage: Android/data/<pkg>/
        java.io.File extFilesDir = context.getExternalFilesDir(null);
        if (extFilesDir != null && path.startsWith(extFilesDir.getParent())) {
            return true;
        }
        return false;
    }
}
