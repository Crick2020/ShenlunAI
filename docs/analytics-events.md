# 申论智批 - 埋点事件文档

本文档定义网站统计埋点的事件名、说明、触发时机与参数规范，便于产品/运营配置统计平台及后续分析。

---

## 一、会话与留存

| 事件名 | 说明 | 触发时机 | 参数 |
|--------|------|----------|------|
| `user_session_start` | 用户会话开始 | App 挂载时触发一次 | 见下表 |

`user_session_start` 参数：

| 参数名 | 类型 | 说明 |
|--------|------|------|
| `is_new_user` | boolean | 是否首次访问（用于新用户数统计） |
| `is_new_day` | boolean | 今天是否首次打开（用于 DAU 统计） |
| `visit_count` | number | 累计访问天数（≥1） |
| `days_since_first` | number | 距首次访问的自然天数（留存分析用） |
| `last_visit_days_ago` | number | 距上次访问的天数；当天再次打开时为 0 |

**留存分析方法（以百度统计 / 51.LA 为例）**：
- **DAU**：统计 `user_session_start` 中 `is_new_day=true` 的 UV，即每日活跃用户数。
- **次日留存**：`days_since_first=1` 且 `is_new_day=true` 的用户数 ÷ 首日新用户数。
- **7 日 / 30 日留存**：`days_since_first=7/30` 时对应的用户数做同口径计算。
- `last_visit_days_ago` 可辅助分析用户沉默后的回流行为。

---

## 二、页面与访问

| 事件名 | 说明 | 触发时机 | 参数 |
|--------|------|----------|------|
| `page_view` | 页面浏览 | 每次进入某页面时 | `page`: `home` \| `exam` \| `report` \| `profile` |

用于 PV/UV 与访问人数统计。在应用内 `currentPage` 切换时上报。

**示例**：进入做题页 → `page_view`，`page=exam`。

---

## 三、试卷相关

| 事件名 | 说明 | 触发时机 | 参数 |
|--------|------|----------|------|
| `paper_click` | 点击试卷卡片 | 首页点击某张试卷卡片 | `paper_id`, `paper_name`, `exam_type`, `region`, `year` |
| `paper_submit_click` | 点击「提交并批改」 | 做题页点击提交按钮 | `paper_id`, `paper_name`, `question_id`, `question_title`, `question_type`, `answer_length` |
| `grading_result` | 批改结果 | 批改请求结束后（成功或失败） | `paper_id`, `paper_name`, `question_id`, `question_type`, `status`: `success` \| `fail`, `error?` |

- `question_type`：`SMALL`（小题）或 `ESSAY`（大作文），可用于分别统计小题和大题的提交/批改量。
- `answer_length`：提交时的答案字数，可分析用户作答长度分布。
- `grading_result` 仅在接口返回后上报一次，成功与失败二选一。

**统计小题 vs 大题批改量**：
- 筛选 `grading_result` 事件，按 `question_type=SMALL` 和 `question_type=ESSAY` 分组计数即可。

**示例**：
- 首页点击「2025 安徽公务员 A 卷」→ `paper_click`。
- 做题页点击「提交并批改」→ `paper_submit_click`，`question_type=SMALL`，`answer_length=350`。
- 批改接口成功 → `grading_result`，`status=success`；接口异常 → `grading_result`，`status=fail`，`error` 为简要错误信息。

---

## 四、作答行为

| 事件名 | 说明 | 触发时机 | 参数 |
|--------|------|----------|------|
| `question_switch` | 切换题目 | 做题页点击题目导航（非初始进入） | `paper_id`, `question_index`（从 0 起）, `question_type` |
| `answer_start` | 开始作答 | 某题首次输入任意字符时触发一次 | `paper_id`, `question_id`, `question_type` |

- `question_switch` 用于分析用户是否浏览了多道题，以及大小题的关注分布。
- `answer_start` 用于「到达题目 → 开始作答」的漏斗转化分析；每题只上报一次，不随字数增减重复触发。

---

## 五、按钮与交互

| 事件名 | 说明 | 触发位置 | 参数 |
|--------|------|----------|------|
| `filter_change` | 筛选变更 | 首页考试类型/地区 | `filter_type`: `type` \| `region`, `value` |
| `exam_back` | 做题页返回 | ExamDetail 返回按钮 | `paper_id` |
| `exam_tab_switch` | 材料/题目切换 | 做题页移动端「材料/问题」切换 | `tab`: `material` \| `question` |
| `photo_upload_click` | 点击拍照/上传或粘贴图片 | 做题页上传答案图片 | `paper_id`, `question_id`, `source`: `button` \| `paste` |
| `payment_modal_confirm` | 支付弹窗确认批改 | PaymentModal 点「去批改/立即支付/确定」 | 可选 `paper_id` |
| `payment_modal_close` | 支付弹窗关闭 | 关闭弹窗（按钮或遮罩） | 可选 `paper_id` |
| `report_back` | 报告页返回列表 | Report「返回列表」 | 无 |
| `report_copy` | 报告页一键复制 | Report「一键复制」 | 无 |
| `nav_click` | 导航点击 | Navbar 各入口 | `target`: `home` \| `list` \| `history` \| `profile` \| `logout` |
| `history_record_click` | 历史记录点击 | Profile 点击某条记录 | `paper_name`, `record_id` |

- **地区 tag 点击**：通过 `filter_change`，`filter_type=region`，`value=<地区名>` 统计；按 `value` 分组即可看出各地区的关注热度。
- `photo_upload_click` 的 `source=paste` 表示用户通过粘贴方式上传图片。

---

## 六、统计平台映射说明

- **百度统计**：使用 `_trackEvent(category, action, label, value)`。建议将「事件名」作为 `category`，固定传 `'event'` 作为 `action`，参数 JSON 作为 `label`。
- **51.LA**：在后台配置自定义事件名与属性，与上表事件名、参数一一对应即可。

开发环境可通过开关仅打印 log 不上报，避免污染生产数据（`isDev` 为 `true` 时自动降级为 `console.log`）。

---

## 七、关键指标汇总

| 指标 | 数据来源事件 | 统计方式 |
|------|-------------|----------|
| 每日用户数（DAU） | `user_session_start` | 筛选 `is_new_day=true` 的 UV，按日期分组 |
| 新用户数 | `user_session_start` | 筛选 `is_new_user=true` 的 UV |
| 次日留存率 | `user_session_start` | `days_since_first=1` UV ÷ 首日新用户 UV |
| 7 日留存率 | `user_session_start` | `days_since_first=7` UV ÷ 对应首日新用户 UV |
| 地区 tag 点击热度 | `filter_change` | `filter_type=region`，按 `value` 分组计数 |
| 试卷点击量 | `paper_click` | 按 `paper_id` 或 `region` 分组计数 |
| 小题提交批改量 | `grading_result` | 筛选 `question_type=SMALL` 且 `status=success` |
| 大题提交批改量 | `grading_result` | 筛选 `question_type=ESSAY` 且 `status=success` |
| 批改成功率 | `grading_result` | `status=success` 次数 ÷ 总次数 |
| 作答漏斗转化 | `paper_click` → `answer_start` → `paper_submit_click` → `grading_result` | 各环节 UV 依次计算 |
