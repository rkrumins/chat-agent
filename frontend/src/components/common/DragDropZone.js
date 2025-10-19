import React from 'react';
import { useDropzone } from 'react-dropzone';
import { Box, Typography, Paper } from '@mui/material';
import CloudUploadIcon from '@mui/icons-material/CloudUpload';
import DescriptionIcon from '@mui/icons-material/Description';
import PictureAsPdfIcon from '@mui/icons-material/PictureAsPdf';

const DragDropZone = ({ onFileSelect, accept, multiple = false, disabled = false }) => {
  const { getRootProps, getInputProps, isDragActive, isDragReject } = useDropzone({
    onDrop: (acceptedFiles) => {
      if (acceptedFiles.length > 0) {
        if (multiple) {
          onFileSelect(acceptedFiles);
        } else {
          onFileSelect(acceptedFiles[0]);
        }
      }
    },
    accept: accept || {
      'application/pdf': ['.pdf'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
      'application/msword': ['.doc'],
      'text/plain': ['.txt'],
      'application/json': ['.json'],
    },
    multiple,
    disabled,
  });

  const getFileIcon = () => {
    if (accept && accept['application/pdf']) return <PictureAsPdfIcon sx={{ fontSize: 48 }} />;
    return <DescriptionIcon sx={{ fontSize: 48 }} />;
  };

  return (
    <Paper
      {...getRootProps()}
      sx={{
        border: '2px dashed',
        borderColor: isDragActive
          ? 'primary.main'
          : isDragReject
          ? 'error.main'
          : 'grey.400',
        bgcolor: isDragActive
          ? 'primary.50'
          : isDragReject
          ? 'error.50'
          : 'background.default',
        p: 4,
        textAlign: 'center',
        cursor: disabled ? 'not-allowed' : 'pointer',
        transition: 'all 0.3s ease',
        opacity: disabled ? 0.5 : 1,
        '&:hover': !disabled && {
          borderColor: 'primary.main',
          bgcolor: 'primary.50',
          transform: 'scale(1.01)',
        },
      }}
    >
      <input {...getInputProps()} />
      <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
        {isDragActive ? (
          <>
            <CloudUploadIcon sx={{ fontSize: 64, color: 'primary.main' }} />
            <Typography variant="h6" color="primary">
              Drop {multiple ? 'files' : 'file'} here
            </Typography>
          </>
        ) : isDragReject ? (
          <>
            {getFileIcon()}
            <Typography variant="h6" color="error">
              Invalid file type
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Please upload PDF, DOCX, TXT, or JSON files
            </Typography>
          </>
        ) : (
          <>
            <CloudUploadIcon sx={{ fontSize: 64, color: 'text.secondary' }} />
            <Typography variant="h6" color="text.primary">
              Drag & drop {multiple ? 'files' : 'a file'} here
            </Typography>
            <Typography variant="body2" color="text.secondary">
              or click to browse
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ mt: 1 }}>
              Supported: PDF, DOCX, TXT, JSON
            </Typography>
          </>
        )}
      </Box>
    </Paper>
  );
};

export default DragDropZone;

