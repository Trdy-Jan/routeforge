/** 登录接口成功、但随后的鉴权请求仍 401 时，说明浏览器没有保存会话 cookie。 */
export function cookieNotSavedHint(protocol: string): string {
  if (protocol === 'http:') {
    return (
      '密码正确，但浏览器没有保存登录状态：当前通过 HTTP 访问，而服务端要求仅在 HTTPS 下发送 cookie。' +
      '请改用 HTTPS 访问，或把环境变量 ROUTEFORGE_COOKIE_SECURE 设为 auto（或 false）后重启服务。'
    )
  }
  return (
    '密码正确，但浏览器没有保存登录状态。请检查浏览器是否禁用了 cookie，' +
    '或反向代理是否改写了 Cookie / Set-Cookie 头。'
  )
}
