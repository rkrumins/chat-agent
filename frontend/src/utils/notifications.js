import { enqueueSnackbar } from 'notistack';

/**
 * Utility functions for displaying toast notifications
 */

export const notify = {
  success: (message, options = {}) => {
    enqueueSnackbar(message, {
      variant: 'success',
      autoHideDuration: 3000,
      anchorOrigin: { vertical: 'top', horizontal: 'right' },
      ...options,
    });
  },

  error: (message, options = {}) => {
    enqueueSnackbar(message, {
      variant: 'error',
      autoHideDuration: 5000,
      anchorOrigin: { vertical: 'top', horizontal: 'right' },
      ...options,
    });
  },

  info: (message, options = {}) => {
    enqueueSnackbar(message, {
      variant: 'info',
      autoHideDuration: 3000,
      anchorOrigin: { vertical: 'top', horizontal: 'right' },
      ...options,
    });
  },

  warning: (message, options = {}) => {
    enqueueSnackbar(message, {
      variant: 'warning',
      autoHideDuration: 4000,
      anchorOrigin: { vertical: 'top', horizontal: 'right' },
      ...options,
    });
  },
};

