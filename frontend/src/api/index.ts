import { request } from './client'
import type {
  FilterMember, ImportResult, NodeItem, Preview, Profile, ProfileDetail, ProfileSummary, RefreshResult,
  Source, SourceInput, SourcePatch, TemplateInfo,
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
  importNodes: (id: number, text: string) =>
    request<ImportResult>('POST', `/api/sources/${id}/nodes/import`, { text }),

  listNodes: (params: { source_id?: number | null; q?: string } = {}) =>
    request<NodeItem[]>('GET', '/api/nodes' + buildQuery(params)),
  updateNode: (id: number, body: { name?: string; enabled?: boolean }) =>
    request<NodeItem>('PATCH', `/api/nodes/${id}`, body),
  deleteNode: (id: number) => request<void>('DELETE', `/api/nodes/${id}`),
  bulkNodes: (ids: number[], enabled: boolean) =>
    request<{ updated: number }>('POST', '/api/nodes/bulk', { ids, enabled }),
  matchNodes: (filter: Omit<FilterMember, 'kind'>) => request<NodeItem[]>('POST', '/api/nodes/match', filter),

  listProfiles: () => request<ProfileSummary[]>('GET', '/api/profiles'),
  createProfile: (name: string) => request<ProfileDetail>('POST', '/api/profiles', { name }),
  getProfile: (id: number) => request<ProfileDetail>('GET', `/api/profiles/${id}`),
  saveProfile: (id: number, profile: Profile) => request<ProfileDetail>('PUT', `/api/profiles/${id}`, profile),
  deleteProfile: (id: number) => request<void>('DELETE', `/api/profiles/${id}`),
  applyTemplate: (id: number, templateId: string) =>
    request<{ profile: ProfileDetail; notes: string[] }>('POST', `/api/profiles/${id}/apply-template`,
      { template_id: templateId }),
  rotateToken: (id: number) => request<ProfileDetail>('POST', `/api/profiles/${id}/rotate-token`),
  preview: (id: number) => request<Preview>('GET', `/api/profiles/${id}/preview`),

  listTemplates: () => request<TemplateInfo[]>('GET', '/api/templates'),
}
