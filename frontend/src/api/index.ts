import { request } from './client'
import type {
  FilterMember, ImportItem, ImportResult, ParseResult, LibraryCategory, LibraryIndex, RuleContent, NodeItem, OpenClashSettings, OpenClashSettingsInput, Preview, Profile, ProfileDetail, ProfileSummary, RefreshResult,
  PushStatus, Source, SourceInput, SourcePatch, TemplateInfo,
} from './types'

export function buildQuery(params: Record<string, string | number | null | undefined>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
  return entries.length ? '?' + new URLSearchParams(entries.map(([k, v]) => [k, String(v)])).toString() : ''
}

export const api = {
  login: (password: string) => request<{ ok: boolean }>('POST', '/api/auth/login', { password }),
  logout: () => request<{ ok: boolean }>('POST', '/api/auth/logout'),
  me: () => request<{ admin: boolean }>('GET', '/api/auth/me'),

  listSources: () => request<Source[]>('GET', '/api/sources'),
  createSource: (body: SourceInput) => request<Source>('POST', '/api/sources', body),
  updateSource: (id: number, body: SourcePatch) => request<Source>('PATCH', `/api/sources/${id}`, body),
  deleteSource: (id: number) => request<void>('DELETE', `/api/sources/${id}`),
  refreshSource: (id: number) => request<RefreshResult>('POST', `/api/sources/${id}/refresh`),
  parseNodes: (id: number, text: string) =>
    request<ParseResult>('POST', `/api/sources/${id}/nodes/parse`, { text }),
  importNodes: (id: number, nodes: ImportItem[]) =>
    request<ImportResult>('POST', `/api/sources/${id}/nodes/import`, { nodes }),

  listNodes: (params: { source_id?: number | null; q?: string } = {}) =>
    request<NodeItem[]>('GET', '/api/nodes' + buildQuery(params)),
  updateNode: (id: number, body: { name?: string; enabled?: boolean; config?: string }) =>
    request<NodeItem>('PATCH', `/api/nodes/${id}`, body),
  getNodeConfig: (id: number) => request<{ config: string }>('GET', `/api/nodes/${id}/config`),
  deleteNode: (id: number) => request<void>('DELETE', `/api/nodes/${id}`),
  bulkNodes: (ids: number[], enabled: boolean) =>
    request<{ updated: number }>('POST', '/api/nodes/bulk', { ids, enabled }),
  bulkDeleteNodes: (ids: number[]) =>
    request<{ deleted: number; skipped: number }>('POST', '/api/nodes/bulk-delete', { ids }),
  matchNodes: (filter: Omit<FilterMember, 'kind'>) => request<NodeItem[]>('POST', '/api/nodes/match', filter),

  listProfiles: () => request<ProfileSummary[]>('GET', '/api/profiles'),
  createProfile: (name: string) => request<ProfileDetail>('POST', '/api/profiles', { name }),
  getProfile: (id: number) => request<ProfileDetail>('GET', `/api/profiles/${id}`),
  saveProfile: (id: number, profile: Profile) => request<ProfileDetail>('PUT', `/api/profiles/${id}`, profile),
  cloneProfile: (id: number, name?: string) =>
    request<ProfileDetail>('POST', `/api/profiles/${id}/clone`, name ? { name } : {}),
  deleteProfile: (id: number) => request<void>('DELETE', `/api/profiles/${id}`),
  applyTemplate: (id: number, templateId: string) =>
    request<{ profile: ProfileDetail; notes: string[] }>('POST', `/api/profiles/${id}/apply-template`,
      { template_id: templateId }),
  rotateToken: (id: number) => request<ProfileDetail>('POST', `/api/profiles/${id}/rotate-token`),
  preview: (id: number) => request<Preview>('GET', `/api/profiles/${id}/preview`),

  listTemplates: () => request<TemplateInfo[]>('GET', '/api/templates'),

  ruleLibrary: () => request<LibraryIndex>('GET', '/api/rule-library'),
  refreshRuleLibrary: () => request<LibraryIndex>('POST', '/api/rule-library/refresh'),
  ruleContent: (category: LibraryCategory, name: string, params: { q?: string; offset?: number; limit?: number } = {}) =>
    request<RuleContent>(
      'GET',
      `/api/rule-library/${category}/${encodeURIComponent(name)}/content` + buildQuery(params),
    ),

  getOpenClash: () => request<OpenClashSettings>('GET', '/api/openclash/settings'),
  saveOpenClash: (body: OpenClashSettingsInput) => request<OpenClashSettings>('PUT', '/api/openclash/settings', body),
  testOpenClash: () => request<{ ok: boolean; message: string }>('POST', '/api/openclash/test'),
  pushOpenClash: () => request<PushStatus>('POST', '/api/openclash/push'),
}
