export type SourceKind = 'manual' | 'subscription'

export interface UserInfo {
  upload?: number
  download?: number
  total?: number
  expire?: number
}

export interface Source {
  id: number
  kind: SourceKind
  name: string
  url: string | null
  refresh_interval: number
  user_agent: string
  last_fetched_at: string | null
  last_error: string | null
  userinfo: UserInfo | null
  node_count: number
}

export interface SourceInput {
  kind: SourceKind
  name: string
  url?: string
  refresh_interval?: number
  user_agent?: string
}

export type SourcePatch = Partial<Pick<Source, 'name' | 'refresh_interval' | 'user_agent'>> & { url?: string }

export interface LineError {
  line: string
  message: string
}

export interface ImportResult {
  added: number
  errors: LineError[]
}

export interface RefreshResult {
  ok: boolean
  error: string | null
  added: number
  updated: number
  removed: number
  parse_errors: LineError[]
}

export interface NodeItem {
  id: number
  source_id: number
  name: string
  type: string
  server: string
  port: number
  enabled: boolean
  position: number
  data: Record<string, unknown>
}

export interface FilterMember {
  kind: 'filter'
  source_id: number | null
  name_regex: string
  exclude_regex: string | null
}

export type Member =
  | { kind: 'node'; node_id: number }
  | { kind: 'group'; name: string }
  | { kind: 'builtin'; name: 'DIRECT' | 'REJECT' }
  | FilterMember

export type GroupType = 'select' | 'url-test' | 'fallback' | 'load-balance'

export interface ProxyGroup {
  name: string
  type: GroupType
  members: Member[]
  url: string
  interval: number
  tolerance: number
}

export const RULE_TYPES = [
  'DOMAIN', 'DOMAIN-SUFFIX', 'DOMAIN-KEYWORD', 'IP-CIDR', 'IP-CIDR6',
  'GEOSITE', 'GEOIP', 'PROCESS-NAME', 'RULE-SET', 'MATCH',
] as const

export type RuleType = (typeof RULE_TYPES)[number]

/** 可填多个值的规则类型：值存于 values，生成配置时按值展开为多行。 */
export const MULTI_VALUE_RULE_TYPES: readonly RuleType[] = [
  'DOMAIN', 'DOMAIN-SUFFIX', 'DOMAIN-KEYWORD', 'IP-CIDR', 'IP-CIDR6', 'PROCESS-NAME',
]

export interface Rule {
  type: RuleType
  /** 单值类型（RULE-SET / GEOSITE / GEOIP）使用 */
  value: string
  /** 多值类型使用 */
  values: string[]
  target: string
  no_resolve: boolean
}

export interface RuleProvider {
  name: string
  behavior: 'domain' | 'ipcidr' | 'classical'
  format: 'yaml' | 'text' | 'mrs'
  url: string
  interval: number
}

export interface Chain {
  node: { kind: 'node'; node_id: number }
  via: { kind: 'group'; name: string } | { kind: 'node'; node_id: number }
}

export interface Profile {
  name: string
  groups: ProxyGroup[]
  rules: Rule[]
  rule_providers: RuleProvider[]
  chains: Chain[]
}

export interface ProfileSummary {
  id: number
  name: string
  token: string
}

export interface ProfileDetail {
  id: number
  token: string
  last_good_at: string | null
  profile: Profile
}

export type IssueSection = 'groups' | 'rules' | 'providers' | 'chains'

export interface Issue {
  section: IssueSection
  message: string
  hint: string
}

export interface Preview {
  ok: boolean
  content: string | null
  errors: string[]
  warnings: string[]
  issues: Issue[]
}

export interface TemplateInfo {
  id: string
  name: string
  description: string
}

export interface PushStatus {
  at: string
  ok: boolean
  message: string
  trigger: 'auto' | 'manual'
}

export interface OpenClashSettings {
  router_url: string
  username: string
  has_password: boolean
  config_name: string
  profile_id: number | null
  auto_push: boolean
  status: PushStatus | null
}

export interface OpenClashSettingsInput {
  router_url: string
  username: string
  password?: string
  config_name: string
  profile_id: number | null
  auto_push: boolean
}

export type LibraryCategory = 'geosite' | 'geoip' | 'geo-lite'

export interface LibraryItem {
  category: LibraryCategory
  name: string
  behavior: 'domain' | 'ipcidr'
  url: string
}

export interface LibraryIndex {
  updated_at: string | null
  error: string | null
  items: LibraryItem[]
}

export interface RuleContent {
  total: number
  lines: string[]
  truncated: boolean
}
