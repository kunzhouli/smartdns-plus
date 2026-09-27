'use client';

import * as React from 'react';
import {
  Alert, Box, Button, Card, CardContent, Checkbox, FormControl, FormControlLabel,
  IconButton, InputLabel, ListItemText, MenuItem, OutlinedInput, Select, Stack,
  Switch, TextField, Typography,
} from '@mui/material';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import { useTranslation } from 'react-i18next';
import { type ManagedUpstreamServer, type UpstreamConfig, smartdnsServer } from '@/lib/backend/server';
import { useUser } from '@/hooks/use-user';

const emptyConfig: UpstreamConfig = { groups: [], default_group: '', servers: [] };

export function UpstreamManagement(): React.JSX.Element {
  const { t } = useTranslation();
  const { checkSessionError } = useUser();
  const [config, setConfig] = React.useState<UpstreamConfig>(emptyConfig);
  const [saved, setSaved] = React.useState<UpstreamConfig | null>(null);
  const [newGroup, setNewGroup] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState('');
  const [message, setMessage] = React.useState('');

  React.useEffect(() => {
    void smartdnsServer.GetUpstreamConfig().then(async (result) => {
      if (result.data) { setConfig(result.data); setSaved(result.data); }
      if (result.error) {
        await checkSessionError?.(result.error);
        setError(smartdnsServer.getErrorMessage(result.error));
      }
    });
  }, [checkSessionError]);

  const updateServer = (index: number, patch: Partial<ManagedUpstreamServer>): void => {
    setConfig((previous) => ({
      ...previous,
      servers: previous.servers.map((server, row) => row === index ? { ...server, ...patch } : server),
    }));
  };

  const renameGroup = (index: number, name: string): void => {
    setConfig((previous) => {
      const oldName = previous.groups[index];
      return {
        ...previous,
        groups: previous.groups.map((group, row) => row === index ? name : group),
        default_group: previous.default_group === oldName ? name : previous.default_group,
        servers: previous.servers.map((server) => ({
          ...server,
          groups: server.groups.map((group) => group === oldName ? name : group),
        })),
      };
    });
  };

  const removeGroup = (index: number): void => {
    if (config.groups[index] === config.default_group) {
      setError(t('Select another default DNS group before removing this group.'));
      return;
    }
    setConfig((previous) => {
      const name = previous.groups[index];
      return {
        ...previous,
        groups: previous.groups.filter((_, row) => row !== index),
        servers: previous.servers.map((server) => ({
          ...server,
          groups: server.groups.filter((group) => group !== name),
        })),
      };
    });
  };

  const addGroup = (): void => {
    const name = newGroup.trim();
    if (!name || config.groups.includes(name)) {
      setError(t('Enter a unique server group name.'));
      return;
    }
    setConfig((previous) => ({ ...previous, groups: [...previous.groups, name] }));
    setNewGroup('');
    setError('');
  };

  const addServer = (): void => {
    setConfig((previous) => ({
      ...previous,
      servers: [...previous.servers, {
        endpoint: '', groups: [], exclude_default: false, enabled: true, host_ip: '',
      }],
    }));
  };

  const settings = (value: UpstreamConfig): string => JSON.stringify({
    groups: value.groups, default_group: value.default_group, servers: value.servers,
  });
  const hasUnsavedChanges = saved === null || settings(config) !== settings(saved);

  const save = async (): Promise<void> => {
    setBusy(true);
    setError('');
    setMessage('');
    const result = await smartdnsServer.SaveUpstreamConfig(config);
    if (result.error) {
      await checkSessionError?.(result.error);
      setError(smartdnsServer.getErrorMessage(result.error));
    } else if (result.data) {
      setConfig(result.data);
      setSaved(result.data);
      setMessage(t('Upstream settings saved. SmartDNS is restarting.'));
    }
    setBusy(false);
  };

  return <Card>
    <CardContent>
      <Stack spacing={2}>
        <Typography variant="h5">{t('Manage upstream servers')}</Typography>
        <Typography variant="body2" color="textSecondary">
          {t('Add DNS servers here, then assign them to groups for GeoSite and nameserver rules. Existing servers in hand-written configuration remain unchanged.')}
        </Typography>
        {error ? <Alert severity="error">{error}</Alert> : null}
        {message ? <Alert severity="success">{message}</Alert> : null}

        <Typography variant="h6">{t('Server groups')}</Typography>
        {config.groups.map((group, index) => <Stack key={index} direction="row" spacing={1} alignItems="center">
          <TextField size="small" label={t('Group name')} value={group} onChange={(event) => renameGroup(index, event.target.value)} sx={{ minWidth: 220 }} />
          <IconButton aria-label={t('Remove group')} onClick={() => removeGroup(index)}><DeleteOutlineIcon /></IconButton>
        </Stack>)}
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
          <TextField size="small" label={t('New group name')} value={newGroup} onChange={(event) => setNewGroup(event.target.value)} sx={{ minWidth: 220 }} />
          <Button variant="outlined" onClick={addGroup}>{t('Add group')}</Button>
        </Stack>

        <FormControl sx={{ maxWidth: 400 }} size="small">
          <InputLabel id="default-dns-group-label">{t('Default DNS group')}</InputLabel>
          <Select labelId="default-dns-group-label" label={t('Default DNS group')}
            value={config.default_group}
            onChange={(event) => setConfig((previous) => ({ ...previous, default_group: event.target.value }))}>
            <MenuItem value="">{t('Use per-server default settings')}</MenuItem>
            {config.groups.map((group) => <MenuItem key={group} value={group}>{group}</MenuItem>)}
          </Select>
        </FormControl>
        <Typography variant="body2" color="textSecondary">
          {t('Queries without a matching routing rule use enabled servers in the selected group. Other managed servers are excluded from the default group.')}
        </Typography>

        <Typography variant="h6">{t('Managed DNS servers')}</Typography>
        {config.servers.map((server, index) => <Card key={index} variant="outlined">
          <CardContent>
            <Stack spacing={1.5}>
              <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} alignItems={{ md: 'center' }}>
                <TextField fullWidth label={t('DNS server address or URL')} value={server.endpoint}
                  onChange={(event) => updateServer(index, { endpoint: event.target.value })}
                  helperText={t('Examples: 1.1.1.1, tls://dns.google:853, https://dns.google/dns-query')} />
                <TextField label={t('Host IP (optional)')} value={server.host_ip}
                  onChange={(event) => updateServer(index, { host_ip: event.target.value })}
                  helperText={t('Use a bootstrap IP for a hostname-based server.')} sx={{ minWidth: 200 }} />
                <IconButton aria-label={t('Remove DNS server')} onClick={() => setConfig((previous) => ({
                  ...previous, servers: previous.servers.filter((_, row) => row !== index),
                }))}><DeleteOutlineIcon /></IconButton>
              </Stack>
              <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems={{ md: 'center' }}>
                <FormControl sx={{ minWidth: 220 }} size="small">
                  <InputLabel id={`server-groups-${index}`}>{t('Server groups')}</InputLabel>
                  <Select<string[]> multiple labelId={`server-groups-${index}`} value={server.groups}
                    onChange={(event) => updateServer(index, {
                      groups: typeof event.target.value === 'string' ? event.target.value.split(',') : event.target.value,
                    })}
                    input={<OutlinedInput label={t('Server groups')} />}
                    renderValue={(selected) => selected.join(', ')}>
                    {config.groups.map((group) => <MenuItem key={group} value={group}>
                      <Checkbox checked={server.groups.includes(group)} /><ListItemText primary={group} />
                    </MenuItem>)}
                  </Select>
                </FormControl>
                <FormControlLabel control={<Switch checked={server.enabled} onChange={(event) => updateServer(index, { enabled: event.target.checked })} />} label={t('Enabled')} />
                {config.default_group === '' ? <FormControlLabel control={<Switch checked={server.exclude_default} onChange={(event) => updateServer(index, { exclude_default: event.target.checked })} />} label={t('Exclude from default group')} /> : null}
              </Stack>
            </Stack>
          </CardContent>
        </Card>)}
        <Box><Button variant="outlined" onClick={addServer}>{t('Add DNS server')}</Button></Box>
        {config.manual_servers?.length ? <Alert severity="info">
          {t('Servers in smartdns.conf are read-only here:')} {config.manual_servers.join(' ; ')}
        </Alert> : null}
        <Box><Button variant="contained" disabled={busy || !hasUnsavedChanges} onClick={() => void save()}>{t('Save upstream settings')}</Button></Box>
      </Stack>
    </CardContent>
  </Card>;
}
