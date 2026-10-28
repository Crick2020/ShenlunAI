import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.aixue.shenlun',
  appName: '爱学申论',
  webDir: 'dist',
  android: {
    allowMixedContent: false,
  },
};

export default config;
