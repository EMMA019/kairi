const KEY = "kairi_show_advanced_modes";

/** IDE / Char / Radar など上級 UI。個人用途メインルートでは既定 ON（設定から OFF も可）。 */
export function getShowAdvancedModes(): boolean {
  try {
    return localStorage.getItem(KEY) !== "0";
  } catch {
    return true;
  }
}

export function setShowAdvancedModes(on: boolean): void {
  try {
    localStorage.setItem(KEY, on ? "1" : "0");
  } catch {
    /* ignore */
  }
  window.dispatchEvent(new CustomEvent("kairi-advanced-modes", { detail: on }));
}
