'use client';

import * as React from 'react';
import { Box, Card, CardContent, Stack, Tab } from '@mui/material';
import { TabContext, TabList, TabPanel } from '@mui/lab';
import { useTranslation } from 'react-i18next';
import { config } from '@/config';
import { GeositeSettings } from '@/components/dashboard/settings/geosite-settings';
import { DomainRoutesSettings } from '@/components/dashboard/rules/domain-routes-settings';

export default function Page(): React.JSX.Element {
  const { t } = useTranslation();
  const [tab, setTab] = React.useState('domains');
  React.useEffect(() => {
    document.title = `${t('Rules')} | ${t('Dashboard')} | ${config.site.name}`;
  }, [t]);

  return <Stack spacing={2}><Card><CardContent><TabContext value={tab}>
    <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
      <TabList onChange={(_, value: string) => setTab(value)}>
        <Tab value="domains" label={t('Domain rules')} />
        <Tab value="geosite" label={t('GeoSite rules')} />
      </TabList>
    </Box>
    <TabPanel value="domains"><DomainRoutesSettings /></TabPanel>
    <TabPanel value="geosite"><GeositeSettings /></TabPanel>
  </TabContext></CardContent></Card></Stack>;
}
