package com.aixue.shenlun;

import android.os.Bundle;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        registerPlugin(UmengAnalyticsPlugin.class);
        super.onCreate(savedInstanceState);
    }
}
