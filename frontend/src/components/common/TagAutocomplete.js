import React, { useState, useEffect } from 'react';
import { Autocomplete, TextField, Chip } from '@mui/material';
import { tagsAPI } from '../../services/api';

const TagAutocomplete = ({ value, onChange, collectionName, label = "Tags", placeholder = "Add tags...", disabled = false }) => {
  const [availableTags, setAvailableTags] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchTags();
  }, [collectionName]);

  const fetchTags = async () => {
    try {
      setLoading(true);
      const data = collectionName
        ? await tagsAPI.getByCollection(collectionName)
        : await tagsAPI.getAll();
      setAvailableTags(data.tags.map(t => t.tag));
    } catch (err) {
      console.error('Error fetching tags:', err);
    } finally {
      setLoading(false);
    }
  };

  // Parse value (could be string or array)
  const getTagsArray = () => {
    if (Array.isArray(value)) return value;
    if (typeof value === 'string') {
      return value.split(',').map(t => t.trim()).filter(t => t);
    }
    return [];
  };

  const handleChange = (event, newValue) => {
    // newValue is an array of selected tags
    onChange(newValue.join(', '));
  };

  return (
    <Autocomplete
      multiple
      freeSolo
      options={availableTags}
      value={getTagsArray()}
      onChange={handleChange}
      disabled={disabled}
      loading={loading}
      renderTags={(value, getTagProps) =>
        value.map((option, index) => (
          <Chip
            variant="outlined"
            label={option}
            {...getTagProps({ index })}
          />
        ))
      }
      renderInput={(params) => (
        <TextField
          {...params}
          variant="outlined"
          label={label}
          placeholder={placeholder}
        />
      )}
    />
  );
};

export default TagAutocomplete;

