package com.aixue.shenlun;

import android.app.Application;
import android.content.Context;
import android.content.pm.ApplicationInfo;
import com.umeng.commonsdk.UMConfigure;
import android.os.Bundle;
import com.umeng.umcrash.UMCrash;

public class UmengApplication extends Application {

    private static final String PRIVACY_PREFS = "aixue_privacy";
    private static final String PRIVACY_KEY = "umeng_consent_granted";
    private static volatile boolean sdkInitialized = false;

    @Override
    public void onCreate() {
        super.onCreate();

        boolean isDebuggable =
            (getApplicationInfo().flags & ApplicationInfo.FLAG_DEBUGGABLE) != 0;
        UMConfigure.setLogEnabled(isDebuggable);
        UMConfigure.preInit(this, "6ae30847863270068caec55c", "xiaomi");
        if (hasPrivacyConsent(this)) {
            new Thread(() -> initializeUmengSdk(this)).start();
        }
    }

    public static boolean hasPrivacyConsent(Context context) {
        return context
            .getSharedPreferences(PRIVACY_PREFS, Context.MODE_PRIVATE)
            .getBoolean(PRIVACY_KEY, false);
    }

    public static boolean isSdkInitialized() {
        return sdkInitialized;
    }

    public static synchronized void grantPrivacyConsent(Context context) {
        context
            .getSharedPreferences(PRIVACY_PREFS, Context.MODE_PRIVATE)
            .edit()
            .putBoolean(PRIVACY_KEY, true)
            .apply();
        initializeUmengSdk(context);
    }

    public static synchronized void initializeUmengSdk(Context context) {
        if (sdkInitialized || !hasPrivacyConsent(context)) {
            return;
        }

        Bundle bundle = new Bundle();
        bundle.putBoolean(UMCrash.KEY_ENABLE_CRASH_JAVA, true);
        bundle.putBoolean(UMCrash.KEY_ENABLE_CRASH_NATIVE, true);
        bundle.putBoolean(UMCrash.KEY_ENABLE_ANR, true);
        bundle.putBoolean(UMCrash.KEY_ENABLE_PA, true);
        bundle.putBoolean(UMCrash.KEY_ENABLE_LAUNCH, true);
        bundle.putBoolean(UMCrash.KEY_ENABLE_MEM, true);
        bundle.putBoolean(UMCrash.KEY_ENABLE_NET, true);
        bundle.putBoolean(UMCrash.KEY_ENABLE_PAGE, true);
        bundle.putBoolean(UMCrash.KEY_ENABLE_POWER, true);
        bundle.putBoolean(UMCrash.KEY_ENABLE_CODE_LOG, true);
        bundle.putBoolean(UMCrash.KEY_ENABLE_MEMLEAK, true);
        bundle.putLong(UMCrash.KEY_PA_TIMEOUT_TIME, 2000L);
        UMCrash.initConfig(bundle);

        UMConfigure.init(
            context.getApplicationContext(),
            "6ae30847863270068caec55c",
            "xiaomi",
            UMConfigure.DEVICE_TYPE_PHONE,
            null
        );
        sdkInitialized = true;
    }
}
