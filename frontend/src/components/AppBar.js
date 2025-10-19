import React from 'react';
import {
  AppBar as MuiAppBar,
  Toolbar,
  Typography,
  IconButton,
  Box,
  Chip,
  Tooltip,
} from '@mui/material';
import MenuIcon from '@mui/icons-material/Menu';
import StorageIcon from '@mui/icons-material/Storage';
import Brightness4Icon from '@mui/icons-material/Brightness4';
import Brightness7Icon from '@mui/icons-material/Brightness7';

const AppBar = ({ onToggleSidebar, selectedCollection, darkMode, onToggleDarkMode }) => {
  return (
    <MuiAppBar
      position="fixed"
      sx={{
        zIndex: (theme) => theme.zIndex.drawer + 1,
        background: darkMode 
          ? 'linear-gradient(45deg, #1a237e 30%, #3f51b5 90%)'
          : 'linear-gradient(45deg, #1976d2 30%, #42a5f5 90%)',
        transition: 'background 0.3s ease',
      }}
    >
      <Toolbar>
        <IconButton
          color="inherit"
          edge="start"
          onClick={onToggleSidebar}
          sx={{ mr: 2 }}
        >
          <MenuIcon />
        </IconButton>
        <StorageIcon sx={{ mr: 2 }} />
        <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
          VectorDB Manager
        </Typography>
        {selectedCollection && (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mr: 2 }}>
            <Typography variant="body2" sx={{ mr: 1 }}>
              Active Collection:
            </Typography>
            <Chip
              label={selectedCollection.name}
              color="secondary"
              size="small"
              sx={{ fontWeight: 'bold' }}
            />
          </Box>
        )}
        <Tooltip title={darkMode ? 'Light Mode' : 'Dark Mode'}>
          <IconButton
            color="inherit"
            onClick={onToggleDarkMode}
            sx={{ ml: 1 }}
          >
            {darkMode ? <Brightness7Icon /> : <Brightness4Icon />}
          </IconButton>
        </Tooltip>
      </Toolbar>
    </MuiAppBar>
  );
};

export default AppBar;

