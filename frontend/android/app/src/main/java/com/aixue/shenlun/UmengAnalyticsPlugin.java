package com.aixue.shenlun;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.umeng.analytics.MobclickAgent;
import java.util.HashMap;
import java.util.Iterator;
import java.util.Map;

@CapacitorPlugin(name = "UmengAnalytics")
public class UmengAnalyticsPlugin extends Plugin {

    private static final int MAX_PARAMETERS = 8;

    @PluginMethod
    public void getPrivacyConsent(PluginCall call) {
        JSObject result = new JSObject();
        result.put("granted", UmengApplication.hasPrivacyConsent(getContext()));
        call.resolve(result);
    }

    @PluginMethod
    public void grantPrivacyConsent(PluginCall call) {
        UmengApplication.grantPrivacyConsent(getContext());
        call.resolve();
    }

    @PluginMethod
    public void track(PluginCall call) {
        if (!UmengApplication.hasPrivacyConsent(getContext())) {
            call.reject("Umeng requires privacy consent");
            return;
        }
        if (!UmengApplication.isSdkInitialized()) {
            UmengApplication.initializeUmengSdk(getContext());
        }
        if (!UmengApplication.isSdkInitialized()) {
            call.reject("Umeng SDK is not initialized");
            return;
        }

        String eventId = call.getString("eventId");
        if (eventId == null || !eventId.matches("^[a-z][a-z0-9_]{0,127}$")) {
            call.reject("Invalid Umeng event id");
            return;
        }

        JSObject input = call.getObject("params", new JSObject());
        Map<String, Object> params = new HashMap<>();
        Iterator<String> keys = input.keys();
        while (keys.hasNext() && params.size() < MAX_PARAMETERS) {
            String key = keys.next();
            if (key == null || !key.matches("^[a-z][a-z0-9_]{0,63}$")) {
                continue;
            }

            Object value = input.opt(key);
            if (value instanceof String) {
                String text = ((String) value).trim();
                if (!text.isEmpty()) {
                    params.put(key, text.length() > 128 ? text.substring(0, 128) : text);
                }
            } else if (value instanceof Number || value instanceof Boolean) {
                params.put(key, value);
            }
        }

        MobclickAgent.onEventObject(getContext(), eventId, params);
        call.resolve();
    }
}
