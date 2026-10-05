'use client';

import * as React from 'react';
import { Alert, Autocomplete, Button, IconButton, MenuItem, Stack, TextField, Typography } from '@mui/material';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward';
import DragIndicatorIcon from '@mui/icons-material/DragIndicator';
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
  const [draggedRule, setDraggedRule] = React.useState<number | null>(null);
  const [dropRule, setDropRule] = React.useState<number | null>(null);

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

  const moveRule = (from: number, to: number): void => {
    setConfig((previous) => {
      const rules = [...previous.rules];
      rules.splice(to, 0, ...rules.splice(from, 1));
      return { ...previous, rules };
    });
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
    <Typography variant="body2">{t(String.raw`Custom rules have highest priority and are checked from top to bottom. A plain domain matches it and its subdomains; *.example.com matches subdomains only; -.example.com matches the exact domain only. Use regex:^api[0-9]+\.example\.com$ for a POSIX regular expression. Matching queries only use the selected DNS group and fail if it is unavailable.`)}</Typography>
    {groups.length > 0 ? <Typography variant="body2">{t('Managed groups')}: {groups.join(', ')}</Typography> : null}
    {error ? <Alert severity="error">{error}</Alert> : null}
    {message ? <Alert severity="success">{message}</Alert> : null}
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
      <IconButton draggable aria-label={`${t('Drag to reorder')} ${rule.domain || index + 1}`}
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
      <TextField label={t('Domain or regular expression')} value={rule.domain} onChange={(event) => changeRule(index, 'domain', event.target.value)} placeholder="example.com" fullWidth />
      <Autocomplete freeSolo options={groups} inputValue={rule.group}
        onInputChange={(_, value) => changeRule(index, 'group', value)}
        renderInput={(params) => <TextField {...params} label={t('Nameserver group')} />}
        sx={{ minWidth: 190 }} />
      <IconButton aria-label={`${t('Move up')} ${rule.domain || index + 1}`} disabled={index === 0}
        onClick={() => moveRule(index, index - 1)}><ArrowUpwardIcon /></IconButton>
      <IconButton aria-label={`${t('Move down')} ${rule.domain || index + 1}`} disabled={index === config.rules.length - 1}
        onClick={() => moveRule(index, index + 1)}><ArrowDownwardIcon /></IconButton>
      <IconButton aria-label={t('Remove rule')} onClick={() => setConfig((previous) => ({ rules: previous.rules.filter((_, row) => row !== index) }))}><DeleteOutlineIcon /></IconButton>
    </Stack>)}
    <Stack direction="row" spacing={1}>
      <Button onClick={() => setConfig((previous) => ({ rules: [...previous.rules, { domain: '', group: '' }] }))}>{t('Add domain rule')}</Button>
      <Button variant="contained" disabled={busy || saved !== null && JSON.stringify(config) === JSON.stringify(saved)} onClick={() => void save()}>{t('Save')}</Button>
    </Stack>
  </Stack>;
}
