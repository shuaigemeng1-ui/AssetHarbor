<script setup>
import {
  CircleAlert,
  ChevronRight,
  Circle,
  FolderOpen,
  Gauge,
  Image,
  KeyRound,
  LockKeyhole,
  LogOut,
  Menu,
  ShieldCheck,
  Upload,
  UserRound,
  UsersRound,
  Video,
} from 'lucide-vue-next'

defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 18 },
})

const icons = {
  overview: Gauge,
  image: Image,
  video: Video,
  collection: FolderOpen,
  teams: UsersRound,
  admin: ShieldCheck,
  account: UserRound,
  alert: CircleAlert,
  invite: KeyRound,
  lock: LockKeyhole,
  security: ShieldCheck,
  upload: Upload,
  logout: LogOut,
  menu: Menu,
  chevron: ChevronRight,
}
</script>

<template>
  <component
    :is="icons[name] || Circle"
    class="app-icon"
    :size="Number(size)"
    :stroke-width="1.8"
    aria-hidden="true"
  />
</template>

<style scoped>
.app-icon {
  display: block;
  flex: 0 0 auto;
}
</style>
