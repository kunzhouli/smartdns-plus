'use client';

import * as React from 'react';
import { Alert, Box, Button, FormControlLabel, IconButton, MenuItem, Stack, Switch, TextField, Typography } from '@mui/material';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import DragIndicatorIcon from '@mui/icons-material/DragIndicator';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward';
import { useTranslation } from 'react-i18next';
import { GeositeConfig, GeositeRule, smartdnsServer } from '@/lib/backend/server';

const defaultConfig: GeositeConfig = {
  source: 'https://github.com/v2fly/domain-list-community/releases/latest/download/dlc.dat',
  github_proxy: '', auto_update: false, interval_hours: 24, rules: [],
};

export function GeositeSettings(): React.JSX.Element {
  const { t } = useTranslation();
  const [config, setConfig] = React.useState<GeositeConfig>(defaultConfig);
  const [savedConfig, setSavedConfig] = React.useState<GeositeConfig | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState('');
  const [message, setMessage] = React.useState('');
  const [draggedRule, setDraggedRule] = React.useState<number | null>(null);
  const [dropRule, setDropRule] = React.useState<number | null>(null);

  React.useEffect(() => {
    void smartdnsServer.GetGeositeConfig().then((result) => {
      if (result.data) { setConfig(result.data); setSavedConfig(result.data); }
      if (result.error) setError(smartdnsServer.getErrorMessage(result.error));
    });
  }, []);

  const change = (key: keyof GeositeConfig, value: string | number | boolean): void => {
    setConfig((previous) => ({ ...previous, [key]: value }));
  };

  const changeRule = (index: number, key: keyof GeositeRule, value: string): void => {
    setConfig((previous) => ({ ...previous, rules: previous.rules.map((rule, row) => row === index ? { ...rule, [key]: value } : rule) }));
  };

  const moveRule = (from: number, to: number): void => {
    setConfig((previous) => {
      const rules = [...previous.rules];
      rules.splice(to, 0, ...rules.splice(from, 1));
      return { ...previous, rules };
    });
  };

  const run = async (action: 'save' | 'update'): Promise<void> => {
    setBusy(true);
    setError('');
    setMessage('');
    const result = action === 'save' ? await smartdnsServer.SaveGeositeConfig(config) : await smartdnsServer.UpdateGeosite();
    if (result.error) setError(smartdnsServer.getErrorMessage(result.error));
    else {
      if (result.data) { setConfig(result.data); setSavedConfig(result.data); }
      setMessage(t(action === 'save' ? 'GeoSite settings saved.' : 'GeoSite data updated.'));
    }
    setBusy(false);
  };

  const settings = (value: GeositeConfig): string => JSON.stringify({
    source: value.source, github_proxy: value.github_proxy, auto_update: value.auto_update,
    interval_hours: value.interval_hours, rules: value.rules,
  });
  const hasUnsavedChanges = savedConfig === null || settings(config) !== settings(savedConfig);

  return <Stack spacing={2} sx={{ maxWidth: 850 }}>
    <Typography variant="body2">{t('Create a server group under Upstream Servers before routing GeoSite categories to it.')}</Typography>
    {error ? <Alert severity="error">{error}</Alert> : null}
    {message ? <Alert severity="success">{message}</Alert> : null}
    <TextField fullWidth label={t('GeoSite source URL')} value={config.source} onChange={(event) => change('source', event.target.value)} />
    <TextField fullWidth label={t('GitHub proxy prefix')} value={config.github_proxy} onChange={(event) => change('github_proxy', event.target.value)} helperText={t('Optional URL prefix used only for github.com downloads.')} />
    <Stack direction="row" spacing={2} alignItems="center">
      <FormControlLabel control={<Switch checked={config.auto_update} onChange={(event) => change('auto_update', event.target.checked)} />} label={t('Automatic updates')} />
      <TextField label={t('Update interval (hours)')} type="number" size="small" value={config.interval_hours} onChange={(event) => change('interval_hours', Number(event.target.value))} inputProps={{ min: 1, max: 8760 }} sx={{ width: 190 }} />
    </Stack>
    <Typography variant="body2">{config.has_data ? t('Data ready') : t('No GeoSite data yet')}{config.last_update ? ` · ${t('Last update')}: ${new Date(config.last_update * 1000).toLocaleString()}` : ''}</Typography>
    <Typography variant="h6">{t('GeoSite rules')}</Typography>
    {config.rules.map((rule, index) => <Stack key={index} direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems="center"
      onDragOver={(event) => {
        if (draggedRule === null) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = 'move';
        setDropRule(index);
      }}
      onDrop={(event) => {
        event.preventDefault();
        if (draggedRule !== null && draggedRule !== index) moveRule(draggedRule, index);
        setDraggedRule(null);
        setDropRule(null);
      }}
      sx={{ borderRadius: 1, outline: dropRule === index && draggedRule !== index ? '2px solid' : 'none',
        outlineColor: 'primary.main', opacity: draggedRule === index ? 0.5 : 1 }}>
      <IconButton draggable aria-label={`${t('Drag to reorder')} ${rule.site || index + 1}`}
        title={t('Drag to reorder')} sx={{ cursor: 'grab', alignSelf: { xs: 'flex-start', sm: 'center' } }}
        onDragStart={(event) => {
          event.dataTransfer.effectAllowed = 'move';
          event.dataTransfer.setData('text/plain', String(index));
          setDraggedRule(index);
        }}
        onDragEnd={() => { setDraggedRule(null); setDropRule(null); }}><DragIndicatorIcon /></IconButton>
      <TextField select size="small" label={t('Priority')} value={index + 1} sx={{ minWidth: 90 }}
        onChange={(event) => moveRule(index, Number(event.target.value) - 1)}>
        {config.rules.map((_, position) => <MenuItem key={position} value={position + 1}>{position + 1}</MenuItem>)}
      </TextField>
      <TextField label={t('Category')} value={rule.site} onChange={(event) => changeRule(index, 'site', event.target.value)} helperText={index === 0 ? t('Example: geolocation-!cn or category-ads-all@ads') : undefined} fullWidth />
      <TextField select label={t('Action')} value={rule.action} onChange={(event) => changeRule(index, 'action', event.target.value)} sx={{ minWidth: 130 }}>
        <MenuItem value="route">{t('Route')}</MenuItem><MenuItem value="block">{t('Block')}</MenuItem>
      </TextField>
      <TextField label={t('Nameserver group')} disabled={rule.action === 'block'} value={rule.group} onChange={(event) => changeRule(index, 'group', event.target.value)} sx={{ minWidth: 160 }} />
      <IconButton aria-label={`${t('Move up')} ${rule.site || index + 1}`} disabled={index === 0}
        onClick={() => moveRule(index, index - 1)}><ArrowUpwardIcon /></IconButton>
      <IconButton aria-label={`${t('Move down')} ${rule.site || index + 1}`} disabled={index === config.rules.length - 1}
        onClick={() => moveRule(index, index + 1)}><ArrowDownwardIcon /></IconButton>
      <IconButton aria-label={t('Remove rule')} onClick={() => setConfig((previous) => ({ ...previous, rules: previous.rules.filter((_, row) => row !== index) }))}><DeleteOutlineIcon /></IconButton>
    </Stack>)}
    <Box><Button onClick={() => setConfig((previous) => ({ ...previous, rules: [...previous.rules, { site: '', action: 'route', group: '' }] }))}>{t('Add rule')}</Button></Box>
    <Stack direction="row" spacing={1}>
      <Button variant="contained" disabled={busy} onClick={() => void run('save')}>{t('Save')}</Button>
      <Button variant="outlined" disabled={busy || hasUnsavedChanges} onClick={() => void run('update')}>{t('Update GeoSite now')}</Button>
    </Stack>
    {hasUnsavedChanges ? <Typography variant="caption">{t('Save settings before updating.')}</Typography> : null}
  </Stack>;
}
