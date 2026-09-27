import { ArticleOutlined, SettingsOutlined, DnsOutlined, type SvgIconComponent, QueryStatsOutlined, EventNoteOutlined, TerminalOutlined, DevicesOutlined, RuleOutlined } from '@mui/icons-material';

export const navIcons = {
  QueryStats: QueryStatsOutlined,
  EventNote: EventNoteOutlined,
  Dns: DnsOutlined,
  Rule: RuleOutlined,
  Devices: DevicesOutlined,
  Article: ArticleOutlined,
  Settings: SettingsOutlined,
  Terminal: TerminalOutlined,
} as Record<string, SvgIconComponent>;
