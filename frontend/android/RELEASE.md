# 爱学申论 Android 发布说明

- 应用名称：爱学申论
- 包名：`com.aixue.shenlun`
- 当前版本：`1.0.7`（versionCode `8`）
- 最低 Android 版本：Android 7.0（API 24）
- 目标 Android 版本：Android 16（API 36）

## 版本记录

- `1.0.7`（8）：修复公文/应用文参考答案的排版——标题、主送机关、正文、落款、日期分段显示，落款与日期靠右，公文正文不再满篇加粗；网页端不再展示隐私政策弹窗。
- `1.0.6`（7）：APP 端无功能变更，仅重新构建以与后端版本对齐（后端新增批改结果日志、小题踩分标尺固化与质量门禁）。可直接覆盖安装 1.0.5。
- `1.0.5`（6）：修复批改报告中 `**“原词”**` 这类加粗写法不渲染、直接显示星号的问题。
- `1.0.4`（5）：修复小题批改材料缺失（江苏2025C卷第一题只发 1 份材料，应为资料1-4）；内置试卷库同步最新后端数据。
- `1.0.3`（4）：接入隐私合规弹窗与友盟统计。
- `1.0.2`（3）：修复报告页 Markdown 渲染。
- `1.0.1`（2）：内置离线试卷，首屏不再依赖后端冷启动。
- `1.0.0`（1）：首个发布版本。

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
