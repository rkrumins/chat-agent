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
  const [nameError, setNameError] = useState('');
  const navigate = useNavigate();
  
  // Validate collection name according to ChromaDB rules
  const validateCollectionName = (name) => {
    if (!name || !name.trim()) {
      return 'Collection name is required';
    }
    
    const trimmedName = name.trim();
    
    // Check length (3-512 characters)
    if (trimmedName.length < 3) {
      return 'Collection name must be at least 3 characters long';
    }
    if (trimmedName.length > 512) {
      return 'Collection name must be 512 characters or less';
    }
    
    // Check allowed characters: [a-zA-Z0-9._-]
    const validPattern = /^[a-zA-Z0-9._-]+$/;
    if (!validPattern.test(trimmedName)) {
      return 'Collection name can only contain letters, numbers, dots (.), underscores (_), and hyphens (-). No spaces allowed.';
    }
    
    // Must start and end with alphanumeric [a-zA-Z0-9]
    const alphanumericPattern = /^[a-zA-Z0-9].*[a-zA-Z0-9]$|^[a-zA-Z0-9]$/;
    if (!alphanumericPattern.test(trimmedName)) {
      return 'Collection name must start and end with a letter or number';
    }
    
    return '';
  };

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
    // Validate collection name
    const validationError = validateCollectionName(newCollection.name);
    if (validationError) {
      setNameError(validationError);
      notify.error(validationError);
      return;
    }
    
    setNameError(''); // Clear any previous errors

    try {
      setCreating(true);
      await collectionsAPI.create(newCollection);
      notify.success(`Collection "${newCollection.name}" created successfully`);
      setCreateDialogOpen(false);
      setNewCollection({ name: '', description: '' });
      setNameError('');
      await fetchCollections();
      onRefresh();
    } catch (err) {
      // Parse error message from backend
      let errorMessage = 'Failed to create collection';
      
      if (err.response?.data?.detail) {
        const detail = err.response.data.detail;
        // Check for validation errors
        if (detail.includes('Validation error') || detail.includes('Expected a name')) {
          errorMessage = 'Invalid collection name. Collection names must:\n' +
            '• Be 3-512 characters long\n' +
            '• Contain only letters, numbers, dots (.), underscores (_), and hyphens (-)\n' +
            '• Start and end with a letter or number\n' +
            '• Not contain spaces\n\n' +
            `Example: "software-engineering" or "software_engineering" instead of "Software Engineering"`;
        } else {
          errorMessage = detail;
        }
      } else if (err.message) {
        errorMessage = err.message;
      }
      
      setNameError(errorMessage.split('\n')[0]); // Show first line in TextField
      notify.error(errorMessage);
      console.error('Error creating collection:', err);
    } finally {
      setCreating(false);
    }
  };
  
  const handleNameChange = (e) => {
    const name = e.target.value;
    setNewCollection({ ...newCollection, name });
    // Clear error when user starts typing
    if (nameError) {
      setNameError('');
    }
  };
  
  const handleDialogClose = () => {
    if (!creating) {
      setCreateDialogOpen(false);
      setNewCollection({ name: '', description: '' });
      setNameError('');
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

                    <Stack direction="row" spacing={1} sx={{ mb: 1 }}>
                      <Chip
                        label={`${collection.count} documents`}
                        size="small"
                        color="primary"
                        variant="outlined"
                      />
                    </Stack>
                    
                    {/* Embedding Model Info */}
                    {collection.metadata?.embedding_model && (
                      <Box sx={{ mt: 1 }}>
                        <Typography variant="caption" color="text.secondary" display="block">
                          Embedding Model:
                        </Typography>
                        <Chip
                          label={collection.metadata.embedding_model}
                          size="small"
                          sx={{ 
                            mt: 0.5,
                            fontSize: '0.7rem',
                            height: '20px',
                            bgcolor: 'info.light',
                            color: 'info.contrastText'
                          }}
                        />
                        {collection.metadata?.embedding_dimension && (
                          <Typography variant="caption" color="text.secondary" sx={{ ml: 1, display: 'inline' }}>
                            ({collection.metadata.embedding_dimension}D)
                          </Typography>
                        )}
                      </Box>
                    )}
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
        onClose={handleDialogClose}
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
            onChange={handleNameChange}
            onBlur={(e) => {
              // Validate on blur
              const error = validateCollectionName(e.target.value);
              if (error) {
                setNameError(error);
              }
            }}
            disabled={creating}
            error={!!nameError}
            helperText={nameError || '3-512 characters, letters, numbers, dots, underscores, hyphens only. Must start/end with letter/number. Example: "software-engineering"'}
            sx={{ mb: 2 }}
          />
          
          {nameError && nameError.includes('spaces') && (
            <Alert severity="info" sx={{ mb: 2 }}>
              <Typography variant="body2">
                <strong>Tip:</strong> Replace spaces with hyphens or underscores. For example:
                <br />• "Software Engineering" → "software-engineering" or "software_engineering"
                <br />• "My Collection" → "my-collection" or "my_collection"
              </Typography>
            </Alert>
          )}
          
          <TextField
            margin="dense"
            label="Description (optional)"
            fullWidth
            multiline
            rows={3}
            value={newCollection.description}
            onChange={(e) => setNewCollection({ ...newCollection, description: e.target.value })}
            disabled={creating}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={handleDialogClose} disabled={creating}>
            Cancel
          </Button>
          <Button 
            onClick={handleCreateCollection} 
            variant="contained" 
            disabled={creating || (!!nameError && newCollection.name.trim() !== '')}
          >
            {creating ? <CircularProgress size={24} /> : 'Create'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default CollectionList;

