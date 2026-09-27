'use client';

import * as React from 'react';
import { Alert, Autocomplete, Button, IconButton, Stack, TextField, Typography } from '@mui/material';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import { useTranslation } from 'react-i18next';
import { DomainRoutesConfig, smartdnsServer } from '@/lib/backend/server';

export function DomainRoutesSettings(): React.JSX.Element {
  const { t } = useTranslation();
  const [config, setConfig] = React.useState<DomainRoutesConfig>({ rules: [] });
  const [saved, setSaved] = React.useState<DomainRoutesConfig | null>(null);
  const [groups, setGroups] = React.useState<string[]>([]);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState('');
  const [message, setMessage] = React.useState('');

  React.useEffect(() => {
    void smartdnsServer.GetDomainRoutesConfig().then((result) => {
      if (result.data) { setConfig(result.data); setSaved(result.data); }
      if (result.error) setError(smartdnsServer.getErrorMessage(result.error));
    });
    void smartdnsServer.GetUpstreamConfig().then((result) => {
      if (result.data) setGroups(result.data.groups);
    });
  }, []);

  const changeRule = (index: number, field: 'domain' | 'group', value: string): void => {
    setConfig((previous) => ({ rules: previous.rules.map((rule, row) => row === index ? { ...rule, [field]: value } : rule) }));
  };

  const save = async (): Promise<void> => {
    setBusy(true);
    setError('');
    setMessage('');
    const result = await smartdnsServer.SaveDomainRoutesConfig(config);
    if (result.error) setError(smartdnsServer.getErrorMessage(result.error));
    else if (result.data) { setConfig(result.data); setSaved(result.data); setMessage(t('Domain rules saved.')); }
    setBusy(false);
  };

  return <Stack spacing={2} sx={{ maxWidth: 850 }}>
    <Typography variant="body2">{t('Route a domain to an existing DNS server group. A plain domain matches it and its subdomains; *.example.com matches subdomains only; -.example.com matches the exact domain only.')}</Typography>
    {groups.length > 0 ? <Typography variant="body2">{t('Managed groups')}: {groups.join(', ')}</Typography> : null}
    {error ? <Alert severity="error">{error}</Alert> : null}
    {message ? <Alert severity="success">{message}</Alert> : null}
    {config.rules.map((rule, index) => <Stack key={index} direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems="center">
      <TextField label={t('Domain')} value={rule.domain} onChange={(event) => changeRule(index, 'domain', event.target.value)} placeholder="example.com" fullWidth />
      <Autocomplete freeSolo options={groups} inputValue={rule.group}
        onInputChange={(_, value) => changeRule(index, 'group', value)}
        renderInput={(params) => <TextField {...params} label={t('Nameserver group')} />}
        sx={{ minWidth: 190 }} />
      <IconButton aria-label={t('Remove rule')} onClick={() => setConfig((previous) => ({ rules: previous.rules.filter((_, row) => row !== index) }))}><DeleteOutlineIcon /></IconButton>
    </Stack>)}
    <Stack direction="row" spacing={1}>
      <Button onClick={() => setConfig((previous) => ({ rules: [...previous.rules, { domain: '', group: '' }] }))}>{t('Add domain rule')}</Button>
      <Button variant="contained" disabled={busy || saved !== null && JSON.stringify(config) === JSON.stringify(saved)} onClick={() => void save()}>{t('Save')}</Button>
    </Stack>
  </Stack>;
}
