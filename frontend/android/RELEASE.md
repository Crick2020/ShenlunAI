# 爱学申论 Android 发布说明

- 应用名称：爱学申论
- 包名：`com.aixue.shenlun`
- 当前版本：`1.0.1`（versionCode `2`）
- 最低 Android 版本：Android 7.0（API 24）
- 目标 Android 版本：Android 16（API 36）

## 重新构建

```bash
npm run android:sync
cd android
./gradlew assembleRelease bundleRelease
```

输出文件：

```text
android/app/build/outputs/apk/release/app-release.apk
android/app/build/outputs/bundle/release/app-release.aab
```

## 发布签名

签名证书和密码保存在以下本地文件中，二者均已加入 Git 忽略：

```text
frontend/android/keystore/aixue-shenlun-release.jks
frontend/android/keystore.properties
```

必须将这两个文件备份到安全的密码管理或离线存储中。后续版本更新必须继续使用同一张证书；遗失后无法用新证书覆盖更新已发布应用。

当前证书 SHA-256：

```text
65:22:A1:37:C5:F2:50:2F:F2:3C:DA:48:78:53:65:14:55:95:4D:36:34:34:43:AD:2F:9D:01:A3:99:96:69:15
```
