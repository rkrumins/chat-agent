import React, { useState, useEffect } from 'react';
import {
  Box,
  Grid,
  Card,
  CardContent,
  Typography,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Chip,
  CircularProgress,
  Paper,
} from '@mui/material';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts';
import FolderIcon from '@mui/icons-material/Folder';
import DescriptionIcon from '@mui/icons-material/Description';
import DataObjectIcon from '@mui/icons-material/DataObject';
import UploadIcon from '@mui/icons-material/Upload';
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';
import { analyticsAPI } from '../services/api';
import { notify } from '../utils/notifications';

const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884D8', '#82CA9D'];

const Dashboard = () => {
  const [stats, setStats] = useState(null);
  const [activity, setActivity] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchData();
    // Refresh every 30 seconds
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [statsData, activityData] = await Promise.all([
        analyticsAPI.getStats(),
        analyticsAPI.getRecentActivity(10)
      ]);
      setStats(statsData);
      setActivity(activityData.activities || []);
    } catch (err) {
      console.error('Error fetching dashboard data:', err);
      notify.error('Failed to load dashboard data');
    } finally {
      setLoading(false);
    }
  };

  if (loading && !stats) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 400 }}>
        <CircularProgress />
      </Box>
    );
  }

  // Prepare chart data
  const collectionChartData = stats?.collections?.map((col) => ({
    name: col.name,
    documents: col.document_count,
    chunks: col.chunk_count,
  })) || [];

  // Filter out collections with 0 documents for pie chart
  const pieData = stats?.collections
    ?.filter(col => col.document_count > 0)
    .map((col) => ({
      name: col.name,
      value: col.document_count,
    })) || [];

  // Check if we have any data to display
  const hasDocuments = stats?.total_documents > 0;

  const getActivityIcon = (type) => {
    switch (type) {
      case 'upload':
        return <UploadIcon color="primary" />;
      case 'update':
        return <EditIcon color="info" />;
      case 'delete':
        return <DeleteIcon color="error" />;
      default:
        return <DescriptionIcon />;
    }
  };

  const formatTimestamp = (timestamp) => {
    if (!timestamp) return 'Unknown';
    try {
      const date = new Date(timestamp);
      const now = new Date();
      const diffMs = now - date;
      const diffMins = Math.floor(diffMs / 60000);
      const diffHours = Math.floor(diffMs / 3600000);
      const diffDays = Math.floor(diffMs / 86400000);

      if (diffMins < 1) return 'Just now';
      if (diffMins < 60) return `${diffMins}m ago`;
      if (diffHours < 24) return `${diffHours}h ago`;
      return `${diffDays}d ago`;
    } catch {
      return timestamp;
    }
  };

  return (
    <Box>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h4" component="h1" fontWeight="bold">
          Dashboard
        </Typography>
        <Typography variant="body2" color="text.secondary">
          System overview and analytics
        </Typography>
      </Box>

      {/* Stats Cards */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} sm={6} md={4}>
          <Card sx={{ height: '100%' }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                <FolderIcon sx={{ fontSize: 40, color: 'primary.main', mr: 2 }} />
                <Box>
                  <Typography variant="h3" fontWeight="bold">
                    {stats?.total_collections || 0}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Collections
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={4}>
          <Card sx={{ height: '100%' }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                <DescriptionIcon sx={{ fontSize: 40, color: 'success.main', mr: 2 }} />
                <Box>
                  <Typography variant="h3" fontWeight="bold">
                    {stats?.total_documents || 0}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Documents
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={4}>
          <Card sx={{ height: '100%' }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                <DataObjectIcon sx={{ fontSize: 40, color: 'warning.main', mr: 2 }} />
                <Box>
                  <Typography variant="h3" fontWeight="bold">
                    {stats?.total_chunks || 0}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Chunks
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Grid container spacing={3}>
        {/* Collection Distribution Bar Chart */}
        <Grid item xs={12} lg={8}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Collection Distribution
              </Typography>
              {collectionChartData.length > 0 ? (
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={collectionChartData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis 
                      dataKey="name" 
                      angle={-45}
                      textAnchor="end"
                      height={80}
                      interval={0}
                    />
                    <YAxis allowDecimals={false} />
                    <Tooltip 
                      formatter={(value, name) => {
                        if (name === 'Documents') return [`${value} documents`, name];
                        if (name === 'Chunks') return [`${value} chunks`, name];
                        return [value, name];
                      }}
                    />
                    <Legend />
                    <Bar dataKey="documents" fill="#8884d8" name="Documents" />
                    <Bar dataKey="chunks" fill="#82ca9d" name="Chunks" />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <Box sx={{ 
                  textAlign: 'center', 
                  py: 8,
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  height: 300
                }}>
                  <FolderIcon sx={{ fontSize: 60, color: 'text.secondary', mb: 2, opacity: 0.3 }} />
                  <Typography variant="body2" color="text.secondary">
                    No collections yet
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    Create a collection to get started
                  </Typography>
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Document Distribution Pie Chart */}
        <Grid item xs={12} lg={4}>
          <Card sx={{ height: '100%' }}>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Documents by Collection
              </Typography>
              {hasDocuments && pieData.length > 0 ? (
                <ResponsiveContainer width="100%" height={300}>
                  <PieChart>
                    <Pie
                      data={pieData}
                      cx="50%"
                      cy="50%"
                      labelLine={false}
                      label={({ name, percent, value }) => {
                        // Only show label if percentage is significant (>3%)
                        if (percent < 0.03) return '';
                        return `${name}: ${(percent * 100).toFixed(0)}%`;
                      }}
                      outerRadius={80}
                      fill="#8884d8"
                      dataKey="value"
                    >
                      {pieData.map((entry, index) => (
                        <Cell
                          key={`cell-${index}`}
                          fill={COLORS[index % COLORS.length]}
                        />
                      ))}
                    </Pie>
                    <Tooltip 
                      formatter={(value, name) => [`${value} documents`, name]}
                    />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <Box sx={{ 
                  textAlign: 'center', 
                  py: 8,
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  height: 300
                }}>
                  <DescriptionIcon sx={{ fontSize: 60, color: 'text.secondary', mb: 2, opacity: 0.3 }} />
                  <Typography variant="body2" color="text.secondary">
                    No documents yet
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    Upload documents to see distribution
                  </Typography>
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Recent Activity */}
        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Recent Activity
              </Typography>
              {activity.length > 0 ? (
                <List>
                  {activity.map((item, index) => (
                    <ListItem key={index} divider={index < activity.length - 1}>
                      <ListItemIcon>{getActivityIcon(item.type)}</ListItemIcon>
                      <ListItemText
                        primary={item.message}
                        secondary={
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 0.5 }}>
                            {item.collection && (
                              <Chip
                                label={item.collection}
                                size="small"
                                variant="outlined"
                              />
                            )}
                            <Typography variant="caption" color="text.secondary">
                              {formatTimestamp(item.timestamp)}
                            </Typography>
                          </Box>
                        }
                      />
                      <Chip
                        label={item.status}
                        size="small"
                        color={
                          item.status === 'completed'
                            ? 'success'
                            : item.status === 'failed'
                            ? 'error'
                            : 'default'
                        }
                      />
                    </ListItem>
                  ))}
                </List>
              ) : (
                <Box sx={{ textAlign: 'center', py: 4 }}>
                  <Typography variant="body2" color="text.secondary">
                    No recent activity
                  </Typography>
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Collection Details */}
        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Collection Details
              </Typography>
              <Grid container spacing={2}>
                {stats?.collections?.map((collection, index) => (
                  <Grid item xs={12} sm={6} md={4} key={index}>
                    <Paper
                      sx={{
                        p: 2,
                        border: '1px solid',
                        borderColor: 'divider',
                        borderRadius: 2,
                      }}
                    >
                      <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                        <FolderIcon sx={{ mr: 1, color: COLORS[index % COLORS.length] }} />
                        <Typography variant="subtitle1" fontWeight="medium">
                          {collection.name}
                        </Typography>
                      </Box>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                        <Typography variant="body2" color="text.secondary">
                          Documents:
                        </Typography>
                        <Typography variant="body2" fontWeight="medium">
                          {collection.document_count}
                        </Typography>
                      </Box>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                        <Typography variant="body2" color="text.secondary">
                          Chunks:
                        </Typography>
                        <Typography variant="body2" fontWeight="medium">
                          {collection.chunk_count}
                        </Typography>
                      </Box>
                      {collection.metadata?.description && (
                        <Typography
                          variant="caption"
                          color="text.secondary"
                          sx={{ mt: 1, display: 'block' }}
                        >
                          {collection.metadata.description}
                        </Typography>
                      )}
                    </Paper>
                  </Grid>
                ))}
              </Grid>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
};

export default Dashboard;

