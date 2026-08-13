# 工作区宽屏与 1K 刷新布局修复 Design QA

- 源视觉真值：`C:\Users\user\AppData\Local\Temp\codex-clipboard-04dbcb9d-af6e-4d41-88c5-24d11d2fd7be.png`
- 同视口修复前截图：`C:\Users\user\Desktop\oss\frontend\audit\layout-fix\01-before-2048x1024.png`
- 同视口实现截图：`C:\Users\user\Desktop\oss\frontend\audit\layout-fix\02-after-2048x1024.png`
- 原始附件：2560 × 1392 px，包含浏览器边框、右侧空白区域和红色标注。
- 归一化对比：2048 × 1024 CSS px，device scale factor 1；修复前后均来自同一线上 DOM、相同登录态和相同空任务状态，实现截图在隔离验收标签页中临时加载本次精确 CSS 变更。
- 页面状态：系统管理员、视频上传中心、无上传任务。

## 全视图比较

- 修复前：工作区主栏宽 1801px，但正文仅 1273px，正文左缘位于 x=496；`documentElement` 为唯一滚动容器，`clientHeight=1024`、`scrollHeight=1028`，短页面也出现纵向滚动条。
- 修复后：工作区主栏宽 1816px，正文扩展到 1760px，正文左缘移动到 x=260；`clientHeight=1024`、`scrollHeight=1024`，无多余纵向滚动条。
- 页面仍由文档根节点负责滚动，没有新增嵌套滚动容器，也没有横向溢出。

## 重点区域比较

无需另做裁剪：2048 × 1024 全视图中，正文左右边界、右侧滚动条和页脚位置都清晰可辨。几何数据作为重点证据：

- 正文宽度：1273px → 1760px。
- 正文左边距：264px → 28px（相对于主栏）。
- 根滚动高度：1028px → 1024px。
- 工作区右边界：修复后严格对齐 x=2048。

## 比较历史与修复

1. P1 — 2K 宽度被压回窄版
   - 原因：`clamp(1180px, calc(100% - 528px), 1800px)` 在约 2048px 有效视口下只给正文约 1280px。
   - 修复：正文连续使用主栏可用宽度，保留 56px 最小页面边距并在超宽屏封顶 1800px；不依赖物理分辨率或突变断点。
   - 结果：同视口正文增至 1760px，宽屏空间被有效利用。

2. P1 — 短页面无内容也出现滚动条
   - 原因：页头 68px、正文 `100vh - 126px`、页脚约 61.6px 相加后比视口多约 4px。
   - 修复：桌面普通页面改为 `auto / minmax(0, 1fr) / auto` 三行 Grid，移除正文高度魔法数字；媒体库与移动布局保持原有全屏规则。
   - 结果：短页滚动高度与视口完全相等；长内容页仍由文档自然滚动。

3. P2 — 根布局宽度没有明确合同
   - 修复：为 `html/body/#app/.app-shell/.workspace-shell/.workspace-main` 明确 `width: 100%` 与 `max-width: none`，并新增静态回归合同。
   - 结果：所有根级容器均填满浏览器布局视口，没有嵌套根滚动或宽度上限。

## 跨页面检查

在 2048 × 1024 下检查了媒体概览、视频上传中心、图片、视频、分组、团队、管理中心、账户与密钥八个路由：

- 全部路由均无横向溢出。
- 上传中心、图片、视频、分组、团队、账户短页均不再产生多余纵向滚动。
- 媒体概览和管理中心因内容真实超过一屏而保留文档滚动，行为符合预期。
- 图片、视频和团队的全宽页面仍保持全宽，不受普通正文上限影响。
- 浏览器控制台没有 error 或 warning。

## 必查视觉面

- 字体与排版：字体、字号、字重和换行未改；宽屏下只改变可用内容宽度。
- 间距与布局节奏：普通页面保留 28px 最小侧边距；页头、正文、页脚改为自动测量，不再依赖魔法高度。
- 颜色与视觉令牌：未改。
- 图片与资产：未改，也未新增替代资产。
- 文案与业务内容：未改。

## 自动化验证

- `npm test -- --run`：29 个测试文件、164 项测试通过。
- `npm run build`：Vite 生产构建成功。
- `git diff --check`：通过，仅有 Git 的 LF/CRLF 提示。
- 未启动前端或后端服务。

## 1K 刷新裁切复盘（2026-08-13）

- 异常源图：`C:\Users\user\.codex\attachments\5c8aec64-5ffe-4404-ab4a-083542452815\image-1.png`。
- 清理后截图：`C:\Users\user\Desktop\oss\frontend\audit\layout-fix\03-after-1k-viewport-reset.png`。
- 根因：上一轮 2K 验收遗留了 2048 × 1024 浏览器设备指标覆盖。附件实际窗口约 1916px，但详情栏仍从 x=1688 开始，严格符合 2048px 布局公式；右侧 132–136px 和底部约 108px 被浏览器物理窗口裁掉。应用没有保存 viewport、zoom 或缩放状态。
- 现场修复：已清除设备指标覆盖。刷新后 `innerWidth=1912`、`documentElement.clientWidth=1912`、`visualViewport.width=1912`、`scrollWidth=1912`，视频详情栏完整显示。
- 全路由验证：在真实 1912px 视口以及 1024 × 768 视口下，逐一刷新 overview、upload-center、images、my-images、videos、my-videos、groups、teams、admin、account；每页 `documentElement.scrollWidth === clientWidth`，shell、main、page、媒体库与团队页右边界均未越过视口。
- 代码加固：图片详情、视频详情和团队成员面板统一在 1408px 进入抽屉模式。该阈值扣除 232px 固定侧栏及约 16px 系统滚动条后，为主内容保留 1160px；1366px 常见屏幕不再把详情栏硬塞进过窄主区。1409–1573px 的内联媒体库使用三列，1574px 起四列的单卡宽度仍不少于约 220px，消除了断点处骤缩。
- 可访问性：关闭的图片/视频详情抽屉使用 `aria-hidden + inert`；团队成员抽屉打开时锁定背景滚动并将背景设为 inert，关闭、跨阈值和卸载都会释放锁。
- 回归保护：新增图片、视频、团队三个 1366px 抽屉行为测试，并由布局合同锁定 CSS 与 JavaScript 使用同一阈值、抽屉定位和过渡列数。

final result: passed
