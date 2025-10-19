import { useEffect } from 'react';
import { useHotkeys } from 'react-hotkeys-hook';

/**
 * Custom hook to register keyboard shortcuts
 */
export const useKeyboardShortcuts = (shortcuts) => {
  // Register each shortcut
  Object.entries(shortcuts).forEach(([keys, callback]) => {
    useHotkeys(keys, callback, [callback]);
  });
};

export default useKeyboardShortcuts;

