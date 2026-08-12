<script setup>
import { computed, onMounted, ref } from 'vue'
import { getLibraryStats, listMedia } from '../api'
import { formatBytes, formatDate } from '../utils/format'
import AppIcon from './AppIcon.vue'

const props = defineProps({ user: { type: Object, required: true } })
const emit = defineEmits(['navigate'])

const stats = ref(null)
const recent = ref([])
const loading = ref(true)
const error = ref('')

const greeting = computed(() => {
  const hour = new Date().getHours()
  if (hour < 6) return '夜深了'
  if (hour < 12) return '早上好'
  if (hour < 14) return '中午好'
  if (hour < 18) return '下午好'
  return '晚上好'
})

const pendingText = computed(() => {
  const bytes = Number(stats.value?.pending_upload_bytes || 0)
  return bytes ? `${formatBytes(bytes)} 正在等待完成` : '当前没有未完成上传'
})

async function loadOverview() {
  loading.value = true
  error.value = ''
  try {
    const [summary, media] = await Promise.all([
      getLibraryStats(),
      listMedia({ limit: 6, offset: 0 }),
    ])
    stats.value = summary
    recent.value = media.items || []
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

onMounted(loadOverview)
</script>

<template>
  <section class="overview-view">
    <div class="welcome-panel">
      <div class="welcome-copy">
        <span class="welcome-kicker">MEDIA WORKSPACE</span>
        <h1>{{ greeting }}，{{ user.username }}</h1>
        <p>图片、视频和团队素材，都在一个清晰有序的空间里。</p>
      </div>
      <div class="welcome-actions">
        <button class="quick-action primary-action" @click="emit('navigate', 'images')">
          <span class="quick-icon"><AppIcon name="upload" /></span>
          <span><strong>上传图片</strong><small>快速获取分享链接</small></span>
          <AppIcon name="chevron" size="16" />
        </button>
        <button class="quick-action" @click="emit('navigate', 'videos')">
          <span class="quick-icon video"><AppIcon name="video" /></span>
          <span><strong>上传视频</strong><small>支持分片与断点续传</small></span>
          <AppIcon name="chevron" size="16" />
        </button>
      </div>
    </div>

    <div v-if="loading" class="overview-loading" aria-live="polite">
      <span class="loading-orb"></span>正在整理媒体概览…
    </div>
    <div v-else-if="error" class="overview-error" role="alert">
      <div><strong>概览加载失败</strong><span>{{ error }}</span></div>
      <button class="secondary" @click="loadOverview">重新加载</button>
    </div>

    <template v-else>
      <div class="overview-section-heading">
        <div>
          <span>空间概览</span>
          <h2>{{ stats?.scope === 'global' ? '全站媒体资产' : '我的媒体资产' }}</h2>
        </div>
        <p>{{ pendingText }}</p>
      </div>

      <div class="overview-stats">
        <article class="overview-stat featured">
          <div class="stat-icon"><AppIcon name="collection" /></div>
          <div><span>全部媒体</span><strong>{{ stats?.media_total || 0 }}</strong></div>
          <small>{{ stats?.images || 0 }} 张图片 · {{ stats?.videos || 0 }} 个视频</small>
        </article>
        <article class="overview-stat">
          <div class="stat-icon violet"><AppIcon name="upload" /></div>
          <div><span>存储占用</span><strong>{{ formatBytes(stats?.storage_bytes || 0) }}</strong></div>
          <small>原始文件持久化存储</small>
        </article>
        <article class="overview-stat">
          <div class="stat-icon amber"><AppIcon name="collection" /></div>
          <div><span>媒体分组</span><strong>{{ stats?.groups || 0 }}</strong></div>
          <small>用于归档和整理素材</small>
        </article>
        <article class="overview-stat">
          <div class="stat-icon green"><AppIcon name="teams" /></div>
          <div><span>协作团队</span><strong>{{ stats?.teams_count || 0 }}</strong></div>
          <small>你当前参与的团队空间</small>
        </article>
      </div>

      <div class="overview-content-grid">
        <section class="recent-panel">
          <div class="panel-heading">
            <div><span>最近更新</span><h2>最新媒体</h2></div>
            <button class="text-action" @click="emit('navigate', 'images')">浏览媒体 <AppIcon name="chevron" size="14" /></button>
          </div>

          <div v-if="recent.length" class="recent-list">
            <button
              v-for="item in recent"
              :key="item.code"
              class="recent-item"
              @click="emit('navigate', item.media_kind === 'video' ? 'videos' : 'images')"
            >
              <span class="recent-type" :class="item.media_kind">
                <AppIcon :name="item.media_kind === 'video' ? 'video' : 'image'" />
              </span>
              <span class="recent-info">
                <strong>{{ item.name || item.original_filename || item.code }}</strong>
                <small>{{ item.original_filename }} · {{ formatBytes(item.size) }}</small>
              </span>
              <span class="recent-meta">
                <small>{{ formatDate(item.created_at) }}</small>
                <em :class="item.visibility">{{ item.visibility === 'private' ? '私密' : '公开' }}</em>
              </span>
            </button>
          </div>
          <div v-else class="recent-empty">
            <span><AppIcon name="image" size="22" /></span>
            <div><strong>还没有媒体</strong><p>上传一张图片或一个视频，开始建立你的媒体库。</p></div>
          </div>
        </section>

        <aside class="organize-panel">
          <div class="organize-visual">
            <span class="folder folder-back"></span>
            <span class="folder folder-front"><AppIcon name="collection" size="25" /></span>
          </div>
          <span class="organize-kicker">保持井然有序</span>
          <h2>用分组整理项目素材</h2>
          <p>同一张图片或视频可以加入多个分组，个人内容与团队内容相互独立。</p>
          <button class="organize-button" @click="emit('navigate', 'groups')">
            管理媒体分组 <AppIcon name="chevron" size="15" />
          </button>
        </aside>
      </div>
    </template>
  </section>
</template>

<style scoped>
.overview-view { display: grid; gap: 28px; }
.welcome-panel {
  position: relative;
  overflow: hidden;
  min-height: 220px;
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(310px, .8fr);
  align-items: center;
  gap: 42px;
  padding: 38px 42px;
  border: 1px solid #dfe6f2;
  border-radius: 26px;
  background:
    radial-gradient(circle at 78% 5%, rgb(94 92 230 / 13%), transparent 18rem),
    radial-gradient(circle at 4% 100%, rgb(59 130 246 / 10%), transparent 19rem),
    #fff;
  box-shadow: 0 18px 55px rgb(33 46 78 / 8%);
}
.welcome-panel::after {
  content: '';
  position: absolute;
  right: -80px;
  bottom: -125px;
  width: 300px;
  height: 300px;
  border: 1px solid rgb(79 70 229 / 9%);
  border-radius: 50%;
  box-shadow: 0 0 0 34px rgb(79 70 229 / 3%), 0 0 0 68px rgb(79 70 229 / 2%);
  pointer-events: none;
}
.welcome-copy, .welcome-actions { position: relative; z-index: 1; }
.welcome-kicker, .overview-section-heading span, .panel-heading span, .organize-kicker {
  color: #6366f1;
  font-size: 11px;
  font-weight: 750;
  letter-spacing: .12em;
  text-transform: uppercase;
}
.welcome-copy h1 { margin: 9px 0 10px; font-size: clamp(29px, 4vw, 43px); line-height: 1.1; letter-spacing: -.045em; }
.welcome-copy p { max-width: 530px; margin: 0; color: #6b7280; font-size: 15px; }
.welcome-actions { display: grid; gap: 10px; }
.quick-action {
  width: 100%;
  min-height: 70px;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  border: 1px solid #e2e7f0;
  border-radius: 16px;
  padding: 11px 14px;
  background: rgb(255 255 255 / 78%);
  color: #1f2937;
  cursor: pointer;
  text-align: left;
  transition: 160ms ease;
}
.quick-action:hover { border-color: #c7d2fe; box-shadow: 0 10px 24px rgb(52 64 112 / 10%); transform: translateY(-1px); }
.quick-action.primary-action { border-color: #d8ddff; background: linear-gradient(135deg, #f0f2ff, #f7f9ff); }
.quick-action > span:nth-child(2) { min-width: 0; display: grid; }
.quick-action strong { font-size: 13px; }
.quick-action small { margin-top: 2px; color: #7b8498; font-size: 11px; }
.quick-icon, .stat-icon {
  display: grid;
  place-items: center;
  border-radius: 12px;
  background: #e9edff;
  color: #5658d8;
}
.quick-icon { width: 42px; height: 42px; }
.quick-icon.video { background: #ecf8ff; color: #0284c7; }
.overview-loading, .overview-error { min-height: 130px; display: flex; align-items: center; justify-content: center; gap: 12px; border: 1px solid #e4e9f2; border-radius: 18px; background: #fff; color: #6b7280; }
.loading-orb { width: 18px; height: 18px; border: 2px solid #dce2fb; border-top-color: #5b5bd6; border-radius: 50%; animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.overview-error { justify-content: space-between; padding: 22px; }
.overview-error div { display: grid; }
.overview-error strong { color: #b42318; }
.overview-error span { font-size: 12px; }
.overview-section-heading, .panel-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; }
.overview-section-heading h2, .panel-heading h2 { margin: 3px 0 0; font-size: 20px; letter-spacing: -.025em; }
.overview-section-heading p { margin: 0; color: #7b8498; font-size: 12px; }
.overview-stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }
.overview-stat {
  min-width: 0;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: 13px;
  border: 1px solid #e3e8f1;
  border-radius: 18px;
  padding: 18px;
  background: #fff;
  box-shadow: 0 5px 18px rgb(40 51 78 / 4%);
}
.overview-stat.featured { border-color: #dce1ff; background: linear-gradient(145deg, #fff, #f7f7ff); }
.stat-icon { width: 42px; height: 42px; }
.stat-icon.violet { background: #f1eefe; color: #7c3aed; }
.stat-icon.amber { background: #fff4de; color: #c56b16; }
.stat-icon.green { background: #e8f8f1; color: #14825f; }
.overview-stat div:nth-child(2) { min-width: 0; display: grid; }
.overview-stat span { color: #778094; font-size: 11px; }
.overview-stat strong { overflow: hidden; color: #1c2536; font-size: 23px; line-height: 1.25; text-overflow: ellipsis; white-space: nowrap; }
.overview-stat small { grid-column: 1 / -1; color: #929aad; font-size: 10px; }
.overview-content-grid { display: grid; grid-template-columns: minmax(0, 1.55fr) minmax(270px, .65fr); gap: 18px; }
.recent-panel, .organize-panel { border: 1px solid #e2e7ef; border-radius: 20px; background: #fff; box-shadow: 0 5px 20px rgb(40 51 78 / 4%); }
.recent-panel { padding: 22px; }
.panel-heading { margin-bottom: 15px; }
.text-action { display: inline-flex; align-items: center; gap: 3px; border: 0; padding: 6px; background: transparent; color: #5b5bd6; cursor: pointer; font-size: 12px; font-weight: 650; }
.recent-list { display: grid; }
.recent-item {
  min-width: 0;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  border: 0;
  border-top: 1px solid #edf0f5;
  padding: 12px 4px;
  background: transparent;
  color: #20293a;
  cursor: pointer;
  text-align: left;
}
.recent-item:hover { background: #fafbfe; }
.recent-type { width: 38px; height: 38px; display: grid; place-items: center; border-radius: 11px; background: #eef4ff; color: #3972d8; }
.recent-type.video { background: #f1efff; color: #6d5bd0; }
.recent-info { min-width: 0; display: grid; }
.recent-info strong, .recent-info small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.recent-info strong { font-size: 12px; }
.recent-info small, .recent-meta small { color: #8991a3; font-size: 10px; }
.recent-meta { display: grid; justify-items: end; gap: 4px; }
.recent-meta em { padding: 2px 7px; border-radius: 999px; background: #eaf8f2; color: #14765a; font-size: 9px; font-style: normal; }
.recent-meta em.private { background: #f1f2f6; color: #667085; }
.recent-empty { min-height: 180px; display: flex; align-items: center; justify-content: center; gap: 13px; color: #7d8699; }
.recent-empty > span { width: 46px; height: 46px; display: grid; place-items: center; border-radius: 14px; background: #f1f3f8; }
.recent-empty strong { color: #343d4f; font-size: 13px; }
.recent-empty p { margin: 3px 0 0; font-size: 11px; }
.organize-panel { overflow: hidden; padding: 26px; background: linear-gradient(160deg, #22243d, #30345a); color: #fff; }
.organize-visual { position: relative; height: 84px; margin-bottom: 18px; }
.folder { position: absolute; display: grid; place-items: center; border-radius: 12px; }
.folder-back { top: 8px; left: 22px; width: 70px; height: 53px; border: 1px solid rgb(255 255 255 / 8%); background: #505583; transform: rotate(-8deg); }
.folder-front { top: 20px; left: 45px; width: 83px; height: 58px; border: 1px solid rgb(255 255 255 / 13%); background: linear-gradient(135deg, #7e80ed, #6266d8); box-shadow: 0 15px 28px rgb(0 0 0 / 22%); transform: rotate(5deg); }
.organize-kicker { color: #a9acf4; }
.organize-panel h2 { margin: 7px 0 8px; font-size: 21px; line-height: 1.25; letter-spacing: -.03em; }
.organize-panel p { color: #b9bfd3; font-size: 12px; }
.organize-button { display: inline-flex; align-items: center; gap: 4px; border: 1px solid rgb(255 255 255 / 16%); border-radius: 10px; padding: 9px 12px; background: rgb(255 255 255 / 9%); color: #fff; cursor: pointer; font-size: 12px; font-weight: 650; }
.organize-button:hover { background: rgb(255 255 255 / 15%); }
@media (max-width: 1050px) {
  .welcome-panel { grid-template-columns: 1fr; gap: 24px; }
  .welcome-actions { grid-template-columns: 1fr 1fr; }
  .overview-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 760px) {
  .welcome-panel { padding: 27px 24px; border-radius: 20px; }
  .welcome-actions, .overview-content-grid { grid-template-columns: 1fr; }
  .organize-panel { min-height: 270px; }
}
@media (max-width: 520px) {
  .overview-view { gap: 20px; }
  .welcome-copy h1 { font-size: 29px; }
  .overview-stats { grid-template-columns: 1fr; }
  .overview-section-heading { align-items: flex-start; flex-direction: column; gap: 4px; }
  .recent-item { grid-template-columns: auto minmax(0, 1fr); }
  .recent-meta { grid-column: 2; justify-items: start; }
}
</style>
