import React, { useState, useEffect, useCallback } from 'react';
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
  Button,
  ToggleButton,
  ToggleButtonGroup,
  Pagination,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import ErrorIcon from '@mui/icons-material/Error';
import HourglassEmptyIcon from '@mui/icons-material/HourglassEmpty';
import PlayCircleIcon from '@mui/icons-material/PlayCircle';
import CancelIcon from '@mui/icons-material/Cancel';
import WorkIcon from '@mui/icons-material/Work';
import { jobsAPI } from '../services/api';

const JOBS_PER_PAGE = 20;

const TaskMonitor = () => {
  const [jobs, setJobs] = useState([]);
  const [stats, setStats] = useState(null);
  const [workerStatus, setWorkerStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [statusFilter, setStatusFilter] = useState(null);
  const [page, setPage] = useState(1);
  const [totalJobs, setTotalJobs] = useState(0);

  const fetchJobs = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      // Fetch job history with pagination
      const historyData = await jobsAPI.getHistory(
        statusFilter,
        JOBS_PER_PAGE,
        (page - 1) * JOBS_PER_PAGE
      );
      setJobs(historyData.jobs || []);
      setTotalJobs(historyData.total || 0);

      // Fetch stats
      const statsData = await jobsAPI.getStats();
      setStats(statsData);
      setWorkerStatus(statsData.worker_pool);

    } catch (err) {
      setError('Failed to load jobs from vector service');
      console.error('Error fetching jobs:', err);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, page]);

  useEffect(() => {
    fetchJobs();
  }, [fetchJobs]);

  // Auto-refresh every 3 seconds when enabled
  useEffect(() => {
    if (!autoRefresh) return;

    const interval = setInterval(() => {
      fetchJobs();
    }, 3000);

    return () => clearInterval(interval);
  }, [autoRefresh, fetchJobs]);

  const handleCancelJob = async (jobId) => {
    try {
      await jobsAPI.cancelJob(jobId);
      fetchJobs();
    } catch (err) {
      console.error('Failed to cancel job:', err);
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'completed':
        return <CheckCircleIcon color="success" />;
      case 'failed':
        return <ErrorIcon color="error" />;
      case 'processing':
        return <PlayCircleIcon color="primary" />;
      case 'pending':
        return <HourglassEmptyIcon color="action" />;
      case 'cancelled':
        return <CancelIcon color="disabled" />;
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
      cancelled: 'default',
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

  const formatDate = (dateStr) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleString();
  };

  const totalPages = Math.ceil(totalJobs / JOBS_PER_PAGE);

  if (loading && jobs.length === 0) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 400 }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h4" component="h1" fontWeight="bold">
          Job Queue Monitor
        </Typography>
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
          <Button
            variant={autoRefresh ? 'contained' : 'outlined'}
            size="small"
            onClick={() => setAutoRefresh(!autoRefresh)}
          >
            {autoRefresh ? 'Auto-refresh ON' : 'Auto-refresh OFF'}
          </Button>
          <Tooltip title="Refresh now">
            <IconButton onClick={fetchJobs} color="primary">
              <RefreshIcon />
            </IconButton>
          </Tooltip>
        </Box>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}

      {/* Worker Pool Status */}
      {workerStatus && (
        <Alert
          severity={workerStatus.running ? 'success' : 'warning'}
          icon={<WorkIcon />}
          sx={{ mb: 3 }}
        >
          Worker Pool: {workerStatus.active_workers}/{workerStatus.num_workers} workers active
          {workerStatus.pending_jobs > 0 && ` • ${workerStatus.pending_jobs} jobs pending`}
        </Alert>
      )}

      {/* Stats Cards */}
      {stats && (
        <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 2, mb: 3 }}>
          <Card>
            <CardContent sx={{ textAlign: 'center', py: 2 }}>
              <Typography color="text.secondary" variant="body2">Total</Typography>
              <Typography variant="h4" fontWeight="bold">{stats.total}</Typography>
            </CardContent>
          </Card>
          <Card>
            <CardContent sx={{ textAlign: 'center', py: 2 }}>
              <Typography color="text.secondary" variant="body2">Pending</Typography>
              <Typography variant="h4" fontWeight="bold" color="text.secondary">
                {stats.by_status?.pending || 0}
              </Typography>
            </CardContent>
          </Card>
          <Card>
            <CardContent sx={{ textAlign: 'center', py: 2 }}>
              <Typography color="text.secondary" variant="body2">Processing</Typography>
              <Typography variant="h4" fontWeight="bold" color="primary.main">
                {stats.by_status?.processing || 0}
              </Typography>
            </CardContent>
          </Card>
          <Card>
            <CardContent sx={{ textAlign: 'center', py: 2 }}>
              <Typography color="text.secondary" variant="body2">Completed</Typography>
              <Typography variant="h4" fontWeight="bold" color="success.main">
                {stats.by_status?.completed || 0}
              </Typography>
            </CardContent>
          </Card>
          <Card>
            <CardContent sx={{ textAlign: 'center', py: 2 }}>
              <Typography color="text.secondary" variant="body2">Failed</Typography>
              <Typography variant="h4" fontWeight="bold" color="error.main">
                {stats.by_status?.failed || 0}
              </Typography>
            </CardContent>
          </Card>
        </Box>
      )}

      {/* Filter */}
      <Box sx={{ mb: 2 }}>
        <ToggleButtonGroup
          value={statusFilter}
          exclusive
          onChange={(e, val) => { setStatusFilter(val); setPage(1); }}
          size="small"
        >
          <ToggleButton value={null}>All</ToggleButton>
          <ToggleButton value="pending">Pending</ToggleButton>
          <ToggleButton value="processing">Processing</ToggleButton>
          <ToggleButton value="completed">Completed</ToggleButton>
          <ToggleButton value="failed">Failed</ToggleButton>
        </ToggleButtonGroup>
      </Box>

      {/* Jobs Table */}
      {jobs.length === 0 ? (
        <Card sx={{ textAlign: 'center', py: 8 }}>
          <CardContent>
            <HourglassEmptyIcon sx={{ fontSize: 80, color: 'text.secondary', mb: 2 }} />
            <Typography variant="h6" color="text.secondary" gutterBottom>
              No jobs found
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Jobs will appear here when documents are uploaded
            </Typography>
          </CardContent>
        </Card>
      ) : (
        <>
          <TableContainer component={Paper} sx={{ borderRadius: 2 }}>
            <Table size="small">
              <TableHead>
                <TableRow sx={{ bgcolor: 'grey.50' }}>
                  <TableCell width={50}></TableCell>
                  <TableCell><strong>Job ID</strong></TableCell>
                  <TableCell><strong>Collection</strong></TableCell>
                  <TableCell><strong>Status</strong></TableCell>
                  <TableCell><strong>Progress</strong></TableCell>
                  <TableCell><strong>Created</strong></TableCell>
                  <TableCell><strong>Completed</strong></TableCell>
                  <TableCell width={80}></TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {jobs.map((job) => (
                  <TableRow key={job.id} hover>
                    <TableCell>{getStatusIcon(job.status)}</TableCell>
                    <TableCell>
                      <Typography variant="caption" sx={{ fontFamily: 'monospace' }}>
                        {job.id.substring(0, 8)}...
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Chip label={job.collection_name} size="small" variant="outlined" />
                    </TableCell>
                    <TableCell>{getStatusChip(job.status)}</TableCell>
                    <TableCell width={180}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <LinearProgress
                          variant="determinate"
                          value={job.progress_percent || 0}
                          sx={{ flex: 1 }}
                        />
                        <Typography variant="caption" sx={{ minWidth: 35 }}>
                          {Math.round(job.progress_percent || 0)}%
                        </Typography>
                      </Box>
                      <Typography variant="caption" color="text.secondary">
                        {job.processed_count}/{job.total_documents} docs
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="caption" color="text.secondary">
                        {formatDate(job.created_at)}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="caption" color="text.secondary">
                        {formatDate(job.completed_at)}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      {job.status === 'pending' && (
                        <Tooltip title="Cancel Job">
                          <IconButton size="small" onClick={() => handleCancelJob(job.id)}>
                            <CancelIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>

          {/* Pagination */}
          {totalPages > 1 && (
            <Box sx={{ display: 'flex', justifyContent: 'center', mt: 2 }}>
              <Pagination
                count={totalPages}
                page={page}
                onChange={(e, val) => setPage(val)}
                color="primary"
              />
            </Box>
          )}
        </>
      )}

      {autoRefresh && (
        <Alert severity="info" sx={{ mt: 3 }}>
          Auto-refresh enabled. Job list updates every 3 seconds.
        </Alert>
      )}
    </Box>
  );
};

export default TaskMonitor;
