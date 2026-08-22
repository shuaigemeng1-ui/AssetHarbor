<script setup>
import {
  Check,
  CheckCheck,
  CheckSquare,
  CircleAlert,
  ChevronDown,
  ChevronRight,
  Copy,
  Circle,
  Download,
  Eye,
  EyeOff,
  ExternalLink,
  FileText,
  Filter,
  FolderOpen,
  Gauge,
  Globe2,
  Image,
  KeyRound,
  Layers,
  LockKeyhole,
  LogOut,
  Maximize2,
  Menu,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Search,
  Settings,
  ShieldCheck,
  Square,
  Trash2,
  Upload,
  UserRound,
  UsersRound,
  Video,
  X,
  ZoomIn,
  ZoomOut,
} from 'lucide-vue-next'

defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 18 },
})

const icons = {
  overview: Gauge,
  image: Image,
  file: FileText,
  pdf: FileText,
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
  download: Download,
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
  checkAll: CheckCheck,
  checkSquare: CheckSquare,
  square: Square,
  layers: Layers,
  filter: Filter,
  retry: RefreshCw,
  preview: Eye,
  eyeOff: EyeOff,
  external: ExternalLink,
  'external-link': ExternalLink,
  zoomIn: ZoomIn,
  zoomOut: ZoomOut,
  zoomReset: RotateCcw,
  fullscreen: Maximize2,
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
