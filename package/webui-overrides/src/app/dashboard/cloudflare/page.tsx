'use client';

import * as React from 'react';
import { Card, CardContent, Stack, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { config } from '@/config';
import { CloudflareSettings } from '@/components/dashboard/settings/cloudflare-settings';

export default function Page(): React.JSX.Element {
  const { t } = useTranslation();

  React.useEffect(() => {
    document.title = `${t('Cloudflare IP Optimization')} | ${t('Dashboard')} | ${config.site.name}`;
  }, [t]);

  return <Stack spacing={2}><Card><CardContent>
    <Typography variant="h5" sx={{ mb: 2 }}>{t('Cloudflare IP Optimization')}</Typography>
    <CloudflareSettings />
  </CardContent></Card></Stack>;
}
