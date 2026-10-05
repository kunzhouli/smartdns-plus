"use client";

import * as React from 'react';
import Stack from '@mui/material/Stack';

import { UpdatePasswordForm } from '@/components/dashboard/settings/update-password-form';
import { ChangeLang } from '@/components/dashboard/settings/change-lang';
import { TabContext, TabList, TabPanel } from '@mui/lab';
import { Box, Card, CardContent, Tab, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';

const tabs = [
  {
    label: 'Password',
    pannel: <UpdatePasswordForm />,
  },
  {
    label: 'Language',
    pannel: <ChangeLang />,
  },
];

export default function SettingsTab(): React.JSX.Element {
  const { t } = useTranslation();
  const [value, setValue] = React.useState('0');

  const handleChange = (event: React.SyntheticEvent, newValue: string): void => {
    setValue(newValue);
  };

  return (
    <Stack spacing={1}>
      <Card>
        <Typography variant="h4" sx={{ marginTop: -2 }}>
          <TabContext value={value}>
            <CardContent>
              <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
                <TabList onChange={handleChange}>
                  {tabs.map((tab, index) => {
                    return <Tab key={tab.label} label={t(tab.label)} value={index.toString()} />
                  })}
                </TabList>
              </Box>
              {tabs.map((tab, index) => {
                return <TabPanel key={tab.label} value={index.toString()}>{tab.pannel}</TabPanel>
              })}
            </CardContent>
          </TabContext>
        </Typography>
      </Card>
    </Stack>
  );
}
