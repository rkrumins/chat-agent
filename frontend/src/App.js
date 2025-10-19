import React, { useState } from 'react';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import { CssBaseline, Box } from '@mui/material';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import AppBar from './components/AppBar';
import Sidebar from './components/Sidebar';
import CollectionList from './components/CollectionList';
import DocumentList from './components/DocumentList';
import TaskMonitor from './components/TaskMonitor';

const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#1976d2',
    },
    secondary: {
      main: '#dc004e',
    },
    background: {
      default: '#f5f5f5',
      paper: '#ffffff',
    },
  },
  typography: {
    fontFamily: 'Roboto, Arial, sans-serif',
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: 'none',
          borderRadius: 8,
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 12,
        },
      },
    },
  },
});

function App() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [selectedCollection, setSelectedCollection] = useState(null);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  const handleToggleSidebar = () => {
    setSidebarOpen(!sidebarOpen);
  };

  const handleCollectionSelect = (collection) => {
    setSelectedCollection(collection);
  };

  const handleRefresh = () => {
    setRefreshTrigger(prev => prev + 1);
  };

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Router>
        <Box sx={{ display: 'flex', minHeight: '100vh' }}>
          <AppBar 
            onToggleSidebar={handleToggleSidebar} 
            selectedCollection={selectedCollection}
          />
          <Sidebar 
            open={sidebarOpen} 
            onCollectionSelect={handleCollectionSelect}
            selectedCollection={selectedCollection}
            refreshTrigger={refreshTrigger}
          />
          <Box
            component="main"
            sx={{
              flexGrow: 1,
              p: 3,
              mt: 8,
              ml: sidebarOpen ? '280px' : '0px',
              transition: 'margin-left 0.3s',
              backgroundColor: 'background.default',
              minHeight: 'calc(100vh - 64px)',
            }}
          >
            <Routes>
              <Route path="/" element={<CollectionList onRefresh={handleRefresh} />} />
              <Route 
                path="/collections/:collectionName/documents" 
                element={<DocumentList onRefresh={handleRefresh} />} 
              />
              <Route path="/tasks" element={<TaskMonitor />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Box>
        </Box>
      </Router>
    </ThemeProvider>
  );
}

export default App;

