"use client";

import * as React from 'react';
import Stack from '@mui/material/Stack';

import { config } from '@/config';
import { UpstreamServersTable } from '@/components/dashboard/upstream-servers/upstream-servers-table';
import { UpstreamManagement } from '@/components/dashboard/upstream-servers/upstream-management';
import { useTranslation } from 'react-i18next';
import Typography from '@mui/material/Typography';

export default function Page(): React.JSX.Element {
  const { t} = useTranslation();

  React.useEffect(() => {
    document.title = `${t('Upstream Servers')} | ${t('Dashboard')} | ${config.site.name}`;
  }, [t]);

  return (
    <Stack spacing={2}>
      <UpstreamManagement />
      <Typography variant="h5">{t('Runtime upstream status')}</Typography>
      <UpstreamServersTable />
    </Stack>
  );
}
