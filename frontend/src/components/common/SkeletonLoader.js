import React from 'react';
import { Box, Card, CardContent, Skeleton, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Paper } from '@mui/material';

export const CollectionCardSkeleton = () => (
  <Card>
    <CardContent>
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
        <Skeleton variant="circular" width={40} height={40} sx={{ mr: 1 }} />
        <Skeleton variant="text" width="60%" height={32} />
      </Box>
      <Skeleton variant="text" width="80%" />
      <Skeleton variant="text" width="40%" sx={{ mt: 1 }} />
      <Box sx={{ mt: 2 }}>
        <Skeleton variant="rectangular" width={100} height={24} />
      </Box>
    </CardContent>
  </Card>
);

export const DocumentTableSkeleton = () => (
  <TableContainer component={Paper} sx={{ borderRadius: 2 }}>
    <Table>
      <TableHead>
        <TableRow sx={{ bgcolor: 'grey.50' }}>
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
        {[...Array(5)].map((_, index) => (
          <TableRow key={index}>
            <TableCell>
              <Skeleton variant="circular" width={24} height={24} />
            </TableCell>
            <TableCell>
              <Skeleton variant="text" width="80%" />
              <Skeleton variant="text" width="50%" />
            </TableCell>
            <TableCell>
              <Skeleton variant="text" width="70%" />
            </TableCell>
            <TableCell>
              <Skeleton variant="text" width="60%" />
            </TableCell>
            <TableCell>
              <Skeleton variant="rectangular" width={80} height={24} />
            </TableCell>
            <TableCell>
              <Skeleton variant="text" width="90%" />
            </TableCell>
            <TableCell>
              <Box sx={{ display: 'flex', gap: 1, justifyContent: 'flex-end' }}>
                <Skeleton variant="circular" width={32} height={32} />
                <Skeleton variant="circular" width={32} height={32} />
              </Box>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  </TableContainer>
);

export const SidebarSkeleton = () => (
  <Box sx={{ p: 2 }}>
    {[...Array(5)].map((_, index) => (
      <Box key={index} sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
        <Skeleton variant="circular" width={24} height={24} sx={{ mr: 2 }} />
        <Skeleton variant="text" width="70%" />
      </Box>
    ))}
  </Box>
);

