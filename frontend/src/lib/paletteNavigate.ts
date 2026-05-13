/**
 * Command palette: open in a new browser tab on Ctrl/Cmd+click or Ctrl/Cmd+Enter.
 * Plain click and plain Enter stay in the same tab.
 */
export function isPaletteOpenInNewTab(event?: MouseEvent | KeyboardEvent | null): boolean {
  if (!event) return false;
  if (event instanceof KeyboardEvent) {
    return event.key === "Enter" && (event.ctrlKey || event.metaKey);
  }
  return event.ctrlKey || event.metaKey;
}
