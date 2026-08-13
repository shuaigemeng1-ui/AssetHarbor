<script setup>
import {
  Check,
  CircleAlert,
  ChevronDown,
  ChevronRight,
  Copy,
  Circle,
  Eye,
  EyeOff,
  ExternalLink,
  FolderOpen,
  Gauge,
  Globe2,
  Image,
  KeyRound,
  LockKeyhole,
  LogOut,
  Menu,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  Search,
  Settings,
  ShieldCheck,
  Trash2,
  Upload,
  UserRound,
  UsersRound,
  Video,
  X,
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
  down: ChevronDown,
  search: Search,
  close: X,
  copy: Copy,
  edit: Pencil,
  delete: Trash2,
  public: Globe2,
  private: LockKeyhole,
  check: Check,
  retry: RefreshCw,
  preview: Eye,
  eyeOff: EyeOff,
  external: ExternalLink,
  key: KeyRound,
  play: Play,
  plus: Plus,
  settings: Settings,
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
