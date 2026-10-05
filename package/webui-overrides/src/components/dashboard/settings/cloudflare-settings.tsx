'use client';

import * as React from 'react';
import { Alert, Box, Button, CircularProgress, FormControlLabel, Stack, Switch, TextField, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { CloudflareConfig, smartdnsServer } from '@/lib/backend/server';

const defaults: CloudflareConfig = {
  enabled: false, schedule_enabled: false, run_time: '03:00', interval_days: 1, ipv6_enabled: true, threads: 40,
};

function settings(value: CloudflareConfig): string {
  return JSON.stringify({ enabled: value.enabled, schedule_enabled: value.schedule_enabled, run_time: value.run_time,
    interval_days: value.interval_days, ipv6_enabled: value.ipv6_enabled, threads: value.threads });
}

export function CloudflareSettings(): React.JSX.Element {
  const { t } = useTranslation();
  const [config, setConfig] = React.useState<CloudflareConfig>(defaults);
  const [saved, setSaved] = React.useState<CloudflareConfig | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState('');
  const [message, setMessage] = React.useState('');
  const wasRunning = React.useRef(false);
  const logBox = React.useRef<HTMLPreElement>(null);
  const followLog = React.useRef(true);

  React.useEffect(() => {
    if (followLog.current && logBox.current) logBox.current.scrollTop = logBox.current.scrollHeight;
  }, [config.log]);

  React.useEffect(() => {
    let active = true;
    void smartdnsServer.GetCloudflareConfig().then((result) => {
      if (!active) return;
      if (result.data) { setConfig(result.data); setSaved(result.data); }
      if (result.error) setError(smartdnsServer.getErrorMessage(result.error));
    });
    let polling = false;
    const timer = window.setInterval(() => {
      if (polling) return;
      polling = true;
      void smartdnsServer.GetCloudflareConfig().then((result) => {
        if (!active || !result.data) return;
        if (wasRunning.current && !result.data.running) setMessage('');
        wasRunning.current = Boolean(result.data.running);
        const { running, log, last_attempt, last_success, last_error, best_v4, best_v6 } = result.data;
        setConfig((previous) => ({ ...previous, running, log, last_attempt, last_success, last_error, best_v4, best_v6 }));
      }).finally(() => { polling = false; });
    }, 1000);
    return () => { active = false; window.clearInterval(timer); };
  }, []);

  const change = (key: keyof CloudflareConfig, value: string | number | boolean): void => {
    setConfig((previous) => ({ ...previous, [key]: value }));
  };

  const run = async (action: 'save' | 'test'): Promise<void> => {
    setBusy(true);
    setError('');
    setMessage('');
    const result = action === 'save' ? await smartdnsServer.SaveCloudflareConfig(config) : await smartdnsServer.RunCloudflareSpeedTest();
    if (result.error) setError(smartdnsServer.getErrorMessage(result.error));
    else {
      if (result.data) { setConfig(result.data); setSaved(result.data); wasRunning.current = Boolean(result.data.running); }
      setMessage(t(action === 'save' ? 'Cloudflare settings saved.' : 'Cloudflare speed test started.'));
    }
    setBusy(false);
  };

  const dirty = saved === null || settings(saved) !== settings(config);
  const date = (timestamp?: number): string => timestamp ? new Date(timestamp * 1000).toLocaleString() : t('Never');

  return <Stack spacing={2} sx={{ maxWidth: 750 }}>
    <Typography variant="body2">{t('When an A or AAAA answer belongs to a Cloudflare IP range, return the fastest measured IP of the same family. Other answers stay unchanged.')}</Typography>
    {error ? <Alert severity="error">{error}</Alert> : null}
    {message ? <Alert severity="success">{message}</Alert> : null}
    {config.cfst_available ? null : <Alert severity="warning">{t('CloudflareSpeedTest binary is unavailable on this server.')}</Alert>}
    <FormControlLabel control={<Switch checked={config.enabled} onChange={(event) => change('enabled', event.target.checked)} />} label={t('Enable Cloudflare acceleration')} />
    <FormControlLabel control={<Switch checked={config.schedule_enabled} onChange={(event) => change('schedule_enabled', event.target.checked)} />} label={t('Run automatically on a schedule')} />
    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
      <TextField disabled={!config.schedule_enabled} label={t('Run at (server time)')} type="time" value={config.run_time} onChange={(event) => change('run_time', event.target.value)} InputLabelProps={{ shrink: true }} />
      <TextField disabled={!config.schedule_enabled} label={t('Repeat every (days)')} type="number" value={config.interval_days} onChange={(event) => change('interval_days', Number(event.target.value))} inputProps={{ min: 1, max: 365 }} />
      <TextField label={t('Test threads')} type="number" value={config.threads} onChange={(event) => change('threads', Number(event.target.value))} inputProps={{ min: 1, max: 200 }} />
    </Stack>
    <FormControlLabel control={<Switch checked={config.ipv6_enabled} onChange={(event) => change('ipv6_enabled', event.target.checked)} />} label={t('Measure IPv6 too')} />
    <Typography variant="body2">{t('Best IPv4')}: {config.best_v4 || '—'} · {t('Best IPv6')}: {config.best_v6 || '—'}</Typography>
    <Typography variant="body2">{t('Last attempt')}: {date(config.last_attempt)} · {t('Last success')}: {date(config.last_success)}</Typography>
    {config.last_error ? <Alert severity="warning">{config.last_error}</Alert> : null}
    <Stack direction="row" spacing={1} alignItems="center">
      <Button variant="contained" disabled={busy || config.running} onClick={() => void run('save')}>{t('Save')}</Button>
      <Button variant="outlined" disabled={busy || config.running || dirty || !config.cfst_available} onClick={() => void run('test')}>{t('Run speed test now')}</Button>
      {busy || config.running ? <CircularProgress size={20} /> : null}
    </Stack>
    {dirty ? <Typography variant="caption">{t('Save settings before testing.')}</Typography> : null}
    <Typography variant="caption">{t('A speed test may take several minutes and uses download bandwidth.')}</Typography>
    <Typography variant="h6">{t('Run log')}</Typography>
    <Box component="pre" ref={logBox} aria-live="polite" onScroll={(event) => {
      const element = event.currentTarget;
      followLog.current = element.scrollHeight - element.scrollTop - element.clientHeight < 32;
    }} sx={{ bgcolor: 'action.hover', borderRadius: 1, p: 2, m: 0, maxHeight: 360, overflow: 'auto', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', fontFamily: 'monospace', fontSize: 12 }}>
      {config.log || t('No run log yet.')}
    </Box>
  </Stack>;
}
