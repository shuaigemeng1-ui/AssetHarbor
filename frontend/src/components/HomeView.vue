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
        <button class="quick-action primary-action" @click="emit('navigate', 'images', { upload: true })">
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
.overview-view {
  display: grid;
  gap: 24px;
  color: var(--text, #1c1917);
}

.welcome-panel {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(320px, 480px);
  align-items: center;
  gap: 40px;
  padding: 28px 30px;
  border: 1px solid var(--border, #e7e5e4);
  border-radius: 8px;
  background: #fff;
}

.welcome-kicker, .overview-section-heading span, .panel-heading span, .organize-kicker {
  color: var(--muted, #78716c);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .11em;
  text-transform: uppercase;
}

.welcome-copy h1 {
  margin: 8px 0 8px;
  font-size: clamp(26px, 3vw, 36px);
  line-height: 1.15;
  letter-spacing: -.035em;
}

.welcome-copy p {
  max-width: 530px;
  margin: 0;
  color: var(--muted, #78716c);
  font-size: 14px;
}

.welcome-actions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.quick-action {
  width: 100%;
  min-height: 64px;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  border: 1px solid var(--border, #e7e5e4);
  border-radius: 6px;
  padding: 10px 12px;
  background: #fff;
  color: var(--text, #1c1917);
  cursor: pointer;
  text-align: left;
  transition: border-color 140ms ease, background-color 140ms ease;
}

.quick-action:hover { border-color: #a8a29e; background: #fafaf9; }
.quick-action:focus-visible, .text-action:focus-visible, .recent-item:focus-visible, .organize-button:focus-visible { outline: 2px solid #2563eb; outline-offset: 2px; }
.quick-action.primary-action { border-color: #1c1917; background: #1c1917; color: #fff; }
.quick-action.primary-action:hover { border-color: #292524; background: #292524; }
.quick-action > span:nth-child(2) { min-width: 0; display: grid; }
.quick-action strong { font-size: 12px; }
.quick-action small { margin-top: 2px; color: var(--muted, #78716c); font-size: 10px; }
.quick-action.primary-action small { color: #d6d3d1; }
.quick-icon, .stat-icon {
  display: grid;
  place-items: center;
  border-radius: 5px;
  background: #f5f5f4;
  color: #57534e;
}
.quick-icon { width: 36px; height: 36px; }
.quick-action.primary-action .quick-icon { background: #fff; color: #1c1917; }
.quick-icon.video { background: #f5f5f4; color: #57534e; }

.overview-loading, .overview-error {
  min-height: 112px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  border: 1px solid var(--border, #e7e5e4);
  border-radius: 8px;
  background: #fff;
  color: var(--muted, #78716c);
}

.loading-orb { width: 16px; height: 16px; border: 2px solid #e7e5e4; border-top-color: #57534e; border-radius: 50%; animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.overview-error { justify-content: space-between; padding: 22px; }
.overview-error div { display: grid; }
.overview-error strong { color: #b42318; }
.overview-error span { font-size: 12px; }
.overview-section-heading, .panel-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; }
.overview-section-heading h2, .panel-heading h2 { margin: 4px 0 0; font-size: 18px; letter-spacing: -.02em; }
.overview-section-heading p { margin: 0; color: var(--muted, #78716c); font-size: 11px; }

.overview-stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.overview-stat {
  min-width: 0;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: 12px;
  border: 1px solid var(--border, #e7e5e4);
  border-radius: 6px;
  padding: 16px;
  background: #fff;
}
.overview-stat.featured { border-color: #a8a29e; }
.stat-icon { width: 36px; height: 36px; }
.stat-icon.violet, .stat-icon.amber, .stat-icon.green { background: #f5f5f4; color: #57534e; }
.overview-stat div:nth-child(2) { min-width: 0; display: grid; }
.overview-stat span { color: var(--muted, #78716c); font-size: 10px; }
.overview-stat strong { overflow: hidden; color: var(--text, #1c1917); font-size: 22px; line-height: 1.25; text-overflow: ellipsis; white-space: nowrap; }
.overview-stat small { grid-column: 1 / -1; color: #a8a29e; font-size: 10px; }

.overview-content-grid { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(250px, .55fr); gap: 8px; }
.recent-panel, .organize-panel { border: 1px solid var(--border, #e7e5e4); border-radius: 8px; background: #fff; }
.recent-panel { padding: 20px; }
.panel-heading { margin-bottom: 15px; }
.text-action { display: inline-flex; align-items: center; gap: 3px; border: 0; padding: 6px; background: transparent; color: var(--text, #1c1917); cursor: pointer; font-size: 11px; font-weight: 650; }
.text-action:hover { color: #57534e; }
.recent-list { display: grid; }
.recent-item {
  min-width: 0;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  border: 0;
  border-top: 1px solid var(--border, #e7e5e4);
  padding: 12px 4px;
  background: transparent;
  color: var(--text, #1c1917);
  cursor: pointer;
  text-align: left;
}
.recent-item:hover { background: #fafaf9; }
.recent-type { width: 36px; height: 36px; display: grid; place-items: center; border-radius: 5px; background: #f5f5f4; color: #57534e; }
.recent-type.video { background: #f5f5f4; color: #57534e; }
.recent-info { min-width: 0; display: grid; }
.recent-info strong, .recent-info small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.recent-info strong { font-size: 12px; }
.recent-info small, .recent-meta small { color: var(--muted, #78716c); font-size: 10px; }
.recent-meta { display: grid; justify-items: end; gap: 4px; }
.recent-meta em { padding: 2px 6px; border: 1px solid #d6d3d1; border-radius: 4px; background: #fff; color: #57534e; font-size: 9px; font-style: normal; }
.recent-meta em.private { background: #f5f5f4; color: #57534e; }
.recent-empty { min-height: 180px; display: flex; align-items: center; justify-content: center; gap: 13px; color: var(--muted, #78716c); }
.recent-empty > span { width: 42px; height: 42px; display: grid; place-items: center; border: 1px solid var(--border, #e7e5e4); border-radius: 6px; background: #fafaf9; }
.recent-empty strong { color: var(--text, #1c1917); font-size: 13px; }
.recent-empty p { margin: 3px 0 0; font-size: 11px; }

.organize-panel { display: flex; flex-direction: column; align-items: flex-start; justify-content: center; padding: 24px; color: var(--text, #1c1917); }
.organize-panel h2 { margin: 8px 0 8px; font-size: 18px; line-height: 1.3; letter-spacing: -.02em; }
.organize-panel p { margin: 0; color: var(--muted, #78716c); font-size: 11px; line-height: 1.7; }
.organize-button { display: inline-flex; align-items: center; gap: 4px; margin-top: 20px; border: 1px solid #d6d3d1; border-radius: 5px; padding: 8px 10px; background: #fff; color: var(--text, #1c1917); cursor: pointer; font-size: 11px; font-weight: 650; }
.organize-button:hover { border-color: #a8a29e; background: #fafaf9; }

@media (max-width: 1050px) {
  .welcome-panel { grid-template-columns: 1fr; gap: 22px; }
  .overview-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 760px) {
  .welcome-panel { padding: 24px; }
  .welcome-actions, .overview-content-grid { grid-template-columns: 1fr; }
  .organize-panel { min-height: 220px; }
}

@media (max-width: 520px) {
  .overview-view { gap: 20px; }
  .welcome-panel { padding: 20px; }
  .welcome-copy h1 { font-size: 27px; }
  .overview-stats { grid-template-columns: 1fr; }
  .overview-section-heading { align-items: flex-start; flex-direction: column; gap: 4px; }
  .recent-item { grid-template-columns: auto minmax(0, 1fr); }
  .recent-meta { grid-column: 2; justify-items: start; }
}
</style>
