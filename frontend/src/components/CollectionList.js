import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  Grid,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  CircularProgress,
  Alert,
  Chip,
  Stack,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import FolderIcon from '@mui/icons-material/Folder';
import { useNavigate } from 'react-router-dom';
import { useHotkeys } from 'react-hotkeys-hook';
import { collectionsAPI } from '../services/api';
import { notify } from '../utils/notifications';
import { CollectionCardSkeleton } from './common/SkeletonLoader';

const CollectionList = ({ onRefresh }) => {
  const [collections, setCollections] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [newCollection, setNewCollection] = useState({
    name: '',
    description: '',
  });
  const [creating, setCreating] = useState(false);
  const navigate = useNavigate();

  const fetchCollections = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await collectionsAPI.list();
      setCollections(data.collections || []);
    } catch (err) {
      setError('Failed to load collections');
      notify.error('Failed to load collections');
      console.error('Error fetching collections:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCollections();
  }, []);

  const handleCreateCollection = async () => {
    if (!newCollection.name.trim()) {
      notify.warning('Please enter a collection name');
      return;
    }

    try {
      setCreating(true);
      await collectionsAPI.create(newCollection);
      notify.success(`Collection "${newCollection.name}" created successfully`);
      setCreateDialogOpen(false);
      setNewCollection({ name: '', description: '' });
      await fetchCollections();
      onRefresh();
    } catch (err) {
      notify.error('Failed to create collection: ' + err.message);
      console.error('Error creating collection:', err);
    } finally {
      setCreating(false);
    }
  };

  const handleDeleteCollection = async (collectionName) => {
    if (!window.confirm(`Are you sure you want to delete collection "${collectionName}"?`)) {
      return;
    }

    try {
      await collectionsAPI.delete(collectionName);
      notify.success(`Collection "${collectionName}" deleted successfully`);
      await fetchCollections();
      onRefresh();
    } catch (err) {
      notify.error('Failed to delete collection: ' + err.message);
      console.error('Error deleting collection:', err);
    }
  };

  const handleCollectionClick = (collection) => {
    navigate(`/collections/${collection.name}/documents`);
  };

  // Keyboard shortcuts
  useHotkeys('ctrl+n, cmd+n', (e) => {
    e.preventDefault();
    setCreateDialogOpen(true);
  });

  if (loading) {
    return (
      <Box>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
          <Typography variant="h4" component="h1" fontWeight="bold">
            Collections
          </Typography>
        </Box>
        <Grid container spacing={3}>
          {[...Array(6)].map((_, index) => (
            <Grid item xs={12} sm={6} md={4} key={index}>
              <CollectionCardSkeleton />
            </Grid>
          ))}
        </Grid>
      </Box>
    );
  }

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h4" component="h1" fontWeight="bold">
          Collections
        </Typography>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => setCreateDialogOpen(true)}
          size="large"
        >
          New Collection
        </Button>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}

      {collections.length === 0 ? (
        <Card sx={{ textAlign: 'center', py: 8 }}>
          <CardContent>
            <FolderIcon sx={{ fontSize: 80, color: 'text.secondary', mb: 2 }} />
            <Typography variant="h6" color="text.secondary" gutterBottom>
              No collections yet
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
              Create your first collection to start managing documents
            </Typography>
            <Button
              variant="contained"
              startIcon={<AddIcon />}
              onClick={() => setCreateDialogOpen(true)}
            >
              Create Collection
            </Button>
          </CardContent>
        </Card>
      ) : (
        <Grid container spacing={3}>
          {collections.map((collection) => (
            <Grid item xs={12} sm={6} md={4} key={collection.id}>
              <Card
                sx={{
                  height: '100%',
                  cursor: 'pointer',
                  transition: 'transform 0.2s, box-shadow 0.2s',
                  '&:hover': {
                    transform: 'translateY(-4px)',
                    boxShadow: 4,
                  },
                }}
              >
                <CardContent>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 2 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', flex: 1 }} onClick={() => handleCollectionClick(collection)}>
                      <FolderIcon sx={{ fontSize: 40, color: 'primary.main', mr: 1 }} />
                      <Typography variant="h6" component="div" fontWeight="bold">
                        {collection.name}
                      </Typography>
                    </Box>
                    <IconButton
                      size="small"
                      color="error"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDeleteCollection(collection.name);
                      }}
                    >
                      <DeleteIcon />
                    </IconButton>
                  </Box>

                  <Box onClick={() => handleCollectionClick(collection)}>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 2, minHeight: 40 }}>
                      {collection.metadata?.description || 'No description'}
                    </Typography>

                    <Stack direction="row" spacing={1}>
                      <Chip
                        label={`${collection.count} documents`}
                        size="small"
                        color="primary"
                        variant="outlined"
                      />
                    </Stack>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      )}

      {/* Create Collection Dialog */}
      <Dialog
        open={createDialogOpen}
        onClose={() => !creating && setCreateDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Create New Collection</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="Collection Name"
            fullWidth
            required
            value={newCollection.name}
            onChange={(e) => setNewCollection({ ...newCollection, name: e.target.value })}
            disabled={creating}
            sx={{ mb: 2 }}
          />
          <TextField
            margin="dense"
            label="Description"
            fullWidth
            multiline
            rows={3}
            value={newCollection.description}
            onChange={(e) => setNewCollection({ ...newCollection, description: e.target.value })}
            disabled={creating}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateDialogOpen(false)} disabled={creating}>
            Cancel
          </Button>
          <Button onClick={handleCreateCollection} variant="contained" disabled={creating}>
            {creating ? <CircularProgress size={24} /> : 'Create'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default CollectionList;

