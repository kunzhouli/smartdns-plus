'use client';

import * as React from 'react';
import {
  Alert, Box, Button, Card, CardContent, Checkbox, FormControl, FormControlLabel,
  IconButton, InputLabel, ListItemText, MenuItem, OutlinedInput, Select, Stack,
  Switch, TextField, Typography,
} from '@mui/material';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import AddIcon from '@mui/icons-material/Add';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward';
import { useTranslation } from 'react-i18next';
import { type ManagedUpstreamServer, type UpstreamConfig, smartdnsServer } from '@/lib/backend/server';
import { useUser } from '@/hooks/use-user';

const emptyConfig: UpstreamConfig = { groups: [], default_group: '', bootstrap_dns: {}, group_order: {}, group_parallel: {}, servers: [] };

function orderedMembers(config: UpstreamConfig, group: string): string[] {
  const members = config.servers.filter((server) => server.enabled && server.groups.includes(group)).map((server) => server.endpoint);
  return [...(config.group_order?.[group] ?? []).filter((endpoint) => members.includes(endpoint)),
    ...members.filter((endpoint) => !(config.group_order?.[group] ?? []).includes(endpoint))];
}

function normalizeConfig(config: UpstreamConfig): UpstreamConfig {
  const group_order = Object.fromEntries(config.groups.map((group) => [group, orderedMembers(config, group)]));
  const group_parallel = Object.fromEntries(Object.entries(config.group_parallel ?? {}).filter(([group]) => config.groups.includes(group))
    .map(([group, count]) => [group, Math.max(1, Math.min(count, group_order[group]?.length || 1))]));
  return { ...config, group_order, group_parallel };
}
const groupRowSx = {
  display: 'grid',
  gridTemplateColumns: { xs: 'minmax(0, 1fr)', md: 'minmax(180px, 240px) minmax(240px, 1fr) 160px' },
  alignItems: 'center',
  gap: 1.5,
  px: 2,
  py: 1.5,
};

export function UpstreamManagement(): React.JSX.Element {
  const { t } = useTranslation();
  const { checkSessionError } = useUser();
  const [config, setConfig] = React.useState<UpstreamConfig>(emptyConfig);
  const [saved, setSaved] = React.useState<UpstreamConfig | null>(null);
  const [newGroup, setNewGroup] = React.useState('');
  const [newBootstrap, setNewBootstrap] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState('');
  const [message, setMessage] = React.useState('');

  React.useEffect(() => {
    void smartdnsServer.GetUpstreamConfig().then(async (result) => {
      if (result.data) { const value = normalizeConfig(result.data); setConfig(value); setSaved(value); }
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
        bootstrap_dns: Object.fromEntries(Object.entries(previous.bootstrap_dns ?? {}).map(([group, address]) => [group === oldName ? name : group, address])),
        group_order: Object.fromEntries(Object.entries(previous.group_order ?? {}).map(([group, order]) => [group === oldName ? name : group, order])),
        group_parallel: Object.fromEntries(Object.entries(previous.group_parallel ?? {}).map(([group, count]) => [group === oldName ? name : group, count])),
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
        bootstrap_dns: Object.fromEntries(Object.entries(previous.bootstrap_dns ?? {}).filter(([group]) => group !== name)),
        group_order: Object.fromEntries(Object.entries(previous.group_order ?? {}).filter(([group]) => group !== name)),
        group_parallel: Object.fromEntries(Object.entries(previous.group_parallel ?? {}).filter(([group]) => group !== name)),
        servers: previous.servers.map((server) => ({
          ...server,
          groups: server.groups.filter((group) => group !== name),
        })),
      };
    });
  };

  const addGroup = (): void => {
    const name = newGroup.trim();
    const bootstrap = newBootstrap.trim();
    if (!name || config.groups.includes(name)) {
      setError(t('Enter a unique server group name.'));
      return;
    }
    setConfig((previous) => ({
      ...previous,
      groups: [...previous.groups, name],
      bootstrap_dns: bootstrap ? { ...previous.bootstrap_dns, [name]: bootstrap } : previous.bootstrap_dns,
    }));
    setNewGroup('');
    setNewBootstrap('');
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
    groups: value.groups, default_group: value.default_group, bootstrap_dns: value.bootstrap_dns,
    group_order: value.group_order, group_parallel: value.group_parallel, servers: value.servers,
  });
  const hasUnsavedChanges = saved === null || settings(config) !== settings(saved);

  const save = async (): Promise<void> => {
    setBusy(true);
    setError('');
    setMessage('');
    const result = await smartdnsServer.SaveUpstreamConfig(normalizeConfig(config));
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

        <Box>
          <Typography variant="h6">{t('Server groups')}</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            {t('Set a plain UDP DNS IP for each group to resolve upstream hostnames. Leave it blank to use the existing method. Example: 1.1.1.1 or 1.1.1.1:53.')}
          </Typography>
        </Box>
        <Box sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 2, overflow: 'hidden', maxWidth: 1100 }}>
          {config.groups.map((group, index) => <Box key={index} sx={{ ...groupRowSx, borderBottom: '1px solid', borderColor: 'divider' }}>
            <TextField fullWidth size="small" label={t('Group name')} value={group} onChange={(event) => renameGroup(index, event.target.value)} />
            <TextField fullWidth size="small" label={t('Bootstrap DNS (optional)')} placeholder="1.1.1.1"
              value={config.bootstrap_dns?.[group] ?? ''}
              onChange={(event) => setConfig((previous) => ({ ...previous, bootstrap_dns: { ...previous.bootstrap_dns, [group]: event.target.value } }))} />
            <IconButton aria-label={t('Remove group')} onClick={() => removeGroup(index)}
              sx={{ justifySelf: 'end', color: 'text.secondary', '&:hover': { color: 'error.main' } }}>
              <DeleteOutlineIcon />
            </IconButton>
          </Box>)}
          <Box sx={{ ...groupRowSx, bgcolor: 'action.hover' }}>
            <TextField fullWidth size="small" label={t('New group name')} value={newGroup} onChange={(event) => setNewGroup(event.target.value)} />
            <TextField fullWidth size="small" label={t('Bootstrap DNS (optional)')} placeholder="1.1.1.1"
              value={newBootstrap} onChange={(event) => setNewBootstrap(event.target.value)} />
            <Button variant="outlined" startIcon={<AddIcon />} onClick={addGroup} sx={{ justifySelf: { xs: 'stretch', md: 'end' }, whiteSpace: 'nowrap' }}>
              {t('Add group')}
            </Button>
          </Box>
        </Box>

        {config.groups.map((group) => {
          const members = orderedMembers(config, group);
          const count = config.group_parallel?.[group];
          return <Box key={`order-${group}`} sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 2, p: 2 }}>
            <Stack spacing={1.5}>
              <Typography variant="subtitle1">{group}: {t('Upstream query order')}</Typography>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems={{ sm: 'center' }}>
                <FormControlLabel control={<Switch checked={count !== undefined} disabled={members.length === 0}
                  onChange={(event) => setConfig((previous) => {
                    const group_parallel = { ...previous.group_parallel };
                    if (event.target.checked) group_parallel[group] = 1;
                    else delete group_parallel[group];
                    return { ...previous, group_parallel };
                  })} />} label={t('Query in order until an IP is found')} />
                {count !== undefined ? <TextField size="small" type="number" label={t('Servers queried in parallel')}
                  value={count} inputProps={{ min: 1, max: members.length }} sx={{ width: 230 }}
                  helperText={t('1 means strictly sequential; larger values query batches in order.')}
                  onChange={(event) => setConfig((previous) => ({ ...previous, group_parallel: {
                    ...previous.group_parallel, [group]: Math.max(1, Math.min(members.length, Number(event.target.value) || 1)),
                  } }))} /> : null}
              </Stack>
              {members.map((endpoint, index) => <Stack key={endpoint} direction="row" spacing={1} alignItems="center">
                <Typography variant="body2" sx={{ minWidth: 25 }}>{index + 1}.</Typography>
                <Typography variant="body2" sx={{ flex: 1, overflowWrap: 'anywhere' }}>{endpoint}</Typography>
                <IconButton size="small" disabled={index === 0} aria-label={`${t('Move up')} ${endpoint}`}
                  onClick={() => setConfig((previous) => {
                    const order = orderedMembers(previous, group);
                    [order[index - 1], order[index]] = [order[index], order[index - 1]];
                    return { ...previous, group_order: { ...previous.group_order, [group]: order } };
                  })}><ArrowUpwardIcon fontSize="small" /></IconButton>
                <IconButton size="small" disabled={index === members.length - 1} aria-label={`${t('Move down')} ${endpoint}`}
                  onClick={() => setConfig((previous) => {
                    const order = orderedMembers(previous, group);
                    [order[index], order[index + 1]] = [order[index + 1], order[index]];
                    return { ...previous, group_order: { ...previous.group_order, [group]: order } };
                  })}><ArrowDownwardIcon fontSize="small" /></IconButton>
              </Stack>)}
            </Stack>
          </Box>;
        })}

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
              <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} alignItems={{ md: 'flex-start' }}>
                <TextField fullWidth label={t('DNS server address or URL')} value={server.endpoint}
                  onChange={(event) => updateServer(index, { endpoint: event.target.value })}
                  helperText={t('Examples: 1.1.1.1, tls://dns.google:853, https://dns.google/dns-query')} />
                <TextField label={t('Host IP (optional)')} value={server.host_ip}
                  onChange={(event) => updateServer(index, { host_ip: event.target.value })}
                  helperText={t('Connect directly to this IP; leave blank to use the group bootstrap DNS.')} sx={{ minWidth: 200 }} />
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
