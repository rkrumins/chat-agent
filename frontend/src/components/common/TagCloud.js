import React, { useState, useEffect } from 'react';
import { Box, Chip, CircularProgress, Typography } from '@mui/material';
import { tagsAPI } from '../../services/api';

const TagCloud = ({ onTagClick, collectionName }) => {
  const [tags, setTags] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchTags();
  }, [collectionName]);

  const fetchTags = async () => {
    try {
      setLoading(true);
      const data = collectionName
        ? await tagsAPI.getByCollection(collectionName)
        : await tagsAPI.getAll();
      setTags(data.tags || []);
    } catch (err) {
      console.error('Error fetching tags:', err);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', p: 2 }}>
        <CircularProgress size={24} />
      </Box>
    );
  }

  if (tags.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ p: 2, textAlign: 'center' }}>
        No tags available
      </Typography>
    );
  }

  // Calculate sizes based on count
  const maxCount = Math.max(...tags.map(t => t.count));
  const minCount = Math.min(...tags.map(t => t.count));
  const countRange = maxCount - minCount || 1;

  const getSize = (count) => {
    const normalized = (count - minCount) / countRange;
    if (normalized > 0.66) return 'medium';
    if (normalized > 0.33) return 'small';
    return 'small';
  };

  const getColor = (count) => {
    const normalized = (count - minCount) / countRange;
    if (normalized > 0.66) return 'primary';
    if (normalized > 0.33) return 'default';
    return 'default';
  };

  return (
    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, p: 1 }}>
      {tags.slice(0, 20).map((tag, index) => (
        <Chip
          key={index}
          label={`${tag.tag} (${tag.count})`}
          size={getSize(tag.count)}
          color={getColor(tag.count)}
          onClick={() => onTagClick && onTagClick(tag.tag)}
          sx={{
            cursor: onTagClick ? 'pointer' : 'default',
            '&:hover': onTagClick && {
              transform: 'scale(1.05)',
              transition: 'transform 0.2s',
            },
          }}
        />
      ))}
    </Box>
  );
};

export default TagCloud;

