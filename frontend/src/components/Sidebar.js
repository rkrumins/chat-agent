import React, { useEffect, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  Drawer,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Divider,
  Typography,
  Box,
  CircularProgress,
  Alert,
  Chip,
} from '@mui/material';
import FolderIcon from '@mui/icons-material/Folder';
import HomeIcon from '@mui/icons-material/Home';
import TaskIcon from '@mui/icons-material/Task';
import { collectionsAPI } from '../services/api';

const DRAWER_WIDTH = 280;

const Sidebar = ({ open, onCollectionSelect, selectedCollection, refreshTrigger }) => {
  const [collections, setCollections] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const navigate = useNavigate();
  const location = useLocation();

  const fetchCollections = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await collectionsAPI.list();
      setCollections(data.collections || []);
    } catch (err) {
      setError('Failed to load collections');
      console.error('Error fetching collections:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCollections();
  }, [refreshTrigger]);

  const handleCollectionClick = (collection) => {
    onCollectionSelect(collection);
    navigate(`/collections/${collection.name}/documents`);
  };

  const handleHomeClick = () => {
    onCollectionSelect(null);
    navigate('/');
  };

  const handleTasksClick = () => {
    navigate('/tasks');
  };

  return (
    <Drawer
      variant="persistent"
      anchor="left"
      open={open}
      sx={{
        width: DRAWER_WIDTH,
        flexShrink: 0,
        '& .MuiDrawer-paper': {
          width: DRAWER_WIDTH,
          boxSizing: 'border-box',
          mt: 8,
          borderRight: '1px solid rgba(0, 0, 0, 0.12)',
        },
      }}
    >
      <Box sx={{ overflow: 'auto' }}>
        <List>
          <ListItem disablePadding>
            <ListItemButton
              selected={location.pathname === '/'}
              onClick={handleHomeClick}
            >
              <ListItemIcon>
                <HomeIcon color={location.pathname === '/' ? 'primary' : 'inherit'} />
              </ListItemIcon>
              <ListItemText primary="Home" />
            </ListItemButton>
          </ListItem>
          <ListItem disablePadding>
            <ListItemButton
              selected={location.pathname === '/tasks'}
              onClick={handleTasksClick}
            >
              <ListItemIcon>
                <TaskIcon color={location.pathname === '/tasks' ? 'primary' : 'inherit'} />
              </ListItemIcon>
              <ListItemText primary="Tasks" />
            </ListItemButton>
          </ListItem>
        </List>

        <Divider />

        <Box sx={{ p: 2 }}>
          <Typography variant="subtitle2" color="text.secondary" gutterBottom>
            Collections
          </Typography>
        </Box>

        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', p: 3 }}>
            <CircularProgress size={24} />
          </Box>
        ) : error ? (
          <Box sx={{ p: 2 }}>
            <Alert severity="error" size="small">
              {error}
            </Alert>
          </Box>
        ) : collections.length === 0 ? (
          <Box sx={{ p: 2 }}>
            <Typography variant="body2" color="text.secondary" align="center">
              No collections yet
            </Typography>
          </Box>
        ) : (
          <List>
            {collections.map((collection) => (
              <ListItem key={collection.id} disablePadding>
                <ListItemButton
                  selected={selectedCollection?.name === collection.name}
                  onClick={() => handleCollectionClick(collection)}
                >
                  <ListItemIcon>
                    <FolderIcon
                      color={
                        selectedCollection?.name === collection.name
                          ? 'primary'
                          : 'inherit'
                      }
                    />
                  </ListItemIcon>
                  <ListItemText
                    primary={collection.name}
                    secondary={
                      <Chip
                        label={`${collection.count} docs`}
                        size="small"
                        sx={{ mt: 0.5, height: 20, fontSize: '0.7rem' }}
                      />
                    }
                  />
                </ListItemButton>
              </ListItem>
            ))}
          </List>
        )}
      </Box>
    </Drawer>
  );
};

export default Sidebar;

