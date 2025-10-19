import React, { useState, useMemo } from 'react';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import { CssBaseline, Box } from '@mui/material';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { SnackbarProvider } from 'notistack';
import AppBar from './components/AppBar';
import Sidebar from './components/Sidebar';
import CollectionList from './components/CollectionList';
import DocumentList from './components/DocumentList';
import TaskMonitor from './components/TaskMonitor';
import Dashboard from './components/Dashboard';
import { useDarkMode } from './hooks/useDarkMode';

const getTheme = (darkMode) => createTheme({
  palette: {
    mode: darkMode ? 'dark' : 'light',
    primary: {
      main: darkMode ? '#90caf9' : '#1976d2',
    },
    secondary: {
      main: darkMode ? '#f48fb1' : '#dc004e',
    },
    background: {
      default: darkMode ? '#121212' : '#f5f5f5',
      paper: darkMode ? '#1e1e1e' : '#ffffff',
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
          transition: 'transform 0.2s ease-in-out, box-shadow 0.2s ease-in-out',
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          transition: 'background-color 0.3s ease',
        },
      },
    },
  },
});

function App() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [selectedCollection, setSelectedCollection] = useState(null);
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [darkMode, toggleDarkMode] = useDarkMode();

  const theme = useMemo(() => getTheme(darkMode), [darkMode]);

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
      <SnackbarProvider 
        maxSnack={3}
        anchorOrigin={{ vertical: 'top', horizontal: 'right' }}
        autoHideDuration={3000}
      >
        <Router>
          <Box sx={{ display: 'flex', minHeight: '100vh' }}>
            <AppBar 
              onToggleSidebar={handleToggleSidebar} 
              selectedCollection={selectedCollection}
              darkMode={darkMode}
              onToggleDarkMode={toggleDarkMode}
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
                transition: 'margin-left 0.3s ease, background-color 0.3s ease',
                backgroundColor: 'background.default',
                minHeight: 'calc(100vh - 64px)',
              }}
            >
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/collections" element={<CollectionList onRefresh={handleRefresh} />} />
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
      </SnackbarProvider>
    </ThemeProvider>
  );
}

export default App;

