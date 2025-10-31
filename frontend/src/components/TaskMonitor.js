import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  CircularProgress,
  Alert,
  LinearProgress,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  IconButton,
  Tooltip,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import ErrorIcon from '@mui/icons-material/Error';
import HourglassEmptyIcon from '@mui/icons-material/HourglassEmpty';
import { tasksAPI } from '../services/api';

const TaskMonitor = () => {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const fetchTasks = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await tasksAPI.list();
      setTasks(data.tasks || []);
    } catch (err) {
      setError('Failed to load tasks');
      console.error('Error fetching tasks:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTasks();
  }, []);

  // Auto-refresh every 2 seconds
  useEffect(() => {
    if (!autoRefresh) return;

    const interval = setInterval(() => {
      fetchTasks();
    }, 2000);

    return () => clearInterval(interval);
  }, [autoRefresh]);

  const getStatusIcon = (status) => {
    switch (status) {
      case 'completed':
        return <CheckCircleIcon color="success" />;
      case 'failed':
        return <ErrorIcon color="error" />;
      case 'processing':
        return <CircularProgress size={20} />;
      case 'pending':
        return <HourglassEmptyIcon color="action" />;
      default:
        return null;
    }
  };

  const getStatusChip = (status) => {
    const colorMap = {
      completed: 'success',
      failed: 'error',
      processing: 'primary',
      pending: 'default',
    };

    return (
      <Chip
        label={status}
        color={colorMap[status] || 'default'}
        size="small"
        icon={getStatusIcon(status)}
      />
    );
  };

  if (loading && tasks.length === 0) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 400 }}>
        <CircularProgress />
      </Box>
    );
  }

  const pendingTasks = tasks.filter(
    (t) => t.status === 'pending' || t.status === 'processing'
  );
  const completedTasks = tasks.filter((t) => t.status === 'completed');
  const failedTasks = tasks.filter((t) => t.status === 'failed');

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h4" component="h1" fontWeight="bold">
          Task Monitor
        </Typography>
        <Tooltip title="Refresh">
          <IconButton onClick={fetchTasks} color="primary">
            <RefreshIcon />
          </IconButton>
        </Tooltip>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}

      {/* Summary Cards */}
      <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 2, mb: 3 }}>
        <Card>
          <CardContent>
            <Typography color="text.secondary" gutterBottom variant="body2">
              Total Tasks
            </Typography>
            <Typography variant="h4" fontWeight="bold">
              {tasks.length}
            </Typography>
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <Typography color="text.secondary" gutterBottom variant="body2">
              In Progress
            </Typography>
            <Typography variant="h4" fontWeight="bold" color="primary">
              {pendingTasks.length}
            </Typography>
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <Typography color="text.secondary" gutterBottom variant="body2">
              Completed
            </Typography>
            <Typography variant="h4" fontWeight="bold" color="success.main">
              {completedTasks.length}
            </Typography>
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <Typography color="text.secondary" gutterBottom variant="body2">
              Failed
            </Typography>
            <Typography variant="h4" fontWeight="bold" color="error.main">
              {failedTasks.length}
            </Typography>
          </CardContent>
        </Card>
      </Box>

      {tasks.length === 0 ? (
        <Card sx={{ textAlign: 'center', py: 8 }}>
          <CardContent>
            <HourglassEmptyIcon sx={{ fontSize: 80, color: 'text.secondary', mb: 2 }} />
            <Typography variant="h6" color="text.secondary" gutterBottom>
              No tasks yet
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Tasks will appear here when you create or update documents
            </Typography>
          </CardContent>
        </Card>
      ) : (
        <TableContainer component={Paper} sx={{ borderRadius: 2 }}>
          <Table>
            <TableHead>
              <TableRow sx={{ bgcolor: 'grey.50' }}>
                <TableCell width={60}></TableCell>
                <TableCell><strong>Task ID</strong></TableCell>
                <TableCell><strong>Document ID</strong></TableCell>
                <TableCell><strong>Status</strong></TableCell>
                <TableCell><strong>Message</strong></TableCell>
                <TableCell><strong>Progress</strong></TableCell>
                <TableCell><strong>Created</strong></TableCell>
                <TableCell><strong>Updated</strong></TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {tasks
                .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
                .map((task) => (
                  <TableRow key={task.task_id} hover>
                    <TableCell>{getStatusIcon(task.status)}</TableCell>
                    <TableCell>
                      <Typography variant="caption" sx={{ fontFamily: 'monospace' }}>
                        {task.task_id.substring(0, 8)}...
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="caption" sx={{ fontFamily: 'monospace' }}>
                        {task.document_id ? task.document_id.substring(0, 8) + '...' : '-'}
                      </Typography>
                    </TableCell>
                    <TableCell>{getStatusChip(task.status)}</TableCell>
                    <TableCell>
                      <Typography variant="body2">{task.message}</Typography>
                    </TableCell>
                    <TableCell width={150}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <LinearProgress
                          variant="determinate"
                          value={task.progress}
                          sx={{ flex: 1 }}
                        />
                        <Typography variant="caption">{task.progress}%</Typography>
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Typography variant="caption" color="text.secondary">
                        {new Date(task.created_at).toLocaleString()}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="caption" color="text.secondary">
                        {new Date(task.updated_at).toLocaleString()}
                      </Typography>
                    </TableCell>
                  </TableRow>
                ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {autoRefresh && (
        <Alert severity="info" sx={{ mt: 3 }}>
          Auto-refresh enabled. Task list updates every 2 seconds.
        </Alert>
      )}
    </Box>
  );
};

export default TaskMonitor;

