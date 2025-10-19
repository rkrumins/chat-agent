import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
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
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Collapse,
  Tooltip,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Tabs,
  Tab,
  Checkbox,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import DescriptionIcon from '@mui/icons-material/Description';
import UploadFileIcon from '@mui/icons-material/UploadFile';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import TextFieldsIcon from '@mui/icons-material/TextFields';
import { useHotkeys } from 'react-hotkeys-hook';
import { documentsAPI, tasksAPI, bulkAPI } from '../services/api';
import { notify } from '../utils/notifications';
import DragDropZone from './common/DragDropZone';
import SearchBar from './common/SearchBar';
import { DocumentTableSkeleton } from './common/SkeletonLoader';
import BulkActionToolbar from './common/BulkActionToolbar';

const DocumentList = ({ onRefresh }) => {
  const { collectionName } = useParams();
  const [documents, setDocuments] = useState([]);
  const [filteredDocuments, setFilteredDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [selectedDocument, setSelectedDocument] = useState(null);
  const [expandedRows, setExpandedRows] = useState({});
  const [processingTasks, setProcessingTasks] = useState({});
  const [uploadMethod, setUploadMethod] = useState(0); // 0 = text, 1 = file
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedDocuments, setSelectedDocuments] = useState([]);

  const [formData, setFormData] = useState({
    name: '',
    purpose: '',
    tags: '',
    content: '',
    custom_metadata: '',
    chunk_size: 500,
    chunk_overlap: 50,
  });

  const [selectedFile, setSelectedFile] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const fetchDocuments = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await documentsAPI.list(collectionName);
      setDocuments(data.documents || []);
      setFilteredDocuments(data.documents || []);
    } catch (err) {
      setError('Failed to load documents');
      notify.error('Failed to load documents');
      console.error('Error fetching documents:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (collectionName) {
      fetchDocuments();
    }
  }, [collectionName]);

  // Search/filter functionality
  useEffect(() => {
    if (!searchQuery.trim()) {
      setFilteredDocuments(documents);
      return;
    }

    const query = searchQuery.toLowerCase();
    const filtered = documents.filter(doc => 
      doc.metadata.name?.toLowerCase().includes(query) ||
      doc.metadata.purpose?.toLowerCase().includes(query) ||
      doc.metadata.tags?.toLowerCase().includes(query) ||
      doc.content?.toLowerCase().includes(query)
    );
    setFilteredDocuments(filtered);
  }, [searchQuery, documents]);

  // Poll for task status
  useEffect(() => {
    const taskIds = Object.keys(processingTasks);
    if (taskIds.length === 0) return;

    const interval = setInterval(async () => {
      for (const taskId of taskIds) {
        try {
          const status = await tasksAPI.getStatus(taskId);
          setProcessingTasks((prev) => ({
            ...prev,
            [taskId]: status,
          }));

          if (status.status === 'completed' || status.status === 'failed') {
            setTimeout(() => {
              setProcessingTasks((prev) => {
                const updated = { ...prev };
                delete updated[taskId];
                return updated;
              });
              fetchDocuments();
              onRefresh();
            }, 2000);
          }
        } catch (err) {
          console.error('Error fetching task status:', err);
        }
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [processingTasks]);

  const resetForm = () => {
    setFormData({
      name: '',
      purpose: '',
      tags: '',
      content: '',
      custom_metadata: '',
      chunk_size: 500,
      chunk_overlap: 50,
    });
    setSelectedFile(null);
    setUploadMethod(0);
  };

  const handleFileChange = (event) => {
    const file = event.target.files[0];
    setSelectedFile(file);
    if (file && !formData.name) {
      // Auto-fill name from filename
      setFormData({ ...formData, name: file.name });
    }
  };

  const handleCreateDocument = async () => {
    if (!formData.name.trim()) {
      notify.warning('Please provide a document name');
      return;
    }

    if (uploadMethod === 0 && !formData.content.trim()) {
      notify.warning('Please provide text content');
      return;
    }

    if (uploadMethod === 1 && !selectedFile) {
      notify.warning('Please select a file to upload');
      return;
    }

    try {
      setSubmitting(true);

      let response;
      
      if (uploadMethod === 1) {
        // File upload
        const formDataToSend = new FormData();
        formDataToSend.append('file', selectedFile);
        formDataToSend.append('name', formData.name);
        formDataToSend.append('purpose', formData.purpose);
        formDataToSend.append('tags', formData.tags);
        formDataToSend.append('chunk_size', formData.chunk_size.toString());
        formDataToSend.append('chunk_overlap', formData.chunk_overlap.toString());
        formDataToSend.append('custom_metadata', formData.custom_metadata || '{}');

        response = await documentsAPI.uploadFile(collectionName, formDataToSend);
      } else {
        // Text input
        const documentData = {
          collection_name: collectionName,
          metadata: {
            name: formData.name,
            purpose: formData.purpose,
            tags: formData.tags,
            custom_metadata: formData.custom_metadata ? JSON.parse(formData.custom_metadata) : {},
          },
          content: formData.content,
          chunk_size: formData.chunk_size,
          chunk_overlap: formData.chunk_overlap,
        };

        response = await documentsAPI.create(collectionName, documentData);
      }

      // Track the task
      if (response.task_id) {
        setProcessingTasks((prev) => ({
          ...prev,
          [response.task_id]: {
            task_id: response.task_id,
            status: 'pending',
            message: 'Processing...',
            progress: 0,
          },
        }));
        notify.info('Document processing started');
      }

      setCreateDialogOpen(false);
      resetForm();
      await fetchDocuments();
      onRefresh();
    } catch (err) {
      notify.error('Failed to create document: ' + (err.response?.data?.detail || err.message));
      console.error('Error creating document:', err);
    } finally {
      setSubmitting(false);
    }
  };

  const handleEditDocument = async () => {
    if (!formData.name.trim()) {
      notify.warning('Please fill in name');
      return;
    }

    try {
      setSubmitting(true);

      const updateData = {
        metadata: {
          name: formData.name,
          purpose: formData.purpose,
          tags: formData.tags,
          custom_metadata: formData.custom_metadata ? JSON.parse(formData.custom_metadata) : {},
        },
        chunk_size: formData.chunk_size,
        chunk_overlap: formData.chunk_overlap,
      };

      if (formData.content.trim()) {
        updateData.content = formData.content;
      }

      const response = await documentsAPI.update(
        collectionName,
        selectedDocument.id,
        updateData
      );

      // Track the task
      if (response.task_id) {
        setProcessingTasks((prev) => ({
          ...prev,
          [response.task_id]: {
            task_id: response.task_id,
            status: 'pending',
            message: 'Processing...',
            progress: 0,
          },
        }));
        notify.info('Document update processing started');
      } else {
        notify.success('Document updated successfully');
      }

      setEditDialogOpen(false);
      setSelectedDocument(null);
      resetForm();
      await fetchDocuments();
      onRefresh();
    } catch (err) {
      notify.error('Failed to update document: ' + (err.response?.data?.detail || err.message));
      console.error('Error updating document:', err);
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeleteDocument = async (documentId) => {
    if (!window.confirm('Are you sure you want to delete this document?')) {
      return;
    }

    try {
      await documentsAPI.delete(collectionName, documentId);
      notify.success('Document deleted successfully');
      await fetchDocuments();
      onRefresh();
    } catch (err) {
      notify.error('Failed to delete document: ' + (err.response?.data?.detail || err.message));
      console.error('Error deleting document:', err);
    }
  };

  const openEditDialog = (document) => {
    setSelectedDocument(document);
    setFormData({
      name: document.metadata.name || '',
      purpose: document.metadata.purpose || '',
      tags: document.metadata.tags || '',
      content: document.content || '',
      custom_metadata: JSON.stringify(
        document.metadata.custom_metadata || {},
        null,
        2
      ),
      chunk_size: document.metadata.chunk_size || 500,
      chunk_overlap: document.metadata.chunk_overlap || 50,
    });
    setEditDialogOpen(true);
  };

  const toggleRowExpansion = (documentId) => {
    setExpandedRows((prev) => ({
      ...prev,
      [documentId]: !prev[documentId],
    }));
  };

  // Bulk selection handlers
  const handleSelectAll = (event) => {
    if (event.target.checked) {
      setSelectedDocuments(filteredDocuments.map(doc => doc.id));
    } else {
      setSelectedDocuments([]);
    }
  };

  const handleSelectOne = (documentId) => {
    setSelectedDocuments((prev) => {
      if (prev.includes(documentId)) {
        return prev.filter(id => id !== documentId);
      } else {
        return [...prev, documentId];
      }
    });
  };

  const handleBulkDelete = async () => {
    try {
      const result = await bulkAPI.deleteDocuments(collectionName, selectedDocuments);
      notify.success(`Deleted ${result.deleted} of ${result.total} document(s)`);
      
      if (result.errors && result.errors.length > 0) {
        notify.warning(`${result.errors.length} document(s) failed to delete`);
      }
      
      setSelectedDocuments([]);
      await fetchDocuments();
      onRefresh();
    } catch (err) {
      notify.error('Failed to delete documents: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleBulkUpdateTags = async (tags, mode) => {
    try {
      const result = await bulkAPI.updateTags(collectionName, selectedDocuments, tags, mode);
      notify.success(`Updated tags for ${result.updated} of ${result.total} document(s)`);
      
      if (result.errors && result.errors.length > 0) {
        notify.warning(`${result.errors.length} document(s) failed to update`);
      }
      
      setSelectedDocuments([]);
      await fetchDocuments();
      onRefresh();
    } catch (err) {
      notify.error('Failed to update tags: ' + (err.response?.data?.detail || err.message));
    }
  };

  const isSelected = (documentId) => selectedDocuments.includes(documentId);

  // Keyboard shortcuts
  useHotkeys('ctrl+n, cmd+n', (e) => {
    e.preventDefault();
    setCreateDialogOpen(true);
  });

  useHotkeys('ctrl+f, cmd+f', (e) => {
    e.preventDefault();
    // Focus search bar if it exists
    const searchInput = document.querySelector('input[placeholder*="Search"]');
    if (searchInput) searchInput.focus();
  });

  useHotkeys('escape', () => {
    if (createDialogOpen) setCreateDialogOpen(false);
    if (editDialogOpen) setEditDialogOpen(false);
  });

  if (loading) {
    return (
      <Box>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
          <Box>
            <Typography variant="h4" component="h1" fontWeight="bold">
              Documents
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Collection: {collectionName}
            </Typography>
          </Box>
        </Box>
        <DocumentTableSkeleton />
      </Box>
    );
  }

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Box>
          <Typography variant="h4" component="h1" fontWeight="bold">
            Documents
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Collection: {collectionName}
          </Typography>
        </Box>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => setCreateDialogOpen(true)}
          size="large"
        >
          Add Document
        </Button>
      </Box>

      {/* Search Bar */}
      {documents.length > 0 && (
        <Box sx={{ mb: 3 }}>
          <SearchBar
            value={searchQuery}
            onChange={setSearchQuery}
            placeholder="Search documents by name, purpose, tags, or content..."
          />
          {searchQuery && (
            <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
              Found {filteredDocuments.length} of {documents.length} documents
            </Typography>
          )}
        </Box>
      )}

      {/* Bulk Action Toolbar */}
      <BulkActionToolbar
        selectedCount={selectedDocuments.length}
        onDelete={handleBulkDelete}
        onUpdateTags={handleBulkUpdateTags}
        onClear={() => setSelectedDocuments([])}
        collectionName={collectionName}
      />

      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}

      {/* Processing Tasks */}
      {Object.values(processingTasks).length > 0 && (
        <Box sx={{ mb: 3 }}>
          {Object.values(processingTasks).map((task) => (
            <Alert
              key={task.task_id}
              severity={
                task.status === 'completed'
                  ? 'success'
                  : task.status === 'failed'
                  ? 'error'
                  : 'info'
              }
              sx={{ mb: 1 }}
            >
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                <Typography variant="body2">{task.message}</Typography>
                {task.status === 'processing' && (
                  <CircularProgress size={16} />
                )}
                <Typography variant="caption">({task.progress}%)</Typography>
              </Box>
            </Alert>
          ))}
        </Box>
      )}

      {filteredDocuments.length === 0 && documents.length === 0 ? (
        <Card sx={{ textAlign: 'center', py: 8 }}>
          <CardContent>
            <DescriptionIcon sx={{ fontSize: 80, color: 'text.secondary', mb: 2 }} />
            <Typography variant="h6" color="text.secondary" gutterBottom>
              No documents yet
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
              Add your first document to this collection
            </Typography>
            <Button
              variant="contained"
              startIcon={<AddIcon />}
              onClick={() => setCreateDialogOpen(true)}
            >
              Add Document
            </Button>
          </CardContent>
        </Card>
      ) : filteredDocuments.length === 0 ? (
        <Card sx={{ textAlign: 'center', py: 8 }}>
          <CardContent>
            <DescriptionIcon sx={{ fontSize: 80, color: 'text.secondary', mb: 2 }} />
            <Typography variant="h6" color="text.secondary" gutterBottom>
              No documents match your search
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
              Try different keywords or clear the search
            </Typography>
            <Button
              variant="outlined"
              onClick={() => setSearchQuery('')}
            >
              Clear Search
            </Button>
          </CardContent>
        </Card>
      ) : (
        <TableContainer component={Paper} sx={{ borderRadius: 2 }}>
          <Table>
            <TableHead>
              <TableRow sx={{ bgcolor: 'grey.50' }}>
                <TableCell padding="checkbox">
                  <Checkbox
                    indeterminate={selectedDocuments.length > 0 && selectedDocuments.length < filteredDocuments.length}
                    checked={filteredDocuments.length > 0 && selectedDocuments.length === filteredDocuments.length}
                    onChange={handleSelectAll}
                  />
                </TableCell>
                <TableCell width={50}></TableCell>
                <TableCell><strong>Name</strong></TableCell>
                <TableCell><strong>Purpose</strong></TableCell>
                <TableCell><strong>Tags</strong></TableCell>
                <TableCell><strong>Chunks</strong></TableCell>
                <TableCell><strong>Updated</strong></TableCell>
                <TableCell align="right"><strong>Actions</strong></TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {filteredDocuments.map((doc) => (
                <React.Fragment key={doc.id}>
                  <TableRow hover selected={isSelected(doc.id)}>
                    <TableCell padding="checkbox">
                      <Checkbox
                        checked={isSelected(doc.id)}
                        onChange={() => handleSelectOne(doc.id)}
                      />
                    </TableCell>
                    <TableCell>
                      <IconButton
                        size="small"
                        onClick={() => toggleRowExpansion(doc.id)}
                      >
                        {expandedRows[doc.id] ? (
                          <ExpandLessIcon />
                        ) : (
                          <ExpandMoreIcon />
                        )}
                      </IconButton>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" fontWeight="medium">
                        {doc.metadata.name}
                      </Typography>
                      {doc.metadata.filename && (
                        <Typography variant="caption" color="text.secondary">
                          {doc.metadata.filename}
                        </Typography>
                      )}
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" color="text.secondary">
                        {doc.metadata.purpose || '-'}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      {doc.metadata.tags && (
                        <Typography variant="body2" color="text.secondary">
                          {doc.metadata.tags}
                        </Typography>
                      )}
                    </TableCell>
                    <TableCell>
                      <Chip 
                        label={`${doc.metadata.chunk_count || 1} chunks`} 
                        size="small" 
                        variant="outlined"
                      />
                      <Typography variant="caption" display="block" color="text.secondary">
                        Size: {doc.metadata.chunk_size || 500}, Overlap: {doc.metadata.chunk_overlap || 50}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="caption" color="text.secondary">
                        {doc.updated_at
                          ? new Date(doc.updated_at).toLocaleString()
                          : '-'}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Tooltip title="Edit">
                        <IconButton
                          size="small"
                          color="primary"
                          onClick={() => openEditDialog(doc)}
                        >
                          <EditIcon />
                        </IconButton>
                      </Tooltip>
                      <Tooltip title="Delete">
                        <IconButton
                          size="small"
                          color="error"
                          onClick={() => handleDeleteDocument(doc.id)}
                        >
                          <DeleteIcon />
                        </IconButton>
                      </Tooltip>
                    </TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell colSpan={8} sx={{ py: 0, borderBottom: expandedRows[doc.id] ? undefined : 'none' }}>
                      <Collapse in={expandedRows[doc.id]} timeout="auto" unmountOnExit>
                        <Box sx={{ p: 2, bgcolor: 'grey.50' }}>
                          <Typography variant="subtitle2" gutterBottom>
                            Content Preview:
                          </Typography>
                          <Typography
                            variant="body2"
                            color="text.secondary"
                            sx={{
                              whiteSpace: 'pre-wrap',
                              maxHeight: 200,
                              overflow: 'auto',
                              p: 2,
                              bgcolor: 'white',
                              borderRadius: 1,
                            }}
                          >
                            {doc.content.substring(0, 500)}
                            {doc.content.length > 500 && '...'}
                          </Typography>
                        </Box>
                      </Collapse>
                    </TableCell>
                  </TableRow>
                </React.Fragment>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {/* Create Document Dialog */}
      <Dialog
        open={createDialogOpen}
        onClose={() => !submitting && setCreateDialogOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>Add New Document</DialogTitle>
        <DialogContent>
          <Tabs value={uploadMethod} onChange={(e, v) => setUploadMethod(v)} sx={{ mb: 2 }}>
            <Tab icon={<TextFieldsIcon />} label="Text Input" />
            <Tab icon={<UploadFileIcon />} label="File Upload" />
          </Tabs>

          <TextField
            autoFocus
            margin="dense"
            label="Document Name *"
            fullWidth
            required
            value={formData.name}
            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
            disabled={submitting}
            sx={{ mb: 2 }}
          />
          
          <TextField
            margin="dense"
            label="Purpose (optional)"
            fullWidth
            value={formData.purpose}
            onChange={(e) =>
              setFormData({ ...formData, purpose: e.target.value })
            }
            disabled={submitting}
            sx={{ mb: 2 }}
          />
          
          <TextField
            margin="dense"
            label="Tags (comma-separated)"
            fullWidth
            placeholder="e.g., important, reference, tutorial"
            value={formData.tags}
            onChange={(e) => setFormData({ ...formData, tags: e.target.value })}
            disabled={submitting}
            sx={{ mb: 2 }}
          />

          {uploadMethod === 0 ? (
            <TextField
              margin="dense"
              label="Content *"
              fullWidth
              required
              multiline
              rows={8}
              value={formData.content}
              onChange={(e) =>
                setFormData({ ...formData, content: e.target.value })
              }
              disabled={submitting}
              sx={{ mb: 2 }}
            />
          ) : (
            <Box sx={{ mb: 2 }}>
              <DragDropZone
                onFileSelect={setSelectedFile}
                disabled={submitting}
              />
              {selectedFile && (
                <Alert severity="success" sx={{ mt: 2 }}>
                  <Typography variant="body2">
                    <strong>Selected:</strong> {selectedFile.name} ({(selectedFile.size / 1024).toFixed(2)} KB)
                  </Typography>
                </Alert>
              )}
            </Box>
          )}

          <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 2, mb: 2 }}>
            <TextField
              margin="dense"
              label="Chunk Size"
              type="number"
              value={formData.chunk_size}
              onChange={(e) =>
                setFormData({ ...formData, chunk_size: parseInt(e.target.value) || 500 })
              }
              disabled={submitting}
              helperText="Characters per chunk"
            />
            <TextField
              margin="dense"
              label="Chunk Overlap"
              type="number"
              value={formData.chunk_overlap}
              onChange={(e) =>
                setFormData({ ...formData, chunk_overlap: parseInt(e.target.value) || 50 })
              }
              disabled={submitting}
              helperText="Overlap between chunks"
            />
          </Box>

          <Alert severity="info" sx={{ mb: 2 }}>
            <Typography variant="caption">
              <strong>Chunk Size Tips:</strong><br/>
              • Policies/Long docs: 800-1000 with 100 overlap<br/>
              • General docs: 500 with 50 overlap (default)<br/>
              • Definitions/Short: 200-300 with 20 overlap
            </Typography>
          </Alert>

          <TextField
            margin="dense"
            label="Custom Metadata (JSON, optional)"
            fullWidth
            multiline
            rows={3}
            placeholder='{"key": "value"}'
            value={formData.custom_metadata}
            onChange={(e) =>
              setFormData({ ...formData, custom_metadata: e.target.value })
            }
            disabled={submitting}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => { setCreateDialogOpen(false); resetForm(); }} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={handleCreateDocument} variant="contained" disabled={submitting}>
            {submitting ? <CircularProgress size={24} /> : 'Create'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Edit Document Dialog */}
      <Dialog
        open={editDialogOpen}
        onClose={() => !submitting && setEditDialogOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>Edit Document</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="Document Name *"
            fullWidth
            required
            value={formData.name}
            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
            disabled={submitting}
            sx={{ mb: 2 }}
          />
          <TextField
            margin="dense"
            label="Purpose"
            fullWidth
            value={formData.purpose}
            onChange={(e) =>
              setFormData({ ...formData, purpose: e.target.value })
            }
            disabled={submitting}
            sx={{ mb: 2 }}
          />
          <TextField
            margin="dense"
            label="Tags (comma-separated)"
            fullWidth
            placeholder="e.g., important, reference, tutorial"
            value={formData.tags}
            onChange={(e) => setFormData({ ...formData, tags: e.target.value })}
            disabled={submitting}
            sx={{ mb: 2 }}
          />
          <TextField
            margin="dense"
            label="Content (leave empty to keep existing)"
            fullWidth
            multiline
            rows={8}
            value={formData.content}
            onChange={(e) =>
              setFormData({ ...formData, content: e.target.value })
            }
            disabled={submitting}
            sx={{ mb: 2 }}
          />
          <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 2, mb: 2 }}>
            <TextField
              margin="dense"
              label="Chunk Size"
              type="number"
              value={formData.chunk_size}
              onChange={(e) =>
                setFormData({ ...formData, chunk_size: parseInt(e.target.value) || 500 })
              }
              disabled={submitting}
              helperText="Characters per chunk"
            />
            <TextField
              margin="dense"
              label="Chunk Overlap"
              type="number"
              value={formData.chunk_overlap}
              onChange={(e) =>
                setFormData({ ...formData, chunk_overlap: parseInt(e.target.value) || 50 })
              }
              disabled={submitting}
              helperText="Overlap between chunks"
            />
          </Box>
          <TextField
            margin="dense"
            label="Custom Metadata (JSON)"
            fullWidth
            multiline
            rows={3}
            placeholder='{"key": "value"}'
            value={formData.custom_metadata}
            onChange={(e) =>
              setFormData({ ...formData, custom_metadata: e.target.value })
            }
            disabled={submitting}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => { setEditDialogOpen(false); resetForm(); }} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={handleEditDocument} variant="contained" disabled={submitting}>
            {submitting ? <CircularProgress size={24} /> : 'Update'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default DocumentList;
