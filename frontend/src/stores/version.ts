import { computed, ref } from "vue";
import { defineStore } from "pinia";

import type { AppVersionInfo } from "@/services/api";
import { versionApi } from "@/services/api";

const HEYM_RELEASES_URL = "https://github.com/heymrun/heym/releases";

function fallbackVersionInfo(): AppVersionInfo {
  return {
    version: import.meta.env.VITE_APP_VERSION || "unknown",
    latest_version: null,
    update_available: false,
    release_url: null,
    compare_url: null,
    compare_label: null,
    source: "local",
    checked_at: null,
    error: null,
  };
}

function formatVersion(version: string): string {
  const trimmed = version.trim();
  if (!trimmed) {
    return "vunknown";
  }
  return trimmed.toLowerCase().startsWith("v") ? trimmed : `v${trimmed}`;
}

export const useVersionStore = defineStore("version", () => {
  const versionInfo = ref<AppVersionInfo>(fallbackVersionInfo());
  const loading = ref(false);
  const loaded = ref(false);
  const error = ref<string | null>(null);

  const displayVersion = computed((): string => formatVersion(versionInfo.value.version));
  const updateHref = computed((): string | null => {
    if (!versionInfo.value.update_available) {
      return null;
    }
    return HEYM_RELEASES_URL;
  });
  const updateTitle = computed((): string => {
    if (!versionInfo.value.update_available) {
      return `Heym ${displayVersion.value}`;
    }
    const latestVersion = versionInfo.value.latest_version
      ? formatVersion(versionInfo.value.latest_version)
      : displayVersion.value;
    return `Update available: ${latestVersion}`;
  });

  async function loadVersionInfo(options?: { force?: boolean }): Promise<void> {
    if ((!options?.force && loaded.value) || loading.value) {
      return;
    }

    loading.value = true;
    try {
      versionInfo.value = await versionApi.getInfo();
      error.value = null;
    } catch (err) {
      versionInfo.value = fallbackVersionInfo();
      error.value = err instanceof Error ? err.message : "Failed to load version info";
    } finally {
      loaded.value = true;
      loading.value = false;
    }
  }

  return {
    versionInfo,
    loading,
    loaded,
    error,
    displayVersion,
    updateHref,
    updateTitle,
    loadVersionInfo,
  };
});
