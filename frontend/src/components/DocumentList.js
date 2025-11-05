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
  FormHelperText,
  Tabs,
  Tab,
  Checkbox,
  Grid,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import DescriptionIcon from '@mui/icons-material/Description';
import UploadFileIcon from '@mui/icons-material/UploadFile';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import TextFieldsIcon from '@mui/icons-material/TextFields';
import InfoIcon from '@mui/icons-material/Info';
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';
import PreviewIcon from '@mui/icons-material/Preview';
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
  const [advancedMode, setAdvancedMode] = useState(false);
  const [selectedPreset, setSelectedPreset] = useState('semantic');
  const [expandedAdvice, setExpandedAdvice] = useState(null); // Track which preset's advice is expanded
  const [showChunkPreview, setShowChunkPreview] = useState(false); // Show/hide chunk preview
  const [selectedDocumentChunks, setSelectedDocumentChunks] = useState(null); // Store chunks for selected document
  const [loadingChunks, setLoadingChunks] = useState(false);
  const [chunksDialogOpen, setChunksDialogOpen] = useState(false);

  const [formData, setFormData] = useState({
    name: '',
    purpose: '',
    tags: '',
    document_type: '',  // Optional: 'book', 'definition', 'article', 'blog_post', 'poem', 'unknown'
    content: '',
    custom_metadata: '',
    chunk_size: 1000,
    chunk_overlap: 200,
    chunking_strategy: 'semantic',  // Backend strategy: 'semantic', 'size', 'lines', 'paragraphs', 'sentences', 'custom'
    separator: '\n\n',  // Advanced: custom separator (for paragraphs or custom strategy)
    max_chunks: null,   // Advanced: limit total chunks
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

  // Poll for task status - optimized to avoid unnecessary re-renders
  useEffect(() => {
    const taskIds = Object.keys(processingTasks);
    if (taskIds.length === 0) return;

    const interval = setInterval(async () => {
      for (const taskId of taskIds) {
        try {
          const status = await tasksAPI.getStatus(taskId);
          setProcessingTasks((prev) => {
            const current = prev[taskId];
            // Only update if status or progress changed to avoid unnecessary re-renders
            if (!current || current.status !== status.status || current.progress !== status.progress) {
              return {
                ...prev,
                [taskId]: status,
              };
            }
            return prev;
          });

          // Handle completion or failure
          if (status.status === 'completed') {
            notify.success(`Document "${status.message || 'processed'}" completed successfully!`);
            setTimeout(() => {
              setProcessingTasks((prev) => {
                const updated = { ...prev };
                delete updated[taskId];
                return updated;
              });
              // Refresh documents list when task completes
              fetchDocuments();
              onRefresh();
            }, 1000);
          } else if (status.status === 'failed') {
            notify.error(`Document processing failed: ${status.message || 'Unknown error'}`);
            setTimeout(() => {
              setProcessingTasks((prev) => {
                const updated = { ...prev };
                delete updated[taskId];
                return updated;
              });
            }, 5000);
          }
        } catch (err) {
          console.error('Error fetching task status:', err);
        }
      }
    }, 2000); // Poll every 2 seconds instead of 1 to reduce load

    return () => clearInterval(interval);
  }, [processingTasks]);

  // Comprehensive chunking strategy presets with interactive advice
  const chunkPresets = {
    'semantic': {
      name: 'Semantic (Recommended)',
      strategy: 'semantic',
      size: 1000,
      overlap: 200,
      separator: null,
      icon: '🧠',
      description: 'AI-powered smart chunking that respects meaning and context. Best for most documents.',
      detailedAdvice: 'Automatically detects sentence and paragraph boundaries. Adapts chunk size based on document type (smaller for definitions, larger for books). Preserves semantic coherence.',
      example: 'Content: "Machine learning is a subset of artificial intelligence. It enables computers to learn from data without explicit programming.\n\nDeep learning uses neural networks..."\n\nResult: Chunks maintain complete thoughts and sentences together.',
      whenToUse: [
        'General documents (articles, blogs, books)',
        'Mixed content types',
        'When you want optimal retrieval quality',
        'First-time users (recommended default)'
      ],
      whenNotToUse: [
        'Structured data with fixed formats',
        'When you need exact control over chunk boundaries',
        'Code files (use code-specific strategy instead)'
      ]
    },
    'size': {
      name: 'Fixed Size',
      strategy: 'size',
      size: 1000,
      overlap: 200,
      separator: null,
      icon: '📏',
      description: 'Character-based chunking with fixed size. Consistent chunks regardless of content.',
      detailedAdvice: 'Splits text at word boundaries to respect your exact size limit. Good when you need uniform chunk sizes. Overlap helps maintain context between chunks.',
      example: 'Size: 500 chars, Overlap: 50 chars\n\nContent: "The quick brown fox jumps over the lazy dog. The dog was sleeping peacefully..."\n\nResult: Chunks are exactly ~500 characters, with 50 characters overlapping between adjacent chunks.',
      whenToUse: [
        'When you need consistent chunk sizes',
        'Simple documents without complex structure',
        'When you want predictable behavior',
        'Processing large volumes of similar content'
      ],
      whenNotToUse: [
        'Documents with important sentence boundaries',
        'Code or structured data',
        'When meaning preservation is critical'
      ]
    },
    'sentences': {
      name: 'By Sentences',
      strategy: 'sentences',
      size: 1000,
      overlap: 200,
      separator: null,
      icon: '💬',
      description: 'Chunks respect sentence boundaries. Maintains complete thoughts.',
      detailedAdvice: 'Never splits mid-sentence. Groups sentences together until reaching size limit. Perfect for natural language content where sentence integrity matters.',
      example: 'Content: "Artificial intelligence is transforming industries. Machine learning drives innovation. Deep learning enables breakthroughs."\n\nResult: Each chunk contains complete sentences, never breaking mid-sentence.',
      whenToUse: [
        'Narrative content (stories, articles)',
        'When sentence integrity is important',
        'Natural language documents',
        'Documents with clear sentence structure'
      ],
      whenNotToUse: [
        'Code or technical specs',
        'Structured lists or tables',
        'Documents without sentence markers'
      ]
    },
    'paragraphs': {
      name: 'By Paragraphs',
      strategy: 'paragraphs',
      size: 2000,
      overlap: 200,
      separator: '\n\n',
      icon: '📑',
      description: 'One paragraph per chunk. Ideal for well-structured documents.',
      detailedAdvice: 'Uses double newlines (\\n\\n) as paragraph separators. If a paragraph exceeds the size limit, it will be split by sentences. Great for documents with clear paragraph structure.',
      example: 'Content:\n\n"Paragraph 1 text here.\n\nParagraph 2 text here.\n\nParagraph 3 text here."\n\nResult: Each paragraph becomes its own chunk, preserving topic boundaries.',
      whenToUse: [
        'Well-formatted articles and essays',
        'Documents with clear paragraph structure',
        'When paragraph-level retrieval is desired',
        'Academic papers and reports'
      ],
      whenNotToUse: [
        'Single-paragraph documents',
        'Documents without paragraph breaks',
        'When you need smaller chunks'
      ]
    },
    'lines': {
      name: 'By Lines',
      strategy: 'lines',
      size: null,
      overlap: 0,
      separator: '\n',
      icon: '📝',
      description: 'One line per chunk. Perfect for structured lists and line-based data.',
      detailedAdvice: 'Each line becomes a separate chunk. No overlap by default. Ideal for structured data where each line is an independent unit.',
      example: 'Content:\n"Apple\nBanana\nCherry\nDate"\n\nResult: 4 separate chunks, one per line.',
      whenToUse: [
        'FAQs (Q&A format)',
        'Glossaries and dictionaries',
        'To-do lists and checklists',
        'Structured line-by-line data',
        'CSV-like content'
      ],
      whenNotToUse: [
        'Paragraphs or prose',
        'When context between lines matters',
        'Long-form documents',
        'When you need overlapping chunks'
      ]
    },
    'code': {
      name: 'Code / Technical',
      strategy: 'paragraphs',
      size: 1500,
      overlap: 150,
      separator: '\n\n',
      icon: '💻',
      description: 'Optimized for code, API docs, and technical documentation.',
      detailedAdvice: 'Uses paragraph-level chunking with code-friendly settings. Preserves function/class boundaries. Good for preserving code block integrity.',
      example: 'Content:\n\n"def calculate_sum(a, b):\n    return a + b\n\nclass Calculator:\n    def __init__(self):\n        ..."\n\nResult: Functions and classes stay together as coherent chunks.',
      whenToUse: [
        'Source code documentation',
        'API documentation',
        'Technical specifications',
        'Code snippets and examples'
      ],
      whenNotToUse: [
        'Regular text documents',
        'When semantic meaning is more important'
      ]
    },
    'custom': {
      name: 'Custom Separator',
      strategy: 'custom',
      size: 1000,
      overlap: 200,
      separator: '---',
      icon: '⚙️',
      description: 'Use a custom separator string to define chunk boundaries.',
      detailedAdvice: 'Split text at your custom separator. Useful for documents with known structure markers. Specify your separator string (e.g., "---", "CHAPTER", "##").',
      example: 'Separator: "---"\n\nContent: "Section 1---Section 2---Section 3"\n\nResult: 3 chunks split at "---" markers.',
      whenToUse: [
        'Documents with custom section markers',
        'Structured data with known delimiters',
        'When you know the document structure',
        'Processing specialized formats'
      ],
      whenNotToUse: [
        'General documents',
        'When structure is unknown',
        'First-time use (try semantic first)'
      ]
    }
  };

  const resetForm = () => {
    setFormData({
      name: '',
      purpose: '',
      tags: '',
      document_type: '',
      content: '',
      custom_metadata: '',
      chunk_size: 1000,
      chunk_overlap: 200,
      chunking_strategy: 'semantic',
      separator: '\n\n',
      max_chunks: null,
    });
    setSelectedFile(null);
    setUploadMethod(0);
    setAdvancedMode(false);
    setSelectedPreset('semantic');
    setShowChunkPreview(false);
  };

  const applyPreset = (presetKey) => {
    const preset = chunkPresets[presetKey];
    setSelectedPreset(presetKey);
    setFormData({
      ...formData,
      chunking_strategy: preset.strategy,
      chunk_size: preset.size || 1000,
      chunk_overlap: preset.overlap || 200,
      separator: preset.separator !== null ? preset.separator : '\n\n',
    });
    // Auto-show preview when strategy changes
    if (formData.content && formData.content.trim() && !showChunkPreview) {
      setShowChunkPreview(true);
    }
  };

  const handleFileChange = (event) => {
    const file = event.target.files[0];
    handleFileSelection(file);
  };

  // Validation constants (match backend)
  const MAX_FILE_SIZE = 100 * 1024 * 1024; // 100MB
  const MIN_CHUNK_SIZE = 10;
  const MAX_CHUNK_SIZE = 50000;
  const SUPPORTED_FILE_TYPES = ['.pdf', '.docx', '.doc', '.txt', '.text', '.json'];

  // Pre-upload validation
  const validateFile = (file) => {
    if (!file) {
      return { valid: false, error: 'No file selected' };
    }

    // Check file size
    if (file.size > MAX_FILE_SIZE) {
      return {
        valid: false,
        error: `File size (${(file.size / 1024 / 1024).toFixed(2)}MB) exceeds maximum allowed size (${MAX_FILE_SIZE / 1024 / 1024}MB)`
      };
    }

    if (file.size === 0) {
      return { valid: false, error: 'File is empty' };
    }

    // Check file extension
    const extension = file.name.toLowerCase().substring(file.name.lastIndexOf('.'));
    if (!SUPPORTED_FILE_TYPES.includes(extension)) {
      return {
        valid: false,
        error: `Unsupported file type: ${extension}. Supported: ${SUPPORTED_FILE_TYPES.join(', ')}`
      };
    }

    return { valid: true };
  };

  const validateChunkingParameters = () => {
    const chunkSize = formData.chunk_size || 1000;
    const chunkOverlap = formData.chunk_overlap || 200;
    const strategy = formData.chunking_strategy || 'semantic';

    if (chunkSize < MIN_CHUNK_SIZE) {
      return {
        valid: false,
        error: `Chunk size (${chunkSize}) is too small (minimum ${MIN_CHUNK_SIZE} characters)`
      };
    }

    if (chunkSize > MAX_CHUNK_SIZE) {
      return {
        valid: false,
        error: `Chunk size (${chunkSize}) is too large (maximum ${MAX_CHUNK_SIZE} characters)`
      };
    }

    if (chunkOverlap < 0) {
      return { valid: false, error: 'Chunk overlap cannot be negative' };
    }

    if (chunkOverlap >= chunkSize) {
      return {
        valid: false,
        error: `Chunk overlap (${chunkOverlap}) must be less than chunk size (${chunkSize})`
      };
    }

    if (formData.max_chunks !== null && formData.max_chunks <= 0) {
      return { valid: false, error: 'max_chunks must be a positive integer' };
    }

    return { valid: true };
  };

  const validateContent = (content) => {
    if (!content || !content.trim()) {
      return { valid: false, error: 'Content is empty or missing' };
    }

    if (content.trim().length < 1) {
      return { valid: false, error: 'Content contains no meaningful text' };
    }

    return { valid: true };
  };

  const handleFileSelection = (file) => {
    if (!file) return;
    
    // Validate file before setting
    const validation = validateFile(file);
    if (!validation.valid) {
      notify.error(validation.error);
      return;
    }
    
    setSelectedFile(file);
    
    // Auto-fill name from filename, removing extension
    const nameWithoutExt = file.name.replace(/\.[^/.]+$/, '');
    
    // Check if name already exists
    const existingNames = documents.map(d => d.metadata.name);
    let finalName = nameWithoutExt;
    
    if (existingNames.includes(finalName)) {
      // Add timestamp to make unique
      const timestamp = new Date().toLocaleString('en-US', { 
        month: 'short', 
        day: 'numeric', 
        hour: '2-digit', 
        minute: '2-digit' 
      });
      finalName = `${nameWithoutExt} (${timestamp})`;
    }
    
    setFormData({ ...formData, name: finalName });
    
    // Show file info
    notify.success(`File selected: ${file.name} (${(file.size / 1024).toFixed(1)}KB)`);
  };

  // Chunking preview function - mimics backend chunking logic
  const previewChunks = React.useMemo(() => {
    const text = formData.content.trim() || '';
    if (!text) return [];

    const strategy = formData.chunking_strategy || 'semantic';
    const chunkSize = formData.chunk_size || 1000;
    const overlap = formData.chunk_overlap || 200;
    const separator = formData.separator || '\n\n';
    const maxChunks = formData.max_chunks || null;

    try {
      // Lines strategy
      if (strategy === 'lines') {
        const lines = text.split('\n').filter(line => line.trim());
        return (maxChunks ? lines.slice(0, maxChunks) : lines).map((line, idx) => ({
          index: idx + 1,
          text: line.trim(),
          length: line.trim().length
        }));
      }

      // Paragraphs strategy
      if (strategy === 'paragraphs') {
        const paragraphs = text.split(separator).filter(p => p.trim());
        let processedChunks = [];
        
        for (const para of paragraphs) {
          const trimmed = para.trim();
          
          // If paragraph exceeds chunk_size, split it by sentences
          if (trimmed.length > chunkSize) {
            const sentencePattern = /([.!?]+)\s+/g;
            const parts = trimmed.split(sentencePattern);
            const sentences = [];
            for (let i = 0; i < parts.length; i += 2) {
              if (parts[i] && parts[i].trim()) {
                sentences.push(parts[i] + (parts[i + 1] || ''));
              }
            }
            
            // Build chunks from sentences, respecting chunk_size
            let currentChunk = [];
            let currentLength = 0;
            
            for (const sentence of sentences) {
              const trimmedSentence = sentence.trim();
              if (!trimmedSentence) continue;
              
              const sentenceLength = trimmedSentence.length;
              
              if (currentLength + sentenceLength + 1 > chunkSize && currentChunk.length > 0) {
                processedChunks.push(currentChunk.join(' '));
                
                if (overlap > 0) {
                  const overlapCount = Math.max(1, Math.floor(currentChunk.length * overlap / chunkSize));
                  currentChunk = currentChunk.slice(-overlapCount);
                  currentChunk.push(trimmedSentence);
                  currentLength = currentChunk.join(' ').length;
                } else {
                  currentChunk = [trimmedSentence];
                  currentLength = sentenceLength;
                }
              } else {
                currentChunk.push(trimmedSentence);
                currentLength += sentenceLength + 1;
              }
              
              if (maxChunks && processedChunks.length >= maxChunks) break;
            }
            
            if (currentChunk.length > 0 && (!maxChunks || processedChunks.length < maxChunks)) {
              processedChunks.push(currentChunk.join(' '));
            }
            
            if (maxChunks && processedChunks.length >= maxChunks) break;
          } else {
            // Paragraph fits within chunk_size, use it as-is
            processedChunks.push(trimmed);
            if (maxChunks && processedChunks.length >= maxChunks) break;
          }
        }
        
        // Apply overlap between paragraph-based chunks (but ensure chunks don't exceed chunk_size)
        if (overlap > 0 && processedChunks.length > 1) {
          const overlapped = [];
          for (let i = 0; i < processedChunks.length; i++) {
            let chunk = processedChunks[i];
            if (i > 0) {
              const prevChunk = processedChunks[i - 1];
              // Calculate how much overlap we can add without exceeding chunk_size
              const maxOverlap = Math.min(overlap, prevChunk.length);
              const overlapText = prevChunk.slice(-maxOverlap);
              const combinedLength = overlapText.length + separator.length + chunk.length;
              
              // If adding overlap would exceed chunk_size, reduce the main chunk content
              if (combinedLength > chunkSize) {
                const availableSpace = chunkSize - overlapText.length - separator.length;
                if (availableSpace > 0) {
                  // Truncate the main chunk to make room for overlap
                  chunk = chunk.slice(0, availableSpace);
                  chunk = overlapText + separator + chunk;
                } else {
                  // If there's no room even after truncation, just use overlap + minimal content
                  chunk = overlapText + separator + (chunk.length > 0 ? chunk.slice(0, Math.max(0, chunkSize - overlapText.length - separator.length)) : '');
                }
              } else {
                chunk = overlapText + separator + chunk;
              }
            }
            overlapped.push(chunk);
          }
          processedChunks = overlapped;
        }
        
        const result = (maxChunks ? processedChunks.slice(0, maxChunks) : processedChunks).map((chunk, idx) => ({
          index: idx + 1,
          text: chunk.trim(),
          length: chunk.trim().length
        }));
        return result;
      }

      // Sentences strategy
      if (strategy === 'sentences') {
        const sentencePattern = /([.!?]+)\s+/g;
        const parts = text.split(sentencePattern);
        const sentences = [];
        for (let i = 0; i < parts.length; i += 2) {
          if (parts[i] && parts[i].trim()) {
            sentences.push(parts[i] + (parts[i + 1] || ''));
          }
        }

        const chunks = [];
        let currentChunk = [];
        let currentLength = 0;

        for (const sentence of sentences) {
          const trimmed = sentence.trim();
          if (!trimmed) continue;
          
          const sentenceLength = trimmed.length;
          
          if (currentLength + sentenceLength + 1 > chunkSize && currentChunk.length > 0) {
            chunks.push(currentChunk.join(' '));
            
            if (overlap > 0) {
              const overlapCount = Math.max(1, Math.floor(currentChunk.length * overlap / chunkSize));
              currentChunk = currentChunk.slice(-overlapCount);
              currentChunk.push(trimmed);
              currentLength = currentChunk.join(' ').length;
              
              // Ensure overlap + new sentence doesn't exceed chunk_size (if it does, start fresh)
              if (currentLength > chunkSize) {
                currentChunk = [trimmed];
                currentLength = sentenceLength;
              }
            } else {
              currentChunk = [trimmed];
              currentLength = sentenceLength;
            }
          } else {
            currentChunk.push(trimmed);
            currentLength += sentenceLength + 1;
          }
          
          if (maxChunks && chunks.length >= maxChunks) break;
        }

        if (currentChunk.length > 0 && (!maxChunks || chunks.length < maxChunks)) {
          chunks.push(currentChunk.join(' '));
        }

        return chunks.map((chunk, idx) => ({
          index: idx + 1,
          text: chunk,
          length: chunk.length
        }));
      }

      // Size strategy
      if (strategy === 'size') {
        const words = text.split(/\s+/);
        const chunks = [];
        let currentChunk = [];
        let currentLength = 0;

        for (const word of words) {
          const wordWithSpace = word + ' ';
          const wordLength = wordWithSpace.length;

          if (currentLength + wordLength > chunkSize && currentChunk.length > 0) {
            chunks.push(currentChunk.join(' '));
            
            if (overlap > 0) {
              const overlapWords = Math.max(1, Math.floor(currentChunk.length * overlap / chunkSize));
              currentChunk = currentChunk.slice(-overlapWords);
              currentChunk.push(word);
              currentLength = currentChunk.join(' ').length;
              
              // Ensure overlap + new word doesn't exceed chunk_size (if it does, start fresh)
              if (currentLength > chunkSize) {
                currentChunk = [word];
                currentLength = word.length;
              }
            } else {
              currentChunk = [word];
              currentLength = word.length;
            }
          } else {
            currentChunk.push(word);
            currentLength += wordLength;
          }
          
          if (maxChunks && chunks.length >= maxChunks) break;
        }

        if (currentChunk.length > 0 && (!maxChunks || chunks.length < maxChunks)) {
          chunks.push(currentChunk.join(' '));
        }

        return chunks.map((chunk, idx) => ({
          index: idx + 1,
          text: chunk,
          length: chunk.length
        }));
      }

      // Custom separator strategy
      if (strategy === 'custom') {
        const chunks = text.split(separator).filter(c => c.trim()).map(c => c.trim());
        let result = chunks;
        
        // If chunks exceed chunk_size, split them further
        if (chunkSize) {
          const sizedChunks = [];
          for (const chunk of chunks) {
            if (chunk.length > chunkSize) {
              // Split large chunks by sentences or words
              const words = chunk.split(/\s+/);
              let currentChunk = [];
              let currentLength = 0;
              
              for (const word of words) {
                const wordWithSpace = word + ' ';
                const wordLength = wordWithSpace.length;
                
                if (currentLength + wordLength > chunkSize && currentChunk.length > 0) {
                  sizedChunks.push(currentChunk.join(' '));
                  
                  if (overlap > 0) {
                    const overlapWords = Math.max(1, Math.floor(currentChunk.length * overlap / chunkSize));
                    currentChunk = currentChunk.slice(-overlapWords);
                    currentChunk.push(word);
                    currentLength = currentChunk.join(' ').length;
                  } else {
                    currentChunk = [word];
                    currentLength = word.length;
                  }
                } else {
                  currentChunk.push(word);
                  currentLength += wordLength;
                }
                
                if (maxChunks && sizedChunks.length >= maxChunks) break;
              }
              
              if (currentChunk.length > 0 && (!maxChunks || sizedChunks.length < maxChunks)) {
                sizedChunks.push(currentChunk.join(' '));
              }
              
              if (maxChunks && sizedChunks.length >= maxChunks) break;
            } else {
              sizedChunks.push(chunk);
              if (maxChunks && sizedChunks.length >= maxChunks) break;
            }
          }
          result = sizedChunks;
        }
        
        // Apply overlap (but ensure chunks don't exceed chunk_size)
        if (overlap > 0 && result.length > 1 && chunkSize) {
          const overlapped = [];
          for (let i = 0; i < result.length; i++) {
            let chunk = result[i];
            if (i > 0) {
              const prevChunk = result[i - 1];
              const maxOverlap = Math.min(overlap, prevChunk.length);
              const overlapText = prevChunk.slice(-maxOverlap);
              const combinedLength = overlapText.length + separator.length + chunk.length;
              
              if (combinedLength > chunkSize) {
                const availableSpace = chunkSize - overlapText.length - separator.length;
                if (availableSpace > 0) {
                  chunk = chunk.slice(0, availableSpace);
                  chunk = overlapText + separator + chunk;
                } else {
                  chunk = overlapText + separator + (chunk.length > 0 ? chunk.slice(0, Math.max(0, chunkSize - overlapText.length - separator.length)) : '');
                }
              } else {
                chunk = overlapText + separator + chunk;
              }
            }
            overlapped.push(chunk);
          }
          result = overlapped;
        } else if (overlap > 0 && result.length > 1 && !chunkSize) {
          // If no chunk_size specified, just add overlap as-is
          const overlapped = [];
          for (let i = 0; i < result.length; i++) {
            let chunk = result[i];
            if (i > 0) {
              const prevChunk = result[i - 1];
              const overlapText = prevChunk.slice(-Math.min(overlap, prevChunk.length));
              chunk = overlapText + separator + chunk;
            }
            overlapped.push(chunk);
          }
          result = overlapped;
        }
        
        return (maxChunks ? result.slice(0, maxChunks) : result).map((chunk, idx) => ({
          index: idx + 1,
          text: chunk,
          length: chunk.length
        }));
      }

      // Semantic strategy (simplified approximation)
      if (strategy === 'semantic') {
        const paragraphs = text.split(/\n\s*\n/);
        const chunks = [];
        let currentChunk = [];
        let currentLength = 0;

        for (const para of paragraphs) {
          const sentences = para.match(/[^.!?]+[.!?]+/g) || [para];
          
          for (const sentence of sentences) {
            const trimmed = sentence.trim();
            if (!trimmed) continue;
            
            const sentenceLength = trimmed.length;
            
            if (currentLength + sentenceLength + 1 > chunkSize && currentChunk.length > 0) {
              chunks.push(currentChunk.join(' '));
              
              if (overlap > 0) {
                // Calculate overlap: keep last N sentences based on overlap size
                const overlapCount = Math.max(1, Math.floor(currentChunk.length * overlap / chunkSize));
                currentChunk = currentChunk.slice(-overlapCount);
                currentChunk.push(trimmed);
                currentLength = currentChunk.join(' ').length;
                
                // Ensure overlap + new sentence doesn't exceed chunk_size (if it does, start fresh)
                if (currentLength > chunkSize) {
                  currentChunk = [trimmed];
                  currentLength = sentenceLength;
                }
              } else {
                currentChunk = [trimmed];
                currentLength = sentenceLength;
              }
            } else {
              currentChunk.push(trimmed);
              currentLength += sentenceLength + 1;
            }
            
            if (maxChunks && chunks.length >= maxChunks) break;
          }
          
          if (maxChunks && chunks.length >= maxChunks) break;
        }

        if (currentChunk.length > 0 && (!maxChunks || chunks.length < maxChunks)) {
          chunks.push(currentChunk.join(' '));
        }

        return chunks.map((chunk, idx) => ({
          index: idx + 1,
          text: chunk,
          length: chunk.length
        }));
      }

      return [{
        index: 1,
        text: text,
        length: text.length
      }];
    } catch (error) {
      console.error('Error previewing chunks:', error);
      return [{
        index: 1,
        text: text,
        length: text.length
      }];
    }
  }, [formData.content, formData.chunking_strategy, formData.chunk_size, formData.chunk_overlap, formData.separator, formData.max_chunks]);

  const handleCreateDocument = async () => {
    // Pre-submit validation
    if (!formData.name || !formData.name.trim()) {
      notify.error('Document name is required');
      return;
    }

    // Validate chunking parameters
    const chunkValidation = validateChunkingParameters();
    if (!chunkValidation.valid) {
      notify.error(chunkValidation.error);
      return;
    }

    // Validate content (for text upload)
    if (uploadMethod === 0) {
      const contentValidation = validateContent(formData.content);
      if (!contentValidation.valid) {
        notify.error(contentValidation.error);
        return;
      }
    }

    // Validate file (for file upload)
    if (uploadMethod === 1) {
      if (!selectedFile) {
        notify.error('Please select a file to upload');
        return;
      }
      const fileValidation = validateFile(selectedFile);
      if (!fileValidation.valid) {
        notify.error(fileValidation.error);
        return;
      }
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
        if (formData.document_type) {
          formDataToSend.append('document_type', formData.document_type);
        }
        formDataToSend.append('chunk_size', formData.chunk_size.toString());
        formDataToSend.append('chunk_overlap', formData.chunk_overlap.toString());
        formDataToSend.append('chunking_strategy', formData.chunking_strategy || 'semantic');
        if (formData.separator) {
          formDataToSend.append('chunk_separator', formData.separator);
        }
        if (formData.max_chunks) {
          formDataToSend.append('max_chunks', formData.max_chunks.toString());
        }
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
            document_type: formData.document_type || null,
            custom_metadata: formData.custom_metadata ? JSON.parse(formData.custom_metadata) : {},
          },
          content: formData.content,
          chunk_size: formData.chunk_size,
          chunk_overlap: formData.chunk_overlap,
          chunking_strategy: formData.chunking_strategy || 'semantic',
          chunk_separator: formData.separator || null,
          max_chunks: formData.max_chunks || null,
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
            message: response.message || 'Processing...',
            progress: 0,
          },
        }));
        notify.success('Document upload started! Processing in background...');
      }

      // Close dialog immediately and reset form - don't wait for processing
      setCreateDialogOpen(false);
      setExpandedAdvice(null);
      resetForm();
      setSubmitting(false);
      
      // Don't fetch documents here - let the polling mechanism handle it when task completes
      // This prevents UI blocking
    } catch (err) {
      notify.error('Failed to create document: ' + (err.response?.data?.detail || err.message));
      console.error('Error creating document:', err);
      setSubmitting(false);
    }
  };

  const handleViewChunks = async (document) => {
    try {
      setLoadingChunks(true);
      setSelectedDocument(document);
      setChunksDialogOpen(true);
      
      const chunksData = await documentsAPI.getChunks(collectionName, document.id);
      setSelectedDocumentChunks(chunksData);
    } catch (err) {
      notify.error('Failed to load chunks: ' + (err.response?.data?.detail || err.message));
      console.error('Error loading chunks:', err);
    } finally {
      setLoadingChunks(false);
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
          document_type: formData.document_type || null,
          custom_metadata: formData.custom_metadata ? JSON.parse(formData.custom_metadata) : {},
        },
        chunk_size: formData.chunk_size,
        chunk_overlap: formData.chunk_overlap,
        chunking_strategy: formData.chunking_strategy || 'semantic',
        chunk_separator: formData.separator || null,
        max_chunks: formData.max_chunks || null,
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
      setExpandedAdvice(null);
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
    const existingStrategy = document.metadata.chunking_strategy || 'semantic';
    setFormData({
      name: document.metadata.name || '',
      purpose: document.metadata.purpose || '',
      tags: document.metadata.tags || '',
      document_type: document.metadata.document_type || '',
      content: document.content || '',
      custom_metadata: JSON.stringify(
        document.metadata.custom_metadata || {},
        null,
        2
      ),
      chunk_size: document.metadata.chunk_size || 1000,
      chunk_overlap: document.metadata.chunk_overlap || 200,
      chunking_strategy: existingStrategy,
      separator: document.metadata.chunk_separator || '\n\n',
      max_chunks: document.metadata.max_chunks || null,
    });
    setSelectedPreset(existingStrategy === 'semantic' ? 'semantic' : 
                     existingStrategy === 'size' ? 'size' :
                     existingStrategy === 'lines' ? 'lines' :
                     existingStrategy === 'paragraphs' ? 'paragraphs' :
                     existingStrategy === 'sentences' ? 'sentences' :
                     existingStrategy === 'custom' ? 'custom' : 'semantic');
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
                        {doc.metadata.chunking_strategy && (
                          <>
                            Strategy: {doc.metadata.chunking_strategy}
                            <br />
                          </>
                        )}
                        {doc.metadata.chunking_strategy !== 'lines' && (
                          <>
                            Size: {doc.metadata.chunk_size != null ? Number(doc.metadata.chunk_size) : 'N/A'}, 
                            Overlap: {doc.metadata.chunk_overlap != null ? Number(doc.metadata.chunk_overlap) : 'N/A'}
                          </>
                        )}
                        {doc.metadata.chunking_strategy === 'lines' && (
                          <>One chunk per line</>
                        )}
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
                      <Tooltip title="View Chunks">
                        <IconButton
                          size="small"
                          color="info"
                          onClick={() => handleViewChunks(doc)}
                        >
                          <PreviewIcon />
                        </IconButton>
                      </Tooltip>
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
                          <Grid container spacing={2}>
                            <Grid item xs={12} md={6}>
                              <Typography variant="subtitle2" gutterBottom>
                                📋 Metadata
                              </Typography>
                              <Stack spacing={1} sx={{ mb: 2 }}>
                                {doc.metadata.document_type && (
                                  <Box>
                                    <Typography variant="caption" color="text.secondary">Document Type:</Typography>
                                    <Chip label={doc.metadata.document_type} size="small" sx={{ ml: 1 }} />
                                  </Box>
                                )}
                                {doc.metadata.author && doc.metadata.author !== 'unknown' && (
                                  <Box>
                                    <Typography variant="caption" color="text.secondary">Author:</Typography>
                                    <Typography variant="body2" component="span" sx={{ ml: 1 }}>{doc.metadata.author}</Typography>
                                  </Box>
                                )}
                                {doc.metadata.source && (
                                  <Box>
                                    <Typography variant="caption" color="text.secondary">Source:</Typography>
                                    <Chip label={doc.metadata.source} size="small" variant="outlined" sx={{ ml: 1 }} />
                                  </Box>
                                )}
                                {doc.metadata.chunking_strategy && (
                                  <Box>
                                    <Typography variant="caption" color="text.secondary">Chunking Strategy:</Typography>
                                    <Chip label={doc.metadata.chunking_strategy} size="small" color="primary" variant="outlined" sx={{ ml: 1 }} />
                                  </Box>
                                )}
                                {doc.metadata.created_at && (
                                  <Box>
                                    <Typography variant="caption" color="text.secondary">Created:</Typography>
                                    <Typography variant="body2" component="span" sx={{ ml: 1 }}>
                                      {new Date(doc.metadata.created_at).toLocaleString()}
                                    </Typography>
                                  </Box>
                                )}
                                {doc.metadata.content_length && (
                                  <Box>
                                    <Typography variant="caption" color="text.secondary">Content Length:</Typography>
                                    <Typography variant="body2" component="span" sx={{ ml: 1 }}>
                                      {doc.metadata.content_length.toLocaleString()} chars, {doc.metadata.word_count?.toLocaleString() || Math.floor(doc.metadata.content_length / 5)} words
                                    </Typography>
                                  </Box>
                                )}
                                {doc.metadata.embedding_model && (
                                  <Box>
                                    <Typography variant="caption" color="text.secondary">Embedding Model:</Typography>
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: 0.5 }}>
                                      <Chip 
                                        label={doc.metadata.embedding_model} 
                                        size="small" 
                                        sx={{ 
                                          fontSize: '0.7rem',
                                          height: '22px',
                                          bgcolor: 'info.light',
                                          color: 'info.contrastText'
                                        }} 
                                      />
                                      {doc.metadata.embedding_dimension && (
                                        <Typography variant="caption" color="text.secondary">
                                          ({doc.metadata.embedding_dimension}D)
                                        </Typography>
                                      )}
                                    </Box>
                                  </Box>
                                )}
                              </Stack>
                            </Grid>
                            <Grid item xs={12} md={6}>
                              <Typography variant="subtitle2" gutterBottom>
                                📄 Content Preview:
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
                            </Grid>
                          </Grid>
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
                onFileSelect={handleFileSelection}
                disabled={submitting}
              />
              {selectedFile && (
                <Alert severity="success" sx={{ mt: 2 }}>
                  <Typography variant="body2">
                    <strong>Selected:</strong> {selectedFile.name} ({(selectedFile.size / 1024).toFixed(2)} KB)
                  </Typography>
                  <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
                    Document name: {formData.name}
                  </Typography>
                </Alert>
              )}
            </Box>
          )}

          <Box sx={{ mb: 2 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
              <Typography variant="subtitle2">
                Chunking Strategy
              </Typography>
              <Button
                size="small"
                onClick={() => setAdvancedMode(!advancedMode)}
                sx={{ textTransform: 'none' }}
              >
                {advancedMode ? '← Basic' : 'Advanced →'}
              </Button>
            </Box>

            {!advancedMode ? (
              // BASIC MODE - Smart Presets with Interactive Advice
              <>
                <Grid container spacing={2} sx={{ mb: 2 }}>
                  {Object.entries(chunkPresets).map(([key, preset]) => (
                    <Grid item xs={12} sm={6} md={4} key={key}>
                      <Card
                        sx={{
                          cursor: 'pointer',
                          border: selectedPreset === key ? 2 : 1,
                          borderColor: selectedPreset === key ? 'primary.main' : 'divider',
                          bgcolor: selectedPreset === key ? 'primary.50' : 'background.paper',
                          transition: 'all 0.2s',
                          height: '100%',
                          display: 'flex',
                          flexDirection: 'column',
                          '&:hover': {
                            borderColor: 'primary.main',
                            transform: 'translateY(-2px)',
                            boxShadow: 2,
                          },
                        }}
                        onClick={() => applyPreset(key)}
                      >
                        <CardContent sx={{ p: 2, '&:last-child': { pb: 2 }, flexGrow: 1, display: 'flex', flexDirection: 'column' }}>
                          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
                            <Box sx={{ display: 'flex', alignItems: 'center' }}>
                              <Typography variant="h6" sx={{ mr: 1 }}>
                                {preset.icon}
                              </Typography>
                              <Typography variant="subtitle2" fontWeight="bold">
                                {preset.name}
                              </Typography>
                            </Box>
                            <IconButton
                              size="small"
                              onClick={(e) => {
                                e.stopPropagation();
                                setExpandedAdvice(expandedAdvice === key ? null : key);
                              }}
                              sx={{ ml: 1 }}
                            >
                              <HelpOutlineIcon fontSize="small" />
                            </IconButton>
                          </Box>
                          <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1, flexGrow: 1 }}>
                            {preset.description}
                          </Typography>
                          <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
                            {preset.size && (
                              <Chip
                                label={`${preset.size} chars`}
                                size="small"
                                variant="outlined"
                              />
                            )}
                            {preset.overlap !== null && preset.overlap !== undefined && (
                              <Chip
                                label={`${preset.overlap} overlap`}
                                size="small"
                                variant="outlined"
                              />
                            )}
                          </Box>
                        </CardContent>
                        <Collapse in={expandedAdvice === key}>
                          <Box sx={{ p: 2, bgcolor: 'grey.50', borderTop: 1, borderColor: 'divider' }}>
                            <Typography variant="caption" fontWeight="bold" display="block" gutterBottom>
                              📚 Detailed Information:
                            </Typography>
                            <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1, whiteSpace: 'pre-line' }}>
                              {preset.detailedAdvice}
                            </Typography>
                            <Typography variant="caption" fontWeight="bold" display="block" gutterBottom sx={{ mt: 1 }}>
                              ✅ When to Use:
                            </Typography>
                            <Typography variant="caption" component="ul" sx={{ m: 0, pl: 2, mb: 1 }}>
                              {preset.whenToUse.map((item, idx) => (
                                <li key={idx}>{item}</li>
                              ))}
                            </Typography>
                            <Typography variant="caption" fontWeight="bold" display="block" gutterBottom>
                              ❌ When NOT to Use:
                            </Typography>
                            <Typography variant="caption" component="ul" sx={{ m: 0, pl: 2 }}>
                              {preset.whenNotToUse.map((item, idx) => (
                                <li key={idx}>{item}</li>
                              ))}
                            </Typography>
                            <Typography variant="caption" fontWeight="bold" display="block" gutterBottom sx={{ mt: 1 }}>
                              💡 Example:
                            </Typography>
                            <Typography variant="caption" color="text.secondary" display="block" sx={{ whiteSpace: 'pre-line', fontFamily: 'monospace', bgcolor: 'background.paper', p: 1, borderRadius: 0.5 }}>
                              {preset.example}
                            </Typography>
                          </Box>
                        </Collapse>
                      </Card>
                    </Grid>
                  ))}
                </Grid>

                {selectedPreset && chunkPresets[selectedPreset] && (
                  <Alert severity="success" icon={<InfoIcon />} sx={{ mb: 2 }}>
                    <Typography variant="body2" fontWeight="bold" gutterBottom>
                      Selected: {chunkPresets[selectedPreset].name}
                    </Typography>
                    <Typography variant="caption" component="div">
                      {chunkPresets[selectedPreset].description}
                      {chunkPresets[selectedPreset].detailedAdvice && (
                        <>
                          <br /><br />
                          <strong>Tip:</strong> Click the <HelpOutlineIcon sx={{ fontSize: 14, verticalAlign: 'middle', mx: 0.5 }} /> icon on any strategy card for detailed information, examples, and when to use it.
                        </>
                      )}
                    </Typography>
                  </Alert>
                )}
              </>
            ) : (
              // ADVANCED MODE - Full Control
              <>
                <Alert severity="warning" sx={{ mb: 2 }}>
                  <Typography variant="caption">
                    <strong>⚙️ Advanced Mode:</strong> Full control over chunking parameters. Use this when presets don't meet your needs.
                  </Typography>
                </Alert>

                <FormControl fullWidth sx={{ mb: 2 }}>
                  <InputLabel>Chunking Strategy *</InputLabel>
                  <Select
                    value={formData.chunking_strategy}
                    label="Chunking Strategy *"
                    onChange={(e) => {
                      const strategy = e.target.value;
                      const updates = { chunking_strategy: strategy };
                      
                      // Auto-set separator based on strategy
                      if (strategy === 'paragraphs') {
                        updates.separator = '\n\n';
                      } else if (strategy === 'lines') {
                        updates.separator = '\n';
                      } else if (strategy === 'custom' && !formData.separator) {
                        updates.separator = '---';
                      }
                      
                      setFormData({ ...formData, ...updates });
                      
                      // Auto-show preview when strategy changes if content exists
                      if (formData.content && formData.content.trim() && !showChunkPreview) {
                        setShowChunkPreview(true);
                      }
                    }}
                    disabled={submitting}
                  >
                    <MenuItem value="semantic">
                      <Box>
                        <Typography variant="body2" fontWeight="bold">🧠 Semantic (Recommended)</Typography>
                        <Typography variant="caption" color="text.secondary">Smart chunking with context preservation</Typography>
                      </Box>
                    </MenuItem>
                    <MenuItem value="size">
                      <Box>
                        <Typography variant="body2" fontWeight="bold">📏 Fixed Size</Typography>
                        <Typography variant="caption" color="text.secondary">Character-based with word boundaries</Typography>
                      </Box>
                    </MenuItem>
                    <MenuItem value="sentences">
                      <Box>
                        <Typography variant="body2" fontWeight="bold">💬 By Sentences</Typography>
                        <Typography variant="caption" color="text.secondary">Respects sentence boundaries</Typography>
                      </Box>
                    </MenuItem>
                    <MenuItem value="paragraphs">
                      <Box>
                        <Typography variant="body2" fontWeight="bold">📑 By Paragraphs</Typography>
                        <Typography variant="caption" color="text.secondary">Uses paragraph separators</Typography>
                      </Box>
                    </MenuItem>
                    <MenuItem value="lines">
                      <Box>
                        <Typography variant="body2" fontWeight="bold">📝 By Lines</Typography>
                        <Typography variant="caption" color="text.secondary">One line per chunk</Typography>
                      </Box>
                    </MenuItem>
                    <MenuItem value="custom">
                      <Box>
                        <Typography variant="body2" fontWeight="bold">⚙️ Custom Separator</Typography>
                        <Typography variant="caption" color="text.secondary">Split by custom separator string</Typography>
                      </Box>
                    </MenuItem>
                  </Select>
                  <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5 }}>
                    Choose the chunking strategy. See Basic mode for detailed information about each strategy.
                  </Typography>
                </FormControl>

                <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 2, mb: 2 }}>
                  <TextField
                    label="Chunk Size"
                    value={formData.chunk_size}
                    onChange={(e) => {
                      const value = e.target.value;
                      if (value === '') {
                        setFormData({ ...formData, chunk_size: '' });
                      } else {
                        const parsed = parseInt(value);
                        if (!isNaN(parsed) && parsed > 0) {
                          setFormData({ ...formData, chunk_size: parsed });
                        }
                      }
                    }}
                    onBlur={() => {
                      if (formData.chunk_size === '') {
                        setFormData({ ...formData, chunk_size: 1000 });
                      }
                    }}
                    disabled={submitting || formData.chunking_strategy === 'lines'}
                    helperText={formData.chunking_strategy === 'lines' ? 'Not used for line-based chunking' : 'Characters per chunk (100-5000 recommended)'}
                    inputProps={{ inputMode: 'numeric', min: 1, max: 10000 }}
                  />
                  <TextField
                    label="Chunk Overlap"
                    value={formData.chunk_overlap}
                    onChange={(e) => {
                      const value = e.target.value;
                      if (value === '') {
                        setFormData({ ...formData, chunk_overlap: '' });
                      } else {
                        const parsed = parseInt(value);
                        if (!isNaN(parsed) && parsed >= 0) {
                          setFormData({ ...formData, chunk_overlap: parsed });
                        }
                      }
                    }}
                    onBlur={() => {
                      if (formData.chunk_overlap === '') {
                        setFormData({ ...formData, chunk_overlap: 200 });
                      }
                    }}
                    disabled={submitting || formData.chunking_strategy === 'lines'}
                    helperText={formData.chunking_strategy === 'lines' ? 'Not used for line-based chunking' : 'Overlap between chunks (typically 10-20% of chunk size)'}
                    inputProps={{ inputMode: 'numeric', min: 0 }}
                  />
                </Box>

                {(formData.chunking_strategy === 'paragraphs' || formData.chunking_strategy === 'custom') && (
                  <TextField
                    fullWidth
                    label="Separator"
                    value={formData.separator}
                    onChange={(e) => setFormData({ ...formData, separator: e.target.value })}
                    disabled={submitting}
                    helperText={
                      formData.chunking_strategy === 'paragraphs' 
                        ? 'Paragraph separator (default: \\n\\n for double newline)'
                        : 'Custom separator string (e.g., "---", "CHAPTER", "##"). Text will be split at this separator.'
                    }
                    required={formData.chunking_strategy === 'custom'}
                    sx={{ mb: 2 }}
                  />
                )}

                <TextField
                  fullWidth
                  label="Max Chunks (optional)"
                  type="number"
                  value={formData.max_chunks || ''}
                  onChange={(e) => {
                    const value = e.target.value;
                    if (value === '') {
                      setFormData({ ...formData, max_chunks: null });
                    } else {
                      const parsed = parseInt(value);
                      if (!isNaN(parsed) && parsed > 0) {
                        setFormData({ ...formData, max_chunks: parsed });
                      }
                    }
                  }}
                  disabled={submitting}
                  helperText="Limit total number of chunks (leave empty for no limit). Useful for testing or when you want to process only a portion of a document."
                  inputProps={{ inputMode: 'numeric', min: 1 }}
                  sx={{ mb: 2 }}
                />

                <Alert severity="info" sx={{ mt: 2 }}>
                  <Typography variant="caption">
                    <strong>💡 Pro Tip:</strong> Each strategy has specific use cases. Switch to Basic mode to see interactive advice, examples, and recommendations for each strategy.
                  </Typography>
                </Alert>
              </>
            )}
          </Box>

          {/* Chunk Preview Section */}
          {uploadMethod === 0 && formData.content.trim() && (
            <Box sx={{ mb: 2 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                <Typography variant="subtitle2" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <PreviewIcon fontSize="small" />
                  Chunk Preview
                </Typography>
                <Button
                  size="small"
                  onClick={() => setShowChunkPreview(!showChunkPreview)}
                  startIcon={showChunkPreview ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                  sx={{ textTransform: 'none' }}
                >
                  {showChunkPreview ? 'Hide Preview' : 'Show Preview'}
                </Button>
              </Box>
              <Collapse in={showChunkPreview}>
                <Card variant="outlined" sx={{ bgcolor: 'grey.50' }}>
                  <CardContent>
                    {previewChunks.length > 0 ? (
                      <>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2, flexWrap: 'wrap', gap: 1 }}>
                          <Typography variant="body2" fontWeight="medium">
                            Preview: {previewChunks.length} chunk{previewChunks.length !== 1 ? 's' : ''} will be created
                          </Typography>
                          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                            <Chip
                              label={`Strategy: ${formData.chunking_strategy || 'semantic'}`}
                              size="small"
                              color="primary"
                              variant="outlined"
                            />
                            {formData.chunk_size && formData.chunking_strategy !== 'lines' && (
                              <Chip
                                label={`Size: ${formData.chunk_size} chars`}
                                size="small"
                                variant="outlined"
                              />
                            )}
                            {formData.chunk_overlap !== null && formData.chunk_overlap !== undefined && formData.chunking_strategy !== 'lines' && (
                              <Chip
                                label={`Overlap: ${formData.chunk_overlap} chars`}
                                size="small"
                                variant="outlined"
                              />
                            )}
                          </Box>
                        </Box>
                        <Box sx={{ maxHeight: 400, overflow: 'auto' }}>
                          {previewChunks.slice(0, 10).map((chunk, idx) => (
                            <Card
                              key={idx}
                              variant="outlined"
                              sx={{
                                mb: 1.5,
                                bgcolor: 'background.paper',
                                '&:hover': {
                                  boxShadow: 2,
                                },
                              }}
                            >
                              <CardContent sx={{ p: 2 }}>
                                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                                  <Chip
                                    label={`Chunk ${chunk.index}`}
                                    size="small"
                                    color="primary"
                                    sx={{ fontWeight: 'bold' }}
                                  />
                                  <Typography variant="caption" color="text.secondary">
                                    {chunk.length} characters
                                  </Typography>
                                </Box>
                                <Typography
                                  variant="body2"
                                  sx={{
                                    whiteSpace: 'pre-wrap',
                                    wordBreak: 'break-word',
                                    fontFamily: 'monospace',
                                    fontSize: '0.875rem',
                                    lineHeight: 1.6,
                                    maxHeight: 150,
                                    overflow: 'auto',
                                    bgcolor: 'grey.50',
                                    p: 1.5,
                                    borderRadius: 1,
                                    border: '1px solid',
                                    borderColor: 'divider',
                                  }}
                                >
                                  {chunk.text.length > 500 ? `${chunk.text.substring(0, 500)}...` : chunk.text}
                                </Typography>
                              </CardContent>
                            </Card>
                          ))}
                          {previewChunks.length > 10 && (
                            <Alert severity="info" sx={{ mt: 1 }}>
                              <Typography variant="caption">
                                Showing first 10 of {previewChunks.length} chunks. All chunks will be processed when you create the document.
                              </Typography>
                            </Alert>
                          )}
                        </Box>
                        <Alert severity="info" sx={{ mt: 2 }}>
                          <Typography variant="caption">
                            <strong>Note:</strong> This preview shows how your document will be split into chunks based on your selected strategy. 
                            Each chunk will be converted to an embedding vector for similarity search. Adjust chunk size, overlap, or strategy to change the chunking behavior.
                          </Typography>
                        </Alert>
                      </>
                    ) : (
                      <Alert severity="warning">
                        <Typography variant="body2">
                          No chunks to preview. Please add content to see how it will be chunked.
                        </Typography>
                      </Alert>
                    )}
                  </CardContent>
                </Card>
              </Collapse>
            </Box>
          )}

          {/* Show preview hint for file uploads */}
          {uploadMethod === 1 && (
            <Alert severity="info" sx={{ mb: 2 }}>
              <Typography variant="caption">
                <strong>Tip:</strong> After uploading your file, you can preview the chunks by editing the document. 
                The chunk preview will show how your document will be split based on the selected strategy.
              </Typography>
            </Alert>
          )}

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
          <Button onClick={() => { setCreateDialogOpen(false); setExpandedAdvice(null); setShowChunkPreview(false); resetForm(); }} disabled={submitting}>
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
          <FormControl fullWidth sx={{ mb: 2 }}>
            <InputLabel>Document Type (optional)</InputLabel>
            <Select
              value={formData.document_type}
              label="Document Type (optional)"
              onChange={(e) => setFormData({ ...formData, document_type: e.target.value })}
              disabled={submitting}
            >
              <MenuItem value="">Auto-detect (default)</MenuItem>
              <MenuItem value="book">📚 Book</MenuItem>
              <MenuItem value="definition">📖 Definition/Glossary</MenuItem>
              <MenuItem value="article">📄 Article</MenuItem>
              <MenuItem value="blog_post">📝 Blog Post</MenuItem>
              <MenuItem value="poem">✍️ Poem</MenuItem>
              <MenuItem value="unknown">❓ Unknown/Other</MenuItem>
            </Select>
            <FormHelperText>
              Specify document type to help with chunking optimization. If not specified, the system will auto-detect.
            </FormHelperText>
          </FormControl>
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
          <Box sx={{ mb: 2 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
              <Typography variant="subtitle2">
                Chunking Strategy
              </Typography>
              <Button
                size="small"
                onClick={() => setAdvancedMode(!advancedMode)}
                sx={{ textTransform: 'none' }}
              >
                {advancedMode ? '← Basic' : 'Advanced →'}
              </Button>
            </Box>

            {!advancedMode ? (
              // BASIC MODE - Smart Presets (Edit Dialog - Compact View)
              <>
                <Grid container spacing={1.5} sx={{ mb: 2 }}>
                  {Object.entries(chunkPresets).map(([key, preset]) => (
                    <Grid item xs={12} sm={6} key={key}>
                      <Card
                        sx={{
                          cursor: 'pointer',
                          border: selectedPreset === key ? 2 : 1,
                          borderColor: selectedPreset === key ? 'primary.main' : 'divider',
                          bgcolor: selectedPreset === key ? 'primary.50' : 'background.paper',
                          transition: 'all 0.2s',
                          '&:hover': {
                            borderColor: 'primary.main',
                            transform: 'translateY(-1px)',
                          },
                        }}
                        onClick={() => applyPreset(key)}
                      >
                        <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 } }}>
                          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5 }}>
                            <Box sx={{ display: 'flex', alignItems: 'center' }}>
                              <Typography variant="body2" sx={{ mr: 0.5 }}>
                                {preset.icon}
                              </Typography>
                              <Typography variant="caption" fontWeight="bold">
                                {preset.name}
                              </Typography>
                            </Box>
                            <IconButton
                              size="small"
                              onClick={(e) => {
                                e.stopPropagation();
                                setExpandedAdvice(expandedAdvice === key ? null : key);
                              }}
                              sx={{ ml: 1, p: 0.5 }}
                            >
                              <HelpOutlineIcon fontSize="small" />
                            </IconButton>
                          </Box>
                          <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
                            {preset.description}
                          </Typography>
                          <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
                            {preset.size && (
                              <Chip
                                label={`${preset.size} chars`}
                                size="small"
                                variant="outlined"
                              />
                            )}
                            {preset.overlap !== null && preset.overlap !== undefined && (
                              <Chip
                                label={`${preset.overlap} overlap`}
                                size="small"
                                variant="outlined"
                              />
                            )}
                          </Box>
                        </CardContent>
                        <Collapse in={expandedAdvice === key}>
                          <Box sx={{ p: 1.5, bgcolor: 'grey.50', borderTop: 1, borderColor: 'divider' }}>
                            <Typography variant="caption" fontWeight="bold" display="block" gutterBottom>
                              📚 {preset.detailedAdvice}
                            </Typography>
                            <Typography variant="caption" fontWeight="bold" display="block" gutterBottom sx={{ mt: 1 }}>
                              ✅ When to Use:
                            </Typography>
                            <Typography variant="caption" component="ul" sx={{ m: 0, pl: 2, mb: 1 }}>
                              {preset.whenToUse.slice(0, 3).map((item, idx) => (
                                <li key={idx}>{item}</li>
                              ))}
                            </Typography>
                          </Box>
                        </Collapse>
                      </Card>
                    </Grid>
                  ))}
                </Grid>
                {selectedPreset && chunkPresets[selectedPreset] && (
                  <Alert severity="success" icon={<InfoIcon />} sx={{ mb: 2 }}>
                    <Typography variant="caption">
                      <strong>Selected:</strong> {chunkPresets[selectedPreset].name} - {chunkPresets[selectedPreset].description}
                    </Typography>
                  </Alert>
                )}
              </>
            ) : (
              // ADVANCED MODE - Full Control (Same as create dialog)
              <>
                <Alert severity="warning" sx={{ mb: 2 }}>
                  <Typography variant="caption">
                    <strong>⚙️ Advanced Mode:</strong> Full control over chunking parameters.
                  </Typography>
                </Alert>

                <FormControl fullWidth sx={{ mb: 2 }}>
                  <InputLabel>Chunking Strategy *</InputLabel>
                  <Select
                    value={formData.chunking_strategy}
                    label="Chunking Strategy *"
                    onChange={(e) => {
                      const strategy = e.target.value;
                      const updates = { chunking_strategy: strategy };
                      
                      // Auto-set separator based on strategy
                      if (strategy === 'paragraphs') {
                        updates.separator = '\n\n';
                      } else if (strategy === 'lines') {
                        updates.separator = '\n';
                      } else if (strategy === 'custom' && !formData.separator) {
                        updates.separator = '---';
                      }
                      
                      setFormData({ ...formData, ...updates });
                      
                      // Auto-show preview when strategy changes if content exists
                      if (formData.content && formData.content.trim() && !showChunkPreview) {
                        setShowChunkPreview(true);
                      }
                    }}
                    disabled={submitting}
                  >
                    <MenuItem value="semantic">🧠 Semantic (Recommended)</MenuItem>
                    <MenuItem value="size">📏 Fixed Size</MenuItem>
                    <MenuItem value="sentences">💬 By Sentences</MenuItem>
                    <MenuItem value="paragraphs">📑 By Paragraphs</MenuItem>
                    <MenuItem value="lines">📝 By Lines</MenuItem>
                    <MenuItem value="custom">⚙️ Custom Separator</MenuItem>
                  </Select>
                </FormControl>

                <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 2, mb: 2 }}>
                  <TextField
                    size="small"
                    label="Chunk Size"
                    value={formData.chunk_size}
                    onChange={(e) => {
                      const value = e.target.value;
                      if (value === '') {
                        setFormData({ ...formData, chunk_size: '' });
                      } else {
                        const parsed = parseInt(value);
                        if (!isNaN(parsed) && parsed > 0) {
                          setFormData({ ...formData, chunk_size: parsed });
                        }
                      }
                    }}
                    disabled={submitting || formData.chunking_strategy === 'lines'}
                    helperText={formData.chunking_strategy === 'lines' ? 'Not used' : 'Characters per chunk'}
                    inputProps={{ inputMode: 'numeric' }}
                  />
                  <TextField
                    size="small"
                    label="Chunk Overlap"
                    value={formData.chunk_overlap}
                    onChange={(e) => {
                      const value = e.target.value;
                      if (value === '') {
                        setFormData({ ...formData, chunk_overlap: '' });
                      } else {
                        const parsed = parseInt(value);
                        if (!isNaN(parsed) && parsed >= 0) {
                          setFormData({ ...formData, chunk_overlap: parsed });
                        }
                      }
                    }}
                    disabled={submitting || formData.chunking_strategy === 'lines'}
                    helperText={formData.chunking_strategy === 'lines' ? 'Not used' : 'Overlap between chunks'}
                    inputProps={{ inputMode: 'numeric' }}
                  />
                </Box>

                {(formData.chunking_strategy === 'paragraphs' || formData.chunking_strategy === 'custom') && (
                  <TextField
                    fullWidth
                    size="small"
                    label="Separator"
                    value={formData.separator}
                    onChange={(e) => setFormData({ ...formData, separator: e.target.value })}
                    disabled={submitting}
                    helperText={formData.chunking_strategy === 'custom' ? 'Custom separator string' : 'Paragraph separator'}
                    sx={{ mb: 2 }}
                  />
                )}

                <TextField
                  fullWidth
                  size="small"
                  label="Max Chunks (optional)"
                  type="number"
                  value={formData.max_chunks || ''}
                  onChange={(e) => {
                    const value = e.target.value;
                    if (value === '') {
                      setFormData({ ...formData, max_chunks: null });
                    } else {
                      const parsed = parseInt(value);
                      if (!isNaN(parsed) && parsed > 0) {
                        setFormData({ ...formData, max_chunks: parsed });
                      }
                    }
                  }}
                  disabled={submitting}
                  helperText="Limit total number of chunks"
                  sx={{ mb: 2 }}
                />
              </>
            )}
          </Box>

          {/* Chunk Preview Section for Edit Dialog */}
          {formData.content && formData.content.trim() && (
            <Box sx={{ mb: 2 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                <Typography variant="subtitle2" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <PreviewIcon fontSize="small" />
                  Chunk Preview
                </Typography>
                <Button
                  size="small"
                  onClick={() => setShowChunkPreview(!showChunkPreview)}
                  startIcon={showChunkPreview ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                  sx={{ textTransform: 'none' }}
                >
                  {showChunkPreview ? 'Hide Preview' : 'Show Preview'}
                </Button>
              </Box>
              <Collapse in={showChunkPreview}>
                <Card variant="outlined" sx={{ bgcolor: 'grey.50' }}>
                  <CardContent>
                    {previewChunks.length > 0 ? (
                      <>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2, flexWrap: 'wrap', gap: 1 }}>
                          <Typography variant="body2" fontWeight="medium">
                            Preview: {previewChunks.length} chunk{previewChunks.length !== 1 ? 's' : ''} will be created
                          </Typography>
                          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                            <Chip
                              label={`Strategy: ${formData.chunking_strategy || 'semantic'}`}
                              size="small"
                              color="primary"
                              variant="outlined"
                            />
                            {formData.chunk_size && formData.chunking_strategy !== 'lines' && (
                              <Chip
                                label={`Size: ${formData.chunk_size} chars`}
                                size="small"
                                variant="outlined"
                              />
                            )}
                            {formData.chunk_overlap !== null && formData.chunk_overlap !== undefined && formData.chunking_strategy !== 'lines' && (
                              <Chip
                                label={`Overlap: ${formData.chunk_overlap} chars`}
                                size="small"
                                variant="outlined"
                              />
                            )}
                          </Box>
                        </Box>
                        <Box sx={{ maxHeight: 400, overflow: 'auto' }}>
                          {previewChunks.slice(0, 10).map((chunk, idx) => (
                            <Card
                              key={idx}
                              variant="outlined"
                              sx={{
                                mb: 1.5,
                                bgcolor: 'background.paper',
                                '&:hover': {
                                  boxShadow: 2,
                                },
                              }}
                            >
                              <CardContent sx={{ p: 2 }}>
                                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                                  <Chip
                                    label={`Chunk ${chunk.index}`}
                                    size="small"
                                    color={
                                      formData.chunking_strategy !== 'lines' && chunk.length > (formData.chunk_size || 1000)
                                        ? 'error'
                                        : formData.chunking_strategy !== 'lines' && chunk.length < (formData.chunk_size || 1000) * 0.5 && chunk.index < previewChunks.length
                                        ? 'warning'
                                        : 'primary'
                                    }
                                    sx={{ fontWeight: 'bold' }}
                                  />
                                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                    <Typography 
                                      variant="caption" 
                                      color={
                                        formData.chunking_strategy !== 'lines' && chunk.length > (formData.chunk_size || 1000)
                                          ? 'error'
                                          : 'text.secondary'
                                      }
                                      fontWeight={
                                        formData.chunking_strategy !== 'lines' && chunk.length > (formData.chunk_size || 1000)
                                          ? 'bold'
                                          : 'normal'
                                      }
                                    >
                                      {chunk.length} characters
                                    </Typography>
                                    {formData.chunking_strategy !== 'lines' && formData.chunk_size && (
                                      <Typography variant="caption" color="text.secondary">
                                        / {formData.chunk_size} max
                                      </Typography>
                                    )}
                                  </Box>
                                </Box>
                                {formData.chunking_strategy !== 'lines' && chunk.length > (formData.chunk_size || 1000) && (
                                  <Alert severity="error" sx={{ mb: 1 }}>
                                    <Typography variant="caption">
                                      ⚠️ This chunk exceeds the maximum size of {formData.chunk_size} characters. This should not happen - please report this issue.
                                    </Typography>
                                  </Alert>
                                )}
                                <Typography
                                  variant="body2"
                                  sx={{
                                    whiteSpace: 'pre-wrap',
                                    wordBreak: 'break-word',
                                    fontFamily: 'monospace',
                                    fontSize: '0.875rem',
                                    lineHeight: 1.6,
                                    maxHeight: 150,
                                    overflow: 'auto',
                                    bgcolor: 'grey.50',
                                    p: 1.5,
                                    borderRadius: 1,
                                    border: '1px solid',
                                    borderColor: 'divider',
                                  }}
                                >
                                  {chunk.text.length > 500 ? `${chunk.text.substring(0, 500)}...` : chunk.text}
                                </Typography>
                              </CardContent>
                            </Card>
                          ))}
                          {previewChunks.length > 10 && (
                            <Alert severity="info" sx={{ mt: 1 }}>
                              <Typography variant="caption">
                                Showing first 10 of {previewChunks.length} chunks. All chunks will be processed when you update the document.
                              </Typography>
                            </Alert>
                          )}
                        </Box>
                        <Alert severity="info" sx={{ mt: 2 }}>
                          <Typography variant="caption">
                            <strong>Note:</strong> This preview shows how your document will be split into chunks based on your selected strategy. 
                            Updating the document will regenerate all embeddings with the new chunking strategy.
                          </Typography>
                        </Alert>
                      </>
                    ) : (
                      <Alert severity="warning">
                        <Typography variant="body2">
                          No chunks to preview. Please add content to see how it will be chunked.
                        </Typography>
                      </Alert>
                    )}
                  </CardContent>
                </Card>
              </Collapse>
            </Box>
          )}

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
          <Button onClick={() => { setEditDialogOpen(false); setSelectedDocument(null); setExpandedAdvice(null); setShowChunkPreview(false); resetForm(); }} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={handleEditDocument} variant="contained" disabled={submitting}>
            {submitting ? <CircularProgress size={24} /> : 'Update'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Chunks Dialog */}
      <Dialog
        open={chunksDialogOpen}
        onClose={() => setChunksDialogOpen(false)}
        maxWidth="lg"
        fullWidth
      >
        <DialogTitle>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography variant="h6">
              Chunks & Metadata
              {selectedDocument && ` - ${selectedDocument.metadata.name || selectedDocument.metadata.title || selectedDocument.metadata.document_name || 'Document'}`}
            </Typography>
            {selectedDocumentChunks && (
              <Chip 
                label={`${selectedDocumentChunks.total || selectedDocumentChunks.chunks?.length || 0} chunks`} 
                color="primary" 
                variant="outlined"
              />
            )}
          </Box>
        </DialogTitle>
        <DialogContent>
          {loadingChunks ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
              <CircularProgress />
            </Box>
          ) : selectedDocumentChunks && selectedDocumentChunks.chunks.length > 0 ? (
            <Box sx={{ mt: 2 }}>
              {selectedDocumentChunks.chunks.map((chunk, idx) => (
                <Card key={chunk.id} variant="outlined" sx={{ mb: 2 }}>
                  <CardContent>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 2 }}>
                      <Typography variant="h6" component="div">
                        Chunk {chunk.chunk_number}
                        {chunk.chunk_position && ` (${chunk.chunk_position})`}
                      </Typography>
                      <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                        {chunk.content_type && (
                          <Chip 
                            label={chunk.content_type} 
                            size="small" 
                            color="info" 
                            variant="outlined"
                          />
                        )}
                        {chunk.difficulty_level && (
                          <Chip 
                            label={chunk.difficulty_level} 
                            size="small" 
                            color={
                              chunk.difficulty_level === 'Beginner' ? 'success' :
                              chunk.difficulty_level === 'Advanced' ? 'error' : 'default'
                            }
                            variant="outlined"
                          />
                        )}
                        <Chip 
                          label={`${chunk.length} chars`} 
                          size="small" 
                          variant="outlined"
                        />
                      </Box>
                    </Box>
                    
                    {chunk.section_title && (
                      <Typography variant="subtitle2" color="primary" gutterBottom>
                        📑 {chunk.section_title}
                      </Typography>
                    )}
                    
                    {chunk.topics && chunk.topics !== 'general' && (
                      <Box sx={{ mb: 2 }}>
                        <Typography variant="caption" color="text.secondary">Topics: </Typography>
                        {chunk.topics.split(', ').map((topic, i) => (
                          <Chip 
                            key={i}
                            label={topic.trim()} 
                            size="small" 
                            sx={{ mr: 0.5, mb: 0.5 }}
                          />
                        ))}
                      </Box>
                    )}
                    
                    <Typography
                      variant="body2"
                      sx={{
                        whiteSpace: 'pre-wrap',
                        p: 2,
                        bgcolor: 'grey.50',
                        borderRadius: 1,
                        maxHeight: 300,
                        overflow: 'auto',
                      }}
                    >
                      {chunk.content}
                    </Typography>
                    
                    <Box sx={{ mt: 2, pt: 2, borderTop: '1px solid', borderColor: 'divider' }}>
                      <Grid container spacing={1}>
                        <Grid item xs={6} sm={3}>
                          <Typography variant="caption" color="text.secondary">Words:</Typography>
                          <Typography variant="body2">{chunk.word_count}</Typography>
                        </Grid>
                        <Grid item xs={6} sm={3}>
                          <Typography variant="caption" color="text.secondary">Characters:</Typography>
                          <Typography variant="body2">{chunk.length}</Typography>
                        </Grid>
                        {chunk.metadata.page_number && (
                          <Grid item xs={6} sm={3}>
                            <Typography variant="caption" color="text.secondary">Page:</Typography>
                            <Typography variant="body2">{chunk.metadata.page_number}</Typography>
                          </Grid>
                        )}
                      </Grid>
                    </Box>
                  </CardContent>
                </Card>
              ))}
            </Box>
          ) : (
            <Alert severity="info" sx={{ mt: 2 }}>
              No chunks found for this document.
            </Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setChunksDialogOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default DocumentList;
