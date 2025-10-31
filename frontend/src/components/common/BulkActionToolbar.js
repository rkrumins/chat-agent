import React, { useState } from 'react';
import {
  Box,
  Toolbar,
  Typography,
  IconButton,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Tooltip,
} from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import LabelIcon from '@mui/icons-material/Label';
import CloseIcon from '@mui/icons-material/Close';
import TagAutocomplete from './TagAutocomplete';

const BulkActionToolbar = ({
  selectedCount,
  onDelete,
  onUpdateTags,
  onClear,
  collectionName,
}) => {
  const [tagDialogOpen, setTagDialogOpen] = useState(false);
  const [tagValue, setTagValue] = useState('');
  const [tagMode, setTagMode] = useState('append');

  const handleDeleteClick = () => {
    if (window.confirm(`Are you sure you want to delete ${selectedCount} document(s)?`)) {
      onDelete();
    }
  };

  const handleTagUpdate = () => {
    if (!tagValue.trim()) {
      return;
    }
    onUpdateTags(tagValue, tagMode);
    setTagDialogOpen(false);
    setTagValue('');
  };

  if (selectedCount === 0) return null;

  return (
    <>
      <Toolbar
        sx={{
          pl: { sm: 2 },
          pr: { xs: 1, sm: 1 },
          bgcolor: 'primary.main',
          color: 'primary.contrastText',
          borderRadius: 1,
          mb: 2,
        }}
      >
        <Typography sx={{ flex: '1 1 100%' }} variant="subtitle1">
          {selectedCount} selected
        </Typography>

        <Tooltip title="Update tags">
          <IconButton color="inherit" onClick={() => setTagDialogOpen(true)}>
            <LabelIcon />
          </IconButton>
        </Tooltip>

        <Tooltip title="Delete selected">
          <IconButton color="inherit" onClick={handleDeleteClick}>
            <DeleteIcon />
          </IconButton>
        </Tooltip>

        <Tooltip title="Clear selection">
          <IconButton color="inherit" onClick={onClear}>
            <CloseIcon />
          </IconButton>
        </Tooltip>
      </Toolbar>

      {/* Tag Update Dialog */}
      <Dialog
        open={tagDialogOpen}
        onClose={() => setTagDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Update Tags for {selectedCount} Document(s)</DialogTitle>
        <DialogContent>
          <FormControl fullWidth sx={{ mb: 2, mt: 1 }}>
            <InputLabel>Action</InputLabel>
            <Select
              value={tagMode}
              onChange={(e) => setTagMode(e.target.value)}
              label="Action"
            >
              <MenuItem value="replace">Replace All Tags</MenuItem>
              <MenuItem value="append">Add Tags</MenuItem>
              <MenuItem value="remove">Remove Tags</MenuItem>
            </Select>
          </FormControl>

          <TagAutocomplete
            value={tagValue}
            onChange={setTagValue}
            collectionName={collectionName}
            label="Tags"
            placeholder={
              tagMode === 'replace'
                ? 'New tags (replaces existing)'
                : tagMode === 'append'
                ? 'Tags to add'
                : 'Tags to remove'
            }
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setTagDialogOpen(false)}>Cancel</Button>
          <Button onClick={handleTagUpdate} variant="contained">
            Update Tags
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
};

export default BulkActionToolbar;

